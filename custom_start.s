// Custom IOService::start() override, installed at instance vtable slot
// 190 (offset 0x5f0) for our custom instance vtable (see afk_stub9.s).
// Called via blraa with x0=this, x1=provider. Forwards to the real
// IOService::start(), and on success also calls the real
// IOService::registerService() — which the generic inherited start()
// never does on its own, and which is required for the driver-matching
// engine to continue past this stub instance.

.extern _REAL_IOSERVICE_START
.extern _REAL_REGISTERSERVICE

.text
.align 2
.globl _custom_start
_custom_start:
    pacibsp
    stp  fp,  lr,  [sp, #-0x10]!
    mov  fp, sp
    stp  x19, x20, [sp, #-0x10]!
    stp  x21, xzr, [sp, #-0x10]!

    mov  x19, x0                   // save this
    mov  x20, x1                   // save provider

    bl   _REAL_IOSERVICE_START     // x0=this, x1=provider already in place
    mov  w21, w0                   // save real start()'s bool result

    tbz  w21, #0, Lcustom_start_ret

    mov  x0, x19
    mov  x1, #0
    bl   _REAL_REGISTERSERVICE

Lcustom_start_ret:
    mov  w0, w21
    ldp  x21, xzr, [sp], #0x10
    ldp  x19, x20, [sp], #0x10
    ldp  fp,  lr,  [sp], #0x10
    retab
