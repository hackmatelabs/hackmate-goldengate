# Phase 11: opendirectoryd crash loop SOLVED — most stable boot in project history

## Context

Picking up from `CODEX_HANDOFF3.md`. Codex had already identified the real
reason `/private/var` was invisible to the guest despite the Data volume
existing: the guest boot log said `md0s1 Volume Macintosh HD is not in a
volume group` -- macOS mounts the System volume as root but never
automatically stitches in the Data volume the way it would on a real Mac
(where System+Data pairing is driven by a shared volume-group UUID set up
by the installer, which our raw `diskutil apfs addVolume` never
established for these two volumes).

Codex's fix, already fully built and left in place: wrap
`/usr/libexec/opendirectoryd`'s own LaunchDaemon so every time it's about
to start, it first explicitly `mount_apfs /dev/md0s2
/System/Volumes/Data`, then `exec`s the real daemon. Patched files (already
on the real target's system volume, no further action needed):

- `/System/Library/LaunchDaemons/com.apple.opendirectoryd.plist` --
  `ProgramArguments` changed from `/usr/libexec/opendirectoryd` to
  `/bin/bash /goldengate-od-wrapper.sh`.
- `/goldengate-od-wrapper.sh` -- mounts Data, logs diagnostic markers to
  `/dev/console`, then `exec /usr/libexec/opendirectoryd`.

## Result: this actually works

Booted with Codex's known-good command (`DARWIN_FB=1 DARWIN_RTKIT=1`, real
Cocoa display, `dtree.dcp8.bigdram2.dcpbyte.nubx`, plain
`bootkc.md0size.uidfix` -- no additional csr_check patch of any kind).

- `opendirectoryd` (running as wrapper pid 44) triggered a real DYLD
  shared-region unnest operation (`bash[44] triggered unnest of range
  0x1f6000000->0x1fa000000`), reached `running`/`INIT` state at
  `00:01:17`, and **never crashed or exited again** for the rest of the
  run. This is the first time in this entire project that opendirectoryd
  has not crash-looped.
- `loginwindow` (pid 75) also spawned cleanly via `ipc (mach)` and reached
  `running` state, same as the DCP-fix session, but now WITHOUT
  opendirectoryd crash-looping underneath it.
- **Zero panics, zero `VIOLATION_DOUBLE_NEST`, in 5+ minutes of runtime**
  (longer than every one of this project's DOUBLE_NEST-crash attempts, and
  stable rather than reset-looping).
- `WindowServer` still has not printed a "Successfully spawned" line as of
  this writing -- still watching a live run. This is the very next thing to
  confirm.

Note: the wrapper script's own `echo GOLDENGATE_OD_*` diagnostic markers do
NOT appear in the `-serial file:...` log, because the script explicitly
does `exec >/dev/console 2>&1` and with `DARWIN_FB=1` active, `/dev/console`
routes to the graphical framebuffer console (visible in the QEMU Cocoa
window), not the serial UART. Confirmed opendirectoryd's success
indirectly via launchd's own bootstrap log lines instead (no crash/exit
events for pid 44 after it reached `running`). If you need the wrapper's
own markers directly, either take a screenshot of the QEMU window at the
right moment, or change the wrapper to redirect to `/dev/ttys0`
(serial) instead of `/dev/console` for a boot config that doesn't need the
graphical console.

## Follow-up: WindowServer still didn't spawn

Let the run continue for 15+ minutes: `opendirectoryd` and `loginwindow`
both stayed alive and stable the entire time (huge win, see above), but
`WindowServer` never printed a "Successfully spawned" line. The run
eventually hit the same pre-existing, unrelated `TXM [Panic]: code
0x00000063` crash noted in PHASE10 (not a regression -- known, separate
wall).

**Why WindowServer doesn't launch, confirmed via the boot log**: right at
boot, repeated `Couldn't alloc class "AFKResource"` failures (lines
235/253/295/1264 in `/tmp/cl4_odwrap_serial.log`). This is exactly the
wall Codex already flagged in `CODEX_HANDOFF3.md`'s "Important graphics
reality check" section: with the `dcp` node defanged (necessary to avoid
`VIOLATION_DOUBLE_NEST`, see PHASE10), there is no real
IOFramebuffer-conforming display service in this boot at all --
`AFKFirmwareService`'s personality exists in the kernelcache but the
actual `AFKResource` class/support isn't available, so nothing can
allocate it. WindowServer's core requirement (at least one working
display service to attach to) is never satisfied, so it never proceeds to
actually launch, regardless of how healthy opendirectoryd/loginwindow are.

**This is not a new problem and not caused by anything in Phase 10/11** --
it's the trade-off of disabling DCP to survive the SPTM crash, and it was
explicitly anticipated. Fixing opendirectoryd got us all the way to this
wall for the first time; the graphics/AFK pipeline is now THE remaining
blocker for real Aqua.

## Next step for whoever picks this up

Investigate the actual display pipeline path now that everything below it
is stable:
1. Understand what `AFKResource`/`AFKFirmwareService` actually needs --
   is the class genuinely missing from this kernelcache build (would need
   a different bootkc image with fuller AFK/DCP kext support), or is it
   present but failing to instantiate because the `dcp` node it wants to
   bind to was intentionally defanged?
2. Consider whether a MIDDLE GROUND exists: keep the `dcp` node's
   `compatible` string defanged (to avoid the RTBuddy secure-route crash)
   but see if a different/simpler IOFramebuffer-conforming service could
   be registered separately (not going through the DCP mailbox at all) --
   possibly extending QEMU's own `DARWIN_FB=1` boot-framebuffer mechanism
   into something IOKit-visible as a real framebuffer service, rather than
   just a console text renderer.
3. This is squarely "the DCP/AFK display-pipeline wall" flagged as likely
   back in PHASE5_LOG, now finally reachable and worth real investigation
   time.

## Housekeeping note

The known-good real-target device tree is now
`dtree.dcp8.bigdram2.dcpbyte.nubx` (Codex's refinement of the Phase 10
`.dcpbyte` fix -- defangs `iop-nub,rtbuddy-v2` -> `xop-nub,rtbuddy-v2` for
the DCP child nub specifically, on top of the original `dcp` node
`compatible` byte patch). Use this one going forward, not the plain
`.dcpbyte` from Phase 10.
