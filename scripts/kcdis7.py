from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
for off in (0x4C297D8 - 0x20, 0x4C283AC - 0x20):
    print("===== file 0x%x (static 0x%x) =====" % (off, off + 0x7004000))
    code = data[off:off + 0x40]
    for ins in md.disasm(code, off + 0x7004000):
        print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
