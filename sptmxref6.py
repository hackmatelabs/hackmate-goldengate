import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TBASE = 0xFFFFFFF0270A4000  # VA of TEXTOFF

def va_of(foff):
    return TBASE + (foff - TEXTOFF)

STRS = {
    0xFFFFFFF027004000 + 0xC19B: "VIOLATION_DOUBLE_NEST",
    0xFFFFFFF027004000 + 0x14459: "expected_shared_region",
}
for (va, nm) in STRS.items():
    print("%s VA 0x%x page 0x%x" % (nm, va, va & ~0xFFF))

def adrp_imm(w):
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 0x3)
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

exact = []
for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 8, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0x9F000000) != 0x90000000:
        continue
    va = va_of(foff)
    tpage = (va & ~0xFFF) + adrp_imm(w)
    w2 = struct.unpack_from("<I", data, foff + 4)[0]
    t = None
    if (w2 & 0xFF000000) == 0x91000000 and ((w2 >> 22) & 0x3) == 0:  # ADD imm, no shift
        t = tpage + ((w2 >> 10) & 0xFFF)
    if t in STRS:
        exact.append((foff, va, STRS[t]))
print("exact hits:", len(exact))
for (foff, va, nm) in exact:
    print("fileoff 0x%x va 0x%x -> %s" % (foff, va, nm))
