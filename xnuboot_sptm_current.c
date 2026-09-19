#include "qemu/osdep.h"
#include "exec/memattrs.h"
#include "hw/arm/machines-qom.h"
#include "system/address-spaces.h"
#include "cpu.h"
#include <sys/mman.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <inttypes.h>
#include "qemu/bitops.h"
#include "xnu/boot/xnuboot.h"
#include "xnu/boot/args.h"
#include "xnu/boot/trustcache.h"
#include "xnu/apple_dtree.h"
#include "xnu/mach-o/loader.h"
#include "xnu/mach-o/macho_arm64.h"
#include "xnu/patch.h"
#include "xnu/macho.h"

// #define DEBUG_MEMORY_LAYOUT

// This will move the virtual base to place the boot kc *exactly* at the macho's virtual base.
// Only use this for debugging early kernel boot- it can cause SPTM/ TXM to freak out during launchd
// #define LINEUP_BOOTKC_NICELY

#define PAGE_SIZE ((DARWIN_PAGE_SIZE))

// SPTM overrides the virtual base for TXM/ BootKC:
// TXM actual virt addr = sptm.virtlo + 1 * SPTM_EXPECTED_STRIDE
// BKC actual virt addr = sptm.virtlo + 2 * SPTM_EXPECTED_STRIDE
#define SPTM_EXPECTED_STRIDE    0x10000000

#define GET_L2_PT_INDEX(a)      (( ((a)) & ( (BIT(36)-1)) ))
#define STRIP_L2_PT_INDEX(a)    (( ((a)) & (~(BIT(36)-1)) ))

static void alloc_ram(Object *cpuobj, hwaddr base, size_t len) {
    MemoryRegion *ram_main = get_system_memory();
    MemoryRegion *ram_subreg = g_new(MemoryRegion, 1);
    memory_region_init_ram(ram_subreg, NULL, "dram", len, &error_fatal);
    memory_region_add_subregion(ram_main, base, ram_subreg);
}

static hwaddr vtop(macho_info_t *mi, hwaddr v) {
    return mi->physlo + (v - mi->virtlo);
}

static void set_adt_mmap(struct dtree_node *memory_map, const char *reg_name, hwaddr paddr, size_t sz) {
    u64 *map_prop = adt_get_prop_val(memory_map, reg_name);
    if (!map_prop) {
        fprintf(stderr, "dtree is missing /chosen/memory-map/%s\n", reg_name);
        exit(1);
    }
    assert(map_prop);
    map_prop[0] = paddr;
    map_prop[1] = sz;
#ifdef DEBUG_MEMORY_LAYOUT
    printf("%16s:\t0x%016llX (0x%016llX)\n", reg_name, map_prop[0], map_prop[1]);
#endif // DEBUG_MEMORY_LAYOUT
}

static trust_cache_offsets_t get_tcinfo(void) {
    assert (8 == sizeof(trust_cache_offsets_t));
    return (trust_cache_offsets_t) {
        .num_caches = 1,
        .offsets = {sizeof(trust_cache_offsets_t)},
    };
}

// Push something from the "blob" into the ADT map
static void push_adt_mmap(struct dtree_node *memory_map, const char *reg_name, hwaddr *paddr, hwaddr *last_map_entry) {
    assert(0 == ((*paddr) & (PAGE_SIZE-1)));
    set_adt_mmap(memory_map, reg_name, *last_map_entry, *paddr - *last_map_entry);
    *last_map_entry = *paddr;
}

// Push a macho segment into the "blob"
static void push_seg(hwaddr *paddr, macho_info_t *mi, const char *segname) {
    seg_t *s = macho_find_seg(mi->macho, segname);
    macho_load_seg_at(mi, s, *paddr);
    *paddr += s->vmsize;
}

static hwaddr get_seglen(macho_info_t *mi, const char *segname) {
    seg_t *s = macho_find_seg(mi->macho, segname);
    if (s) return s->vmsize;
    return 0;
}


// Apply CL4's DYLD chained fixups to its __DATA (component 'tadk'), rebasing
// each pointer to the physical address where its target segment was loaded.
// CL4 runs MMU-off at load, and __TEXT/__DATA are non-contiguous in physical
// (phase1/phase2 split), so rebase per-segment. ptr_format 12
// (ARM64E_USERLAND24): target field = offset from the 0xc0000000 image base.
/*
 * EXPERIMENTAL PROBE (not a real fix): SPTM hands the SK/CL4 genter x1=0 in our
 * synthesized boot, so CL4's boot-info tag3 (a pointer to a domain descriptor) is
 * null and CL4 faults dereferencing it. To learn the next layer we synthesize a
 * minimal domain descriptor {domain_id, 0...} and inject x1 -> &descriptor at the
 * exact ERET into CL4's entrypoint (see target/arm/tcg/helper-a64.c). The domain
 * id defaults to 0xc00000001 and can be overridden with $CL4_DOMAIN_ID.
 */
uint64_t g_cl4_entry_pc = 0;
uint64_t g_cl4_x1_inject = 0;
/* CL4 __mod_init_func constructor-runner trampoline (see ios27-cl4-secure-world/
 * experiments/cl4-ctor-runner). Saves x0/x1, installs a scratch stack, calls the
 * 11 __mod_init_func ctors in order, restores x0/x1, sets SP=0, jumps to CL4 entry.
 * The 4-quad literal pool at +CL4_TRAMP_POOL_OFF is filled by the loader. */
uint64_t g_cl4_tramp_pc = 0;
int      g_cl4_ctors_done = 0;
uint64_t g_cl4_tpidr = 0;   /* fake empty per-thread context for the ctor run */
uint64_t g_cl4_tpidrro = 0; /* fake read-only per-thread context (TPIDRRO_EL0) */
static const uint8_t cl4_ctor_trampoline[] = {
    0xf3, 0x03, 0x00, 0xaa, 0xf4, 0x03, 0x01, 0xaa, 0x15, 0x02, 0x00, 0x58,
    0x36, 0x02, 0x00, 0x58, 0x49, 0x02, 0x00, 0x58, 0x3f, 0x01, 0x00, 0x91,
    0xbf, 0x02, 0x16, 0xeb, 0x82, 0x00, 0x00, 0x54, 0xb7, 0x86, 0x40, 0xf8,
    0xe0, 0x02, 0x3f, 0xd6, 0xfc, 0xff, 0xff, 0x17, 0xe0, 0x03, 0x13, 0xaa,
    0xe1, 0x03, 0x14, 0xaa, 0xe9, 0x03, 0x1f, 0xaa, 0x3f, 0x01, 0x00, 0x91,
    0x30, 0x01, 0x00, 0x58, 0x5f, 0xd0, 0x1b, 0xd5, 0x00, 0x02, 0x1f, 0xd6,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
#define CL4_TRAMP_POOL_OFF 0x48
#define CL4_TRAMP_SIZE     0x68

static void apply_cl4_fixups(u8 *macho, hwaddr rx_phys, hwaddr rw_phys,
                             hwaddr le_phys) {
    sect_t *cf = macho_find_sect(macho, "__TEXT", "__chain_fixups");
    if (!cf || !cf->size) { printf("[cl4] no __chain_fixups\n"); return; }
    u8 *fx = macho + cf->offset;
    u32 starts_offset = *(u32*)(fx + 4);
    u8 *si = fx + starts_offset;
    u32 seg_count = *(u32*)si;
    u32 *seg_offs = (u32*)(si + 4);
    u32 applied = 0;
    for (u32 sg = 0; sg < seg_count; sg++) {
        if (!seg_offs[sg]) continue;
        u8 *seg = si + seg_offs[sg];
        u16 page_size = *(u16*)(seg + 4);
        u64 seg_off   = *(u64*)(seg + 8);   // vmaddr-relative segment base
        u16 page_count = *(u16*)(seg + 20);
        u16 *page_start = (u16*)(seg + 22);
        // Only the __DATA segment (seg_off 0x68c000) carries our chains.
        if (seg_off != 0x68c000) continue;
        for (u16 pi = 0; pi < page_count; pi++) {
            if (page_start[pi] == 0xFFFF) continue;
            u64 off = (u64)pi * page_size + page_start[pi];
            for (;;) {
                hwaddr slot = rw_phys + off;   // __DATA content base = rw_phys
                u64 raw = 0;
                address_space_read(&address_space_memory, slot,
                                   MEMTXATTRS_UNSPECIFIED, &raw, 8);
                u32 next = (raw >> 51) & 0x7ff;
                bool auth = (raw >> 63) & 1;
                u64 target = auth ? (raw & 0xffffffffULL)
                                  : (raw & 0x7ffffffffffULL);
                hwaddr nv;
                if (target < 0x68c000)       nv = rx_phys + target;
                else if (target < 0x6d4000)  nv = rw_phys + (target - 0x68c000);
                else                         nv = le_phys + (target - 0x6d4000);
                address_space_write(&address_space_memory, slot,
                                    MEMTXATTRS_UNSPECIFIED, &nv, 8);
                applied++;
                if (!next) break;
                off += (u64)next * 8;
            }
        }
    }
    printf("[cl4] applied %u chained fixups to __DATA "
           "(rx 0x%llX rw 0x%llX le 0x%llX)\n", applied,
           (unsigned long long)rx_phys, (unsigned long long)rw_phys,
           (unsigned long long)le_phys);
    fflush(stdout);
}

static void arm_load_xnu_sptm(ARMCPU *cpu, MachineState *ms, struct xnu_boot_info *info) {
    u8 *dtree = (u8*)info->dtree_f.buf;
    u8 *macho_sptm = (u8*)info->sptm_f.buf;
    u8 *macho_bkc = (u8*)info->bootkc_f.buf;
    u8 *macho_txm = (u8*)info->txm_f.buf;

    alloc_ram(OBJECT(cpu), info->dram_base, info->dram_size);

    macho_info_t bkc_mi  = macho_get_info(macho_bkc);
    macho_info_t txm_mi  = macho_get_info(macho_txm);
    macho_info_t sptm_mi = macho_get_info(macho_sptm);
    bool have_cl4 = (info->cl4_f.buf != NULL);
    macho_info_t cl4_mi;
    hwaddr cl4_rx_phys = 0, cl4_rw_phys = 0, cl4_le_phys = 0;
    if (have_cl4) {
        macho_verify_header((u8*)info->cl4_f.buf, false);
        cl4_mi = macho_get_info((u8*)info->cl4_f.buf);
    }

    hwaddr args_base_phys  = 0;
    hwaddr dtree_base_phys = 0;
    hwaddr tc_base_phys = 0;
    hwaddr rd_base_phys = 0;
    hwaddr fb_base_phys = 0;

    hwaddr tc_size_rounded = ROUND_NEXT_PAGE(sizeof(trust_cache_offsets_t) + info->tc_f.len);
    hwaddr dtree_size_rounded = ROUND_NEXT_PAGE(info->dtree_f.len);

    macho_verify_header(macho_bkc, true);
    macho_verify_header(macho_txm, false);
    macho_verify_header(macho_sptm, false);
    patch_kc(macho_bkc);

    struct dtree_node *map = adt_find_node((struct dtree_node*)dtree, "chosen/memory-map");
    hwaddr blob_head = info->dram_base;
    hwaddr blob_tail = blob_head;

    // PUSH_SEG(m,s): push a segment into the blob
    // m: which macho_info_t to search for the segment in
    // s: which segment to look for
#define PUSH_SEG(m,s) push_seg(&blob_head, &m##_mi, s)

    // SEGLEN(m,s): get length of a segment
    // m: which macho_info_t to search for the segment in
    // s: which segment to look for
    // Returns the number of bytes PUSH_SEG will consume when pushing this
    // segment without actually pushing it to the blob
#define SEGLEN(m,s) get_seglen(&m##_mi, s)

    // END_ENTRY(n): mark the end of an ADT memory map entry
    // n: name of the ADT entry we are ending
#define END_ENTRY(n) push_adt_mmap(map, n, &blob_head, &blob_tail)

    // SKIP(n): skip n bytes in the blob
#define SKIP(n) \
    blob_head += n; \
    blob_tail = blob_head;

    // Ideally, the boot KC is loaded *exactly* where the macho wants it,
    // because that's the file we're going to be doing the most debugging in,
    // and relocating fileset KCs is annoying.
    //
    // To make that happen, we need SPTM to be loaded 2*SPTM_EXPECTED_STRIDE
    // before BKC's virtlo.
    //
    // We can make this happen by:
    //  1. Setting the L2 page table index (bits [35:0]) to match exactly
    //  2. Setting the upper bits ([63:36]) in bargs.virtBase to
    //     2*SPTM_EXPECTED_STRIDE before where bkc wants to be loaded.
    //
    // Since we can't arbitrarily place SPTM-ro (the start of SPTM) wherever we
    // want, we need to shift the entire blob forward by enough to put it where
    // we want.
    //
    // Specifically, we need:
    // GET_L2_PT_INDEX(SPTM-ro) == GET_L2_PT_INDEX(bkc_mi.virtlo)
    //
    // First, calculate where SPTM-ro ends up if we do nothing,
    // then skip however many bytes we need to make it end up where we want
    //
    // Sliding the blob forward in memory also seems to prevent random TXM
    // panics during early launchd.
    hwaddr bytes_before_sptm =
        SEGLEN(txm, "__TEXT") +
        SEGLEN(txm, "__DATA_CONST") +
        SEGLEN(txm, "__TEXT_EXEC") +
        SEGLEN(txm, "__TEXT_BOOT_EXEC") +
        SEGLEN(bkc, "__TEXT_EXEC") +
        SEGLEN(bkc, "__TEXT_BOOT_EXEC") +
        SEGLEN(bkc, "__TEXT") +
        SEGLEN(bkc, "__PRELINK_TEXT") +
        SEGLEN(bkc, "__DATA_CONST") +
        SEGLEN(bkc, "__DATA_SPTM") +
        dtree_size_rounded +
        tc_size_rounded +
        (have_cl4 ? (cl4_mi.virthi - cl4_mi.virtlo) : 0) +
        DARWIN_PAGE_SIZE; // extra page we skip in front of the device tree

    assert(GET_L2_PT_INDEX(bkc_mi.virtlo) > bytes_before_sptm);
    SKIP(GET_L2_PT_INDEX(bkc_mi.virtlo) - bytes_before_sptm);

    // To find struct layout in SPTM, search for function that uses the string
    // "%s: region '%s' [%p-%p] not immediately after region '%s' [ending at %p]"
    // This string is used in a call to panic at the bottom of a loop that
    // iterates over structs that tell you exactly which sections SPTM wants in
    // what order.

    // TXM-ro
    {
        PUSH_SEG(txm, "__TEXT");
        PUSH_SEG(txm, "__DATA_CONST");
        END_ENTRY("TXM-ro");
    }

    // TXM-rx
    {
        PUSH_SEG(txm, "__TEXT_EXEC");
        END_ENTRY("TXM-rx");
    }

    // TXM-bx
    {
        PUSH_SEG(txm, "__TEXT_BOOT_EXEC");
        END_ENTRY("TXM-bx");
    }

    // TrustCache
    {
        tc_base_phys = blob_head;
        blob_head += tc_size_rounded;
        END_ENTRY("TrustCache");
    }

    // AuxKC-ro, AuxKC-rx (ignored)

    // BootKC-rx
    {
        PUSH_SEG(bkc, "__TEXT_EXEC");
        END_ENTRY("BootKC-rx");
    }

    // BootKC-bx
    {
        PUSH_SEG(bkc, "__TEXT_BOOT_EXEC");
        END_ENTRY("BootKC-bx");
    }

    // BootKC-ro
    {
        PUSH_SEG(bkc, "__TEXT");
        PUSH_SEG(bkc, "__PRELINK_TEXT");
        PUSH_SEG(bkc, "__DATA_CONST");
        END_ENTRY("BootKC-ro");
    }

    // BootKC-rs
    {
        PUSH_SEG(bkc, "__DATA_SPTM");
        END_ENTRY("BootKC-rs");
    }

    // CL4 secure kernel (exclavecore 'txtk'). CL4 runs its early boot MMU-OFF
    // with PC-relative (adrp) accesses to its own __DATA, so __DATA MUST sit at
    // the contiguous physical offset rx + (__DATA.vmaddr - __TEXT.vmaddr) =
    // rx + 0x68c000. We therefore push __TEXT, __DATA and __LINKEDIT contiguously
    // here and cover __DATA+__LINKEDIT with the CL4-ro region, so SPTM still sees
    // DeviceTree immediately after CL4-ro (validate_region_order is satisfied).
    // The writable CL4-rw / CL4-le regions are registered later (phase 2) pointing
    // back into this same contiguous block.
    if (have_cl4) {
        cl4_rx_phys = blob_head;
        PUSH_SEG(cl4, "__TEXT");
        END_ENTRY("CL4-rx");
        // __DATA and __LINKEDIT immediately after __TEXT (contiguous).
        cl4_rw_phys = blob_head;
        PUSH_SEG(cl4, "__DATA");
        cl4_le_phys = blob_head;
        PUSH_SEG(cl4, "__LINKEDIT");
        // Cover __DATA+__LINKEDIT as CL4-ro so the region order stays
        // CL4-rx, CL4-ro, DeviceTree (SPTM requirement).
        END_ENTRY("CL4-ro");
        set_adt_mmap(map, "CL4-virt", cl4_mi.virtlo, 0);
        set_adt_mmap(map, "CL4-entry", cl4_mi.entrypoint, 0);
        // Rebase __DATA chained pointers now that the block is placed. Contiguous
        // layout -> uniform physical base: new = rx_phys + target_offset.
        apply_cl4_fixups((u8*)info->cl4_f.buf, cl4_rx_phys, cl4_rw_phys,
                         cl4_le_phys);
        printf("[cl4] contiguous rx 0x%llX rw 0x%llX le 0x%llX virt 0x%llX entry 0x%llX\n",
               (unsigned long long)cl4_rx_phys, (unsigned long long)cl4_rw_phys,
               (unsigned long long)cl4_le_phys, (unsigned long long)cl4_mi.virtlo,
               (unsigned long long)cl4_mi.entrypoint);
        fflush(stdout);
    }

    // DeviceTree
    {
        // SPTM reads a few bytes before the device tree during early boot, and
        // will panic if you don't provide an extra readable page here.
        blob_head += PAGE_SIZE;
        dtree_base_phys = blob_head;
        blob_head += dtree_size_rounded;
        END_ENTRY("DeviceTree");
    }

    // SPTM gets loaded in its entirety right here
    macho_load(&sptm_mi, blob_head);

    // SPTM-ro
    {
        seg_t *sptm_text = macho_find_seg(sptm_mi.macho, "__TEXT");
        seg_t *sptm_data_const = macho_find_seg(sptm_mi.macho, "__DATA_CONST");
        seg_t *sptm_late_const = macho_find_seg(sptm_mi.macho, "__LATE_CONST");

        hwaddr sptm_ro_start = vtop(&sptm_mi, sptm_text->vmaddr);
        size_t sptm_ro_size = sptm_text->vmsize + sptm_data_const->vmsize + sptm_late_const->vmsize;
        set_adt_mmap(map, "SPTM-ro", sptm_ro_start, sptm_ro_size);
    }

    // SPTM-rx
    {
        seg_t *sptm_text_exec = macho_find_seg(sptm_mi.macho, "__TEXT_EXEC");
        seg_t *sptm_last = macho_find_seg(sptm_mi.macho, "__LAST");

        hwaddr sptm_rx_start = vtop(&sptm_mi, sptm_text_exec->vmaddr);
        size_t sptm_rx_size = sptm_text_exec->vmsize + sptm_last->vmsize;
        set_adt_mmap(map, "SPTM-rx", sptm_rx_start, sptm_rx_size);
    }

    // SPTM-rw
    {
        seg_t *sptm_data = macho_find_seg(sptm_mi.macho, "__DATA");
        seg_t *sptm_bootdata = macho_find_seg(sptm_mi.macho, "__BOOTDATA");

        hwaddr sptm_rw_start = vtop(&sptm_mi, sptm_data->vmaddr);
        size_t sptm_rw_size = sptm_data->vmsize + sptm_bootdata->vmsize;
        set_adt_mmap(map, "SPTM-rw", sptm_rw_start, sptm_rw_size);
    }

    // SPTM-le
    {
        seg_t *sptm_linkedit = macho_find_seg(sptm_mi.macho, "__LINKEDIT");

        set_adt_mmap(map, "SPTM-le", vtop(&sptm_mi, sptm_linkedit->vmaddr), sptm_linkedit->vmsize);
    }

    SKIP(sptm_mi.virthi - sptm_mi.virtlo);

    // TXM-rw
    {
        PUSH_SEG(txm, "__DATA");
        END_ENTRY("TXM-rw");
    }

    // TXM-le
    {
        PUSH_SEG(txm, "__LINKEDIT");
        END_ENTRY("TXM-le");
    }

    // BootKC-rw
    {
        PUSH_SEG(bkc, "__PRELINK_INFO");
        PUSH_SEG(bkc, "__DATA");
        END_ENTRY("BootKC-rw");
    }

    // BootKC-le
    {
        PUSH_SEG(bkc, "__LINKEDIT");
        END_ENTRY("BootKC-le");

    // CL4-rw, CL4-le (phase 2): the writable __DATA / __LINKEDIT regions were
    // already placed contiguously after __TEXT in phase 1; here we only register
    // the region descriptors pointing back at that block so SPTM's SK handoff
    // reports the correct addresses. (No blob_head advance -- do NOT re-push.)
    if (have_cl4) {
        u64 cl4_data_sz = SEGLEN(cl4, "__DATA");
        u64 cl4_le_sz   = SEGLEN(cl4, "__LINKEDIT");
        set_adt_mmap(map, "CL4-rw", cl4_rw_phys, cl4_data_sz);
        set_adt_mmap(map, "CL4-le", cl4_le_phys, cl4_le_sz);
    }
    }

    // CL4-dummypage  (also used as the experimental probe scratch page)
    {
        hwaddr cl4_dummy = blob_head;
        // Enlarge the dummy page into an 0x8000 scratch: domain descriptor at +0,
        // ctor-runner trampoline at +0x80, scratch stack up to the top.
        blob_head += (have_cl4 ? 0x8000 : DARWIN_PAGE_SIZE);
        END_ENTRY("CL4-dummypage");
        if (have_cl4) {
            const uint64_t CL4_SCRATCH_SZ = 0x8000;
            const char *ds = getenv("CL4_DOMAIN_ID");
            uint64_t domain_id = ds ? strtoull(ds, NULL, 0) : 0xc00000001ULL;
            address_space_write(&address_space_memory, cl4_dummy,
                                MEMTXATTRS_UNSPECIFIED, &domain_id, 8);
            g_cl4_x1_inject = getenv("CL4_X1") ? cl4_dummy : 0;
            g_cl4_entry_pc  = cl4_rx_phys + (cl4_mi.entrypoint - cl4_mi.virtlo);
            // Install the ctor-runner trampoline and fill its literal pool, unless
            // disabled via CL4_NO_CTORS (to compare with the old x1-only probe).
            if (getenv("CL4_CTORS")) {   /* opt-in experimental ctor-runner (agent: wrong order; CL4 runs its own ctors after domain-setup) */
                hwaddr tramp_phys = cl4_dummy + 0x80;
                address_space_write(&address_space_memory, tramp_phys,
                                    MEMTXATTRS_UNSPECIFIED,
                                    cl4_ctor_trampoline, CL4_TRAMP_SIZE);
                uint64_t modinit_phys = cl4_rx_phys + 0x698fc0; // __mod_init_func
                uint64_t pool[4] = {
                    modinit_phys,
                    modinit_phys + 11 * 8,
                    (cl4_dummy + CL4_SCRATCH_SZ) & ~0xFULL,
                    g_cl4_entry_pc,
                };
                address_space_write(&address_space_memory,
                                    tramp_phys + CL4_TRAMP_POOL_OFF,
                                    MEMTXATTRS_UNSPECIFIED, pool, sizeof(pool));
                g_cl4_tramp_pc = tramp_phys;
                // Fake empty per-thread context so ctors that read TPIDR_EL0
                // (accessor 0x..92aca0: ldr [tpidr+8]; factory 0x..a1e70:
                // ldr [tpidr+0x10]->[0]) see valid-but-empty pointers instead of
                // dereferencing 0. ctx @ +0x200; its +8/+0x10 point at a zeroed
                // cell @ +0x400 (empty list head = 0). CL4 installs its real
                // TPIDR at 0xc00aa724 later and overwrites this.
                {
                    // Fake per-thread ctx @ +0x200. [ctx+8] -> zeroed cell (an
                    // accessor returns it). [ctx+0x10] -> regobj @ +0x400 whose
                    // [0] is the singly-linked list head. Pre-seed the base
                    // per-thread services CL4's domain-setup would register, so
                    // constructors that look them up during the ctor pass (before
                    // domain-setup runs) find them instead of dereferencing null.
                    hwaddr ctx    = cl4_dummy + 0x200;
                    hwaddr cell8  = cl4_dummy + 0x600;
                    hwaddr regobj = cl4_dummy + 0x400;
                    hwaddr node   = cl4_dummy + 0x420;
                    address_space_write(&address_space_memory, ctx + 0x08,
                                        MEMTXATTRS_UNSPECIFIED, &cell8, 8);
                    address_space_write(&address_space_memory, ctx + 0x10,
                                        MEMTXATTRS_UNSPECIFIED, &regobj, 8);
                    address_space_write(&address_space_memory, regobj,
                                        MEMTXATTRS_UNSPECIFIED, &node, 8);
                    // node (2,5): next=0, key1=2, key2=5, value=rx+0x6fece8
                    uint64_t nxt = 0, val = cl4_rx_phys + 0x6fece8;
                    uint32_t k1 = 2, k2 = 5;
                    address_space_write(&address_space_memory, node + 0x00,
                                        MEMTXATTRS_UNSPECIFIED, &nxt, 8);
                    address_space_write(&address_space_memory, node + 0x08,
                                        MEMTXATTRS_UNSPECIFIED, &k1, 4);
                    address_space_write(&address_space_memory, node + 0x10,
                                        MEMTXATTRS_UNSPECIFIED, &k2, 4);
                    address_space_write(&address_space_memory, node + 0x18,
                                        MEMTXATTRS_UNSPECIFIED, &val, 8);
                    g_cl4_tpidr = ctx;
                    g_cl4_tpidrro = cl4_dummy + 0x700; /* zeroed region */
                }
                printf("[cl4] ctor-runner: tramp 0x%llX modinit 0x%llX stack 0x%llX entry 0x%llX\n",
                       (unsigned long long)tramp_phys, (unsigned long long)modinit_phys,
                       (unsigned long long)pool[2], (unsigned long long)g_cl4_entry_pc);
            }
            printf("[cl4] probe: entry_pc 0x%llX x1->scratch 0x%llX domain_id 0x%llX\n",
                   (unsigned long long)g_cl4_entry_pc, (unsigned long long)cl4_dummy,
                   (unsigned long long)domain_id);
            fflush(stdout);
        }
    }

    // BootArgs
    {
        args_base_phys = blob_head;
        blob_head += sizeof(boot_args);
        blob_head = ROUND_NEXT_PAGE(blob_head);
        END_ENTRY("BootArgs");
    }

    // RAMDisk — same sequential placement XNU has always expected (keeps
    // topOfKernelData/blob_head/ADT consistency exactly as before), but
    // backed directly by its file via a high-priority overlay region
    // instead of being copied byte-for-byte into the underlying anonymous
    // DRAM. This lets a ramdisk image far larger than available host RAM
    // boot: only the pages XNU actually touches get faulted in from the
    // file (via mmap, private/copy-on-write so the source file is never
    // modified). Tried placing this at a separate, non-sequential address
    // first (both far away and within dram_size) — both paniced identically
    // with "ramdisk params @IOKitBSDInit.cpp:789" even though the mapped
    // content itself was verified correct via the QEMU monitor, pointing at
    // a consistency check against the sequential blob layout rather than a
    // mapping/content problem.
    {
        rd_base_phys = blob_head;
        blob_head += info->ramdisk_f.len;
        blob_head = ROUND_NEXT_PAGE(blob_head);
        END_ENTRY("RAMDisk");
        MemoryRegion *rd_mr = g_new0(MemoryRegion, 1);
        memory_region_init_ram_from_file(rd_mr, NULL, "ramdisk-file",
                                         info->ramdisk_f.len, 0, 0,
                                         info->ramdisk, 0, &error_fatal);
        memory_region_add_subregion_overlap(get_system_memory(), rd_base_phys,
                                            rd_mr, 1);
        printf("[darwin] ramdisk: %llu bytes (0x%llX) file-mapped at 0x%llX (no copy)\n",
               (unsigned long long)info->ramdisk_f.len,
               (unsigned long long)info->ramdisk_f.len,
               (unsigned long long)rd_base_phys);
        fflush(stdout);
    }

#undef PUSH_SEG
#undef END_ENTRY
#undef SKIP

    set_adt_mmap(map, "TXM-virt",  txm_mi.virtlo, 0);
    set_adt_mmap(map, "TXM-entry", txm_mi.entrypoint, 0);
    set_adt_mmap(map, "BootKC-virt",  bkc_mi.virtlo, 0);
    set_adt_mmap(map, "BootKC-entry", bkc_mi.entrypoint, 0);
    set_adt_mmap(map, "SPTM-virt",  sptm_mi.virtlo, 0);
    set_adt_mmap(map, "SPTM-entry", sptm_mi.entrypoint, 0);

    // SPTM places TXM 1x SPTM_EXPECTED_STRIDE away, and BKC 2x
    // SPTM_EXPECTED_STRIDE away in virtual memory. It completely ignores the
    // -virt dtree entries when choosing where to load TXM/ BKC. It happens
    // that TXM and the BKC machos have their virtlo 1x and 2x
    // SPTM_EXPECTED_STRIDE before SPTM's virtlo respectively. I'm not sure
    // whether SPTM is hardcoded to place TXM/ BKC this many bytes after it, or
    // whether it calculates this based on the macho header of TXM/ BKC, so for
    // now just assert the machos match what we expect in case this ever
    // changes later on.
    assert(1 * SPTM_EXPECTED_STRIDE == GET_L2_PT_INDEX(sptm_mi.virtlo - txm_mi.virtlo));
    assert(2 * SPTM_EXPECTED_STRIDE == GET_L2_PT_INDEX(sptm_mi.virtlo - bkc_mi.virtlo));

    boot_args args = {0};
    args.Revision = kBootArgsRevision2;
    args.Version = kBootArgsVersion2;

#ifdef LINEUP_BOOTKC_NICELY
    args.virtBase = STRIP_L2_PT_INDEX(bkc_mi.virtlo) - (2 * SPTM_EXPECTED_STRIDE);
#else // LINEUP_BOOTKC_NICELY
    args.virtBase = STRIP_L2_PT_INDEX(bkc_mi.virtlo);
#endif // ! LINEUP_BOOTKC_NICELY

    args.physBase = info->dram_base;
    args.memSizeActual = info->dram_size;
    if (info->has_mte) {
        args.memSize = (31 * info->dram_size) / 32;
    } else {
        args.memSize = info->dram_size;
    }
    // Park the boot framebuffer at the very top of DRAM and hide it from the
    // kernel by shrinking memSize, which is what iBoot does. Carving it out of
    // the boot blob instead would land it inside the contiguous region chain
    // SPTM validates, and the guest hangs before it can print anything.
    if (info->fb_size) {
        args.memSize = ROUND_DOWN_POW2(args.memSize - info->fb_size, DARWIN_PAGE_SIZE);
        fb_base_phys = info->dram_base + args.memSize;
        info->fb_base = fb_base_phys;
    }

    // ANS coprocessor carve-out, same trick as the framebuffer: take it off the
    // top of DRAM and hide it behind memSize so XNU never hands it out.
    if (info->ansfw_f.buf) {
        uint64_t region = info->ansfw_region;
        args.memSize = ROUND_DOWN_POW2(args.memSize - region, DARWIN_PAGE_SIZE);
        hwaddr fw_base = info->dram_base + args.memSize;

        address_space_write(&address_space_memory, fw_base, MEMTXATTRS_UNSPECIFIED,
                            info->ansfw_f.buf, info->ansfw_f.len);

        struct dtree_node *nub =
            adt_find_node((struct dtree_node*)dtree, "arm-io/ans/iop-ans-nub");
        if (nub) {
            u64 *rb = adt_get_prop_val(nub, "region-base");
            u64 *rs = adt_get_prop_val(nub, "region-size");
            if (rb) *rb = fw_base;
            if (rs) *rs = region;
            printf("[darwin] ans firmware: %llu bytes at 0x%llX, region 0x%llX\n",
                   (unsigned long long)info->ansfw_f.len,
                   (unsigned long long)fw_base,
                   (unsigned long long)region);
        } else {
            printf("[darwin] ans firmware loaded but iop-ans-nub not in dtree\n");
        }
        fflush(stdout);
    }

    if (info->dcpfw_f.buf) {
        uint64_t region = info->dcpfw_region;
        args.memSize = ROUND_DOWN_POW2(args.memSize - region, DARWIN_PAGE_SIZE);
        hwaddr fw_base = info->dram_base + args.memSize;

        address_space_write(&address_space_memory, fw_base, MEMTXATTRS_UNSPECIFIED,
                            info->dcpfw_f.buf, info->dcpfw_f.len);

        struct dtree_node *nub =
            adt_find_node((struct dtree_node*)dtree, "arm-io/dcp/iop-dcp-nub");
        u64 *rb = nub ? adt_get_prop_val(nub, "region-base") : NULL;
        u64 *rs = nub ? adt_get_prop_val(nub, "region-size") : NULL;
        if (rb && rs) {
            *rb = fw_base; *rs = region;
            printf("[darwin] dcp firmware: %llu bytes at 0x%llX, region 0x%llX\n",
                   (unsigned long long)info->dcpfw_f.len,
                   (unsigned long long)fw_base, (unsigned long long)region);
        } else {
            printf("[darwin] dcp firmware loaded but iop-dcp-nub has no "
                   "region-base/region-size (use DCP_REGION=1 in dt_fixup)\n");
        }
        fflush(stdout);
    }

    args.topOfKernelData = blob_head;
    args.deviceTreeP = dtree_base_phys - args.physBase + args.virtBase;
    args.deviceTreeLength = info->dtree_f.len;
    g_strlcpy(args.CommandLine, info->args, BOOT_LINE_LENGTH);

    // Hand XNU the boot display. With v_baseAddr set, PE_init_platform wires
    // up the graphics console instead of falling back to serial only.
    // Back the embedded panic log (agent finding): XNU's panic logger maps
    // /pram reg and stores a global pointer; if that map fails (reg was {0,0})
    // the global stays NULL and a later panic double-faults (store to NULL+0xb1),
    // MASKING the real panic. Carve RAM and set /pram reg base; size + the
    // /chosen:embedded-panic-log-size gate come from firmware/dtree_pram.
    {
        uint64_t psz = 0x100000;
        args.memSize = ROUND_DOWN_POW2(args.memSize - psz, DARWIN_PAGE_SIZE);
        hwaddr pram_base = info->dram_base + args.memSize;
        struct dtree_node *pram =
            adt_find_node((struct dtree_node*)dtree, "pram");
        if (pram) {
            u64 *reg = adt_get_prop_val(pram, "reg");
            if (reg) { reg[0] = pram_base; reg[1] = psz; }
            printf("[darwin] pram panic-log backed at 0x%llX size 0x%llX\n",
                   (unsigned long long)pram_base, (unsigned long long)psz);
        } else {
            printf("[darwin] pram node not found in dtree\n");
        }
        fflush(stdout);
    }

    // Publish the framebuffer the way iBoot does. boot_args.Video alone isn't
    // enough on modern iOS: the /vram node is what the IODeviceTree platform
    // expert reads, and display-scale is left at 0 by the stock tree, which is
    // not a value the display path expects.
    if (info->fb_size && info->fb_video) {
        struct dtree_node *vram_node = adt_find_node((struct dtree_node*)dtree, "vram");
        if (vram_node) {
            u64 *vram_reg = adt_get_prop_val(vram_node, "reg");
            if (vram_reg) {
                vram_reg[0] = fb_base_phys;
                vram_reg[1] = info->fb_size;
                printf("[darwin] /vram reg = 0x%llX (0x%llX)\n",
                       (unsigned long long)vram_reg[0], (unsigned long long)vram_reg[1]);
            }
        }
        struct dtree_node *chosen = adt_find_node((struct dtree_node*)dtree, "chosen");
        if (chosen) {
            u32 *scale = adt_get_prop_val(chosen, "display-scale");
            if (scale && *scale == 0) *scale = 1;
        }
        fflush(stdout);
    }

    if (info->fb_size && info->fb_video) {
        args.Video.v_baseAddr = fb_base_phys;
        args.Video.v_display  = 1;
        args.Video.v_rowBytes = info->fb_width * 4;
        args.Video.v_width    = info->fb_width;
        args.Video.v_height   = info->fb_height;
        args.Video.v_depth    = 32 | (1 << kBootVideoDepthScaleShift);
    }

    // Always report where SPTM will actually land things. A sampled runtime PC
    // is meaningless against the on-disk kernelcache without this slide.
    {
        uint64_t sptm_rt = args.virtBase - args.physBase + sptm_mi.physlo;
        uint64_t bkc_rt  = sptm_rt + 2 * SPTM_EXPECTED_STRIDE;
        printf("[darwin] bkc static virtlo = 0x%llX\n",
               (unsigned long long)bkc_mi.virtlo);
        printf("[darwin] bkc runtime base  = 0x%llX\n",
               (unsigned long long)bkc_rt);
        printf("[darwin] bkc slide         = 0x%llX  (runtime - static)\n",
               (unsigned long long)(bkc_rt - bkc_mi.virtlo));
        fflush(stdout);
    }

#ifdef DEBUG_MEMORY_LAYOUT
    uint64_t sptm_load = args.virtBase - args.physBase + sptm_mi.physlo;
    uint64_t txm_load = sptm_load + 1 * SPTM_EXPECTED_STRIDE;
    uint64_t bkc_load = sptm_load + 2 * SPTM_EXPECTED_STRIDE;

    printf("==========\n");
    printf("SPTM base: 0x%016llX\n", sptm_load);
    printf("TXM base:  0x%016llX\n", txm_load);
    printf("BKC base:  0x%016llX\n", bkc_load);
    printf("==========\n");
#endif // DEBUG_MEMORY_LAYOUT

    address_space_write(
        &address_space_memory,
        args_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        &args,
        sizeof(args)
    );

    address_space_write(
        &address_space_memory,
        dtree_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        info->dtree_f.buf,
        info->dtree_f.len
    );

    trust_cache_offsets_t tc_info = get_tcinfo();

    address_space_write(
        &address_space_memory,
        tc_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        &tc_info,
        sizeof(tc_info)
    );

    address_space_write(
        &address_space_memory,
        tc_base_phys + sizeof(tc_info),
        MEMTXATTRS_UNSPECIFIED,
        info->tc_f.buf,
        info->tc_f.len
    );

    // No address_space_write for the ramdisk here: its content is already
    // present at rd_base_phys via the direct file-backed memory region
    // created above.

    info->init_pc = vtop(&sptm_mi, sptm_mi.entrypoint);
    info->init_x0 = args_base_phys;
}

static void arm_load_xnu_nosptm(ARMCPU *cpu, MachineState *ms, struct xnu_boot_info *info) {
    u8 *macho_bkc = (u8*)info->bootkc_f.buf;

    alloc_ram(OBJECT(cpu), info->dram_base, info->dram_size);

    macho_info_t bkc_mi  = macho_get_info(macho_bkc);

    // iOS wants the trustcache to be both beneath the kernel and
    // not in the first huge page of DRAM
    hwaddr tc_base_phys = info->dram_base + DARWIN_HUGE_PAGE_SIZE;
    hwaddr xnu_load_phys = info->dram_base + XNU_STRIP_VMA(bkc_mi.virtlo);
    hwaddr args_base_phys  = info->dram_base + XNU_STRIP_VMA(bkc_mi.virthi);
    hwaddr dtree_base_phys = ROUND_NEXT_PAGE(args_base_phys + sizeof(boot_args));
    hwaddr rd_base_phys = ROUND_NEXT_PAGE(dtree_base_phys + info->dtree_f.len);

    assert(xnu_load_phys >= tc_base_phys + info->tc_f.len);
    assert(args_base_phys >= xnu_load_phys + bkc_mi.virthi - bkc_mi.virtlo);
    assert(dtree_base_phys >= args_base_phys + sizeof(boot_args));
    assert(rd_base_phys >= dtree_base_phys + info->dtree_f.len);
    assert(info->dram_base + info->dram_size > tc_base_phys + info->tc_f.len);

    // We could support loading pre-SPTM KCs with MTE, but they don't exist, so
    // since we aren't loading SPTM, confirm we aren't expecting MTE to work.
    assert(!info->has_mte);

    macho_verify_header(macho_bkc, true);
    patch_kc(macho_bkc);
    macho_load(&bkc_mi, xnu_load_phys);

    struct dtree_node *map = adt_find_node((struct dtree_node*)info->dtree_f.buf, "chosen/memory-map");
    set_adt_mmap(map, "TrustCache", tc_base_phys, info->tc_f.len + sizeof(trust_cache_offsets_t));
    set_adt_mmap(map, "RAMDisk", rd_base_phys, info->ramdisk_f.len);

    boot_args args = {0};
    args.Revision = kBootArgsRevision2;
    args.Version = kBootArgsVersion2;
    args.virtBase = STRIP_L2_PT_INDEX(bkc_mi.virtlo);
    args.physBase = info->dram_base;
    args.memSize = info->dram_size;
    args.topOfKernelData = rd_base_phys + ROUND_NEXT_PAGE(info->ramdisk_f.len);
    args.deviceTreeP = dtree_base_phys - args.physBase + args.virtBase;
    args.deviceTreeLength = info->dtree_f.len;
    g_strlcpy(args.CommandLine, info->args, BOOT_LINE_LENGTH);

    assert(args.topOfKernelData > bkc_mi.physlo + (bkc_mi.virthi - bkc_mi.virtlo));

#ifdef DEBUG_MEMORY_LAYOUT
    printf("xnu:   0x%lX\n", xnu_load_phys);
    printf("rd:    0x%lX\n", rd_base_phys);
    printf("tc:    0x%lX\n", tc_base_phys);
    printf("rdlen: 0x%lX\n", info->ramdisk_f.len);
    printf("ktop:  0x%lX\n", args.topOfKernelData);
    printf("vbase: 0x%lX\n", args.virtBase);
    printf("pbase: 0x%lX\n", args.physBase);
    printf("dtp:   0x%llX\n", args.deviceTreeP);
#endif // DEBUG_MEMORY_LAYOUT

    address_space_write(
        &address_space_memory,
        args_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        &args,
        sizeof(args)
    );

    address_space_write(
        &address_space_memory,
        dtree_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        info->dtree_f.buf,
        info->dtree_f.len
    );

    trust_cache_offsets_t tc_info = get_tcinfo();

    address_space_write(
        &address_space_memory,
        tc_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        &tc_info,
        sizeof(tc_info)
    );

    address_space_write(
        &address_space_memory,
        tc_base_phys + sizeof(tc_info),
        MEMTXATTRS_UNSPECIFIED,
        info->tc_f.buf,
        info->tc_f.len
    );

    address_space_write(
        &address_space_memory,
        rd_base_phys,
        MEMTXATTRS_UNSPECIFIED,
        info->ramdisk_f.buf,
        info->ramdisk_f.len
    );

    info->init_pc = vtop(&bkc_mi, bkc_mi.entrypoint);
    info->init_x0 = args_base_phys;
}

void arm_load_xnu(ARMCPU *cpu, MachineState *ms, struct xnu_boot_info *info) {
    if (info->sptm) arm_load_xnu_sptm(cpu, ms, info);
    else arm_load_xnu_nosptm(cpu, ms, info);
}
