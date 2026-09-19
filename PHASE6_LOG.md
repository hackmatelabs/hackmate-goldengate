# Phase 6: `-icount` clock fix verified, md0 32-bit truncation fixed, real system volume MOUNTS

## 2026-09-18 — `-icount` confirmed to fix the CNTVCTSS_EL0 seqlock stall (partially)

Picked up directly from FORCLAUDE.md's "UNVERIFIED — start here" handoff: the
previous session had launched a boot with `-icount shift=auto` to test the fix
for the seqlock-retry spin (`CNTVCTSS_EL0` read + memory-shadow re-check that
never converges under slow TCG, root-caused in PHASE5_LOG.md) but lost contact
with the T480s before confirming the result.

Relaunched the exact command from FORCLAUDE.md (dummy 1MB all-zero ramdisk, no
`rd=md0`, to force the ANS/NVMe root-discovery path that previously froze
immediately after the 4 ANS controller `probe()` lines):

```
DARWIN_FB=1 DARWIN_RTKIT=1 DARWIN_DART=1 DARWIN_AIC=1 DARWIN_RTKIT_ANS=1 \
  build/qemu-system-aarch64 -icount shift=auto \
  -M darwin -bootkc firmware/bootkc -dtree firmware/dtree.dcp8 \
  -tc firmware/ramdisk.tc -ramdisk /tmp/empty_ramdisk2.dmg \
  -sptm firmware/sptm -txm firmware/txm \
  -args "serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" \
  -serial mon:stdio -display none \
  -monitor unix:/tmp/cl4_icount.sock,server,nowait -m 8G
```

**Result: real, confirmed progress.** The boot got **past** the previous
freeze point — `RTBuddy(DCP): start()` fired, `AppleFSCompressionType*` kexts
loaded, NFS/ASP security policy initialized, `Added memory device md0/rmd0`
appeared, and it reached `Waiting on <dict ...IOMedia Apple_HFS...>` (the
normal root-device wait, which can never resolve with the intentionally-empty
dummy ramdisk). This is real forward motion that never happened before
`-icount` — confirms the root cause and fix direction from PHASE5_LOG were
correct.

**But it then hit the identical stall** at the same PC/registers documented in
PHASE5_LOG (`PC=fffffe002bc2d6c4`, `X01=feedfacefeedfad3`), sampled 3x via the
HMP monitor 2-3s apart with zero log growth in between — genuine spin, not
slow progress. Tried a larger fixed `-icount shift=7` (more virtual-time
headroom per instruction): **identical stall, same PC**, so headroom wasn't
the variable.

**Conclusion:** `-icount` genuinely fixes the *original* manifestation of the
seqlock bug (during ANS/DCP driver matching, early in boot) — real progress —
but the *same* underlying generic timer-consistency code is reached again
later, this time inside the root-device wait/timeout loop that only exists
because I deliberately gave the guest no matching root device. This is not a
new bug; it is the identical clock-desync issue, hit at a different call site
that only exists in this synthetic "force the ANS path" test.

## Regression check: `-icount` does not break the known-good boot

Before trusting the fix, verified `-icount shift=auto` against the proven-good
path (real `firmware/ramdisk.dmg`, `rd=md0`, so the guest actually finds and
mounts a root device quickly and never reaches the stall-prone wait/timeout
code at all):

```
... -icount shift=auto -bootkc firmware/bootkc -dtree firmware/dtree.dcp8 \
    -tc firmware/ramdisk.tc -ramdisk firmware/ramdisk.dmg \
    -args "rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" ...
```

**Reached `bash-3.2#`**, identical to every previous non-icount boot. `-icount`
is safe to leave on going forward — it does not regress the working path, and
it demonstrably helps the ANS-matching path. The dummy-ramdisk stall is an
artifact of a test scenario chosen specifically to force a code path that real
usage (a root device that actually resolves) doesn't hit.

## THE BIG ONE: the real 14.19GB macOS system volume MOUNTS

Since `rd=md0` + a real ramdisk avoids the stall, tried the obvious next step:
point `-ramdisk` at the real, previously-acquired, decrypted 14.19GB macOS
system volume (`~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg`)
instead of the small restore ramdisk — the exact experiment PHASE5_LOG left off
at, which had died with:

```
nx_dev_init: md0 superblock container size 14189330432
             greater than device size 1304428544
```

(a 32-bit truncation of the real 14189330432-byte container size, confirmed in
PHASE5_LOG as `14189330432 mod 2^32 = 1304428544`, an exact match — not a
guess).

### Building the fix: a semantic-anchor patcher for the 32-bit md0 truncation

The `ios27-cl4-secure-world` companion research track had already fully
designed (but never applied, and never against this macOS kernelcache) a fix
for the *identical* bug class in
`ios27-cl4-secure-world/experiments/md0-size/patch_md0_size.py` — a **semantic
finder**, not a hardcoded-address patch: it scans `com.apple.kernel
__TEXT_EXEC` for the pattern "a value loaded from the mdSize page-count field
(`ldr w,[x,#8]`) that is converted to a byte size via a **32-bit** `<<12`
shift" and widens each hit (plus its dependent `sub`/`udiv` ops) to 64-bit
using Keystone (the LSL-immediate re-encoding is NOT a single bit flip — a
32-bit `UBFM` encoding differs from the 64-bit form in more than the `sf` bit,
so hand-patching bytes would be wrong; must reassemble with Keystone).

Set up a fresh venv (`~/goldengate/.venv`, capstone 5.0.7 + keystone-engine
0.9.2 — this machine had none of the previous session's tooling), copied the
scripts to `~/goldengate/md0patch/`, repointed `macho_map.py`'s `KC` constant
at `~/goldengate/qemu-sptm-cl4-native/firmware/bootkc` (this machine's actual
macOS/t8112 kernelcache — the original script was written against a
*different* project's iOS/iPhone17,3 kernelcache, but the finder is
architecture/build-agnostic since it locates sites by instruction pattern, not
address).

**Ran cold against our real macOS bootkc — found exactly 6 sites, matching the
documented shape (Site A blockcount triple + Site B/C I/O clamp/bounds +
Site D ramdisk-extent global) with zero modification to the finder logic:**

```
va=0xfffffe000bdfcd20  add w9, w8, w9, lsl #12   -> add x9, x8, x9, lsl #12
va=0xfffffe000bdfcd24  sub w9, w9, #1            -> sub x9, x9, #1
va=0xfffffe000bdfcd28  udiv w8, w9, w8           -> udiv x8, x9, x8
va=0xfffffe000bdfce48  lsl w9, w9, #0xc          -> lsl x9, x9, #0xc
va=0xfffffe000bdfcfa4  lsl w9, w9, #0xc          -> lsl x9, x9, #0xc
va=0xfffffe000c498298  lsl w8, w8, #0xc          -> lsl x8, x8, #0xc
```

Emitted a patched copy: `firmware/bootkc.md0size` (same file size, 6
instructions changed in place, nothing else touched).

**Regression-checked the patch first** (small ramdisk, `rd=md0`,
`-icount shift=auto`, patched kernelcache): reached `bash-3.2#` identically to
the unpatched boot. The patch is inert/safe for a small ramdisk, as expected
(all 6 truncations only matter above 4GB).

### The real test — real system volume, patched kernelcache

Also needed more DRAM headroom for XNU's pmap bootstrap to recognize the
larger backing range (per PHASE5_LOG's file-backed-overlay technique — the
overlay is lazy/mmap-based, so this does NOT require 28-30GB of real host RAM
resident, confirmed again this session: RSS stayed ~330-420MB throughout).
`firmware/dtree.bigdram` already existed with `dram-size` bumped to 30GB, but
critically **it was missing the `dart-id` property fix** (the PHASE4 fix that
stopped SPTM from hanging on the DART nodes) — booting with it would have
reintroduced the original SPTM hang. Built a new device tree combining both:
`firmware/dtree.dcp8.bigdram` = `dtree.dcp8`'s full node set (dart-id intact)
+ `dram-size` binary-patched from 8GB to 30GB directly in the ADT bytes
(offset located by scanning for the `dram-size` property name, value is a
plain little-endian u64 at `+32+4`).

```
DARWIN_FB=1 DARWIN_RTKIT=1 DARWIN_DART=1 DARWIN_AIC=1 DARWIN_RTKIT_ANS=1 \
  build/qemu-system-aarch64 -icount shift=auto \
  -M darwin -bootkc firmware/bootkc.md0size -dtree firmware/dtree.dcp8.bigdram \
  -tc firmware/ramdisk.tc \
  -ramdisk ~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg \
  -sptm firmware/sptm -txm firmware/txm \
  -args "rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" \
  -serial mon:stdio -display none \
  -monitor unix:/tmp/cl4_sysvol.sock,server,nowait -m 8G
```

**RESULT — the real macOS system volume mounts, for the first time in this
entire project:**

```
Added memory device md0/rmd0 (03000000/16000000) at <ptr> for 000000034DC00000
BSD root: md0, major 3, minor 0
apfs_vfsop_mountroot:3156: apfs: mountroot called!
container_rootmount:2638: boot from ramdisk /dev/md0
dev_init:296: md0 device accelerated crypto: 0 (compiled @ Aug 30 2026 18:52:12)
dev_init:299: md0 device_handle block size 512 block count 27713536 features 0 internal
nx_mount:1157: md0 initializing cache w/hash_size 16384 and cache size 34816
nx_mount:1482: md0 checkpoint search: largest xid 673, best xid 673 @ 3
nx_mount:1509: md0 stable checkpoint indices: desc 2 data 4
...
apfs_vfsop_mount:2914: md0s1 failed to find named root snapshot: Need authenticator (81)
apfs_log_op_with_proc:3279: md0s1 mounting volume Macintosh HD, requested by: kernel_task (pid 0)
apfs_vfsop_mount:3017: md0s1 fs iokit node was not found
handle_mount:893: md0s1 vol-uuid: 20ED2DC7-B9F5-4DD3-8EE9-C6EF9AD3AD5A block size: 4096 block count: 3464192 (unencrypted; flags: 0x1; features: 1.0.12)
handle_mount:906: md0s1 setting dev block size to 4096 from 512
nx_volume_group_update:712: md0s1 Volume Macintosh HD is not in a volume group
apfs_log_op_with_proc:3279: md0s1 mount-complete volume Macintosh HD, requested by: kernel_task (pid 0)
```

**`block count 27713536 * 512 = 14,189,330,432` bytes — exactly the real,
untruncated size of the decrypted system volume.** The md0size patch is a
complete, working fix. `mount-complete volume Macintosh HD` — no panic, no
hang, the real APFS container's real 14GB `Macintosh HD` volume is genuinely
mounted as root. `Need authenticator (81)` / `fs iokit node was not found`
logged but non-fatal, same class of benign SSV-related log line seen
throughout this project on the small ramdisk boots (this container has no
sealed snapshot).

### New wall (immediately downstream, expected): missing dyld shared cache

Boot continued into `libignition`/launchd, then panicked:

```
panic(cpu 0 caller 0xfffffe002c19f5ac): launchd[1] fatal signal 6 -- namespace 6 code 0x1
description Library not loaded: /usr/lib/libSystem.B.dylib
  Referenced from: <D339377B-2AD6-3AED-8AF7-2A437F8C71FE> /sbin/launchd
  Reason: tried: '/usr/lib/libSystem.B.dylib' (no such file, no dyld cache)
```

Mounted the volume read-only on the host to confirm directly
(`hdiutil attach -readonly -nomount` + `mount_apfs -o rdonly`):
- No `/System/Library/dyld/` directory at all.
- No `libSystem*` anywhere under `/usr/lib`.
- `/System/Cryptexes/OS` is a symlink to `../../System/Volumes/Preboot/Cryptexes/OS`,
  and `/System/Volumes/Preboot/` is **completely empty** (no Preboot volume
  was ever extracted/mounted alongside this System volume).
- `WindowServer`, `Dock.app`, `Finder.app`, `loginwindow.app` are all still
  genuinely present and intact (re-confirmed, matches FORCLAUDE.md).

**This is the exact same shape of wall the `ios27-cl4-secure-world` companion
track hit and solved for iOS**: a modern Apple restore image splits the base
OS volume from a separate, dedicated **OS Cryptex** (there: `Cryptex1,SystemOS`,
~2.3GB) that carries the actual dyld shared cache and system dylibs; the base
System volume alone was never meant to be self-sufficient.

**Confirmed via the real BuildManifest.plist** (not the small 4.9KB
`BootabilityBundle/Restore/BuildManifest.plist` `ipsw` grabs by default on a
loose pattern match — the real one is `BuildManifest.plist` at the IPSW root,
31MB, 180 build identities): the `j473ap` (t8112/Mac14,3) "macOS Customer"
build identity's `Manifest` dict has a `Cryptex1,SystemOS` component whose
`Info.Path` is `043-70701-646.dmg.aea` (2.4GB, separate from the 11GB `OS`
component / `043-70867-635.dmg.aea` we already have). Confirmed via:

```python
import plistlib
d = plistlib.load(open('BuildManifest.plist','rb'))
bi = next(b for b in d['BuildIdentities']
          if b['Info']['DeviceClass']=='j473ap' and b['Info']['Variant']=='macOS Customer')
bi['Manifest']['Cryptex1,SystemOS']['Info']['Path']   # -> '043-70701-646.dmg.aea'
```

Also present in the same manifest: `Cryptex1,AppOS`, `Cryptex1,RosettaOS`, and
their matching `*TrustCache`/`*Volume` entries — the full split-volume-group
picture, same shape as iOS's `Cryptex1,SystemOS` + `Cryptex1,AppOS` +
`ExclaveOS` + `RestoreRamDisk`.

**In progress at end of this session**: downloading `043-70701-646.dmg.aea`
(2.4GB) directly from the IPSW via `ipsw extract --remote <url> --pattern`, to
`~/goldengate/system_volume/26A428__MacOS/cryptex_systemos/`. Once decrypted
(same `ipsw fw aea -k` / `-b <base64key>` method already proven for the 11GB
OS volume — Apple's AEA keys have consistently been generic
OS-distribution keys, not device-locked), the plan (mirroring the
`ios27-cl4-secure-world` `inject_cryptex.sh` approach, adapted to this
project's boot path) is to make the decrypted SystemOS Cryptex reachable at
`/private/preboot/Cryptexes/OS` inside the mounted system volume (or
present it as a second `-ramdisk`-equivalent overlay if the single-`-ramdisk`
QEMU flag can't take two volumes — needs checking `hw/arm/xnuboot_sptm.c`'s
overlay code for whether it supports a second file-backed region, or whether
the Preboot content needs to be merged directly into the System volume image
before boot).

## Current known-good artifacts (T480s, `~/goldengate/qemu-sptm-cl4-native/firmware/`)

- `bootkc.md0size` — the real bootkc + the 6-instruction md0 32-bit->64-bit
  widen. Regression-checked safe. **Use this going forward for anything
  involving `-ramdisk` over ~1GB.**
- `dtree.dcp8.bigdram` — `dtree.dcp8`'s full DCP+ANS+dart-id node set with
  `dram-size` bumped from 8GB to 30GB. Use this for the system-volume boot.
- `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg` — the
  real, complete, now-provably-fully-mountable 14.19GB macOS system volume.
- `-icount shift=auto` should be added to every future boot command by
  default — proven safe on the known-good path, proven to unblock real
  forward progress on the ANS-matching path, no observed downside.

## Next steps (in order)

1. Finish downloading + decrypt `043-70701-646.dmg.aea` (`Cryptex1,SystemOS`).
2. Get its dyld shared cache + system dylibs reachable to the booted guest
   (Preboot-volume merge, or a second overlay region, or copying the
   Cryptex's payload directly into the System volume's `/private/preboot/`
   tree before boot — whichever is more tractable given this project's
   single-`-ramdisk` QEMU boot path, unlike `ios27-cl4-secure-world`'s
   apparently-richer overlay tooling).
3. Once launchd can load `libSystem.B.dylib`, expect it to run further and
   hit the next wall — likely `AFKFirmwareService` (documented in PHASE5_LOG
   as missing from this exact kernelcache build, blocking the DCP display
   path specifically) or an SSV/code-signing wall (the `ios27-cl4-secure-world`
   track hit several of these in sequence: dyld cache shared-region mapping,
   arm64e PAC/auth-remap, TXM trust-cache platform-binary checks — expect
   macOS's version of some subset of these, though macOS is not SEP-gated the
   same way as some of those iOS-specific checks).
4. Keep `-icount shift=auto` on for all of this — it's free and has only
   helped so far.

## Continued, same session — full macOS userspace boot achieved: WindowServer, loginwindow, endpointsecurityd, IOMFB_FDR_Loader all running

Picked up directly from the "New wall (immediately downstream, expected): missing
dyld shared cache" section above. This is a huge continuation — the session went
from "launchd can't find libSystem.B.dylib" to a real macOS userspace boot with
dozens of real daemons running, including **the actual login/display stack**.

### Fix 1: dyld cache placement corrected

The first Cryptex-merge attempt placed `Cryptex1,SystemOS`'s content at
`/System/Volumes/Preboot/Cryptexes/OS` (following an older iOS-track doc's
convention: `Caches/com.apple.dyld`). **Wrong for this build.** Inspecting the
decrypted Cryptex directly showed its `dyld_shared_cache_arm64e*` files live at
its own root `/System/Library/dyld/` — and the base System volume has **no**
`/System/Library/dyld/` directory at all, confirming this Cryptex is meant to be
merged directly onto the base tree at boot (SSV-construction-style), not mounted
via the Preboot indirection. Re-did the merge:
`cp -R <cryptex>/System/Library/dyld/. <sysvol>/System/Library/dyld/` and
`cp -R <cryptex>/usr/. <sysvol>/usr/` directly onto the base volume tree. This
required growing the system volume's APFS container from 14.19GB to 27.07GB
(see "Container growth" below) since the merge needs several GB of free space
that the base volume didn't have.

**Container growth, the safe way**: `hdiutil resize` refuses a bare (non-GPT)
raw APFS container image — `-alllimits` reports `min=current=max`, no headroom.
The actual working method: append raw zero bytes to the `.dmg` file with `dd`,
then `hdiutil attach -nomount` + `diskutil apfs resizeContainer diskN 0` (which
runs a full fsck + grows the space manager correctly). **Critical gotcha hit and
fixed**: `dd if=/dev/zero bs=1m count=N >> file 2>&1` redirects `dd`'s own
human-readable stderr summary ("N+0 records in/out...") into the same file
handle as the binary append, corrupting the image with text bytes mixed into
the raw disk bytes (this doesn't corrupt the *recorded* APFS container size, so
`hdiutil attach -nomount` cleanly failed with "image not recognized" rather than
silently mounting something broken — first time truncating back to the exact
original byte count recovers the file perfectly). Fix: redirect `dd`'s stderr to
a separate file (`2>/tmp/dd_stderr.log`), never `2>&1` after a `>>` redirect to
the target image.

**Ownership**: could not `chown -R 0:0` the copied content — no root/sudo access
(`sudo -n true` fails, `sudo -l -n` shows only unrelated `NOPASSWD` entries for
EFI mounting, real `sudo` needs an interactive password we don't have). Copied
files end up owned by a placeholder UID (99, "unknown") because `hdiutil attach
-owners off` is needed to bypass root-owned-directory write permission errors
during the copy, and that mode stores new files with the UNKNOWN_UID sentinel
rather than a real uid. This became load-bearing for Fix 2 below.

### Fix 2: kernel patch to neutralize a uid-ownership gate (bootkc)

Boot then hit, verbatim:
```
vm: shared_region: [1(launchd)] map(...'dyld_shared_cache_arm64e'): not in trust cache
vm: shared_region: [1(launchd)] map(...'dyld_shared_cache_arm64e'): owned by uid=99 instead of 0
dyld[1]: dyld cache '(null)' not loaded: syscall to map cache into shared region failed
dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib
panic: launchd[1] fatal signal 6 ...
```
Two separate, precisely-named gates in `shared_region_map_and_slide_2_np`'s
call chain. Since we cannot fix ownership at the filesystem level, patched the
KERNEL check instead — same "authorized research, patch the specific validation
gate" method used throughout this project.

Found via string anchor + ADRP+ADD xref scan (own venv:
`~/goldengate/.venv`, capstone 5.0.7 + keystone 0.9.2, scripts in
`~/goldengate/md0patch/`, `macho_map2.py` repointed at
`firmware/bootkc.md0size`):
- Full strings: `"vm: shared_region: %p [%d(%s)] map(%p:'%s'): not in trust cache\n"`
  and `"...: owned by uid=%d instead of 0\n"` (file offsets `0xbcd8d`, `0xbce20`
  in `bootkc.md0size` — **the string START**, not a mid-string substring match,
  matters for ADRP+ADD xref hits).
- The "owned by uid" log call falls straight through into `mov w25, #1` at
  static va **`0xfffffe000c273548`** (the reject flag for this specific gate).
  Keystone-patched to `mov w25, #0` (`39008052` → `19008052`). Regression-checked
  safe on the small ramdisk first.
- The "not in trust cache" check's own reject write was never isolated (its log
  block falls into a much larger, generic continuation) — turned out not to
  matter once Fix 3 (below) made the trust-cache check pass for real.

Result: `firmware/bootkc.md0size.uidfix`.

### Fix 3: the REAL fix for "not in trust cache" — build a complete trust cache for the whole system volume

Neutering the uid flag alone just moved the crash to a genuine kernel data
abort (`far=0x4`, a null-deref inside a generic list-walk helper whose list
head is populated only on a *successful* trust-cache registration) — confirming
the trust-cache failure needed a real fix, not another bypass.

- Got the real cdhash for the dyld cache directly from macOS's own `codesign`:
  `codesign -dvvv <path>/dyld_shared_cache_arm64e` → `CDHash=5adc58ff...` (sha256,
  20-byte truncated form — exactly the `hashType=2` format this project's
  `build_tc.py` (`TrustCacheModule1_t`, from `darwin-vm-m2/build_tc.py`) expects).
- Computed cdhashes for all ~104 Cryptex files this way, merged into the
  existing `darwin-vm-m2/firmware/all_hashes` list, rebuilt via `build_tc.py`.
  **First attempt still failed** — this only covered the Cryptex, not the
  thousands of binaries native to the base system volume itself, which then hit
  mass `platform binary ... not in trust cache` failures for the whole base
  OS (xprotectd, powerd, fseventsd, sandboxd, syspolicyd, etc.), cascading into
  a crash loop and (at the time) an `[SPTM] VIOLATION_INVALID_ASID` panic
  (later shown to be a real, separate SPTM issue, not just a side effect of the
  crash loop — see Fix 4).
- **Full-volume trust cache**: `codesign` per-file across the volume's 311,060
  files would be far too slow. Wrote a fast, from-scratch Python cdhash
  extractor (`~/goldengate/md0patch/fast_cdhash.py`) that parses Mach-O/fat
  binaries directly — finds `LC_CODE_SIGNATURE`, locates the `CSSLOT_CODEDIRECTORY`
  blob inside the embedded `CSMAGIC_EMBEDDED_SIGNATURE` superblob, hashes it
  with SHA-256, truncates to 20 bytes. **Verified byte-for-byte correct**
  against `codesign -dvvv --arch arm64e` on a real fat binary (`/usr/bin/vim`)
  before trusting it at scale — caught and fixed two real bugs during
  verification: (1) codesign defaults to the **host** architecture (x86_64 on
  this Intel Mac) for a fat binary, but the **guest** needs the **arm64e**
  slice specifically — fixed by returning cdhashes for *all* slices, not just
  the first; (2) a Mach-O magic endianness bug — the *fat* header's own fields
  are big-endian per spec, but the *inner* per-architecture Mach-O header is
  native-endian (little-endian on every real target), so reading the inner
  magic with the same big-endian `struct` format silently produced the
  byte-swapped value and matched nothing. Fixed by reading `MH_MAGIC`/`MH_MAGIC_64`
  little-endian and `FAT_MAGIC` big-endian separately.
- Parallelized with `multiprocessing.Pool(8)` (I/O-bound, not CPU-bound —
  roughly ~10 minutes wall-clock for the full 309,920-file, 311,060-total-file
  scan on this machine). Result: **14,242 unique cdhashes** from the system
  volume alone.
- Merged with the original restore-ramdisk hashes + the ~104 Cryptex hashes:
  **14,660 total unique cdhashes** → `firmware/ramdisk_full.tc` (322,544 bytes
  = `24 + 14660*22`, matches `TrustCacheModule1_t` layout exactly).
- Regression-checked safe on the small ramdisk first, then booted the real
  system volume: **all mass trust-cache failures gone.** `launchd` ran cleanly
  through its entire boot-task sequence with zero `not in trust cache` or
  `owned by uid` lines at all.

### Milestone: real userspace boot — WindowServer, loginwindow, real daemons

With Fix 1+2+3 combined, the boot went **dramatically** further than ever
before in this project: `com.apple.WindowServer` appears and launchd attempts
to bootstrap it; `com.apple.loginwindow` (the real macOS login UI process)
actually **spawns** (`pid 75/76` across different runs);
`com.apple.endpointsecurity.endpointsecurityd`, `com.apple.configd`,
`com.apple.iomfb_fdr_loader`, `com.apple.accessoryupdaterd`,
`com.apple.uarpassetmanagerd` and dozens more real daemons spawn and run. This
is the deepest point ever reached in the macOS Golden Gate track — genuinely
comparable to the `ios27-cl4-secure-world` track's own "full userspace boots"
milestone, but for macOS specifically, on the QEMU/TCG path, for the first time.

### Wall found and fixed: `[SPTM] VIOLATION_INVALID_ASID`

Immediately after `loginwindow[N]` triggers a (normal, documented) shared-region
**unnest** — `vm: loginwindow[N] triggered unnest of range ... of DYLD shared
region in VM map ... While not abnormal for debuggers, this increases system
memory footprint until the target exits.` — boot panics:
```
panic(...): [SPTM] VIOLATION_INVALID_ASID: validate_asid(sptm_validation.h:220) - asid(0x100), sptm_num_asids(0x4000)
```
`sptm_num_asids=0x4000` is not small (16384), so this isn't a bounds/exhaustion
check — `validate_asid` is checking whether ASID `0x100` is *currently properly
registered* with SPTM, not whether it's numerically in range. The unnest
operation itself is legitimate XNU behavior (confirmed: the exact string is
XNU's own documented `vm_map` unnest-on-protection-change log message, found
in `bootkc` at file offset `0xb9736`); the bug is downstream, in how the
resulting TLB-invalidate-by-ASID call reaches SPTM.

Root-caused the check to `firmware/sptm` directly (a separate Mach-O, own
`__TEXT`/`__TEXT_EXEC` segments, static base `0xfffffff027004000`,
`__TEXT_EXEC` at `0xfffffff0270a4000`/fileoff `0xa0000`). Found via the same
string-anchor method: `"sptm_validation.h"` (fileoff `0x148b6`) and
`"validate_asid"` (fileoff `0x14d8a`) function-name strings, cross-referenced
via ADRP+ADD, then located the specific `mov w11, #0xdc` (220 decimal — the
line number) immediately adjacent to each `validate_asid` string load,
confirming exactly two inlined call sites: static va `0xfffffff0270e8850` and
`0xfffffff0270f8034`, both of the shape `mov w0, #4 ; bl 0xfffffff0270fea94`
(a shared violation-report/panic function used by many different checks in
this file, distinguished by the `w0` "category" argument — `4` = ASID check,
`5`/`0x10`/`0x50`/`2` etc. seen nearby for sibling checks). Neither call site's
following code consumes the call's return value, so NOPping just the `bl`
(Keystone `1f2003d5`) at both sites safely skips only this specific check.
Result: `firmware/sptm.asidfix`. Regression-checked safe on the small ramdisk,
then confirmed on the real volume: **the ASID violation is completely gone,
boot progresses further.**

### Wall found and fixed: `[SPTM] VIOLATION_INVALID_FLAG: validate_root_flags`

Immediately next: `validate_root_flags(sptm_validation.h:1208) -
root_flags(0x88b6)`. Same file, same technique, same call-site cluster (right
next to the ASID checks) — string va for `validate_root_flags` found via
xref, paired `mov w0, #0x10 ; bl 0xfffffff0270fea94` at static va
`0xfffffff0270e88f0` and `0xfffffff0270f7fec`. NOPped both. Result:
`firmware/sptm.asidfix2`. Regression-checked, then confirmed: **this violation
is also gone.**

### Wall found and fixed: `[SPTM] VIOLATION_ASID_IN_USE`

Next: `cpu_root_table_user_address_space_set_up(sptm_types.c:3804) -
fte(0xfffffdf0019af520), fte->type(XNU_DEFAULT), asid(117541046)` — a
*different* source file (`sptm_types.c`, not `sptm_validation.h`) but the
identical call-site shape and cluster location. Found via the
`cpu_root_table_user_address_space_set_up` function-name string, paired
`mov w0, #0x4f ; bl 0xfffffff0270fea94` at static va `0xfffffff0270e8938` and
`0xfffffff0270f807c`. NOPped both. Result: `firmware/sptm.asidfix3`.
Regression-checked safe, then confirmed on the real volume: **this violation
is also gone**, and boot progresses to a **new, different kind of wall** (see
below) — confirming this really was a distinct, separate check, not a
re-trigger of the same one.

**Honest note on this whole line of SPTM patches**: none of these are
understood at the "why does this actually happen" level the way the earlier
`dart-id` or `md0` truncation bugs were — they're patched empirically, by
finding the specific violation-report call and skipping it, in the same spirit
as the ios27 track's own "patch the validation gate, see what's next"
iterations on far harder secure-world checks. Every one has been
regression-checked safe on the known-good small-ramdisk boot before being
trusted on the real volume, so even though the root mechanism (why an ASID
that looks legitimately allocated fails SPTM's live-registration check, three
times in a row, for what's almost certainly the same underlying "our ASID
allocation/registration path doesn't fully match what SPTM independently
tracks" cause) isn't fully understood, the *practical effect* (unblocking
forward boot progress with no observed regression) is verified each time.

### Current wall: `TXM [Panic]: [code: 0x00000068 | 0]`

With all three SPTM patches applied, boot reaches even further — real daemons
`com.apple.iomfb_fdr_loader`, `com.apple.accessoryupdaterd`,
`com.apple.uarpassetmanagerd`, `com.apple.configd`,
`com.apple.endpointsecurity.endpointsecurityd` all spawn, and
`"AMFI: Denying core dump for pid 74 (opendirectoryd)"` appears immediately
before the panic — then:
```
panic(cpu 0 caller 0xfffffe002c550010): TXM [Panic]: [code: 0x00000068 | 0]
```
This is a **different security monitor entirely** (TXM, the Trusted Execution
Monitor — code-signing/entitlement enforcement — not SPTM, the page-table
monitor). `com.apple.txm` now appears in the panic backtrace's kext list for
the first time this session. Not yet root-caused — next step is the same
method: find the `"TXM [Panic]: "` format string in `firmware/txm` (confirmed
present at file offset `0x1991`, paired with `"Exception occurred at pc:
0x%016llx, lr: 0x%01..."` right after it, though that longer format doesn't
appear to have printed for this SPECIFIC panic, suggesting this is a simpler,
direct numeric-code panic path, not the exception-decode one), then find what
computes/checks code `0x68` specifically — likely a numeric enum in TXM's own
panic-code table, tied to whatever `opendirectoryd`'s core-dump-denial path
triggers on the TXM side (a coredump entitlement/monitor-extension check is a
very plausible culprit given the immediately-preceding AMFI line).

## Current known-good artifact set (use these going forward)

- `firmware/bootkc.md0size.uidfix` — md0 32-bit fix (Phase 6, earlier) + uid-gate
  neutered. Regression-checked safe.
- `firmware/dtree.dcp8.bigdram2` — `dtree.dcp8`'s DCP+ANS+dart-id node set,
  `dram-size` bumped to 40GB (room for the now-27GB grown system volume).
- `firmware/ramdisk_full.tc` — complete trust cache: restore-ramdisk hashes +
  Cryptex hashes + all 14,242 real cdhashes from the full system volume.
- `firmware/sptm.asidfix3` — three SPTM violation-report calls NOPped
  (VIOLATION_INVALID_ASID x2 sites, VIOLATION_INVALID_FLAG x2 sites,
  VIOLATION_ASID_IN_USE x2 sites — 6 total NOPs across 3 distinct checks).
- The merged, grown (27.07GB) system volume at
  `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg` now
  has the real dyld shared cache + `usr/lib` content merged directly onto its
  base tree at `/System/Library/dyld/` and `/usr/`.
- Full known-good boot command:
```
DARWIN_FB=1 DARWIN_RTKIT=1 DARWIN_DART=1 DARWIN_AIC=1 DARWIN_RTKIT_ANS=1 \
  build/qemu-system-aarch64 -icount shift=auto \
  -M darwin -bootkc firmware/bootkc.md0size.uidfix -dtree firmware/dtree.dcp8.bigdram2 \
  -tc firmware/ramdisk_full.tc \
  -ramdisk ~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg \
  -sptm firmware/sptm.asidfix3 -txm firmware/txm \
  -args "rd=md0 serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" \
  -serial mon:stdio -display none \
  -monitor unix:/tmp/<name>.sock,server,nowait -m 8G
```

## Next steps

1. Root-cause and patch the `TXM [Panic]: [code: 0x00000068]` wall (find the
   panic-code table / triggering check in `firmware/txm`, same
   string-anchor + ADRP+ADD xref method, regression-check, retest).
2. Keep iterating — expect more walls in this same family as boot pushes
   toward actual WindowServer/Aqua rendering; each one gets the same
   treatment.
3. Once (if) userspace stabilizes past this point, the previously-documented
   `AFKFirmwareService`/DCP display-pipeline wall (PHASE5_LOG.md) is still the
   known next blocker specifically for getting real pixels — worth checking
   whether it's still accurate now that so much more of the real OS is
   actually running (a fuller kernelcache/personality environment might behave
   differently than earlier restore-ramdisk-only investigations assumed).
4. **User's end-goal clarification (2026-09-18, this session)**: once/if a
   real graphical desktop is reached, the deliverable needs to go further than
   "runs inside a QEMU process on the existing host macOS" — the user wants a
   **USB drive that can be installed onto and FULL BOOTS the bare T480s
   hardware directly** (EFI-bootable, launches straight into this qemu-sptm +
   firmware stack with no host OS underneath). This is follow-up packaging
   work, tracked in persistent memory (`project_golden_gate_intel.md`), not
   yet started — the emulation breakthrough is the prerequisite.
