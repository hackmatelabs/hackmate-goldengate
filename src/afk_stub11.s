// v11: adds one more fix on top of v10. v10's custom instance vtable
// copied IOService's entire real vtable wholesale (safe, singleton-free)
// but left slot 0 (getMetaClass, offset 0x0) pointing at IOService's own
// real implementation, which returns IOService's real metaclass pointer
// as a fixed immediate. That means our fake AFKFirmwareService instance
// was reporting its own runtime class as "IOService" to anything calling
// getMetaClass()/getClassName() on it -- including ioreg's tree display --
// even though allocClassWithName("AFKFirmwareService") correctly found
// and constructed it via the real OSMetaClass class registry. v11 patches
// slot 0 too, with a custom_getmetaclass that returns our own descriptor
// address instead.

.extern _OSMETACLASS_CTOR_BODY
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _IOSERVICE_INSTANCE_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _NEW_META_VTABLE_ADDR
.extern _NEW_INSTANCE_VTABLE_ADDR
.extern _CUSTOM_ALLOC_ADDR
.extern _CUSTOM_START_ADDR
.extern _CUSTOM_GETMETACLASS_ADDR
.extern _ORIG_FUNC_PLUS8

.set STUB_CLASS_SIZE, 0x88
.set META_VTABLE_SLOTS, 30
.set INST_VTABLE_SLOTS, 272
.set ALLOC_SLOT_OFF, 0xa8
.set START_SLOT_OFF, 0x5f0
.set GETMETACLASS_SLOT_OFF, 0x0
.set ALLOC_DIVERSIFIER, 0x1601
.set START_DIVERSIFIER, 0x3c68
.set GETMETACLASS_DIVERSIFIER, 0x3771

.text
.align 2
.globl _afk_stub_init_v11
_afk_stub_init_v11:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    sub  sp, sp, #0x40
    stp  x29, x30, [sp, #0x00]
    stp  x0,  x1,  [sp, #0x10]
    stp  x2,  x3,  [sp, #0x20]

    // --- build custom instance vtable: copy IOSERVICE_INSTANCE_VTABLE ---
    adrp x9,  _IOSERVICE_INSTANCE_VTABLE@PAGE
    add  x9,  x9, _IOSERVICE_INSTANCE_VTABLE@PAGEOFF
    adrp x10, _NEW_INSTANCE_VTABLE_ADDR@PAGE
    add  x10, x10, _NEW_INSTANCE_VTABLE_ADDR@PAGEOFF
    mov  x11, #INST_VTABLE_SLOTS
Lcopy_inst_vt:
    ldr  x12, [x9], #8
    str  x12, [x10], #8
    subs x11, x11, #1
    b.ne Lcopy_inst_vt

    // patch slot 190 (start) with pacia-signed custom_start
    adrp x24, _CUSTOM_START_ADDR@PAGE
    add  x24, x24, _CUSTOM_START_ADDR@PAGEOFF
    mov  x25, #START_DIVERSIFIER
    pacia x24, x25
    adrp x10, _NEW_INSTANCE_VTABLE_ADDR@PAGE
    add  x10, x10, _NEW_INSTANCE_VTABLE_ADDR@PAGEOFF
    str  x24, [x10, #START_SLOT_OFF]

    // patch slot 0 (getMetaClass) with pacia-signed custom_getmetaclass
    adrp x24, _CUSTOM_GETMETACLASS_ADDR@PAGE
    add  x24, x24, _CUSTOM_GETMETACLASS_ADDR@PAGEOFF
    mov  x25, #GETMETACLASS_DIVERSIFIER
    pacia x24, x25
    adrp x10, _NEW_INSTANCE_VTABLE_ADDR@PAGE
    add  x10, x10, _NEW_INSTANCE_VTABLE_ADDR@PAGEOFF
    str  x24, [x10, #GETMETACLASS_SLOT_OFF]

    // --- build custom metaclass vtable: copy IORESOURCES_METACLASS_VTABLE ---
    adrp x9,  _IORESOURCES_METACLASS_VTABLE@PAGE
    add  x9,  x9, _IORESOURCES_METACLASS_VTABLE@PAGEOFF
    adrp x10, _NEW_META_VTABLE_ADDR@PAGE
    add  x10, x10, _NEW_META_VTABLE_ADDR@PAGEOFF
    mov  x11, #META_VTABLE_SLOTS
Lcopy_meta_vt:
    ldr  x12, [x9], #8
    str  x12, [x10], #8
    subs x11, x11, #1
    b.ne Lcopy_meta_vt

    // patch slot 21 (alloc) with pacia-signed custom_alloc
    adrp x24, _CUSTOM_ALLOC_ADDR@PAGE
    add  x24, x24, _CUSTOM_ALLOC_ADDR@PAGEOFF
    mov  x25, #ALLOC_DIVERSIFIER
    pacia x24, x25
    adrp x10, _NEW_META_VTABLE_ADDR@PAGE
    add  x10, x10, _NEW_META_VTABLE_ADDR@PAGEOFF
    str  x24, [x10, #ALLOC_SLOT_OFF]

    // --- construct the AFKFirmwareService descriptor ---
    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name11@PAGE
    add  x1, x1, Lafk_name11@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR_BODY

    // point the descriptor's own vtable at our CUSTOM metaclass vtable
    adrp x16, _NEW_META_VTABLE_ADDR@PAGE
    add  x16, x16, _NEW_META_VTABLE_ADDR@PAGEOFF
    mov  x17, x19
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x19]

    ldp  x29, x30, [sp, #0x00]
    ldp  x0,  x1,  [sp, #0x10]
    ldp  x2,  x3,  [sp, #0x20]
    add  sp, sp, #0x40
    b    _ORIG_FUNC_PLUS8

.align 3
Lafk_name11:
    .asciz "AFKFirmwareService"
