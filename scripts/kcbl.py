from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True
for (off, base) in ((0x4C29954, 0xFFFFFE000BC29954), (0x4C2811C, 0xFFFFFE000BC2811C)):
    code = data[off:off + 4]
    for ins in md.disasm(code, base):
        print("file 0x%x -> 0x%x %s %s" % (off, ins.address, ins.mnemonic, ins.op_str))
