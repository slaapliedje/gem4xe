#!/usr/bin/env python3
"""Phase 163 gate: a plain Atari program run from the desktop on MyDOS and
on DOS 2 (docs/run8-plan.md, step 2).

Each DOS's own GEM floppy in D1: -- build/gem-mydos.atr, MyDOS 4.50 with
GEM as AUTORUN.SYS; build/gem-boot.atr, a double-density DOS 2 the same way -- and in D2:
a disk of that DOS's holding PROG.XEX, a program that prints a line and
returns, and LOOP.XEX, one that prints a line and loops for ever.  On each:

  1. D2: opened, PROG.XEX double-clicked: GEM ends, its stub at $0400
     (src/run8.s) runs PROG.XEX -- its line is on the screen -- and then
     GEM again: the boot screen, then the desktop.
  2. LOOP.XEX double-clicked: its line, and RESET -- and GEM comes back,
     through the stub's DOSINI.  A WARM start: the stub cleared COLDST,
     which the OS leaves $FF all through a GEM started as AUTORUN.SYS, so
     without that a RESET booted the disk again -- and GEM came back for
     that reason instead (WARMST says which).
  3. File -> Quit: the DOS's own DUP menu.  The stub gave DOSVEC and
     DOSINI back before it ran GEM, so GEM's own exit is the DOS's again.

    python3 tests/emu/m68_run8dos.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE   # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from deskrsc import FILEMENU, QUITITEM        # noqa: E402
from fdos_shell import prog, lines, wait_for  # noqa: E402
from m67_run8 import gem_back                 # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
COLDST, WARMST = 0x0244, 0x0008                # the OS's: a RESET's two flags
OUT = os.path.join(BUILD, "shots", "run8dos")
# (the tag, GEM's floppy, its symbols, a MyDOS D2:)
DOSES = [
    ("MyDOS 4.50", "gem-mydos.atr", "gem.sym", True),
    ("a double-density DOS 2", "gem-boot.atr", "gem-dos2.sym", False),
]
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def make_d2(path, mydos):
    # MyDOS's on double density: a single-density VTOC has no bit for the
    # sector 720 MyDOS uses (tools/atr.py Dos2.format)
    img = atr.ATRImage(256 if mydos else 128, 720)
    fs = atr.Dos2.format(img, mydos=mydos)
    fs.add_file("PROG.XEX", prog("PROGRAM RAN"))
    fs.add_file("LOOP.XEX", prog("LOOPING", back=False))
    img.save(path)


def one(name, disk, symname, mydos, work):
    print(f"  -- {name}")
    syms = symfile.load(os.path.join(BUILD, symname))
    d1, d2 = os.path.join(work, f"{symname}-d1.atr"), os.path.join(work, f"{symname}-d2.atr")
    shutil.copy(os.path.join(BUILD, disk), d1)
    make_d2(d2, mydos)
    emu = launch(tag="m68", memsize="1088K", extra_args=["--disk", d1, "--disk", d2])
    b = emu.bridge
    tag = "mydos" if mydos else "dos2"

    def shot(what):
        p = os.path.join(OUT, f"{tag}-{what}.png")
        b.screenshot(p)
        return p

    def desk():
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D2:"))
        t.click(t.gadget(W_FULLER))
        return t

    try:
        boot(b, syms, OUT)
        t = desk()
        t.dclick(t.item("PROG.XEX"))
        f = wait_for(b, lambda ls: any("PROGRAM RAN" in ln for ln in ls), 20000)
        p = shot("prog")
        check(f >= 0, f"{name}: PROG.XEX double-clicked, GEM ended and the program "
                      f"ran ({p}): {lines(b)[-4:]}")
        f = gem_back(b, syms)
        p = shot("back")
        if not check(f >= 0, f"{name}: ...and GEM came back after it ({p}): {lines(b)[-4:]}"):
            return
        print(f"  {name}: GEM back {f} frames after the program")

        t = desk()
        t.dclick(t.item("LOOP.XEX"))
        f = wait_for(b, lambda ls: any("LOOPING" in ln for ln in ls), 20000)
        p = shot("loop")
        check(f >= 0, f"{name}: LOOP.XEX ran ({p}): {lines(b)[-4:]}")
        b.frames(200)
        check(b.peek(COLDST) == 0, f"{name}: COLDST {b.peek(COLDST):#x} while it runs: "
                                   f"the stub did not clear it, so RESET is cold")
        b.ok("WARM_RESET")
        b.frames(30)
        check(b.peek(WARMST) == 0xFF, f"{name}: WARMST {b.peek(WARMST):#x} after RESET: "
                                      f"a cold start, the disk booting again")
        f = gem_back(b, syms)
        p = shot("reset")
        if not check(f >= 0, f"{name}: RESET during LOOP.XEX, GEM came back ({p}): "
                             f"{lines(b)[-4:]}"):
            return
        print(f"  {name}: GEM back {f} frames after the RESET")

        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.choose(FILEMENU, QUITITEM)
        f = wait_for(b, lambda ls: any("SELECT ITEM" in ln.upper() for ln in ls), 20000)
        p = shot("quit")
        check(f >= 0, f"{name}: File -> Quit, the DOS's DUP menu ({p}): {lines(b)[-3:]}")
    finally:
        emu.stop()


def main():
    print("gem4xe-m68: a plain Atari program from the desktop, on MyDOS and DOS 2")
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="m68-")
    try:
        for name, disk, symname, mydos in DOSES:
            one(name, disk, symname, mydos, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m68: {'PASS' if not problems else 'FAIL'} -- a plain Atari program "
          f"from the desktop on MyDOS and DOS 2, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
