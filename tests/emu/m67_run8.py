#!/usr/bin/env python3
"""Phase 162 gate: a plain Atari program run from the desktop on G4DOS
(docs/run8-plan.md, step 1).

The G4DOS system floppy in D1:, and in D2: an SDFS disk holding
\\GAMES\\PROG.XEX, a program that prints a line and returns, and LOOP.XEX,
one that prints a line and loops for ever.

  1. D2: opened, GAMES opened, PROG.XEX double-clicked: GEM ends, the shell
     runs PROG.XEX -- its line is on the screen -- and when it returns, the
     shell runs GEM again: the boot screen, then the desktop.  The note in
     the cassette buffer is gone.
  2. LOOP.XEX double-clicked: its line is on the screen, it never ends,
     RESET -- and GEM comes back from that too.
  3. M53.PRG started from D2: and put aside with CONTROL-TAB, then LOOP.XEX
     double-clicked: refused, because GEM's ending would lose M53 -- the
     alert says to quit it first, sh_lastrc is APP_E_PLAIN, the desktop
     comes back with M53 still aside, and LOOP.XEX has not run.
  4. With no note, RESET goes to the shell's prompt, as before: the note
     is used once.

    python3 tests/emu/m67_run8.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from product_boot import boot_screen          # noqa: E402
from fdos_shell import prog, lines, wait_for, fresh   # noqa: E402
from sdx816 import find_text                  # noqa: E402
from m17_desktop import header                # noqa: E402
from aesref import W_FULLER                   # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "run8")
NOTE = 0x0444                                 # src/sys/runnote.h
APP = os.path.join(BUILD, "m53_app.g4a")      # the switcher gate's program
APP_E_PLAIN = -14                             # src/sys/app.h
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def make_d2(path):
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "PLAIN")
    fs.mkdir("GAMES")
    fs.add_file("GAMES>PROG.XEX", prog("PROGRAM RAN"))
    fs.add_file("LOOP.XEX", prog("LOOPING", back=False))
    img.save(path)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"),
                        path, APP, "M53.PRG"], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"install.py: {r.stderr.strip()}")


def gem_back(b, syms, most=40000):
    """GEM started again: its boot screen, then the desktop settled.  The
    frames it took, or -1."""
    f = 0
    while f < most and boot_screen(b) is None:
        b.frames(50)
        f += 50
    if f >= most:
        return -1
    calls = syms["app_calls"]
    n, still = b.peek16(calls), 0
    while f < most:
        b.frames(250)
        f += 250
        now = b.peek16(calls)
        still = still + 1 if now == n else 0
        n = now
        if still >= 2 and now:
            return f
    return -1


def main():
    print("gem4xe-m67: a plain Atari program from the desktop, on G4DOS")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m67-")
    d1, d2 = os.path.join(work, "d1.atr"), os.path.join(work, "d2.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), d1)
    make_d2(d2)
    emu = launch(tag="m67", memsize="1088K", extra_args=["--disk", d1, "--disk", d2])
    b = emu.bridge

    def shot(name):
        p = os.path.join(OUT, f"{name}.png")
        b.screenshot(p)
        return p

    def desk(syms):
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D2:"))
        t.click(t.gadget(W_FULLER))     # every entry in view
        return t

    try:
        boot(b, syms, OUT)
        t = desk(syms)
        t.dclick(t.item("GAMES"))
        t.dclick(t.item("PROG.XEX"))
        f = wait_for(b, lambda ls: any("PROGRAM RAN" in ln for ln in ls), 20000)
        p = shot("prog")
        check(f >= 0, f"PROG.XEX double-clicked: GEM ended and the program ran, "
                      f"its line on the screen ({p}): {lines(b)[-4:]}")
        f = gem_back(b, syms)
        p = shot("back")
        if not check(f >= 0, f"...and GEM came back after it ({p}): {lines(b)[-4:]}"):
            return 1
        check(b.peek(NOTE) == 0, f"the note is gone once used: {b.peek(NOTE):#x}")
        print(f"  GEM back {f} frames after the program")

        t = desk(syms)
        t.dclick(t.item("LOOP.XEX"))
        f = wait_for(b, lambda ls: any("LOOPING" in ln for ln in ls), 20000)
        p = shot("loop")
        check(f >= 0, f"LOOP.XEX ran, its line on the screen ({p}): {lines(b)[-4:]}")
        b.frames(200)
        b.ok("WARM_RESET")
        f = gem_back(b, syms)
        p = shot("reset")
        if not check(f >= 0, f"RESET during LOOP.XEX: GEM came back ({p}): {lines(b)[-4:]}"):
            return 1
        print(f"  GEM back {f} frames after the RESET")

        # -- a program aside: refused ----------------------------------------
        psym = symfile.load(os.path.join(BUILD, "m53_app.sym"))
        plink = header(APP)[0]

        def desk_runs():
            return b.peek16(syms["sh_deskrun"]) != 0

        def until(pred, limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if pred():
                    return True
            return False

        t = desk(syms)
        t.dclick(t.item("M53.PRG"))
        ready = until(lambda: not desk_runs() and b.peek16(
            psym["r_ready"] - plink + b.peek16(syms["app_near"])) == 1)
        p = shot("m53")
        if not check(ready, f"M53.PRG started from D2: ({p}, sh_lastrc "
                            f"{b.peek16(syms['sh_lastrc']):#x})"):
            return 1
        b.key("TAB", ctrl=True)
        if not check(until(desk_runs), "CONTROL-TAB: the desktop, M53 aside"):
            return 1
        t.settle()
        runs = b.peek16(syms["sh_runs"])
        t.dclick(t.item("LOOP.XEX"))
        b.frames(300)
        p = shot("aside")
        rc = b.peek16(syms["sh_lastrc"])
        rc = rc - 0x10000 if rc & 0x8000 else rc
        check(rc == APP_E_PLAIN, f"LOOP.XEX with M53 aside: sh_lastrc {rc}, "
                                 f"wanted APP_E_PLAIN ({APP_E_PLAIN})")
        check(find_text(p, "needs all") is not None,
              f"...and the alert says why ({p})")
        b.key("RETURN")
        check(until(lambda: desk_runs() and b.peek16(syms["sh_runs"]) > runs),
              "...OK, and the desktop is back")
        t.settle()
        check(not any("LOOPING" in ln for ln in lines(b)), "...LOOP.XEX did not run")
        check(b.peek(NOTE) == 0, f"...and there is no note: {b.peek(NOTE):#x}")
        print("  refused with M53 aside: the alert, the desktop back, no note")

        b.ok("WARM_RESET")
        f = wait_for(b, fresh, 20000)
        p = shot("prompt")
        check(f >= 0, f"RESET with no note: the shell's prompt, as before ({p}): "
                      f"{lines(b)[-3:]}")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m67: {'PASS' if not problems else 'FAIL'} -- a plain Atari "
          f"program from the desktop, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
