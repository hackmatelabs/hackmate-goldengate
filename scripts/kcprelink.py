import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

# __PRELINK_INFO: fileoff 0x5550000, filesize 0x3C4000. Usually XML plist (maybe compressed?).
blob = data[0x5550000:0x5550000 + 0x3C4000]
print("first bytes:", blob[:80])
# find BootPolicy / SEPManager entries
for m in re.finditer(rb"com\.apple\.(security\.BootPolicy|driver\.AppleSEPManager)[^<]{0,200}", blob):
    print(hex(m.start()), m.group(0)[:200])
