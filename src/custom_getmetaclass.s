// Custom OSMetaClass *getMetaClass() override, installed at instance
// vtable slot 0 (offset 0x0). v10's instance vtable copied IOService's
// entire real vtable wholesale (safe, no singleton side effects) but that
// includes slot 0 unchanged, which returns IOService's OWN real metaclass
// pointer as a fixed immediate -- meaning our fake AFKFirmwareService
// instance was actually reporting its runtime class as "IOService" to
// anything that calls getMetaClass()/getClassName() on it (ioreg's tree
// display included), even though allocClassWithName("AFKFirmwareService")
// correctly found and constructed it via the real OSMetaClass class
// registry. Fixes identity reporting: return our own descriptor address
// (NEW_INSTANCE_ADDR) instead.

.extern _NEW_INSTANCE_ADDR

.text
.align 2
.globl _custom_getmetaclass
_custom_getmetaclass:
    bti  c
    adrp x0, _NEW_INSTANCE_ADDR@PAGE
    add  x0, x0, _NEW_INSTANCE_ADDR@PAGEOFF
    ret
