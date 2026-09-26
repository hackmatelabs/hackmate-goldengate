from pathlib import Path
import json, bisect

symfile = Path('/tmp/symmap_bootkc.json')
targets = {
    'pc': 0xfffffe002bd815f4,
    'lr': 0xfffffe002bbec218,
    'x7_ptr': 0xfffffe002c52d8d0,
    'x16': 0xfffffe002c4d8ec8,
}

import subprocess
root = Path.home()/'goldengate/qemu-sptm-cl4-native'
bootkc = root/'firmware/bootkc.netboot10.bootfb-probe'
symdir = Path('/tmp/symmap2')
symdir.mkdir(exist_ok=True)
ipsw = '/usr/local/homebrew/bin/ipsw'
r = subprocess.run([ipsw, 'kernel', 'symbolicate', '--json', '--output', str(symdir), str(bootkc)],
                    capture_output=True, text=True, timeout=180)
print(r.stdout[-2000:])
print(r.stderr[-2000:])

jf = symdir/'bootkc.netboot10.bootfb-probe.symbols.json'
if not jf.exists():
    cands = list(symdir.glob('*.symbols.json'))
    print('candidates:', cands)
    jf = cands[0] if cands else None
if jf and jf.exists():
    d = json.load(open(jf))
    addr_name = {int(k): v for k, v in d.items() if isinstance(v, str)}
    sorted_addrs = sorted(addr_name.keys())
    for name, va in targets.items():
        static = va - 0x20000000
        i = bisect.bisect_right(sorted_addrs, static) - 1
        if i >= 0:
            base = sorted_addrs[i]
            print(name, hex(va), 'static', hex(static), '->', addr_name[base], '+0x%x' % (static - base))
