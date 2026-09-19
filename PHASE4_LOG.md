# Phase 4: SPTM root-cause fix, real driver matching achieved, and the path to a real desktop

## 2026-09-16, late night — the SPTM hang: root cause found and fixed for real

Continuing from PHASE3_LOG.md's open question (does `arm-io/dart-dcp`'s
`compatible` restoration hang SPTM itself, and why). Reverse-engineered
`firmware/sptm` directly rather than guessing further from black-box
behavior:

- `ipsw macho info` confirmed `firmware/sptm` is a real, mostly-unstripped
  arm64e Mach-O with a huge (~84KB) `__TEXT.__cstring` section containing
  full internal function names (`t8110dart_bootstrap_dart_instance_properties`,
  etc.) used by Apple's internal assert/panic macros — meaning it's fully
  traceable via string cross-references even without a real symbol table.
- Used `ipsw macho disass -x __TEXT_EXEC.__text` to dump the full
  disassembly (~101K lines) and grepped for these function names to locate
  the actual DART bootstrap validation code. This confirmed a huge amount of
  validation logic (SID counts, vm-base/vm-size, APF/GAPF/PIOGW/SMMU
  sub-instance properties, etc.) — far more than `dt_fixup.py`'s
  `EXTRA_NODES` mechanism alone restores (it only preserves `compatible`,
  not the full property set — though the full property set turned out to
  already be intact on the pristine tree since `dt_fixup.py` never touches
  non-`compatible` properties).
- **The actual breakthrough came from live debugging, not static analysis.**
  Reproduced the hang, then used the QEMU HMP monitor (`info registers`) on
  the live paused CPU to read real register state — discovered `PSTATE`
  shows `EL2t` (the CPU is at Exception Level 2), and critically, the vector
  registers `Q00`–`Q03` contained a **partially-constructed string** — the
  CPU was caught mid-flight formatting a panic/log message. Decoded the raw
  register bytes and it matched, near-exactly, a string already extracted
  from `firmware/sptm`: **`"%s: dart %s:%s:%d: error %d getting dart-id"`**.
- Confirmed via direct device-tree inspection that `dart-id` is **not a
  property Apple's own pristine, unmutated device tree has** on
  `arm-io/dart-dcp`, `arm-io/dart-dcp/mapper-dcp`, or `arm-io/dcp0-expert` —
  it must normally be derived some other way that our synthetic
  QEMU/SPTM/XNU environment doesn't reproduce correctly.

**Fix**: inject a synthetic `dart-id = u32:0` property directly onto
`dart-dcp` and `mapper-dcp` after `dt_fixup.py`'s normal fixup pass (not
achievable via `EXTRA_NODES`, which only preserves existing properties —
this needed a small custom post-processing step using the same
`ADTNode`/`decode_node`/`encode_node` primitives). Result:
**the SPTM hang is completely gone.** Verified via multiple full boots to
`bash-3.2#` with the complete node set restored
(`dcp0-expert;dcp;dcp/iop-dcp-nub;dart-dcp;dart-dcp/mapper-dcp`) — the tree
that previously hung 100% of the time now boots cleanly every time.

New known-good device tree: `firmware/dtree.dcp7` on the T480s
(`~/goldengate/qemu-sptm-cl4-native/firmware/dtree.dcp7`). This supersedes
`dtree.dcp4` — it has the fuller node set AND the dart-id fix, and is the
one to build on going forward.

### Also fixed along the way (real, general bug, kept even though not sufficient alone)

`init_darts()` in `hw/arm/darwin.c` already looked up each DART's
`interrupts` device-tree property and called `aic_irq_line()`, but this
silently returned `NULL` for every caller project-wide unless
`DARWIN_AIC=1` was explicitly set (only `DARWIN_AIC=1` invokes
`init_aic_real()`, the version that actually sets the global `g_aic` state
`aic_irq_line()` reads; the default `init_aic()` stub never does). Extended
`create_dart()`/`DartState` to accept and store a real IRQ line, and made
`dart_write()` pulse it (`qemu_irq_pulse`) on every register write. Tested
in isolation (before finding the dart-id issue) by wiring a genuinely
working IRQ end-to-end (`DARWIN_AIC=1`, confirmed via boot-log `(irq wired)`
annotations) — this alone did **not** fix the SPTM hang (ruling out "missing
interrupt delivery" as the cause before finding the real one), but it's a
real, harmless, additive improvement worth keeping for whenever real DART
interrupt-driven behavior is needed later.

## Real driver matching confirmed — RTBuddy(DCP) actually starts

With the dart-id fix in place, booted with a **safe, targeted**
`IOKitDebug=0x7f` (the low-numbered kIOLog* bits: attach/probe/start/
register/match/config — NOT `0xffffffff`, which caused a genuine CPU-bound
busy-spin hang, likely from expensive leak-tracking/other high-numbered
debug bits not meant for normal use) to get real IOKit matching traces
without needing fragile interactive shell access.

Result: **`RTBuddy(DCP): start(<ptr>) - (Aug 30 2026@18:51:59)`** appears in
the boot log — a real, driver-authored `IOLog` call, definitive proof that
`AppleDCPExpert`'s matching against our `dcp0-expert` node succeeded, and
that the RTBuddy(DCP) driver instance actually starts. This is the deepest
point reached in this entire project — actual Apple driver code for the
display coprocessor is running and initializing against our emulated
hardware.

Immediately after, `Couldn't alloc class "AFKFirmwareService"` appears —
but its personality (`DCPFirmwareServiceEXT`) matches
`IOPropertyMatch: {"role": "DCPEXT"}`, which corresponds to the *external*
display expert node (`arm-io/dcpext-expert`/`dcpext`, a sibling we never
touched), not our primary internal panel path — likely irrelevant to what
we actually need. `AFKResource` also still fails, but cross-checked via two
independent methods (a) string search of `bootkc` finds `"AFKResource"` only
as plist metadata, never as a runtime cstring referenced by code, and (b)
`kextlog=0xfff` shows `AppleFirmwareKit`'s own module-start registering ~40
real classes but never `AFKResource`/`AFKFirmwareService`/
`AFKResourceUserClient` — strong evidence these specific classes' C++
implementations are simply not compiled into this exact (`26A428`, an early
Golden Gate seed build) kernelcache at all, independent of anything we
control. Likely a genuine, harmless Apple-side gap in this seed build, not
a real blocker — boot continues cleanly regardless every time.

Checked whether RTBuddy(DCP) proceeds to touch the actual mailbox hardware
given more wall-clock time (in case hardware bring-up is deferred) — waited
several minutes past reaching the shell prompt with no further guest-
initiated RTKit mailbox traffic (`CPU_CONTROL RUN` / `HELLO`) ever appearing.

## The real reason nothing further happens: there's no WindowServer to ask for it

Mounted `firmware/ramdisk.dmg` directly (`hdiutil attach` + `mount_apfs`) and
inspected its actual filesystem contents. Confirmed: **this ramdisk has no
`WindowServer`, `loginwindow`, `SystemUIServer`, or any graphical UI
component at all** — `/System/Library/CoreServices` contains only
`ReportCrash` and `SystemVersion.plist`. This is Apple's real "restored"
(external-restore-agent) personality ramdisk, used for erasing/restoring a
target Mac's disk from another device over USB/network — a purely headless
backend service, not an installer or recovery UI, even in its original,
unpatched form.

Checked whether this project's own `patch_ramdisk()` step (in `get_files.sh`)
destroyed a real UI that would otherwise be there: it renames the original
`LaunchDaemons` to `LaunchDaemons.old` (preserved, not deleted) before
installing just the debug-shell plist. Inspected `LaunchDaemons.old` inside
the mounted ramdisk directly — it only contains genuinely headless daemons
(`com.apple.restored_external`, `com.apple.kernelmanagerd`,
`com.apple.diskimagesiod`, `com.apple.syslogd`, etc.) — **no UI daemon was
ever there to begin with.** This rules out a fast "just don't patch the
ramdisk" shortcut. There is no path to real graphical output from this
ramdisk, however perfectly the DCP/IOMFB kernel driver chain ends up
working, because nothing in userspace would ever open a display connection.

**This means RTBuddy(DCP) successfully starting, while a huge and real
milestone, cannot by itself produce visible output.** Getting an actual
macOS desktop requires an actual macOS **System Volume** (the real OS
install, with WindowServer/loginwindow/Dock/Finder present) booting as root,
not this restore ramdisk.

## In progress: acquiring the real system volume

The source IPSW (`UniversalMac_27.0_26A428_Restore.ipsw`) contains
`043-70867-635.dmg.aea` (11GB), confirmed via the IPSW's own
`Restore.plist` → `SystemRestoreImageFileSystems` key to be tagged
`"APFS"` — i.e. very likely the actual system volume image, sealed
(`Firmware/043-70867-635.dmg.root_hash` + `.trustcache` present alongside
it, consistent with a Signed System Volume). It's AEA-encrypted, but `ipsw
fw aea -k` fetched a working decryption key successfully and independently
of the full download (`base64:iUC7LXadMs+MFgcAVrgG51JfRrNdS7S33BEiAINxnyc=`,
saved to `~/goldengate/system_volume/aea_key.txt` on the T480s) — confirming
this is a generic OS-distribution key, not device-locked/personalized, so
decryption is fully viable once downloaded.

Download started in the background on the T480s:
`~/goldengate/system_volume/26A428__MacOS/043-70867-635.dmg.aea`
(`nohup ipsw extract --remote <ipsw-url> --output . --flat --pattern
'043-70867-635.dmg.aea' -j`, logged to `/tmp/sysvol_download.log`). At
current observed rate (~40MB/30s) this will take roughly 2+ hours to
complete. **Do not re-trigger this download** — check whether the file
already exists and is complete (compare against the 11GB IPSW-listed size)
before starting a new one.

### Next steps once the download completes

1. Decrypt: `ipsw fw aea -o <output_dir> -b
   'base64:iUC7LXadMs+MFgcAVrgG51JfRrNdS7S33BEiAINxnyc='
   ~/goldengate/system_volume/26A428__MacOS/043-70867-635.dmg.aea` (verify
   exact flag syntax with `ipsw fw aea --help` first — this session
   confirmed the key-fetch flag works but did not verify the full
   decrypt-and-extract invocation end-to-end since the download wasn't
   complete yet).
2. Mount/inspect the decrypted DMG to confirm it's really the system volume
   (look for `/System/Library/CoreServices/WindowServer`,
   `/System/Library/CoreServices/loginwindow.app`, etc.) before investing
   further effort.
3. **The hard unsolved part**: getting XNU to actually boot with this as
   root instead of the small ramdisk. The current boot uses `rd=md0` +
   QEMU's own `-ramdisk` flag, which loads the *entire* image into guest RAM
   as a block device — fine for the current ~373MB ramdisk, but an 11GB+
   system volume almost certainly won't fit as a full in-memory copy
   alongside everything else in an 8GB (or even considerably larger) guest.
   `hw/arm/darwin.c` already has **partial, real** ANS/NVMe emulation
   scaffolding (`ans_nvme_read`/`ans_nvme_write`, handling `BOOT_STATUS` and
   doorbell registers) reverse-engineered from Linux's
   `drivers/nvme/host/apple.c` — but it's register-stub-level only, with no
   real submission/completion-queue command processing or DMA data
   transfer. Making a real block device work end-to-end (submission queue
   parsing, PRP/SGL data transfer to/from a real backing file, completion
   queue posting) is a substantial, from-scratch emulation task — likely the
   single biggest remaining piece of engineering work in this entire
   project, bigger than anything done so far this session.
4. Separately: a real macOS System Volume is very likely **sealed** (Signed
   System Volume / cryptex), meaning XNU/SPTM will expect to verify a
   Merkle-tree root hash against the mounted volume before trusting it as
   root — exactly the kind of validation that caused the `dart-id` hang
   earlier in this session. Expect a similar reverse-engineering cycle
   (string search bootkc/sptm for SSV/seal-related panic strings, live
   register inspection at any hang) to be needed here too if it doesn't
   just work.
5. Even if the volume mounts and boots, WindowServer itself still needs the
   **AGX GPU** to actually composite/render anything beyond very early boot
   progress UI (which might use a simpler DCP-direct raster path — worth
   checking whether early boot progress bars are DCP-composited rather than
   GPU-rendered, since that path might already be reachable with what we
   have working right now).

## Session summary / where things stand

This session took the project from "Codex found a real fix that was
incomplete and ran out of usage mid-experiment" to: the actual root cause of
the DCP/DART matching failure precisely identified and fixed (the `dart-id`
property), a hang that was blocking ALL forward progress completely
resolved, and **genuine confirmed evidence of real Apple driver code
(RTBuddy(DCP)) successfully starting and matching against our emulated
hardware** — the deepest point reached in this entire project. The reason
nothing is visible on screen isn't a remaining driver-matching bug at all;
it's that the ramdisk environment used so far was never meant to have a
display client running. The path forward is well-understood and
technically characterized (system volume + real NVMe block emulation +
likely SSV verification), even though it represents substantial further
engineering work, not a quick fix.
