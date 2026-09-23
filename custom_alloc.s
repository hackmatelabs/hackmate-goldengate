// Custom OSMetaClass::alloc() override, installed at metaclass vtable slot
// 21 (offset 0xa8) for our AFKFirmwareService descriptor's CUSTOM metaclass
// vtable (see afk_stub9.s). Called via blraa (this = the metaclass
// descriptor, which our real target never actually reads from — see
// REAL_IORESOURCES_ALLOC's own disassembly, which sources its classSize
// and zone tag from fixed immediates baked into its own code, not from
// `this`). We call it directly to get a properly allocated+constructed
// real IOResources-shaped instance, then repoint that instance's vtable
// pointer at our custom instance vtable (with start() patched) before
// returning it.

.extern _REAL_IORESOURCES_ALLOC
.extern _NEW_INSTANCE_VTABLE_ADDR

.text
.align 2
.globl _custom_alloc
_custom_alloc:
    pacibsp
    stp  fp, lr, [sp, #-0x10]!
    mov  fp, sp

    bl   _REAL_IORESOURCES_ALLOC   // x0 = newly allocated+constructed instance

    mov  x9, x0
    adrp x16, _NEW_INSTANCE_VTABLE_ADDR@PAGE
    add  x16, x16, _NEW_INSTANCE_VTABLE_ADDR@PAGEOFF
    mov  x17, x9
    movk x17, #0xcda1, lsl #48
    pacda x16, x17
    str  x16, [x9]
    mov  x0, x9

    ldp  fp, lr, [sp], #0x10
    retab
