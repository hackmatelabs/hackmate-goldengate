from pathlib import Path

candidates = [
    Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix5',
    Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/txm.slotfix4',
]
needles = [
    b'cpu_root_table_tsd',
    b'INVALID_FRAME_TYPE',
    b'does not match the type class',
]
for p in candidates:
    data = p.read_bytes()
    print('===', p.name, '===')
    for n in needles:
        idx = data.find(n)
        print(' ', n, '-> file offset', hex(idx) if idx >= 0 else 'NOT FOUND')
