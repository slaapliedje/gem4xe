#!/usr/bin/env python3
"""The system floppy boots by itself: no SpartaDOS X, only the disk's own
DOS, G4DOS (src/fdos.s, src/fdboot.s, docs/fdos.md).

build/gem-sdx.atr in D1: and build/gem-apps.atr in D2:, on a machine
with no SDX cartridge -- an emulator's default, or a machine without one:

  1. the boot sectors load G4DOS.SYS, which loads GEM.COM, and the desk
     comes up: gem4xe has started, and GEMDOS took the DOS for a DOS 2
     (src/sys/dos.h), which is what makes its paths flat;
  2. D1:'s window lists the system's files -- DESKTOP.PRG and the rest
     live in \\GEM\\ on the disk, and the listing is flat;
  3. Options > Save desktop saves: no alert, and when the run is over
     the emulator's working copy of the disk has DESKTOP.INF in its root
     (G4DOS writes to the root, which its flat view reads first), the
     layout gem4xe wrote, and tools/atr.py's check finds the bitmap, the
     chains and the free count in agreement;
  4. D2:'s window lists the applications floppy, \\APPS\\ and \\GEM\\
     together, and EDIT.PRG double-clicked there RUNS: a program loaded
     off the second drive through the same handler.  EDIT given no file
     asks for one, so the file selector is what proves it started.

    python3 tests/emu/fdos_boot.py
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                    # noqa: E402
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
    # A copy, written to: the emulator keeps its working copy of it by its
    # hash in the run's configuration (tests/emu/gemarc.py does the same).
    work = tempfile.mkdtemp(prefix="fdos-")
    disk = os.path.join(work, "gem-sdx.atr")
    shutil.copy(os.path.join(BUILD, "gem-sdx.atr"), disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("fdos"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="fdos", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk,
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

        # Options > Save desktop: written, so nothing to say about it
        t.choose(OPTNMENU, SAVEITEM)
        b.frames(120)
        t.settle()
        p = os.path.join(OUT, "save.png")
        b.screenshot(p)
        check(find_text(p, "could not") is None,
              f"Save desktop puts up no alert ({p})")

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
    if check(os.path.exists(written), f"the emulator wrote its working copy ({written})"):
        fs = atr.Sdfs(atr.ATRImage.load(written))
        inf = fs.read("DESKTOP.INF") if "DESKTOP.INF" in fs.list("") else None
        check(inf is not None and inf[:1] == b"#",
              f"DESKTOP.INF is in the root, {len(inf or b'')} bytes of layout"
              + (f", starting {inf[:16]!r}" if inf else ""))
        bad = fs.check()
        check(not bad, "the bitmap, the chains and the free count agree"
              + ("" if not bad else ": " + "; ".join(bad[:6])))
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-fdos: {'FAIL' if problems else 'PASS'} -- the system floppy "
          f"boots by itself, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
