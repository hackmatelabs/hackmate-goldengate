import plistlib
import shutil
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: patch_afk_prelink.py SRC DST")
src, dst = sys.argv[1:]
data = bytearray(open(src, "rb").read())
base = 0x5550000
capacity = 0x3C4000
blob = bytes(data[base:base + capacity])
start = blob.find(b"<?xml")
end = blob.find(b"</plist>", start)
if start < 0 or end < 0:
    raise SystemExit("PRELINK_INFO XML not found")
end += len(b"</plist>")
plist = plistlib.loads(blob[start:end])
targets = {
    "com.apple.driver.AppleFirmwareKit",
    "com.apple.driver.AppleDCP",
    "com.apple.iokit.IOMobileGraphicsFamily-DCP",
}
changed = []
for entry in plist.get("_PrelinkInfoDictionary", []):
    ident = entry.get("CFBundleIdentifier")
    if ident in targets:
        old = entry.get("OSBundleRequired")
        entry["OSBundleRequired"] = "Root"
        changed.append((ident, old))
encoded = plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False)
if start + len(encoded) > base + capacity:
    raise SystemExit("rewritten PRELINK_INFO does not fit")
shutil.copyfile(src, dst)
out = bytearray(open(dst, "rb").read())
out[base + start:base + start + len(encoded)] = encoded
out[base + start + len(encoded):base + end] = b"\0" * (end - start - len(encoded))
open(dst, "wb").write(out)
print("patched", changed, "xml_bytes", len(encoded), "old_bytes", end - start)
