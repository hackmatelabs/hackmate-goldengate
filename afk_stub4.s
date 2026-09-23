// Diagnostic v4: trampoline mechanism ONLY, no OSMetaClass construction
// at all. If this boots clean (same behavior as the fully unpatched
// original), it isolates the v3 bug to the constructor-call interaction
// specifically, not the trampoline hook mechanism itself.

.extern _ORIG_FUNC_PLUS8

.text
.align 2
.globl _afk_stub_init_v4
_afk_stub_init_v4:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    b    _ORIG_FUNC_PLUS8          // resume the original function exactly, no extra work
