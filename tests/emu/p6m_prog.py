#!/usr/bin/env python3
"""p6m_prog.py -- make test-p6m: a program of several banks, its data in
the RAM under the OS ROM, on a stock 6502 (docs/6502.md, step 5c-1).

src/p6m_prog.c is built with the kit like src/p6_prog.c but linked by
src/app/gemappm6502.scm: its code in three banks of its own, its veneers,
runtime, constants, data and C stack under the ROM, its calls across
banks through its own trampoline (src/app/crt6502m.s, _pcall).  It is
P6PROG.G6A of format 2 on build/a6m-boot.atr, and A6 (src/a6_evt.c)
loads it into three banks from the far heap.  The gate holds it to:

  - the load: CIO's status 1 and every byte of the file's pieces and
    banks; three banks, 16 KB-aligned and different; its link block at
    $C000 naming each one's bank index and the system's b6_cur, b6_portb
    and bank kind;
  - the system running with the ROM out (src/a6_tree.c): PORTB bit 0
    clear, the RAM vectors at $FFFA-$FFFF the resident handlers
    (src/sys6502/gate6502.s), and KEYDEF pointing at the OS's key table
    copied to $FE00 under it, its bytes the ROM's;
  - its calls: bank 1 to 2 to 3 and back with an initialised global
    (26), banks 2 and 3 recursing into each other ten deep (55), a table
    of function pointers into all three (107), a pointer to a constant
    returned from bank 3 ("BANK THREE"), and a bss counter every one of
    them counted in (17);
  - the system with its data: appl_init's ap_id 2; Fread of P6PROG.RSC's
    first 18 bytes into its buffer under the ROM, as the file has them;
    and its alert, text under the ROM, answering Return with its default,
    2 -- with the second button only if the text was read whole;
  - its far memory (step 5c-2): a Malloc'd block written through gem.h's
    FSET and fa_put (src/app/farm6502.s, which maps the far bank itself)
    -- a record, one past the first 16 KB piece, 8 bytes across the
    boundary -- read back through FGET and fa_get, and through the
    system's far_fetch, which maps it its own way;
  - it ran to its end, nothing stopped at $0604, no call refused.

With --axlon SIZE (an Axlon on a 130XE): the same, all of it, on the
Axlon's banks.  Its register at $CFFF is heard with the ROM in, so every
switch -- the system's, _pcall's and fa_*'s -- goes through ax_sw
(src/sys6502/bank6502.s), which puts the ROM in for the one write: the
ROM is out, and the link block gives ax_sw's address.  Until 0.17 a
program of several banks was refused there, and with it the desktop.

    python3 tests/emu/p6m_prog.py [--shot] [--axlon 4096K]
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, XLROM   # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6m-boot.atr"))
G6A = os.path.abspath(os.path.join(ROOT, "build", "p6mprog.g6a"))
RSC = os.path.abspath(os.path.join(ROOT, "build", "p6prog.rsc"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
PMAP = os.path.abspath(os.path.join(ROOT, "build", "p6mprog.map"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "p6m.png"))
STATUS = 0x0600
PORTB = 0xD301
G6_LINK = 0xC000                    # src/app/crt6502m.s
KEYDEF, KEYDEF_LEN, KEYDEF_AT = 0x0079, 192, 0xFE00   # src/a6_tree.c
SHARED = ("_Zp", "_Vsp", "_Vfp")    # the calling convention's, both links
# what src/p6m_prog.c computes, worked out again here
CHAIN = 7 * 3 + 5
DOWN = sum(range(1, 11))
OPS = (1 + 100) + (2 * 2) + (3 - 1)
COUNT = 2 + 11 + 3 + 1              # chain+mul3, down2/down3 x11, ops, name3
NAME = b"BANK THREE"
ALERT_DEF = 2


def main(argv):
    keep = "--shot" in argv
    axlon = argv[argv.index("--axlon") + 1] if "--axlon" in argv else None
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-p6m: a program of several banks, its data under the OS ROM, "
          "on a stock 6502")
    text, ptext = open(MAP).read(), open(PMAP).read()

    def sym(n, t=text):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", t, re.M).group(1), 16)

    for n in SHARED:
        check(sym(n) == sym(n, ptext), f"{n} at the same address in both links")

    g6a = open(G6A, "rb").read()
    n, np = g6a[3], g6a[4]
    want_rd = len(g6a) - (6 + 4 * np + (4 if g6a[5] & 1 else 2) * n)
    if axlon:
        emu = launch(tag="p6m", memsize="128K", vbxe=False, rapidus=False,
                     extra_args=["--axlonmemsize", axlon])
        emu.bridge.boot(DISK)
    else:
        emu = launch(tag="p6m", memsize="1088K", vbxe=False, rapidus=False,
                     extra_args=["--disk", DISK])
    b = emu.bridge

    def w16(at):
        return b.peek(at) | (b.peek(at + 1) << 8)

    def poke16(at, v):
        b.poke(at, v & 0xFF)
        b.poke(at + 1, (v >> 8) & 0xFF)

    def until(*stages):
        for _ in range(600):
            b.frames(5)
            if b.peek(STATUS + 0x40) in stages or b.peek(STATUS + 4):
                break
    try:
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        b.poke(STATUS + 0x62, 0)
        b.poke(STATUS + 12, 1)              # the program, at the go
        b.poke(STATUS + 6, 1)
        until(ord("a"), ord("E"))
        at_alert = b.peek(STATUS + 0x40) == ord("a")
        if at_alert:
            ptr = sym("ptr_state")
            poke16(ptr + 6, 0)              # PTR_NONE: the gate moves it
            poke16(ptr, 300)
            poke16(ptr + 2, 180)
            b.frames(30)
            b.poke(STATUS + 0x62, 1)
            b.frames(400)
            b.screenshot(SHOT)
            b.key("RETURN")
            until(ord("E"))
        b.frames(60)
        if axlon:
            check(b.peek(sym("b6_kind")) == ord("A"), "the probe took the Axlon's banks")

        stuck = b.peek(STATUS + 4)
        check(not stuck, f"no stub that must not run was reached "
                         f"({chr(stuck) if stuck else 'none'} at $0604)")
        rd, n_rd = b.peek(STATUS + 13), w16(STATUS + 14)
        check(rd == 1 and n_rd == want_rd,
              f"it was read: CIO status {rd}, {n_rd} bytes of pieces and banks; "
              f"the file has {want_rd}")

        # its banks, and the link block the loader filled
        nb = b.peek(sym("p6_nbanks"))
        base = sym("p6_banks")
        banks = [w16(base + 4 * k) | (w16(base + 4 * k + 2) << 16) for k in range(nb)]
        check(nb == n and len(set(banks)) == n and all(a and not a & 0x3FFF and a >> 16
                                                         for a in banks),
              f"{nb} banks from the far heap, {[f'${a:06X}' for a in banks]}: want {n}, "
              f"16 KB-aligned, different")
        fb = b.peek(sym("b6_far_base"))
        want_idx = [fb + ((a >> 16) - 1) * 4 + ((a >> 14) & 3) for a in banks]
        idx = [b.peek(G6_LINK + 1 + k) for k in range(n)]
        check(idx == want_idx, f"the link block names their bank indexes {idx}, "
                               f"want {want_idx}")
        lk = (w16(G6_LINK + 0x10), w16(G6_LINK + 0x12), b.peek(G6_LINK + 0x14),
              w16(G6_LINK + 0x16))
        want_lk = (sym("b6_cur"), sym("b6_portb"), b.peek(sym("b6_kind")), sym("ax_sw"))
        check(lk == want_lk, f"...and b6_cur, b6_portb, the kind, ax_sw: "
                             f"{tuple(hex(x) for x in lk)}, want "
                             f"{tuple(hex(x) for x in want_lk)}")

        # the system with the ROM out
        pb = b.peek(PORTB)
        check(not pb & 1, f"the OS ROM is out: PORTB ${pb:02X}")
        vec = [w16(0xFFFA + 2 * k) for k in range(3)]
        want_vec = [sym("g6_nmi"), sym("g6_reset"), sym("g6_irq")]
        check(vec == want_vec, f"the RAM vectors {[hex(v) for v in vec]}, want "
                               f"{[hex(v) for v in want_vec]}")
        kd = w16(KEYDEF)
        got = bytes(b.memdump(kd, KEYDEF_LEN))
        rom = open(XLROM, "rb").read() if os.path.exists(XLROM) else b""
        check(kd == KEYDEF_AT and (not rom or rom.find(got) >= 0),
              f"KEYDEF ${kd:04X}, want ${KEYDEF_AT:04X}, the system's under the ROM; "
              f"its 192 bytes {'found' if rom.find(got) >= 0 else 'NOT found'} in the "
              f"OS ROM")

        stage = b.peek(STATUS + 0x40)
        check(stage == ord("E"), f"it ran to its end (stage "
                                 f"{chr(stage) if stage > 31 else stage!r})")
        check(b.peek(STATUS + 0x41) == 2, f"appl_init answered {b.peek(STATUS + 0x41)}, "
                                          f"want 2")
        got = (w16(STATUS + 0x42), w16(STATUS + 0x44), w16(STATUS + 0x46),
               b.peek(STATUS + 0x48))
        check(got == (CHAIN, DOWN, OPS, COUNT),
              f"across its banks: chain {got[0]}, down {got[1]}, the pointers' sum "
              f"{got[2]}, the count {got[3]}; want {CHAIN}, {DOWN}, {OPS}, {COUNT}")
        name = bytes(b.memdump(STATUS + 0x50, 16)).split(b"\0")[0]
        check(name == NAME, f"bank 3's constant, from under the ROM: {name!r}")
        rsc = open(RSC, "rb").read()
        cnt, data = b.peek(STATUS + 0x70), bytes(b.memdump(STATUS + 0x80, 18))
        check(cnt == 18 and data == rsc[:18],
              f"Fread into its buffer under the ROM: {cnt} bytes, {data.hex()}; want 18, "
              f"{rsc[:18].hex()}")
        # its far memory through gem.h's FGET/FSET and fa_* (step 5c-2),
        # read back through them and through the system's far_fetch
        blk = w16(STATUS + 0xA0) | (w16(STATUS + 0xA2) << 16)
        fr = [b.peek(STATUS + 0xA4 + k) for k in range(4)]
        across = bytes(b.memdump(STATUS + 0xA8, 8))
        check(blk >> 16 >= 1, f"Malloc(20000) gave far address ${blk:06X}")
        check(fr[:3] == [1, 1, 1],
              f"FGET read back what FSET put: record 0 {fr[0]}, record 1300 (past 16 KB) "
              f"{fr[1]}, 8 bytes across the piece boundary {fr[2]}; want 1, 1, 1")
        check(b.peek(STATUS + 0xB3) == 1,
              f"a word and two longs across the piece boundary read back "
              f"({b.peek(STATUS + 0xB3)}), want 1")
        check(fr[3] == 1 and across == b"ABCDEFGH",
              f"...and the system's far_fetch saw them the same ({fr[3]}), the 8 bytes "
              f"{across!r}")
        fcnt, fok, mf = (b.peek(STATUS + 0xB0), b.peek(STATUS + 0xB1),
                         b.peek(STATUS + 0xB2))
        check(fcnt == 18 and fok == 1,
              f"Fread straight into the far block (a far address, as it is): {fcnt} "
              f"bytes, the file's {fok}; want 18, 1")
        check(mf == 0, f"Mfree of the block by its far address answered {mf}, want 0")
        ans = w16(STATUS + 0x60)
        check(at_alert and ans == ALERT_DEF,
              f"its alert, text under the ROM, answered {ans} to Return; want {ALERT_DEF}")
        bad, op = w16(sym("gem_bad")), w16(sym("gem_badop"))
        check(bad == 0, f"no call refused (gem_bad {bad}, last opcode {op:#x})")
    finally:
        emu.stop()
    return finish(fails, keep)


def finish(fails, keep):
    if not fails and not keep and os.path.exists(SHOT):
        os.remove(SHOT)
    print(f"gem4xe-p6m: {'PASS' if not fails else 'FAIL'} -- a program of several banks, "
          f"its data under the OS ROM, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
