# Phase 8: raw APFS b-tree fix, /private SF_NOUNLINK cleared, and proof the
# blocker is NOT the flag -- it's SIP/csr_check, and bypassing it (narrow or
# broad) both trip the same SPTM VIOLATION_DOUBLE_NEST cascade.

## Context

Continuing directly from PHASE7's paused raw-APFS b-tree descent bug. Full
read-path infrastructure (`~/goldengate/md0patch/apfs_raw.py`) was left with
a documented, unfixed non-leaf child-selection bug preventing resolution
past the volume-level omap root.

## Bugs found and fixed in `apfs_raw.py`

1. **`val_bytes` had a spurious extra `- val_size` term.** The correct
   formula for a kvoff_t/kvloc_t value's start offset is simply
   `val_area_end - v_off` (v_off already points to the START of the value,
   not its end). The old formula shifted every non-leaf child pointer to a
   CONSISTENT but WRONG slot -- dangerous because the wrong slot still
   looked like a plausible, validly-typed BTREE_NODE object. Caught by
   manually cross-checking a resolved child's own min-key against the
   parent key that pointed to it (the standard b+tree invariant: key[i]
   must equal the smallest key in child[i]'s subtree). Found the constant
   offset empirically (v_table[i] = v_needed[i] + 8 across all 5 test
   entries) before realizing the real bug was the redundant subtraction.

2. **Non-leaf child-selection now correctly scans the whole TOC** for the
   last key <= target (was previously an exact-match-only shortcut).

3. **Discovered the volume's `apfs_superblock.root_tree_type == 0x2`**,
   i.e. storage type bits are all zero == `OBJ_VIRTUAL`. This means the fs
   (catalog) tree is NOT a plain physical tree like most APFS content --
   every single non-leaf child "pointer" is itself a virtual OID that must
   be re-resolved through the volume omap on EVERY hop, not a direct
   physical block number. Treating them as direct block numbers gave block
   numbers that were superficially "in range" but pointed at unrelated
   garbage (confirmed via `obj_type()` mismatches). Fixed by threading
   `vol_om_tree_oid` through `descend_fs_tree`/`find_dir_rec`/`find_inode`
   and calling `resolve_omap` on every non-leaf hop.

With both fixed, full read-path now works end to end: container superblock
-> container omap -> volume superblock -> volume omap -> fs tree root ->
directory-record lookup by name (`find_dir_rec`, linear-scans a resolved
leaf since dir-rec keys are name-hashed) -> inode lookup by obj_id
(`find_inode`) -> file content read via extent records (`find_file_extents`
+ `read_file`, added this session, `APFS_TYPE_FILE_EXTENT` records keyed by
the inode's `private_id`, sorted by logical offset).

## The real /private inode, found and inspected

`/private`'s own inode (root dir oid=2 -> dir_rec "private" -> inode
1152921500312607384) has:
- `bsd_flags = 0x908000` = `SF_FIRMLINK(0x800000) | SF_NOUNLINK(0x100000) |
  UF_HIDDEN(0x8000)`. Confirms `/private` is a genuine firmlink stub, not a
  plain directory -- consistent with real macOS's Data-volume firmlink
  design, just missing its Data-volume target on this single-volume image.

## The raw-disk patch (applied, verified, held)

Computed the exact absolute file offset of the `bsd_flags` field inside the
leaf node containing this inode (leaf block 107556, `bsd_flags` at file
offset 440552394), backed up the 4096-byte block, cleared the
`SF_NOUNLINK` bit (`0x908000 -> 0x808000`), and recomputed the node's
Fletcher-64 `obj_phys_t` checksum (covers bytes 8..4095 of the block; the
algorithm was cross-verified by recomputing the checksum of the
*unmodified* block first and confirming it matched the on-disk value
exactly before touching anything). Re-read after writing: flag is 0x808000,
checksum matches. Re-checked again after a full ~4 minute boot ran against
this image: **flag is still 0x808000 -- the patch holds, nothing in the
kernel/journal reverted it.**

This is a real, durable, checksum-correct raw disk edit. Save the pattern
(`apfs_raw.py`'s `find_inode`/read chain + Fletcher-64 recompute) for any
future single-field inode edit.

## But the flag wasn't the blocker (important correction to PHASE7's framing)

**`SF_NOUNLINK` only blocks unlinking/renaming/deleting the flagged object
itself.** It does NOT block creating new entries inside a flagged
directory. This was a wrong assumption carried over from PHASE7's Attempt 1
writeup. Clearing it on `/private` was a real, verified fix, but not
sufficient by itself -- and indeed, after clearing it and rebooting,
`/goldengate-diag.sh`'s `mkdir -p /private/var/...` chain still did not
create anything (`find_dir_rec(private_oid, "var")` still returns None
after the boot completed).

The real blocker for creating entries under `/private` is SIP's
`csr_check()`-gated filesystem-protection check (same one PHASE7's Attempt
2 found), independent of any per-inode flag.

## New, more targeted attempt at the csr_check bypass -- also failed the same way

PHASE7's Attempt 2 patched `_csr_check` to unconditionally return "allowed"
for every mask, which worked for the mkdir but triggered a cascading,
apparently-unrelated `VIOLATION_DOUBLE_NEST` / `cpu_root_table_tsd` SPTM
panic and was reverted as too broad a hammer.

This session tried a narrower version: disassembled `_csr_check` (found via
`com.apple.kernel`'s embedded `LC_SYMTAB`, `_csr_check` @
`0xfffffe000c17047c`). The function computes an "effective allowed config"
word (`w8`) from the real `csr_active_config` global, masks it to 13 bits,
then returns `(mask & ~w8) != 0` (i.e. EPERM unless every requested bit is
already in the allowed set). Patched **only** the single instruction that
selects `w8` (`csel w8, w9, w10, eq` at file offset `0x516c498`) to instead
unconditionally OR in bit 1 (`CSR_ALLOW_UNRESTRICTED_FS = 0x2`):
`orr w8, w9, #2`. This preserves every other real SIP bit faithfully and
only ever grants the filesystem-protection bit -- as narrow a csr_check
patch as is reasonably possible without fully reimplementing per-call-site
gating.

- Regression-checked clean on the small known-good ramdisk (`bash-3.2#`
  reached, 0 panics) -- saved as
  `firmware/bootkc.md0size.uidfix.fsbit` methodology (file itself deleted
  after the real-target test failed, to avoid confusion; recreate by
  re-applying the single 4-byte patch above to `bootkc.md0size.uidfix` at
  file offset `0x516c498`, new bytes `28 01 1f 32`).
- **On the real target: hit the exact same `VIOLATION_DOUBLE_NEST` panic
  (`sptm_set_shared_region(sptm.c:3105) - expected_shared_region(0)`) as
  the broad patch, at effectively the same point in boot.**

This is the important new finding this session: **the SPTM violation is not
proportional to how much of csr_check you bypass.** Both the fully-open
patch and the single-bit-narrowed patch trigger the identical downstream
panic. That strongly suggests the trigger isn't "too much SIP disabled" but
rather **some specific operation that only happens once
mkdir/chflags-under-/private actually succeeds** -- most likely something
in opendirectoryd's (or another daemon's) respawn/exec path once it can
actually see a populated (or population-attempted) `/private/var` for the
first time, doing a shared-region setup this QEMU/SPTM emulation doesn't
model correctly for a "second" attach. This reads like a genuine emulation
gap in `qemu-sptm`'s shared-region/SPTM-nesting tracking, not something
fixable by being more careful about which SIP bit to open.

Reverted: deleted `bootkc.md0size.uidfix.fsbit`, killed the crashed/looping
QEMU process, and relaunched the previously-known-stable
`bootkc.md0size.uidfix` (no csr_check patch, `SF_NOUNLINK`-cleared image)
in the background as a zero-risk baseline observation, same as prior
sessions' "patient test" pattern.

## Current known-good, regression-verified artifact set (unchanged from PHASE7 except the disk image)

- `firmware/bootkc.md0size.uidfix` (kernel: md0 64-bit size fix + uid-gate
  neutered; does NOT include the csr_check patch, which is reverted)
- `firmware/dtree.dcp8.bigdram2`
- `firmware/ramdisk_full.tc`
- `firmware/sptm.asidfix4`
- `firmware/txm.slotfix4`
- `-ramdisk` = the real system volume dmg at
  `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg`,
  which now differs from every prior session's copy in exactly one place:
  the single 4-byte `bsd_flags` field of `/private`'s inode (SF_NOUNLINK
  cleared) plus its containing leaf node's recomputed Fletcher-64 checksum.
  Backup of the original 4096-byte block is at
  `/private/tmp/claude-501/-Users-raahimsyed/dafcda55-588a-4881-8612-b9900f014269/scratchpad/block_107556_backup.bin`
  (block 107556) if this ever needs reverting.

## Next steps, in honest order of promise

1. **Root-cause the `VIOLATION_DOUBLE_NEST`/`expected_shared_region(0)`
   panic directly**, now that we know it's decoupled from "how much SIP is
   open." Find `sptm_set_shared_region` in the SPTM firmware binary and
   trace what makes `expected_shared_region` go to 0 unexpectedly --this is
   now the *real* single blocker standing between us and a populated
   `/private/var`, not a filesystem-permissions problem anymore. Likely
   candidates: a process re-exec/respawn path (opendirectoryd itself
   respawns constantly already) doing a shared-region teardown/setup that
   this emulated SPTM can't track correctly when it happens while another
   thread/process is mid-shared-region-nest.
2. Alternatively, sidestep entirely: since we now have a fully-working raw
   APFS **read** path, consider implementing raw APFS **directory-entry
   creation** (new inode + new dir_rec + b-tree insert with node split
   handling + checksum + free-space accounting) to build the
   `/private/var` skeleton entirely from the host, with zero guest-side
   mkdir/chflags/SIP interaction at all. This avoids the SPTM violation
   category entirely since nothing new happens at guest runtime. This is
   a substantially bigger and riskier engineering task than anything done
   so far (real b-tree mutation, not just a single in-place field edit),
   but the read-side infrastructure built this session
   (`apfs_raw.py`) is the necessary foundation for it either way.
3. Build the proper second Data-role APFS volume with kernel-level mount +
   firmlink support (matches real macOS's actual architecture) -- the
   "LEVER 1/LEVER 2" approach the `ios27-cl4-secure-world` track left
   unfinished. Bigger lift than option 2 but the most "correct" fix and
   avoids all guesswork about SIP/SPTM interaction.

## Practical/session notes

- Fletcher-64 for APFS `obj_phys_t.o_cksum`: standard two-sum algorithm
  over 4-byte little-endian words of bytes `[8:]` of the block, modulus
  `0xFFFFFFFF`, `ck_low = mod - ((sum1+sum2) % mod)`, `ck_high = mod -
  ((sum1+ck_low) % mod)`, result = `(ck_high << 32) | ck_low`. Verified
  byte-for-byte against real on-disk checksums before trusting it for a
  write.
- `apfs_raw.py` extended this session with fs-tree (catalog) support:
  `toc_entry_var`/`fs_entry` (kvloc_t variable-length parsing),
  `descend_fs_tree`, `find_dir_rec`, `find_inode`, `find_file_extents`,
  `read_file`. All read-only, all now verified working against the real
  27GB image end to end (walked `/System/Library/LaunchDaemons/
  com.apple.netbiosd.plist` and `/goldengate-diag.sh` by full path and read
  their real contents byte-for-byte).
- Symbol resolution recipe reused successfully again: parse the
  kernelcache's top-level Mach-O `LC_FILESET_ENTRY` list, find
  `com.apple.kernel`'s own embedded `LC_SYMTAB`, linear-scan for the
  symbol name. Only `_csr_check` is present as an exported symbol; searched
  for and did NOT find `rootless_check_restricted_flag`,
  `vn_authorize_mkdir`, `sandbox_check`, `datavault`, or similar --
  whatever the more granular rootless check function is, it's either
  inlined or its symbol is stripped from this kernelcache's symtab.
