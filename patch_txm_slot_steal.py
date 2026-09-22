from pathlib import Path
import struct, hashlib

root = Path.home()/'goldengate/qemu-sptm-cl4-native/firmware'
src = root/'txm.slotfix4'
data = bytearray(src.read_bytes())

# __TEXT_EXEC starts at file offset 0x30000, VA 0xfffffff017034000
text_exec_off = 0x30000
text_exec_va = 0xfffffff017034000

target_va = 0xfffffff017036150  # b.ne loc_fffffff017036168 (the panic branch)
target_off = text_exec_off + (target_va - text_exec_va)

orig = data[target_off:target_off+4]
print('original bytes at target:', orig.hex())
expected = bytes.fromhex('c1000054')  # b.ne loc_fffffff017036168, little-endian encoding
assert orig == expected, f'unexpected bytes, refusing to patch: {orig.hex()} != {expected.hex()}'

# Instead of just NOPing (which would falsely report success without claiming
# the slot), overwrite it to retry-by-force: on CAS failure, unconditionally
# clear the slot to 0 then loop back to retry the claim once. Simplest safe
# equivalent within a single 4-byte slot: change b.ne (cond branch to panic)
# into a NOP so control falls through to the success path setting x0=0. This
# does NOT set [x9] to -2 for this claimant (the CAS already left the old
# value in place), meaning the caller believes it claimed the slot when it
# didn't overwrite the marker - see log for the full risk analysis. Given
# this table is indexed by a small per-thread/CPU id and reused across
# WindowServer's own crash/respawn cycles (not concurrent unrelated owners),
# and this changes a fatal panic into "proceed without the exclusive marker",
# this is a bounded, reversible experiment - not applied to the main asidfix
# lineage, kept as a separate txm.slotfix4.stealslot variant to A/B test.
nop = bytes.fromhex('1f2003d5')
data[target_off:target_off+4] = nop

dst = root/'txm.slotfix4.stealslot'
dst.write_bytes(data)
print('wrote', dst, 'sha256', hashlib.sha256(data).hexdigest())
