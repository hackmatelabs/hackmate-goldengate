# Handoff: Golden Gate on Intel — read this first, then go

You are picking up an in-progress, multi-day project from another Claude
Code session running on the user's desktop. The user (raahimsyed) is now on
a road trip with their **ThinkPad T480s** (the actual target machine — this
laptop, the one you are running on) and wants this to keep moving without
them driving every step.

## The standing instruction — this is the most important thing in this file

The user has said, repeatedly and with escalating force, across this whole
project:

> "BRO JUST KEEP GOING TIL ITS ON MY SCREEN, THE USABLE DESKTOP ENVIRONMENT
> MACOS 27 ITSELF"

> "save to memory and go and dont stop til its finsihed, even massive stuff u
> find/bugs/fixes. jsut keep going. dont ask querstions, figure out stuff
> yourself. do not hand back that prompt til i see golden gate on the t480s
> screen"

> (earlier, when offered a fake/mockup desktop shortcut instead of the real
> thing) "no, we WILL AND ABSOLUTELY WILL NO MATTER HOW LONG IT TAKES WE
> WILL AND WILL MAKE MACOS GOLDEN GATE ITSELF RUN ON THIS."

**Treat this as a durable, standing instruction, not a one-off for a single
turn.** Concretely:
- The goal is the REAL macOS Golden Gate desktop, rendered by Apple's own
  WindowServer/Aqua, actually visible on the T480s's physical screen. Not a
  mockup, not a custom-drawn "looks like a desktop" screen, not a serial
  console shell claimed as a win.
- Work continuously through build/boot/debug cycles without pausing to ask
  the user how to proceed or report routine incremental status. Resolve
  ambiguity yourself.
- Only surface back to the user when there's a genuine milestone (a real
  wall broken through, pixels changed) or a truly unrecoverable blocker —
  not merely a hard/slow one.
- If you're running via `/loop` or similar autonomous scheduling on this
  machine, use it. If not, and the user asks you to just keep going, keep
  going across as many turns/tool calls as it takes.
- Document everything you find in this repo as you go (see "How to keep
  this repo updated" below) — the user explicitly wants even "massive
  stuff you find/bugs/fixes" saved, not just final results.

## What this project is

RAM (YouTuber, channelramble, 103K subs) challenged HackMate (the user's
open-source hackintosh tool) to run **macOS 27 "Golden Gate"** — Apple's
newest OS, Apple-Silicon-only, zero x86 code path — on Intel hardware. Since
there's no native path, this is full ARM64 CPU emulation: booting a real
Apple Silicon macOS build under **QEMU/TCG software emulation** (no HVF, no
real Apple Silicon anywhere) on the T480s's Intel CPU.

Nobody has ever gotten Apple Silicon macOS to show graphical output under
QEMU/emulation on any hardware. The furthest public prior art (the
`darwin-vm`/`qemu-sptm` line of work this project builds on) tops out at a
**text-only serial console shell**, and even that was on real ARM hosts
with hardware acceleration, not x86 TCG. This project has already gone
further than any known public work.

## Where the real, authoritative project lives

**This repo (`hackmate-goldengate`) is documentation, logs, device-tree
snapshots, and source-code checkpoints — it is NOT the live build.** The
actual working QEMU fork, kernelcache, firmware, and build toolchain live
**on this T480s itself**, over SSH-able localhost (you're running on it):

```
~/goldengate/qemu-sptm-cl4-native/     <- the actual QEMU fork, build/qemu-system-aarch64
~/goldengate/qemu-sptm-cl4-native/firmware/   <- bootkc, dtree.*, sptm, txm, ramdisk.dmg
~/goldengate/system_volume/            <- the real decrypted 14.19GB macOS system volume
```

If you're running as Claude Code directly on the T480s (macOS), you have
local shell access to all of this already — no SSH wrapper needed, that was
only how the desktop-side Claude reached this machine remotely. Just use
Bash directly.

Build command:
```
cd ~/goldengate/qemu-sptm-cl4-native/build && \
  export PATH=/usr/local/homebrew/bin:/usr/local/bin:$HOME/Library/Python/3.9/bin:$PATH && \
  ninja -j2
```

## Current state as of hand-off (2026-09-18, end of desktop session)

Read `PHASE5_LOG.md` in this repo fully — it has the complete, evidence-backed
history. Short version, most-recent-first:

### The live thread: `-icount` fix for a root-caused timer bug (UNVERIFIED — start here)

The last several hours of investigation chased why the 4 candidate ANS
storage controllers (`AppleANS2CGv2Controller`, `AppleANS2NVMeController`,
`AppleANS3CGv2Controller`, `AppleANS3NVMeController`) never reach `start()`
after `probe()` — boot would freeze indefinitely right after all 4 probe
score lines print. Extensive gdbstub work (breakpoints, single-stepping,
and finally **live PC sampling via the QMP/HMP monitor socket** — cheap,
doesn't pause the VM) found the *actual* root cause, and it's **not**
ANS/storage-specific at all:

**A seqlock-style timer-consistency retry loop (reading `CNTVCTSS_EL0` +
re-checking a memory-shadowed timestamp) never converges under TCG,
because QEMU's `QEMU_CLOCK_VIRTUAL` (which drives the emulated counter,
see `target/arm/helper.c`'s `gt_get_countervalue()`) ticks based on real
host wall-clock time, not guest instruction count.** TCG's huge
per-instruction slowdown means the counter always advances between the two
back-to-back reads this retry loop does, so it spins forever — something
that would converge in 1-2 iterations on real hardware. Full technical
detail, the exact disassembly, and the exact live-PC-sampling method are
in `PHASE5_LOG.md` under "ROOT CAUSE FOUND: an infinite seqlock-retry
spin reading `CNTVCTSS_EL0`".

**The fix being tested when the desktop session lost contact with this
laptop**: QEMU's standard answer to this class of problem is `-icount`
mode, which decouples `QEMU_CLOCK_VIRTUAL` from real host time and ties it
to executed instruction count instead — so a tight guest retry loop sees
the same tiny amount of *virtual* time pass regardless of how slow TCG
actually is. A test was launched with:

```bash
cd ~/goldengate/qemu-sptm-cl4-native
DARWIN_FB=1 DARWIN_RTKIT=1 DARWIN_DART=1 DARWIN_AIC=1 DARWIN_RTKIT_ANS=1 \
  build/qemu-system-aarch64 -icount shift=auto \
  -M darwin -bootkc firmware/bootkc -dtree firmware/dtree.dcp8 \
  -tc firmware/ramdisk.tc -ramdisk /tmp/empty_ramdisk2.dmg \
  -sptm firmware/sptm -txm firmware/txm \
  -args "serial=3 -v -noprogress wdt=-1 wlan-olyhal-abort" \
  -serial mon:stdio -display none \
  -monitor unix:/tmp/cl4_icount.sock,server,nowait -m 8G
```

(`/tmp/empty_ramdisk2.dmg` is a 1MB all-zero dummy file, used deliberately
so no `Apple_HFS` IOMedia can match it and XNU is forced toward real
NVMe/ANS root discovery instead of shortcutting via the ramdisk — this is
what exposes the bug. For a normal/control boot that reaches an
interactive shell quickly, just use the real `firmware/ramdisk.dmg` and add
`rd=md0` to `-args` instead.)

It booted cleanly past the point where the machine was disconnected, no
`-icount`-related QEMU errors. **The very next thing to do is check
whether it actually got past the previous freeze point** (past the 4 ANS
`probe()` score lines) or whether it hung again. If the process is still
running, check its log; if it died or was never rechecked, relaunch this
exact command and watch it — if it works, this may unblock ANS/storage
AND potentially other stalls elsewhere in the project that hit the same
underlying timer bug.

If `-icount shift=auto` doesn't fully fix it, try a fixed shift value
(e.g. `-icount shift=7` or higher — higher shift = more virtual-time-per-
instruction = more "headroom" for slow TCG code between counter checks),
and watch for `-icount`'s own gotchas (it works best single-threaded TCG,
which this project already is; watch for `align=on`/`sleep=on` interactions
if timing-sensitive I/O elsewhere starts behaving strangely).

### If `-icount` fixes the ANS stall

The path forward is roughly: get to an interactive shell booted from the
**real macOS system volume** (not the small restore ramdisk — see
"file-backed memory overlay" technique in `PHASE5_LOG.md`, already proven
working this project) via the real NVMe/ANS storage stack now that it can
actually complete matching. Then the remaining known blocker is
`AFKFirmwareService` (missing from this kernelcache build, confirmed via
string-absence + kextlog-absence) for the **DCP display path only** — that
blocks getting a real framebuffer up via `AppleDCPExpert`/`RTBuddy(DCP)`
needed before WindowServer can do anything. `hw/arm/xnu_patch.c`'s existing
`patch_kc()`/`patch_img4_deadlock()` functions are the established
precedent/pattern for patching a kernelcache function's machine code
in-place before boot (find a fileset entry, locate a function via string
cross-reference, overwrite instructions to force a return value) — this is
the right tool to reach for if `AFKFirmwareService` needs a stub
implementation supplied this way.

### Known-working baseline (already proven, don't re-litigate)

- Boots to a real interactive `bash-3.2#` shell over serial from the small
  restore ramdisk (`firmware/ramdisk.dmg`, with `rd=md0` in `-args`) —
  fast, reliable, reproducible, real command execution works.
- Real pixel rendering onto the actual `/vram` framebuffer XNU uses,
  proven via `apple_dcp.c`'s `dcp_console_feed()` (serial console text
  rendered as real glyphs) — confirmed via QEMU screendump byte-inspection.
- The real, complete, 14.19GB decrypted macOS system volume (genuine
  `WindowServer`/`Dock.app`/`Finder.app`/`loginwindow.app`) is sitting at
  `~/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg` on
  this T480s — this is what needs to actually become the boot volume.
- A file-backed QEMU memory-overlay technique
  (`memory_region_init_ram_from_file` + `memory_region_add_subregion_overlap`
  at the exact original sequential blob address XNU expects) lets XNU boot
  from that real 14GB volume without needing 14GB of host RAM resident —
  already implemented and proven in `hw/arm/xnuboot_sptm.c` on this T480s.
- XNU's `rd=md0` memory-disk mechanism has a **real, structural 32-bit
  size-field limit** (proven via exact `mod 2^32` arithmetic) — the real
  system volume can only ever boot through the actual NVMe/ANS storage
  stack, never through `rd=md0` directly. This is exactly why the
  `-icount`/ANS-matching thread above matters so much.

### Ruled out (don't re-chase these)

- `AFKFirmwareService` is **not** relevant to the ANS/storage path (only
  `role: "DCP"`/`role: "DCPEXT"` personalities need it — confirmed via
  exhaustive personality search).
- `AppleSART`/`IOCoastGuardSARTMapper` loads and scores successfully for
  both ANS controller candidates — not the blocker.
- The ANS stall is not a "just needs more patience" slow-but-finite
  algorithm — a 30-real-minute unobserved run produced zero log progress,
  conclusively ruling that out before the `-icount` root cause was found.

## Debugging toolkit (all proven this project, reuse freely)

- **gdbstub**: launch QEMU with `-s -S` (pauses at start, listens on
  `127.0.0.1:1234`), then `lldb -o 'gdb-remote 127.0.0.1:1234'` or
  `lldb -b -s <script.lldb>` for batch/scripted multi-step sessions.
  Runtime kernel addresses = static symbol-map address (from
  `ipsw kernel symbolicate --json --output <dir> firmware/bootkc`)
  **+ 0x20000000**.
- **Live PC/register sampling without pausing the VM**: `echo 'info
  registers' | nc -U <monitor-socket-path> -w 2` against the `-monitor
  unix:...,server,nowait` socket every QEMU invocation in this project
  already uses. This is how the `-icount` root cause was actually found —
  cheaper and less invasive than gdbstub for "is it actually stuck or just
  slow" questions. Sample several times a few seconds apart; identical PC
  + identical registers across samples = genuine spin, not just revisiting
  code as part of real progress.
- **Batch lldb scripts abort entirely on the first erroring command** —
  don't mix commands you're not sure will succeed with ones you need later
  in the same script.
- **Nearest-symbol lookup for arbitrary runtime addresses**: subtract
  0x20000000 (undo the slide) then binary-search the symbolicate JSON's
  keys (which are static addresses) for the nearest preceding one — small
  offsets (\<0x200 or so) are trustworthy attributions; large offsets
  (many KB+) mean the symbol table is just sparse there and the
  attribution isn't meaningful.
- `ipsw macho disass firmware/bootkc --fileset-entry com.apple.kernel -a
  <static-addr> -c <count>` disassembles real kernel code directly —
  very useful for understanding what a stuck/looping address is actually
  doing (this is literally how the `CNTVCTSS_EL0` loop was identified).
- `[ans-nvme]`/`[aic]`/similar `printf`-based MMIO trace hooks already
  exist in `hw/arm/darwin.c` for several hardware regions — check there
  before adding new instrumentation.

## How to keep this repo updated

This is a **private** repo (`riftaway7-code/hackmate-goldengate` on
GitHub). As you make progress:
- Keep appending to `PHASE5_LOG.md` (or start `PHASE6_LOG.md` if it's
  getting unwieldy) with the same level of technical detail — exact
  commands, exact addresses, exact evidence, not just conclusions. The
  user explicitly wants "even massive stuff you find/bugs/fixes" recorded,
  not just final wins.
- Commit and push regularly (this repo has `gh`/git already set up — same
  GitHub account, `riftaway7-code`). Don't wait for a milestone to commit;
  commit as you go so the desktop-side session (or the user checking from
  their phone) can see live progress.
- Update this `FORCLAUDE.md` file's "Current state as of hand-off" section
  when you reach a new milestone or rule something else out, so any future
  hand-off (back to the desktop, or to yet another session) starts from an
  accurate picture instead of a stale one.
- If you get the desktop up on the actual screen — genuinely reaching a
  rendered WindowServer/Aqua desktop — that's the whole goal. Screenshot
  it (QEMU screendump or a real photo of the T480s screen), commit the
  proof, and only then does the standing "don't stop" instruction relax.

## Practical notes

- The user is on a road trip — expect intermittent connectivity/attention
  from them. Keep working autonomously; don't block on responses.
  Don't ping/notify unless you're genuinely stuck with no further avenue,
  or you've hit the actual goal.
- Full session history and reasoning that led here (including several dead
  ends worth not re-treading) is in this repo's `PHASE0_LOG.md` through
  `PHASE5_LOG.md`, plus `CODEX_HANDOFF.md` (an earlier, narrower handoff
  written for a Codex sub-agent — still useful background, but this file
  supersedes it for scope/priority).
