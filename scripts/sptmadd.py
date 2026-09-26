import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TBASE = 0xFFFFFFF0270A4000

def va_of(foff):
    return TBASE + (foff - TEXTOFF)

def adrp_imm(w):
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 0x3)
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

# find all ADD-imm with imm12 == 0x19B preceded by ADRP; show adrp page + full target
for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 8, 4):
    w2 = struct.unpack_from("<I", data, foff)[0]
    if (w2 & 0xFFC00000) != 0x91000000:
        continue
    if ((w2 >> 10) & 0xFFF) != 0x19B or ((w2 >> 22) & 0x3) != 0:
        continue
    w = struct.unpack_from("<I", data, foff - 4)[0]
    if (w & 0x9F000000) != 0x90000000:
        print("ADD #0x19B at fileoff 0x%x WITHOUT adrp before (prev 0x%08x)" % (foff, w))
        continue
    va = va_of(foff - 4)
    tpage = (va & ~0xFFF) + adrp_imm(w)
    print("adrp+add#0x19B at fileoff 0x%x -> target VA 0x%x" % (foff - 4, tpage + 0x19B))
