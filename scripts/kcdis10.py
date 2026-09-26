from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
# ...9140 = static 0xBC29140, file 0x4C25140. Map exits: 9340-9440, 94b4-9630, 9780-97e0
for (sfx, n) in ((0x300, 0x50), (0x4B4, 0x90), (0x640, 0x50)):
    off = 0x4C25140 + sfx
    print("===== file 0x%x (static 0x%x) =====" % (off, off + 0x7004000))
    code = data[off:off + n * 4]
    for ins in md.disasm(code, off + 0x7004000):
        print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
