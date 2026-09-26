from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# candidate ...c3cf700 at file 0xA8F00 (from panic-slide math - VERIFY by content!)
off = 0xA8F00
code = data[off:off + 0x80]
for ins in md.disasm(code, 0xFFFFFE00070A8F00):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
