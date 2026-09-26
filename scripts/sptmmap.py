import struct

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()
print("size 0x%x" % len(data))

i = data.find(b"VIOLATION_DOUBLE_NEST")
print("VIOLATION_DOUBLE_NEST at fileoff 0x%x" % i)
j = data.find(b"expected_shared_region")
print("expected_shared_region at fileoff 0x%x" % j)

# Mach-O header
magic = struct.unpack_from("<I", data, 0)[0]
print("magic 0x%08x" % magic)
if magic == 0xFEEDFACF:
    ncmds = struct.unpack_from("<I", data, 16)[0]
    print("ncmds", ncmds)
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:
            segname = data[off + 8:off + 24].split(b"\x00")[0]
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            print("%-16s vmaddr=0x%x vmsize=0x%x fileoff=0x%x filesize=0x%x" % (
                segname.decode(), vmaddr, vmsize, fileoff, filesize))
        if cmdsize == 0:
            break
        off += cmdsize
