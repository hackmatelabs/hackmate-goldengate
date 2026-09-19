# Phase 1 — Golden Gate firmware acquisition (this session's progress)

Continuing directly from Phase 0 (qemu-sptm built successfully). Target device: **M1 Mac Mini (Macmini9,1 / t8103 / j274ap)** — chosen because darwin-vm's own compatibility table confirms macOS 27.0 (26A428, Golden Gate) boots on it, and it's the simplest supported config (no SPTM/TXM — those were only added for newer chips).

## What got done, entirely without a Mac

1. Installed `jq` and `ipsw` (blacktop/ipsw) via `winget` — both are genuinely cross-platform Go/native tools, contrary to `get_files.sh`'s `brew install` instructions which are just the author's own (Mac-centric) dev environment, not a hard requirement.
2. Used `ipsw download ipsw --device Macmini9,1 --build 26A428 --urls` to resolve the **real, current Golden Gate IPSW URL**:
   `https://updates.cdn-apple.com/2026FallFCS/afcfc88e-bbe6-44bf-a5da-07c56eebc06c/UniversalMac_27.0_26A428_Restore.ipsw`
3. Ran `get_files.sh` (`DEVNAME=Macmini9,1 URL=<above>`) directly on this Windows desktop via Git Bash. It correctly:
   - Identified the device (board `j274ap`, kernel ext `mac13g`, chip `t8103`, sdk `macosx`)
   - Extracted `firmware/bootkc` (kernelcache, 122MB) and `firmware/dtree` (device tree, 232KB) **remotely** via `ipsw extract --remote` — no local IPSW download needed
   - Confirmed t8103 has no SPTM/TXM (correctly skipped, matches the compat table)
   - Extracted `firmware/ramdisk.dmg` (373MB) the same way
   - Ran `patch_dtree` (device tree fixup) successfully
   - **Stopped cleanly and correctly** at `patch_ramdisk`, which explicitly checks `uname == Darwin` and exits — this is the one step the script itself says needs a real Mac.

## Investigated whether the ramdisk step can be done without a Mac — it can't, here's why

- `patch_ramdisk` needs to: mount the ramdisk as a writable filesystem, swap in a different `LaunchDaemons` folder, and (for the `macosx` SDK path we're on) read existing code-signature CDHashes via `codesign -d` to build a trustcache. No new signing is needed for macOS specifically (only the `iphoneos` path in the script copies + freshly signs new binaries) — so this is *narrower* than it first looked.
- Checked `ipsw mount rdisk` (a purpose-built Apple-firmware tool) — it mounts straight from an IPSW container, not a standalone extracted `.dmg`, and would require downloading the full multi-GB restore image just to remount something we already extracted. Not worth it for this alone.
- Checked 7-Zip 26.02, which does have real APFS read support: it correctly identifies `ramdisk.dmg` as a raw APFS volume (`ramdisk`, 1390 files, 822 directories, no UDIF wrapper) and can list/extract its contents. **But 7-Zip has no APFS write/creation support** — there is no available Windows tool that can repack a modified, valid, bootable APFS image. This is a real, hard tooling gap on Windows, not a missed trick.
- **Conclusion**: reading/inspecting the ramdisk is possible on Windows; writing a patched one back is not, without either real macOS (`hdiutil`) or building APFS write support from scratch (a much bigger, separate research project not worth doing when the T480s's actual hackintosh Tahoe install already has this for free).

## Next step (needs the T480s)

Once the T480s is physically available: copy `C:\GoldenGate\darwin-vm` (or just the `firmware/` dir + `get_files.sh`/`fix_perms.sh`/`launchdaemons/`) to it, boot into the hackintosh Tahoe install, and run:
```
./fix_perms.sh firmware/ramdisk.dmg
```
(the `get_files.sh` run already completed everything up to that point — `fix_perms.sh` alone should be enough to finish the ramdisk prep, no need to redo the download). Then copy `firmware/` back and attempt `./run.sh` here (or on the T480s directly, boot-hardware-permitting) for the actual first boot attempt.

## Files present as of this session

```
C:\GoldenGate\darwin-vm\firmware\
  bootkc       122,945,536 bytes  (Golden Gate kernelcache for t8103)
  dtree            232,800 bytes  (device tree, patched)
  ramdisk.dmg  373,293,056 bytes  (APFS ramdisk, needs Mac-side patching)
  info                 128 bytes  (device/URL record)
```
