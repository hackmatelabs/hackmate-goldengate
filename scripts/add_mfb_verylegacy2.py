from pathlib import Path
import struct, plistlib, copy, hashlib

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
src = root/'bootkc.netboot10.bootfb-probe'
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
    'IOClass': 'IOMobileFramebufferVeryLegacy',
    'IOPersonalityPublisher': 'com.apple.iokit.IOGraphicsFamily',
    'IOProviderClass': 'IOBootFramebuffer',
    'IOProbeScore': 1000,
}
entry['IOKitPersonalities']['GoldenGateMFBVeryLegacy'] = personality
fragment = plistlib.dumps({'GoldenGateMFBVeryLegacy': personality}, fmt=plistlib.FMT_XML, sort_keys=False)
fragment = fragment[fragment.index(b'<dict>')+6:fragment.rindex(b'</dict>')]

# Same proven anchor as make_bootfb_probe_fixed.py: IODisplayWrangler's key
# is unique in the whole file and sits inside IOGraphicsFamily's own
# IOKitPersonalities dict.
needle = b'<key>IODisplayWrangler</key>'
assert raw[:end].count(needle) == 1
new_xml = raw[:end].replace(needle, fragment + needle, 1)

trailing = raw[end:end+1]
assert trailing == b'\n', f'unexpected byte after </plist>: {trailing!r}'
assert not any(raw[end+1:]), 'unexpected nonzero bytes beyond the trailing newline'
new_region = new_xml + trailing
assert len(new_region) < xml_size, f'patched xml too big: {len(new_region)} >= {xml_size}'
assert plistlib.loads(new_xml[begin:]) == after

image[xml_off:xml_off+xml_size] = new_region.ljust(xml_size, b'\0')
dst = root/'bootkc.netboot10.bootfb-probe.mfblegacy'
dst.write_bytes(image)
print('wrote', dst, 'sha256', hashlib.sha256(image).hexdigest())
