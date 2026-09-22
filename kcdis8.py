from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# ...9140:9630 path (static 0xBC29630, file 0x4C29630) + ...9140 exits (949c/960c/9630/978c...)
off = 0x4C29630
code = data[off:off + 0x120]
for ins in md.disasm(code, 0xFFFFFE000BC29630):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
