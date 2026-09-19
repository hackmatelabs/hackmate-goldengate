# Phase 10: BREAKTHROUGH — found and killed VIOLATION_DOUBLE_NEST. loginwindow
# runs for the first time ever in this project's history.

## The fix

One byte. In the device tree, the internal Display CoProcessor's ("dcp")
`compatible` property string `"iop,ascwrap-v4"` was changed to
`"xop,ascwrap-v4"` (first character only). This is a raw, same-length,
in-place byte patch — no re-encoding, no risk of disturbing anything else in
the device tree blob. Applied at file offset `0x2a258` in both
`firmware/dtree.dcp8` (small-ramdisk regression variant) and
`firmware/dtree.dcp8.bigdram2` (real-target variant), producing
`dtree.dcp8.dcpbyte` and `dtree.dcp8.bigdram2.dcpbyte`.

This makes the `dcp` node invisible to IOKit's driver-personality matching
(no kext's `IOPCIPersonalities`/`IOKitPersonalities` `compatible` list will
match `"xop,ascwrap-v4"`), while leaving every other property (`reg`,
`interrupts`, `AAPL,phandle`, etc.) completely untouched -- anything that
depends on the raw hardware-description properties being present (rather
than on a driver actually binding to them) is unaffected.

## Why: the real root cause

This session's `panic(cpu 0 caller ...)` backtrace resolution (finally done
correctly this time -- see "How we got the address right" below) showed the
crashing call stack passes through **`com.apple.driver.RTBuddy`,
`com.apple.driver.AppleA7IOP`, `com.apple.driver.IOSlaveProcessor`** --
i.e. Apple's generic "RTKit" coprocessor-mailbox driver framework, NOT
process-exec/dyld-shared-cache code as every earlier theory this project
held assumed.

Our own QEMU fork's source (`hw/arm/darwin.c`) has a comment, written by
whoever built the RTKit emulation engine, that says it directly:

> `// Point the RTKit engine at the ANS instead, whose RTBuddy driver has no`
> `// secure route and comes up cleanly -- a way to validate the engine's`
> `// handshake against a real Apple driver that will actually drive it.`

Translation: the **ANS** (storage) coprocessor's RTBuddy driver talks to
its coprocessor with no SPTM-mediated "secure route" involved, and that
path works fine in this emulator. The **DCP** (display) coprocessor's
RTBuddy driver DOES use an SPTM-secured shared-memory route for its
mailbox, and that path was never fully implemented/correct here -- and we
weren't even passing `DARWIN_RTKIT=1` to enable the (partial) engine for it
in the first place, so XNU's DCP kext was matching a real hardware
description and trying to drive actual silicon-shaped MMIO that nothing on
the QEMU side was answering correctly. The DCP kext (RTBuddy-based) retries
its secure shared-region setup against that non-responding/incorrectly-
responding coprocessor, and after enough retries -- specifically once
other things (like opendirectoryd finally reaching further because
`/private/var` exists, see PHASE9) change the timing/order of what's
running -- SPTM's own bookkeeping catches a shared-region nest attempted
while one was already (incompletely torn down) active: `VIOLATION_DOUBLE_NEST`.

Simply making XNU never see the `dcp` node as a valid, matchable device
sidesteps the entire broken code path. No more DCP kext attach attempt, no
more secure-route retries, no more double-nest.

## How we got the panic backtrace address right (a real methodology fix)

Earlier attempts this session (see PHASE9) tried to resolve
`panic(cpu 0 caller 0x...)` using the WRONG arithmetic and landed on
unrelated IOMedia code, wasting real time. The bug: that "caller" field is
a generic exception-dispatch trampoline reused across many different
violation types (confirmed by tracing the SAME caller address on a
DIFFERENT panic instance in this same log file -- one was `DOUBLE_NEST`,
another was a totally unrelated `TXM [Panic]: code 0x63`, both reporting
the identical caller address). Chasing the wrapper's caller field is a
dead end.

**What actually worked**: read the FULL panicked-thread backtrace (the
`lr:`/`fp:` chain XNU dumps for the panicking thread itself, further down
in the panic text, not the one-line "caller" summary) and read XNU's own
**"Kernel Extensions in backtrace"** section, which literally lists which
loaded kexts' address ranges the backtrace passes through by name. This
needs zero symbol resolution or slide arithmetic -- XNU already did that
work and printed the kext names directly. This is the technique to use
first next time, before any manual address-resolution attempt.

Validated the general slide/offset arithmetic separately (for future use)
against `_csr_check`'s known static address: `runtime_addr = static_addr +
reported_slide`, and `fileoff_within_segment = runtime_addr -
"Kernel text exec base"(runtime)` -- confirmed self-consistent by checking
the offset came out identical to the file offset from the Mach-O segment
table. Kept for future use, but for THIS bug it was the kext-name list
that actually cracked it, not manual address math.

## What we actually got, verified, this run

Booted `dtree.dcp8.bigdram2.dcpbyte` (the DCP-defanged real-target device
tree) + the already-working Data volume + `SF_NOUNLINK`-cleared image from
PHASE8/9 (no other changes) against the plain `bootkc.md0size.uidfix` --
**no `csr_check` bypass of any kind needed for this specific fix.**

- **Zero occurrences of `VIOLATION_DOUBLE_NEST` in a ~20 minute run**,
  versus reliably crashing within the first few minutes on every single
  prior attempt (broad csr_check bypass, narrow csr_check bypass, real
  Data volume with zero bypass -- see PHASE8/PHASE9). This is the
  strongest possible confirmation available without a formal proof: same
  image, same everything else, only the one-byte dcp change differs, and
  the specific crash we've been chasing all week never happens again.
- **`loginwindow` actually spawned and reached "running" state**
  (`Successfully spawned loginwindow[76] because ipc (mach)`) -- this is
  the first time in this entire project's history (per every prior phase
  log) that loginwindow has been confirmed running, not just registered.
- loginwindow immediately performed a real, successful shared-region
  operation: `loginwindow[76] triggered unnest of range
  0x1ec000000->0x1f0000000 of DYLD shared region ... While not abnormal
  for debuggers, this increases system memory footprint until the target
  exits.` -- note this is XNU's own normal/expected-case log line for this
  operation, not an error.
- `opendirectoryd` is STILL crash-looping, but the pattern changed
  qualitatively: respawn intervals now grow via launchd's normal
  exponential backoff (10s, 11s, ... eventually minutes apart) rather than
  the tight ~1-2 second crash-loop seen in every prior run. This means
  opendirectoryd is failing LATER in its own startup than before (getting
  further each time before whatever it's still missing stops it), not
  crashing at the same early point repeatedly.
- The run eventually did hit a **different, unrelated, already-known**
  crash after ~20 minutes: `TXM [Panic]: [code: 0x00000063 | 0]`. This
  exact panic type was already observed independently in earlier
  long-running baseline tests THIS SESSION that had nothing to do with DCP
  or shared regions (see the "stable3" baseline in PHASE9) -- it's a
  pre-existing, separate instability that shows up after enough runtime
  regardless. Not a regression from this fix; a pre-existing wall to
  tackle next.

## Next steps, in honest order of promise

1. **opendirectoryd is still not fully working.** It has an empty
   `/private/var/db/dslocal/nodes/Default` (we only created the directory
   skeleton in PHASE9, via the real Data volume, not real database
   content). Real macOS ships actual local-directory-database seed files
   there (default `root`/`daemon`/system account records in
   `dslocal`'s on-disk plist-based format). Populating that with real seed
   data (copied from a real reference or synthesized) is the most direct
   path to opendirectoryd fully succeeding, which should let loginwindow
   proceed far enough to make its mach-service connection to WindowServer
   and trigger its on-demand launch -- the actual next milestone.
2. Investigate the newly-exposed `TXM [Panic]: code 0x63` wall -- now that
   DOUBLE_NEST is gone, THIS is the crash standing between us and a longer
   run. Apply the same methodology fix from this session (read the full
   backtrace + kext list, not just the caller field) from the start next
   time, rather than re-deriving it.
3. Continue watching whether, once opendirectoryd is fully healthy,
   anything else in the AMFI "Launch Constraint Violation" spam (currently
   non-fatal/"not enforcing" for keybagd, CSCSupportd, opendirectoryd,
   CoreServices, and others) becomes a hard blocker once those daemons are
   actually expected to succeed rather than crash-loop.

## Files changed

- `firmware/dtree.dcp8.dcpbyte`, `firmware/dtree.dcp8.bigdram2.dcpbyte`
  (new, one-byte-patched device trees; both live in the untracked
  `qemu-sptm-cl4-native` build tree, not this git repo -- noting the exact
  patch here so it's reproducible: file offset `0x2a258`, byte `0x69`
  ('i') -> `0x78` ('x'), turning `"iop,ascwrap-v4"` into
  `"xop,ascwrap-v4"` for the arm-io/dcp node's `compatible` property only
  -- verified NOT shared with any other node via context-byte
  cross-check before patching, since `ans`'s RTBuddy node happens to use
  the exact same string and must NOT be touched).
