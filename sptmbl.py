import struct

F4 = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
d4 = open(F4, "rb").read()

# asidfix4's bl at 0xF6B68 -> target?
w = struct.unpack_from("<I", d4, 0xF6B68)[0]
print("insn at 0xF6B68: 0x%08x" % w)
imm = w & 0x03FFFFFF
if imm & 0x02000000:
    imm -= 0x04000000
tgt = 0xF6B68 + imm * 4
print("bl target fileoff 0x%x" % tgt)
# dump 64 bytes there + nearby strings
print("bytes:", d4[tgt:tgt + 32].hex())
import re
# nearest strings within 2KB after target
chunk = d4[tgt:tgt + 2048]
strs = [m.group(0).decode() for m in re.finditer(rb"[\x20-\x7e]{6,}", chunk)]
print("strings near target:")
for s in strs[:15]:
    print(" ", s[:100])
