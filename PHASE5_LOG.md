# Phase 5: Real system volume acquired; ANS/storage controller matching; the precise remaining wall

## The real macOS system volume: acquired, decrypted, and confirmed complete

`043-70867-635.dmg.aea` from the source IPSW (11.27GB encrypted) downloaded
and decrypted successfully:
```
ipsw fw aea -o decrypted -b 'base64:iUC7LXadMs+MFgcAVrgG51JfRrNdS7S33BEiAINxnyc=' 043-70867-635.dmg.aea
```
Output: `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg`,
14.19GB, raw APFS whole-disk image, unencrypted. **The AEA key is a generic
OS-distribution key, not device-locked** — confirmed by fetching it
independently before the full download even completed.

Mounted and inspected directly (`hdiutil attach` + `mount_apfs -o rdonly`):
this is a **complete, real macOS root filesystem** —
`/Applications`, full `/System/Library/CoreServices` with `Dock.app`,
`Finder.app`, `loginwindow.app`, and the actual `WindowServer` binary at
`/System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer`
(208,512 bytes, real executable). This is everything needed for a genuine
desktop, confirmed present and intact.

**The restore ramdisk (`firmware/ramdisk.dmg`, ~373MB) used for every boot so
far has none of this** — confirmed by mounting it too:
`/System/Library/CoreServices` there contains only `ReportCrash` and
`SystemVersion.plist`. It's Apple's real "restored_external" personality
(a headless USB-restore backend), not an installer or recovery UI, even
unpatched. No amount of driver work on that ramdisk would ever show a
desktop — nothing in it would ever open a display connection. This is why
the system volume matters: it's the only thing in this whole project that
actually contains WindowServer.

**Host RAM makes the naive approach (load the whole system volume into guest
RAM like the current ramdisk mechanism does) infeasible**: the T480s has
16GB total host RAM; a 14GB+ in-memory disk alongside everything else the
guest needs doesn't fit. Real NVMe/block-device emulation (file-backed, not
memory-resident) is a genuine requirement, not a nice-to-have.

## ANS/storage RTKit transport: works exactly like DCP, and IOKit picks a real candidate driver

Found that `AppleANS3NVMeController` (Apple Silicon's real internal SSD
controller driver, embedded inside `com.apple.iokit.IONVMeFamily`, not a
separate kext bundle) matches via `IOProviderClass: RTBuddyService` +
`IOPropertyMatch: {"role": "ANS2"}` — **structurally identical to how
`AppleDCPExpert`/RTBuddy(DCP) matches**, which we already got working
earlier this session. The device tree's `arm-io/ans` node already has
`role=ANS2` and `compatible=iop,ascwrap-v4` in Apple's pristine tree (same
shape as `arm-io/dcp`), with `arm-io/ans/iop-ans-nub` mirroring
`arm-io/dcp/iop-dcp-nub` (`compatible=iop-nub,rtbuddy-v2`) and
`arm-io/sart-ans` (a SART, not a DART — simpler, and did NOT trigger any
SPTM-level hang the way `dart-dcp` did).

Extended the working device tree (`EXTRA_NODES` now includes
`arm-io/ans;arm-io/ans/iop-ans-nub;arm-io/sart-ans` alongside the existing
DCP nodes) → **`firmware/dtree.dcp8`** on the T480s. Booted with
`DARWIN_RTKIT_ANS=1` added. Result, all real, driver-authored log lines:

```
RTBuddy(ANS2): start(<ptr>) - (Aug 30 2026@18:51:59)
AppleANS2CGv2Controller::probe ... Found (ANS2) provider and coastguard, returning score 400000
AppleANS2NVMeController::probe ... Found (ANS2) provider, returning score 100000
AppleANS3CGv2Controller::probe ... Found (ANS2) provider and coastguard, returning score 500000   <- winner
AppleANS3NVMeController::probe ... Found (ANS2) provider and linear-sq, returning score 300000
```

This is **real Apple IOKit driver-matching competition, resolved
correctly** — multiple real candidate storage-controller classes probed our
emulated hardware, scored themselves, and IOKit picked the highest scorer
(`AppleANS3CGv2Controller`, 500000) exactly as it would on real silicon.
This is now the third piece of genuine Apple driver code (after
RTBuddy(DCP) and RTBuddy(ANS2) itself) confirmed running correctly against
our emulation.

## The precise remaining wall: `AFKFirmwareService` is genuinely missing from this kernelcache, and it blocks the winning candidate

Immediately after the winning probe, `Couldn't alloc class
"AFKFirmwareService"` appears — and critically, **nothing ANS/NVMe-related
ever appears in the log again** after that line (no `start()` call from
`AppleANS3CGv2Controller`, no register access on the `[ans-nvme]` MMIO
window at all beyond the initial region-mapping printf). This revises an
earlier, too-optimistic read from PHASE4_LOG.md (which guessed this class
was only needed for the irrelevant external-display `DCPEXT` path) — for the
storage controller specifically, its absence appears to be a **real,
hard stop** on hardware bring-up, not a harmless side failure.

Already confirmed via two independent methods this session that
`AFKFirmwareService`'s C++ implementation is **not compiled into this
specific kernelcache** (`firmware/bootkc`, from the `26A428` Golden Gate
seed build) at all, despite its personality existing in the plist:
(a) the literal string `"AFKFirmwareService"` never appears in `bootkc`'s
runtime `__TEXT.__cstring` — only in plist metadata — and (b) `kextlog=0xfff`
shows `AppleFirmwareKit`'s own module-start registering ~40 real
OSMetaClasses but never this one (nor `AFKResource`, its sibling gap). This
looks like a genuine Apple-side omission specific to this early seed build,
not something fixable via device tree, QEMU emulation, or boot-args.

**Ruled out an alternative theory too**: checked whether "coastguard" (the
`sart,coastguard`-matched `IOCoastGuardSARTMapper`, referenced in the
winning probe's own log message) might be the real hidden blocker instead.
It isn't — `IOCoastGuardSARTMapper` matches via simple `IONameMatch` against
`compatible` (no `dart-id`-style derived-property complexity like DART had),
and critically, the probe log line itself (*"Found (ANS2) provider **and
coastguard**, returning score 500000"*) proves coastguard matching already
succeeded — it's a precondition for that exact score being computed.
`AFKFirmwareService` really is the specific, isolated remaining blocker.

## Live guest debugging via QEMU's gdbstub (new capability, proven working)

Went past static analysis to get live, definitive answers, using a
technique not used earlier this session: QEMU's built-in guest-CPU gdbstub
(`-s -S` flags), connected to via `lldb`'s `gdb-remote 127.0.0.1:1234`
(macOS only has `lldb`, no `gdb`, but `lldb`'s gdb-remote client works fine
against a bare-metal AArch64 target once you know to expect unsymbolicated
frames and address-only breakpoints).

**Nailed down the address-slide question definitively** (this also
retroactively confirms the earlier SPTM `dart-id` investigation's addressing
was interpreted correctly): on connect, the gdbstub itself reports
`Load Address: 0xfffffe002700c000` — exactly `static_base + 0x20000000`,
matching the `bkc slide` value printed at boot. So: **live/runtime kernel
code addresses = the static symbol-map address + 0x20000000**, always, for
normal XNU kernel/kext code (the earlier SPTM hang PC was a different,
special case — an EL2 address outside this normal kernel range entirely,
which is why it didn't fit this pattern).

Generated a full symbol map (`ipsw kernel symbolicate --json`,
`/tmp/symmap/bootkc.symbols.json` on the T480s, 16,524 symbols) and used it
to set a real breakpoint on `AppleANS3CGv2Controller`'s constructor.
**It hit** — direct, live proof the winning candidate really does get
instantiated (not skipped or dead code). The backtrace at that point
resolves (via nearest-symbol, since the map doesn't have every function) to
`IOCatalogue`/`IORegistryIterator`/`OSOrderedSet`-adjacent code — i.e. IOKit's
own generic driver-matching machinery constructing a probe candidate, the
normal, expected flow.

Then set a **read watchpoint directly on the `"Couldn't alloc class \"%s\""`
format string's own memory address** (a cleaner technique than hunting for
the ADRP/ADD cross-reference site by hand, since we don't need to know the
caller's address in advance — just watch the string itself and let the CPU
tell us who reads it). It fired twice, both times **still inside generic
IOKit registry/matching code** (`IORegistryIterator`/`OSValueObject`-adjacent
addresses again), not inside anything specifically named
`AppleANS3CGv2Controller`. This is genuinely ambiguous evidence — it's
consistent with the failure happening as part of the **shared, personality-
driven matching sweep** IOKit runs for every `RTBuddyService`-provided
instance (which would include re-litigating my PHASE4 guess that this
specific string is actually about the *external display* (`role: DCPEXT`)
match, not our ANS2/primary-panel one) — but it doesn't conclusively rule
out an ANS-critical-path failure either, since the sparse symbol map can't
fully resolve these frames to real function names.

**Followed up on this caveat directly, and it's more interesting than
expected.** The `"Couldn't alloc class \"%s\""` string is shared by every
failed class allocation, so a watchpoint on it fires for all of them — but
figuring out *which* class per hit is possible: at the outer call site,
`x2` holds the format string and `x3` holds a varargs pointer whose first
qword, dereferenced, is a pointer to the actual class-name string (`x0`/`x1`
at the inner, nested vprintf-style call one level down — confirmed
`(*(long*)($x3))` → a valid pointer → dereferenced again → a clean
`"AFKResource"` string, twice, matching the same address both times,
meaning that pair of hits was one logical event seen at two call layers).

**But this technique is much noisier than assumed**: continuing past that
pair, the *next several* hits land at the exact same PC as the "inner" layer
but with `x0` holding single ASCII byte values (`0x43`, `0x6f`, `0x75`,
`0x6c`, `0x64`, `0x6e` → `'C'`,`'o'`,`'u'`,`'l'`,`'d'`,`'n'`) — i.e. the
watchpoint is also triggering on a **byte-by-byte scan of the same format
string** (almost certainly an internal `strlen`/copy loop inside whatever
implements the log call), not on separate logical `"Couldn't alloc class"`
events. This means the "8 hits" captured this session are mostly redundant
noise from a single event's internal string handling, not 8 distinct class-
allocation failures — so **this run never actually reached a hit for
`AFKFirmwareService` specifically** (chronologically, per the boot log,
`AFKFirmwareService` fires *before* any `AFKResource` occurrence, so the
first clean hit reading `"AFKResource"` twice is already surprising, and
likely reflects boot-to-boot scheduling non-determinism rather than a
contradiction).

**Net conclusion on this specific line of inquiry: still open.** The
watchpoint-on-format-string approach works and is a legitimate technique
(confirmed it can cleanly resolve a class name), but distinguishing the
*specific* `AFKFirmwareService` occurrence from the noise needs a tighter
technique — e.g. a real breakpoint on `OSMetaClass::allocClassWithName`'s
entry (reading its own class-name argument directly, no string-scan noise
to filter) rather than watching the shared format string. Finding that
function's address (no direct symbol in our sparse map) is the next concrete
step, via the same string cross-reference method already proven on `sptm`
this session, applied to `bootkc`'s far larger `__TEXT_EXEC` this time.

**Ruled out one possible hole in the "no further ANS register activity"
finding**: checked whether `AnsNvmeState`'s trace-print budget (governing
the `[ans-nvme] read/write` log lines) was actually available — confirmed
it's initialized to 60 (`s->trace = 60`), not zero, so if any of the 60
first register accesses had happened they would have been logged. None
were. This closes the gap and reconfirms: whatever finally happens (or
doesn't) after the winning candidate is chosen, it genuinely never touches
the ANS/NVMe MMIO window at all in this boot.

## Correction to PHASE4's "DCPEXT-only, likely harmless" theory — this is bigger than that

PHASE4_LOG.md guessed `AFKFirmwareService`'s failure was specific to the
*external* display path (`role: "DCPEXT"`) and therefore probably harmless
to the primary panel. **That was wrong.** Checked every
`AFKFirmwareService`-matching personality in `bootkc`:

```
com.apple.driver.AppleDCP         -> DCPFirmwareServiceEXT  role="DCPEXT"
com.apple.driver.DCPAVFamilyProxy -> DCPFirmwareService     role="DCP"      <- the primary panel
```

`AFKFirmwareService` is required for the **primary internal panel path too**
(published by `DCPAVFamilyProxy`, matching our actual `dcp0-expert`/`role:
ANS2`-sibling `role: DCP`), not just the external-display one. Combined with
it also blocking the ANS storage controller (confirmed this session), this
single missing class is very likely **the one shared blocker standing
between where this project is now and real AFK/IOMFB protocol traffic on
every remaining front** — DCP's real display pipeline and ANS storage both.
Confirmed directly too: booted with every fix combined (`dtree.dcp8`,
`DARWIN_FB/RTKIT/DART/AIC/RTKIT_ANS` all set) and waited well past normal
boot completion — `"AFK transport up"` never appears anywhere in the log,
on either endpoint, consistent with this shared blocker theory.

This makes supplying a working `AFKFirmwareService` implementation (or
finding another way past it) the clear highest-leverage next step — more
so than continuing to chase ANS-specific or DCP-specific dead ends
separately.

### What this means, and the honest options from here

1. ~~Check whether a different/later Golden Gate build exists~~ **Ruled
   out**: `ipsw download ipsw --device Mac14,3 --macos --version 27.0 --urls`
   returns exactly one URL, the same `26A428` build already in use. Golden
   Gate shipped very recently and this is genuinely the only public build
   right now — no alternate kernelcache to fall back on.
2. **Binary-patch the kernelcache** to supply a working
   `AFKFirmwareService` implementation ourselves. This is a real, if
   extreme, option — we already have the tooling (`ipsw macho`/disassembly,
   proven this session on both `sptm` and `bootkc`) and understand the class
   registration mechanism precisely (`OSDeclareDefaultStructors`-generated
   static constructors, confirmed via `kextlog`'s exact "registered class X"
   trace). Reconstructing and injecting a minimal working version is a
   substantial, multi-session engineering task, not a quick fix.
3. **Confirm whether this really is fatal**, rather than assuming from
   silence — attach `lldb` to a live boot at this exact point (same
   technique used successfully for the SPTM `dart-id` discovery) to see
   whether `AppleANS3CGv2Controller::start()` is actually being called and
   returning early/failing, vs. genuinely never being invoked at all. This
   would definitively settle whether the class is truly required or whether
   something else entirely is silently deciding not to proceed.

## Overall session arc (for continuity across sessions)

Picked up from Codex's incomplete `dart-dcp` device-tree fix →
root-caused and fixed the actual SPTM hang (missing `dart-id` property,
found via live register inspection of a mid-panic CPU) → confirmed real
Apple driver code (`RTBuddy(DCP)`) starting for the first time in this
project → discovered the restore ramdisk can never show a desktop
regardless of driver progress (no WindowServer present) → acquired,
decrypted, and confirmed a complete real macOS system volume with
WindowServer/Finder/Dock present → found the ANS/storage driver uses the
exact same, already-proven RTKit transport as DCP → got real IOKit driver
competition/scoring working correctly for the storage controller → precisely
identified the next wall (`AFKFirmwareService` missing from this kernelcache
build). Every step from the SPTM fix onward is a genuine first for this
project. Full detail in `PHASE3_LOG.md` and `PHASE4_LOG.md`; this file
covers the system-volume acquisition and ANS breakthrough specifically.

## Phase 6 (same continued session): booting XNU directly from the real system volume — got extremely close

Pivoted away from the `AFKFirmwareService` kernel-patching problem toward a
more promising, more tractable idea: since XNU already knows how to boot
from a "ramdisk" (`rd=md0`) — proven working all session — what if the
*real* macOS system volume could be presented through that exact same
mechanism instead of needing full NVMe emulation from scratch?

**The RAM problem and its real solution**: the existing ramdisk-loading code
(`arm_load_xnu_sptm` in `hw/arm/xnuboot_sptm.c`) copies the whole ramdisk
file into anonymous guest RAM via `address_space_write()` — fine for the
current ~373MB ramdisk, impossible for a 14GB system volume on a 16GB-RAM
host. Fixed this by backing the ramdisk's guest memory region directly with
its file via QEMU's `memory_region_init_ram_from_file()` (real `mmap()`,
private/copy-on-write) instead of copying — this only faults in pages XNU
actually touches, using host page cache/disk as backing rather than
requiring the whole thing resident in RAM up front.

**First attempt failed with a real, informative panic**: placing the new
region at a separate address (either far away or elsewhere within
`dram_size`) reliably panicked with `"ramdisk params @IOKitBSDInit.cpp:789"`
— even though the mapped content itself was verified byte-correct via the
QEMU monitor (`xp`, confirmed a real APFS `NXSB` superblock magic at the
mapped address). This ruled out a mapping/content bug and pointed at a
consistency check against XNU's expected sequential boot-blob layout
(`topOfKernelData` etc.) instead.

**The fix that actually worked**: keep the ramdisk's placement exactly where
XNU has always expected it (the original sequential `blob_head` address,
preserving `topOfKernelData` and ADT layout exactly as before), but back
*that same address* with the file-mapped region as a high-priority overlay
(`memory_region_add_subregion_overlap(..., priority=1)`) instead of the
plain anonymous-RAM subregion the copy used to fill. **This booted the
existing small ramdisk cleanly, confirming the mechanism works.**

**Extending to the real 14GB system volume**: increased the device tree's
`chosen/dram-size` (in `dt_fixup.py`) to a much larger nominal value
(28GB) to make room for the ramdisk within the address range XNU's pmap
bootstrap recognizes as valid — confirmed empirically that this does **not**
require 28GB of real host RAM (`ps` showed ~300MB resident after boot start;
anonymous RAM backing is itself lazily-committed, and the overlaid ramdisk
range never touches it at all since the file-backed overlay takes priority
there). Pointed `-ramdisk` directly at the decrypted
`043-70867-635.dmg` (the real system volume) and booted.

**Result: it worked far further than anything in this entire project so
far.** Full, clean kernel bootstrap — VM bootstrap, TXM/Image4/AMFI/Sandbox/
EndpointSecurity policy loading, all completely normal — then reached actual
**APFS mount code actively parsing the real system volume's real superblock**
(`nx_dev_init`, `apfs_vfsop_mountroot`, `container_rootmount`). No panic, no
hang. It correctly read the volume's true size directly from its own
on-disk APFS superblock: `nx_dev_init:740: md0 superblock container size
14189330432` — a dead-accurate 14.19GB, proving content integrity, DMA path,
and the overlay mechanism all genuinely work end-to-end for the real data.

**The wall reached this time**: `"container size 14189330432 greater than
device size 1304428544"` — XNU's BSD memory-device layer reports a *device*
size of exactly `14189330432 mod 2^32 = 1304428544`. This is an exact,
unambiguous 32-bit truncation (confirmed via the arithmetic, not a guess):
somewhere in XNU's own `rd=md0` memory-device driver, the size is carried in
a 32-bit field, silently wrapping for anything over ~4GB. This looks like a
genuine, structural limitation of the memory-disk-boot mechanism itself
(real Apple memory-disk boots were never meant to be this large), not
something introduced by this session's patch — the same ceiling would very
likely have hit the old copy-based approach too, had anyone tried a
multi-GB ramdisk with it.

### What this means for the next step

The overlay/file-mapping technique is real, proven, and reusable — this is
a genuine capability now, not a dead end. The blocker is specifically
**getting a bootable macOS system volume under ~4GB**. Two honest paths from
here, neither attempted yet:

1. **Build a trimmed system volume** from the real one now in hand — strip
   `/Applications`, non-English `.lproj` localizations, and other safely
   prunable content to get the real volume under 4GB, then repoint
   `-ramdisk` at that instead. Real risk: modern macOS system volumes are
   normally Signed/Sealed (SSV) with per-file hash verification; it's
   unknown yet whether this emulated boot chain enforces that strictly
   enough to reject a locally-modified volume, or tolerates it the way it
   already tolerates other relaxed security checks seen this session
   (`AMFI: developer mode is force enabled`, `Booted in a VM`, etc.).
   **Not attempted this session** — deliberately, because the T480s only had
   ~16GB free disk (not enough to safely copy-before-trim the 14GB volume),
   and the original encrypted `.aea` source was already deleted to reclaim
   space earlier this session, meaning a botched in-place trim would need a
   full ~2-hour re-download + re-decrypt to recover from. This needs either
   more free disk space first, or a carefully-planned in-place approach,
   not a rushed one.
2. **Real NVMe/block-device emulation** (the original plan, set aside for
   this detour) — sidesteps the 32-bit ramdisk-size ceiling entirely, since
   real block I/O doesn't require the whole device size to fit in any
   XNU-internal 32-bit field the way the memory-disk mechanism apparently
   does. Still the "proper", larger undertaking noted in earlier phases.

### Attempted trimming this session — real progress, didn't converge, and a key realization

Attempted path 1 directly. Mounted the real volume read-only (never
touched — safe) and surveyed sizes: `/System` is 12GB of the 14GB total,
`/usr` 903MB, everything else (`/Applications`, `/Library`, `/Users`, etc.)
is 0 bytes — this volume is a modern split System/Data volume-group image,
and the *System* side alone (which is all we need — `WindowServer`,
`Dock.app`, `Finder.app`, `loginwindow.app` all live under
`/System/Library/CoreServices`) is what needs to fit.

Checked `otool -L` on `WindowServer` itself: only 2 direct link
dependencies (`SkyLight.framework`, `libSystem.B.dylib`) — and confirmed
**no dyld shared cache exists anywhere on this volume**
(`/System/Library/dyld/` doesn't exist), meaning every framework's real
code genuinely lives in its own individual files on disk (no pre-linked
cache to lean on, but also nothing to "lose" by excluding unused
frameworks individually).

Built an exclusion list of clearly non-essential content (iOS app-
compatibility support, system Apps bundle, spell-check/dictation
linguistic data, document templates, wallpapers, Siri/ML/vision/handwriting/
home-automation frameworks — ~26 individually identified, totaling a couple
GB) and `rsync`'d into a fresh, empty 3.8GB APFS image (never touching the
original 14GB source). **Ran out of space before finishing** — even after
those exclusions, `CoreServices` alone measured 961MB copied,
`Fonts` 789MB, `Frameworks` 626MB, `Components` 366MB, plus `/usr`'s 903MB,
already exceeding 3.8GB before even reaching the (much larger)
`PrivateFrameworks` remainder. Cleaned up the failed attempt (deleted the
partial trimmed image, the real 14GB source was never at risk).

**The real lesson from this attempt, more valuable than the failed size
target**: getting a modern macOS system volume under 4GB by manual
exclusion is a much bigger, more iterative undertaking than a first
reasonable pass can close — realistically needs proper dependency-graph
tracing (`otool -L`/`dyld_info` followed recursively from `WindowServer`
outward, keeping exactly what's linked and nothing else) rather than
size-based guessing, which is a substantial task on its own.

**But this also produced a bigger-picture realization that matters more
than the failed attempt itself**: `rd=md0`/the memory-disk boot mechanism
was never designed for full system volumes on *any* real Apple hardware
either — real Macs always boot their real, multi-GB system volume through
the actual NVMe storage stack (`AppleANS3NVMeController`, matched via
`RTBuddyService`/`role: ANS2` — the same driver this session already got to
matching-and-probing successfully). **The two threads from this session
converge, not diverge**: getting the real system volume to boot still goes
through fixing the `AFKFirmwareService` gap (Phase 5's main finding) either
way — that isn't a detour from the ramdisk-trimming idea, it's confirmation
that it was always the correct, necessary path. The trimming/overlay
detour this phase wasn't wasted, though: the file-backed overlay
memory-region technique is real, proven, general-purpose infrastructure
(confirmed working end-to-end against real 14GB content) that will likely
be directly useful for backing real NVMe DMA buffers/data transfer
directly from a file too, once that work resumes.

**T480s state at end of session**: no QEMU processes running (cleaned up).
`~/goldengate/system_volume/trimmed.dmg` was deleted (the failed attempt);
`~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg` (the
real, untouched, complete system volume) remains on disk, ~16GB free
remaining.
Known-good artifacts: `firmware/dtree.dcp8` (DCP + ANS nodes restored, safe,
boots to shell every time), `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg`
(the real, confirmed-complete system volume, 14.19GB, ready to use once a
real block-device path exists to present it to the guest).

## New reusable capability: live QEMU guest debugging via gdbstub

Worth calling out on its own since it'll be useful for whatever comes next,
not just this session's specific investigation:

```
# 1. Launch QEMU with -s -S added (gdbstub on :1234, halted at reset)
# 2. Connect and drive it:
lldb -o 'gdb-remote 127.0.0.1:1234' -o '<commands>' ...
# or, more reliably for multi-step sessions, a command file:
lldb -b -s /path/to/script.lldb
```

Key things learned the hard way, worth remembering next time:
- Runtime kernel/kext code addresses = the static symbol-map address
  (`ipsw kernel symbolicate --json`) **+ 0x20000000** — confirmed directly
  from the gdbstub's own `Load Address:` banner on connect, which equals
  `static_base + slide` every time.
- `ipsw kernel symbolicate --json --output <dir> <bootkc>` produces a
  reusable `<name>.symbols.json` address→symbol map — generate it once,
  reuse it for every lookup rather than re-running full C++ symbol discovery
  each time (it's slow, ~16K symbols).
- `lldb -b -s <script>` (batch mode from a command file) is far more
  reliable than chaining many `-o` flags for multi-step sessions — but it
  **aborts the whole script on the first command that errors** (e.g. a bad
  memory dereference), so don't mix commands you're not sure will succeed
  with ones you need later in the same script; split into separate runs if
  unsure.
- Data watchpoints on a shared/generic string (like a format string reused
  by many log call sites) are much noisier than expected — they fire on
  *every* read including internal byte-by-byte scanning (`strlen`-style
  loops), not just the "logical" one-hit-per-call-site read you're hoping
  for. A conditional/targeted **code breakpoint** at a specific instruction
  address (found via one prior watchpoint hit, then reused directly) is
  cleaner once you know roughly where to look, but you still need the
  address of the *real* function entry point, not just an instruction
  somewhere inside it that happened to be visible in one backtrace, to
  reliably distinguish separate logical events from each other.
- QEMU's own `-serial mon:stdio` mode multiplexes the monitor onto the same
  stream as guest serial output — use a **separate** `-monitor
  unix:...,server,nowait` socket (as this whole project already does) so
  `-s -S`/gdbstub work doesn't fight with wanting to read the boot log

## Correction: AFKFirmwareService is NOT relevant to the ANS/storage path

Earlier in this same continued session this log stated both the DCP display
path and the ANS storage path "converge on one single next step" (patching
`AFKFirmwareService`). That's wrong for the ANS path specifically. An
exhaustive search of every IOKit personality requiring `AFKFirmwareService`
(via the kexts.json/kextlog symbol map) found only `role: "DCP"` and
`role: "DCPEXT"` — no `role: "ANS2"` personality references it at all.
`AppleSART`/`IOCoastGuardSARTMapper` was also confirmed loading and scoring
successfully for both `AppleANS2CGv2Controller` and `AppleANS3CGv2Controller`
(`kextlog` shows `Kext com.apple.driver.AppleSART loaded.` and both
controllers' `probe()` logging `Found (ANS2) provider and coastguard`). So
neither of the two leading suspects from earlier in this session actually
explains why the ANS controllers never touch hardware. AFKFirmwareService
remains a real, separate, still-open problem for the DCP *display* path only.

## The real ANS blocker: a genuine, confirmed CPU-bound hang after all 4 candidates probe — not a WFI stall, not a missing class

Used the project's gdbstub technique (see above) to settle this properly
instead of guessing from black-box boot-log silence:

- Located all 4 ANS storage-controller candidate constructors via the
  `bootkc.symbols.json` map (`AppleXCGv2Controller::AppleXCGv2Controller`
  static addresses, +0x20000000 for runtime): `AppleANS2CGv2Controller`,
  `AppleANS2NVMeController`, `AppleANS3CGv2Controller`,
  `AppleANS3NVMeController`. Breakpointed all 4 — each hits exactly once,
  confirming (again) IOKit constructs one instance per matching candidate,
  and all 4 return to the same shared caller (`0xfffffe002c36ee00`, the
  candidate-construction loop).
- After the 4th constructor returns, single-stepped (`thread step-inst -c
  25` in a loop, ~3000 instructions total) rather than blindly
  `continue`-ing. **This is the key methodological fix**: the CPU is
  genuinely, continuously executing — cycling through real code in several
  distinct functions (`0xfffffe002bd538xx`, `0xfffffe002bc74xxx`,
  `0xfffffe002bc73axx`, `0xfffffe002bbfdexx`) that look like array/loop
  iteration, hashing, and comparison logic (classic driver-matching
  scoring/sort machinery) — **not** a `WFI`/spin-on-nothing instruction.
  This directly disproves the earlier "it's just parked/deadlocked"
  assumption from this session's prior black-box waits.
- BUT: confirmed separately (plain, non-debugged boot, `-ramdisk` pointed at
  a 1MB all-zero dummy file so no `Apple_HFS` IOMedia can ever match it, no
  `rd=md0` boot-arg so XNU can't shortcut straight to the ramdisk) that after
  **12 real minutes** of continuous ~100% CPU (`ps` showed `12:36` of CPU
  time accumulated against a 12-minute wall clock — i.e. it never stopped
  running), the boot log is **byte-for-byte identical** to where it was
  after the first ~15 seconds: stuck immediately after the same 4 `probe()`
  score lines, zero further output. A control boot in the same session with
  `rd=md0` present reached an interactive `bash-3.2#` shell in well under a
  minute. So this **is** a genuine hang, just not the kind you can see from
  a `WFI`/register dump — it's a real, `busy`-executing loop/algorithm in
  the matching-to-start transition that never terminates for the ANS
  candidate family specifically, in this exact configuration.
- `[ans-nvme]` MMIO trace (`hw/arm/darwin.c`'s trace_budget, 60 slots,
  proven available and unused) shows exactly **one** hit the entire time,
  at the very start of boot (line 14, `0x279000000 + 0x1000000 (reg[4])`,
  almost certainly incidental device-tree/ADT probing before any driver
  matching begins) — zero hits during or after the 12-minute busy-loop.
  Whatever this loop is doing, it never touches ANS/NVMe hardware registers
  at all; it's purely spinning in software.
- **Leading theory, not yet confirmed**: `RTBuddy(ANS2)::start()` (the
  RTKit/coprocessor-proxy layer, separate from the 4 higher-level storage
  *controller* candidates) does fire successfully and print its start
  banner — so the low-level RTKit mailbox handshake with the emulated ANS
  coprocessor works at a basic level. The busy-loop most likely lives in
  IOKit's post-probe matching/instantiation code trying to actually bring up
  the winning candidate (`AppleANS3CGv2Controller`, score 500000) and is
  probably polling/retrying on a coprocessor-level acknowledgment (an RTKit
  message round-trip) that this project's `DARWIN_RTKIT_ANS=1` emulation
  never sends, because the specific message/protocol needed for full
  controller bring-up (as opposed to just the basic RTKit handshake
  `RTBuddy(ANS2): start()` needs) isn't implemented. This has NOT been
  proven yet — the next concrete step is a **hardware watchpoint** on
  whatever memory location the `0xfffffe002bd538xx`/`0xfffffe002bc74xxx`
  loop keeps re-reading, to identify the exact poll condition, rather than
  further blind single-stepping.
- **Practical implication**: this means implementing real NVMe/ANS
  register-level command emulation (SetupAdminQueue, submission/completion
  queues, etc.) would currently be wasted effort — the guest never reaches
  the point of touching those registers regardless of what's implemented
  there, because it's stuck one layer up, in IOKit's own matching/start
  logic, before any hardware access is attempted.

**Correction/refinement (same continued session, next tick)**: breakpointed
the small nested loop found in the stepi trace directly
(`0xfffffe002bd538f8`) and counted real hits over a fresh 10-minute window:
only **61 hits total** (≈4 full invocations of that small helper — its own
loop bounds are tiny, `x25` fixed at 2, `x19` fixed at 8, `x8` never exceeds
1). That means this specific small hash/array helper is NOT the time sink —
it's called only a handful of times. The actual 10-12 minutes of real
100%-CPU time is being spent somewhere else in the surrounding call chain
(frames above it: `0xfffffe002bc746b8` → `0xfffffe002bc7445c` →
`0xfffffe002bbfdf1c` → `0xfffffe002c3343f4` → `0xfffffe002adf94d0` → the
same `0xfffffe002c36ee00` candidate-processing loop from before), most
likely iterating some much larger systemwide collection (candidate
personality count, or the full `sAllClassesDict` of 3924 registered C++
classes noted earlier this session) where each element's processing touches
this same small code footprint. **This softens the "genuine hang" claim
above** — it's equally consistent with legitimately slow-but-finite O(n) or
O(n·log n) work over a large collection as it is with a true infinite loop;
12 minutes of observation doesn't distinguish the two. Next step in
progress: a much longer (45+ minute) unobserved, full-speed (no gdbstub
overhead) boot to see whether it ever actually completes on its own — if it
does, this whole "wall" resolves itself with patience alone and needs no
code fix at all.

## ROOT CAUSE FOUND: an infinite seqlock-retry spin reading `CNTVCTSS_EL0`, not an ANS/storage bug at all

**The 30-minute patience test above ran to completion with zero log
progress — definitively ruling out "slow but finite."** Two further,
decisive steps pinned down the exact cause:

1. Breakpointed `IONVMeBlockStorageDevice::IONVMeBlockStorageDevice`
   (static `0xfffffe000adf94cc`, found via nearest-symbol lookup on one
   frame of the earlier stuck backtrace) and let it run 20+ minutes: **it
   is called exactly once.** This rules out "an object is being
   reconstructed in a loop" — whatever's looping is *inside* a single call,
   not at the object-construction granularity.
2. Rather than another breakpoint/backtrace, queried the live vCPU state
   directly and cheaply via the QMP/HMP socket (`echo 'info registers' | nc
   -U <monitor-socket>`) — no gdbstub pause needed, doesn't perturb
   execution. **Sampled the live PC six times over ~15 real seconds: every
   single sample returned the exact same PC (`0xfffffe002bc2d6c4`) with
   identical register contents (`X00`, `X01`, etc. bit-for-bit unchanged
   across samples).** That is conclusive: the CPU is in a genuine tight
   spin, not merely revisiting the same code occasionally as part of slow
   but real progress.

Disassembling around that PC (`ipsw macho disass ... -a
0xfffffe000bc2d690 -c 30`, static address, EL2 — `PSTATE` showed `EL2t`,
consistent with this being SPTM/TXM-adjacent low-level code rather than
plain XNU EL1 kernel code) reveals a classic seqlock/timestamp-consistency
retry pattern:

```
loc_fffffe000bc2d6c0:
    mov   x8, x10
    mrs   x9, agtcntvctss_el0        ; read ARM's self-synchronized virtual
                                       ; counter (FEAT_ECV CNTVCTSS_EL0)
    ldr   x10, [x20, #0x1c0]
    ldr   x10, [x10, #0x58]          ; re-read a memory-shadowed copy
    cmp   x10, x8
    b.ne  loc_fffffe000bc2d6c0        ; retry if the shadow value changed
                                       ; since loop entry
    add   x21, x9, x8                 ; (never reached in our runs)
```

This is the standard "read hardware counter + a software-maintained shadow
value, retry until both agree" pattern used to get a self-consistent
timestamp. **It is supposed to converge in 1–2 iterations.** In every run
this session it never converges — the register snapshot (`x8`) taken at
loop entry never matches the freshly re-read shadow value (`x10`) on the
very next check, forever. **This means QEMU's TCG emulation of
`CNTVCTSS_EL0` (or whatever maintains the memory-shadowed copy at
`[x20+0x1c0]→+0x58` that this code cross-checks it against) is
internally inconsistent** — most likely the register read and the memory
shadow update are driven by two different, unsynchronized time sources in
this project's QEMU fork, so they never agree bit-for-bit at the same
instant, and this particular consistency-check loop (present somewhere in
SPTM/TXM or very low-level XNU EL2-adjacent code, not in `AppleANS*`/
`IONVMe*` code at all) spins forever as a result.

**This reframes the entire "ANS storage controller never touches
hardware" investigation from earlier in this session**: it was never an
ANS/NVMe/storage-specific problem. The 4 ANS candidates' `probe()` calls
and one `IONVMeBlockStorageDevice` construction are exactly where boot
*happens* to reach this generic timer-consistency code next (during the
CPU-time / clock-set-up path this matching machinery triggers) — the real
bug is a **generic, project-wide timekeeping emulation inconsistency**
that would eventually be hit by ANY boot path that reaches this specific
consistency-check call, not something specific to storage matching. It's
plausible this exact spin is also why earlier phases' *other* stalls (not
yet re-examined with this lens) looked mysterious — worth checking whether
previously-"working" boots (the ones reaching `bash-3.2#`) simply never
happen to execute this particular code path, rather than not being
affected by the underlying bug.

**Next step**: find where this consistency loop's memory-shadow value
(`[x20+0x1c0]→+0x58`) gets written in this project's `qemu-sptm-cl4-native`
QEMU source (likely in `hw/arm/xnuboot_sptm.c`, `hw/arm/darwin.c`, or
wherever `CNTVCTSS_EL0`/the commpage-style continuous-time value is set up)
and check whether it's updated using the same clock/tick source as the
register read, or a genuinely different one that can never agree.
  cleanly at the same time.
