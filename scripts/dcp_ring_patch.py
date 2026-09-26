from pathlib import Path
p=Path('~/goldengate/qemu-sptm-cl4-native/hw/arm/apple_dcp.c').expanduser()
s=p.read_text()
needle='''typedef struct AppleDCPState {
'''
insert='''typedef struct DcpAfkRingHeader {
    uint32_t bufsz;
    uint32_t unk;
    uint32_t pad1[14];
    uint32_t rptr;
    uint32_t pad2[15];
    uint32_t wptr;
    uint32_t pad3[15];
} DcpAfkRingHeader;

typedef struct DcpAfkQueueEntry {
    uint32_t magic;
    uint32_t size;
    uint32_t channel;
    uint32_t type;
} DcpAfkQueueEntry;

#define DCP_AFQ_MAGIC 0x20504f49u
#define DCP_AFQ_HDR_SIZE 192u

'''+needle
if needle not in s: raise SystemExit('struct needle missing')
s=s.replace(needle,insert,1)
needle2='''static bool dcp_ep_handler(AppleRTKit *rtk, uint32_t ep, uint64_t msg,
                           void *opaque)
'''
func='''static void dcp_dump_epic_ring(AppleDCPState *s)
{
    uint8_t raw[sizeof(DcpAfkRingHeader) + sizeof(DcpAfkQueueEntry) + 64];
    MemTxResult mr = address_space_read(&address_space_memory, s->bfr_dva,
                                        MEMTXATTRS_UNSPECIFIED, raw, sizeof(raw));
    if (mr != MEMTX_OK) {
        printf("[dcp] AFK ring read failed at 0x%llx (status %d)\\n",
               (unsigned long long)s->bfr_dva, mr);
        return;
    }
    DcpAfkRingHeader *rh = (DcpAfkRingHeader *)raw;
    uint32_t bufsz = le32_to_cpu(rh->bufsz);
    uint32_t rptr = le32_to_cpu(rh->rptr);
    uint32_t wptr = le32_to_cpu(rh->wptr);
    printf("[dcp] AFK TX ring: bufsz=0x%x rptr=0x%x wptr=0x%x\\n",
           bufsz, rptr, wptr);
    if (rptr == wptr || rptr >= bufsz || rptr + sizeof(DcpAfkQueueEntry) > bufsz) return;
    uint8_t qe_raw[sizeof(DcpAfkQueueEntry) + 64] = {0};
    hwaddr qe_addr = s->bfr_dva + DCP_AFQ_HDR_SIZE + rptr;
    mr = address_space_read(&address_space_memory, qe_addr,
                            MEMTXATTRS_UNSPECIFIED, qe_raw, sizeof(qe_raw));
    if (mr != MEMTX_OK) return;
    DcpAfkQueueEntry *qe = (DcpAfkQueueEntry *)qe_raw;
    uint32_t magic = le32_to_cpu(qe->magic), size = le32_to_cpu(qe->size);
    uint32_t channel = le32_to_cpu(qe->channel), type = le32_to_cpu(qe->type);
    printf("[dcp] AFK QE: magic=0x%x size=0x%x channel=%u type=%u\\n",
           magic, size, channel, type);
    if (magic != DCP_AFQ_MAGIC || size == 0 || size > 64) return;
    printf("[dcp] EPIC bytes:");
    for (uint32_t i = 0; i < size && i < 64; i++) printf(" %02x", qe_raw[16 + i]);
    printf("\\n");
    fflush(stdout);
}

'''+needle2
if needle2 not in s: raise SystemExit('handler needle missing')
s=s.replace(needle2,func,1)
old='''        MemoryRegionSection sec = memory_region_find(get_system_memory(),
                                                       s->bfr_dva, 0x800);'''
new='''        dcp_dump_epic_ring(s);
        MemoryRegionSection sec = memory_region_find(get_system_memory(),
                                                       s->bfr_dva, 0x800);'''
if old not in s: raise SystemExit('recv needle missing')
s=s.replace(old,new,1)
p.write_text(s)