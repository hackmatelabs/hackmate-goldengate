import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

F = "/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4"
data = open(F, "rb").read()

TEXTOFF, TEXTLEN = 0xA0000, 0x60000
blob = data[TEXTOFF:TEXTOFF + TEXTLEN]

TARGETS = {
    0xFFFFFFF02701019B: "VIOLATION_DOUBLE_NEST",
    0xFFFFFFF027012B7C: "expected_shared_region",
}

def adrp_imm(w):
    immlo = (w >> 29) & 0x3
    immhi = (w >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    if imm & 0x100000:
        imm -= 0x200000
    return imm * 0x1000

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = False
insns = {}
for ins in md.disasm(blob, TEXTOFF):
    insns[ins.address] = (ins.mnemonic, ins.op_str)

print("decoded", len(insns))
for off in sorted(insns):
    (m, op) = insns[off]
    if m != "adrp":
        continue
    w = struct.unpack_from("<I", blob, off - TEXTOFF)[0]
    # VA of this insn:
    va = 0xFFFFFFF0270A4000 + (off - TEXTOFF)
    page = va & ~0xFFF
    tpage = page + adrp_imm(w)
    nxt = insns.get(off + 4)
    if nxt is None:
        continue
    (m2, op2) = nxt
    t = None
    if m2 in ("add", "sub"):
        parts = op2.split(",")
        if len(parts) == 3 and "#" in parts[2]:
            try:
                imm = int(parts[2].split("#")[1].split()[0], 16)
            except Exception:
                continue
            t = tpage + imm if m2 == "add" else tpage - imm
    elif m2 == "ldr":
        parts = op2.split(",")
        if len(parts) == 2 and "#" in parts[1]:
            try:
                imm = int(parts[1].split("#")[1].split()[0], 16)
            except Exception:
                continue
            t = tpage + imm
    elif m2 == "adr":
        try:
            t = va + 4 + int(op2.split("#")[1].split()[0], 16)
        except Exception:
            continue
    if t in TARGETS:
        print("HIT fileoff 0x%x -> %s via %s %s / %s %s" % (off, TARGETS[t], m, op, m2, op2))
