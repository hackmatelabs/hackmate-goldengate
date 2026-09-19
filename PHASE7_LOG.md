# Phase 7: Codex's continuation, the missing Data-volume wall, and a paused raw-APFS attempt

## Context: what Codex did after the Phase 6 handoff (2026-09-18 late night / 2026-09-19)

Picked up this session from `CODEX_HANDOFF.md` (written when Claude ran out of
usage right after getting real macOS userspace booting — WindowServer/
loginwindow/endpointsecurityd all spawning, with two untested TXM panic fixes,
`sptm.asidfix3`/`txm.slotfix2`, queued as the next thing to test).

Found on disk (no corresponding repo commit, so recording here from the
artifacts + logs left behind): Codex continued the exact same wall-by-wall
SPTM/TXM patching method through **two more iterations**:

- `firmware/sptm.asidfix4` — one more NOPped SPTM violation-report call beyond
  `asidfix3`'s three (exact new check not re-derived this session; diff
  against `asidfix3` if needed).
- `firmware/txm.slotfix3`, `firmware/txm.slotfix4` — two more NOPped TXM
  `cas`-based table-slot checks beyond `slotfix2`'s two (same CAS-vs-sentinel
  pattern as the `[code: 0x68]`/`[code: 0x69]` fixes from Phase 6).
- `firmware/com.apple.netbiosd.plist.original` — a backup Codex made before
  **repurposing** `/System/Library/LaunchDaemons/com.apple.netbiosd.plist`
  (a real but unused Apple LaunchDaemon) into a custom diagnostic job:
  `Label` changed to `com.jprx.goldengate-diag`, `ProgramArguments` changed to
  `/bin/bash /goldengate-diag.sh`, `RunAtLoad` true, stdout/stderr to
  `/dev/console`. This is a clean trick worth reusing: it gets arbitrary
  script execution at boot **without needing a new trust-cache entry**, since
  it reuses an already-trusted plist slot and an already-trusted binary
  (`/bin/bash`).
- `/goldengate-diag.sh` on the system volume (source copy also at
  `firmware/`-adjacent — check the volume directly, see below) — a diagnostic
  script that: dumps `date`/`id`/mounts/`df -h`/directory listings, does a
  write-probe to `/var/tmp/codex_probe`, lists WindowServer/loginwindow/
  opendirectoryd-related processes, and runs `launchctl print
  system/com.apple.opendirectoryd` and `system/com.apple.WindowServer`.

**Result of Codex's continued patching**: with `sptm.asidfix4` +
`txm.slotfix4`, the boot got dramatically further — confirmed this session by
re-running it: `loginwindow[76/77]` genuinely reaches `service state: running`
(not just spawned), real per-boot-session labels appear
(`com.apple.loginwindow.<GUID>`), and the boot survives past the **exact**
point that used to hard-panic (previously `TXM [Panic]: [code: 0x68]` then
`[code: 0x69]`). One of Codex's runs (`/tmp/cl4_txmfix4_visible_serial.prev.log`,
2743 lines) got as far as **guest time 00:07:20** with **zero kernel panics**
before hitting a *launchd-level* (not kernel-level) problem: `Process[104]
crashed: DumpPanic. Too many corpses being created.` — `com.apple.opendirectoryd`
crash-looping so persistently that launchd's own crash-report daemon
(`DumpPanic`) couldn't keep up and started crash-looping too. This is NOT a
kernel panic — the guest CPU keeps running, XNU stays up, it's userspace
noise — but it never resolves into WindowServer actually starting.

## This session (Claude, resumed via `codex resume`): root-caused *why* opendirectoryd crash-loops

### The real root cause: this is a single-volume boot with no Data volume, so `/private/var` and friends were **never created**

Mounted the (already merged, grown-to-27.07GB) system volume read-only and
found:

```
/private/            <- exists, but is COMPLETELY EMPTY (only . and ..)
/tmp -> private/tmp  <- symlink target doesn't exist
/var -> private/var  <- symlink target doesn't exist
/etc -> private/etc  <- symlink target doesn't exist
```

Checked `/usr/share/firmlinks` on the volume — it's real, and lists `/private`
(among `/Applications`, `/Library`, `/Users`, `/Volumes`, `/cores`, `/opt`,
`/pkg`, `/usr/local`, etc.) as a genuine **firmlink target that's supposed to
resolve onto a separate Data volume**. On a real Mac (and in every
`ios27-cl4-secure-world` iOS boot this whole project has done), the System
volume's `/private` is an intentionally-empty placeholder; the *real*
`/private/var`, `/private/tmp`, etc. live on a **separate Data volume**,
joined to the System volume via APFS volume-group + firmlink resolution at
boot. Our boot is a single monolithic volume (`rd=md0` pointed straight at
the System volume) — there is no Data volume, so nothing ever populates
`/private/var`, and every daemon that needs to write there (`opendirectoryd`
writing to `/private/var/db/dslocal`, in particular) either can't find the
path or can't create it, and dies.

**This exact wall was already hit and left "PARKED" by the `ios27-cl4-secure-world`
companion track** — see `docs/STATE_darwinvm_boot.md`'s own notes: *"A DATA
volume was synthesized and paired into a real APFS volume group... but the
DATA volume is still not mounted at /private/var. LEVER 2 (kernel_mount
md0s2) is PARKED (XNU-core mount symbols stripped in this release KC)."* So
this is a known-hard, not-yet-fully-solved problem even on the more mature
research track, not something specific to a mistake this session made.

### Attempt 1 (failed cleanly): have the guest itself create `/private/var`

Rewrote `/goldengate-diag.sh` (via Codex's `com.jprx.goldengate-diag`
LaunchDaemon slot) to run, before anything else:
```bash
/usr/bin/chflags nosunlnk /private
mkdir -p /private/var/db/dslocal/nodes/Default /private/var/tmp ... (full skeleton)
chmod 1777 /private/tmp /private/var/tmp /private/var/folders
...
exec >/private/tmp/goldengate-diag.log 2>&1   # (moved AFTER mkdir, so the log itself doesn't depend on the fix succeeding)
```
Copied onto the volume, booted. **Failed**: after the boot, `/private/` on
disk was still completely empty. The `chflags` call inside the guest — run as
the guest's own root — did not take effect.

### Root cause of Attempt 1's failure: `SF_NOUNLINK` ("sunlnk") + XNU rootless/SIP protection, verified from BOTH sides

Checked the `/private` directory's BSD flags directly (`ls -ldO`): it carries
the **`sunlnk`** flag (`SF_NOUNLINK`), and so does the volume's own root `/`.
Confirmed this is enforced as a genuine SIP/rootless protection, not a plain
permission issue, two ways:

1. **From the host**, mounting the (unrelated, not-currently-booted) volume
   with `hdiutil attach -owners off`: `mkdir /private/testdir` fails with
   **`EPERM` ("Operation not permitted")**, not `EACCES` ("Permission
   denied") — the specific error code that BSD flag / MAC-policy enforcement
   produces, as opposed to a normal discretionary-permission failure. This
   happens even though "owners off" makes the mount report every file as
   owned by the current host user (so DAC permission bits are not the
   blocker).
2. **From the guest**, the boot log explicitly printed `System Integrity
   Protection is engaged.` at every boot (`grep`-confirmed), and the guest's
   own root-run `chflags` inside the diag script silently had no effect
   (matches: real macOS's rootless/SIP `mac_vnode_check_setutimes`/flag-change
   policy hooks block this **even for root**, unless SIP is actually off).

### Attempt 2 (built, worked partially, then caused a WORSE regression): disable SIP via kernel patch, revert once it regressed

**2a. NVRAM injection (wrong mechanism for this platform, but instructive):**
Found `/chosen/nvram-proxy-data` in the device tree is a flat buffer of
NUL-terminated `key=value` ASCII strings (`nvram\0...common\0...
backlight-level=598\0auto-boot=true\0boot-args=\0...`), with **~4KB of free
zero-padded space** at the end (used bytes end at offset 4159 of 8192).
Appended `csr-active-config=%ff%ff%ff%ff\0` (the standard `nvram` CLI
percent-hex encoding for a raw 0xFFFFFFFF value — "disable everything").
**First attempt panicked immediately** even on the small known-good ramdisk:
```
panic(...): header adler 0x80245B41 != calculated_adler 0xA1F265D6 @IONVRAMCHRPHandler.cpp:440
```
— the NVRAM blob has a **CHRP-style header with an Adler-32 checksum**
covering value bytes `[20:8192]` (empirically confirmed: `zlib.adler32(new_data[20:8192])`
reproduces the "calculated_adler" the panic printed). Recomputed and patched
the checksum field (4 bytes at value-relative offset 16) → the corruption
panic went away, regression-checked clean on the small ramdisk. **But the
real boot still printed "System Integrity Protection is engaged." unchanged**,
and the diag script still didn't create `/private/var`. Conclusion: **this
platform (Apple Silicon / SPTM-based boot) does not read CSR config from this
NVRAM blob** — csr config is sourced some other way (likely LocalPolicy or a
different device-tree property entirely on Apple Silicon; the legacy
Intel-style NVRAM `csr-active-config` string doesn't even appear anywhere in
`bootkc` — confirmed via direct string search, zero hits).

**2b. Kernel patch to `csr_check()` directly — worked, but unlocked a new crash:**
Found the *real* kernel-internal `csr_check(csr_config_t mask)` function by
resolving the `_csr_check` symbol through `com.apple.kernel`'s own embedded
`LC_SYMTAB` (this bootkc is stripped at the *top level* but each
`LC_FILESET_ENTRY` kext — including `com.apple.kernel` itself — still carries
its own local symbol table; parsed `nlist_64` entries directly to resolve the
string-table offset for `_csr_check` to its real address). Found it at static
va **`0xfffffe000c17047c`** (fileoff `0x516c47c` in `bootkc.md0size.uidfix`):
a short, clean function matching real XNU source exactly —
```asm
bti c
adrp x8, ...; ldr w8, [x8, #0x2a8]     ; w8 = global csr_config bitmask
and w9, w8, #0x1fff
orr w10, w9, #8
mov w11, #0x11 ; tst w8, w11 ; csel w8, w9, w10, eq   ; compute effective_config
bics wzr, w0, w8                       ; (requested_mask & ~effective_config), set flags, discard
cset w0, ne                            ; return 1 if any requested bit is NOT allowed, else 0
ret
```
Patched the final `cset w0, ne` (`e0079f1a`) → `mov w0, #0` (`00008052`) —
i.e. `csr_check()` now unconditionally returns 0 ("allowed") for every check,
system-wide. **Regression-checked clean on the small ramdisk.** On the real
system volume: **`chflags`/`mkdir` still didn't create `/private/var`** (the
diag script apparently never got that far this run — see below), and instead
a **brand new, different, earlier panic appeared**:
```
panic(...): [SPTM] VIOLATION_DOUBLE_NEST: sptm_set_shared_region(sptm.c:3105) - expected_shared_region(0)
```
Found and patched this the same way (string `sptm_set_shared_region` →
xref → the `mov w0,#0x3f` / line-number `0xc21`(3105) call site at static va
`0xfffffff0270fab68` in `firmware/sptm.asidfix4` → NOPped → `sptm.asidfix5`,
regression-checked clean). **Retested on the real volume with BOTH the
`csr_check` bypass and `sptm.asidfix5` together — got an even worse, EARLIER
panic**:
```
panic(...): cpu_root_table_tsd: Type (INVALID_FRAME_TYPE) class of FTE (0xfffffdf0019d7510)
            does not match the type class of the type-specific-data trying to be retrieved:
            actual (117539793) != requested (1).
```
This one **looks like genuine internal-state corruption** (a "type" field
reading a large, non-enum-like garbage value: 117539793), not a clean
permission gate — the kind of check that verifies an *invariant SPTM itself
depends on*, not a policy decision. This is qualitatively different from the
earlier ASID/root-flags/CAS-slot checks (which were plausibly "our
emulation doesn't perfectly replicate a real-hardware handshake, but the
underlying operation is still fundamentally sound once you skip the
picky verifier"). Skipping `csr_check` system-wide appears to unlock a
*materially different, more fragile* code path — plausibly because
disabling SIP globally changes how much of the OS's normal
security/sandbox/entitlement machinery gets exercised (way more processes
doing way more privileged things than they would otherwise attempt), and
that exercises SPTM/TXM invariants nothing has stressed before.

**Decision: reverted the `csr_check`/`VIOLATION_DOUBLE_NEST` patches.** This
line of attack is paused, not abandoned — it may still be viable with a
**narrower** patch (e.g. only bypass the specific rootless/flag-change check
in the vnode `chflags`/`mkdir` path, not `csr_check()` globally, which affects
every SIP-gated decision system-wide) but that needs more careful scoping
than was done this session.

### Attempt 3 (in progress, paused): patch the raw APFS bytes directly from the host, bypassing the guest OS entirely

Rationale: this sidesteps the guest's SIP/rootless enforcement completely
(we're not going through any syscall or MAC policy hook — we're editing the
on-disk B-tree records that represent the filesystem, the same way the
kernel itself eventually would, just without asking permission first). No
new kernel-behavior risk (unlike Attempt 2, which changes what the *running
OS* considers valid, this only changes *stored data*).

**Made real progress on the read path, using the standard Apple File System
Reference structures** (this reconstructs several APFS structures from
scratch via a Python script, all against
`~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg`,
**read-only so far, nothing written yet**):

1. Container superblock (`nx_superblock_t`, block 0, magic `NXSB`) — parsed
   `nx_omap_oid` (container-level object map, physical block `107141`) and
   `nx_fs_oid[0]` (the volume's virtual object id, `1026`).
2. Container-level object map (`omap_phys_t` at block `107141`, verified via
   `o_type == 0x4000000b` = `OBJ_PHYSICAL | OBJECT_TYPE_OMAP`) → `om_tree_oid
   = 107142` (a **single-entry, root+leaf** B-tree node — this container
   only has one volume, so this map only needs one entry).
3. Resolved `oid=1026` in that 1-entry tree (found by direct byte-search for
   the 8-byte LE oid value at value-relative offset 504 within the node —
   **note**: with `nkeys=1` this works via direct search, but is **not** the
   general method — see the TOC lesson below) → `paddr=107135`.
4. Block `107135` is confirmed `APSB` (the real **volume** superblock,
   `apfs_superblock_t`). Parsed (using field offsets re-derived from the
   Apple File System Reference, since exact offsets weren't memorized
   precisely and needed empirical confirmation): `apfs_meta_crypto_state_t`
   is 20 bytes at offset 96 (not 16 — confirmed by getting a garbage
   `omap_oid` at the wrong offset first, then correcting), so
   `apfs_root_tree_type`/`apfs_extentref_tree_type`/`apfs_snap_meta_tree_type`
   sit at offsets 116/120/124, and **`apfs_omap_oid` at offset 128,
   `apfs_root_tree_oid` at offset 136** (both 8-byte). Got `apfs_omap_oid =
   106918`, verified via the same `o_type == 0x4000000b` check → confirmed
   correct. `apfs_root_tree_oid = 1028` (a **virtual** oid — this is the
   actual filesystem B-tree root, needs resolving through the volume's own
   omap, layer 3 of indirection: container-omap → volume-superblock →
   volume-omap → fs-tree).
5. **The critical, hard-won lesson of this whole exercise — B-tree node
   traversal for `nkeys > 1` REQUIRES reading the actual Table-Of-Contents
   (TOC) array, not computed fixed-stride offsets.** A `btree_node_phys_t`
   header (`btn_flags` u16, `btn_level` u16, `btn_nkeys` u32,
   `btn_table_space {off,len}` u16+u16 at offset 40, `btn_free_space
   {off,len}` at 44, ...) is followed at `56 + table_off` by an array of
   `nkeys` **`kvoff_t {u16 k; u16 v}`** TOC entries (4 bytes each, **always
   present even for `BTNODE_FIXED_KV_SIZE` nodes** — the fixed-size-ness only
   means keys/values have a *constant size*, it does **not** mean they're
   stored in sorted physical order or that the TOC can be skipped). The
   **key** for TOC entry `i` is at `(56 + table_len) + toc[i].k` (`table_len`
   is the *reserved* TOC region size, a fixed allocation, not
   `nkeys*4` — confirmed: for the container's 1-entry omap, `table_len=448`
   but only 4 bytes are actually used by the single TOC entry). The
   **value** for TOC entry `i` is at `(BS - trailer) - toc[i].v - val_size`
   (i.e. `v` is measured as *distance from the end of the value area to the
   end of that value's bytes*; `trailer = 40` only for a node with the
   `BTNODE_ROOT` flag set — that's where the `btree_info_t` footer lives —
   and `0` for non-root nodes). **Verified empirically**: reading TOC-index
   order (not raw physical order) for the volume-omap's 5-entry root gives
   properly ascending oids (`1028, 13782, 14006, 26799, 40492`); reading
   fixed-stride `i*16` gave an OUT-OF-ORDER, wrong sequence
   (`1028,14006,26799,40492,13782`) that looked *almost* right and could
   easily mislead future work — **don't repeat this mistake**, always use
   the TOC.
6. Using the corrected TOC-based method, resolved `omap_key.oid==1028`'s
   child pointer at the top of the volume omap to physical block `110674`
   (confirmed valid: `o_type == 0x40000003` = `OBJ_PHYSICAL |
   OBJECT_TYPE_BTREE_NODE`, the expected type for a non-root child). **This
   is where the session paused**: block `110674` turned out to be a
   `level=1` (still non-leaf) node whose own smallest key is `14006`, **not
   close to our target `1028`** — meaning either child selection was
   subtly wrong (an off-by-one in "which TOC index's child covers the
   target," possibly because the boundary-key semantics need `oid<=target`
   selection logic re-checked against the *last* index where this holds,
   not blindly index 0 just because it matched exactly), or there's a
   second, unexplored subtlety (e.g. multiple children for the same boundary
   oid at different xids, a genuinely valid state in APFS after
   snapshots/history, requiring xid-aware selection). **Not yet resolved.**

**Decision: paused Attempt 3 here rather than continue debugging live.**
This is real, working infrastructure (steps 1-5 are solid, reusable,
correctly-verified reads) but the final descent-to-target logic needs a
careful, unhurried re-derivation of the *"pick child i where key[i].oid is
the largest key.oid that is <= target, scanning ALL entries not just index 0"*
rule (this is the standard b+tree invariant — it was likely a coding
mistake this session took the exact-match shortcut too eagerly). Once oid
`1028` resolves to the fs-tree root's physical block, the remaining work is:
walk the (much larger, thousands-of-entries) filesystem B-tree from that
root to find `/private`'s own inode record (drec lookup by name from the
root directory, typically a well-known small oid), then either (a) directly
flip the `sunlnk` bit in its `j_inode_val_t.internal_flags`/`bsd_flags`
field in place (a **pure in-place edit, no tree restructuring, no space
allocation, no checksum concerns beyond the containing node's own Fletcher-64
— which DOES need recomputing after ANY byte change in a node, this project
has not yet located/verified that checksum algorithm+coverage for
b-tree/object-phys nodes specifically, only for the separate NVRAM CHRP
Adler-32 case above), or (b) go further and actually insert new `var`/`tmp`
directory-record + inode entries (a full b-tree insert — meaningfully more
work than a flip, needs space-manager allocation, TOC updates, and possibly
node splits if the target leaf is full).

## Current known-good, regression-verified artifact set (unaffected by the paused Attempt 2/3 work — this is the SAFE baseline)

Nothing below has the `csr_check`/`VIOLATION_DOUBLE_NEST` patches — those
were reverted. This is Codex's + this session's confirmed-stable state:

```
firmware/bootkc.md0size.uidfix   (md0 fix + uid-ownership-gate fix; NO csr_check patch)
firmware/dtree.dcp8.bigdram2     (DCP+ANS+dart-id node set, 40GB dram-size; NO nvram edit)
firmware/ramdisk_full.tc         (14,660-cdhash complete trust cache)
firmware/sptm.asidfix4           (Codex's 4th SPTM violation-report NOP set; NO double-nest patch)
firmware/txm.slotfix4            (Codex's 4th TXM CAS-slot-check NOP set)
~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg   (merged + grown to 27.07GB)
```
Full command (same as always, `-icount shift=auto` on):
```bash
cd ~/goldengate/qemu-sptm-cl4-native
DARWIN_FB=1 DARWIN_RTKIT=1 DARWIN_DART=1 DARWIN_AIC=1 DARWIN_RTKIT_ANS=1 \
  build/qemu-system-aarch64 -icount shift=auto \
  -M darwin -bootkc firmware/bootkc.md0size.uidfix -dtree firmware/dtree.dcp8.bigdram2 \
  -tc firmware/ramdisk_full.tc \
  -ramdisk ~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg \
  -sptm firmware/sptm.asidfix4 -txm firmware/txm.slotfix4 \
  -args "rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" \
  -serial mon:stdio -display none \
  -monitor unix:/tmp/<name>.sock,server,nowait -m 8G
```
**Confirmed behavior**: boots cleanly, zero kernel panics observed through
22+ real minutes / correspondingly deep guest time in this session's own
re-test. `opendirectoryd` crash-loops forever (SIGTRAP, throttled by
launchd's exponential backoff — not fatal, never escalates to a kernel
panic in THIS session's re-test, though Codex's own longest run did
eventually hit the separate, non-fatal `DumpPanic`-crash-loop-storm
described above around guest time 00:07:20). **`WindowServer` never spawns
a PID** in any run observed so far, with or without the SIP patches.

The `com.jprx.goldengate-diag` LaunchDaemon (repurposed `netbiosd.plist`) and
`/goldengate-diag.sh` are still in place on the volume (currently containing
this session's var-skeleton-creation version, which does not work due to
`sunlnk`/SIP as documented above) — safe to leave, reuse, or overwrite for
whatever the next diagnostic/fix attempt needs.

## Next steps, in honest order of promise

1. **Finish Attempt 3 (raw APFS edit)** — the most isolated, lowest-blast-radius
   path. Fix the child-selection bug in the b+tree descent (use the standard
   "largest key <= target, scanning the full TOC" rule, not an exact-match
   shortcut), reach the fs-tree root, find `/private`'s inode, and just flip
   its `sunlnk` bit in place (smallest possible edit — no space allocation,
   no tree restructuring). Then let the ALREADY-BUILT
   `/goldengate-diag.sh` skeleton-creation script (still on the volume, see
   Attempt 1) do the rest from inside the guest, since once `sunlnk` is gone
   the guest's own root `mkdir`/`chmod` should work fine (SIP's *rootless*
   protection is fundamentally anchored on that flag + a path-based
   exception list, not some deeper unbypassable mechanism — the flag is the
   actual gate).
2. **If (1) proves harder than expected**: reconsider a *narrower* kernel
   patch than the global `csr_check()` bypass — specifically the vnode-layer
   check that consults `SF_NOUNLINK`/rootless status during `chflags`/`mkdir`
   (likely in `bsd/vfs/vfs_syscalls.c`'s `chflags1`/`vn_mkdir`, calling a
   `rootless_check_*` helper) — bypassing *only* the flag-change/mkdir path
   rather than every `csr_check()` call system-wide might avoid unlocking the
   `VIOLATION_DOUBLE_NEST`/`cpu_root_table_tsd` cascade that the broad bypass
   triggered.
3. **The "proper" real-Mac-shaped fix, bigger scope**: build an actual second
   Data-role APFS volume in the same container (space already confirmed
   available) and get XNU to mount+firmlink it. This is what the
   `ios27-cl4-secure-world` track called "LEVER 1 / LEVER 2" and left
   unfinished (their LEVER 2, `kernel_mount md0s2`, was blocked by stripped
   XNU mount symbols in their kernelcache — worth checking whether THIS
   macOS kernelcache's symbols are less stripped, given this session
   successfully resolved `_csr_check` via `com.apple.kernel`'s embedded
   per-fileset `LC_SYMTAB`, which may also have real mount-path symbols).
4. Once `/private/var` is genuinely writable, re-verify `opendirectoryd`
   stops crash-looping, and specifically watch for `WindowServer` finally
   getting a PID — if it still doesn't spawn, the next investigation target
   is whatever `loginwindow` needs from `opendirectoryd` specifically before
   it will make the mach-service connection that triggers WindowServer's
   on-demand launch (`launchctl print system/com.apple.WindowServer` from
   inside the guest, via the diag script, would show this directly if the
   guest ever gets far enough to run it usefully).
5. Keep the previously-documented `AFKFirmwareService`/DCP display-pipeline
   wall (`PHASE5_LOG.md`) in mind as the LIKELY next wall after WindowServer
   itself starts — that was never conclusively fixed, only characterized as
   "possibly a genuine gap in this exact kernelcache seed build." Worth
   re-checking once we're past the `/private/var` wall, since a fuller
   userspace environment might reveal something the earlier
   restore-ramdisk-only investigation couldn't see.

## Practical/session notes

- No root/sudo access on this machine, still. Every fix must go through
  either a kernel/firmware patch or genuinely root-level guest-side
  execution (which itself is blocked here by SIP) or raw disk-image editing.
- Disk space stayed tight (2-6GB free swinging depending on what's mounted)
  throughout this session — clean up stray `hdiutil attach`es
  (`hdiutil info` / `diskutil list`) and old log files in `/tmp` if a future
  session needs headroom.
- `~/goldengate/.venv` (capstone + keystone) and `~/goldengate/md0patch/`
  scripts remain the toolchain for any further kernel/firmware string-anchor
  patching. No dedicated APFS library was found or installed (`pip install
  apfs`/`pyapfs` both 404); the Attempt 3 raw-parsing code was written from
  scratch this session directly against the Apple File System Reference
  structure layout, ad hoc in a Python one-liner per step (not yet saved as
  a standalone script — worth extracting into `~/goldengate/md0patch/apfs_raw.py`
  before the next session, so the working reads (container superblock →
  container omap → volume superblock → volume omap, TOC-based traversal)
  don't need to be re-derived from scratch).
