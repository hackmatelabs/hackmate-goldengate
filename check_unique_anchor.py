from pathlib import Path
import struct, plistlib

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
raw = bytes(image[xml_off:xml_off+xml_size])
begin = raw.index(b'<plist')
end = raw.index(b'</plist>') + len(b'</plist>')
d = plistlib.loads(raw[begin:end])

for e in d['_PrelinkInfoDictionary']:
    bid = e.get('CFBundleIdentifier', '')
    if bid.startswith('com.apple.iokit.IOMobileGraphicsFamily'):
        pers = e.get('IOKitPersonalities', {})
        print('bundle:', bid, '- personality names:', list(pers.keys()))
        for name in pers.keys():
            keyxml = f'<key>{name}</key>'.encode()
            count = raw.count(keyxml)
            print(f'  "{name}" key occurs {count}x in raw XML')
