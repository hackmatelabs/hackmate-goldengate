# Phase 9: the VIOLATION_DOUBLE_NEST wall is universal, not path-dependent

## The key experiment this session

After PHASE8 found that neither a broad nor a narrowly-scoped `csr_check`
bypass could get past `VIOLATION_DOUBLE_NEST` once `/private/var` creation
actually succeeded, this session tried a completely different, SIP-free way
to populate `/private/var`: **using the host Mac's own real, trusted APFS
tooling to add a genuine second "Data"-role APFS volume to the same
container**, exactly like a real Mac's disk layout (System volume + Data
volume + firmlinks), instead of any guest-side mkdir/chflags/SIP dance.

Concretely:
```
hdiutil attach -nomount -owners on <the system volume dmg>
diskutil apfs addVolume disk8 apfs "Data" -role D
# creates disk8s2, auto-mounts at /Volumes/Data, correctly role-tagged
cd /Volumes/Data && mkdir -p private/var/... (the same skeleton as
  goldengate-diag.sh, but built by the REAL host APFS driver -- correct
  checksums, correct name hashes, no guessing required)
hdiutil detach
```
This completely sidesteps the raw-b-tree-insert idea from earlier in the
session (which was correctly abandoned -- Apple's directory-name hash
algorithm for case-insensitive volumes is undocumented and a from-scratch
brute-force search against `crc32c`/`crc32` with all reasonable
init/refin/refout/xorout/encoding combinations did NOT reproduce the
real on-disk hash for a known name ("private-dir" -> `0xaca68c0c`), so
inserting a directory entry with a guessed hash would have been unsafe:
either silently unreachable by real path lookups, or a real risk if wrong
in a way that isn't just "unreachable"). Using the host's own APFS
implementation avoids needing that algorithm at all.

`diskutil apfs list` confirmed both volumes correctly role-tagged
afterward (`disk8s1 (System)`, `disk8s2 (Data)`), not sealed, not
FileVault. Booted against this now-two-volume image using the **plain,
unpatched** `bootkc.md0size.uidfix` -- no `csr_check` patch of any kind,
no `/private` `SF_NOUNLINK` dependency even needed.

## Result: identical panic, byte for byte

```
panic(cpu 0 caller 0xfffffe002c550010): [SPTM] VIOLATION_DOUBLE_NEST:
sptm_set_shared_region(sptm.c:3105) - expected_shared_region(0)
```

Same file, same line, same message, at effectively the same point in boot,
as both the broad and narrow `csr_check` bypass attempts.

**This is the important finding of this session.** Three completely
different methods of getting userspace further along --
(1) broad `csr_check` bypass, (2) narrow single-bit `csr_check` bypass,
(3) a real second Data volume built with zero guest-side permission
bypass at all -- all three hit the identical panic. This rules out
"which SIP mechanism to use" as the variable that matters. The trigger is
tied to *userspace reaching a certain point of real progress*
(most likely opendirectoryd, or another daemon respawning cleanly for the
first time now that it can see real state under `/private/var`), not to
which method got it there. This is consistent with a genuine
`qemu-sptm` <-> real SPTM-firmware architectural-state emulation gap
(most plausibly in shared-region/TTBR/ASID nesting tracking during a
process exec/respawn), not a permissions problem of any kind.

## Progress toward root-causing the actual crash site

Found the real xrefs to the `sptm_set_shared_region` / `expected_shared_region`
strings in `firmware/sptm.asidfix4` this time (my first attempt this
session used a naive Capstone-op-string-based ADRP+ADD matcher and found
nothing -- the bug was the ADD-immediate bitmask filter, not the strings'
location). The correct raw-bitfield decoder (`scripts/xref_fast.py`'s
approach, reimplemented inline since that script's hardcoded
`sys.path.insert` pointed at a nonexistent `/Users/maliosdark/...` path
left over from a different environment) finds real xrefs at
`0xfffffff0270fa798` (`expected_shared_region`) and four call sites around
`0xfffffff0270faa10`-`0xfffffff0270fab50` (`sptm_set_shared_region`).

However, disassembling around these xrefs shows this whole region
(`~0xfffffff0270fa708` onward) is a **static violation-message
registration table builder** -- a long sequential run of
`adrp+add (string) -> stp (into a descriptor struct) -> mov w0, #<code> ->
bl <generic registration fn>` blocks, one per violation type, run once at
SPTM init to populate a lookup table used later for printing. It is NOT
the runtime check that decides whether `expected_shared_region` is 0. The
actual runtime logic that flips this value lives in whatever function
actually implements the shared-region-nesting state machine and calls
`sptm_violate(<double_nest_code>)` -- a different, not-yet-located
function elsewhere in `__TEXT_EXEC`. Finding and understanding that
function (and, more importantly, WHY its expectation is violated only
under `qemu-sptm`'s TCG emulation and not on real Apple Silicon hardware)
is real, substantial ARM64-architecture-state reverse engineering -- a
different order of difficulty than any patch made so far in this whole
project (every prior successful patch was "skip a check" or "widen an
integer field," not "correctly emulate a piece of hardware/firmware
state machine").

## Current state

- Reverted the Data-volume test image's guest-visible effects are harmless
  (the Data volume + skeleton directories are real and now permanently
  part of the dmg -- this is fine/desired, matches the intended fix, it's
  just not sufficient by itself because of the unrelated SPTM wall found
  above).
- `/private`'s `SF_NOUNLINK` flag is still cleared from PHASE8 (harmless,
  real, verified, holds).
- Running baseline: plain `bootkc.md0size.uidfix` (no csr_check patch),
  same firmware set as always, against the now-two-volume image. Boots
  clean through early userspace; will eventually hit the same
  `VIOLATION_DOUBLE_NEST` once opendirectoryd (or whichever daemon)
  reaches the same trigger point, exactly like before -- this is expected
  and not a new regression, it's the same wall from a cleaner starting
  point.

## Next steps, in honest order of promise

1. **Find the actual runtime check function** (not the message-table
   builder) that calls `sptm_violate` for `DOUBLE_NEST`, by searching for
   `mov w0, #<code>; bl <same generic registration/violate fn used at init>`
   pairs OUTSIDE the init-table region, or by searching for the specific
   immediate code value used in this table entry (need to trace backward
   from the `mov w0, #0x4c` near the `expected_shared_region` xref to
   confirm DOUBLE_NEST's exact enum value, then grep for that same
   immediate elsewhere in a `bl`-adjacent context that ISN'T part of the
   table-builder run).
2. Once found, understand what CPU/MMU state it's actually checking
   (likely a per-CPU or per-address-space "currently nested shared region"
   tracking variable) and why QEMU's TCG ARM64 emulation of whatever
   instruction/register sequence sets or reads that state diverges from
   real hardware. This may ultimately be a `qemu-sptm` (the emulator
   itself, which IS open source at github.com/jprx/qemu-sptm) bug rather
   than something patchable in Apple's firmware at all -- worth checking
   qemu-sptm's own issue tracker / recent commits for known TTBR/ASID/
   shared-region emulation gaps before spending more time on firmware-side
   reverse engineering.
3. If neither pans out in reasonable time, this is the point to consider
   whether continuing to chase this exact wall is worth it vs. other
   directions (e.g. checking whether a newer `qemu-sptm` upstream commit
   already fixes this, since the local fork is pinned to a specific base).

   **Checked this session**: `git fetch origin` (jprx/qemu-sptm) shows
   exactly one commit we don't have,
   `2867d84 fix(xnu_patch): allow pacibsp or bti c to start a function`
   (touches `hw/arm/xnu_patch.c`, QEMU's own automatic-kernel-patching
   helper -- unrelated to shared-region/SPTM logic). No commit anywhere in
   upstream history mentions `shared_region`, `double_nest`, or `nest`.
   This confirms the wall is not a known/already-fixed upstream issue --
   whoever hits it next has to actually solve it, not just update.
