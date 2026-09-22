import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TVADDR = 0xFFFFFFF0270A4000

names = [b"SPTM_FUNCTIONID_SET_SHARED_REGION", b"SPTM_FUNCTIONID_NEST_REGION",
         b"SPTM_FUNCTIONID_UNNEST_REGION", b"sptm_configure_shared_region"]
S = {}
for n in names:
    i = data.find(n)
    if i >= 0:
        # VA: which segment? assume __TEXT (fileoff<0x18000 -> VA 0x27004000+off)
        va = 0xFFFFFFF027004000 + i
        S[va] = n.decode()
        print("%s at fileoff 0x%x va 0x%x" % (n.decode(), i, va))
    else:
        print("%s MISS" % n.decode())

def adrp_imm(w):
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 0x3)
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 8, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0x9F000000) != 0x90000000:
        continue
    va = TVADDR + (foff - TEXTOFF)
    tpage = (va & ~0xFFF) + adrp_imm(w)
    w2 = struct.unpack_from("<I", data, foff + 4)[0]
    t = None
    if (w2 & 0xFF000000) == 0x91000000:
        t = tpage + ((w2 >> 10) & 0xFFF)
    if t in S:
        print("XREF fileoff 0x%x va 0x%x -> %s" % (foff, va, S[t]))
