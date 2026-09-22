import struct

blob = open("/Users/raahimsyed/libbootpolicy_text.bin", "rb").read()
print("size", hex(len(blob)))
nz = sum(1 for b in blob if b != 0)
print("nonzero bytes", nz, "pct", round(100.0 * nz / len(blob), 1))

# count pacibsp
cnt = 0
for off in range(0, len(blob) - 4, 4):
    if blob[off:off + 4] == b"\x3f\x23\x03\xd5":
        cnt += 1
print("pacibsp count", cnt)

# capstone smoke test
try:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    code = b"\x08\x00\x80\xd2\xc0\x03\x5f\xd6"
    got = [(hex(i.address), i.mnemonic, i.op_str) for i in md.disasm(code, 0x1000)]
    print("capstone smoke", got)
except Exception as e:
    print("capstone FAIL", repr(e))

# file size of subcache 07 and anchor context
import os
p07 = "/Volumes/macOS Base System/System/Library/dyld/dyld_shared_cache_arm64e.07"
print("07 size", os.path.getsize(p07))
with open(p07, "rb") as f:
    f.seek(96419110 - 64)
    print(repr(f.read(128)))
