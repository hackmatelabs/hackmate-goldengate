// RTBuddy null-`this` crash guard.
// Hooks the crashing function's third instruction (`sub sp, sp, #0x60`)
// - the first two instructions (`bti c`, `pacibsp`) are left untouched,
// same lesson learned from the AFKFirmwareService BTI fix earlier
// tonight: never overwrite a required landing pad. Since this hook
// point is reached with SP still exactly as it was at function entry
// (pacibsp already signed LR using that SP as modifier, and we haven't
// adjusted SP yet), the null case can `retab` directly with zero
// register/stack unwinding - nothing has been touched yet.
//
// Confirmed via the caller's own disassembly that returning nonzero in
// w0 routes it to a clean, safe early-exit path (0xfffffe000b66f988:
// mov x0,x19; ldp fp,lr; ldp x20,x19; retab) rather than continuing to
// dereference the null-derived object further.

.extern _ORIG_FUNC_PLUS0xc

.text
.align 2
.globl _rtbuddy_nullguard
_rtbuddy_nullguard:
    cbz  x0, Lnull_case
    sub  sp, sp, #0x60             // replay the overwritten original instruction
    b    _ORIG_FUNC_PLUS0xc        // resume the original function exactly

Lnull_case:
    mov  w0, #1                    // signal "not ready" to the caller
    retab                          // sp is still exactly what pacibsp signed for - safe
