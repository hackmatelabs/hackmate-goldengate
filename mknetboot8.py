import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot8"

# P1: 9c0's 954 bl ...9140 -> mov w0,#1 (9c0 exits via 98c)
# P2: ...8048's 811c bl ...9140 -> mov w0,#1 (...8048 exits its 8100 loop)
# NOTE: file offsets are slide-independent (pattern-verified via capstone).
P1_OFF = 0x4C29954
P2_OFF = 0x4C2411C

data = bytearray(open(SRC, "rb").read())
u1 = struct.unpack_from("<I", data, P1_OFF)[0]
u2 = struct.unpack_from("<I", data, P2_OFF)[0]
print("P1 current: 0x%08x  P2 current: 0x%08x" % (u1, u2))
if (u1 & 0xFC000000) != 0x94000000 or (u2 & 0xFC000000) != 0x94000000:
    print("ABORT: not bl insns")
    sys.exit(1)

shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, P1_OFF, 0x52800021)
struct.pack_into("<I", d2, P2_OFF, 0x52800021)
open(DST, "wb").write(d2)
print("wrote", DST)
