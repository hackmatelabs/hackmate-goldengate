from pathlib import Path
import subprocess

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
sptm = root/'sptm.asidfix5'
ipsw = '/usr/local/homebrew/bin/ipsw'

start = 0xfffffff0270a4000
end = 0xfffffff0270fed08
count = (end - start) // 4

proc = subprocess.run([ipsw, 'macho', 'disass', str(sptm), '-a', hex(start), '-c', str(count)],
                       capture_output=True, text=True, timeout=180)
lines = proc.stdout.splitlines()
print('total lines:', len(lines))

targets = ['sptm_set_shared_region', 'sptm.c"', 'expected_shared_region"']
for t in targets:
    idxs = [i for i, l in enumerate(lines) if t in l]
    print(f'--- "{t}": {len(idxs)} hits ---')
    for i in idxs[:20]:
        lo = max(0, i-2)
        hi = min(len(lines), i+3)
        print('  context around line', i, ':')
        for k in range(lo, hi):
            print('   ', lines[k])
        print()
