import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot9"

# Q1: 9c0's 928 ldr -> b 98c (skip inner storm, exit via normal 98c path)
# Q2: ...8048's 811c bl -> b 8134 (...8048 epilogue: pure no-op return)
Q1_OFF = 0x4C29928
Q2_OFF = 0x4C2411C

data = bytearray(open(SRC, "rb").read())
u1 = struct.unpack_from("<I", data, Q1_OFF)[0]
u2 = struct.unpack_from("<I", data, Q2_OFF)[0]
print("Q1 current: 0x%08x (expect 0xf9400a94)  Q2 current: 0x%08x (expect 0x94000409)" % (u1, u2))
if u1 != 0xF9400A94 or u2 != 0x94000409:
    print("ABORT: mismatch")
    sys.exit(1)

shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, Q1_OFF, 0x14000019)  # b +0x64 -> 98c
struct.pack_into("<I", d2, Q2_OFF, 0x14000006)  # b +0x18 -> 8134 epilogue
open(DST, "wb").write(d2)
print("wrote", DST)
