from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
for off in (0xB859C - 0x30, 0xB9B78 - 0x30, 0xB9B9C - 0x30, 0xBB2EC - 0x30):
    print("===== around fileoff 0x%x =====" % (off + 0x30))
    code = data[off:off + 0x60]
    for ins in md.disasm(code, 0xFFFFFFF027000000 + off):
        print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
