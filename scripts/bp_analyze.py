import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

BASE = 0x19DFB4000
blob = open("/Users/raahimsyed/libbootpolicy_text.bin", "rb").read()
print("blob size", hex(len(blob)))

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True

# decode all instructions, index by file offset
insns = {}
for ins in md.disasm(blob, BASE):
    off = ins.address - BASE
    if 0 <= off < len(blob):
        insns[off] = ins
print("decoded", len(insns), "insns")

# find interesting data refs
needles = [b"com.apple.BootPolicy", b"com.apple.security.bootpolicy",
           b"IOConnectCallStructMethod", b"BootPolicy: %s: entry",
           b"Disable sleep for BootPolicy", b"AppleCredentialManager",
           b"bootpolicy_get_current_os_type", b"IOService",
           b"BootPolicy: failed to create power assertion",
           b"LocalPolicy", b"boot-uuid", b"IONVRAM"]
data_addrs = {}
for n in needles:
    i = blob.find(n)
    if i >= 0:
        data_addrs[BASE + i] = (n.decode(), i)
        print("data 0x%x fileoff 0x%x %s" % (BASE + i, i, n.decode()))
    else:
        print("data MISS", n.decode())

# function starts: pacibsp
PACIBSP = 0xD503233F
starts = set()
for off in range(0, len(blob) - 4, 4):
    if struct.unpack_from("<I", blob, off)[0] == PACIBSP:
        starts.add(off)
starts = sorted(starts)
print("prologue candidates", len(starts))

def func_start(off):
    lo, hi = 0, len(starts) - 1
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if starts[mid] <= off:
            best = starts[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best

# xref scan: adrp page + add/ldr/adr
def adrp_target(ins_off, ins):
    # adrp: immhi:immlo -> page
    w = struct.unpack_from("<I", blob, ins_off)[0]
    immlo = (w >> 29) & 0x3
    immhi = (w >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    if imm & 0x100000:
        imm -= 0x200000
    page = (BASE + ins_off) & ~0xFFF
    return page + imm * 0x1000

hits = {}  # func_off -> list of (ins_off, text, target)
for off, ins in insns.items():
    t = None
    if ins.mnemonic == "adrp":
        try:
            page = adrp_target(off, ins)
        except Exception:
            continue
        nxt = insns.get(off + 4)
        if nxt is None:
            continue
        if nxt.mnemonic in ("add", "sub") and len(nxt.operands) == 3:
            try:
                imm = nxt.operands[2].imm
            except Exception:
                continue
            t = page + imm if nxt.mnemonic == "add" else page - imm
        elif nxt.mnemonic == "ldr":
            try:
                t = page + nxt.operands[1].mem.disp
            except Exception:
                continue
        elif nxt.mnemonic == "adr":
            try:
                t = page + nxt.operands[1].imm
            except Exception:
                continue
    elif ins.mnemonic == "adr":
        try:
            t = ins.address + ins.operands[1].imm
        except Exception:
            continue
    if t is not None and t in data_addrs:
        f = func_start(off)
        hits.setdefault(f, []).append((off, ins.mnemonic + " " + ins.op_str, t))

for f in sorted(hits):
    name, foff = data_addrs[hits[f][0][2]]
    print("FUNC fileoff 0x%x vaddr 0x%x refs %d e.g. %s" % (f, BASE + f, len(hits[f]), name))

import sys
want = sys.argv[1] if len(sys.argv) > 1 else "all"
for f in sorted(hits):
    if want != "all" and ("%x" % f) not in want:
        continue
    print("===== FUNC 0x%x =====" % (BASE + f))
    # disassemble until ret (capstone group?) - walk forward max 400 insns
    off = f
    n = 0
    nxt_func = starts[starts.index(f) + 1] if f in starts and starts.index(f) + 1 < len(starts) else len(blob)
    while off < nxt_func and n < 600:
        ins = insns.get(off)
        if ins is None:
            off += 4
            continue
        line = "0x%x %s %s" % (ins.address, ins.mnemonic, ins.op_str)
        # annotate string refs
        for (h_off, h_txt, t) in hits.get(f, []):
            if h_off in (off, off - 4):
                nm, _ = data_addrs[t]
                line += "   ; -> %r" % nm
        print(line)
        n += 1
        if ins.mnemonic == "ret":
            break
        off += 4
