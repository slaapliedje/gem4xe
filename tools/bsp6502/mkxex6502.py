#!/usr/bin/env python3
"""mkxex6502.py -- a banked 6502 link as an Atari binary file.

    python3 tools/bsp6502/mkxex6502.py IN.elf OUT.xex

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


def main(argv):
    if len(argv) != 3:
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
    out = bytearray(b"\xff\xff")
    for a, body in sorted(resident):
        out += seg(a, body)
    out += seg(INITAD, struct.pack("<H", addr("b6_probe")))
    nxt, sel = addr("b6_next"), addr("b6_sel")
    for n in sorted(banks):
        out += seg(nxt, bytes([n]))
        out += seg(INITAD, struct.pack("<H", sel))
        for a, body in sorted(banks[n]):
            out += seg(a, body)
    out += seg(INITAD, struct.pack("<H", addr("b6_main")))
    out += seg(RUNAD, struct.pack("<H", entry))
    open(argv[2], "wb").write(out)
    sizes = ", ".join(f"bank {n} {sum(len(b) for _, b in banks[n])}" for n in sorted(banks))
    print(f"{argv[2]}: {len(out)} bytes; resident {sum(len(b) for _, b in resident)}"
          f"{'; ' + sizes if sizes else ''}; entry ${entry:04X}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
