import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TVADDR = 0xFFFFFFF0270A4000

# string VAs and their pages
STRS = {
    0xFFFFFFF02701019B: "VIOLATION_DOUBLE_NEST",
    0xFFFFFFF027012B7C: "expected_shared_region",
}
PAGES = {}
for (va, nm) in STRS.items():
    PAGES.setdefault(va & ~0xFFF, []).append((va, nm))

def adrp_imm(w):
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 0x3)
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

hits = 0
for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 8, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0x9F000000) != 0x90000000:
        continue
    va = TVADDR + (foff - TEXTOFF)
    tpage = (va & ~0xFFF) + adrp_imm(w)
    if tpage in PAGES:
        w2 = struct.unpack_from("<I", data, foff + 4)[0]
        print("adrp fileoff 0x%x (va 0x%x) -> page 0x%x %s | next 0x%08x" % (
            foff, va, tpage, PAGES[tpage], w2))
        hits += 1
print("total adrp-to-page hits:", hits)
