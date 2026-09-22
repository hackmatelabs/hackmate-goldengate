from pathlib import Path
import subprocess

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
sptm = root/'sptm.asidfix5'
ipsw = None
for cand in ['/usr/local/homebrew/bin/ipsw', '/usr/local/bin/ipsw']:
    if Path(cand).exists():
        ipsw = cand
        break
assert ipsw, 'ipsw not found'

# __TEXT_EXEC.__text is 0xfffffff0270a4000 .. 0xfffffff0270fed08 (from macho info)
start = 0xfffffff0270a4000
end = 0xfffffff0270fed08
count = (end - start) // 4

proc = subprocess.run([ipsw, 'macho', 'disass', str(sptm), '-a', hex(start), '-c', str(count)],
                       capture_output=True, text=True, timeout=180)
lines = proc.stdout.splitlines()
print('total disassembled lines:', len(lines))

# Find every "mov w0, #0x4c" and check nearby lines for a bl to the violate fn
hits = []
for i, line in enumerate(lines):
    if 'mov\tw0, #0x4c' in line or 'mov  w0, #0x4c' in line or ('mov' in line and '#0x4c' in line and 'w0,' in line):
        # look ahead up to 3 lines for a bl
        for j in range(i, min(i+4, len(lines))):
            if '\tbl\t' in lines[j] or ' bl ' in lines[j] or 'bl\t' in lines[j]:
                hits.append((line.strip(), lines[j].strip()))
                break

print('mov w0,#0x4c -> bl sites found:', len(hits))
for a, b in hits:
    print(' ', a, '  ==>  ', b)
