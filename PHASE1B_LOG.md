# Phase 1B — First actual boot attempt (T480s, native macOS build)

Ran directly on the T480s hackintosh (macOS 26.5.2 Tahoe), using a fresh **native** qemu-sptm
build (no Windows portability patches needed — clean build on real Darwin/clang, confirming those
6 fixes really were Windows-only issues). Target: **macOS 27.0 Golden Gate (26A428) on Macmini9,1
(t8103/M1)**, the fully-patched firmware from Phase 1 (ramdisk chown'd, LaunchDaemons swapped,
trustcache built).

## Setup

- Transferred the Phase 1 firmware (`bootkc`, `dtree`, `ramdisk.dmg`, `ramdisk.tc`) from Windows to
  the T480s over the local network (~473MB, few minutes). Had to strip CRLF line endings the
  Windows→Mac transfer introduced on the `.sh`/`.py` helper scripts before they'd run.
- `fix_perms.sh` (ownership) ran clean. The fuller `patch_ramdisk()` logic from `get_files.sh`
  (LaunchDaemons swap + trustcache) was extracted into a standalone script since `ipsw` isn't
  installed on the T480s and re-running all of `get_files.sh` would've redownloaded everything —
  ran that instead, completed cleanly (546 codesign hashes collected, `ramdisk.tc` built, 12KB).
- Installed Homebrew manually (the official installer now refuses Intel Macs entirely — had to use
  the old tarball method), then `pkg-config`/`glib`/`pixman` (built from source, ~15 min, no bottles
  available for this setup) and `meson`/`ninja`/`tomli` via pip (Python 3.9's Command Line Tools
  Python needs `tomli` — no builtin `tomllib` before 3.11).
- Fresh `git clone` of `darwin-vm` + `qemu-sptm` directly on the T480s (not copying the Windows
  build). Configured and built with **zero modifications** — clean 2142/2142 compile, confirming
  all 6 Phase 0 fixes really were Windows/MinGW-specific.

## The actual boot attempt

Ran `qemu-system-aarch64 -M darwin -bootkc ... -dtree ... -tc ... -ramdisk ... -args "rd=md0
serial=3/7 -v -noprogress wdt=-1 wlan-olyhal-abort" -nographic -serial file:boot_log.txt -m 8G`.

**Result: hangs. Zero serial output. CPU pegged at ~100%, genuinely computing (not deadlocked on
I/O) — confirmed by querying the QEMU monitor over a Unix socket (`info registers`) and watching
PC across a 10-second gap.**

**Exact hang location, disassembled live via the monitor:**
```
0x80c4c8100:  add      x3, x1, x3
0x80c4c8104:  ldr      x21, [x1, #8]
0x80c4c8108:  cbz      x21, #0x80c4c8108      <-- stuck here, spinning on itself
0x80c4c810c:  ldr      w2, [x21, #0x1c8]
0x80c4c8110:  cmp      x0, x2
0x80c4c8114:  b.eq     #0x80c4c8128
0x80c4c8118:  add      x1, x1, x19
0x80c4c811c:  cmp      x1, x3
0x80c4c8120:  b.eq     #0x80c4c8190
0x80c4c8124:  b        #0x80c4c8104
```
Register state at the hang: `PC=0x80c4c8108`, `X21=0`, `X01=0x80c988960`, `EL2h`. This is a
table-walk loop (stride `X19`, bounded by `X03`) looking for an entry whose `[X21+0x1c8]` field
matches `X00` — but the current entry's `[X01+8]` pointer (loaded into `X21`) is null, and instead
of skipping/erroring on a null entry, the code spins on `cbz x21, <self>` waiting for something
else to write a non-zero value there. Nothing in our emulation does. Tried both `serial=3` (matches
`run.sh`'s shipped default) and `serial=7` (matches `darwin.c`'s own internal default) — identical
hang in both cases at the identical address, so the serial-port argument isn't the cause; this is
upstream of any console output entirely.

This is `EL2h` (guarded/hypervisor level, pre-XNU-proper), t8103 has no SPTM, so this is early
boot code before or during the CPU-topology/policy table walk that (on real hardware, or under
HVF-accelerated darwin-vm) some other agent — real firmware, SPTM on SPTM-capable chips, or
possibly a value this exact kernelcache/devicetree combination expects the device tree to already
carry — would have populated. No symbols on this RELEASE kernelcache, so pinning down exactly
*which* XNU/iBoot table this is without deeper reverse-engineering wasn't done tonight.

## Second attempt: M2 Mac Mini (Mac14,3/t8112)

Tried the SPTM-capable-per-README M2 target on the theory that a different chip generation might
sidestep the hang. Downloaded fresh firmware directly (still no `sptm`/`txm` files extracted for
this device either — Golden Gate apparently doesn't ship a separate SPTM binary for t8112 in this
build, contrary to my assumption), patched the ramdisk the same way, booted.

**Identical failure mode.** Different absolute address (different kernelcache build), but *the
exact same instruction sequence* at the exact same relative structure:
```
mul x3, x19, x4
add x3, x1, x3
ldr x21, [x1, #8]
cbz x21, <self>          <-- same spin pattern
ldr w2, [x21, #0x1c8]
...
```
`X00=0` (the search key) in both cases too. This strongly implies the hang is **not
device-specific** — it's common early-boot logic (likely a table walk keyed on something from the
device tree, e.g. resolving a board/feature id) that both kernelcaches hit identically, upstream
of anything SPTM/TXM would touch. So swapping target chips again probably won't help; the real
gap is likely in how we're preparing the device tree or firmware handoff itself, not which device
we pick.

## Symbol hunting (ipsw kernel symbolicate + macho disass)

`ipsw kernel symbolicate` (no signatures needed — it auto-discovers 15,671 C++ symbols and the
syscall/trap tables from the kernelcache's own metadata) resolved the hang, once the address
mapping was worked out: **darwin-vm's QEMU guest PC and the kernelcache's real mach-o virtual
address share identical low 32 bits, just under a different upper half** (confirmed by matching
our PC's low bits against `__TEXT_BOOT_EXEC`'s segment start from `ipsw macho info`). Real address:
`0xfffffe000c54c10c`, inside the tiny (32KB) `__TEXT_BOOT_EXEC` segment — which is XNU's earliest,
pre-scheduler boot code, consistent with hanging this early.

`ipsw macho disass --vaddr <addr> --all-fileset-entries` on the static kernelcache file (no need to
keep QEMU running) showed the full routine:
```
ldr x21, [x1, #8]              ; cpu_data_entry.cpu_data_paddr
cbz x21, <self>                ; <- our hang: this entry's paddr is null
ldr w2, [x21, #0x1c8]          ; entry->cpu_id (offset matches XNU's cpu_data_t)
cmp x0, x2                     ; does it match the CPU we're looking for?
b.eq <found>
...                            ; else advance to next table slot, loop
<found>:
msr spsel, #1
ldr x10, [x21, #0x28]          ; per-CPU stack pointer
mov sp, x10
...
ldr x2, [x21, #0xb8]           ; per-CPU start function pointer
cbz x2, <panic_fallback>
...                            ; compare against known handler addrs, branch
<panic_fallback>:
movk x0, #0xdeadb001, ...      ; classic Apple debug/panic magic constant
```
This is unmistakably **XNU's `start.s` reset-vector CPU dispatch**, walking the `CpuDataEntries[]`
array (a fixed-size table of `{cpu_data_vaddr, cpu_data_paddr}` pairs, one per possible CPU) to find
the entry matching the currently-executing CPU's id, so it can load that CPU's boot stack pointer
and jump to its start function. **This is real, documented XNU structure** — confirmed against
public `apple-oss-distributions/xnu` source (`osfmk/arm/arm_init.c`, `osfmk/arm64/start.s`): on a
normal cold boot, `arm_init()` populates `CpuDataEntries[master_cpu].cpu_data_vaddr = &BootCpuData`
and computes the matching `cpu_data_paddr` very early, and this reset-vector code (used for both
the initial cold-boot entry *and* warm resets/secondary-CPU wake, per Apple's own source) expects
that slot already populated when it runs.

We're landing exactly on the kernelcache's own declared entry point (`LC_UNIXTHREAD`'s `pc` in
`ipsw macho info` matches where we hang, give or take), so darwin-vm isn't jumping to a wrong
address — the gap is that whatever populates `CpuDataEntries[0]`'s `cpu_data_paddr` before/during
this exact entry point on real hardware (or under HVF-accelerated darwin-vm, which the upstream
project actually tests) isn't happening in our from-cold TCG boot. Exactly where that
initialization is supposed to come from (iBoot, an earlier instruction we haven't reached, or
something `darwin.c`'s C-level machine setup is supposed to write into the emulated device-tree
regions before jumping to `init_pc`) needs either the exact XNU 26A428 source (not public — 2 days
old) or deeper cross-referencing against `arm_init.c`'s actual call sequence.

## Honest assessment

This is real, first-of-its-kind data: nobody has published a Golden Gate boot attempt via
`darwin-vm`/`qemu-sptm` before (M1/t8103 macOS 27 support in the README is presumably tested with
HVF-accelerated boot on real ARM Mac hosts, not from-cold x86 TCG with our exact device/firmware
combo). A specific, reproducible, symbol-free hang at a specific instruction is a legitimate
starting point for the next debugging session — not a dead end, but not something to keep
blind-guessing at tonight after this much ground already covered. Two concrete next moves, in
order of promise:
1. ~~Try an SPTM-capable target (M2 Mac Mini / `t8112`)~~ — **done, ruled out**: identical hang
   pattern on a completely different device/kernelcache (see below). Not device-specific.
2. Symbolicate `bootkc` against public XNU source to identify what's actually at the hang address
   and what table it's walking — the only remaining honest path to "we know exactly what data
   structure needs populating and why" rather than guessing. Complicated by Golden Gate being 2
   days old: the matching `xnu` source release may not be public yet on
   apple-oss-distributions/xnu, and there's no Kernel Debug Kit (needs an Apple Developer account)
   for symbols on this exact build. Worth checking both before assuming it's blocked.
3. Compare against what darwin-vm's own tested path actually does differently — their README
   examples boot in seconds using HVF acceleration on real ARM hosts; it's possible something
   about our device tree preparation (`dt_fixup.py`) or the specific `-args` boot arguments is
   missing a step their tested flow has that we don't, independent of TCG-vs-HVF speed.
