import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot2"

# Runtime (slide-independent within file): insn at ...2d978 = ldr w2,[sp,#0xc] (0xB9400FE2?)
# We locate the retry-loop tail by its distinctive neighbor triplet:
#   978: ldr w2, [sp, #0xc]      -> bytes E2 0F 40 B9
#   97c: b 0x...2d94c (back -0x30) -> F4 FF FF 17
#   980: bl 0x...2c52e0c8         -> computed below, same in file (position-dependent but fixed)
# Verify bl target: bl_imm = (0x2c52e0c8 - 0x2c2d980) >> 2, encoding = 0x94000000 | (imm & 0x3FFFFFF)
bl_imm = (0xFFFFFE002C52E0C8 - 0xFFFFFE002BC2D980) >> 2
bl_enc = (0x94000000 | (bl_imm & 0x03FFFFFF)) & 0xFFFFFFFF
print("expected bl @980: 0x%08x" % bl_enc)

data = bytearray(open(SRC, "rb").read())
print("size 0x%x" % len(data))

pat_b = struct.pack("<I", 0x17FFFFF4)
cands = []
i = 0
while True:
    i = data.find(pat_b, i)
    if i < 0:
        break
    cands.append(i)
    i += 1
print("raw B-to-(-0x30) candidates:", len(cands))

hits = []
for off in cands:
    if off < 8:
        continue
    prev2 = struct.unpack_from("<I", data, off - 4)[0]   # should be ldr w2,[sp,#0xc] = 0xB9400FE2
    nxt = struct.unpack_from("<I", data, off + 4)[0]    # should be bl to ...52e0c8
    if prev2 == 0xB9400FE2 and nxt == bl_enc:
        # also check one more: off+8 should be bl ...81030? compute: (0x2BD81030-0x2C2D984)>>2
        bl2_imm = (0xFFFFFE002BD81030 - 0xFFFFFE002BC2D984) >> 2
        bl2_enc = (0x94000000 | (bl2_imm & 0x03FFFFFF)) & 0xFFFFFFFF
        nxt2 = struct.unpack_from("<I", data, off + 8)[0]
        if nxt2 == bl2_enc:
            hits.append(off)

print("full-triplet hits:", [hex(h) for h in hits])
if len(hits) != 1:
    print("ABORT: need exactly 1 hit")
    sys.exit(1)

off = hits[0]
print("patching fileoff 0x%x: b->94c => b->98c (0x14000004)" % off)
shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, off, 0x14000004)
open(DST, "wb").write(d2)
print("wrote", DST)
