#!/bin/zsh
P07="/Volumes/macOS Base System/System/Library/dyld/dyld_shared_cache_arm64e.07"
python3 -c "
import re
data = open('$P07','rb').read()
ANCHOR = 96419110
blob = data[ANCHOR-0x50000:ANCHOR+0x8000]
strs = set(m.group(0).decode() for m in re.finditer(rb'[\x20-\x7e]{4,}', blob))
for s in sorted(strs):
    ls = s.lower()
    if any(k in ls for k in ['bootarg', 'boot-arg', 'testingmode', 'fastsim', 'simulat', 'skip', 'disable', 'force', 'no-sep', 'nosep', 'testmode', 'internal']):
        if len(s) < 100:
            print(s)
"
