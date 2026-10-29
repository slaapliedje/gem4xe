#!/usr/bin/env python3
"""The system floppy boots by itself: no SpartaDOS X, only the disk's own
read-only DOS (src/fdos.s, src/fdboot.s, docs/fdos.md).

build/gem-sdx.atr in D1: and build/gem-apps.atr in D2:, on a machine
with no SDX cartridge -- an emulator's default, or a machine without one:

  1. the boot sectors load G4DOS.SYS, which loads GEM.COM, and the desk
     comes up: gem4xe has started, and GEMDOS took the DOS for a DOS 2
     (src/sys/dos.h), which is what makes its paths flat;
  2. D1:'s window lists the system's files -- DESKTOP.PRG and the rest
     live in \\GEM\\ on the disk, and the listing is flat;
  3. Options > Save desktop says it could not be saved -- the disk is
     read-only here -- and the desk carries on;
  4. D2:'s window lists the applications floppy, \\APPS\\ and \\GEM\\
     together, and EDIT.PRG double-clicked there RUNS: a program loaded
     off the second drive through the same handler.  EDIT given no file
     asks for one, so the file selector is what proves it started.

    python3 tests/emu/fdos_boot.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_FULLER, W_CLOSER         # noqa: E402
from deskrsc import OPTNMENU, SAVEITEM        # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "fdos")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def main():
    print("gem4xe-fdos: the system floppy boots by itself")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    emu = launch(tag="fdos", memsize="1088K",
                 extra_args=["--disk", os.path.join(BUILD, "gem-sdx.atr"),
                             "--disk", os.path.join(BUILD, "gem-apps.atr")])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        check(True, "the desk came up from gem-sdx.atr with no SpartaDOS X")
        kind = b.peek(syms["dos"])
        check(kind == 0, f"GEMDOS took the floppy's DOS for a DOS 2 (kind {kind})")
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D1:"))
        t.click(t.gadget(W_FULLER))
        names = []
        for n in ("DESKTOP.PRG", "DESKTOP.RSC", "GEM.COM", "LANG.RSC"):
            try:
                t.item(n)
                names.append(n)
            except KeyError:
                pass
        p = os.path.join(OUT, "d1.png")
        b.screenshot(p)
        check(len(names) == 4, f"D1:'s window lists the system flat: {names} ({p})")
        t.click(t.gadget(W_CLOSER))             # the D2: icon is under it
        t.settle()

        # Read-only: Options > Save desktop must say it could not, and the
        # desk must carry on -- not hang, not write somewhere it should not
        t.choose(OPTNMENU, SAVEITEM)
        b.frames(120)
        t.settle()
        p = os.path.join(OUT, "save.png")
        b.screenshot(p)
        check(find_text(p, "could not") is not None,
              f"Save desktop says the desktop could not be saved ({p})")
        b.key("RETURN")
        b.frames(60)
        t.settle()

        t.dclick(t.desk_icon("DISK D2:"))
        t.click(t.gadget(W_FULLER))
        p = os.path.join(OUT, "d2.png")
        b.screenshot(p)
        try:
            at = t.item("EDIT.PRG")
        except KeyError:
            at = None
        if check(at is not None, f"D2:'s window lists EDIT.PRG out of \\APPS\\ ({p})"):
            t.dclick(at)
            f, p, seen = 0, None, False
            while f < 6000 and not seen:
                b.frames(200)
                f += 200
                p = os.path.join(OUT, "edit.png")
                b.screenshot(p)
                seen = find_text(p, "Open a file") is not None
            check(seen, f"EDIT.PRG ran off D2: and asked for a file ({p})")
    finally:
        emu.stop()
    print(f"gem4xe-fdos: {'FAIL' if problems else 'PASS'} -- the system floppy "
          f"boots by itself, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
