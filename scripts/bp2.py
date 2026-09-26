import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

P07 = "/Volumes/macOS Base System/System/Library/dyld/dyld_shared_cache_arm64e.07"
ANCHOR = 96419110  # file offset of 'com.apple.BootPolicy' cstring
W0 = ANCHOR - 0x50000
with open(P07, "rb") as f:
    f.seek(W0)
    blob = f.read(0x58000)
print("window fileoff 0x%x size 0x%x" % (W0, len(blob)))

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False

insns = {}
total = 0
CH = 0x10000
for base in range(0, len(blob), CH):
    chunk = blob[base:base + CH]
    n = 0
    for ins in md.disasm(chunk, base):
        insns[ins.address] = (ins.mnemonic, ins.op_str)
        n += 1
    total += n
print("decoded", total)

needles = [b"com.apple.BootPolicy", b"BootPolicy: IOConnectCallStructMethod returned %d",
           b"BootPolicy: %s: entry", b"Disable sleep for BootPolicy transaction",
           b"BootPolicy: failed to create power assertion",
           b"bootpolicy_get_current_os_type", b"connect != ((io_object_t) 0)",
           b"service != ((io_object_t) 0)", b"kr == 0 ",
           b"BootPolicy: failed to obtain the proposed local policy nonce"]
nd = {}
for n in needles:
    i = blob.find(n)
    print(("found 0x%x  " % i if i >= 0 else "MISS ") + n.decode())
    if i >= 0:
        nd[i] = n.decode()

PAC = b"\x3f\x23\x03\xd5"
starts = []
for off in range(0, len(blob) - 4, 4):
    if blob[off:off + 4] == PAC:
        starts.append(off)
print("pacibsp count", len(starts))

def func_of(off):
    best = 0
    lo, hi = 0, len(starts) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if starts[mid] <= off:
            best = starts[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best

def adrp_imm(w):
    immlo = (w >> 29) & 0x3
    immhi = (w >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

# pass 1: adrp/add/ldr/adr refs to needles
hits = {}
for off in sorted(insns):
    m, op = insns[off]
    t = None
    w = struct.unpack_from("<I", blob, off)[0]
    if m == "adrp":
        page = ((W0 + off) & ~0xFFF) + adrp_imm(w)
        nxt = insns.get(off + 4)
        if nxt is None:
            continue
        m2, op2 = nxt
        parts = op2.split(",")
        if m2 in ("add", "sub") and len(parts) == 3 and "#" in parts[2]:
            try:
                imm = int(parts[2].split("#")[1].split()[0], 16)
            except Exception:
                continue
            t = page + imm if m2 == "add" else page - imm
        elif m2 == "ldr" and len(parts) == 2 and "#" in parts[1]:
            try:
                imm = int(parts[1].split("#")[1].split()[0], 16)
            except Exception:
                continue
            t = page + imm
    if t is not None:
        rel = t - W0
        if rel in nd:
            f = func_of(off)
            hits.setdefault(f, []).append((off, m, rel))

for f in sorted(hits):
    desc = ", ".join(sorted(set(nd[r] for (_, _, r) in hits[f])))
    print("FUNC 0x%x refs %d :: %s" % (f, len(hits[f]), desc[:110]))

# pass 2: find BL callers of each hit function
blmap = {}
for off in sorted(insns):
    m, op = insns[off]
    if m == "bl" and op.startswith("#"):
        try:
            tgt = int(op[1:], 16)
        except Exception:
            continue
        # capstone arm64 prints bl target as absolute address (base+offset math)
        rel = tgt - 0  # ins.address was file-relative; target likewise file-relative
        blmap.setdefault(rel, []).append(off)

import sys
sel = sys.argv[1] if len(sys.argv) > 1 else "all"
for f in sorted(hits):
    if sel != "all" and sel not in ("%x" % f):
        continue
    print("===== FUNC fileoff 0x%x =====" % f)
    callers = blmap.get(f, [])
    print("called from %d sites: %s" % (len(callers), [hex(c) for c in callers[:10]]))
    idx = starts.index(f)
    end = starts[idx + 1] if idx + 1 < len(starts) else len(blob)
    off = f
    n = 0
    while off < end and n < 500:
        if off in insns:
            m, op = insns[off]
            line = "0x%x %s %s" % (off, m, op)
            for (h, hm, r) in hits.get(f, []):
                if h == off or h == off - 4:
                    line += "   ; -> %r" % nd[r]
            print(line)
            n += 1
            if m == "ret":
                break
            off += 4
        else:
            off += 4
