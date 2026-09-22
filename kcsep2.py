import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

strs = [(m.start(), m.group(0).decode()) for m in re.finditer(rb"[\x20-\x7e]{6,}", data)]
hits = []
for (off, s) in strs:
    if "SEP" in s and len(s) < 200 and " " in s:
        # skip obvious non-log (paths, identifiers w/o spaces handled by " " check)
        ls = s.lower()
        if any(w in ls for w in ["wait", "timeout", "endpoint", "not ", "fail", "error", "load", "boot", "avail", "ready", "pend", "manag", "service", "provid", "match", "start", "stop", "init"]):
            hits.append((off, s))
print("hits:", len(hits))
for (off, s) in hits[:60]:
    print("0x%x: %s" % (off, s[:150]))
