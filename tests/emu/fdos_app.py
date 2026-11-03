#!/usr/bin/env python3
"""An appliance disk boots straight into its program (docs/g4dos-plan.md,
step 1): tools/mkfloppy.py --app, a G4DOS disk with the system less the
desktop and a program in the desktop's place.

build/gem-appliance.atr is EDIT's: EDIT.PRG as \\GEM\\DESKTOP.PRG and
EDIT.RSC beside it.  In D1: of a machine with no SpartaDOS X:

  1. G4DOS loads GEM.COM and gem4xe comes up, as the system floppy does;
  2. the shell runs EDIT where it would run the desktop, and EDIT, given
     no file, asks for one -- the file selector is what proves it ran;
  3. and the desktop did not: none of its drive icons is drawn.

    python3 tests/emu/fdos_app.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import boot, SYMS                  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "gem-appliance.atr")
OUT = os.path.join(BUILD, "shots", "fdosapp")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def main():
    print("gem4xe-fdosapp: an appliance disk boots straight into its program")
    os.makedirs(OUT, exist_ok=True)
    fs = atr.Sdfs(atr.ATRImage.load(DISK))
    gem = {e.filename for e in fs.entries("GEM")}
    check("DESKTOP.PRG" in gem and "DESKTOP.RSC" not in gem and "EDIT.RSC" in gem,
          f"the disk: the program as DESKTOP.PRG, the desktop's own files left out "
          f"({sorted(gem)})")
    syms = symfile.load(SYMS)
    emu = launch(tag="fdosapp", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        f, p, seen = 0, None, False
        while f < 6000 and not seen:
            b.frames(200)
            f += 200
            p = os.path.join(OUT, "app.png")
            b.screenshot(p)
            seen = find_text(p, "Open a file") is not None
        check(seen, f"EDIT ran in the desktop's place and asked for a file ({p})")
        check(find_text(p, "DISK D1") is None,
              f"and the desktop did not run: no drive icon on the screen ({p})")
    finally:
        emu.stop()
    print(f"gem4xe-fdosapp: {'FAIL' if problems else 'PASS'} -- an appliance "
          f"disk boots straight into its program, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
