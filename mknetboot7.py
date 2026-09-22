import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot7"

# 9c0 at static 0x0BC2D928: ldr x20,[x20,#0x10]  ->  b 0xBC2D98C (exit, +0x64)
OFF = 0x4C2997C - 0x54
print("target fileoff 0x%x" % OFF)
assert OFF == 0x4C29928, "unexpected offset"

data = bytearray(open(SRC, "rb").read())
u0 = struct.unpack_from("<I", data, OFF)[0]
print("current: 0x%08x (expect ldr x20,[x20,#0x10]=0xf9400a94)" % u0)
if u0 != 0xF9400A94:
    print("ABORT: mismatch")
    sys.exit(1)

shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, OFF, 0x14000019)  # b +0x64
open(DST, "wb").write(d2)
print("wrote", DST)
