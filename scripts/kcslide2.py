# Derive slide from ...821c (known static via file pattern), then map panic addrs.
STATIC_821C = 0xFFFFFE000BC2410C  # file 0x4C2410C + delta 0x7004000 (capstone-verified callers)
RT_821C = 0xFFFFFE002BC28120      # runtime on netboot3-panic boot
SLIDE = RT_821C - STATIC_821C
print("derived slide: 0x%x" % SLIDE)

addrs = {
    "c0bd04": 0xFFFFFE002BC0BD04,
    "c3cf700": 0xFFFFFE002BC3CF700,
    "c291ac_9140": 0xFFFFFE002BC29140,
    "BP_kext_start": 0xFFFFFE002A2A0110,
    "BP_kext_end": 0xFFFFFE002A2A26B3,
    "RTBuddy_start": 0xFFFFFE002B645B60,
}

SEGS = [
    ("__TEXT", 0xFFFFFE0007004000, 0x8000, 0x0),
    ("__PRELINK_TEXT", 0xFFFFFE000700C000, 0xDE8000, 0x8000),
    ("__DATA_CONST", 0xFFFFFE0007DF4000, 0xC74000, 0xDF0000),
    ("__DATA_SPTM", 0xFFFFFE0008A68000, 0x74000, 0x1A64000),
    ("__TEXT_EXEC", 0xFFFFFE0008ADC000, 0x3A70000, 0x1AD8000),
    ("__TEXT_BOOT_EXEC", 0xFFFFFE000C54C000, 0x8000, 0x5548000),
    ("__PRELINK_INFO", 0xFFFFFE000C554000, 0x3C4000, 0x5550000),
    ("__DATA", 0xFFFFFE000C918000, 0x3D4000, 0x5914000),
    ("__LINKEDIT", 0xFFFFFE000CCEC000, 0x1A54000, 0x5CE8000),
]

for (name, rt) in addrs.items():
    st = rt - SLIDE
    seg = None
    for (sn, va, vsz, fo) in SEGS:
        if va <= st < va + vsz:
            seg = (sn, "fileoff 0x%x" % (st - va + fo))
            break
    print("%-14s runtime 0x%x -> static 0x%x -> %s" % (name, rt, st, seg))
