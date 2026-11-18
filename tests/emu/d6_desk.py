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
SHOT = os.path.abspath(os.path.join(ROOT, "build", "d6.png"))
STATUS = 0x0600
SHARED = (0xD800, 0x2600)           # a program's RAM under the ROM
D1_ICON = (34, 28)                  # DISK D1:, the desk's first cell
NBANKS = 8


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-d6: the desktop on a stock 6502")
    text = open(MAP).read()

    def sym(n):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", text, re.M).group(1), 16)

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

        ram = bytes(b.memdump(*SHARED))
        check(b" D1:\\*.* " in ram, "a window titled \" D1:\\*.* \" in the desktop's memory")
        found = re.search(rb" \d+ bytes used in \d+ items\.", ram)
        got = found.group(0) if found else None
        check(got == want_info, f"its information line {got!r}; D1:'s {len(d1)} files make "
                                f"{want_info!r}")
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
