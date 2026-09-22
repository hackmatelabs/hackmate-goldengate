import plistlib, shutil, sys
if len(sys.argv) != 3:
    raise SystemExit("usage: patch_afk_ioservice.py SRC DST")
src, dst = sys.argv[1:]
data = bytearray(open(src, "rb").read())
base, cap = 0x5550000, 0x3C4000
blob = bytes(data[base:base + cap])
start = blob.find(b"<?xml")
end = blob.find(b"</plist>", start) + len(b"</plist>")
pl = plistlib.loads(blob[start:end])
for e in pl.get("_PrelinkInfoDictionary", []):
    if e.get("CFBundleIdentifier") == "com.apple.driver.AppleFirmwareKit":
        p = e["IOKitPersonalities"]["AFKResource"]
        p["IOClass"] = "IOService"
        p.pop("IOUserClientClass", None)
        break
else:
    raise SystemExit("AppleFirmwareKit personality missing")
enc = plistlib.dumps(pl, fmt=plistlib.FMT_XML, sort_keys=False)
if start + len(enc) > base + cap:
    raise SystemExit("PRELINK_INFO overflow")
shutil.copyfile(src, dst)
out = bytearray(open(dst, "rb").read())
out[base + start:base + start + len(enc)] = enc
open(dst, "wb").write(out)
print("patched AFKResource -> IOService")
