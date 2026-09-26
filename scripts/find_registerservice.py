import json
from pathlib import Path

jf = Path('/tmp/symmap2/bootkc.netboot10.bootfb-probe.symbols.json')
d = json.load(open(jf))
for k, v in d.items():
    if isinstance(v, str) and 'registerService' in v and 'IOService::' in v:
        print(hex(int(k)), v)
