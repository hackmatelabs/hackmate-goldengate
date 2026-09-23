// AFKFirmwareService minimal stub metaclass registration
// Chained onto com.apple.kernel's last __mod_init_func entry.

.extern _ORIG_INIT_FUNC
.extern _OSMETACLASS_CTOR
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _NEW_INSTANCE_ADDR

.set STUB_CLASS_SIZE, 0x88

.text
.align 2
.globl _afk_stub_init
_afk_stub_init:
    pacibsp
    stp fp, lr, [sp, #-0x30]!
    mov fp, sp
    stp x19, x20, [sp, #0x10]
    stp x21, x22, [sp, #0x20]

    // 1) run the original init function first, exactly as before
    bl _ORIG_INIT_FUNC

    // 2) construct a new OSMetaClass instance named "AFKFirmwareService"
    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name@PAGE
    add  x1, x1, Lafk_name@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR

    // 3) overwrite the new instance's vtable ptr with IOResources::MetaClass's
    //    real vtable, re-signed for THIS instance's address (same scheme the
    //    real constructor just used: pacda with modifier = (this, 0xcda1))
    adrp x16, _IORESOURCES_METACLASS_VTABLE@PAGE
    add  x16, x16, _IORESOURCES_METACLASS_VTABLE@PAGEOFF
    mov  x17, x19
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x19]

    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp fp, lr, [sp], #0x30
    retab

.align 3
Lafk_name:
    .asciz "AFKFirmwareService"
