import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TVADDR = 0xFFFFFFF0270A4000

STR_VA = {
    0xFFFFFFF02701019B: "VIOLATION_DOUBLE_NEST",
    0xFFFFFFF027012B7C: "expected_shared_region",
}

def adrp_imm(w):
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 0x3)
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

def is_add_imm(w):
    return (w & 0xFF000000) == 0x91000000

def is_adr(w):
    return (w & 0x9F000000) == 0x10000000

def is_ldr_uimm64(w):
    return (w & 0xFFC00000) == 0xF9400000

exact = []
for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 8, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0x9F000000) != 0x90000000:
        continue
    va = TVADDR + (foff - TEXTOFF)
    tpage = (va & ~0xFFF) + adrp_imm(w)
    w2 = struct.unpack_from("<I", data, foff + 4)[0]
    t = None
    if is_add_imm(w2):
        imm = (w2 >> 10) & 0xFFF
        t = tpage + imm
    elif is_adr(w2):
        immlo = (w2 >> 29) & 0x3
        immhi = (w2 >> 5) & 0x7FFFF
        imm = (immhi << 2) | immlo
        if imm & 0x200000:
            imm -= 0x400000
        t = va + 4 + imm * 1
    elif is_ldr_uimm64(w2):
        imm = (w2 >> 10) & 0xFFF
        t = tpage + imm * 8
    if t in STR_VA:
        exact.append((foff, va, STR_VA[t], w2))

print("exact hits:", len(exact))
for (foff, va, nm, w2) in exact:
    print("fileoff 0x%x va 0x%x -> %s (next 0x%08x)" % (foff, va, nm, w2))
