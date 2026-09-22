import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

# BootPolicy kext: runtime 0x2A2A0110-0x2A2A26B3 (panic), slide 0x20000000
# -> static 0x0A2A0110, fileoff = static - 0x7004000 = 0x35A0110, len 0x25A4
OFF = 0x35A0110
blob = data[OFF:OFF + 0x2600]
strs = [m.group(0).decode() for m in re.finditer(rb"[\x20-\x7e]{4,}", blob)]
print("total strings:", len(strs))
print("=== with / (paths/props) ===")
for s in strs:
    if "/" in s and len(s) < 120:
        print(s)
print("=== knob-like (lowercase, _, -) ===")
for s in strs:
    if re.fullmatch(r"[a-z][a-z0-9_\-\.]{2,40}", s):
        print(s)
