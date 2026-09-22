import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
# report-formatting cluster approx file [0xF6700, 0xF6A00] (from disasm: formatting + bl 0xFAA94)
LO, HI = 0xF6700, 0xF6C00

for foff in range(TEXTOFF, TEXTOFF + TEXTLEN - 4, 4):
    w = struct.unpack_from("<I", data, foff)[0]
    if (w & 0xFC000000) != 0x94000000:
        continue
    rel = w & 0x03FFFFFF
    if rel & 0x02000000:
        rel -= 0x04000000
    tgt = foff + rel * 4
    if LO <= tgt < HI:
        print("bl at fileoff 0x%x -> report cluster 0x%x" % (foff, tgt))
