import shutil, sys

SRC = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
DST = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot10"

data = bytearray(open(SRC, "rb").read())

# Locate BootPolicy kext dict in PRELINK_INFO (fileoff base 0x5550000)
base = 0x5550000
anchor = data.find(b"com.apple.security.BootPolicy", base)
print("anchor at 0x%x" % anchor)
if anchor < 0:
    print("ABORT: anchor missing")
    sys.exit(1)

# Find IOResourceMatch key + IOBSD value AFTER the anchor (within BootPolicy dict, few KB)
key = data.find(b"<key>IOResourceMatch</key>", anchor)
print("IOResourceMatch key at 0x%x" % key)
if key < 0 or key - anchor > 8192:
    print("ABORT: key not in range")
    sys.exit(1)
val_open = data.find(b"<string>", key)
val_close = data.find(b"</string>", val_open)
val = bytes(data[val_open + 8:val_close])
print("value: %r at 0x%x" % (val, val_open))
if val != b"IOBSD":
    print("ABORT: unexpected value")
    sys.exit(1)

# Same-length swap IOBSD -> ZZZZZ (5 bytes, XML stays valid, no size change)
shutil.copyfile(SRC, DST)
d2 = bytearray(open(DST, "rb").read())
d2[val_open + 8:val_close] = b"ZZZZZ"
open(DST, "wb").write(d2)
print("wrote", DST, "(BootPolicy IOResourceMatch IOBSD->ZZZZZ)")
