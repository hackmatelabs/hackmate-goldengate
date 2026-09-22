import json, sys

syms = json.load(open("/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/bootkc.symbols.json"))
items = sorted((int(k), v) for k, v in syms.items())

def sym(pc):
    static = pc - 0x20000000
    lo, hi = 0, len(items) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if items[mid][0] <= static:
            best = items[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return "static 0x%x: no symbol" % static
    return "runtime 0x%x static 0x%x: %s +0x%x" % (pc, static, best[1], static - best[0])

for arg in sys.argv[1:]:
    print(sym(int(arg, 16)))
