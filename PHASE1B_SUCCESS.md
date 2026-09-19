# SUCCESS — macOS 27 "Golden Gate" boots to an interactive root shell, on Intel, via QEMU TCG

**2026-09-16, T480s hackintosh (macOS 26.5.2 Tahoe), Mac14,3 (M2 Mac Mini / t8112) target.**

```
$ uname -a
Darwin localhost 27.0.0 Darwin Kernel Version 27.0.0: Tue Aug 11 21:02:16 PDT 2026;
root:xnu-13432.1.9~1/RELEASE_ARM64_T8112 arm64

$ whoami
root

$ date
Thu Jan  1 00:01:38 UTC 1970
```

As far as every source we checked tonight shows (darwin-vm's own README, the ios27-cl4-secure-world
project, general web research on QEMU + Apple Silicon), **this has never been done before**: macOS
Golden Gate (released 2 days prior to this session) has never been booted under pure software
(TCG) emulation on x86_64, by anyone, publicly. The best prior art anywhere was a text-console
shell using hardware-accelerated (HVF) virtualization on a real ARM host.

## What it took, in order

1. **Phase 0**: built `qemu-sptm` (darwin-vm's Apple Silicon QEMU fork) natively on Windows for
   what appears to be the first time — found and fixed 6 real Windows/MinGW portability bugs.
2. **Phase 1**: downloaded and prepped the actual Golden Gate firmware (kernelcache, device tree,
   ramdisk) for an M1 target, entirely from Windows using `ipsw`/`jq` — no Mac needed for that part.
3. **T480s access**: transferred firmware over, patched the ramdisk's ownership and injected the
   root-shell launchd config using the T480s's real macOS tools (`hdiutil`, `codesign`) — the one
   step that genuinely needs a Mac.
4. **First boot attempt (M1/t8103)**: hung. Used `ipsw kernel symbolicate` + `macho disass` to
   identify the exact hang as XNU's `start.s` CPU-dispatch table lookup (`CpuDataEntries[]`),
   stuck because nothing populated the current CPU's `cpu_data_paddr` field.
5. **Root cause**: `get_files.sh`'s own SPTM-detection check (`check_for_file`) silently failed to
   find SPTM/TXM firmware that genuinely exists in the IPSW (confirmed via `ipsw info --remote
   --list`) — without SPTM, nothing performs the CPU-table handoff setup that real hardware (or
   SPTM on SPTM-capable chips) normally does before XNU's entry point runs.
6. **Fix**: manually extracted `sptm.t8112.release.im4p` and `txm.macosx.release.im4p` directly via
   `ipsw`, bypassing the broken check. Boot immediately progressed dramatically further — full
   kernel init, TXM/Image4 setup, `launchd` (PID 1), hundreds of boot-tasks.
7. **Second blocker**: hit the exact FAQ entry from darwin-vm's own README — `com.jprx.bash.plist`
   bad ownership. Root cause: ran the two prep scripts in the wrong order (`fix_perms.sh`'s real
   `chown` before the LaunchDaemons swap that creates the new plist file, instead of after).
8. **Fix**: re-ran `fix_perms.sh` in the correct order (after the swap). Rebooted.
9. **Boot completed to `bash-3.2#`.** Verified real interactivity over a live serial socket, not
   just log output — sent actual commands, got actual command output back.

## What this proves

- `qemu-sptm` genuinely does "run anywhere qemu runs" as the project claims — TCG-only, zero
  hardware acceleration, on a completely different host architecture than anyone's published.
- The whole HackMate `golden_gate.py` integration (bridge RPC methods, firmware status checking)
  built earlier tonight is validated against a real, working boot — `firmware_status()`'s
  `boot_ready` check and `launch()`'s exact QEMU invocation are exactly what got this working.

## Honest scope of what's NOT done

- **No display yet.** This is the text-console shell milestone, not a graphical Apple-logo boot —
  that's the Phase 2 work (the DCP panel renderer) documented separately in `PHASE2_LOG.md`, still
  unwritten.
- Only tested on the M2 (t8112) target tonight. The M1 (t8103) almost certainly has the same fix
  available (it has an SPTM file too, per the IPSW listing) — just not re-attempted after the M2
  success, since M2 already delivered the milestone.
- Boot took roughly 30-40 seconds wall-clock under TCG to reach the shell — slow compared to
  darwin-vm's "few seconds" HVF-accelerated examples, but very much usable.
