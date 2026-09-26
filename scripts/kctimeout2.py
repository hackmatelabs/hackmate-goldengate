import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

strs = [(m.start(), m.group(0).decode()) for m in re.finditer(rb"[\x20-\x7e]{4,}", data)]
for (off, s) in strs:
    ls = s.lower()
    if ("multiplier" in ls or "sep_timeout" in ls or "timeout_mult" in ls) and len(s) < 100:
        print("0x%x: %s" % (off, s[:100]))
print("---done---")
# also: any lowercase boot-arg-ish containing sep?
print("=== sep knob-like ===")
seen = set()
for (off, s) in strs:
    if re.fullmatch(r"[a-z][a-z0-9_\-]{2,40}", s) and "sep" in s:
        if s not in seen:
            seen.add(s)
            print("0x%x: %s" % (off, s))
