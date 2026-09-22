import struct, sys, shutil

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.md0size.uidfix.netboot1"
data = open(F, "rb").read()
print("size 0x%x" % len(data))

LC_SEGMENT_64 = 0x19
LC_FILESET_ENTRY = 0x8000000C

def parse_macho(base, out_segs, out_entries):
    magic = struct.unpack_from("<I", data, base)[0]
    if magic != 0xFEEDFACF:
        return False
    ncmds = struct.unpack_from("<I", data, base + 16)[0]
    off = base + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == LC_SEGMENT_64:
            segname = data[off + 8:off + 24].split(b"\x00")[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            out_segs.append((segname, vmaddr, vmsize, fileoff, filesize, base))
        elif cmd == LC_FILESET_ENTRY:
            vmaddr, vmsize, entry_off = struct.unpack_from("<QQQ", data, off + 8)
            name_off = off + 32
            end = data.index(b"\x00", name_off)
            name = data[name_off:end].decode()
            out_entries.append((name, vmaddr, vmsize, entry_off))
        if cmdsize == 0:
            break
        off += cmdsize
    return True

segs = []
entries = []
assert parse_macho(0, segs, entries)
print("top-level segments:", [(s[0], hex(s[1])) for s in segs])
print("fileset entries:", len(entries))
for (name, va, vsz, eoff) in entries[:8]:
    print("  %s va=0x%x file-entry-off=0x%x" % (name, va, eoff))
if len(entries) > 8:
    print("  ... and %d more" % (len(entries) - 8))

# recurse into entries, collect executable segments
all_segs = list(segs)
for (name, va, vsz, eoff) in entries:
    esegs = []
    eentries = []
    if parse_macho(eoff, esegs, eentries):
        for s in esegs:
            all_segs.append((name + ":" + s[0], s[1], s[2], s[3], s[4], eoff))

def lookup(static_va):
    for (segname, vmaddr, vmsize, fileoff, filesize, base) in all_segs:
        if vmaddr <= static_va < vmaddr + vmsize:
            foff = static_va - vmaddr + fileoff
            # fileoff in entry-relative or absolute? LC segments inside entry use entry-absolute offsets?
            # Try absolute first; caller verifies by content.
            return segname, foff, base
    return None

for (segname, vmaddr, vmsize, fileoff, filesize, base) in segs:
    print("%-16s vmaddr=0x%x vmsize=0x%x fileoff=0x%x filesize=0x%x end=0x%x" % (
        segname, vmaddr, vmsize, fileoff, filesize, vmaddr + vmsize))
