import plistlib, shutil, sys
if len(sys.argv) != 3:
    raise SystemExit("usage: patch_afk_dedup.py SRC DST")
src, dst = sys.argv[1:]
data = open(src, "rb").read(); base, cap = 0x5550000, 0x3C4000
blob = data[base:base + cap]; start = blob.find(b"<?xml")
end = blob.find(b"</plist>", start) + len(b"</plist>")
pl = plistlib.loads(blob[start:end])
for e in pl.get("_PrelinkInfoDictionary", []):
    if e.get("CFBundleIdentifier") == "com.apple.driver.AppleFirmwareKit":
        pers = e["IOKitPersonalities"]
        p = pers["AFKResource"]
        p["IOClass"] = "AFKSharedMemoryResource"
        p["IOUserClientClass"] = "AFKSharedMemoryUserClient"
        pers.pop("AFKSharedMemoryResource", None)
        break
else:
    raise SystemExit("AppleFirmwareKit entry missing")
enc = plistlib.dumps(pl, fmt=plistlib.FMT_XML, sort_keys=False)
if start + len(enc) > base + cap:
    raise SystemExit("PRELINK_INFO overflow")
shutil.copyfile(src, dst); out = bytearray(open(dst, "rb").read())
out[base + start:base + start + len(enc)] = enc
open(dst, "wb").write(out)
print("patched AFKResource to shared-memory class and removed duplicate personality")
