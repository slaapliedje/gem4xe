#!/usr/bin/env python3
"""mkxex6502.py -- a banked 6502 link as an Atari binary file.

    python3 tools/bsp6502/mkxex6502.py IN.elf OUT.xex [--report] [--bank N=PROG.elf ...]
    python3 tools/bsp6502/mkxex6502.py --g6a [--pack] PROG.elf OUT.G6A

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
    $04  p, f                its pieces under the ROM (0..2), its flags
    $06  p x (addr, len)     each piece's address and length, two words
         n x len             each bank's length in the file, a word
         n x out             if f bit 0: each bank's length unpacked
         the pieces' bytes, then the banks', in that order

--pack (f bit 0) stores each bank as one G4Z chunk (tools/mkxex.py) when
that is shorter and it can be unpacked IN PLACE: the loader reads the
packed bytes into the top of the bank, $8000 - len up, and unpacks them
from $4000 (src/sys6502/far6502.s, g6z_far), so no byte may be written
before it is read.  Where it cannot, or packing gains nothing, the bank
is stored as it is and its two lengths are equal.  The pieces under the
ROM are not packed: 3-4 KB, through CIO's buffer.

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

    $0400 + INITAD               BASIC off (PORTB bit 1, BASICF)
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

--pack writes each bank packed (tools/mkxex.py's format, G4Z): its
window segments as one image, gaps zero, cut into chunks that fit
$8000-$9EFF -- ANTIC's screen-to-be, which nothing in the file loads
into -- each a segment there then INITAD b6_unz (src/sys6502/g6z6502.s),
which unpacks it into the window:

        b6_next = n, INITAD b6_sel
        $8000: where (a word), how many (a word), the packed bytes
        INITAD b6_unz                ...again for each chunk of the bank

Each chunk is decoded again here, by tools/mkxex.py's decoder, and must
give the bank back.  A floppy's serial bus is slow enough that half the
bytes are worth the 6502's 70 cycles a byte; a hard disk is not, so the
choice is the build's (docs/6502.md, "Disk").

And writes b6_sites: the address of every bank switch (each public
label b6sw_*, checked to be LDA b6_portb,X/Y then STA PORTB), which
src/sys6502/bank6502.s rewrites to STA $CFFF on an Axlon's machine.
"""
import struct
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elfsym import Elf  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mkxex  # noqa: E402

STORE = 0x10000
BANK = 0x4000
WIN_LO, WIN_HI = 0x4000, 0x7FFF
INITAD, RUNAD = 0x02E2, 0x02E0
# BASIC OFF before anything loads: the resident link has data at
# $A000-$BFFF, which is BASIC's ROM on an XL/XE booted without OPTION.
# PORTB bit 1 set takes it out, and BASICF ($03F8) non-zero keeps it out
# across a warm start.  In the cassette buffer, which nothing loads into:
#   LDA PORTB / ORA #2 / STA PORTB / LDA #1 / STA BASICF / RTS
NOBASIC_AT = 0x0400
NOBASIC = bytes([0xAD, 0x01, 0xD3, 0x09, 0x02, 0x8D, 0x01, 0xD3,
                 0xA9, 0x01, 0x8D, 0xF8, 0x03, 0x60])
NOBASIC_END = NOBASIC_AT + len(NOBASIC) - 1
STAGE, STAGE_END = 0x8000, 0x9EFF       # src/sys6502/g6z6502.s's B6_STAGE


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


class _Src(bytes):
    """A packed bank as decode reads it: how far it has read."""
    def __new__(cls, b):
        o = super().__new__(cls, b)
        o.read = 0
        return o

    def __getitem__(self, k):
        r = super().__getitem__(k)
        e = (k.stop if isinstance(k, slice) else k + 1)
        self.read = max(self.read, e)
        return r


class _InPlace(list):
    """decode's output, written from $4000 below the packed bytes read at
    base and up: each byte written must be over one already read."""
    def __init__(self, src, base):
        super().__init__()
        self.src, self.base, self.margin = src, base, 1 << 16

    def _at(self, end):
        m = self.base + self.src.read - end
        if m < self.margin:
            self.margin = m

    def append(self, v):
        super().append(v)
        self._at(len(self))

    def __iadd__(self, more):
        super().__iadd__(list(more))
        self._at(len(self))
        return self


def pack_bank(img):
    """(packed bytes, margin), or None: one chunk, unpacked in place."""
    ch = mkxex.chunks(bytes(img), BANK)
    if len(ch) != 1 or ch[0][0] != len(img) or len(ch[0][1]) >= len(img):
        return None
    data = ch[0][1]
    src = _Src(data)
    out = _InPlace(src, BANK - len(data))
    mkxex.decode(src, len(img), out, 0)
    if bytes(out) != bytes(img):
        raise SystemExit("mkxex6502: --g6a --pack: a bank does not decode as it was")
    return (data, out.margin) if out.margin >= 0 else None


def g6a2(elf, out, segs, pack=False):
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
    store, notes = {}, []
    for k in range(1, n + 1):
        p = pack_bank(banks[k]) if pack else None
        store[k] = p[0] if p else bytes(banks[k])
        notes.append(f"{len(banks[k])}" + (f"->{len(p[0])} (margin {p[1]})" if p
                                           else " raw" if pack else ""))
    head = bytes([ord("G"), ord("6"), 2, n, len(pieces), 1 if pack else 0])
    head += b"".join(struct.pack("<HH", a, len(b)) for a, b in pieces)
    head += b"".join(struct.pack("<H", len(store[k])) for k in range(1, n + 1))
    if pack:
        head += b"".join(struct.pack("<H", len(banks[k])) for k in range(1, n + 1))
    data = head + b"".join(bytes(b) for _, b in pieces) + \
        b"".join(store[k] for k in range(1, n + 1))
    open(out, "wb").write(data)
    print(f"{out}: format 2, {len(data)} bytes: {n} bank(s) of "
          f"{', '.join(notes)} bytes; under the ROM "
          f"{', '.join(f'${a:04X}+{len(b)}' for a, b in pieces)}")
    return 0


def g6a(elf, out, pack=False):
    _, segs = segments(open(elf, "rb").read())
    if any(a >= STORE or a >= 0xC000 for a, _ in segs):
        return g6a2(elf, out, segs, pack)
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


def packed(bodies, unz, n):
    """A bank's window segments packed: the segments --pack writes."""
    lo = min(a for a, _ in bodies)
    img = bytearray(max(a + len(b) for a, b in bodies) - lo)
    for a, b in bodies:
        img[a - lo:a - lo + len(b)] = b
    out, back, last, dst = bytearray(), bytearray(), 0, lo
    for count, data in mkxex.chunks(bytes(img), STAGE_END + 1 - STAGE - 4):
        last = mkxex.decode(data, count, back, last)
        out += seg(STAGE, struct.pack("<HH", dst, count) + data)
        out += seg(INITAD, struct.pack("<H", unz))
        dst += count
    if back != img:
        raise SystemExit(f"mkxex6502: --pack: bank {n} does not decode to itself")
    return out


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
    if len(argv) == 5 and argv[1:3] == ["--g6a", "--pack"]:
        return g6a(argv[3], argv[4], True)
    extra = [a.split("=", 1)[1] for a in argv if a.startswith("--bank=")]
    argv = [a for a in argv if not a.startswith("--bank=")]
    while "--bank" in argv:
        i = argv.index("--bank")
        extra.append(argv[i + 1])
        del argv[i:i + 2]
    pack = "--pack" in argv
    argv = [a for a in argv if a != "--pack"]
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
    if pack:
        for a, body in resident:
            if a <= STAGE_END and a + len(body) > STAGE:
                raise SystemExit(f"mkxex6502: --pack: resident segment ${a:04X}+{len(body)} "
                                 f"is in the staging buffer ${STAGE:04X}-${STAGE_END:04X}")
    for a, body in resident:
        if a <= NOBASIC_END and a + len(body) > NOBASIC_AT:
            raise SystemExit(f"mkxex6502: resident segment ${a:04X}+{len(body)} is where "
                             f"the BASIC-off code goes, ${NOBASIC_AT:04X}-${NOBASIC_END:04X}")
    out = bytearray(b"\xff\xff")
    out += seg(NOBASIC_AT, NOBASIC)
    out += seg(INITAD, struct.pack("<H", NOBASIC_AT))
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
        if pack:
            out += packed(banks[n], addr("b6_unz"), n)
        else:
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
