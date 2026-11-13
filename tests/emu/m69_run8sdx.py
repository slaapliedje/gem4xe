#!/usr/bin/env python3
"""Phase 164 gate: a plain Atari program run from the desktop under
SpartaDOS X (docs/run8-plan.md, step 3).

The system floppy with the SDX cartridge, as it boots for anybody who has
one: SDX runs AUTOEXEC.BAT, which starts GEM from \\GEM.  In D2: an SDFS
disk with \\GAMES\\PROG.XEX, a program that prints a line and returns, and
LOOP.XEX, one that prints a line and loops for ever.

  1. PROG.XEX double-clicked: GEM writes RUN8.BAT beside GEM.COM -- the
     program, then GEM -- sets BATCH= to it and ends.  SDX's command
     processor runs the batch before its prompt: PROG.XEX's line, then GEM
     again, the boot screen and the desktop.
  2. PROG.XEX again from that GEM, which runs while SDX still has
     RUN8.BAT open -- so through RUN9.BAT -- and GEM back.  Then LOOP.XEX
     from the GEM RUN9.BAT started, through RUN8.BAT again: its line, and
     RESET.  SDX abandons a batch at RESET, so this is SDX's prompt.
  3. GEM started from that prompt, then File -> Quit: SDX's prompt, and
     the batch does not run a second time -- SDX deletes BATCH= as it
     reads it.

    python3 tests/emu/m69_run8sdx.py
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
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from deskrsc import FILEMENU, QUITITEM        # noqa: E402
from fdos_shell import lines, wait_for        # noqa: E402
from m67_run8 import make_d2, gem_back        # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "run8sdx")
TAG = "m69"
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def cart():
    import tomllib
    with open(os.path.join(ROOT, "fixtures.toml"), "rb") as f:
        return tomllib.load(f)["spartados"]["sdx_cart"]


def main():
    print("gem4xe-m69: a plain Atari program from the desktop, under SpartaDOS X")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m69-")
    d1, d2 = os.path.join(work, "d1.atr"), os.path.join(work, "d2.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), d1)
    make_d2(d2)
    sha = hashlib.sha256(open(d1, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for(TAG), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    emu = launch(tag=TAG, memsize="1088K",
                 extra_args=["--bootrw", "--disk", d1, "--disk", d2, "--cart", cart()])
    b = emu.bridge

    def shot(name):
        p = os.path.join(OUT, f"{name}.png")
        b.screenshot(p)
        return p

    def desk():
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D2:"))
        t.click(t.gadget(W_FULLER))
        return t

    def prompt(ls):
        return bool(ls) and ls[-1].endswith(":") and ls[-1][:1] == "D"

    try:
        boot(b, syms, OUT)
        t = desk()
        t.dclick(t.item("GAMES"))
        t.dclick(t.item("PROG.XEX"))
        f = wait_for(b, lambda ls: any("PROGRAM RAN" in ln for ln in ls), 20000)
        p = shot("prog")
        check(f >= 0, f"PROG.XEX double-clicked: GEM ended and SDX's batch ran it "
                      f"({p}): {lines(b)[-4:]}")
        f = gem_back(b, syms)
        p = shot("back")
        if not check(f >= 0, f"...and then GEM, the batch's second line ({p}): "
                             f"{lines(b)[-4:]}"):
            return 1
        print(f"  GEM back {f} frames after the program")

        # again, from the GEM RUN8.BAT started: RUN9.BAT this time
        t = desk()
        t.dclick(t.item("GAMES"))
        t.dclick(t.item("PROG.XEX"))
        f = wait_for(b, lambda ls: any("PROGRAM RAN" in ln for ln in ls), 20000)
        g = gem_back(b, syms) if f >= 0 else -1
        p = shot("prog2")
        if not check(f >= 0 and g >= 0, f"PROG.XEX again, from the GEM the batch started: "
                                        f"ran, and GEM back ({p})"):
            return 1

        t = desk()
        t.dclick(t.item("LOOP.XEX"))
        f = wait_for(b, lambda ls: any("LOOPING" in ln for ln in ls), 20000)
        p = shot("loop")
        check(f >= 0, f"LOOP.XEX ran ({p}): {lines(b)[-4:]}")
        b.frames(200)
        b.ok("WARM_RESET")
        f = wait_for(b, prompt, 6000)
        p = shot("reset")
        check(f >= 0, f"RESET during LOOP.XEX: SDX's prompt, the batch stopped ({p}): "
                      f"{lines(b)[-3:]}")

        for ch in "GEM":
            b.key(ch)
            b.frames(4)
        b.key("RETURN")
        f = gem_back(b, syms)
        if not check(f >= 0, f"GEM typed at the prompt: the desktop ({shot('again')})"):
            return 1
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.choose(FILEMENU, QUITITEM)
        f = wait_for(b, prompt, 6000)
        b.frames(300)
        p = shot("quit")
        ls = lines(b)
        check(f >= 0 and prompt(ls) and not any("PROGRAM RAN" in ln or "LOOPING" in ln
                                                for ln in ls),
              f"File -> Quit: SDX's prompt, and no batch run again ({p}): {ls[-3:]}")
    finally:
        emu.stop()

    written = os.path.join(state, "disk.atr")
    if check(os.path.exists(written), "the emulator wrote D1:'s working copy"):
        fs = atr.Sdfs(atr.ATRImage.load(written))
        # RUN8.BAT, RUN9.BAT, RUN8.BAT: each GEM a batch started runs while
        # SDX still has that batch open, so the next program takes the
        # other -- the third, LOOP.XEX, back in RUN8.BAT
        for name, want in (("RUN8.BAT", b"D2:>LOOP.XEX"), ("RUN9.BAT", b"D2:>GAMES>PROG.XEX")):
            bat = fs.read("GEM>" + name) if fs.find("GEM>" + name) else None
            check(bat is not None and bat.split(b"\x9b")[:2] == [want, b"D1:GEM.COM"],
                  f"D1:>GEM>{name} holds {want.decode()} and GEM: {bat!r}")
        check(not fs.check(), f"D1:'s SDFS: {fs.check()[:3]}")
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m69: {'PASS' if not problems else 'FAIL'} -- a plain Atari program "
          f"from the desktop under SpartaDOS X, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
