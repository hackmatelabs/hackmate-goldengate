import plistlib

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
blob = data[0x5550000:0x5550000 + 0x3C4000]
# trim to plist (starts with <?xml, ends with </plist>)
start = blob.find(b"<?xml")
end = blob.find(b"</plist>") + len(b"</plist>")
pl = plistlib.loads(blob[start:end])
print("top keys:", list(pl.keys())[:10])

def find_kexts(obj, path=""):
    if isinstance(obj, dict):
        bid = obj.get("CFBundleIdentifier", "")
        if bid in ("com.apple.security.BootPolicy", "com.apple.driver.AppleSEPManager",
                   "com.apple.driver.RTBuddy", "com.apple.iokit.IOSlaveProcessor"):
            print("=====", bid, "at", path)
            for k in ("_PrelinkExecutableLoadAddr", "_PrelinkExecutableSize",
                      "_PrelinkExecutableSourceAddr", "_PrelinkBundlePath",
                      "CFBundleVersion", "OSBundleRequired"):
                if k in obj:
                    v = obj[k]
                    if isinstance(v, int):
                        print("  %s = 0x%x (%d)" % (k, v, v))
                    else:
                        print("  %s = %s" % (k, v))
        for (k, v) in obj.items():
            find_kexts(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for (i, v) in enumerate(obj):
            find_kexts(v, path + "[%d]" % i)

find_kexts(pl)
