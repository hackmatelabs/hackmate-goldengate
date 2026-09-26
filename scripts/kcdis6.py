from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
for off in (0x4C25140, 0x4C21140):
    print("===== file 0x%x =====" % off)
    code = data[off:off + 0x60]
    for ins in md.disasm(code, off):
        print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
