from pathlib import Path
import struct

p = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/dtree.netboot10.bootfb-probe'
data = bytearray(p.read_bytes())
cursor = 0

def walk(path):
    global cursor
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
        print('=== /device-tree/vram properties ===')
        for k, v in props.items():
            if len(v) <= 16:
                print(f'  {k}: {v.hex()} (len={len(v)})')
            else:
                print(f'  {k}: <{len(v)} bytes>')
    for _ in range(nc):
        walk(full)

walk('')
