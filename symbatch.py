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
    return "0x%x: %s +0x%x" % (pc, best[1], static - best[0])

addrs = """fffffe002bc2d5ac fffffe002bc2d9c0 fffffe002bc29140 fffffe002bc2821c
fffffe002bc3681c fffffe002bd7cd70 fffffe002c52e0c8 fffffe002bd81030
fffffe002bc28048 fffffe002bc7c5d4 fffffe002bc18524 fffffe002bc297e4""".split()
for a in addrs:
    print(sym(int(a, 16)))
