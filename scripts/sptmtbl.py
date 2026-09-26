import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

off = 0x1AA80
chunk = data[off:off + 0xC0]
print("u32s at 0x%x:" % off)
for i in range(0, len(chunk), 4):
    v = struct.unpack_from("<I", chunk, i)[0]
    print("  +0x%x: 0x%08x (%d)" % (i, v, v))
