from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix3"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# asidfix3 has b.eq at file 0xE43E1 (asidfix4 NOP'd it). Disassemble around.
off = 0xE43E1 - 0x40
code = data[off:off + 0x80]
for ins in md.disasm(code, 0xFFFFFFF027000000 + off):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
