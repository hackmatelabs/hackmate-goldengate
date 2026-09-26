import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot2"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot3"

# 9c0 function entry (static 0xFFFFFE000BC2D9C0) = pacibsp.
# From netboot2 patch: fileoff = static - 0x7000000.
OFF = 0xBC2D9C0 - 0x7004000
print("target fileoff 0x%x" % OFF)

data = bytearray(open(SRC, "rb").read())
cur = struct.unpack_from("<I", data, OFF)[0]
print("current insn: 0x%08x (expect PACIBZ 0xd503237f)" % cur)
if cur != 0xD503237F:
    print("ABORT: mismatch")
    sys.exit(1)
shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
struct.pack_into("<I", d2, OFF, 0xD65F03C0)  # ret
open(DST, "wb").write(d2)
print("wrote", DST, "with ret at entry of 9c0")
