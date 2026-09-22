import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

# VIOLATION_DOUBLE_NEST string VA as LE bytes (pointer-sized, 64-bit)
for va in (0xFFFFFFF02701019B,):
    pat = struct.pack("<Q", va)
    i = 0
    n = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        print("ptr to VIOLATION_DOUBLE_NEST at fileoff 0x%x (VA-equivalent region?)" % i)
        n += 1
        i += 1
        if n > 10:
            break
    print("total:", n)
