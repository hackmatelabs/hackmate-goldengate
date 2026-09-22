import struct, sys, shutil

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot6"

# ...9140 entry (static 0x0BC29140, fileoff 0x4C25140):
#   pacibz ; sub sp,sp,#0x90 ; stp x26,x25,[sp,#0x40]
# becomes:
#   stp xzr,xzr,[x0,#0xe0]   ; clear slot (like ...9140:9410 does on success)
#   mov w0, #1               ; report success
#   ret
OFF = 0x4C25140

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
newcode = bytes.fromhex("1f7c0ea9" "20008052" "c0035fd6")
got = [(i.mnemonic, i.op_str) for i in md.disasm(newcode, 0)]
print("new insns:", got)
assert got == [("stp", "xzr, xzr, [x0, #0xe0]"), ("mov", "w0, #1"), ("ret", "")], "bad assembly"

data = bytearray(open(SRC, "rb").read())
u0 = struct.unpack_from("<I", data, OFF)[0]
u1 = struct.unpack_from("<I", data, OFF + 4)[0]
u2 = struct.unpack_from("<I", data, OFF + 8)[0]
print("current: 0x%08x 0x%08x 0x%08x" % (u0, u1, u2))
if u0 != 0xD503237F or (u1 & 0xFF000000) != 0xD1000000:
    print("ABORT: entry mismatch")
    sys.exit(1)

shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
d2[OFF:OFF + 12] = newcode
open(DST, "wb").write(d2)
print("wrote", DST)
