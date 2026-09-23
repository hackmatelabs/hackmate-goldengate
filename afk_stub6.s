// v6: registers BOTH AFKFirmwareService AND AFKResource (a sibling
// class also confirmed missing from this kernelcache), using the same
// proven technique from v5 (call the real constructor body directly at
// 0xfffffe000c33438c, then set the vtable to IOResources::MetaClass's
// real, working vtable, re-signed for each new instance).

.extern _OSMETACLASS_CTOR_BODY
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _NEW_INSTANCE2_ADDR
.extern _ORIG_FUNC_PLUS8

.set STUB_CLASS_SIZE, 0x88

.text
.align 2
.globl _afk_stub_init_v6
_afk_stub_init_v6:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    sub  sp, sp, #0x40
    stp  x29, x30, [sp, #0x00]     // save fp/lr - lr is the true caller return addr
    stp  x0,  x1,  [sp, #0x10]
    stp  x2,  x3,  [sp, #0x20]

    // --- register AFKFirmwareService ---
    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name6@PAGE
    add  x1, x1, Lafk_name6@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR_BODY

    adrp x16, _IORESOURCES_METACLASS_VTABLE@PAGE
    add  x16, x16, _IORESOURCES_METACLASS_VTABLE@PAGEOFF
    mov  x17, x19
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x19]

    // --- register AFKResource ---
    adrp x19, _NEW_INSTANCE2_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE2_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafkres_name6@PAGE
    add  x1, x1, Lafkres_name6@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR_BODY

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
Lafk_name6:
    .asciz "AFKFirmwareService"
.align 3
Lafkres_name6:
    .asciz "AFKResource"
