from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False

# 9c0's bl to ...821c is at file 0x4C29970 (0x4C2997C - 0xC); static base 0xBC2D970
off = 0x4C29970
print("bytes at 0x%x:" % off, data[off:off + 4].hex())
for ins in md.disasm(data[off:off + 4], 0xFFFFFE000BC2D970):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
