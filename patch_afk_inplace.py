import shutil, sys
if len(sys.argv) != 3:
    raise SystemExit("usage: patch_afk_inplace.py SRC DST")
src, dst = sys.argv[1:]
data = bytearray(open(src, "rb").read())
base, cap = 0x5550000, 0x3C4000
section = bytearray(data[base:base + cap])
anchor = section.find(b"<key>AFKResource</key>")
if anchor < 0:
    raise SystemExit("AFKResource personality missing")
key = section.find(b"<key>IOClass</key>", anchor, anchor + 1024)
old = b"<string>AFKResource</string>"
new = b"<string>IOService</string>"
pos = section.find(old, key, key + 256)
if pos < 0:
    raise SystemExit("AFKResource IOClass value missing")
section[pos:pos + len(old)] = new
section += b"\0" * (cap - len(section))
shutil.copyfile(src, dst)
out = bytearray(open(dst, "rb").read())
out[base:base + cap] = section
open(dst, "wb").write(out)
print("patched AFKResource IOClass in place", hex(base + pos))
