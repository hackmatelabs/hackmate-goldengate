// AFKFirmwareService minimal stub metaclass registration, v2.
// Instruction-trampoline into the ORIGINAL mod_init_func[90] target
// function's own first instruction (its "pacibsp" prologue), instead of
// touching __DATA_CONST.__mod_init_func at all. This is the same style
// of patch already proven working for the TXM fix: overwrite one
// instruction with a branch, replay the overwritten instruction plus do
// extra work, then resume the original function exactly.

.extern _OSMETACLASS_CTOR
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _ORIG_FUNC_PLUS4

.set STUB_CLASS_SIZE, 0x88

.text
.align 2
.globl _afk_stub_init_v2
_afk_stub_init_v2:
    pacibsp                     // replay the overwritten original instruction
    sub  sp, sp, #0x50
    stp  x29, x30, [sp, #0x00]
    stp  x19, x20, [sp, #0x10]
    stp  x0,  x1,  [sp, #0x20]
    stp  x2,  x3,  [sp, #0x30]

    // construct a new OSMetaClass instance named "AFKFirmwareService"
    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name2@PAGE
    add  x1, x1, Lafk_name2@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR

    // overwrite the new instance's vtable ptr with IOResources::MetaClass's
    // real vtable, re-signed for THIS instance's address
    adrp x16, _IORESOURCES_METACLASS_VTABLE@PAGE
    add  x16, x16, _IORESOURCES_METACLASS_VTABLE@PAGEOFF
    mov  x17, x19
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x19]

    ldp  x29, x30, [sp, #0x00]
    ldp  x19, x20, [sp, #0x10]
    ldp  x0,  x1,  [sp, #0x20]
    ldp  x2,  x3,  [sp, #0x30]
    add  sp, sp, #0x50
    b    _ORIG_FUNC_PLUS4       // resume the original function exactly

.align 3
Lafk_name2:
    .asciz "AFKFirmwareService"
