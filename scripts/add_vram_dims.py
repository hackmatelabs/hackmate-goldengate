from pathlib import Path
import struct

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
src = root/'dtree.netboot10.bootfb-probe'
data = bytearray(src.read_bytes())
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
        found.append((node_off, cursor, np, props))
    for _ in range(nc):
        walk(full)

walk('')
assert len(found) == 1, f'expected exactly one /device-tree/vram node, found {len(found)}'
node_off, insert_at, np, props = found[0]

# reg[1] holds the fb byte size; from earlier boot logs fb is 640x1136 32bpp,
# stride = width*4. Read the actual width/height from the reg-adjacent info
# if available, else fall back to the known constants from this session's
# boot logs (640x1136).
width = 640
height = 1136
stride = width * 4
depth = 32

def make_u32_prop(name, value):
    return name.ljust(32, b'\0') + struct.pack('<I', 4) + struct.pack('<I', value)

new_props = [
    make_u32_prop(b'width', width),
    make_u32_prop(b'height', height),
    make_u32_prop(b'depth', depth),
    make_u32_prop(b'stride', stride),
    make_u32_prop(b'rotation', 0),
]
already = set(props.keys())
to_add = []
for blob, name in zip(new_props, [b'width', b'height', b'depth', b'stride', b'rotation']):
    if name.decode() not in already:
        to_add.append(blob)

if not to_add:
    print('all dimension properties already present, no change needed')
else:
    payload = b''.join(to_add)
    data[insert_at:insert_at] = payload
    struct.pack_into('<I', data, node_off, np + len(to_add))
    dst = root/'dtree.netboot10.bootfb-probe.vramdims'
    dst.write_bytes(data)
    print('wrote', dst, 'added', len(to_add), 'properties, delta bytes', len(payload))
