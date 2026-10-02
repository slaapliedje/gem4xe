#!/usr/bin/env python3
"""0.12's gate for item 9: the Control Panel keeps the screen while it is up.

Desk -> Control Panel -> General -> Look: 3D -> OK.  General's OK redraws
the whole screen, because everything on it was drawn in the other look,
and the AES sends every window's owner a redraw (src/apps/general.c).  The
panel is a DIALOG, not a window, so no window's rectangle list knows to
stay off it: on GEM an accessory holds wind_update(BEG_UPDATE) while its
dialog is up and every other program's redraw waits.  Here BEG_UPDATE was
a count, and the desktop repainted its window over the panel while the
panel was still open (phase 97).

So the panel is photographed after General's OK twice: once with nothing
under it, once with drive D1's window open under it.  The panel's
rectangle must be the same pixels both times -- nothing of the window on
it -- and when the panel closes the desktop must draw (its calls rise),
in the new look.

The places clicked are MEASURED off the panel's and General's pictures,
as tests/emu/shots.py measures CPX_ROW1: the panel is an accessory, its
objects in its own memory.  The look changing to 3D is what proves the
click on General's "3D" landed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from PIL import Image                         # noqa: E402
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import (Tour, boot, poke16, PTR_NONE, SYMS, DISK,   # noqa: E402
                   CPX_ROW1, CPX_OPEN)
from deskrsc import DESKMENU                  # noqa: E402
from m7_form import K, F                      # noqa: E402
from aesref import RETURN                     # noqa: E402

OUT = os.path.join(HERE, "..", "..", "build", "shots", "m44")
GN_3D = (319, 148)          # General's "Look: 3D", on the screen
D1_ICON = (40, 38)          # drive D1's icon on the desk
# the panel as the raw screenshot has it: inside its frame, and away from
# the pointer, which is parked at the screen's corner
PANEL = (180, 28, 492, 220)

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def run(window):
    """One boot: the panel after General's OK, as a PNG path, and what the
    look and the desktop did afterwards."""
    tag = "window" if window else "bare"
    syms = symfile.load(SYMS)
    emu = launch(tag=f"m44{tag}", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        if window:
            t.dclick(D1_ICON)
            b.frames(200)
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(60)
        t.click(CPX_ROW1)
        b.frames(20)
        t.click(CPX_OPEN)
        b.frames(60)
        look0 = b.peek16(syms["gl_3d"])
        t.click(GN_3D)
        b.frames(60)
        t.run([K("RETURN", RETURN), F(80)])         # General's OK
        t.go((630, 235))
        b.frames(200)                               # time for any redraw
        shot = os.path.abspath(os.path.join(OUT, f"panel-{tag}.png"))
        b.screenshot(shot)
        calls = b.peek16(syms["app_calls"])
        t.run([K("RETURN", RETURN), F(150)])        # the panel's OK
        b.screenshot(os.path.abspath(os.path.join(OUT, f"closed-{tag}.png")))
        return shot, look0, b.peek16(syms["gl_3d"]), \
            (b.peek16(syms["app_calls"]) - calls) & 0xFFFF
    finally:
        emu.stop()


def main():
    print("gem4xe-m44: the Control Panel keeps the screen while it is up")
    os.makedirs(OUT, exist_ok=True)
    bare, look0, look1, _ = run(window=False)
    check((look0, look1) == (0, 1), f"General switched the look ({look0} -> {look1})")
    covered, _, _, drew = run(window=True)
    a = Image.open(bare).convert("RGB").crop(PANEL)
    w = Image.open(covered).convert("RGB").crop(PANEL)
    pa, pw = a.load(), w.load()
    diff = [(x, y) for y in range(a.size[1]) for x in range(a.size[0])
            if pa[x, y] != pw[x, y]]
    check(not diff, f"the panel is the same with a window under it "
                    f"({len(diff)} pixels differ"
                    + (f", first at {diff[0]})" if diff else ")"))
    check(drew > 0, f"the desktop drew once the panel closed ({drew} calls)")
    print(f"gem4xe-m44: {'PASS' if not problems else 'FAIL'} -- the Control "
          f"Panel, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
