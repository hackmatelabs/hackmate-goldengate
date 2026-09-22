from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# file 0x4B97E40: static 0xBB97E40 (delta 0x7004000)
off = 0x4B97E40
code = data[off:off + 0x60]
for ins in md.disasm(code, 0xFFFFFE000BB97E40):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
