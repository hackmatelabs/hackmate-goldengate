from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
off = 0x4C20100
code = data[off:off + 0x20]
for ins in md.disasm(code, 0xFFFFFE000BC20100):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
