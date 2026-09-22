import json, bisect
from pathlib import Path

jf = Path('/tmp/symmap2/bootkc.netboot10.bootfb-probe.symbols.json')
d = json.load(open(jf))
addr_name = {int(k): v for k, v in d.items() if isinstance(v, str)}
sorted_addrs = sorted(addr_name.keys())

targets = [0xfffffe000ac6c6b4, 0xfffffe000ac6c8c4, 0xfffffe000ac65e34,
           0xfffffe000ac6c624, 0xfffffe000ac6ca84]
for t in targets:
    i = bisect.bisect_right(sorted_addrs, t) - 1
    base = sorted_addrs[i]
    print(hex(t), '->', addr_name[base], '+0x%x' % (t - base))
