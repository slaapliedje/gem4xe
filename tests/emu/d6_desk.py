#!/usr/bin/env python3
"""d6_desk.py -- make test-d6: the desktop on a stock 6502 (docs/6502.md,
step 5c-3).

src/desk/*.c, the 65C816's desktop, built for the 6502 through gem.h's far
accessors (step 5c-2) as a program of eight banks (tools/bsp6502/rules.mk,
build/desk6.g6a) on its own disk in D2:, which A6 loads when $060C is 2 at
the go -- closing its own test windows first -- beside its resources on
D1:.  The gate holds it to:

  - the load: CIO's status 1, eight banks from the far heap, its first
    turn over ($060C 'R'), nothing stopped at $0604, no call refused;
  - the desk is the desktop's: the input owner is its process once it has
    put its desk up (src/aes/wind.c, WF_NEWDESK), not A6's;
  - a double-click on DISK D1: opens a window on it: its title " D1:\\*.* "
    and its information line in the desktop's own memory, under the ROM,
    with the count and the bytes of D1:'s files -- worked out here from
    the disk image itself, by GEMDOS's rule for a DOS 2 directory, its
    sectors times 125 -- which says the listing went through Fsfirst and
    Fsnext into the far DTA and the FNODEs and was counted from there.

    python3 tests/emu/d6_desk.py [--shot]
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
from atr import ATRImage, Dos2              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6d-boot.atr"))
DESK = os.path.abspath(os.path.join(ROOT, "build", "a6d-desk.atr"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
DMAP = os.path.abspath(os.path.join(ROOT, "build", "desk6.map"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "d6.png"))
STATUS = 0x0600
SHARED = (0xD800, 0x2600)           # a program's RAM under the ROM
D1_ICON = (34, 28)                  # DISK D1:, the desk's first cell
D1_CLOSE = (17, 43)                 # D1:'s window's close box
AUTORUN = (56, 71)                  # AUTORUN.SYS, first in D1:'s window
SHOW = (102, 120)                   # the document alert's Show
VIEW_CLOSE = (17, 19)               # the viewer's close box
VIEW_LEN = 16384 - (64 + 4 + 48)    # deskcmd.c: CMD_BUF - CMD_TEXT
D2_ICON = (114, 28)                 # DISK D2:, the second
D2_FULL = (240, 42)                 # its window's full box, where it opens
P6M_ICON = (196, 48)                # P6M.G6A, third in the full window
NBANKS = 8


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-d6: the desktop on a stock 6502, and a program from it")
    text = open(MAP).read()

    def sym(n, t=None):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", t or text, re.M).group(1), 16)
    dtext = open(DMAP).read()

    d1 = [e for e in Dos2(ATRImage.load(DISK)).entries() if e.in_use and e.nameable]
    want_info = f" {sum(e.count for e in d1) * 125} bytes used in {len(d1)} items.".encode()

    emu = launch(tag="d6", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    b.mount(1, DESK)

    def w16(a):
        return b.peek(a) | (b.peek(a + 1) << 8)

    def poke16(a, v):
        b.poke(a, v & 0xFF)
        b.poke(a + 1, (v >> 8) & 0xFF)

    def rom_out():
        """The RAM under the ROM reads as RAM only with the ROM out: the
        system switches it in for CIO and an interrupt, and a read then
        is the ROM's bytes (docs/6502.md, 5c-1).  Between frames until
        PORTB says it is out."""
        for _ in range(50):
            if not b.peek(0xD301) & 1:
                return
            b.frames(1)

    def shared():
        rom_out()
        return bytes(b.memdump(*SHARED))

    def dw16(n):                        # a desktop variable, under the ROM
        rom_out()
        return w16(sym(n, dtext))
    try:
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        b.poke(STATUS + 12, 2)              # the desktop, at the go
        b.poke(STATUS + 6, 1)
        b.frames(3000)

        stuck = b.peek(STATUS + 4)
        check(not stuck, f"nothing stopped at $0604 ({chr(stuck) if stuck else 'none'})")
        rd, slot, nb = b.peek(STATUS + 13), b.peek(STATUS + 12), b.peek(sym("p6_nbanks"))
        check(rd == 1 and nb == NBANKS and slot == ord("R"),
              f"it was read (CIO {rd}) into {nb} banks and its first turn ended "
              f"({chr(slot) if slot > 31 else slot}); want 1, {NBANKS}, 'R'")
        pin, ptab = w16(sym("proc_input")), w16(sym("proc_tab"))
        check(pin != ptab, f"the input owner is the desktop's process (${pin:04X}), not "
                           f"A6's (${ptab:04X})")

        ptr = sym("ptr_state")
        poke16(ptr + 6, 0)                  # PTR_NONE: the gate moves it
        poke16(ptr, D1_ICON[0])
        poke16(ptr + 2, D1_ICON[1])
        b.frames(20)
        for v in (1, 0, 1, 0):              # a double click
            poke16(ptr + 4, v)
            b.frames(4)
        b.frames(5000)

        ram = shared()
        check(b" D1:\\*.* " in ram, "a window titled \" D1:\\*.* \" in the desktop's memory")
        found = re.search(rb" \d+ bytes used in \d+ items\.", ram)
        got = found.group(0) if found else None
        check(got == want_info, f"its information line {got!r}; D1:'s {len(d1)} files make "
                                f"{want_info!r}")

        # THE VIEWER (deskcmd.c): a document's Show reads it into a 16 KB
        # far block and shows it in a window of its own -- its variables
        # landed on the system's zero page until 5d (TINY)
        def click0(xy, n=1):
            poke16(ptr, xy[0])
            poke16(ptr + 2, xy[1])
            b.frames(20)
            for _ in range(n):
                poke16(ptr + 4, 1)
                b.frames(4)
                poke16(ptr + 4, 0)
                b.frames(4)
        click0(AUTORUN, 2)
        b.frames(4000)
        click0(SHOW)
        for _ in range(100):
            b.frames(100)
            if dw16("cmd_id") and dw16("cmd_len") == VIEW_LEN:
                break
        vid, vlen, vlines = dw16("cmd_id"), dw16("cmd_len"), dw16("cmd_lines")
        check(vid > 0 and vlen == VIEW_LEN and vlines > 0,
              f"Show on AUTORUN.SYS: the viewer is window {vid} with {vlen} bytes of it in "
              f"{vlines} lines; want a window, {VIEW_LEN} bytes (all the buffer takes)")
        b.frames(3000)                      # its window drawn before it closes
        click0(VIEW_CLOSE)
        b.frames(3000)
        # A PROGRAM FROM THE DESKTOP (step 5d): D2:'s window, full, and a
        # double-click on P6M.G6A -- the desktop asks for it (shel_write)
        # and ends; A6's shell runs it; when it ends, the desktop again
        def click(xy, n=1, wait=0):
            poke16(ptr, xy[0])
            poke16(ptr + 2, xy[1])
            b.frames(20)
            for _ in range(n):
                poke16(ptr + 4, 1)
                b.frames(4)
                poke16(ptr + 4, 0)
                b.frames(4)
            b.frames(wait)
        starts0 = b.peek(STATUS + 0x3E)
        click(D1_CLOSE, 1, 3000)            # D2:'s then opens where D1:'s was
        click(D2_ICON, 2, 5000)
        click(D2_FULL, 1, 0)
        for _ in range(100):                # polled: the redraw's pace varies
            b.frames(100)
            ram = shared()
            if b"P6M.G6A" in ram and b"P6PROG.G6A" in ram:
                break
        b.frames(500)
        check(b"P6M.G6A" in ram and b"P6PROG.G6A" in ram,
              "D2:'s window lists P6M.G6A and P6PROG.G6A by name")
        b.poke(STATUS + 0x40, 0)
        b.poke(STATUS + 0x62, 0)
        click(P6M_ICON, 2, 0)
        for _ in range(120):
            b.frames(50)
            if b.peek(STATUS + 0x40) == ord("a"):
                break
        starts1 = b.peek(STATUS + 0x3E)
        check(b.peek(STATUS + 0x40) == ord("a") and starts1 == starts0 + 1,
              f"P6M.G6A ran from the desktop: at its alert (stage "
              f"{chr(b.peek(STATUS + 0x40)) if b.peek(STATUS + 0x40) > 31 else 0}), "
              f"programs started {starts0} -> {starts1}")
        check((w16(STATUS + 0x42), w16(STATUS + 0x44)) == (26, 55),
              f"...and did its sums across its banks ({w16(STATUS + 0x42)}, "
              f"{w16(STATUS + 0x44)}; want 26, 55)")
        b.poke(STATUS + 0x62, 1)
        b.frames(300)
        b.key("RETURN")
        for _ in range(120):
            b.frames(50)
            if b.peek(STATUS + 0x3E) == starts1 + 1:
                break
        b.frames(3000)
        starts2 = b.peek(STATUS + 0x3E)
        check(b.peek(STATUS + 0x40) == ord("E") and starts2 == starts1 + 1
              and b.peek(STATUS + 13) == 1,
              f"it ended (stage {chr(b.peek(STATUS + 0x40)) if b.peek(STATUS + 0x40) > 31 else 0})"
              f" and the desktop was started again ({starts1} -> {starts2}, CIO "
              f"{b.peek(STATUS + 13)})")
        for _ in range(100):                # polled, as above
            ram = shared()
            if b"DISK D1:" in ram:
                break
            b.frames(100)
        check(b"DISK D1:" in ram, "the desktop again built its desk: \"DISK D1:\" in its "
                                  "memory (its resource found, on D1: again)")
        pin = w16(sym("proc_input"))
        check(pin != ptab and b.peek(sym("p6_nbanks")) == NBANKS,
              f"the desktop again: {b.peek(sym('p6_nbanks'))} banks, the input its own "
              f"(${pin:04X})")
        bad, op = w16(sym("gem_bad")), w16(sym("gem_badop"))
        check(bad == 0, f"no call refused (gem_bad {bad}, last opcode {op:#x})")
        b.screenshot(SHOT)
    finally:
        emu.stop()
    if not fails and not keep and os.path.exists(SHOT):
        os.remove(SHOT)
    print(f"gem4xe-d6: {'PASS' if not fails else 'FAIL'} -- the desktop on a stock 6502, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
