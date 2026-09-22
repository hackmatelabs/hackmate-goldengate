import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot4"

# be64: mov x21, #0xd507  ; be68: blraa x20, x21 ; be6c: mrs x0, TPIDR_EL1
# movz x21,#0xd507: 1101 0010 1011 0101 0000 1111 10101 -> compute
mov_enc = (0xD2800000 | (0xD507 << 5) | 21) & 0xFFFFFFFF
print("mov x21,#0xd507 = 0x%08x" % mov_enc)
mrs_enc = 0xD538D020  # mrs x0, TPIDR_EL1
print("mrs x0,tpidr = 0x%08x" % mrs_enc)

data = bytearray(open(SRC, "rb").read())
print("size 0x%x" % len(data))

hits = []
needle = bytes.fromhex("f5a09ad2950a3fd780d038d5")
i = 0
while True:
    i = data.find(needle, i)
    if i < 0:
        break
    hits.append((i, struct.unpack_from("<I", data, i + 4)[0]))
    i += 1

print("hits:", [(hex(h), hex(v)) for (h, v) in hits])
if len(hits) != 1:
    print("ABORT: need exactly 1 hit")
    sys.exit(1)

off, blraa = hits[0]
print("patching fileoff 0x%x: blraa 0x%08x => NOP" % (off + 4, blraa))
shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, off + 4, 0xD503201F)
open(DST, "wb").write(d2)
print("wrote", DST)
