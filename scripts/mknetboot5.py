import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot5"

# ...9140 entry (static 0x0BC29140 in __TEXT_EXEC): pacib* ; sub sp,sp,#0x90
OFF = 0xBC29140 - 0x7004000
print("target fileoff 0x%x" % OFF)
assert OFF == 0x4C25140, "unexpected offset"

data = bytearray(open(SRC, "rb").read())
u0 = struct.unpack_from("<I", data, OFF)[0]
u1 = struct.unpack_from("<I", data, OFF + 4)[0]
print("current: 0x%08x 0x%08x" % (u0, u1))
if u0 not in (0xD503233F, 0xD503237F):
    print("ABORT: entry mismatch")
    sys.exit(1)
if (u1 & 0xFF000000) != 0xD1000000:
    print("ABORT: second insn not sub")
    sys.exit(1)

shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, OFF, 0x52800021)      # mov w0, #1
struct.pack_into("<I", d2, OFF + 4, 0xD65F03C0)  # ret
open(DST, "wb").write(d2)
print("wrote", DST, "with ...9140=>success stub")
