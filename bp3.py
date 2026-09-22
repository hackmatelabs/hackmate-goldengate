import struct, glob

path = "/Volumes/macOS Base System/System/Library/dyld/dyld_shared_cache_arm64e.07"
with open(path, "rb") as f:
    hdr = f.read(512)
magic = hdr[:16]
print("magic", magic)
mappingOffset, mappingCount = struct.unpack_from("<II", hdr, 16)
print("mappingOffset 0x%x count %d" % (mappingOffset, mappingCount))
with open(path, "rb") as f:
    f.seek(mappingOffset)
    for i in range(mappingCount):
        e = f.read(32)
        addr, size, foff, mx, init = struct.unpack("<QQQII", e)
        print("map %d addr 0x%x-0x%x size 0x%x fileoff 0x%x prot %d/%d" % (i, addr, addr + size, size, foff, mx, init))
