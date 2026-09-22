from pathlib import Path
import subprocess

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
sptm = root/'sptm.asidfix5'
data = sptm.read_bytes()

# Find the "sptm_set_shared_region" / "DOUBLE_NEST" string to identify the
# violation code used in the init-table entry near it, then search for the
# same immediate value used in a bl-adjacent context elsewhere (the real
# runtime check, not the table-builder).
needle = b'DOUBLE_NEST'
idx = data.find(needle)
print('DOUBLE_NEST string at file offset', hex(idx) if idx >= 0 else 'NOT FOUND')

needle2 = b'sptm_set_shared_region'
idx2 = data.find(needle2)
print('sptm_set_shared_region string at file offset', hex(idx2) if idx2 >= 0 else 'NOT FOUND')

# Use ipsw or objdump-style disassembly around known xref addresses from
# PHASE9 (static VA 0xfffffff0270fa798 for expected_shared_region xref,
# table-builder blocks around 0xfffffff0270faa10-0xfffffff0270fab50).
# First confirm these addresses still resolve the same way in asidfix5
# (file may have shifted since asidfix4).
print('file size', len(data))
