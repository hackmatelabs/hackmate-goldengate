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

# Find which fileset/kext actually defines IOMobileFramebufferVeryLegacy's
# CFBundleIdentifier - it's part of the com.apple.iokit.IOMobileGraphicsFamily
# family (confirmed present in this kernelcache from earlier session work).
entry = None
for e in after['_PrelinkInfoDictionary']:
    if e.get('CFBundleIdentifier', '').startswith('com.apple.iokit.IOMobileGraphicsFamily'):
        entry = e
        break
if entry is None:
    # fall back to the same bundle IOBootFramebuffer's personality used
    for e in after['_PrelinkInfoDictionary']:
        if e.get('CFBundleIdentifier') == 'com.apple.iokit.IOGraphicsFamily':
            entry = e
            break
assert entry is not None, 'could not find a suitable kext entry to attach the personality to'
print('attaching to bundle:', entry.get('CFBundleIdentifier'))

personality = {
    'CFBundleIdentifier': entry.get('CFBundleIdentifier'),
    'IOClass': 'IOMobileFramebufferVeryLegacy',
    'IOPersonalityPublisher': entry.get('CFBundleIdentifier'),
    'IOProviderClass': 'IOBootFramebuffer',
    'IOProbeScore': 1000,
}
entry.setdefault('IOKitPersonalities', {})['GoldenGateMFBVeryLegacy'] = personality
fragment = plistlib.dumps({'GoldenGateMFBVeryLegacy': personality}, fmt=plistlib.FMT_XML, sort_keys=False)
fragment = fragment[fragment.index(b'<dict>')+6:fragment.rindex(b'</dict>')]

# Insert right after the opening <dict> of this entry's own
# IOKitPersonalities block. The bundle id string appears in multiple
# places (dependency references too), so disambiguate using a personality
# name known to belong to THIS entry specifically.
existing_personality_names = [k for k in entry.get('IOKitPersonalities', {}).keys()]
assert existing_personality_names, 'entry has no existing personalities to anchor against'
anchor_name = existing_personality_names[0].encode()

bundle_id = entry.get('CFBundleIdentifier').encode()
search_from = begin
personalities_key = None
while True:
    candidate = raw.find(bundle_id, search_from, end)
    assert candidate != -1, 'could not find the real bundle definition'
    pk = raw.find(b'<key>IOKitPersonalities</key>', candidate, end)
    if pk != -1:
        next_bundle = raw.find(bundle_id, candidate + 1, end)
        limit = next_bundle if next_bundle != -1 else end
        if raw.find(anchor_name, pk, limit) != -1:
            personalities_key = pk
            break
    search_from = candidate + 1
assert personalities_key is not None
dict_open = raw.find(b'<dict>', personalities_key)
assert dict_open != -1
insert_at = dict_open + len(b'<dict>')

new_xml = raw[:end]
new_xml = new_xml[:insert_at] + fragment + new_xml[insert_at:]

trailing = raw[end:end+1]
assert trailing == b'\n', f'unexpected byte after </plist>: {trailing!r}'
assert not any(raw[end+1:]), 'unexpected nonzero bytes beyond the trailing newline'
new_region = new_xml + trailing
assert len(new_region) < xml_size, f'patched xml too big: {len(new_region)} >= {xml_size}'
parsed = plistlib.loads(new_xml[begin:])
if parsed != after:
    # find first differing entry for debugging
    a_list = parsed['_PrelinkInfoDictionary']
    b_list = after['_PrelinkInfoDictionary']
    print('lengths:', len(a_list), len(b_list))
    for i, (a, b) in enumerate(zip(a_list, b_list)):
        if a != b:
            print('diff at index', i, a.get('CFBundleIdentifier'))
            print('parsed personalities:', list(a.get('IOKitPersonalities', {}).keys()))
            print('expected personalities:', list(b.get('IOKitPersonalities', {}).keys()))
            break
    raise SystemExit(1)

image[xml_off:xml_off+xml_size] = new_region.ljust(xml_size, b'\0')
dst = root/'bootkc.netboot10.bootfb-probe.mfblegacy'
dst.write_bytes(image)
print('wrote', dst, 'sha256', hashlib.sha256(image).hexdigest())
