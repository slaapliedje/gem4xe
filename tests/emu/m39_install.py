#!/usr/bin/env python3
"""Phase 61 gate: Install application, and a document opening its program.

On the product disk, driven at the mouse.  The dialog is in PREFS.RSC,
which the desktop could not load at all while GENERAL.CPX's resource
was recorded as the desktop's own (src/aes/rsrc.c rs_hold,
docs/phase61.md) -- so this is also the gate for that.

    APPS\\CALC.PRG selected, Options -> Install application, type BAT
    STARTUP.BAT double-clicked       the shell asked to run CALC.PRG with
                                     A:\\STARTUP.BAT as its command tail
    the calculator's Quit, then the same double-click again
                                     the same -- the desktop that came back
                                     read the install out of DESKTOP.INF
                                     in the shell buffer
    GEM4XE.CFG dropped on DESKTOP.PRG, both in \\GEM\\
                                     the shell asked to run DESKTOP.PRG with
                                     A:\\GEM\\GEM4XE.CFG

What is checked is what the desktop ASKED the shell for -- the program
and the tail in the shell's own buffers (src/aes/shel.c sh_cmd_far,
sh_tail_far) -- because that is the desktop's whole part in it; whether
a program reads its tail is the program's business.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import shots                                  # noqa: E402
from shots import (Tour, boot, poke16, PTR_NONE, SYMS, DISK, placed,   # noqa: E402
                   middle, CLICK, B, F, path)
from aesref import W_FULLER                   # noqa: E402
from deskrsc import OPTNMENU, IAPPITEM, FILEMENU, CLOSITEM   # noqa: E402
from calcrsc import CQUIT                     # noqa: E402

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def asked(b, syms):
    """The program and the command tail the shell was last asked for."""
    cmd = shots.cstring(b, b.peek24(syms["sh_cmd_far"]), 64)
    raw = bytes(b.memdump(b.peek24(syms["sh_tail_far"]), 64))
    tail = raw[1:1 + raw[0]].decode("latin-1") if raw[0] < 63 else ""
    return cmd, tail


def calc_quit(t, b, syms):
    tree = b.peek16(t.csym["tree"] + b.peek16(syms["app_near"]) - t.clink)
    keys = placed(b, tree)
    t.launch(lambda: t.click(middle(keys[CQUIT])), "the desktop", t.bar_up)


def main():
    print("gem4xe-m39: Install application, and documents opening programs")
    syms = symfile.load(SYMS)
    out = os.path.join(HERE, "..", "..", "build", "shots", "m39")
    os.makedirs(out, exist_ok=True)
    emu = launch(tag="m39", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(10)

        t.dclick(t.desk_icon("DISK A"))
        t.dclick(t.item("APPS"))
        t.click(t.item("CALC.PRG"))
        t.choose(OPTNMENU, IAPPITEM)
        b.frames(10)
        t.settle()
        for c in "BAT":
            b.key(c)
            b.frames(3)
        b.key("RETURN")                         # Install: the default
        t.settle()

        t.choose(FILEMENU, CLOSITEM)            # back up to A:\
        t.click(t.gadget(W_FULLER))             # the BATs are below its edge
        t.launch(lambda: t.dclick(t.item("STARTUP.BAT")), "the calculator")
        cmd, tail = asked(b, syms)
        check(cmd.endswith("\\APPS\\CALC.PRG") and tail == "A:\\STARTUP.BAT",
              f"a BAT document runs CALC.PRG with its path "
              f"(asked for {cmd!r}, tail {tail!r})")
        calc_quit(t, b, syms)

        t.launch(lambda: t.dclick(t.item("STARTUP.BAT")), "the calculator")
        cmd2, tail2 = asked(b, syms)
        check((cmd2, tail2) == (cmd, tail) and b.peek16(syms["sh_runs"]) > 0,
              "...and again after the desktop came back: the install was "
              "in DESKTOP.INF")
        calc_quit(t, b, syms)

        t.dclick(t.item("GEM"))                 # fulled already
        src, dst = t.item("GEM4XE.CFG"), t.item("DESKTOP.PRG")
        runs = b.peek16(syms["sh_runs"])
        t.go(src)
        t.run([B(1), F(4)] + path(src, dst, speed=4) + [F(4), B(0), F(4)])
        for _ in range(300):
            if b.peek16(syms["sh_runs"]) != runs:
                break
            b.frames(10)
        cmd3, tail3 = asked(b, syms)
        check(cmd3.endswith("\\GEM\\DESKTOP.PRG")
              and tail3 == "A:\\GEM\\GEM4XE.CFG",
              f"a file dropped on a program runs it with the file "
              f"(asked for {cmd3!r}, tail {tail3!r})")
    finally:
        emu.stop()
    print(f"gem4xe-m39: {'FAIL' if problems else 'PASS'} -- Install application, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
