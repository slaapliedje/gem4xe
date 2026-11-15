#!/usr/bin/env python3
"""bankcheck.py -- refuse a cross-bank call that skips a veneer.

    python3 tools/bsp6502/bankcheck.py build/x.map [--elf build/x.elf]
    python3 tools/bsp6502/bankcheck.py --asm FILE.s --bank SECTION=N ...

Calypsi's 6502 banking is placement only (docs/6502.md): a call into a
bank is a plain `jsr` to the window address, and the linker says nothing
when the caller sits in another bank or in resident memory, where that
`jsr` lands in whatever bank happens to be mapped.  Two checks, because
neither source sees everything:

THE MAP'S CROSS REFERENCE.  Every fragment lists who refers to it, and a
banked fragment is held to: everything that refers to it is in its bank,
or is a veneer (resident code that maps the bank first), or is a resident
data fragment -- a switch table, a const table -- read only from that
bank.  But the map names GLOBAL symbols only: a call to a static function
is not in it at all, either end.  And it shortens a long list to "... 8
more" unless the link is --verbose, which this refuses to read past.

THE CODE ITSELF (--elf).  Every banked fragment, and every resident code
fragment but the veneers (whose .word/.byte are data), is decoded from
the linked bytes, and each JSR and JMP to an address in the window
$4000-$7FFF is held to:
  - from resident code: never (only a veneer may go there, via _bcall);
  - from bank B: the target is in bank B, and outside the caller's own
    fragment it is the start of one of bank B's fragments -- or at least
    not the start of another bank's (the optimiser's shared tails jump
    into the middle of a function in the same bank).
A call to a static function in another bank lands in the middle of
whatever this bank has at that address, which is how one was found:
vdi_v_gdp, bank 3, calling fill_perimeter, bank 2, and the CPU jamming on
the bytes of vdi_v_get_pixel.  (Indirect calls -- a function pointer --
are the map's to see, and the jump tables name veneers: src/portab.h.)

But an address is not a name: two banks' functions often start at the
same address -- $4000 above all -- and a call from one bank to the other's
function there looks, in the bytes, like a call to its own.  So:

THE ASSEMBLY (--asm), where every reference still has its name: each
banked file as tools/bsp6502/bankasm.py leaves it, every JSR, JMP, .word
and #.byte naming a function in a bank other than the referring line's
must name a veneer instead (resident data and code count as no bank).

A bank is the Store a fragment is scattered to: "(scatter to 10000-1001f
in Store1)" on its placement line.  Anything not scattered is resident.

Exit status 1 and a line per violation; 0 and the counts when clean.
"""
import re
import struct
import sys

HEAD = re.compile(r"^(?:(\S+) in section '([^']+)'|Section '([^']+)')(?:\s+placed at address.*)?$")
PLACE = re.compile(r"placed at address ([0-9a-f]+)-([0-9a-f]+) of size")
SCATTER = re.compile(r"\(scatter to ([0-9a-f]+)-([0-9a-f]+) in (\S+)\)")
UNIT = re.compile(r"^\((.+?) unit (\d+) section index (\d+)\)\s*$")
REF = re.compile(r"^\s+(\S+ )?\((.+?) unit (\d+) section index (\d+)\)\s*$")
MORE = re.compile(r"^\s+\.\.\. \d+ more\s*$")
CODE_SECTIONS = {"code", "startup"}
VENEER = "veneer"
WIN_LO, WIN_HI = 0x4000, 0x7FFF

# 6502 instruction lengths, by opcode; the undocumented ones as the NMOS
# part decodes them, so a sweep through data stays in step anyway
LEN = [1] * 256
for op in range(256):
    lo = op & 0x1F
    if op in (0x20, 0x4C, 0x6C):
        LEN[op] = 3
    elif lo in (0x0C, 0x0D, 0x0E, 0x0F, 0x19, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F):
        LEN[op] = 3
    elif lo in (0x01, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0B, 0x10, 0x11, 0x13,
                0x14, 0x15, 0x16, 0x17):
        LEN[op] = 2
    elif lo in (0x00, 0x02) and op & 0x80:      # LDY/CPY/CPX/LDX #imm, NOP #imm
        LEN[op] = 2
for op in (0x00, 0x40, 0x60):                   # BRK as one, RTI, RTS
    LEN[op] = 1
LEN[0x20] = 3


def parse(text):
    """Fragments by (unit, index): name, section, bank, run and store ranges,
    and referrers."""
    frags, truncated = {}, 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1) or ""
        sect = m.group(2) or m.group(3)
        place = lines[i]
        j = i + 1
        if j < len(lines) and lines[j].startswith(" placed at"):
            place += lines[j]
            j += 1
        p = PLACE.search(place)
        s = SCATTER.search(place)
        bank = s.group(3) if s else None
        key = None
        if j < len(lines):
            u = UNIT.match(lines[j])
            if u:
                key = (u.group(2), u.group(3))
                j += 1
        refs, mode = [], None
        while j < len(lines) and lines[j].strip() and not HEAD.match(lines[j]):
            t = lines[j].strip()
            if MORE.match(lines[j]):
                truncated += 1
            elif t.endswith(":"):
                mode = t[:-1]
            elif mode == "Referenced from":
                r = REF.match(lines[j])
                if r:
                    refs.append((r.group(3), r.group(4), (r.group(1) or "").strip()))
            j += 1
        if key:
            frags[key] = {"name": name, "section": sect, "bank": bank, "refs": refs,
                          "run": (int(p.group(1), 16), int(p.group(2), 16)) if p else None,
                          "store": (int(s.group(1), 16), int(s.group(2), 16)) if s else None}
        i = j
    return frags, truncated


def check_map(frags):
    bad = []
    for key, f in frags.items():
        b = f["bank"]
        if not b:
            continue
        for u, x, rname in f["refs"]:
            r = frags.get((u, x))
            if r is None:
                bad.append(f"{f['name'] or key} ({b}): referred to by an unknown fragment "
                           f"{rname or (u, x)}")
                continue
            if r["bank"] == b or r["section"] == VENEER:
                continue
            if r["bank"] is None and r["section"] not in CODE_SECTIONS:
                outside = [frags.get((uu, xx)) for uu, xx, _ in r["refs"]]
                if all(o is not None and o["bank"] == b for o in outside):
                    continue
            who = r["name"] or f"a fragment of section {r['section']}"
            bad.append(f"{f['name'] or 'a fragment'} in {b} ({f['section']}) is referred to "
                       f"from {who} in {r['bank'] or 'resident'} ({r['section']}) without a veneer")
    return bad


def load_elf(path):
    """Address -> bytes: run addresses below $10000, store addresses above."""
    d = open(path, "rb").read()
    (phoff,) = struct.unpack_from("<I", d, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
    mem = {}
    for i in range(phnum):
        t, off, vaddr, paddr, filesz, memsz, flags, align = struct.unpack_from(
            "<8I", d, phoff + i * phentsize)
        if t == 1 and filesz:
            if WIN_LO <= paddr <= WIN_HI:
                continue                # a bank at its run address: its store has it
            for k in range(filesz):
                mem[paddr + k] = d[off + k]
    return mem


def boundaries(f, mem):
    """The run addresses where a banked fragment's instructions start,
    decoding it from its first byte."""
    lo, hi = f["run"]
    base = f["store"][0] - lo
    out, pc = set(), lo
    while pc <= hi:
        op = mem.get(pc + base)
        if op is None:
            break
        out.add(pc)
        pc += LEN[op]
    return out


def check_code(frags, mem):
    bad, scanned = [], 0
    starts = {}                         # bank -> {run address of a fragment start}
    spans = {}                          # bank -> [(lo, hi)]
    insns = {}                          # bank -> {run address of an instruction}
    for f in frags.values():
        if f["bank"] and f["run"]:
            starts.setdefault(f["bank"], set()).add(f["run"][0])
            spans.setdefault(f["bank"], []).append(f["run"])
            insns.setdefault(f["bank"], set()).update(boundaries(f, mem))
    for f in frags.values():
        if not f["run"]:
            continue
        banked = f["bank"] is not None
        if not banked and (f["section"] not in CODE_SECTIONS):
            continue
        lo, hi = f["run"]
        base = f["store"][0] - lo if banked else 0
        pc = lo
        scanned += 1
        while pc <= hi:
            op = mem.get(pc + base)
            if op is None:
                break
            n = LEN[op]
            if op in (0x20, 0x4C) and pc + 2 <= hi:
                t = mem.get(pc + base + 1, 0) | (mem.get(pc + base + 2, 0) << 8)
                if WIN_LO <= t <= WIN_HI:
                    what = f"{'JSR' if op == 0x20 else 'JMP'} ${t:04X} at ${pc:04X} in " \
                           f"{f['name'] or f['section']} ({f['bank'] or 'resident'})"
                    if not banked:
                        bad.append(f"{what}: resident code jumps into the window")
                    elif not any(a <= t <= z for a, z in spans[f["bank"]]):
                        bad.append(f"{what}: nothing of this bank is there")
                    elif not (lo <= t <= hi) and t not in starts[f["bank"]]:
                        # inside one of this bank's fragments but not at its
                        # start: the optimiser's shared tails do that.  It is
                        # a cross-bank call when the address is where another
                        # bank's function starts -- unless it is a JMP onto
                        # an instruction of this bank's code: a shared tail
                        # is only ever jumped to, and the two banks' layouts
                        # can put a tail where another bank's function
                        # starts (antic_cursor_restore's, in step 3b).  A
                        # missed tail call by name is check_asm's.
                        others = [b for b, s in starts.items() if t in s and b != f["bank"]]
                        tail = op == 0x4C and t in insns[f["bank"]]
                        if others and not tail:
                            bad.append(f"{what}: not the start of anything in this bank "
                                       f"-- it is a function in {', '.join(others)}")
            pc += n
    return bad, scanned


ASM_SECTION = re.compile(r"^\s+\.section\s+([A-Za-z_][\w.]*)\s*(?:,\s*(\w+))?")
ASM_LABEL = re.compile(r"^([A-Za-z_]\w*):")
ASM_REF = re.compile(r"^\s*(?:[A-Za-z_]\w*:|`[^`]+`:)?\s*(jsr|jmp|\.word|lda|ldx|ldy|\.byte)\s+(.*)$")
ASM_TOKEN = re.compile(r"(?<![\w`?])([A-Za-z_]\w*)(?![\w`])")


def check_asm(path, banks):
    """Every reference by name to a function in another bank."""
    lines = open(path).read().splitlines()
    func, sect, first = {}, None, False
    for ln in lines:
        m = ASM_SECTION.match(ln)
        if m:
            sect = m.group(1)
            first = (m.group(2) or "") == "text" or sect in banks
            continue
        lab = ASM_LABEL.match(ln)
        if lab and first:
            func[lab.group(1)] = sect
        elif lab is None and ln.strip() and not ln.lstrip().startswith((";", ".")):
            first = False
    bad, sect = [], None
    for k, ln in enumerate(lines, 1):
        m = ASM_SECTION.match(ln)
        if m:
            sect = m.group(1)
            continue
        r = ASM_REF.match(ln)
        if not r or sect == "veneer":
            continue
        here = banks.get(sect, 0)
        for t in ASM_TOKEN.findall(r.group(2).split(";")[0]):
            fs = func.get(t)
            if fs is None or fs not in banks:
                continue
            if banks[fs] != here:
                bad.append(f"{path}:{k}: {r.group(1)} {t} -- in bank {banks[fs]}, from "
                           f"{'bank ' + str(here) if here else 'resident ' + str(sect)}")
    return bad


def main(argv):
    if "--asm" in argv:
        banks = {}
        for i, a in enumerate(argv):
            if a == "--bank":
                sct, n = argv[i + 1].split("=")
                banks[sct] = int(n)
        path = argv[argv.index("--asm") + 1]
        bad = check_asm(path, banks)
        for b in bad:
            print(f"bankcheck: {b}")
        print(f"bankcheck: {path}: {len(bad)} reference(s) across a bank by name")
        return 1 if bad else 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    frags, truncated = parse(open(argv[1], errors="replace").read())
    banked = sum(1 for f in frags.values() if f["bank"])
    bad = []
    if truncated:
        bad.append(f"{truncated} reference list(s) cut short ('... N more'): link with "
                   f"--verbose so the map lists them whole")
    bad += check_map(frags)
    scanned = 0
    if "--elf" in argv:
        more, scanned = check_code(frags, load_elf(argv[argv.index("--elf") + 1]))
        bad += more
    for b in bad:
        print(f"bankcheck: {b}")
    print(f"bankcheck: {argv[1]}: {len(frags)} fragments, {banked} banked, {scanned} decoded; "
          f"{len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
