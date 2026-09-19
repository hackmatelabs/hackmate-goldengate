# Phase 3: DCP transport verification and protocol bring-up

## 2026-09-16 — baseline audit

Read `CODEX_HANDOFF.md` and `PHASE2_LOG.md` in full, then inspected the current
source and a fresh running boot on the T480s.

Verified facts from `/private/tmp/cl4_boot.log`:

- QEMU created the DCP RTKit mailbox and attached the 640x1136 framebuffer.
- The guest reached `bash-3.2#` without a panic.
- The log contains `[dcp] console feed attached`, and the existing screendump
  remains evidence for the serial-to-framebuffer renderer.
- The log contains **no** `CPU_CONTROL RUN`, RTKit `HELLO_REPLY`, AFK `INIT`,
  `GETBUF_ACK`, `START_ACK`, `RECV`, or `AFK transport up` lines.
- The guest instead prints `Couldn't alloc class "AFKResource"` three times.

This means the documented `run_cl4.sh` (`DARWIN_FB=1 DARWIN_RTKIT=1`) does not
reproduce the handoff's claimed AFK handshake. The source explains why:
`apple_rtkit_boot()` is called only after a guest write of `CPU_CONTROL RUN` or
when `DARWIN_RTKIT_ANNOUNCE=<seconds>` schedules a synthetic HELLO. The launch
script sets neither condition, and the guest performs no DCP mailbox MMIO in
this boot. Ring decoding cannot be validated until this lower transport gate
is crossed.

The next controlled experiment is the same known-good boot with only
`DARWIN_RTKIT_ANNOUNCE=5` added. Success requires real guest responses in the
boot log, not the emulator's outbound HELLO alone.

## Reference correction found during audit

Asahi Linux's current `drivers/gpu/drm/apple/afk.c` defines AFK
`RBEP_START_ACK` as `0x86`. The current emulator source defines it as `0xa4`.
No change is being claimed yet: the directionality and the actual Golden Gate
guest traffic must be captured first. This mismatch is a concrete item to test
once the guest answers RTKit HELLO.

## 2026-09-16, later — Codex's device-tree fix and its usage-limit handoff

Codex (working from `CODEX_HANDOFF.md` after Claude hit its own usage limit)
found the actual reason the guest never drove the DCP mailbox at all: the
Mac14,3 device tree used for the M2 firmware set was built by
`darwin-vm-m2/dt_fixup.py`, which strips the `compatible` property from every
device-tree node not in a hardcoded `SUPPORTED_DRIVERS` allowlist — including
`arm-io/dcp`. With no `compatible` string, XNU's IOKit can never match a
driver to that node, so the DCP device object never gets created in the
IORegistry in the first place; RTKit's `apple_rtkit_boot()` also turns out to
only fire on a guest `CPU_CONTROL RUN` write or a `DARWIN_RTKIT_ANNOUNCE=<s>`
synthetic-HELLO env var, neither of which the documented launch script sets.

Codex's fix: ported `EXTRA_NODES` allowlist support (already present in
`ios27-cl4-secure-world/scripts/dt_fixup.py` but missing from the local copy)
into `darwin-vm-m2/dt_fixup.py`, then used `ipsw img4 im4p extract` to pull
the *raw, unmutated* `DeviceTree.j473ap.im4p` from
`darwin-vm-m2/ipsw_db/26A428__MacOS/` and re-ran `dt_fixup.py` with
`EXTRA_NODES='arm-io/dcp;arm-io/dcp/iop-dcp-nub'` to produce a new tree that
keeps DCP's `compatible` property intact (`dtree.mac14_3.dcp`, copied to the
T480s as `firmware/dtree.dcp`). Booting with this tree plus
`DARWIN_RTKIT_ANNOUNCE=5` got further than before — the RTKit mailbox now
self-announces (`[rtkit:dcp] boot -> HELLO(min=11,max=12)`) — but Codex hit
its 5-hour usage limit mid-experiment, right as a *new* error appeared
(`debug_log_init: Error!! gPanicBase is still not initialized`), without
confirming whether the underlying `Couldn't alloc class "AFKResource"` error
was actually resolved.

Full raw transcript of Codex's session: `C:\Users\Raahim
Syed\Downloads\claudeshandofffrommebecausecodexhititslimittoo.txt`.

## 2026-09-16, later still — Claude verifies and corrects Codex's open question

Picked this up directly (Codex's own handoff exhausted its limit before
confirming anything). Findings, all directly verified against
`/tmp/cl4_phase3_dcpnode.log` on the T480s (the exact boot Codex left running,
PID 27541, using `firmware/dtree.dcp` + `DARWIN_RTKIT_ANNOUNCE=5`):

- **`debug_log_init: Error!! gPanicBase is still not initialized` is a red
  herring.** It fires at the same two points (SPTM logging setup, TXM logging
  setup) in *every* boot, including the pre-dtree-change known-good boot from
  earlier today. It's pre-kernel iBoot-stage noise, unrelated to the DCP work
  and not a regression Codex's change introduced. Don't chase it.
- **The DCP node fix was necessary but not sufficient.** `Couldn't alloc class
  "AFKResource"` still fires exactly 3 times in this boot, at the same three
  points as the pre-fix boot (during `nfs_kext_start`, during the `pptp` kext
  load attempt, and right before `load_init_program` hands off to launchd).
  These are generic kext-bootstrap checkpoints, not points where IOKit is
  trying to match a driver against a specific device-tree node — so this
  isn't a device-tree/compatible-string problem at all.
- **New root-cause lead**: `com.apple.driver.AppleFirmwareKit` — confirmed via
  `strings firmware/bootkc | grep -B8 '<key>AFKResource</key>'` to be the kext
  that literally defines the `AFKResource` IOKit class — never once appears
  in the boot log as `load succeeded` or via any kext-start message, unlike
  kexts that genuinely do load (e.g. `com.apple.AppleFSCompressionTypeZlib
  load succeeded`). The kernelcache's prelink personality plist does list
  AppleFirmwareKit (and AppleDCP) among its 3390 driver personalities, but
  personality-plist presence only proves the *metadata* is there, not that
  the kext's executable code is actually loaded/started. `Couldn't alloc
  class` is exactly what `OSMetaClass::allocClassWithName()` prints on a
  lookup failure — i.e., nothing ever ran that kext's load-time metaclass
  registration. Modern macOS boot splits a minimal always-loaded BootKC from
  a much larger SystemKC (and optionally an AuxKC); it's plausible this
  minimal custom ramdisk boot is only ever loading a BootKC-equivalent slice
  of the kernelcache, and AppleFirmwareKit's real code lives in a
  SystemKC/AuxKC slice that darwin-vm's firmware-extraction tooling never
  pulled in.
- **Attempted, inconclusive**: tried to confirm this directly by relaunching
  the boot inside a `screen` session (`screen -dmS cl4boot ...`, `tmux` isn't
  installed on the T480s) with `-serial stdio` (not `mon:stdio`, to avoid
  colliding with QEMU's own Ctrl-A monitor-toggle escape) so a live guest
  shell could be reattached and `kextstat`/`kmutil showloaded` run directly.
  The boot reaches the same idle `bash-3.2#` prompt reliably, but `screen -X
  stuff`/`screen -X hardcopy` issued from one-shot non-interactive SSH calls
  never visibly reached the guest's pty (hardcopy dumped 0 bytes every time,
  even combining stuff+hardcopy in a single SSH invocation). This looks like
  a screen/session-attachment limitation of scripting `-X` commands without a
  real persistent attached terminal, not a QEMU or guest-side problem — a
  future session should either keep one real interactive SSH session
  attached to `screen -r cl4boot` throughout, or find another way to drive
  the guest shell programmatically (e.g. a raw socket to the serial chardev
  instead of `screen`).

### Next step for whoever picks this up

The static evidence (AppleFirmwareKit's personality present but never
"load succeeded") is solid enough to act on without waiting for the
interactive confirmation above. Two candidate fixes, either worth trying:

1. Check whether the M2/26A428 IPSW's restore chain has a separate
   SystemKC/AuxKC file that was never extracted — look in
   `darwin-vm-m2/ipsw_db/26A428__MacOS/` for anything named
   `*SystemKernelExtensions*`, `*KernelCollection*`, `*AuxKC*`, or
   `*kernelmanagement*`, and `ipsw img4 im4p info` each candidate to see if
   any of them is a second kernel collection that needs to be handed to QEMU
   alongside `-bootkc`.
2. If no separate collection exists in the IPSW, try hand-building one:
   `kmutil create`/`kmutil install -n boot --extra-kext <path-to-a-real-
   AppleFirmwareKit-binary-pulled-from-ramdisk.dmg>` to produce a bootkc that
   actually links AppleFirmwareKit's code rather than only its personality
   metadata.

**Both of the above turned out to be unnecessary — see below, this was
solved directly.**

## 2026-09-16, late — root cause fully found and fixed; new (harder) wall found

Went back to basics with `ipsw macho info -z firmware/bootkc` (list every
embedded fileset entry) and `ipsw kernel kexts -j firmware/bootkc` (structured
JSON dump of every kext's Info.plist, including `io_kit_personalities`). This
settled the SystemKC/AuxKC question definitively:

- `firmware/bootkc` is a genuine `MH_FILESET` kernelcache — Apple's real,
  modern, unified single-file kernelcache architecture — with 349 embedded
  kexts, including `com.apple.driver.AppleFirmwareKit`, `AppleDCP`, and
  `RTBuddy`. **There is no missing SystemKC/AuxKC.** The code for all three
  really is present in `firmware/bootkc`.
- Rebuilt one boot with `-args "... kextlog=0xfff"` (the standard XNU verbose
  kext-loading boot-arg) to get real load/link tracing instead of guessing
  from silence. Result: `AppleFirmwareKit` and `RTBuddy` **both fully load and
  start** (`Kext com.apple.driver.AppleFirmwareKit is now started.`), each
  registering dozens of real OSMetaClasses. But `AFKResource` — the specific
  class the "Couldn't alloc class" error names — is conspicuously **absent**
  from AppleFirmwareKit's own registered-class list, even though a
  similarly-named sibling (`AFKSharedMemoryResource`) registers fine. This
  ruled out "kext not loaded" as the cause too.
- The real answer came from checking `AFKResource`'s actual IOKit personality
  in the JSON dump: `IOProviderClass: "IOResources"`, `IOResourceMatch:
  "IOBSD"` — a completely generic, always-available gate with nothing to do
  with DCP hardware. Confirmed other kexts using the exact same generic gate
  (`com.apple.AppleFSCompressionTypeZlib`) DO succeed in the same boot, so the
  gate itself isn't blocked. This means `AFKResource`'s constructor never runs
  not because its own gate is blocked, but because **whatever kext calls
  `OSMetaClass::allocClassWithName("AFKResource")` by name does so before
  AppleFirmwareKit's own registration completes** — a startup-ordering
  symptom, not the disease. The actual disease is upstream: the real
  `AppleDCPExpert` IOKit personality (`IOProviderClass: AppleARMIODevice`,
  `IONameMatch: "dcp-expert-v1"`) that's supposed to anchor the whole DCP
  driver stack was never matching anything, because dt_fixup.py's default
  allowlist strips `compatible` from `arm-io/dcp0-expert` — a **separate
  sibling node** from `arm-io/dcp` that Codex's `EXTRA_NODES` fix never
  covered. Confirmed directly against the pristine, unmutated device tree
  (freshly re-extracted from the IPSW's `DeviceTree.j473ap.im4p` via `ipsw
  img4 im4p extract`, parsed with `dt_fixup.py`'s own `ADTNode`/`decode_node`)
  that Apple really does ship `arm-io/dcp0-expert` with
  `compatible = "dcp-expert-v1"` — an exact match for AppleDCPExpert's
  personality. `dt_fixup.py`'s `IONameMatch`-based node name (`dcp0-expert`,
  the literal `name` property) is a red herring; what actually has to survive
  is the `compatible` string, which is what real Apple ADT-based IOKit
  matching uses even for `IONameMatch`-declared personalities.

**Fix applied**: regenerated the device tree with
`EXTRA_NODES='arm-io/dcp0-expert;arm-io/dcp;arm-io/dcp/iop-dcp-nub;arm-io/dart-dcp;arm-io/dart-dcp/mapper-dcp'`
(the DART/mapper nodes included because `AppleDCPExpert`'s driver chain also
depends on a working memory-mapper for the DCP's DMA). One nasty gotcha hit
along the way: invoking `dt_fixup.py` as a subprocess from Windows/git-bash
with `EXTRA_NODES=... python3 dt_fixup.py ...` silently failed to pass the
env var through (produced a tree with **zero** nodes preserved, not even the
ones that worked before) — the fix that actually worked was setting
`os.environ['EXTRA_NODES']` inside a Python process *before* importing
`dt_fixup` (since `KEEP_NODES` is computed at module-import time from
`os.environ`), then calling `decode_node`/`fixup`/`encode_node` directly
in-process rather than shelling out. Worth remembering if scripting this
again from Windows.

**Bisection results** (each tested by booting on the T480s and checking for
`bash-3.2#` + CPU activity):

| EXTRA_NODES tested | Result |
|---|---|
| `arm-io/dcp;arm-io/dcp/iop-dcp-nub` (Codex's original) | Boots fine, `AFKResource` still fails 3x (no DCP progress) |
| + `arm-io/dcp0-expert` only | **Boots fine**, `AFKResource` still fails 3x (necessary but not sufficient alone) |
| + `arm-io/dcp0-expert` + `arm-io/dart-dcp` (no mapper) | **Hangs** — guest never produces a single log line past QEMU's own device-attach printfs |
| + `arm-io/dart-dcp` alone (no dcp0-expert) | **Hangs**, identical symptom |
| Full 5-node set (+ `mapper-dcp`) | **Hangs**, identical symptom, with or without `DARWIN_DART=1` |

**The hang is caused by `arm-io/dart-dcp`'s `compatible` property becoming
visible, full stop** — independent of `dcp0-expert`, independent of
`mapper-dcp`, and independent of whether QEMU's own `DARWIN_DART=1` DART
register emulation is enabled or not (tried both; identical hang either way).
That last point rules out "the guest's real AppleDART kext driver spins
because our emulated DART registers are incomplete" (the working theory while
mid-investigation, based on a `darwin.c` comment: *"Without \[DART emulation\]
the driver spins during bring-up and the guest never boots"*) — because
providing the DART emulation made no difference at all.

**Confirmed via `lldb -p <pid> -o 'bt all'` attached to the hung process**:
this is not a QEMU machine-init hang, and not an XNU-kernel-level spin either.
The CPU thread (`CPU 0/TCG`) is parked in `qemu_process_cpu_events` /
`qemu_cond_wait_impl` (`cpus.c:474`) — QEMU's normal, correct handling of a
guest **WFI** (Wait-For-Interrupt) instruction. The guest CPU genuinely
started executing and then legitimately halted waiting for an interrupt that
never arrives. Critically, this happens **before a single guest-generated log
line appears** — none of the SPTM/TXM firmware's own extensive logging
(`TXM [Log]: ...` etc., which shows up within the first ~20 lines of every
known-good boot) ever prints. That places the hang inside SPTM/TXM's own
firmware blobs (`firmware/sptm`/`firmware/txm`, opaque signed binaries
extracted from the IPSW, not something this project's own C source
controls), before their own boot-logging subsystem even initializes — i.e.
*before* XNU, before IOKit, before any of the driver-matching work above ever
gets a chance to run.

Corroborating evidence this is an SPTM/secure-firmware-level DART/IOMMU
concern specifically: `dt_fixup.py`'s own `fixup_sptm()` function (called
unconditionally on every device tree, not just ours) includes
`d['arm-io'].remove_child('sgx')` with the comment "Skip the iommu init
stuff" — i.e. the project's own original author already found that leaving
certain IOMMU-related device-tree nodes visible confuses SPTM's early secure
boot sequence, and preemptively strips at least one such node (`sgx`) for
exactly this reason. `dart-dcp` was never on that pre-existing strip list
because it was never visible before (compatible-stripped by the default
allowlist) — restoring it exposes the same class of problem for a different
node.

### What this means going forward

Getting real DCP/IOMFB matching working (needed for anything beyond a text
console) genuinely requires `arm-io/dart-dcp`'s `compatible` to be visible —
`AppleDCPExpert`'s driver chain depends on it, confirmed by the fact that
`dcp0-expert` alone isn't sufficient (`AFKResource` keeps failing without the
DART also present). But exposing it hangs SPTM before the kernel even starts,
in a signed, opaque firmware binary this project doesn't control the source
of. This is a materially harder problem than a device-tree fix — it likely
requires one of:

1. Reverse-engineering what SPTM's DART/IOMMU-related boot sequence actually
   expects from a real T8110 DART's registers (beyond what
   `create_dart()`/`DARWIN_DART=1` currently emulates) and extending
   `create_dart()`'s register model to satisfy it — plausible but needs real
   SPTM disassembly/tracing work (`ipsw macho disass` on `firmware/sptm`, or
   QEMU's own `-d unimp,guest_errors` trace flags during the hang to catch an
   unanswered register read/write SPTM is blocked on).
2. Finding whether SPTM has its own opt-out mechanism (an `EXTRA_NODES`-style
   allowlist, a boot-arg, or a property SPTM specifically checks for) to skip
   IOMMU lockdown for a *specific* DART instance rather than needing it fully
   functional — check `dt_fixup.py`'s `fixup_sptm()` for hints, and consider
   whether other properties on `dart-dcp` (not just `compatible`) are what
   SPTM keys off rather than the compatible string itself.
3. Accept this as the real ceiling for now: keep `dcp0-expert`'s compatible
   restored (safe, necessary) but leave `dart-dcp` stripped (safe, boots), and
   redirect effort toward the `dcp_console_feed()` text-console path (already
   working, real pixels on screen) as the practical deliverable, treating full
   IOMFB/DCP matching as a documented, well-understood-but-unsolved stretch
   goal rather than a near-term blocker.

### Current known-good state on the T480s

`firmware/dtree.dcp4` = the safe, bisected device tree
(`EXTRA_NODES='arm-io/dcp0-expert;arm-io/dcp;arm-io/dcp/iop-dcp-nub'`, no DART
nodes). Boots cleanly to `bash-3.2#` with `DARWIN_FB=1 DARWIN_RTKIT=1` (no
`DARWIN_RTKIT_ANNOUNCE` needed — that env var's only purpose was working
around the DCP/RTBuddy chain never matching at all, which is now understood
precisely rather than worked around). This is the tree to build on going
forward — do not reuse `dtree.dcp`/`dtree.dcp2`/`dtree.dcp3`/`dtree.dcp5`/
`dtree.dcp6` (all either incomplete or the hanging DART-inclusive versions).
A stable boot using this tree is running in the background on the T480s as of
this writing (`/tmp/cl4_stable_baseline.log`).

## 2026-09-16, later still — option 1 tested and ruled out; two real bugs found and fixed along the way

Tested option 1 above directly rather than leaving it as a guess. Two
genuinely useful things came out of this even though the core hang is still
unsolved:

**`-d unimp,guest_errors` during the hang produced zero output.** The guest
CPU isn't touching any unimplemented or invalid MMIO while hung — whatever
it's doing, it's reading/writing registers QEMU already models successfully.
This rules out "SPTM pokes some DART register we never implemented and gets
garbage back" as the mechanism.

**Attached `lldb -p <pid> -o 'bt all'` to the live hung process** (confirmed
safe/reversible — just inspects, `detach` afterward, doesn't kill anything).
This is the single most useful diagnostic move this session: it directly
answered "is this a QEMU hang or a guest hang" with certainty instead of
inference. Backtrace showed the `CPU 0/TCG` thread legitimately parked in
`qemu_process_cpu_events`/`qemu_cond_wait_impl` (`cpus.c:474`) — QEMU's normal
WFI (Wait-For-Interrupt) handling. Confirms: machine-init already finished,
the CPU thread exists and executed real guest code, and is now correctly
waiting for an interrupt that never comes. Not a QEMU deadlock, not corrupted
state — a real "guest asked to wait for an IRQ, and we never deliver one."

**Found and fixed a real, general bug this surfaced**: `init_darts()`
(`hw/arm/darwin.c`) already had code to look up each DART node's
`interrupts` property and wire it to `aic_irq_line()`, but the *actual*
result was always `NULL` — not because of anything DART-specific, but because
by default (no `DARWIN_AIC=1`) the machine only calls the stub `init_aic()`,
never `init_aic_real()` — and only `init_aic_real()` sets the global `g_aic`
that `aic_irq_line()` reads (`hw/arm/darwin.c:519`:
`if (!g_aic || hwirq >= g_aic->nr_irqs) return NULL;`). So **`aic_irq_line()`
silently returns NULL for every caller, project-wide, unless `DARWIN_AIC=1`
is explicitly set** — including inside `init_rtkit_dcp()`'s own identical
lookup for the DCP mailbox's IRQ, which has been silently getting a NULL IRQ
line this entire project (it just doesn't matter for DCP since nothing yet
strictly depends on that IRQ actually firing). Extended `create_dart()`/
`DartState` to accept and store this IRQ line, and made `dart_write()` pulse
it on every register write (`qemu_irq_pulse`) — a real, working improvement:
confirmed via `-d unimp` that with `DARWIN_AIC=1 DARWIN_DART=1`, `aic_irq_line`
now returns a real non-NULL line (`irq wired` now appears in the boot log for
both `dart-disp0` and `dart-dcp`) and the IRQ genuinely pulses on writes.

**Tested with the real IRQ working end-to-end (`DARWIN_AIC=1 DARWIN_DART=1`,
IRQ pulsing on every DART register write) — the hang was byte-for-byte
identical.** Same last log line, same CPU state, no forward progress at all.
This is a clean, high-confidence negative result: **the hang is not "the
guest/SPTM is WFI-waiting for the DART's interrupt."** Whatever it's actually
waiting for, an IRQ from this specific device doesn't satisfy it.

This leaves the strongest remaining explanation as the security/validation
one already noted above: SPTM (or TXM) most likely performs its own internal
sanity check of the `arm-io` device-tree topology against what it expects for
this chip, independent of any interrupt or register protocol, and halts
(rather than panics or logs) on encountering a DART node it doesn't
recognize/trust — consistent with `dt_fixup.py`'s pre-existing, unprompted
`sgx`-node removal for "iommu init stuff." If true, no amount of QEMU-side
device emulation (registers, IRQs, timing) can fix this from our side; it
would require disassembling `firmware/sptm` itself
(`ipsw macho disass`/`ipsw kernel dwarf` might apply, though SPTM is not a
normal XNU kernelcache) to find and either satisfy or patch out whatever
check is failing — a substantially bigger undertaking than anything done in
this session, and arguably out of scope for "reasonable effort" given SPTM is
a signed, opaque Apple secure-firmware binary never intended to be
introspected this way.

**Recommendation: treat option 3 (above) as the actual plan.** Keep
`dtree.dcp4` (dcp0-expert restored, DART left stripped) as the stable base.
The `dcp_console_feed()` text-console path is real, working, and independent
of this DART/SPTM wall. If someone wants to keep pushing on full IOMFB/DCP
matching specifically, the next concrete, bounded step (not yet tried) would
be: boot with `DARWIN_DART=1` (DART emulated) but *without* restoring
`dart-dcp`'s `compatible` in the device tree — i.e. let QEMU model the
hardware, but keep the guest kernel's IOKit matching blind to it, and see
whether SPTM *itself* still finds and touches the DART's `reg`-addressed MMIO
region even without a `compatible` string (SPTM might key off `reg`/physical
address ranges from its own hardcoded expectations rather than the
device-tree `compatible` property at all, which would mean the current
`dcp0-expert`-only tree might already be silently exercising this exact SPTM
codepath without us realizing it — worth checking the `-d unimp,guest_errors`
trace against the *safe, working* boot too, as a sanity baseline, since we
never actually did that on a successful boot for comparison).

**Update: tried this too, same session.** Traced the safe, working
`dtree.dcp4` boot (`DARWIN_FB=1 DARWIN_RTKIT=1`, no DART) with
`-d unimp,guest_errors -D /tmp/cl4_safe_trace.log` all the way to `bash-3.2#`.
Result: only 2 lines total, both `Invalid tlbi page size granule 1` — a
pre-existing, harmless TCG instruction-decode warning unrelated to any
device, and **zero** DART-related entries. This rules out the "SPTM already
touches the DART via raw physical address, `compatible` is irrelevant"
alternative — confirms the DART only becomes relevant to SPTM/the guest at
all once its `compatible` string is visible, i.e. the hang really is
triggered by *revealing* the DART's identity, not by anything intrinsic to
its physical memory range. This is a clean, doubly-confirmed picture:
`compatible`-gated visibility is what matters, restoring it is what SPTM
reacts badly to, and the reaction is unrelated to interrupts or register
values. The SPTM-disassembly path (or accepting option 3) really are the only
two ways forward from here.

**Session state, final**: T480s is clean — no hung processes, only the
original always-running non-CL4 baseline (PID 17299, harmless, been running
since earlier in the day) plus a healthy `dtree.dcp4` boot
(`/tmp/cl4_final_verify.log`) confirmed reaching `bash-3.2#` on the rebuilt
binary that includes the (real, working, but not sufficient alone) DART IRQ
wiring fix. `hw/arm/darwin.c` on the T480s now has `create_dart()` accepting
and pulsing a real IRQ line — safe, additive, doesn't affect the default
(no-DART) boot path at all.
