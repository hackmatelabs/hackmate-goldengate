import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

TARGET = 0x0BC2821C  # ...821c static

# (file_start, file_end, static_of_file_start)
RANGES = [
    (0x1AD8000, 0x1AD8000 + 0x3A70000, 0x08ADC000),  # __TEXT_EXEC
    (0x8000, 0x8000 + 0xDE8000, 0x0700C000),        # __PRELINK_TEXT
]

callers = []
for (fs, fe, sv) in RANGES:
    off = fs
    # scan word-aligned
    while off + 4 <= fe and off + 4 <= len(data):
        w = struct.unpack_from("<I", data, off)[0]
        if (w & 0xFC000000) == 0x94000000:
            rel = w & 0x03FFFFFF
            if rel & 0x02000000:
                rel -= 0x04000000
            tgt = (off - fs + sv) + rel * 4
            if tgt == TARGET:
                callers.append(off)
        off += 4

print("callers of ...821c:", [hex(c) for c in callers])
