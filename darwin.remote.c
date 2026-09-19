#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/arm/boot.h"
#include "hw/arm/machines-qom.h"
#include "cpu.h"
#include "qom/object.h"
#include "system/address-spaces.h"
#include "system/reset.h"
#include "exec/memattrs.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "qemu/config-file.h"
#include "cpregs.h"
#include "hw/arm/exynos4210.h"
#include "system/system.h"
#include "hw/core/sysbus.h"
#include "hw/core/platform-bus.h"
#include "xnu/boot/xnuboot.h"
#include "xnu/apple_dtree.h"
#include "xnu/apple_regs.h"
#include "hw/arm/apple_amcc.h"
#include "xnu/patch.h"
#include "xnu/macho.h"
#include "ui/console.h"
#include "ui/input.h"
#include "ui/surface.h"
#include "hw/misc/unimp.h"
#include "hw/core/irq.h"
#include "hw/arm/apple_rtkit.h"
#include "hw/arm/apple_dcp.h"
#include "qemu/timer.h"
#include "qemu/error-report.h"

// See device tree specification section 2.3.8: ranges
#define IO_RANGE_BASE_OFFSET     1

// Use this for AICs where we don't know how many interrupts there should be
#define A_GOOD_NUMBER_OF_IRQS    0x1000

#define EXPECTED_FIRMWARE_NAME   "qemu-sptm"

// Boot framebuffer geometry. Kept small on purpose: there is no GPU here, every
// frame is blitted under TCG, and XNU only needs somewhere to draw its console.
#define DARWIN_FB_WIDTH          640
#define DARWIN_FB_HEIGHT         1136

static char *g_default_args = (char*)"debug=0x8 kextlog=0xffff cpus=1 rd=md0 serial=7 -v -noprogress keepsyms=1 wdt=-1 -enable_kprintf_spam wlan-olyhal-abort";

#define CPACR_ENABLE_FPU         (( BIT(20) | BIT(21) ))
#define CPTR_ENABLE_FPU          (( BIT(20) | BIT(21) ))

#define TYPE_DARWIN_MACHINE MACHINE_TYPE_NAME("darwin")
OBJECT_DECLARE_SIMPLE_TYPE(DarwinState, DARWIN_MACHINE)

struct DarwinState {
    MachineState parent_obj;
    ARMCPU *cpu;
    struct xnu_boot_info bootinfo;
};

MACHINE_CLASS_ARG(bootkc);
MACHINE_CLASS_ARG(args);
MACHINE_CLASS_ARG(dtree);
MACHINE_CLASS_ARG(sptm);
MACHINE_CLASS_ARG(txm);
MACHINE_CLASS_ARG(cl4);
MACHINE_CLASS_ARG(tc);
MACHINE_CLASS_ARG(ramdisk);

static void alloc_zeroed(const char *name, hwaddr pa, size_t len) {
    if (0 == len) {
        fprintf(stderr, "error: alloc_ram called with len=0 for region %s\n", name);
        exit(1);
    }
    MemoryRegion *ram_main = get_system_memory();
    MemoryRegion *ram_subreg = g_new(MemoryRegion, 1);
    memory_region_init_ram(ram_subreg, NULL, name, len, &error_fatal);
    memory_region_add_subregion(ram_main, pa, ram_subreg);
    address_space_set(&address_space_memory, pa, 0, len, MEMTXATTRS_UNSPECIFIED);
}

static void do_darwin_reset(void *state) {
    DarwinState *s = DARWIN_MACHINE((MachineState *)state);
    ARMCPU *cpu = s->cpu;
    CPUState *cs = CPU(cpu);
    CPUARMState *env = &cpu->env;

    cpu_reset(cs);

    assert(2 == arm_highest_el(env));
    env->xregs[0] = s->bootinfo.init_x0;
    env->pc = s->bootinfo.init_pc;

    // SPTM needs fpu enabled:
    env->cp15.cpacr_el1 |= CPACR_ENABLE_FPU;
    env->cp15.cptr_el[2] |= CPTR_ENABLE_FPU;
    arm_rebuild_hflags(env);
}

static mmap_file_t check_and_open(const char *path, const char *errmsg) {
    int fd;
    struct stat stats;
    void *mapping;

    if (!path) goto fail;

    fd = open(path, O_RDONLY | O_BINARY);
    if (fd < 0) goto fail;

    fstat(fd, &stats);
    mapping = mmap(NULL, stats.st_size, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
    if (MAP_FAILED == mapping) goto fail;

    if (is_im4p(mapping)) {
        fprintf(stderr, "error: %s is an im4p, you need to unwrap it (eg. ipsw img4 im4p extract)\n", path);
        goto fail;
    }

    return (mmap_file_t){
        .buf = mapping,
        .len = stats.st_size,
    };

fail:
    fprintf(stderr, "%s\n", errmsg);
    exit(1);
}

static void init_cpu_impl(struct dtree_node *dt_root) {
    struct dtree_node *cpu0 = adt_find_node(dt_root, "cpus/cpu0");
    struct adt_io_reg *cpu_impl = adt_get_prop_val(cpu0, "cpu-impl-reg");
    struct adt_io_reg *cpm_impl = adt_get_prop_val(cpu0, "cpm-impl-reg");
    alloc_zeroed("cpu_reg_impl", cpu_impl[0].base, cpu_impl[0].len);
    alloc_zeroed("cpm_reg_impl", cpm_impl[0].base, cpm_impl[0].len);
}

static void init_uart(struct dtree_node *dt_root, uint64_t iobase) {
    struct dtree_node *uart = adt_find_node(dt_root, "arm-io/uart0");
    struct adt_io_reg *uart_reg = adt_get_prop_val(uart, "reg");
    exynos4210_uart_create(uart_reg[0].base + iobase, 16, 0, serial_hd(0), 0);
}

static void init_sep(struct dtree_node *dt_root) {
    // This is a bare-bones sep InvalidateHmac config=1 implementation that ignores all register reads/ writes.
    // Since we fixup the device tree to have sio-hmac1-disable-mask = -1, InvalidateHmac is effectively disabled,
    // so long as we can read/ write the "registers" in the reg-block.
    struct dtree_node *sep = adt_find_node(dt_root, "arm-io/sep/iop-sep-nub/InvalidateHmac");
    if (!sep) return;
    struct adt_io_reg *sep_reg = adt_get_prop_val(sep, "reg-block");

    alloc_zeroed("sep", sep_reg[0].base, sep_reg[0].len);
}

static void init_aic(struct dtree_node *dt_root, uint64_t iobase) {
    // This is a bare-bones aic implementation that ignores all register reads/
    // writes, and simply reports the correct number of IRQs
    struct dtree_node *aic = adt_find_node(dt_root, "arm-io/aic");
    struct adt_io_reg *aic_reg = adt_get_prop_val(aic, "reg");

    uint64_t base = aic_reg[0].base + iobase;
    alloc_zeroed("aic", base, aic_reg[0].len);

    int aic_vers = -1;
    sscanf(adt_get_prop_val(aic, "compatible"), "aic,%d", &aic_vers);

    uint32_t num_irqs = 0;
    switch (aic_vers) {
        case 1:
            // aic,1 needs register +0x04 from first iobase to report the number of interrupts
            // This is always 8x the size of the ipid-mask for this device
            num_irqs = 8 * adt_get_prop_len(aic, "ipid-mask");
            address_space_write(&address_space_memory, base + 0x4, MEMTXATTRS_UNSPECIFIED, &num_irqs, sizeof(num_irqs));
            break;

        case 2:
        case 3:
            // aic,2 and aic,3 have num irqs at +0xC
            num_irqs = A_GOOD_NUMBER_OF_IRQS;
            address_space_write(&address_space_memory, base + 0xC, MEMTXATTRS_UNSPECIFIED, &num_irqs, sizeof(num_irqs));
            break;

        default:
            fprintf(stderr, "warning: unsupported AIC, this will probably not work\n");
            break;
    }
}

static void setup_mte(Object *cpuobj, MachineState *machine, struct xnu_boot_info *info) {
    MemoryRegion *tag_sysmem = NULL;

    if (!object_property_find(cpuobj, "tag-memory")) {
        fprintf(stderr, "cpu missing tag-memory property; MTE can't be enabled\n");
        exit(1);
    }

    tag_sysmem = g_new(MemoryRegion, 1);
    memory_region_init(tag_sysmem, OBJECT(machine), "tag-memory", UINT64_MAX / 32);
    object_property_set_link(cpuobj, "tag-memory", OBJECT(tag_sysmem), &error_abort);

    MemoryRegion *tagram = g_new(MemoryRegion, 1);
    memory_region_init_ram(tagram, NULL, "mte_tags", info->dram_size / 32, &error_fatal);
    memory_region_add_subregion(tag_sysmem, info->dram_base / 32, tagram);
}

__attribute__((unused))
static int get_soc_gen(struct dtree_node *dt_root) {
    struct dtree_node *arm_io = adt_find_node(dt_root, "arm-io");
    assert(arm_io);
    const char *soc_gen_str = adt_get_prop_val(arm_io, "soc-generation");
    if (!soc_gen_str || 'H' != soc_gen_str[0]) return 0;
    int soc_gen = 0;
    sscanf(soc_gen_str, "H%d", &soc_gen);
    return soc_gen;
}

static void check_dtree(struct dtree_node *dt_root) {
    struct dtree_node *chosen = adt_find_node(dt_root, "chosen");
    assert(chosen);

    const char *fw_vers = adt_get_prop_val(chosen, "firmware-version");
    assert(fw_vers);

    if (0 != strcmp(fw_vers, EXPECTED_FIRMWARE_NAME)) {
        fprintf(stderr, "error: device tree firmware-version doesn't match %s, did you run dt_fixup on this device tree?\n", EXPECTED_FIRMWARE_NAME);
        exit(1);
    }
}

typedef struct DarwinFB {
    QemuConsole *con;
} DarwinFB;

static bool darwin_fb_update(void *opaque) {
    DarwinFB *fb = opaque;
    qemu_console_update_full(fb->con);
    return true;
}

static const GraphicHwOps darwin_fb_ops = {
    .gfx_update = darwin_fb_update,
};

// Scan out the pixels the kernel loader reserved for us. The surface points
// straight at guest DRAM, so whatever XNU draws lands in the window with no
// copy of our own.
extern void darwin_uart_inject(const uint8_t *buf, int len);

static bool g_kbd_shift, g_kbd_ctrl;

static char qcode_to_ascii(int q, bool sh)
{
    switch (q) {
    case Q_KEY_CODE_A: return sh ? 'A' : 'a';
    case Q_KEY_CODE_B: return sh ? 'B' : 'b';
    case Q_KEY_CODE_C: return sh ? 'C' : 'c';
    case Q_KEY_CODE_D: return sh ? 'D' : 'd';
    case Q_KEY_CODE_E: return sh ? 'E' : 'e';
    case Q_KEY_CODE_F: return sh ? 'F' : 'f';
    case Q_KEY_CODE_G: return sh ? 'G' : 'g';
    case Q_KEY_CODE_H: return sh ? 'H' : 'h';
    case Q_KEY_CODE_I: return sh ? 'I' : 'i';
    case Q_KEY_CODE_J: return sh ? 'J' : 'j';
    case Q_KEY_CODE_K: return sh ? 'K' : 'k';
    case Q_KEY_CODE_L: return sh ? 'L' : 'l';
    case Q_KEY_CODE_M: return sh ? 'M' : 'm';
    case Q_KEY_CODE_N: return sh ? 'N' : 'n';
    case Q_KEY_CODE_O: return sh ? 'O' : 'o';
    case Q_KEY_CODE_P: return sh ? 'P' : 'p';
    case Q_KEY_CODE_Q: return sh ? 'Q' : 'q';
    case Q_KEY_CODE_R: return sh ? 'R' : 'r';
    case Q_KEY_CODE_S: return sh ? 'S' : 's';
    case Q_KEY_CODE_T: return sh ? 'T' : 't';
    case Q_KEY_CODE_U: return sh ? 'U' : 'u';
    case Q_KEY_CODE_V: return sh ? 'V' : 'v';
    case Q_KEY_CODE_W: return sh ? 'W' : 'w';
    case Q_KEY_CODE_X: return sh ? 'X' : 'x';
    case Q_KEY_CODE_Y: return sh ? 'Y' : 'y';
    case Q_KEY_CODE_Z: return sh ? 'Z' : 'z';
    case Q_KEY_CODE_0: return sh ? ')' : '0';
    case Q_KEY_CODE_1: return sh ? '!' : '1';
    case Q_KEY_CODE_2: return sh ? '@' : '2';
    case Q_KEY_CODE_3: return sh ? '#' : '3';
    case Q_KEY_CODE_4: return sh ? '$' : '4';
    case Q_KEY_CODE_5: return sh ? '%' : '5';
    case Q_KEY_CODE_6: return sh ? '^' : '6';
    case Q_KEY_CODE_7: return sh ? '&' : '7';
    case Q_KEY_CODE_8: return sh ? '*' : '8';
    case Q_KEY_CODE_9: return sh ? '(' : '9';
    case Q_KEY_CODE_SPC: return ' ';
    case Q_KEY_CODE_RET: return '\r';
    case Q_KEY_CODE_TAB: return '\t';
    case Q_KEY_CODE_BACKSPACE: return 0x7f;
    case Q_KEY_CODE_ESC: return 0x1b;
    case Q_KEY_CODE_MINUS: return sh ? '_' : '-';
    case Q_KEY_CODE_EQUAL: return sh ? '+' : '=';
    case Q_KEY_CODE_BRACKET_LEFT: return sh ? '{' : '[';
    case Q_KEY_CODE_BRACKET_RIGHT: return sh ? '}' : ']';
    case Q_KEY_CODE_BACKSLASH: return sh ? '|' : '\\';
    case Q_KEY_CODE_SEMICOLON: return sh ? ':' : ';';
    case Q_KEY_CODE_APOSTROPHE: return sh ? '"' : '\'';
    case Q_KEY_CODE_GRAVE_ACCENT: return sh ? '~' : '`';
    case Q_KEY_CODE_COMMA: return sh ? '<' : ',';
    case Q_KEY_CODE_DOT: return sh ? '>' : '.';
    case Q_KEY_CODE_SLASH: return sh ? '?' : '/';
    default: return 0;
    }
}

static void darwin_kbd_event(DeviceState *dev, QemuConsole *src, QemuInputEvent *evt)
{
    if (evt->type != INPUT_EVENT_KIND_KEY) return;
    int q = qemu_input_linux_to_qcode(evt->key.key);  /* evt->key.key is a Linux keycode */
    bool down = evt->key.down;
    if (q == Q_KEY_CODE_SHIFT || q == Q_KEY_CODE_SHIFT_R) { g_kbd_shift = down; return; }
    if (q == Q_KEY_CODE_CTRL || q == Q_KEY_CODE_CTRL_R)   { g_kbd_ctrl  = down; return; }
    if (!down) return;
    char c = qcode_to_ascii(q, g_kbd_shift);
    if (!c) return;
    if (g_kbd_ctrl) { if (c >= 'a' && c <= 'z') c = c - 'a' + 1; else if (c >= 'A' && c <= 'Z') c = c - 'A' + 1; }
    uint8_t b = (uint8_t)c;
    darwin_uart_inject(&b, 1);
}

static const QemuInputHandler darwin_kbd_handler = {
    .name  = "iPhone panel keyboard",
    .mask  = INPUT_EVENT_MASK_KEY,
    .event = darwin_kbd_event,
};

static void init_framebuffer(struct xnu_boot_info *info) {
    if (!info->fb_size) return;

    MemoryRegionSection sec =
        memory_region_find(get_system_memory(), info->fb_base, info->fb_size);
    if (!sec.mr) {
        error_report("framebuffer: no RAM at 0x%" HWADDR_PRIx, info->fb_base);
        return;
    }

    uint8_t *ptr = (uint8_t*)memory_region_get_ram_ptr(sec.mr) + sec.offset_within_region;
    DarwinFB *fb = g_new0(DarwinFB, 1);

    fb->con = qemu_graphic_console_create(NULL, 0, &darwin_fb_ops, fb);
    qemu_console_set_surface(
        fb->con,
        qemu_create_displaysurface_from(info->fb_width, info->fb_height,
                                        PIXMAN_x8r8g8b8, info->fb_width * 4, ptr));

    /* Route the display window's keyboard to the guest UART: type on the panel. */
    QemuInputHandlerState *ihs = qemu_input_handler_register(NULL, &darwin_kbd_handler);
    qemu_input_handler_activate(ihs);

    printf("[darwin] boot framebuffer: %ux%u @ 0x%" HWADDR_PRIx " (keyboard -> UART live)\n",
           info->fb_width, info->fb_height, info->fb_base);
    fflush(stdout);
}



// ---------------------------------------------------------------------------
// Apple AIC v3 - a real interrupt controller
//
// The stock darwin-vm AIC is zeroed RAM with an IRQ count written into it: it
// cannot deliver an interrupt at all, which is why every device-driven
// subsystem in this machine is inert. This is enough of an AIC to accept
// interrupt lines from devices and hand events to the guest.
//
// Register offsets come from the ADT node itself (rev/cap0/maxnumirq/
// aicglbcfg/extint-baseaddress), event encoding from Linux
// drivers/irqchip/irq-apple-aic.c (GPL-2):
//     DIE[31:24] | TYPE[23:16] | NUM[15:0],  TYPE_IRQ = 1
//
// Masking is intentionally not modelled yet: during bring-up a spurious
// interrupt is harmless, a missing one is not.
// ---------------------------------------------------------------------------

#define AIC_MAX_IRQS            0x1000
#define AIC_EVENT_TYPE_IRQ      1

typedef struct AicState {
    MemoryRegion mr;
    qemu_irq parent_irq;
    uint32_t nr_irqs;
    uint32_t rev_off, cap0_off, maxnumirq_off, glbcfg_off, iack_off;
    uint32_t config;
    uint32_t pending[AIC_MAX_IRQS / 32];
    bool enabled;
} AicState;

static bool aic_next_pending(AicState *s, uint32_t *out) {
    for (uint32_t w = 0; w < s->nr_irqs / 32; w++) {
        if (!s->pending[w]) continue;
        for (uint32_t b = 0; b < 32; b++) {
            if (s->pending[w] & (1u << b)) { *out = w * 32 + b; return true; }
        }
    }
    return false;
}

static int aic_deliver_trace = 24;

static void aic_update(AicState *s) {
    uint32_t irq;
    bool assert_line = s->enabled && aic_next_pending(s, &irq);
    if (assert_line && aic_deliver_trace > 0) {
        aic_deliver_trace--;
        printf("[aic] asserting CPU IRQ for hwirq %u (enabled=%d)\n", irq, s->enabled);
        fflush(stdout);
    }
    qemu_set_irq(s->parent_irq, assert_line);
}

// One GPIO line per hardware interrupt, driven by devices.
static void aic_set_irq(void *opaque, int n, int level) {
    AicState *s = opaque;
    if (n < 0 || n >= (int)s->nr_irqs) return;
    if (level) s->pending[n / 32] |= 1u << (n % 32);
    else       s->pending[n / 32] &= ~(1u << (n % 32));
    aic_update(s);
}

static int aic_trace_budget = 40;

static uint64_t aic_read(void *opaque, hwaddr off, unsigned size) {
    AicState *s = opaque;

    if (aic_trace_budget > 0) {
        aic_trace_budget--;
        printf("[aic] read  +0x%05llX\n", (unsigned long long)off);
        fflush(stdout);
    }

    if (off == s->rev_off)       return 3;             // aic,3
    if (off == s->cap0_off)      return s->nr_irqs;
    if (off == s->maxnumirq_off) return s->nr_irqs;
    if (off == s->glbcfg_off)    return s->config;

    if (off == s->iack_off) {
        // Acknowledge: hand over the lowest pending interrupt and retire it.
        uint32_t irq;
        if (aic_deliver_trace > 0) {
            aic_deliver_trace--;
            printf("[aic] guest read IACK\n");
            fflush(stdout);
        }
        if (!aic_next_pending(s, &irq)) return 0;
        printf("[aic] IACK -> delivering hwirq %u\n", irq);
        fflush(stdout);
        s->pending[irq / 32] &= ~(1u << (irq % 32));
        aic_update(s);
        return ((uint32_t)AIC_EVENT_TYPE_IRQ << 16) | (irq & 0xffff);
    }

    return 0;
}

static void aic_write(void *opaque, hwaddr off, uint64_t val, unsigned size) {
    AicState *s = opaque;

    if (aic_trace_budget > 0) {
        aic_trace_budget--;
        printf("[aic] write +0x%05llX = 0x%llX\n",
               (unsigned long long)off, (unsigned long long)val);
        fflush(stdout);
    }
    if (off == s->glbcfg_off) {
        s->config = (uint32_t)val;
        s->enabled = (val & 1) != 0;
        aic_update(s);
    }
    // Mask set/clear and per-irq config are accepted and ignored for now.
}

static const MemoryRegionOps aic_ops = {
    .read = aic_read,
    .write = aic_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 8,
};

static AicState *g_aic;

static uint32_t adt_u32(struct dtree_node *n, const char *prop, uint32_t dflt) {
    uint32_t *p = adt_get_prop_val(n, prop);
    return p ? *p : dflt;
}

static void init_aic_real(struct dtree_node *dt_root, uint64_t iobase, ARMCPU *cpu) {
    struct dtree_node *aic = adt_find_node(dt_root, "arm-io/aic");
    struct adt_io_reg *reg = adt_get_prop_val(aic, "reg");
    if (!reg) { fprintf(stderr, "aic: no reg\n"); return; }

    AicState *s = g_new0(AicState, 1);
    s->nr_irqs       = AIC_MAX_IRQS;
    s->rev_off       = adt_u32(aic, "rev-offset", 0x0);
    s->cap0_off      = adt_u32(aic, "cap0-offset", 0x4);
    s->maxnumirq_off = adt_u32(aic, "maxnumirq-offset", 0xc);
    s->glbcfg_off    = adt_u32(aic, "aicglbcfg-offset", 0x14);
    s->iack_off      = 0x1000;   // dt_fixup.py publishes aic-iack-offset = 0x1000

    uint64_t *iack = adt_get_prop_val(aic, "aic-iack-offset");
    if (iack) s->iack_off = (uint32_t)*iack;

    memory_region_init_io(&s->mr, NULL, &aic_ops, s, "aic", reg[0].len);
    memory_region_add_subregion(get_system_memory(), reg[0].base + iobase, &s->mr);

    s->parent_irq = qdev_get_gpio_in(DEVICE(cpu), ARM_CPU_IRQ);
    g_aic = s;

    printf("[darwin] aic v3: 0x%llX + 0x%llX, %u irqs, iack@0x%x\n",
           (unsigned long long)(reg[0].base + iobase),
           (unsigned long long)reg[0].len, s->nr_irqs, s->iack_off);
    fflush(stdout);
}

// Devices call this to raise/lower one of their device tree interrupts.
static qemu_irq aic_irq_line(uint32_t hwirq) {
    if (!g_aic || hwirq >= g_aic->nr_irqs) return NULL;
    return qemu_allocate_irq(aic_set_irq, g_aic, hwirq);
}


// ---------------------------------------------------------------------------
// Apple ASC mailbox + RTKit management endpoint (the DCP's front door)
//
// We stand in for the coprocessor. The guest's RTBuddy driver boots the IOP and
// then waits for it to say HELLO; everything after that is a message exchange
// on endpoint 0.
//
// Mailbox register layout: Linux drivers/soc/apple/mailbox.c (GPL-2).
// RTKit protocol:          Linux drivers/soc/apple/rtkit.c   (GPL-2).
//
// Direction convention, from the application processor's point of view:
//   A2I  AP -> IOP   guest writes SEND, we consume
//   I2A  IOP -> AP   we produce, guest reads RECV
// ---------------------------------------------------------------------------

#define ASC_A2I_CONTROL   0x110
#define ASC_A2I_SEND0     0x800
#define ASC_A2I_SEND1     0x808
#define ASC_A2I_RECV0     0x810
#define ASC_A2I_RECV1     0x818
#define ASC_I2A_CONTROL   0x114
#define ASC_I2A_SEND0     0x820
#define ASC_I2A_SEND1     0x828
#define ASC_I2A_RECV0     0x830
#define ASC_I2A_RECV1     0x838
#define ASC_CTRL_FULL     BIT(16)
#define ASC_CTRL_EMPTY    BIT(17)

// Taking the coprocessor out of reset, and the handshake ANS's driver polls for.
// Both from Linux drivers/nvme/host/apple.c (GPL-2); the ASC wrapper is shared,
// so the CPU control register is the same for every iop,ascwrap-v6 block.
#define ASC_COPROC_CPU_CONTROL      0x44
#define ASC_COPROC_CPU_CONTROL_RUN  BIT(4)
#define ASC_ANS_BOOT_STATUS         0x1300
#define ASC_ANS_BOOT_STATUS_OK      0xde71ce55

#define RTKIT_TYPE_SHIFT      52          // msg0 bits [59:52]
#define RTKIT_TYPE_MASK       0xffULL
#define RTKIT_MGMT_HELLO       1
#define RTKIT_MGMT_HELLO_REPLY 2
#define RTKIT_MGMT_STARTEP     5
#define RTKIT_MGMT_IOP_PWR     6
#define RTKIT_MGMT_IOP_PWR_ACK 7
#define RTKIT_MGMT_EPMAP       8
#define RTKIT_MGMT_AP_PWR      0xb
#define RTKIT_VER_MIN          11
#define RTKIT_VER_MAX          12
#define RTKIT_EPMAP_LAST       BIT_ULL(51)

typedef struct AscMsg { uint64_t msg0; uint32_t msg1; } AscMsg;

typedef struct AscMboxState {
    MemoryRegion mr;
    qemu_irq irq;
    AscMsg q[32];
    int head, count;
    uint64_t a2i_msg0;
    bool hello_sent;
    bool running;
    QEMUTimer *announce;
    bool is_ans;
    uint32_t cpu_control;
    const char *name;
} AscMboxState;

static void asc_update_irq(AscMboxState *s) {
    qemu_set_irq(s->irq, s->count > 0);
}

static void asc_push(AscMboxState *s, uint64_t msg0, uint32_t ep) {
    if (s->count == (int)ARRAY_SIZE(s->q)) return;
    int slot = (s->head + s->count) % ARRAY_SIZE(s->q);
    s->q[slot].msg0 = msg0;
    s->q[slot].msg1 = ep;
    s->count++;
    asc_update_irq(s);
}

static void asc_send_mgmt(AscMboxState *s, uint64_t type, uint64_t payload) {
    asc_push(s, (type << RTKIT_TYPE_SHIFT) | payload, 0);
}

static void asc_boot(AscMboxState *s) {
    if (s->hello_sent) return;
    s->hello_sent = true;
    // HELLO carries the protocol range we claim to speak.
    asc_send_mgmt(s, RTKIT_MGMT_HELLO,
                  ((uint64_t)RTKIT_VER_MAX << 16) | RTKIT_VER_MIN);
    printf("[asc:%s] coprocessor boot -> HELLO(min=%d,max=%d)\n",
           s->name, RTKIT_VER_MIN, RTKIT_VER_MAX);
    fflush(stdout);
}

static void asc_handle(AscMboxState *s, uint64_t msg0, uint32_t msg1) {
    uint32_t ep = msg1 & 0xff;
    uint64_t type = (msg0 >> RTKIT_TYPE_SHIFT) & RTKIT_TYPE_MASK;

    if (ep != 0) {
        printf("[asc:%s] msg on endpoint 0x%x (ignored)\n", s->name, ep);
        fflush(stdout);
        return;
    }

    switch (type) {
    case RTKIT_MGMT_HELLO_REPLY: {
        // Advertise the endpoints the guest drivers look for. The display
        // driver (AppleDCPLinkServiceSoC) matches an RTBuddyEndpointService
        // named DCPEndpoint24, i.e. endpoint 0x24, so the DCP must offer it.
        uint64_t bitmap = s->is_ans ? 0 : (1ULL << 0x24);
        printf("[asc:%s] HELLO_REPLY -> EPMAP bitmap 0x%llX\n",
               s->name, (unsigned long long)bitmap);
        asc_send_mgmt(s, RTKIT_MGMT_EPMAP,
                      RTKIT_EPMAP_LAST | (bitmap & 0xffffffffULL));
        break;
    }
    case RTKIT_MGMT_EPMAP:
        printf("[asc:%s] EPMAP acknowledged\n", s->name);
        break;
    case RTKIT_MGMT_STARTEP:
        printf("[asc:%s] STARTEP ep=0x%llx\n", s->name,
               (unsigned long long)((msg0 >> 32) & 0xff));
        break;
    case RTKIT_MGMT_IOP_PWR:
        printf("[asc:%s] SET_IOP_PWR_STATE 0x%llx -> ack\n", s->name,
               (unsigned long long)(msg0 & 0xffff));
        asc_send_mgmt(s, RTKIT_MGMT_IOP_PWR_ACK, msg0 & 0xffff);
        break;
    case RTKIT_MGMT_AP_PWR:
        printf("[asc:%s] SET_AP_PWR_STATE 0x%llx -> ack\n", s->name,
               (unsigned long long)(msg0 & 0xffff));
        asc_send_mgmt(s, RTKIT_MGMT_AP_PWR, msg0 & 0xffff);
        break;
    default:
        printf("[asc:%s] mgmt type %llu (unhandled)\n", s->name,
               (unsigned long long)type);
        break;
    }
    fflush(stdout);
}

static int asc_read_trace = 60;

static uint64_t asc_read(void *opaque, hwaddr off, unsigned size) {
    AscMboxState *s = opaque;

    if (asc_read_trace > 0 && s->hello_sent) {
        asc_read_trace--;
        printf("[asc:%s] read  +0x%03llX\n", s->name, (unsigned long long)off);
        fflush(stdout);
    }

    switch (off) {
    case ASC_COPROC_CPU_CONTROL:
        return s->cpu_control;
    case ASC_ANS_BOOT_STATUS:
        // The ANS driver spins here until the coprocessor reports it is up.
        return (s->is_ans && s->running) ? ASC_ANS_BOOT_STATUS_OK : 0;
    case ASC_I2A_CONTROL:
        return s->count ? 0 : ASC_CTRL_EMPTY;
    case ASC_A2I_CONTROL:
        return ASC_CTRL_EMPTY;          // we always drain immediately
    case ASC_I2A_RECV0:
        return s->count ? s->q[s->head].msg0 : 0;
    case ASC_I2A_RECV1: {
        if (!s->count) return 0;
        uint32_t m1 = s->q[s->head].msg1;
        s->head = (s->head + 1) % ARRAY_SIZE(s->q);
        s->count--;
        asc_update_irq(s);
        return m1;
    }
    default:
        return 0;
    }
}

static void asc_write(void *opaque, hwaddr off, uint64_t val, unsigned size) {
    AscMboxState *s = opaque;

    printf("[asc:%s] write +0x%03llX = 0x%llX\n", s->name,
           (unsigned long long)off, (unsigned long long)val);
    fflush(stdout);

    switch (off) {
    case ASC_COPROC_CPU_CONTROL:
        s->cpu_control = (uint32_t)val;
        if ((val & ASC_COPROC_CPU_CONTROL_RUN) && !s->running) {
            s->running = true;
            printf("[asc:%s] CPU_CONTROL RUN -> coprocessor started\n", s->name);
            fflush(stdout);
            asc_boot(s);
        }
        return;
    case ASC_A2I_SEND0:
        s->a2i_msg0 = val;
        break;
    case ASC_A2I_SEND1:
        asc_handle(s, s->a2i_msg0, (uint32_t)val);
        break;
    default:
        break;
    }
}

static const MemoryRegionOps asc_ops = {
    .read = asc_read,
    .write = asc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 8,
};



// ---------------------------------------------------------------------------
// Apple PMGR power/clock gating
//
// Every block behind a power gate has a PS register: the driver writes the
// state it wants into PS_TARGET and then spins until PS_ACTUAL reflects it.
// With this region unmapped the read is always zero, so bringing a coprocessor
// out of power gate never completes -- which is why nothing ever reached the
// ASC mailbox. Transitions here are instantaneous: ACTUAL follows TARGET.
//
// Field layout from Linux drivers/pmdomain/apple/pmgr-pwrstate.c (GPL-2).
// ---------------------------------------------------------------------------

#define PMGR_PS_TARGET_SHIFT   0
#define PMGR_PS_TARGET_MASK    0xf
#define PMGR_PS_ACTUAL_SHIFT   4
#define PMGR_PS_ACTUAL_MASK    0xf
#define PMGR_WAS_PWRGATED      BIT(8)
#define PMGR_WAS_CLKGATED      BIT(9)

typedef struct PmgrState {
    MemoryRegion mr;
    uint32_t *regs;
    size_t nregs;
    int trace;
} PmgrState;

static uint64_t pmgr_read(void *opaque, hwaddr off, unsigned size) {
    PmgrState *s = opaque;
    size_t i = off >> 2;
    uint64_t v = (i < s->nregs) ? s->regs[i] : 0;
    if (s->trace > 0) {
        s->trace--;
        printf("[pmgr] read  +0x%06llX = 0x%llX\n",
               (unsigned long long)off, (unsigned long long)v);
        fflush(stdout);
    }
    return v;
}

static void pmgr_write(void *opaque, hwaddr off, uint64_t val, unsigned size) {
    PmgrState *s = opaque;
    size_t i = off >> 2;
    if (i >= s->nregs) return;

    uint32_t v = (uint32_t)val;
    uint32_t target = (v >> PMGR_PS_TARGET_SHIFT) & PMGR_PS_TARGET_MASK;

    // Report the transition as already complete, and clear the sticky
    // "was gated" bits the driver acknowledges by writing them back.
    v &= ~(PMGR_PS_ACTUAL_MASK << PMGR_PS_ACTUAL_SHIFT);
    v |= target << PMGR_PS_ACTUAL_SHIFT;
    v &= ~(PMGR_WAS_PWRGATED | PMGR_WAS_CLKGATED);
    s->regs[i] = v;

    if (s->trace > 0) {
        s->trace--;
        printf("[pmgr] write +0x%06llX = 0x%llX -> ps %u\n",
               (unsigned long long)off, (unsigned long long)val, target);
        fflush(stdout);
    }
}

static const MemoryRegionOps pmgr_ops = {
    .read = pmgr_read,
    .write = pmgr_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 8,
};

static void init_pmgr(struct dtree_node *dt_root, uint64_t iobase) {
    struct dtree_node *n = adt_find_node(dt_root, "arm-io/pmgr");
    if (!n) { printf("[pmgr] no arm-io/pmgr node\n"); return; }
    struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
    size_t len = reg ? adt_get_prop_len(n, "reg") : 0;
    if (!reg || len < sizeof(*reg)) { printf("[pmgr] no reg\n"); return; }

    for (size_t j = 0; j < len / sizeof(*reg); j++) {
        if (!reg[j].len) continue;
        PmgrState *s = g_new0(PmgrState, 1);
        s->nregs = reg[j].len >> 2;
        s->regs = g_new0(uint32_t, s->nregs);
        s->trace = (j == 0) ? 30 : 0;
        char *nm = g_strdup_printf("pmgr[%zu]", j);
        memory_region_init_io(&s->mr, NULL, &pmgr_ops, s, nm, reg[j].len);
        memory_region_add_subregion_overlap(get_system_memory(),
                                            reg[j].base + iobase, &s->mr, 1);
        printf("[pmgr] %s 0x%llX + 0x%llX\n", nm,
               (unsigned long long)(reg[j].base + iobase),
               (unsigned long long)reg[j].len);
        g_free(nm);
    }
    fflush(stdout);
}

// ---------------------------------------------------------------------------
// ANS NVMe register window
//
// The ANS block has two separate MMIO regions: the ASC mailbox (reg[0], where
// CPU_CONTROL lives) and a 16MB NVMe window (reg[4]) holding BOOT_STATUS, the
// doorbells and the NVMMU. The driver polls BOOT_STATUS there for the
// coprocessor's ready magic, so leaving it unmapped strands start().
//
// Offsets from Linux drivers/nvme/host/apple.c (GPL-2).
// ---------------------------------------------------------------------------

#define ANS_NVME_BOOT_STATUS        0x1300
#define ANS_NVME_BOOT_STATUS_OK     0xde71ce55
#define ANS_NVME_ACQ_DB             0x1004
#define ANS_NVME_IOCQ_DB            0x100c
#define ANS_NVME_MAX_PEND_CMDS      0x1210
#define ANS_NVME_LINEAR_SQ_CTRL     0x24908
#define ANS_NVMMU_NUM_TCBS          0x28100
#define ANS_NVMMU_TCB_STAT          0x28120

typedef struct AnsNvmeState {
    MemoryRegion mr;
    AscMboxState *asc;     // so BOOT_STATUS can follow the coprocessor
    AppleRTKit *rtk;       // ...or the RTKit engine, when that is driving it
    uint32_t linear_sq_ctrl;
    uint32_t num_tcbs;
    int trace;
} AnsNvmeState;

static uint64_t ans_nvme_read(void *opaque, hwaddr off, unsigned size) {
    AnsNvmeState *s = opaque;
    uint64_t v = 0;

    switch (off) {
    case ANS_NVME_BOOT_STATUS:
        if (s->rtk) {
            v = s->rtk->running ? ANS_NVME_BOOT_STATUS_OK : 0;
        } else {
            v = (s->asc && s->asc->running) ? ANS_NVME_BOOT_STATUS_OK : 0;
        }
        break;
    case ANS_NVME_LINEAR_SQ_CTRL:
        v = s->linear_sq_ctrl;
        break;
    case ANS_NVMMU_NUM_TCBS:
        v = s->num_tcbs;
        break;
    default:
        break;
    }

    if (s->trace > 0) {
        s->trace--;
        printf("[ans-nvme] read  +0x%05llX = 0x%llX\n",
               (unsigned long long)off, (unsigned long long)v);
        fflush(stdout);
    }
    return v;
}

static void ans_nvme_write(void *opaque, hwaddr off, uint64_t val, unsigned size) {
    AnsNvmeState *s = opaque;

    if (s->trace > 0) {
        s->trace--;
        printf("[ans-nvme] write +0x%05llX = 0x%llX\n",
               (unsigned long long)off, (unsigned long long)val);
        fflush(stdout);
    }

    switch (off) {
    case ANS_NVME_LINEAR_SQ_CTRL: s->linear_sq_ctrl = (uint32_t)val; break;
    case ANS_NVMMU_NUM_TCBS:      s->num_tcbs = (uint32_t)val; break;
    default: break;
    }
}

static const MemoryRegionOps ans_nvme_ops = {
    .read = ans_nvme_read,
    .write = ans_nvme_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 8,
};

// Nothing in a restore ramdisk ever demands a coprocessor, so RTBuddy never
// takes one out of reset and the mailbox stays silent forever. Here the
// coprocessor announces itself instead: after the guest has had time to attach
// its driver, we behave as if firmware had booted on its own and say HELLO.
// Real silicon does not do this; it is a way to find out whether RTBuddy will
// carry on with the handshake when the other side speaks first.
static void asc_announce_cb(void *opaque) {
    AscMboxState *s = opaque;
    if (s->hello_sent) return;
    printf("[asc:%s] self-announce: pretending firmware booted\n", s->name);
    fflush(stdout);
    s->running = true;
    asc_boot(s);
}

static AscMboxState *init_one_asc(struct dtree_node *dt_root, uint64_t iobase,
                         const char *path, const char *label, bool is_ans) {
    struct dtree_node *n = adt_find_node(dt_root, path);
    if (!n) { printf("[asc] no %s node\n", path); return NULL; }

    struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
    size_t rlen = reg ? adt_get_prop_len(n, "reg") : 0;
    if (!reg || rlen < sizeof(*reg)) { printf("[asc] %s has no reg\n", label); return NULL; }

    uint32_t *irqs = adt_get_prop_val(n, "interrupts");
    size_t ilen = irqs ? adt_get_prop_len(n, "interrupts") : 0;

    AscMboxState *s = g_new0(AscMboxState, 1);
    s->name = label;
    s->is_ans = is_ans;
    memory_region_init_io(&s->mr, NULL, &asc_ops, s, label, reg[0].len);
    memory_region_add_subregion_overlap(get_system_memory(),
                                        reg[0].base + iobase, &s->mr, 1);

    if (irqs && ilen >= 4) {
        s->irq = aic_irq_line(irqs[0]);
        printf("[asc:%s] 0x%llX + 0x%llX, irq %u\n", label,
               (unsigned long long)(reg[0].base + iobase),
               (unsigned long long)reg[0].len, irqs[0]);
    } else {
        printf("[asc:%s] mapped without an interrupt line\n", label);
    }

    const char *delay = getenv("DARWIN_ASC_ANNOUNCE");
    if (delay) {
        int secs = atoi(delay);
        if (secs <= 0) secs = 25;
        s->announce = timer_new_ms(QEMU_CLOCK_VIRTUAL, asc_announce_cb, s);
        timer_mod(s->announce,
                  qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + (int64_t)secs * 1000);
        printf("[asc:%s] will self-announce in %ds\n", label, secs);
    }
    fflush(stdout);
    return s;
}

static AscMboxState *g_ans_asc;
static AppleRTKit *g_ans_rtk;

static void init_ans_nvme(struct dtree_node *dt_root, uint64_t iobase) {
    struct dtree_node *n = adt_find_node(dt_root, "arm-io/ans");
    if (!n) return;
    struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
    size_t len = reg ? adt_get_prop_len(n, "reg") : 0;
    size_t count = len / sizeof(*reg);

    // The NVMe window is the large one; on t8140 it is the 16MB entry.
    int best = -1;
    for (size_t i = 0; i < count; i++) {
        if (reg[i].len < 0x100000) continue;
        if (best < 0 || reg[i].len > reg[best].len) best = (int)i;
    }
    if (best < 0) { printf("[ans-nvme] no large reg window\n"); return; }

    AnsNvmeState *s = g_new0(AnsNvmeState, 1);
    s->asc = g_ans_asc;
    s->rtk = g_ans_rtk;
    s->trace = 60;
    memory_region_init_io(&s->mr, NULL, &ans_nvme_ops, s, "ans-nvme", reg[best].len);
    memory_region_add_subregion_overlap(get_system_memory(),
                                        reg[best].base + iobase, &s->mr, 1);
    printf("[ans-nvme] 0x%llX + 0x%llX (reg[%d])\n",
           (unsigned long long)(reg[best].base + iobase),
           (unsigned long long)reg[best].len, best);
    fflush(stdout);
}

static void init_asc_mailbox(struct dtree_node *dt_root, uint64_t iobase) {
    init_one_asc(dt_root, iobase, "arm-io/dcp", "dcp", false);
    g_ans_asc = init_one_asc(dt_root, iobase, "arm-io/ans", "ans", true);
    init_ans_nvme(dt_root, iobase);
}

// The RTKit engine: a fuller coprocessor model than the inline mailbox above.
// DARWIN_RTKIT=1 selects it for the DCP so the display driver can get past the
// handshake and start speaking its own protocol to us.
static void init_rtkit_dcp(struct dtree_node *dt_root, uint64_t iobase,
                           struct xnu_boot_info *info) {
    struct dtree_node *n = adt_find_node(dt_root, "arm-io/dcp");
    if (!n) { printf("[rtkit] no arm-io/dcp node\n"); return; }

    struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
    size_t rlen = reg ? adt_get_prop_len(n, "reg") : 0;
    if (!reg || rlen < sizeof(*reg)) { printf("[rtkit] dcp has no reg\n"); return; }

    uint32_t *irqs = adt_get_prop_val(n, "interrupts");
    size_t ilen = irqs ? adt_get_prop_len(n, "interrupts") : 0;
    qemu_irq line = (irqs && ilen >= 4) ? aic_irq_line(irqs[0]) : NULL;

    AppleRTKit *rtk = apple_rtkit_new("dcp", reg[0].base + iobase,
                                      reg[0].len, line);
    apple_dcp_attach(rtk, info->fb_width ? info->fb_width : DARWIN_FB_WIDTH,
                     info->fb_height ? info->fb_height : DARWIN_FB_HEIGHT,
                     info->fb_base);

    const char *ann = getenv("DARWIN_RTKIT_ANNOUNCE");
    if (ann) {
        apple_rtkit_announce_after(rtk, atoi(ann) > 0 ? atoi(ann) : 30);
    }
}

// Point the RTKit engine at the ANS instead, whose RTBuddy driver has no secure
// route and comes up cleanly -- a way to validate the engine's handshake
// against a real Apple driver that will actually drive it.
static void init_rtkit_ans(struct dtree_node *dt_root, uint64_t iobase,
                           struct xnu_boot_info *info) {
    struct dtree_node *n = adt_find_node(dt_root, "arm-io/ans");
    if (!n) { printf("[rtkit] no arm-io/ans node\n"); return; }
    struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
    size_t rlen = reg ? adt_get_prop_len(n, "reg") : 0;
    if (!reg || rlen < sizeof(*reg)) { printf("[rtkit] ans has no reg\n"); return; }
    uint32_t *irqs = adt_get_prop_val(n, "interrupts");
    size_t ilen = irqs ? adt_get_prop_len(n, "interrupts") : 0;
    qemu_irq line = (irqs && ilen >= 4) ? aic_irq_line(irqs[0]) : NULL;
    AppleRTKit *rtk = apple_rtkit_new("ans", reg[0].base + iobase, reg[0].len, line);
    g_ans_rtk = rtk;
    init_ans_nvme(dt_root, iobase);   /* BOOT_STATUS/doorbells live in a second window */
    const char *ann = getenv("DARWIN_RTKIT_ANNOUNCE");
    if (ann) apple_rtkit_announce_after(rtk, atoi(ann) > 0 ? atoi(ann) : 30);
}

// ---------------------------------------------------------------------------
// Apple DART (t8110) - minimal model
//
// Just enough register behaviour for the iOS AppleDART driver to finish
// initialising. It does not translate addresses; nothing in this machine DMAs
// yet. Without it the driver spins during bring-up and the guest never boots.
//
// Register layout follows Linux drivers/iommu/apple-dart.c (GPL-2).
// ---------------------------------------------------------------------------

#define DART_T8110_PARAMS3          0x008
#define DART_T8110_PARAMS4          0x00c
#define DART_T8110_TLB_CMD          0x080
#define DART_T8110_ERROR            0x100
#define DART_T8110_ERROR_MASK       0x104
#define DART_T8110_PROTECT          0x200
#define DART_T8110_UNPROTECT        0x204
#define DART_T8110_PROTECT_LOCK     0x208
#define DART_T8110_ENABLE_STREAMS   0xc00
#define DART_T8110_DISABLE_STREAMS  0xc20
#define DART_T8110_TCR              0x1000
#define DART_T8110_TTBR             0x1400
#define DART_SID_COUNT              256

typedef struct DartState {
    MemoryRegion mr;
    uint32_t tcr[DART_SID_COUNT];
    uint32_t ttbr[DART_SID_COUNT];
    uint32_t enabled_streams;
    uint32_t protect;
    uint32_t error_mask;
} DartState;

static uint64_t dart_read(void *opaque, hwaddr off, unsigned size) {
    DartState *s = opaque;

    if (off >= DART_T8110_TTBR && off < DART_T8110_TTBR + DART_SID_COUNT * 4) {
        return s->ttbr[(off - DART_T8110_TTBR) >> 2];
    }
    if (off >= DART_T8110_TCR && off < DART_T8110_TCR + DART_SID_COUNT * 4) {
        return s->tcr[(off - DART_T8110_TCR) >> 2];
    }

    switch (off) {
    case DART_T8110_PARAMS3:
        // PA width 42, VA width 32, version 1.0
        return (42u << 24) | (32u << 16) | (1u << 8);
    case DART_T8110_PARAMS4:
        // 16 clients, DART_SID_COUNT stream ids
        return (16u << 16) | DART_SID_COUNT;
    case DART_T8110_TLB_CMD:
        // Bit 31 is BUSY. Always report idle: our flushes are instantaneous,
        // so the driver's poll loop exits immediately.
        return 0;
    case DART_T8110_ERROR:
        return 0;
    case DART_T8110_ERROR_MASK:
        return s->error_mask;
    case DART_T8110_PROTECT:
        return s->protect;
    case DART_T8110_ENABLE_STREAMS:
        return s->enabled_streams;
    default:
        return 0;
    }
}

static void dart_write(void *opaque, hwaddr off, uint64_t val, unsigned size) {
    DartState *s = opaque;

    if (off >= DART_T8110_TTBR && off < DART_T8110_TTBR + DART_SID_COUNT * 4) {
        s->ttbr[(off - DART_T8110_TTBR) >> 2] = (uint32_t)val;
        return;
    }
    if (off >= DART_T8110_TCR && off < DART_T8110_TCR + DART_SID_COUNT * 4) {
        s->tcr[(off - DART_T8110_TCR) >> 2] = (uint32_t)val;
        return;
    }

    switch (off) {
    case DART_T8110_ERROR_MASK:      s->error_mask = val; break;
    case DART_T8110_PROTECT:         s->protect |= val; break;
    case DART_T8110_UNPROTECT:       s->protect &= ~(uint32_t)val; break;
    case DART_T8110_ENABLE_STREAMS:  s->enabled_streams |= val; break;
    case DART_T8110_DISABLE_STREAMS: s->enabled_streams &= ~(uint32_t)val; break;
    default: break;   // TLB_CMD and friends: accepted and completed instantly
    }
}

static const MemoryRegionOps dart_ops = {
    .read = dart_read,
    .write = dart_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 8,
};

static void create_dart(const char *name, hwaddr base, uint64_t len) {
    DartState *s = g_new0(DartState, 1);
    memory_region_init_io(&s->mr, NULL, &dart_ops, s, name, len);
    memory_region_add_subregion(get_system_memory(), base, &s->mr);
    printf("[darwin] dart %-20s 0x%llX + 0x%llX\n", name,
           (unsigned long long)base, (unsigned long long)len);
}

static void init_darts(struct dtree_node *dt_root, uint64_t iobase) {
    static const char *const darts[] = {
        "arm-io/dart-disp0",
        "arm-io/dart-dcp",
    };

    for (size_t i = 0; i < ARRAY_SIZE(darts); i++) {
        struct dtree_node *n = adt_find_node(dt_root, darts[i]);
        if (!n) continue;
        struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
        size_t len = reg ? adt_get_prop_len(n, "reg") : 0;
        if (!reg || len < sizeof(*reg)) continue;
        for (size_t j = 0; j < len / sizeof(*reg); j++) {
            if (0 == reg[j].len) continue;
            char *nm = g_strdup_printf("%s[%zu]", darts[i], j);
            create_dart(nm, reg[j].base + iobase, reg[j].len);
            g_free(nm);
        }
    }
    fflush(stdout);
}

// Bring-up aid: map every register range of the display stack as a logging
// dummy device, so we can see exactly what the iOS drivers touch. Pair with
// a device tree built with EXTRA_DRIVERS so IOKit actually matches them, and
// run qemu with -d unimp to get the trace.
static void init_display_stub(struct dtree_node *dt_root, uint64_t iobase) {
    static const char *const nodes[] = {
        "arm-io/disp0",
        "arm-io/dcp",
        "arm-io/dcp0-expert",
        "arm-io/dart-disp0",
        "arm-io/dart-dcp",
        "arm-io/display-crossbar0",
    };

    // DARWIN_DISP=all stubs everything; otherwise it is a substring filter so
    // we can bisect which range upsets the boot.
    const char *want = getenv("DARWIN_DISP");
    for (size_t i = 0; i < ARRAY_SIZE(nodes); i++) {
        if (want && strcmp(want, "all") && strcmp(want, "1") &&
            !strstr(nodes[i], want)) {
            continue;
        }
        struct dtree_node *n = adt_find_node(dt_root, nodes[i]);
        if (!n) {
            printf("[darwin] display: %s absent from dtree\n", nodes[i]);
            continue;
        }
        struct adt_io_reg *reg = adt_get_prop_val(n, "reg");
        size_t len = reg ? adt_get_prop_len(n, "reg") : 0;
        if (!reg || len < sizeof(*reg)) {
            printf("[darwin] display: %s has no reg\n", nodes[i]);
            continue;
        }
        for (size_t j = 0; j < len / sizeof(*reg); j++) {
            if (0 == reg[j].len) continue;
            char *nm = g_strdup_printf("%s[%zu]", nodes[i], j);
            hwaddr base = reg[j].base + iobase;
            printf("[darwin] display stub %-26s 0x%llX + 0x%llX\n",
                   nm, (unsigned long long)base, (unsigned long long)reg[j].len);
            create_unimplemented_device(nm, base, reg[j].len);
            g_free(nm);
        }
    }
    fflush(stdout);
}

static void darwin_init(MachineState *ms) {
    DarwinState *s = DARWIN_MACHINE(ms);
    struct xnu_boot_info *info = &s->bootinfo;
    struct dtree_node *dt_root;

    if (!info->args) info->args = g_default_args;
    info->bootkc_f = check_and_open(info->bootkc, "error opening XNU kernel");
    info->dtree_f = check_and_open(info->dtree, "error opening device tree");
    info->tc_f = check_and_open(info->tc, "error opening trust cache");
    info->ramdisk_f = check_and_open(info->ramdisk, "error opening ramdisk");
    if (info->cl4) {
        info->cl4_f = check_and_open(info->cl4, "error opening CL4 secure kernel");
        printf("[cl4] secure kernel: %llu bytes\n",
               (unsigned long long)info->cl4_f.len);
        fflush(stdout);
    }
    if (info->sptm) {
        info->sptm_f = check_and_open(info->sptm, "error opening SPTM");
        info->txm_f = check_and_open(info->txm, "error opening TXM");
    }
    dt_root = info->dtree_f.buf;

    check_dtree(dt_root);

    info->has_mte = kc_uses_mte(info->bootkc_f.buf);

    Object *cpuobj = object_new(ms->cpu_type);
    DeviceState *cpudev = DEVICE(cpuobj);
    ARMCPU *cpu = ARM_CPU(cpuobj);

    cpu->has_el2 = true;
    cpu->has_el3 = false;

    // Disable CBAR because some MSRs conflict with Apple Si specific ones (see aarch64_a57_initfn)
    unset_feature(&cpu->env, ARM_FEATURE_CBAR);
    unset_feature(&cpu->env, ARM_FEATURE_CBAR_RO);
    unset_feature(&cpu->env, ARM_FEATURE_EL3);
    unset_feature(&cpu->env, ARM_FEATURE_PMU);

    // SPTM requires EL2, and non-SPTM XNU can run in either EL1 or EL2, so just always use EL2
    set_feature(&cpu->env, ARM_FEATURE_EL2);

    struct dtree_node *cpu_node = adt_find_node(dt_root, "cpus/cpu0");
    u32 dtree_frq = *(u32*)adt_get_prop_val(cpu_node, "clock-frequency");
    cpu->gt_cntfrq_hz = dtree_frq;

    struct dtree_node *chosen_node = adt_find_node(dt_root, "chosen");
    info->dram_base = *(u64*)adt_get_prop_val(chosen_node, "dram-base");
    info->dram_size = *(u64*)adt_get_prop_val(chosen_node, "dram-size");

    const char *dcpfw = getenv("DARWIN_DCPFW");
    if (dcpfw) {
        info->dcpfw = g_strdup(dcpfw);
        info->dcpfw_f = check_and_open(info->dcpfw, "error opening DCP firmware");
        uint64_t want = ROUND_NEXT_PAGE(info->dcpfw_f.len) + (64 * ONE_MB);
        info->dcpfw_region = ROUND_UP_POW2(want, DARWIN_HUGE_PAGE_SIZE);
    }

    const char *ansfw = getenv("DARWIN_ANSFW");
    if (ansfw) {
        info->ansfw = g_strdup(ansfw);
        info->ansfw_f = check_and_open(info->ansfw, "error opening ANS firmware");
        // Give the coprocessor room beyond the image itself for its working set.
        uint64_t want = ROUND_NEXT_PAGE(info->ansfw_f.len) + (64 * ONE_MB);
        info->ansfw_region = ROUND_UP_POW2(want, DARWIN_HUGE_PAGE_SIZE);
    }

    // Boot framebuffer is opt-in while it is being brought up: DARWIN_FB=1
    // enables the carve + boot_args.Video, DARWIN_FB=carve reserves the pixels
    // but leaves Video zeroed, which isolates the memory layout from the
    // display handoff when something regresses.
    const char *fb_mode = getenv("DARWIN_FB");
    if (fb_mode) {
        info->fb_width  = DARWIN_FB_WIDTH;
        info->fb_height = DARWIN_FB_HEIGHT;
        info->fb_size   = ROUND_NEXT_PAGE((uint64_t)info->fb_width * info->fb_height * 4);
        info->fb_video  = (0 != strcmp(fb_mode, "carve"));
    }

    s->cpu = ARM_CPU(cpuobj);
    arm_load_xnu(s->cpu, ms, info);
    init_framebuffer(info);
    if (info->has_mte) setup_mte(cpuobj, MACHINE(s), info);

    struct dtree_node *amcc_node = adt_find_node(dt_root, "chosen/lock-regs/amcc");
    AMCCState *amcc_dev = NULL;
    if (amcc_node) {
        amcc_dev = (AMCCState*)amcc_create(amcc_node);
    }
    apple_regs_init(cpu, amcc_dev, dt_root, info);

    struct dtree_node *arm_io = adt_find_node(dt_root, "arm-io");
    uint64_t *arm_io_ranges = adt_get_prop_val(arm_io, "ranges");
    uint64_t iobase = arm_io_ranges[IO_RANGE_BASE_OFFSET];
    assert(0 == arm_io_ranges[0]); // child bus phys addr must be zero

    init_uart(dt_root, iobase);
    if (getenv("DARWIN_AIC")) init_aic_real(dt_root, iobase, cpu);
    else                      init_aic(dt_root, iobase);
    // Catch-all MMIO logger under everything else. Without this we only ever
    // see accesses to regions we already model, which makes "no accesses" an
    // ambiguous result: it cannot distinguish a driver that never runs from one
    // touching registers we forgot to map.
    if (getenv("DARWIN_TRACEIO")) {
        uint64_t *r = adt_get_prop_val(arm_io, "ranges");
        size_t rl = adt_get_prop_len(arm_io, "ranges");
        if (r && rl >= 24) {
            create_unimplemented_device("arm-io-catchall", r[1], r[2]);
            printf("[traceio] catch-all 0x%llX + 0x%llX\n",
                   (unsigned long long)r[1], (unsigned long long)r[2]);
            fflush(stdout);
        }
    }

    if (getenv("DARWIN_PMGR")) init_pmgr(dt_root, iobase);
    if (getenv("DARWIN_DART")) init_darts(dt_root, iobase);
    if (getenv("DARWIN_RTKIT_ANS")) init_rtkit_ans(dt_root, iobase, info);
    else if (getenv("DARWIN_RTKIT")) init_rtkit_dcp(dt_root, iobase, info);
    else if (getenv("DARWIN_ASC")) init_asc_mailbox(dt_root, iobase);
    if (getenv("DARWIN_DISP")) init_display_stub(dt_root, iobase);
    init_sep(dt_root);
    init_cpu_impl(dt_root);

    // M4 (T8132) asserts SME's max VQ len is this many.
    // Specifically, rdsvl   x8, #0x1 must return 0x40.
    s->cpu->sme_vq.supported = 0x0b;

    qdev_realize(DEVICE(cpuobj), NULL, &error_fatal);

    // On Apple Si, FIQ is hardwired to platform timer
    qdev_connect_gpio_out(cpudev, GTIMER_HYPVIRT, qdev_get_gpio_in(cpudev, ARM_CPU_FIQ));

    qemu_register_reset(do_darwin_reset, s);
    munmap(info->bootkc_f.buf, info->bootkc_f.len);
    munmap(info->dtree_f.buf, info->dtree_f.len);
    munmap(info->tc_f.buf, info->tc_f.len);
    munmap(info->ramdisk_f.buf, info->ramdisk_f.len);
    if (info->sptm) {
        munmap(info->sptm_f.buf, info->sptm_f.len);
        munmap(info->txm_f.buf, info->txm_f.len);
    }
}

static void darwin_machine_init(MachineClass *mc) {
    mc->desc = "Generic Apple Silicon Device";
    mc->init = darwin_init;
    mc->max_cpus = 1;
    mc->default_cpu_type = ARM_CPU_TYPE_NAME("max");
}

static void darwin_machine_class_init(ObjectClass *oc, const void *data) {
    MachineClass *mc = MACHINE_CLASS(oc);

    object_class_property_add_str(oc, "bootkc", bootkc_darwin_class_get, bootkc_darwin_class_set);
    object_class_property_add_str(oc, "args", args_darwin_class_get, args_darwin_class_set);
    object_class_property_add_str(oc, "dtree", dtree_darwin_class_get, dtree_darwin_class_set);
    object_class_property_add_str(oc, "sptm", sptm_darwin_class_get, sptm_darwin_class_set);
    object_class_property_add_str(oc, "txm", txm_darwin_class_get, txm_darwin_class_set);
    object_class_property_add_str(oc, "cl4", cl4_darwin_class_get, cl4_darwin_class_set);
    object_class_property_add_str(oc, "tc", tc_darwin_class_get, tc_darwin_class_set);
    object_class_property_add_str(oc, "ramdisk", ramdisk_darwin_class_get, ramdisk_darwin_class_set);

    darwin_machine_init(mc);
}

static const TypeInfo darwin_machine_typeinfo = {
    .name           =  TYPE_DARWIN_MACHINE,
    .parent         =  TYPE_MACHINE,
    .class_init     =  darwin_machine_class_init,
    .instance_size  =  sizeof(DarwinState),
    .abstract       =  false,
    .interfaces     =  arm_machine_interfaces,
};

static void darwin_register_types(void) {
    type_register_static(&darwin_machine_typeinfo);
}

type_init(darwin_register_types)
