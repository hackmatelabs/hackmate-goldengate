import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

# VIOLATION_DOUBLE_NEST string at fileoff 0xC19B. Look for u32/u64 references
# to that file offset (as table offset or VA) anywhere in the file.
for (fmt, name) in [("<I", "u32"), ("<Q", "u64")]:
    pat = struct.pack(fmt, 0xC19B)
    i = 0
    n = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        # only interesting outside the string itself (string at 0xC19B contains no self-ref)
        if abs(i - 0xC19B) > 64:
            print("%s ref to 0xC19B at fileoff 0x%x (context %s)" % (
                name, i, data[max(0, i - 16):i + 24].hex()))
            n += 1
            if n > 12:
                break
        i += 1
    print(name, "total refs:", n)

# also VA form (in case of absolute table): VA = 0x27004000+0xC19B = 0x2701019B
for (fmt, name) in [("<Q", "u64VA")]:
    pat = struct.pack(fmt, 0xFFFFFFF02701019B)
    i = 0
    n = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        print("%s ref at fileoff 0x%x" % (name, i))
        n += 1
        i += 1
        if n > 12:
            break
    print(name, "total:", n)
