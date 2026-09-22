from pathlib import Path
import struct, plistlib, copy, hashlib

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
src = root/'bootkc.md0size.uidfix.netboot10'
image = bytearray(src.read_bytes())
off = 32
for _ in range(struct.unpack_from('<I', image, 16)[0]):
    cmd, size = struct.unpack_from('<II', image, off)
    if cmd == 0x19 and image[off+8:off+24].split(b'\0')[0] == b'__PRELINK_INFO':
        _, _, xml_off, xml_size = struct.unpack_from('<QQQQ', image, off+24)
        break
    off += size
else:
    raise RuntimeError('PRELINK_INFO missing')
raw = bytes(image[xml_off:xml_off+xml_size])
begin = raw.index(b'<plist')
end = raw.index(b'</plist>') + len(b'</plist>')
before = plistlib.loads(raw[begin:end])
after = copy.deepcopy(before)
entry = next(e for e in after['_PrelinkInfoDictionary'] if e.get('CFBundleIdentifier') == 'com.apple.iokit.IOGraphicsFamily')
personality = {
    'CFBundleIdentifier': 'com.apple.iokit.IOGraphicsFamily',
    'IOClass': 'IOBootFramebuffer',
    'IOPersonalityPublisher': 'com.apple.iokit.IOGraphicsFamily',
    'IOProviderClass': 'IOService',
    'IONameMatch': 'vram',
    'IOProbeScore': 0,
}
entry['IOKitPersonalities']['GoldenGateBootFramebuffer'] = personality
fragment = plistlib.dumps({'GoldenGateBootFramebuffer': personality}, fmt=plistlib.FMT_XML, sort_keys=False)
fragment = fragment[fragment.index(b'<dict>')+6:fragment.rindex(b'</dict>')]
needle = b'<key>IODisplayWrangler</key>'
assert raw[:end].count(needle) == 1
new_xml = raw[:end].replace(needle, fragment + needle, 1)

# The original xml_size-bounded region is: [begin:end) real content,
# then exactly one trailing '\n' at raw[end], then zero-padding to xml_size.
# Preserve that same trailing newline convention instead of requiring the
# whole tail to be zero.
trailing = raw[end:end+1]
assert trailing == b'\n', f'unexpected byte after </plist>: {trailing!r}'
assert not any(raw[end+1:]), 'unexpected nonzero bytes beyond the trailing newline'
new_region = new_xml + trailing
assert len(new_region) < xml_size
assert plistlib.loads(new_xml[begin:]) == after

image[xml_off:xml_off+xml_size] = new_region.ljust(xml_size, b'\0')
dst = root/'bootkc.netboot10.bootfb-probe'
dst.write_bytes(image)
print('BootKC', dst, 'length', len(image), 'sha256', hashlib.sha256(image).hexdigest())

# Device-tree patch: add AAPL,boot-display to the existing /vram node,
# preserving every other byte and declared property length exactly.
src_dt = root/'dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid'
data = bytearray(src_dt.read_bytes())
cursor = 0
found = []
def walk(path):
    global cursor
    node_off = cursor
    np, nc = struct.unpack_from('<II', data, cursor)
    cursor += 8
    props = {}
    for _ in range(np):
        name = bytes(data[cursor:cursor+32]).split(b'\0')[0].decode()
        length = struct.unpack_from('<I', data, cursor+32)[0] & 0x7fffffff
        cursor += 36
        props[name] = bytes(data[cursor:cursor+length])
        cursor += (length+3) & ~3
    full = path + '/' + props.get('name', b'?').rstrip(b'\0').decode()
    if full == '/device-tree/vram':
        found.append((node_off, cursor, np, 'AAPL,boot-display' in props))
    for _ in range(nc):
        walk(full)
walk('')
assert len(found) == 1, f'expected exactly one /device-tree/vram node, found {len(found)}'
node_off, insert_at, np, already_present = found[0]
if already_present:
    print('DT already has AAPL,boot-display on /vram - no change needed')
    dst_dt = src_dt
else:
    prop = b'AAPL,boot-display'.ljust(32, b'\0') + struct.pack('<I', 0)
    data[insert_at:insert_at] = prop
    struct.pack_into('<I', data, node_off, np+1)
    dst_dt = root/'dtree.netboot10.bootfb-probe'
    dst_dt.write_bytes(data)
    print('DT', dst_dt, 'delta bytes', len(data) - src_dt.stat().st_size)
