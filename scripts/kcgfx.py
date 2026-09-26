import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()

strs = set(m.group(0).decode() for m in re.finditer(rb"[\x20-\x7e]{5,}", data))
keys = ["Paravirtualized", "paravirtual", "AppleVMM", "VMMouse", "SimpleFramebuffer",
        "simple-framebuffer", "GenericFramebuffer", "IOFramebuffer", "IOMFB",
        "DisplayPipe", "DCPDP", "DCPAV"]
for k in keys:
    hits = sorted(s for s in strs if k.lower() in s.lower())
    print("=== %s (%d) ===" % (k, len(hits)))
    for s in hits[:12]:
        print("  ", s[:110])
