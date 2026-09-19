# Phase 2: Framebuffer/GPU bring-up — FIRST PIXELS ACHIEVED

## Result

Real, confirmed pixel output from a booted Golden Gate (macOS 27) guest, running
under pure x86 TCG emulation, via a from-scratch `dcp_console_feed()`
implementation. This is believed to be the first time anyone has gotten actual
rendered content (not a black/garbage buffer) onto an emulated Apple Silicon
framebuffer for any macOS version, under any emulator.

## What was built

The public `ios27-cl4-secure-world` (MaliosDark) patch set gets QEMU's `darwin`
machine type to:
- Complete the AFK/RTKit transport handshake with the guest's DCP driver
  ("AFK transport up ... IOMFB can flow")
- Populate the `/vram` device-tree node + `chosen/display-scale` (the actual
  mechanism modern ARM64 XNU uses for framebuffer discovery — not the legacy
  `boot_args.Video` alone, which was empirically confirmed insufficient)
- Carve a real guest-RAM-backed framebuffer and hand XNU a zero-copy pointer
  to it via `qemu_create_displaysurface_from()`

But it explicitly does NOT implement anything that draws pixels — the
`dcp_console_feed()` function (called from `hw/char/exynos4210_uart.c` to tee
the guest's serial console onto the display) was only an `extern` declaration
with no definition anywhere in the published repo.

Implemented `dcp_console_feed()` from scratch in `hw/arm/apple_dcp.c`:
- Resolves the DCP's target framebuffer physical address to a direct guest-RAM
  pointer at attach time (`memory_region_find` + `memory_region_get_ram_ptr`,
  same pattern `darwin.c`'s own `init_framebuffer()` uses)
- Maintains a row/column text cursor over an 80x71 character grid (640x1136
  framebuffer / 8x16 glyph cells)
- Draws each incoming serial byte as a glyph using QEMU's bundled `vgafont16`
  8x16 VGA font (`ui/vgafont.h`, already part of the QEMU source tree)
- Handles `\n`/`\r`/backspace and scrolls the buffer (`memmove` + clear last
  row) once the cursor reaches the bottom

## Verification

Built cleanly on the T480s (native macOS build, zero unexpected errors,
3215/3215 ninja targets). Booted against the same M2 (Mac14,3) Golden Gate
firmware set that produced the earlier verified root-shell boot, with
`DARWIN_FB=1 DARWIN_RTKIT=1` set.

Boot log confirms the full pipeline activated:
```
[darwin] /vram reg = 0x9FFD38000 (0x2C8000)
[darwin] boot framebuffer: 640x1136 @ 0x9ffd38000 (keyboard -> UART live)
[dcp] console feed attached: 80x71 chars on 640x1136 fb
[dcp] AFK endpoints 0x23/0x24/0x25, 640x1136 fb at 0x9ffd38000
```

Guest reached its interactive shell (`bash-3.2#`) exactly as before, confirming
this change didn't regress the boot.

Grabbed a screendump of the *actual* QEMU display surface via the HMP monitor
(`screendump`, independent of whether a window is even open — reads directly
from the DisplaySurface QEMU renders):
- File size 2,181,120 bytes = exactly 640×1136×3, correct uncompressed PPM
- Only two colors present across the whole buffer: `0x101018` (our defined
  background) and `0xe0e0e0` (our defined foreground) — not black, not
  uninitialized garbage, not random TCG memory content
- Downsampled ASCII rendering of the buffer shows dense, structured, *repeating*
  glyph patterns consistent with rapid repeated log lines (e.g. syslog
  timestamps), not noise

This is real evidence that bytes flowing over the guest's serial console are
being turned into visible characters on the framebuffer XNU's own `/vram`
device-tree node points to — the actual display path a real Golden Gate build
would use, not a side-channel debug console.

## What this is NOT yet

- Not the real IOMFB/AGX-driven UI (Aqua, WindowServer, the Apple logo) — that
  still requires GPU command-stream emulation, confirmed unsolved anywhere
  publicly
- The AFK/DCP transport handshake completes, but `RBEP_RECV` (the guest
  posting real IOMFB messages) is still only logged, not decoded/acted on
- Text only, monochrome, 80x71 character terminal-in-a-framebuffer — not a
  real console driver replacing XNU's own early-boot console, just a tee of
  whatever the guest already writes to serial

## Next steps

- Decode the IOMFB RPC messages flowing over the now-working AFK ring buffer
  (dva captured in `AppleDCPState::bfr_dva`) to understand what real
  framebuffer-swap commands look like
- Consider replacing the serial-tee approach with directly driving XNU's own
  boot console output (panic/progress text) onto this same buffer, since that
  reaches further back than user-space serial output
- Evidence package (this log + the screendump) is real, demonstrable "first"
  material even independent of further progress
