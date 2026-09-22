from pathlib import Path
import struct, plistlib, copy

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
print('needle count in raw[:end]:', raw[:end].count(needle))
new_xml = raw[:end].replace(needle, fragment + needle, 1)
print('xml_size:', xml_size)
print('len(raw):', len(raw))
print('end offset:', end)
print('len(new_xml):', len(new_xml))
print('growth:', len(new_xml) - end)
print('room available (xml_size - end):', xml_size - end)
tail = raw[end:]
print('tail length:', len(tail))
nz = [i for i, b in enumerate(tail) if b != 0]
print('nonzero count in tail:', len(nz))
if nz:
    print('first few nonzero offsets (relative to end):', nz[:10])
    print('bytes at those offsets:', [hex(tail[i]) for i in nz[:10]])
    print('last nonzero offset:', nz[-1], 'byte:', hex(tail[nz[-1]]))
