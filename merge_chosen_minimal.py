#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/raahimsyed/goldengate/ios27-cl4-secure-world/scripts')
from dt_fixup import ADTNode, decode_node, encode_node

working_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.netboot10.bootfb-probe'
broken_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.dcp8.bigdram2.realdcp'
out_path = '/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/dtree.dcp8.bigdram2.realdcp.chosenfix2'

working_root = ADTNode()
decode_node(open(working_path, 'rb').read(), working_root)

broken_root = ADTNode()
decode_node(open(broken_path, 'rb').read(), broken_root)

working_chosen = working_root['chosen']
broken_chosen = broken_root['chosen']

# Only add the ONE key that was entirely missing (boot-uuid). Leave
# every other property from the DCP-enabled tree untouched, including
# the ones that differed in value (sepfw-load-at-boot,
# protected-data-access) - those may be intentionally different for
# this DCP config, and a full wholesale swap hung the VM.
if 'boot-uuid' not in broken_chosen.props:
    broken_chosen.props['boot-uuid'] = working_chosen.props['boot-uuid']
    print('added boot-uuid:', working_chosen.props['boot-uuid'])
else:
    print('boot-uuid already present, nothing to do')

with open(out_path, 'wb') as f:
    f.write(encode_node(broken_root))
print('wrote', out_path)
