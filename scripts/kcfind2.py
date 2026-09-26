import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

def printable(b):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)

# all mrs x0,TPIDR_EL1 sites
sites = []
i = 0
pat = struct.pack("<I", 0xD538D020)
while True:
    i = data.find(pat, i)
    if i < 0:
        break
    sites.append(i)
    i += 1
print("mrs-x0-tpidr sites:", len(sites))

def dis1(w):
    # crude: identify movz/blr/mrs/nop/b/bl
    if w == 0xD503201F:
        return "nop"
    if (w & 0xFF000000) in (0xD6000000, 0xD7000000):
        return "br/auth 0x%08x" % w
    if (w & 0xFFE00000) == 0xD2800000:
        rd = w & 0x1F
        imm = (w >> 5) & 0xFFFF
        return "movz x%d,#0x%x" % (rd, imm)
    if (w & 0xFC000000) == 0x94000000:
        return "bl ?"
    if (w & 0xFF000000) == 0xD5000000:
        return "msr/mrs-ext 0x%08x" % w
    if (w & 0xFC000000) == 0xAA000000:
        return "mov? 0x%08x" % w
    return "0x%08x" % w

for s in sites:
    prev2 = struct.unpack_from("<I", data, s - 8)[0]
    prev1 = struct.unpack_from("<I", data, s - 4)[0]
    print("mrs at 0x%x | -8: %s | -4: %s" % (s, dis1(prev2), dis1(prev1)))
