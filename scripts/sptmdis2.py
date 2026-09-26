from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
off = 0xF6980
code = data[off:off + 0x380]
for ins in md.disasm(code, 0xFFFFFFF027000000 + off):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
