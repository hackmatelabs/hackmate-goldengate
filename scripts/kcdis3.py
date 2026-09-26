from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
off = 0x4C28100
code = data[off:off + 0x30]
for ins in md.disasm(code, 0xFFFFFE000BC28100):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
