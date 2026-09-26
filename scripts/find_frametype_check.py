from pathlib import Path

p = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/bootkc.netboot10.bootfb-probe'
data = p.read_bytes()
needles = [
    b'cpu_root_table_tsd',
    b'INVALID_FRAME_TYPE',
    b'does not match the type class of the type-specific-data',
]
for n in needles:
    idx = data.find(n)
    print(n, '-> file offset', hex(idx) if idx >= 0 else 'NOT FOUND')
