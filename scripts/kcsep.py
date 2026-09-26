import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

strs = [(m.start(), m.group(0).decode()) for m in re.finditer(rb"[\x20-\x7e]{5,}", data)]
print("total strings:", len(strs))

# SEP-manager log strings suggesting waits/endpoints/timeouts/failure
keys = ["AppleSEPManager", "waitForSEP", "SEPEndpoint", "sepfw", "SEPManager"]
for (off, s) in strs:
    ls = s.lower()
    if any(k.lower() in s for k in keys):
        if any(w in ls for w in ["wait", "timeout", "endpoint", "not ", "fail", "error", "load", "boot", "avail", "ready", "pend"]):
            if len(s) < 160:
                print("0x%x: %s" % (off, s))
