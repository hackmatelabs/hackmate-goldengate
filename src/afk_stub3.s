// AFKFirmwareService minimal stub metaclass registration, v3.
// Fixes v2's BTI failure: hooks the SECOND instruction of the target
// function (offset +4), NOT the first (pacibsp, a required BTI landing
// pad for the indirect branch that calls this function via
// mod_init_func). +4 is only ever reached by straight-line fall-through
// from the untouched pacibsp, never as an indirect-branch target, so no
// landing pad is required there.
//
// Register analysis: the overwritten instruction (stp x20, x19,
// [sp, #-0x20]!) writes the CALLER's x20/x19 to the stack immediately -
// replaying it first means the original function's later code, which
// only reads x19/x20 back from that stack slot (never from the live
// registers again), is already satisfied. The one register that matters
// is x30 (LR): the original hasn't saved it to memory yet at this point
// (that happens at its OWN later "stp fp, lr" instruction), so any bl we
// make ourselves must save/restore x30 around it, or the eventual real
// save would capture our own clobbered return address instead.

.extern _OSMETACLASS_CTOR
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _ORIG_FUNC_PLUS8

.set STUB_CLASS_SIZE, 0x88

.text
.align 2
.globl _afk_stub_init_v3
_afk_stub_init_v3:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    sub  sp, sp, #0x40
    stp  x29, x30, [sp, #0x00]     // save fp/lr - lr is the true caller return addr
    stp  x0,  x1,  [sp, #0x10]
    stp  x2,  x3,  [sp, #0x20]

    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name3@PAGE
    add  x1, x1, Lafk_name3@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR

    adrp x16, _IORESOURCES_METACLASS_VTABLE@PAGE
    add  x16, x16, _IORESOURCES_METACLASS_VTABLE@PAGEOFF
    mov  x17, x19
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x19]

    ldp  x29, x30, [sp, #0x00]
    ldp  x0,  x1,  [sp, #0x10]
    ldp  x2,  x3,  [sp, #0x20]
    add  sp, sp, #0x40
    b    _ORIG_FUNC_PLUS8         // resume the original function exactly

.align 3
Lafk_name3:
    .asciz "AFKFirmwareService"
