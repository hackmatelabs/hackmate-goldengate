from pathlib import Path

p = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/txm.slotfix4'
data = p.read_bytes()
print('file size', len(data))
# search for "TXM [Panic]" or similar format strings
needles = [b'TXM [Panic]', b'[Panic]', b'TXM ']
for n in needles:
    idx = data.find(n)
    print(n, '-> offset', hex(idx) if idx >= 0 else 'NOT FOUND')
    all_idx = []
    start = 0
    while True:
        i = data.find(n, start)
        if i < 0:
            break
        all_idx.append(hex(i))
        start = i + 1
        if len(all_idx) > 20:
            break
    print('  all:', all_idx)
