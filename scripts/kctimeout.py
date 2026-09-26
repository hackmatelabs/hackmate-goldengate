import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

strs = [(m.start(), m.group(0).decode()) for m in re.finditer(rb"[\x20-\x7e]{4,}", data)]
print("=== timeout knobs / multiplier names ===")
seen = set()
for (off, s) in strs:
    ls = s.lower()
    if "timeout" in ls and len(s) < 80:
        # print only knob-like or informative ones
        if re.fullmatch(r"[A-Za-z0-9_\-\. ]{4,80}", s):
            key = s.strip()
            if key not in seen:
                seen.add(key)
                print("0x%x: %s" % (off, s[:110]))
