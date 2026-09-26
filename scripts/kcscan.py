import sys

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
print("size 0x%x" % len(data))

def printable(b):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)

for needle in [b"AppleSEPManager", b"com.apple.driver.RTBuddy", b"com.apple.driver.AppleDCP", b"AppleBootPolicy"]:
    n = 0
    i = 0
    while True:
        i = data.find(needle, i)
        if i < 0:
            break
        n += 1
        if n <= 3:
            print(needle.decode(), "at 0x%x" % i)
        i += 1
    print(needle.decode(), "total:", n)

# BootPolicy occurrences that are NOT bootpolicy_xxx function names: look for service/personality context
print("=== BootPolicy non-function contexts ===")
shown = 0
i = 0
while shown < 15:
    i = data.find(b"BootPolicy", i)
    if i < 0:
        break
    # skip bootpolicy_ / BootPolicy: / _bootpolicy (function-ish)
    before = data[max(0, i - 12):i]
    after = data[i + 10:i + 11]
    if b"bootpolicy" in before or before.endswith(b"_") or before.endswith(b":") or before.endswith(b"/"):
        i += 1
        continue
    ctx = printable(data[max(0, i - 60):i + 80])
    print("0x%x: %s" % (i, ctx))
    shown += 1
    i += 1
