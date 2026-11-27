#!/usr/bin/env python3
"""The 6502 floppy: G4DOS boots a stock 6502 into the desktop by itself.

build/gem6502.atr (tools/mkfloppy.py --g6502) is what a tester puts in
D1: -- G4DOS, the 6502 system as GEM.COM with its go and the desktop in a
load segment of its own (build/a6auto.xex), and the desktop, the Control
Panel and their resources beside it.  NOTHING IS POKED: the gates before
it (test-d6) start the desktop from the bridge, and a real machine has
no bridge.

Booted three ways -- ANTIC and VBXE at 1088K, and a 64K XL with a 4 MB
Axlon, a 600XL with a SUBCart -- each must reach the desktop's first
turn, its process holding the input, the arrow up, the screen A6 chose
the machine's, and D1:'s window open on a double click.

G4DOS's loader prints a dot per segment, and A6's loader keeps its bank
table in the OS's screen memory ($BF4B-, the HiRam it owns once loaded):
a row of dots that wrapped made the editor insert a line, the table
moved 40 bytes, and the 24th bank's select switched the OS ROM out (a
garbage screen at 1088K, no desktop on the Axlon).  src/fdos.s keeps the
dots on their row.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "gem6502.atr"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
STATUS = 0x0600
SHARED = (0xD800, 0x2600)           # a program's RAM under the ROM
ARROW_DATA1 = 0x4000                # tools/gemdata.py: ARROW's second row
NBANKS = 8                          # the desktop's (tests/emu/d6_desk.py)
D1_ICON = {"antic": (34, 28), "vbxe": (48, 30)}    # DISK D1:, as in test-d6
RUNS = [("1088K", "antic", None), ("1088K", "vbxe", None), ("64K", "antic", "4096K")]


def main(argv):
    text = open(MAP).read()

    def sym(n):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", text, re.M).group(1), 16)

    def static(n):                      # a file's static: placed, not listed
        return int(re.search(rf"^{n} in section 'zdata'  placed at address "
                             rf"([0-9a-f]+)-", text, re.M).group(1), 16)
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-g6: the 6502 floppy, booted with nothing poked")
    for mem, scr, axlon in RUNS:
        what = f"{mem} {scr.upper()}" + (f" + Axlon {axlon}" if axlon else "")
        if axlon:
            emu = launch(tag="g6a", memsize=mem, vbxe=False, rapidus=False,
                         extra_args=["--axlonmemsize", axlon])
            emu.bridge.boot(DISK)
        else:
            emu = launch(tag="g6" + scr[0], memsize=mem, vbxe=(scr == "vbxe"),
                         rapidus=False, extra_args=["--disk", DISK])
        b = emu.bridge

        def w16(a):
            return b.peek(a) | (b.peek(a + 1) << 8)

        def poke16(a, v):
            b.poke(a, v & 0xFF)
            b.poke(a + 1, (v >> 8) & 0xFF)

        def shared():                   # RAM under the ROM: with it out
            for _ in range(50):
                if not b.peek(0xD301) & 1:
                    break
                b.frames(1)
            return bytes(b.memdump(*SHARED))
        try:
            for i in range(300):
                b.frames(100)
                if b.peek(STATUS + 12) == ord("R") or b.peek(STATUS + 4):
                    break
            b.frames(3000)
            stuck, slot = b.peek(STATUS + 4), b.peek(STATUS + 12)
            nb = b.peek(sym("p6_nbanks"))
            if not check(not stuck and slot == ord("R") and nb == NBANKS,
                         f"{what}: the desktop read into {nb} banks and its first turn "
                         f"ended ('{chr(slot) if slot > 31 else slot}', stop "
                         f"{chr(stuck) if stuck else 'none'}) after {i * 100} frames; "
                         f"want {NBANKS}, 'R', none"):
                b.screenshot(os.path.join(ROOT, "build", f"g6-{mem}-{scr}.png"))
                continue
            got = chr(b.peek(STATUS + 5) or 32)
            check(got == ("V" if scr == "vbxe" else "A"),
                  f"{what}: the screen A6 chose is {got!r}")
            if axlon:
                check(b.peek(sym("b6_kind")) == ord("A"),
                      f"{what}: on the Axlon's banks ({chr(b.peek(sym('b6_kind')))!r})")
            pin, ptab = w16(sym("proc_input")), w16(sym("proc_tab"))
            check(pin != ptab, f"{what}: the desktop's process holds the input")
            hot = (w16(static("cur_xhot")), w16(static("cur_yhot")))
            row1 = w16(static("cur_data") + 2)
            check(hot == (0, 0) and row1 == ARROW_DATA1,
                  f"{what}: the arrow is up (hot spot {hot}, row 1 ${row1:04X})")
            ptr = sym("ptr_state")
            poke16(ptr + 6, 0)              # PTR_NONE: the gate moves it
            poke16(ptr, D1_ICON[scr][0])
            poke16(ptr + 2, D1_ICON[scr][1])
            b.frames(20)
            for v in (1, 0, 1, 0):          # a double click
                poke16(ptr + 4, v)
                b.frames(4)
            b.frames(5000)
            check(b" D1:\\*.* " in shared(), f"{what}: D1:'s window opened")
        finally:
            emu.stop()
    print(f"gem4xe-g6: {'PASS' if not fails else 'FAIL'} -- the 6502 floppy on three "
          f"machines, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
