Golden Gate on Intel — booting real macOS on emulated Apple Silicon under QEMU.

## Layout

- `src/` — kernel patch stubs (`.s` assembly, `.c` source)
- `scripts/` — build/patch/boot helper scripts
- `debug/` — lldb scripts used for live debugging
- `screenshots/` — evidence screenshots
- `darwin-vm/`, `darwin-vm-m2/`, `ios27-cl4-secure-world/` — the QEMU fork and secure-world source trees

Handoff docs, session logs, and debug dumps live locally only (T480s + desktop), not in this repo.

The real, running build lives on the T480s itself, not here — this repo is source and evidence.
