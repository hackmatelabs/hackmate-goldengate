#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/raahimsyed/goldengate/ios27-cl4-secure-world/scripts')
from dt_fixup import ADTNode, decode_node, encode_node

working_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.netboot10.bootfb-probe'
broken_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.dcp8.bigdram2.realdcp'
out_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.dcp8.bigdram2.realdcp.chosenfix'

working_root = ADTNode()
decode_node(open(working_path, 'rb').read(), working_root)

broken_root = ADTNode()
decode_node(open(broken_path, 'rb').read(), broken_root)

working_chosen = working_root['chosen']
broken_chosen = broken_root['chosen']

print('working chosen keys:', sorted(working_chosen.props.keys()))
print('broken chosen keys: ', sorted(broken_chosen.props.keys()))

diffs = []
for k in working_chosen.props:
    wv = working_chosen.props[k]
    bv = broken_chosen.props.get(k, '<MISSING>')
    if wv != bv:
        diffs.append(k)
print('differing keys:', diffs)

# Replace the broken tree's chosen props with the working tree's, wholesale.
broken_chosen.props = dict(working_chosen.props)

with open(out_path, 'wb') as f:
    f.write(encode_node(broken_root))
print('wrote', out_path)
