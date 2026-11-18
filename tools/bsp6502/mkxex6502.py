#!/usr/bin/env python3
"""mkxex6502.py -- a banked 6502 link as an Atari binary file.

    python3 tools/bsp6502/mkxex6502.py IN.elf OUT.xex [--report] [--bank N=PROG.elf ...]
    python3 tools/bsp6502/mkxex6502.py --g6a PROG.elf OUT.G6A

--g6a writes a separately linked program (src/app/gemapp6502.scm) as the
file gem4xe reads into a program slot from a disk (docs/6502.md, step
5b): its window segments as one image from $4000, gaps zero, nothing
after its last byte.  Its first bytes are its header, "G6" and the
format, 1 (src/app/crt6502.s); a file that does not start so, or that
has anything outside the window, is refused.

A PROGRAM OF SEVERAL BANKS (src/app/gemappm6502.scm, docs/6502.md step
5c-1) is format 2: its banks stored from $10000 as the system's are, and
its veneers, runtime and data in the RAM under the OS ROM.  Its .G6A:

    $00  "G6", 2, n          the magic, the format, its banks (1..15)
    $04  p, 0                its pieces under the ROM (0..2)
    $06  p x (addr, len)     each piece's address and length, two words
         n x len             each bank's length, a word
         the pieces' bytes, then the banks', in that order

A piece may be in $C020-$CFFF or $D800-$FDFF and nowhere else -- not the
chips, not the link block the loader fills at $C000, not the system's
$FE00-$FFFF -- and bank 1 must begin with its header, "G6", 2.  The
loader (src/a6_evt.c) checks the same.

--bank N=PROG.elf loads a separately linked program's window segments
($4000-$7FFF: src/app/gemapp6502.scm) into PORTB bank N as well, as if
it were one of the link's own banks -- the program slot of docs/6502.md,
step 5a.  N must be no bank of the link's.

The link (tools/bsp6502/gem6502.scm) puts resident code and data below
$4000 and above $8000, and each bank's code at $4000-$7FFF with its bytes
stored at $10000 + (n-1) * $4000.  A DOS's binary loader puts a segment
where its header says and knows nothing of banks, so the file says it
with INITAD, which the loader calls as soon as the segment that sets it
is in (src/sys6502/bank6502.s):

    the resident segments
    INITAD b6_probe              which PORTB values are banks
    for each bank n:
        b6_next = n              a one-byte segment
        INITAD b6_sel            bank n into the window
        $4000-...                the bank's code
    INITAD b6_main               main memory back
    RUNAD  the entry

Checks what would fail silently: a segment in the window that is not a
bank's, a bank stored where no bank number goes, and the trampoline's
JMP (bc_t) on a page's last byte, which the 6502 reads wrongly.

And writes b6_sites: the address of every bank switch (each public
label b6sw_*, checked to be LDA b6_portb,X/Y then STA PORTB), which
src/sys6502/bank6502.s rewrites to STA $CFFF on an Axlon's machine.
"""
import struct
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elfsym import Elf  # noqa: E402

STORE = 0x10000
BANK = 0x4000
WIN_LO, WIN_HI = 0x4000, 0x7FFF
INITAD, RUNAD = 0x02E2, 0x02E0


def segments(data):
    (phoff,) = struct.unpack_from("<I", data, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", data, 0x2A)
    (entry,) = struct.unpack_from("<I", data, 0x18)
    out = []
    for i in range(phnum):
        t, off, vaddr, paddr, filesz, memsz, flags, align = struct.unpack_from(
            "<8I", data, phoff + i * phentsize)
        if t == 1 and filesz:
            out.append((paddr, data[off:off + filesz]))
    return entry, out


def seg(start, body):
    return struct.pack("<HH", start, start + len(body) - 1) + bytes(body)


SHARED = ((0xC020, 0xCFFF), (0xD800, 0xFDFF))   # under the ROM, a program's
G6_BANKS = 15
G6_LINK = 0xC000                        # src/app/crt6502m.s's link block


def g6a2(elf, out, segs):
    """Format 2: see the head of the file."""
    banks, pieces = {}, []
    for a, body in sorted(segs):
        end = a + len(body) - 1
        if WIN_LO <= a and end <= WIN_HI:
            continue                    # a bank's run copy: its store is the one
        if G6_LINK <= a and end < G6_LINK + 0x20:
            if any(body):
                raise SystemExit(f"mkxex6502: --g6a: {elf}: the link block at "
                                 f"${G6_LINK:04X} has bytes; the loader fills it")
            continue
        if a >= STORE:
            k = (a - STORE) // BANK + 1
            if (end - STORE) // BANK + 1 != k or k > G6_BANKS:
                raise SystemExit(f"mkxex6502: --g6a: {elf}: a segment at ${a:X} is in "
                                 f"no one bank 1..{G6_BANKS}")
            img = banks.setdefault(k, bytearray())
            o = (a - STORE) % BANK
            if len(img) < o:
                img += bytes(o - len(img))
            img[o:o + len(body)] = body
        elif any(lo <= a and end <= hi for lo, hi in SHARED):
            if pieces and pieces[-1][0] + len(pieces[-1][1]) <= a and \
                    any(lo <= pieces[-1][0] and end <= hi for lo, hi in SHARED):
                p0, pb = pieces[-1]
                pb += bytes(a - p0 - len(pb)) + body
            else:
                pieces.append((a, bytearray(body)))
        else:
            raise SystemExit(f"mkxex6502: --g6a: {elf} has a segment at ${a:X}-${end:X}, "
                             f"in no bank and not under the ROM ({SHARED})")
    n = max(banks) if banks else 0
    if sorted(banks) != list(range(1, n + 1)):
        raise SystemExit(f"mkxex6502: --g6a: {elf}: banks {sorted(banks)}, not 1..n")
    if len(pieces) > 2:
        raise SystemExit(f"mkxex6502: --g6a: {elf}: {len(pieces)} pieces under the ROM, "
                         f"room for 2")
    if banks[1][:3] != b"G6\x02":
        raise SystemExit(f"mkxex6502: --g6a: {elf}: bank 1 does not start with its "
                         f"header (\"G6\", 2 at $4000)")
    head = bytes([ord("G"), ord("6"), 2, n, len(pieces), 0])
    head += b"".join(struct.pack("<HH", a, len(b)) for a, b in pieces)
    head += b"".join(struct.pack("<H", len(banks[k])) for k in range(1, n + 1))
    data = head + b"".join(bytes(b) for _, b in pieces) + \
        b"".join(bytes(banks[k]) for k in range(1, n + 1))
    open(out, "wb").write(data)
    print(f"{out}: format 2, {len(data)} bytes: {n} bank(s) of "
          f"{', '.join(str(len(banks[k])) for k in range(1, n + 1))} bytes; under the ROM "
          f"{', '.join(f'${a:04X}+{len(b)}' for a, b in pieces)}")
    return 0


def g6a(elf, out):
    _, segs = segments(open(elf, "rb").read())
    if any(a >= STORE or a >= 0xC000 for a, _ in segs):
        return g6a2(elf, out, segs)
    img = bytearray()
    for a, body in sorted(segs):
        if not (WIN_LO <= a and a + len(body) - 1 <= WIN_HI):
            raise SystemExit(f"mkxex6502: --g6a: {elf} has a segment at ${a:X}, "
                             f"outside the window")
        o = a - WIN_LO
        if len(img) < o:
            img += bytes(o - len(img))
        img[o:o + len(body)] = body
    if img[:3] != b"G6\x01":
        raise SystemExit(f"mkxex6502: --g6a: {elf} does not start with its header "
                         f"(\"G6\", 1 at $4000)")
    open(out, "wb").write(img)
    print(f"{out}: {len(img)} bytes, ${WIN_LO:04X}-${WIN_LO + len(img) - 1:04X}")
    return 0


SITES = 15                              # src/sys6502/bank6502.s's B6_SITES


def sites(segs, syms, addr, elf):
    """Every bank switch, b6sw_*, into b6_sites, then a zero: what
    bank6502.s's patch makes write an Axlon's register instead of PORTB.
    Each is checked to be LDA b6_portb,X/Y and STA PORTB, as patch will
    check it again on the machine."""
    if "b6_sites" not in syms:
        return segs
    names = sorted(n for n in syms if n.startswith("b6sw_"))
    if len(names) > SITES:
        raise SystemExit(f"mkxex6502: {len(names)} bank switches, room for {SITES} in b6_sites")
    segs = [(a, bytearray(b)) for a, b in segs]

    def at(x, n):
        for a, b in segs:
            if a <= x and x + n <= a + len(b) and not (WIN_LO <= a <= WIN_HI):
                return b, x - a
        raise SystemExit(f"mkxex6502: ${x:04X} is in no resident segment of {elf}")
    portb = addr("b6_portb")
    for n in names:
        b, o = at(addr(n), 6)
        if (b[o] not in (0xBD, 0xB9) or b[o + 1] | b[o + 2] << 8 != portb
                or b[o + 3:o + 6] != b"\x8d\x01\xd3"):
            raise SystemExit(f"mkxex6502: {n} at ${addr(n):04X} is not LDA b6_portb,X/Y "
                             f"then STA PORTB: {bytes(b[o:o + 6]).hex(' ')}")
    b, o = at(addr("b6_sites"), 2 * SITES + 2)
    table = b"".join(struct.pack("<H", addr(n)) for n in names) + b"\0\0"
    b[o:o + len(table)] = table
    return [(a, bytes(b)) for a, b in segs]


def main(argv):
    if len(argv) == 4 and argv[1] == "--g6a":
        return g6a(argv[2], argv[3])
    extra = [a.split("=", 1)[1] for a in argv if a.startswith("--bank=")]
    argv = [a for a in argv if not a.startswith("--bank=")]
    while "--bank" in argv:
        i = argv.index("--bank")
        extra.append(argv[i + 1])
        del argv[i:i + 2]
    argv = [a for a in argv if a != "--report"] + (["--report"] if "--report" in argv else [])
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    data = open(argv[1], "rb").read()
    entry, segs = segments(data)
    syms = {s["name"]: s for s in Elf(data).symbols()}

    def addr(name):
        if name not in syms:
            raise SystemExit(f"mkxex6502: {name} is not in {argv[1]}")
        return struct.unpack_from("<I", data, syms[name]["at"] + 4)[0]

    bct = addr("bc_t")
    if bct & 0xFF == 0xFF:
        raise SystemExit(f"mkxex6502: bc_t at ${bct:04X}: JMP (bc_t) would read its high "
                         f"byte from ${bct & 0xFF00:04X}")
    segs = sites(segs, syms, addr, argv[1])
    resident, banks = [], {}
    for a, body in segs:
        if a >= STORE:
            off = a - STORE
            n = off // BANK + 1
            if (off % BANK) + len(body) > BANK:
                raise SystemExit(f"mkxex6502: store segment ${a:X} crosses a bank")
            banks.setdefault(n, []).append((WIN_LO + off % BANK, body))
        elif WIN_LO <= a <= WIN_HI:
            continue                    # a bank's code at its run address: stored above
        else:
            if a < WIN_LO < a + len(body) or a <= WIN_HI < a + len(body) - 1:
                raise SystemExit(f"mkxex6502: resident segment ${a:04X}+{len(body)} "
                                 f"runs into the window")
            resident.append((a, body))
    for spec in extra:
        n_s, path = spec.split("=", 1)
        n = int(n_s, 0)
        if n in banks:
            raise SystemExit(f"mkxex6502: --bank {n}: the link has a bank {n} of its own")
        _, psegs = segments(open(path, "rb").read())
        body_of = []
        for a, body in psegs:
            if not (WIN_LO <= a and a + len(body) - 1 <= WIN_HI):
                raise SystemExit(f"mkxex6502: --bank {n}: {path} has a segment at ${a:X}, "
                                 f"outside the window")
            body_of.append((a, body))
        if not body_of:
            raise SystemExit(f"mkxex6502: --bank {n}: {path} has nothing in the window")
        banks[n] = body_of
    out = bytearray(b"\xff\xff")
    for a, body in sorted(resident):
        out += seg(a, body)
    out += seg(INITAD, struct.pack("<H", addr("b6_probe")))
    if "--report" in argv:              # the probe's findings on E:, now
        out += seg(INITAD, struct.pack("<H", addr("b6_report")))
    nxt, sel = addr("b6_next"), addr("b6_sel")
    for n in sorted(banks):
        out += seg(nxt, bytes([n]))
        out += seg(INITAD, struct.pack("<H", sel))
        if "--report" in argv:          # the bank is in the window
            out += seg(INITAD, struct.pack("<H", addr("b6_report")))
        for a, body in sorted(banks[n]):
            out += seg(a, body)
        if "--report" in argv:          # ...and its code went in
            out += seg(INITAD, struct.pack("<H", addr("b6_report")))
    out += seg(INITAD, struct.pack("<H", addr("b6_main")))
    if "--report" in argv:              # ...and again: every bank went in
        out += seg(INITAD, struct.pack("<H", addr("b6_report")))
    out += seg(RUNAD, struct.pack("<H", entry))
    open(argv[2], "wb").write(out)
    sizes = ", ".join(f"bank {n} {sum(len(b) for _, b in banks[n])}" for n in sorted(banks))
    print(f"{argv[2]}: {len(out)} bytes; resident {sum(len(b) for _, b in resident)}"
          f"{'; ' + sizes if sizes else ''}; entry ${entry:04X}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
