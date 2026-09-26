from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
off = 0xD7EE8
code = data[off:off + 0x80]
for ins in md.disasm(code, 0xFFFFFFF0270A4000 + (off - 0xA0000)):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
