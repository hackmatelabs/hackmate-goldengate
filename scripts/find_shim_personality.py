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
else:
    raise RuntimeError('PRELINK_INFO missing')
raw = bytes(image[xml_off:xml_off+xml_size])
begin = raw.index(b'<plist')
end = raw.index(b'</plist>') + len(b'</plist>')
d = plistlib.loads(raw[begin:end])

for entry in d['_PrelinkInfoDictionary']:
    pers = entry.get('IOKitPersonalities', {})
    for name, p in pers.items():
        ioclass = p.get('IOClass', '')
        if 'MobileFramebuffer' in ioclass or 'MobileFramebuffer' in name or 'BootFramebuffer' in ioclass:
            print('===', name, '===')
            for k, v in p.items():
                print(' ', k, '=', v)
            print()
