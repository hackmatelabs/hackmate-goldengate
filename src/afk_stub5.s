// AFKFirmwareService minimal stub metaclass registration, v5.
// Fixes v3's root cause: v3 called 0xfffffe000c334364, which is NOT a
// standalone constructor entry point - it's a mid-function `bl`
// instruction belonging to a DIFFERENT class's own private static
// initializer (mod_init_func entry[1]). Calling it directly skipped
// that caller's own prologue (which pushes fp/lr that a LATER shared
// epilogue depends on), corrupting the eventual retab.
//
// v5 calls the REAL, self-contained, reusable constructor body
// directly at 0xfffffe000c33438c, which has its own complete
// pacibsp...retab pair (confirmed via disassembly - retab at
// 0xfffffe000c334508, no other pacibsp in between). This has no
// caller-specific dependencies, so it should return cleanly to
// whatever a real bl sets as LR. Also does the vtable-set myself
// directly to IOResources::MetaClass's vtable (the real body doesn't
// set any vtable itself - that was part of entry[1]'s own later
// epilogue code, which we're no longer using at all).

.extern _OSMETACLASS_CTOR_BODY
.extern _IOSERVICE_GMETACLASS
.extern _IORESOURCES_METACLASS_VTABLE
.extern _NEW_INSTANCE_ADDR
.extern _ORIG_FUNC_PLUS8

.set STUB_CLASS_SIZE, 0x88

.text
.align 2
.globl _afk_stub_init_v5
_afk_stub_init_v5:
    stp  x20, x19, [sp, #-0x20]!   // replay the overwritten original instruction
    sub  sp, sp, #0x40
    stp  x29, x30, [sp, #0x00]     // save fp/lr - lr is the true caller return addr
    stp  x0,  x1,  [sp, #0x10]
    stp  x2,  x3,  [sp, #0x20]

    adrp x19, _NEW_INSTANCE_ADDR@PAGE
    add  x19, x19, _NEW_INSTANCE_ADDR@PAGEOFF
    mov  x0, x19
    adrp x1, Lafk_name5@PAGE
    add  x1, x1, Lafk_name5@PAGEOFF
    adrp x2, _IOSERVICE_GMETACLASS@PAGE
    add  x2, x2, _IOSERVICE_GMETACLASS@PAGEOFF
    mov  w3, #STUB_CLASS_SIZE
    bl   _OSMETACLASS_CTOR_BODY

    // set the vtable directly to IOResources::MetaClass's real vtable,
    // re-signed for THIS instance's address
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
Lafk_name5:
    .asciz "AFKFirmwareService"
