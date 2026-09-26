import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
TVADDR = 0xFFFFFFF0270A4000
TARGET_FILEOFF = 0xF65D0
TARGET_VA = TVADDR + (TARGET_FILEOFF - TEXTOFF)

for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 4, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0xFC000000) != 0x94000000:
        continue
    rel = w & 0x03FFFFFF
    if rel & 0x02000000:
        rel -= 0x04000000
    va = TVADDR + (foff - TEXTOFF)
    if va + rel * 4 == TARGET_VA:
        print("bl to report-fn at fileoff 0x%x va 0x%x" % (foff, va))
