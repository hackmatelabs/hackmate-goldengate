from pathlib import Path

p = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware/bootkc.netboot10.bootfb-probe'
data = p.read_bytes()
needles = [
    b'task_generate_corpse',
    b'EXC_BAD_ACCESS',
    b'EXC_CRASH',
    b'exception_triage',
    b'corpse_for_task',
]
for n in needles:
    idx = data.find(n)
    print(n, '-> offset', hex(idx) if idx >= 0 else 'NOT FOUND')
