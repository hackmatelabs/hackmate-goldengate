import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

# find ALL expected_shared_region* strings with exact offsets
i = 0
while True:
    i = data.find(b"expected_shared_region", i)
    if i < 0:
        break
    # show full cstring (to NUL)
    end = data.index(b"\x00", i)
    print("fileoff 0x%x: %r" % (i, data[i:end][:90]))
    i = end + 1
