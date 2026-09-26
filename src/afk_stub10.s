// v9: corrects the plan from v5/v6/v7 (which patched start() on a BORROWED
// instance vtable — wrong, since the boot-time stub only runs once at
// mod_init_func time, long before IOKit's matching engine calls alloc() to
// create the actual instance). v9 instead overrides alloc() on the
// METACLASS DESCRIPTOR itself:
//   - custom_alloc (metaclass vtable slot 21, offset 0xa8) calls the REAL
//     IOResources::MetaClass::alloc() to get a properly constructed
//     instance, then repoints THAT instance's vtable at our custom
//     instance vtable (with start() patched) before returning it.
//   - custom_start (instance vtable slot 190, offset 0x5f0) calls the real
//     IOService::start(), and on success also calls the real
//     IOService::registerService() — which the inherited generic
//     IOService::start() never does on its own.
//
// This stub (chained onto the same mod_init_func slot as v5/v6/v7) builds
// both custom vtables once at boot by copying IOResources' real 30-entry
// metaclass vtable and real 272-entry instance vtable into fresh __DATA
// space, patching one slot in each, then constructs the AFKFirmwareService
// descriptor pointing at the custom metaclass vtable instead of directly
// at IOResources' real one.

.extern _OSMETACLASS_CTOR_BODY
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _IOSERVICE_INSTANCE_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _NEW_META_VTABLE_ADDR
.extern _NEW_INSTANCE_VTABLE_ADDR
.extern _CUSTOM_ALLOC_ADDR
.extern _CUSTOM_START_ADDR
.extern _ORIG_FUNC_PLUS8

.set STUB_CLASS_SIZE, 0x88
.set META_VTABLE_SLOTS, 30
.set INST_VTABLE_SLOTS, 272
.set ALLOC_SLOT_OFF, 0xa8
.set START_SLOT_OFF, 0x5f0
.set ALLOC_DIVERSIFIER, 0x1601
.set START_DIVERSIFIER, 0x3c68

.text
.align 2
.globl _afk_stub_init_v10
_afk_stub_init_v10:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    sub  sp, sp, #0x40
    stp  x29, x30, [sp, #0x00]
    stp  x0,  x1,  [sp, #0x10]
    stp  x2,  x3,  [sp, #0x20]

    // --- build custom instance vtable: copy IORESOURCES_INSTANCE_VTABLE ---
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
    adrp x1, Lafk_name9@PAGE
    add  x1, x1, Lafk_name9@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR_BODY

    // point the descriptor's own vtable at our CUSTOM metaclass vtable
    // (not directly at IOResources' real one, as v5/v6/v7 did)
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
Lafk_name9:
    .asciz "AFKFirmwareService"
