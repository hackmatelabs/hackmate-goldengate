from pathlib import Path

p = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/bootkc.netboot10.bootfb-probe'
data = p.read_bytes()
needles = [
    b'Failed to send exception',
    b'EXC_CORPSE_NOTIFY',
    b'send exception',
]
for n in needles:
    idx = data.find(n)
    print(n, '->', hex(idx) if idx >= 0 else 'NOT FOUND')
    # find all occurrences
    all_idx = []
    start = 0
    while True:
        i = data.find(n, start)
        if i < 0:
            break
        all_idx.append(hex(i))
        start = i + 1
    print('  all offsets:', all_idx[:10])
