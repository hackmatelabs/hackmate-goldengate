import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F4 = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
F5 = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix5"
d4 = open(F4, "rb").read()
d5 = open(F5, "rb").read()
print("len4 0x%x len5 0x%x same_len=%s" % (len(d4), len(d5), len(d4) == len(d5)))

# diff 4 vs 5
ndiff = 0
for i in range(min(len(d4), len(d5))):
    if d4[i] != d5[i]:
        if ndiff < 8:
            print("diff at 0x%x: %02x -> %02x" % (i, d4[i], d5[i]))
        ndiff += 1
print("total differing bytes 4vs5:", ndiff)

# disassemble asidfix4 around 0xE43E1 (the asidfix4 NOP site)
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
off = 0xE43E1 - 0x30
code = d4[off:off + 0x60]
print("=== asidfix4 around 0xE43E1 ===")
for ins in md.disasm(code, 0xFFFFFFF027000000 + off):
    print("0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str))
