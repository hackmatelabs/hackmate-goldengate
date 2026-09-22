import struct, sys, glob, os

CACHE_DIR = "/Volumes/macOS Base System/System/Library/dyld"
TARGET_ADDR = 0x19DFB4000
TARGET_SIZE = 0x19DFFB2D0 - 0x19DFB4000

def parse_header(path):
    with open(path, "rb") as f:
        data = f.read(256)
    magic = data[:16]
    mappingOffset, mappingCount = struct.unpack_from("<II", data, 16)
    return magic, mappingOffset, mappingCount

def find_mapping(path, addr):
    with open(path, "rb") as f:
        hdr = f.read(256)
        mappingOffset, mappingCount = struct.unpack_from("<II", hdr, 16)
        f.seek(mappingOffset)
        for _ in range(mappingCount):
            entry = f.read(32)
            address, size, fileOffset, maxProt, initProt = struct.unpack("<QQQII", entry)
            if address <= addr < address + size:
                return address, size, fileOffset
    return None

def main():
    cands = sorted(glob.glob(os.path.join(CACHE_DIR, "dyld_shared_cache_arm64e*")))
    cands = [c for c in cands if not c.endswith((".map", ".atlas"))]
    print("files:", len(cands))
    for path in cands:
        try:
            m = find_mapping(path, TARGET_ADDR)
        except Exception as e:
            print(os.path.basename(path), "ERR", e)
            continue
        if m:
            address, size, fileOffset = m
            off = fileOffset + (TARGET_ADDR - address)
            print("FOUND in", os.path.basename(path),
                  "mapaddr=0x%x filesz=0x%x fileoff=0x%x read_off=0x%x" % (address, size, fileOffset, off))
            with open(path, "rb") as f:
                f.seek(off)
                blob = f.read(TARGET_SIZE)
            print("read", len(blob), "bytes")
            with open(os.path.expanduser("~/libbootpolicy_text.bin"), "wb") as f:
                f.write(blob)
            print("wrote ~/libbootpolicy_text.bin")
            return
    print("NOT FOUND")

main()
