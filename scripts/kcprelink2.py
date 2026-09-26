import re

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
blob = data[0x5550000:0x5550000 + 0x3C4000]

# Find dicts containing our kexts: look back/forward around the bundle id
for target in [b"com.apple.security.BootPolicy", b"com.apple.driver.AppleSEPManager"]:
    i = blob.find(target)
    if i < 0:
        print(target, "NOT FOUND")
        continue
    # grab surrounding 3000 bytes and pull key numbers
    ctx = blob[max(0, i - 500):i + 2500]
    print("=====", target.decode(), "at blob+0x%x" % i, "=====")
    for m in re.finditer(rb"<key>(_[A-Za-z0-9]+)</key>\s*<integer>(\d+)</integer>", ctx):
        print(" ", m.group(1).decode(), "=", m.group(2).decode())
    for m in re.finditer(rb"<key>(CFBundleIdentifier|_PrelinkBundlePath|_PrelinkExecutableSourceAddr)</key>\s*<string>([^<]{0,120})</string>", ctx):
        print(" ", m.group(1).decode(), "=", m.group(2).decode()[:100])
