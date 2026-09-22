import sys

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

# Find BootPolicy-kext boot-arg knobs: look for boot-arg-like strings near BootPolicy code.
# Strategy: find all lowercase alpha strings containing 'bootpolicy' or known knob prefixes.
import re
strs = set(m.group(0).decode() for m in re.finditer(rb"[a-z][a-z0-9_\-]{2,40}", data))
knobs = sorted(s for s in strs if ("bootpolic" in s or "bpol" in s or "bp_" in s) and len(s) < 44)
print("=== bootpolicy-ish knobs ===")
for k in knobs[:60]:
    print(k)
print("=== debug-ish knobs mentioning policy/sep/rtb ===")
for k in sorted(strs):
    lk = k.lower()
    if ("debug" in lk or "verbose" in lk or "trace" in lk or "log" in lk) and ("polic" in lk or "sep" in lk or "rtb" in lk or "trm" in lk or "acm" in lk):
        print(k)
