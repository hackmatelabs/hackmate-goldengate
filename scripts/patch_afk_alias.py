import shutil, sys

if len(sys.argv) != 3:
    raise SystemExit("usage: patch_afk_alias.py SRC DST")
src, dst = sys.argv[1:]
data = bytearray(open(src, "rb").read())
lo, hi = 0x4A0000, 0x4B0000
repls = {
    b"AFKSharedMemoryResource": b"AFKResource",
    b"AFKSharedMemoryUserClient": b"AFKResourceUserClient",
}
counts = {}
for old, new in repls.items():
    n = 0
    pos = lo
    while True:
        pos = data.find(old, pos, hi)
        if pos < 0:
            break
        if len(new) > len(old):
            raise SystemExit(f"replacement grows string: {old!r}")
        data[pos:pos + len(old)] = new + b"\0" * (len(old) - len(new))
        pos += len(old)
        n += 1
    counts[old.decode()] = n
shutil.copyfile(src, dst)
out = bytearray(open(dst, "rb").read())
out[lo:hi] = data[lo:hi]
open(dst, "wb").write(out)
print(counts)
