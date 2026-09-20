# Phase 12: root-caused the graphics wall completely — it's a missing Auxiliary
# Kernel Collection, and it cannot be built without an Apple KDK that doesn't
# exist for this build. This is a hard, external wall, not a bug in our work.

## Starting point

Picking up from PHASE10/11: DCP was deliberately defanged (device tree
`compatible` string patched) to avoid `VIOLATION_DOUBLE_NEST`, which meant
no real display driver ever attached, which meant `Couldn't alloc class
"AFKResource"` failures and no `WindowServer`. This session re-enabled the
*real* DCP driver to understand the actual failure mode properly, using our
own emulator's real RTKit/AFK mailbox implementation (found to be genuinely
functional -- `hw/arm/apple_rtkit.c` + `hw/arm/apple_dcp.c`, ported in by
Codex from the `ios27-cl4-secure-world` project, complete through the AFK
ring-buffer transport handshake).

## What we found, in order

1. **Reverted the DCP device-tree defang** (both the `dcp` node's
   `compatible` string and the `-nub` child's, at the same byte offsets
   documented in PHASE10) to a new file, `dtree.dcp8.bigdram2.realdcp`.
   Kept the known-safe `.dcpbyte.nubx` baseline untouched (copied before
   editing, this time -- learned from nearly clobbering it once this
   session).
2. Added real ring-buffer-dump instrumentation to `apple_dcp.c`'s
   `RBEP_RECV` handler (previously just printed a placeholder) and rebuilt
   qemu-system-aarch64 via `ninja` (PATH needs
   `/usr/local/homebrew/Cellar/ninja/1.13.2/bin` -- not just `ninja` bare,
   it's not globally linked on this host).
3. Booted with `DARWIN_FB=1 DARWIN_RTKIT=1` (as before) **plus
   `DARWIN_DART=1`, which had never been passed in any prior session's
   real-target boots** -- confirmed via `hw/arm/darwin.c` that DART
   (IOMMU) needs this env var to initialize at all, and RTBuddy(DCP)'s
   driver depends on it for shared-buffer setup.
4. Even with DART now enabled, `RTBuddy(DCP): start(<ptr>)` fires exactly
   once in the boot log and then **nothing** -- our RTKit mailbox
   (confirmed instrumented and printing on every read/write) never
   receives a single byte of traffic afterward, for 8+ minutes of stable
   runtime. This rules out a driver hang/spin; IOKit's `start()` is
   returning `false` silently, before ever touching the hardware.
5. **Live kernel debugging via QEMU's gdbstub + lldb** (this project's
   first real use of this technique end-to-end) pinpointed the actual
   failure: `com.apple.kernel`'s own generic
   `OSMetaClass::allocClassWithName()`-style code path (single xref found
   via the validated raw-bitfield ADRP+ADD/LDR scanner, at static VA
   `0xfffffe000c3cc2e4`) is failing to allocate a class named
   **`"AFKFirmwareService"`** -- read directly out of guest memory at the
   breakpoint (`memory read --format s \`*(unsigned long*)$sp\`` --
   the class-name argument is passed on the stack at `[sp]`, not in a
   register, for this call). Both calling frames resolve to
   `com.apple.kernel` itself, not any specific driver kext -- this is
   core kernel bootstrap code, not a per-driver precondition check.
6. **Confirmed exhaustively that no kext in the entire bootkc actually
   defines this class.** Searched every `LC_FILESET_ENTRY`'s own
   `__TEXT`/`__TEXT_EXEC`/`__DATA`/`__DATA_CONST` segments (explicitly
   excluding the shared `__LINKEDIT` string table, which would give false
   positives) for the literal string `"AFKFirmwareService"` -- zero
   matches anywhere. `com.apple.driver.AppleDCP` (the thin nub, ~36KB
   __TEXT_EXEC) and `com.apple.iokit.IOMobileGraphicsFamily-DCP` (the
   bigger family kext, ~182KB __TEXT_EXEC) both *reference* the class by
   name but neither *implements* it.
7. **Searched the entire system volume's `/System/Library/Extensions` for
   any `.kext` bundle containing this string at all** -- none found,
   including bundles with very plausible names (`AFKACIPCKext.kext`,
   `AFKRemoteCPMS.kext`, `AFKHIDTBDevice.kext`, `DCPAVFamilyProxy.kext`,
   `DCPDPFamilyProxy.kext`, etc.). The implementing kext is not shipped as
   a discoverable file anywhere on this system volume.
8. **Found and checked the real explanation**: real Apple Silicon macOS
   splits kernel code across a `BootKernelExtensions.kc` (what we call
   `bootkc`) and a separate **Auxiliary Kernel Collection (AuxKC)**,
   generated at *install time* by `kmutil createkernelcollection` from the
   kext bundles physically present on the target Mac, and cached under
   `/System/Volumes/Preboot/<UUID>/...` (real structure, confirmed via
   Aiyan's actual Preboot dump this session) or
   `/Library/KernelCollections/` on the Data volume. Our system volume was
   extracted directly from the IPSW and never went through a real install
   -- checked `/System/Library/Templates/Data/Library/KernelCollections/`
   (the install-time seed location) and it contains only a 2-byte
   placeholder file, confirming the AuxKC was never generated for this
   image.

## The actual, final blocker

Tried to build the missing AuxKC ourselves, for real, using the host's own
`kmutil create -n aux --arch arm64e -R <mounted system volume> -r
<Extensions dir> -z --no-authentication --allow-missing-collections
--allow-missing-kdk -B <bootkc path> -A <output path>`.

Result: `DeveloperTools Error: Could not find a SDK or KDK installed that
matches system's build version 26A428`. This is a **hard validation with
no override flag** for the `create` subcommand (the `--allow-missing-kdk`
flag exists but its own help text scopes it to the `rebuild` path
specifically, and empirically had no effect here). `kmutil create`
requires an Apple-signed Kernel Debug Kit matching the exact build
(`26A428`) to be installed on the build machine. No such KDK exists
publicly for this build (checked `/Library/Developer/KDKs/` -- empty;
tried substituting the host's own newest available SDK, `MacOSX26.5.sdk`
-- rejected, since the check is for a build-matching KDK/SDK specifically,
not "any recent one").

**This is where static/host-side tooling genuinely runs out.** There is no
further workaround available through Apple's own supported toolchain
without an artifact (the KDK) that doesn't exist yet, or an approach that
doesn't need `kmutil` at all.

## What this means, honestly

- The DCP/graphics/WindowServer wall is not a bug in this project's own
  work, not an emulation gap in the QEMU/RTKit/AFK code (that part is
  real, tested, and working through the transport handshake), and not
  fixable by any device-tree or kernel patch of the kind used successfully
  everywhere else in this project. It is Apple's own kernel bootstrap
  correctly refusing to instantiate a class whose implementation is
  legitimately absent from this image, exactly as it would on real
  hardware with a corrupted or missing AuxKC.
- Reverted the real-target boot back to the known-safe `.dcpbyte.nubx`
  configuration (DCP defanged) after this investigation -- no reason to
  run with real DCP enabled now that we know it can never succeed with
  this image; it only reintroduces boot-time driver-matching overhead for
  no benefit.

## Remaining honest options, in order of plausibility

1. **Wait for/obtain a real KDK for build 26A428**, if one is ever
   published by Apple (KDKs are normally released alongside or shortly
   after a build). If one becomes available, `kmutil create -n aux` with
   the exact same command line tried above should work directly --
   nothing else about the setup needs to change.
2. **Perform an actual macOS install** (rather than a raw IPSW system
   volume extraction) inside this same QEMU/SPTM boot environment, letting
   the *real* installer generate the AuxKC itself as part of first-boot,
   the way a genuine Mac would. This is a materially different, bigger
   undertaking than anything done in this project so far (the installer
   itself needs to run and complete, which has its own prerequisites we
   haven't touched), but it's the "do it exactly the way Apple intends"
   path and sidesteps needing an external KDK entirely.
3. **Write a from-scratch replacement implementation** of
   `AFKFirmwareService`/`AFKResource` and inject it as a new kext into the
   kernelcache by hand (Mach-O surgery: add a new `LC_FILESET_ENTRY`,
   implement enough of the class's real vtable/ABI for
   `AppleDCP`/`IOMobileGraphicsFamily-DCP` to link against it). This is
   almost certainly the largest, riskiest option -- reimplementing an
   undocumented proprietary Apple framework class well enough to satisfy
   real callers -- and should be a last resort.

## Files/artifacts from this session

- `hw/arm/apple_dcp.c`: added real ring-buffer byte-dump on `RBEP_RECV`
  (kept in the tree; harmless, useful for any future investigation if DCP
  is ever re-enabled).
- `firmware/dtree.dcp8.bigdram2.realdcp`: the real-DCP-enabled device tree
  used for this investigation. Not the boot default going forward --
  `dtree.dcp8.bigdram2.dcpbyte.nubx` (defanged) remains the real-target
  default, restored and verified untouched.
- Confirmed `ninja` build path for this checkout:
  `/usr/local/homebrew/Cellar/ninja/1.13.2/bin/ninja` (not on PATH by
  default) run from `qemu-sptm-cl4-native/build/`, target
  `qemu-system-aarch64`.
- Live kernel debugging recipe that worked end-to-end, worth reusing:
  `qemu-system-aarch64 ... -s -S` (halt at reset, gdbstub on
  `localhost:1234`) + `lldb -b -s <script-file>` (using a **script file**
  via `command source`, not a chain of `-o` flags -- the `-o` chain
  buffers ALL output until the whole batch finishes or errors, which reads
  as a hang; a script file behaves the same way actually, the real fix
  was fixing the LLDB expression syntax itself: use `` `expression` ``
  backtick-substitution inside `memory read`, e.g. `memory read --format s
  \`*(unsigned long*)$sp\``, not a bare register name).
