import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

for name in [b"sptm_set_shared_region", b"sptm_configure_shared_region", b"shared_region_configure"]:
    i = data.find(name)
    print("%s at fileoff 0x%x" % (name.decode(), i) if i >= 0 else "%s MISS" % name.decode())

# exact ADRP+ADD xref scan for sptm_set_shared_region string
TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TVADDR = 0xFFFFFFF0270A4000
s_off = data.find(b"sptm_set_shared_region")
# string could be in __TEXT (fileoff<0x18000 -> VA = 0x27004000+fileoff)
s_va = 0xFFFFFFF027004000 + s_off
print("string VA 0x%x" % s_va)

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
    if (w2 & 0xFF000000) == 0x91000000:  # ADD imm
        t = tpage + ((w2 >> 10) & 0xFFF)
    if t == s_va:
        print("XREF adrp fileoff 0x%x va 0x%x next 0x%08x" % (foff, va, w2))
