import plistlib

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
blob = data[0x5550000:0x5550000 + 0x3C4000]
start = blob.find(b"<?xml")
end = blob.find(b"</plist>") + len(b"</plist>")
pl = plistlib.loads(blob[start:end])

d = pl["_PrelinkInfoDictionary"][204]
print("keys:", list(d.keys()))
pers = d.get("IOKitPersonalities", {})
print("personalities:", list(pers.keys()))
import json
for (k, v) in pers.items():
    print("=====", k, "=====")
    print(json.dumps(v, indent=1, default=str)[:3000])
