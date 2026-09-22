import json
from pathlib import Path

jf = Path('/tmp/symmap2/bootkc.netboot10.bootfb-probe.symbols.json')
d = json.load(open(jf))
hits = []
for k, v in d.items():
    if isinstance(v, str) and 'exception' in v.lower() and '::' not in v and 'gMetaClass' not in v:
        hits.append((v, int(k)))
hits.sort()
for v, k in hits[:60]:
    print(hex(k), v)
