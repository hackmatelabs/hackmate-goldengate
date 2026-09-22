from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# If gg_gdb11 boot had slide 0x20004000, live 0x2BC28100 <-> file 0x4C24100
off = 0x4C24100
code = data[off:off + 0x30]
for ins in md.disasm(code, 0xFFFFFE000BC24100):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
