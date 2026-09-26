import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

# scan backward from 0xF6734 for pacib* (function entries)
for foff in range(0xF6734, 0xF6400, -4):
    w = struct.unpack_from("<I", data, foff)[0]
    if w in (0xD503233F, 0xD503237F):
        # check next insn looks like prologue (sub sp / stp)
        w2 = struct.unpack_from("<I", data, foff + 4)[0]
        print("candidate entry fileoff 0x%x next 0x%08x" % (foff, w2))
