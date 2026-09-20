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

## Immediate next step

Watching the same run for `WindowServer` to get a PID. If opendirectoryd
staying alive was the actual blocker (very plausible -- loginwindow needs
working directory services to authenticate/look up the console user before
it can proceed to connect to WindowServer), this could be the run that
finally gets a WindowServer PID for the first time. If it doesn't happen
within a few more minutes, the next thing to check is exactly what
loginwindow is waiting on post-`running` (same technique as before: full
backtrace + kext-name list from any crash, not the generic caller field;
or just keep reading the live log for what loginwindow tries to connect to
next).

## Housekeeping note

The known-good real-target device tree is now
`dtree.dcp8.bigdram2.dcpbyte.nubx` (Codex's refinement of the Phase 10
`.dcpbyte` fix -- defangs `iop-nub,rtbuddy-v2` -> `xop-nub,rtbuddy-v2` for
the DCP child nub specifically, on top of the original `dcp` node
`compatible` byte patch). Use this one going forward, not the plain
`.dcpbyte` from Phase 10.
