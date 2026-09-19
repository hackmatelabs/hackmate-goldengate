# Phase 0 — QEMU / darwin-vm compilation — **COMPLETE**

Built on this Windows desktop (T480s not physically available this session) on 2026-09-16.

**Final status: BUILD SUCCEEDED.**
`qemu-system-aarch64.exe` at `C:\GoldenGate\darwin-vm\qemu-sptm\build\qemu-system-aarch64.exe` (130MB).

Verified working:
```
$ qemu-system-aarch64.exe --version
QEMU emulator version 11.1.0
Copyright (c) 2003-2026 Fabrice Bellard and the QEMU Project developers

$ qemu-system-aarch64.exe -M help | grep darwin
darwin               Generic Apple Silicon Device
```

The custom `darwin` machine type (qemu-sptm's Apple Silicon support, the whole point of this fork) is present and the binary runs cleanly. As far as we can tell, **this is the first time qemu-sptm has been built natively on Windows** — everything upstream/darwin-vm documents and tests against is Linux/macOS.

## Environment setup

- Existing MSYS2 at `C:\devkitPro\msys2` only had devkitPro's ARM/embedded repos enabled. Enabled `[mingw64]` in `pacman.conf` (mirrorlist already present, just unwired) and installed the real toolchain: `mingw-w64-x86_64-toolchain`, `glib2`, `pixman`, `pkgconf`, `meson`, `ninja`, `python`.
- Project relocated from `C:\Users\Raahim Syed\...` to `C:\GoldenGate` — Meson refuses to build in any path containing spaces.

## Real bugs found and fixed (all genuine Windows/MinGW portability issues, none were environment misconfiguration on our end)

1. **`configure`'s argument parser was silently broken.** `optarg=$(expr "x$opt" : 'x[^=]*=\(.*\)')` — this MSYS2 build's `/usr/bin/expr` (GNU coreutils 8.32) returns `0` instead of the captured group for this exact BRE pattern (confirmed via isolated repro, not a quoting artifact). This broke *every* `--flag=value` argument silently (`--target-list=aarch64-softmmu` became `target_list="0"` → `ERROR: Unknown target name '0'`). Fixed both occurrences (lines 203, 601) to the portable `optarg="${opt#*=}"`.
2. **`hw/arm/darwin.c`** used POSIX `mmap()`/`munmap()`/`PROT_*`/`MAP_PRIVATE`/`MAP_FAILED` to read firmware files into memory — none of that exists on MinGW (no `sys/mman.h`). Since the mapping was `MAP_PRIVATE` (writes never go back to the file anyway), replaced with a portable `g_malloc()` + `read()` loop, and the matching `munmap()` calls with `g_free()`.
3. **`hw/arm/apple_dtree.c`** used `strsep()`, which MinGW's CRT doesn't provide. Added a small local portable reimplementation guarded by `#ifndef HAVE_STRSEP`.
4. **`hw/arm/xnuboot_sptm.c`** had a second, unused `#include <sys/mman.h>` (the file doesn't actually call any real `mmap`/`munmap` — only similarly-named `set_adt_mmap`/`push_adt_mmap` helpers, unrelated). Just removed the include.
5. **The `BIT(nr)` macro itself was unsafe on Windows.** `include/qemu/bitops.h` defined `BIT(nr)` as `(1UL << (nr))`. On Linux/macOS (LP64), `unsigned long` is 64-bit, so `BIT(63)` etc. are fine — this is why nobody's hit it before. On Windows (LLP64), `unsigned long` is 32-bit, so any `BIT(n)` with `n >= 32` silently overflow-shifts. This hit darwin-vm's own Apple-Silicon-specific code in multiple places (`apple_regs.c: BIT(63)`, `xnuboot_sptm.c: BIT(36)`, `BIT(35)`) as well as being a latent landmine for any future code using `BIT()` above 31. Fixed at the root: `BIT(nr)` now matches `BIT_ULL(nr)` (`1ULL << (nr)`), safe for any shift up to 63 on every host.
6. **Upstream QEMU format-string bug, Windows-only.** `target/arm/tcg/translate-a64.c` logged a `vaddr` (which is `long long unsigned int` under MinGW/LLP64) with `%016lX` (expects `long unsigned int`), triggering `-Werror=format=`. Changed to `%016" PRIx64 "` for portable correctness.

None of these fixes touch actual emulation/boot logic — they're all straightforward portability corrections (parsing, memory I/O, a missing libc function, a bit-shift width, a format specifier). Build is otherwise using the project's documented configuration (`--target-list=aarch64-softmmu --disable-pvg`).

## Still open (Phase 1 territory)

- `get_files.sh` / `fix_perms.sh` (IPSW download + ramdisk permission fixup) use real macOS-only tools (`hdiutil`, `codesign`, `sudo chown root:wheel`). These need to run on an actual macOS install — the T480s's hackintosh Tahoe once it's physically accessible, not this Windows desktop. This is the next hard dependency before any boot attempt.
- No boot attempt has been made yet — that requires both the firmware files (blocked above) and running the binary against them via `run.sh`.
- T480s-specific validation (its exact CPU's TCG performance, any hardware-specific quirks) still needs to happen once the user has physical access again — this Windows desktop's successful build is the baseline to reproduce there, not a substitute for it.

## Note: mid-session near-miss

While investigating a related community project's QEMU patches, `cp -r` of the
`qemu-sptm` submodule directory followed by `git checkout <other-commit> -- .`
inside the copy silently reverted the **original** working `qemu-sptm`
directory's uncommitted fixes — because `cp -r` copies the submodule's `.git`
*gitlink file*, which still points at the shared `.git/modules/qemu-sptm`
storage (with `core.worktree` pointing back at the original path), so git
operations inside the "copy" actually acted on the real working tree. All 6
portability fixes above were re-applied and the build was reconfirmed working
(binary re-verified with `--version`). Lesson: never `cp -r` a git submodule
directory for throwaway testing — use a real `git clone` of the remote instead.
