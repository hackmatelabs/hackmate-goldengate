import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

for name, val in [("movz-x21-0xd507", 0xD29AA0F5), ("mrs-x0-tpidr", 0xD538D000),
                  ("nop", 0xD503201F), ("b-minus0x30", 0x17FFFFF4)]:
    n = 0
    i = 0
    while True:
        i = data.find(struct.pack("<I", val), i)
        if i < 0:
            break
        n += 1
        i += 1
    print("%s: %d hits" % (name, n))

# dump file bytes around the EXPECTED be68 fileoff under old delta, for eyeball
for base_off in (0xBB9BE64 - 0x7004000, 0xBB9BE64 - 0x7000000):
    print("bytes at 0x%x:" % base_off, data[base_off:base_off + 12].hex())
