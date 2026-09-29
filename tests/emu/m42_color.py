"""The Color control panel extension (0.9, item 6; docs/phase69.md).

On the VBXE desk, through the Control Panel as a person reaches it:

  1. COLOR.CPX is loaded and listed: the panel's third module, after
     GENERAL.CPX and the gate's TEST.CPX (the shots disk's order).
  2. Its row of swatches IS the palette: the red one shows pen 2 as the
     screen has it, (255, 0, 0).
  3. Pen 2 picked and red stepped down four times: the swatch is (187,
     0, 0) at once -- level 11, which is also the standard palette's
     dark red, so the arithmetic is the palette's own.
  4. Cancel puts it back: opened again, the swatch is (255, 0, 0).
  5. The same four steps and OK, then a COLD RESET: the machine boots,
     the panel puts the saved palette back (CPX_BOOTINIT), and the
     swatch is (187, 0, 0) before anybody has touched it.  Step 2 was
     the same boot without a save, so this is the saved palette and not
     a default.

The swatch is found by its colour in the screenshot, and every other
place is worked out from it and the resource's own layout
(tools/colorrsc.py), so the gate does not depend on where form_center
puts the dialog.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import colorrsc as cr                         # noqa: E402
from shots import (Tour, boot, poke16, PTR_NONE, SYMS, CPX_ROW2,   # noqa: E402
                   CPX_OPEN)
from deskrsc import DESKMENU                  # noqa: E402
from PIL import Image                         # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "gem-shots.atr"))
RAW_X0 = 16                     # a raw VBXE screenshot's left border
CELL = 8                        # the VBXE face's cell, both ways
ROW3 = (CPX_ROW2[0], CPX_ROW2[1] + 8)
RED, DARK_RED = (255, 0, 0), (187, 0, 0)

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


class Dialog:
    """Where the Color dialog is, from the red swatch in a screenshot."""

    def __init__(self, t, name):
        self.t = t
        self.px, (w, h) = self.grab(name)
        pts = [(x, y) for y in range(h) for x in range(w)
               if self.px[x, y] == RED]
        if not pts:
            raise SystemExit(f"FAIL: no red swatch in {name}: is the dialog up?")
        sx, sy = min(p[0] for p in pts) - RAW_X0, min(p[1] for p in pts)
        # the fill is one pixel inside the swatch's border
        self.ox = sx - 1 - (cr.SW_X + 2 * cr.SW_W) * CELL
        self.oy = sy - 1 - cr.SW_Y * CELL

    def grab(self, name):
        self.t.b.frames(4)
        path = self.t.shot(name)
        raw = os.path.join(ROOT, "build", "shots", f"tour-{name}.png")
        im = Image.open(raw if os.path.exists(raw) else path).convert("RGB")
        return im.load(), im.size

    def at(self, cx, cy, dx=None):
        """The middle of a cell range: cx cells in, cy cells down."""
        return (self.ox + cx * CELL + (dx if dx is not None else CELL // 2),
                self.oy + cy * CELL + CELL // 2)

    def swatch(self, pen):
        return self.at(cr.SW_X + cr.SW_W * pen, cr.SW_Y, CELL)

    def swatch_colour(self, pen, name):
        px, _ = self.grab(name)
        x, y = self.swatch(pen)
        return px[x + RAW_X0, y]

    def button(self, cx, cy, w):
        return self.at(cx, cy, w * CELL // 2)


def open_color(t):
    t.choose(DESKMENU, t.desk_acc("Control Panel"))
    t.b.frames(60)
    t.click(ROW3)
    t.b.frames(20)
    t.click(CPX_OPEN)
    t.b.frames(80)
    t.go((600, 220))
    t.b.frames(20)


def step_red_down(t, d, n):
    t.click(d.swatch(2))
    t.b.frames(10)
    minus = d.button(10, cr.CH_Y, 3)            # Red's "-" (colorrsc)
    for _ in range(n):
        t.click(minus)
        t.b.frames(10)


def main():
    print("gem4xe-m42: the Color control panel extension")
    syms = symfile.load(SYMS)
    out = os.path.join(ROOT, "build", "shots", "m42")
    os.makedirs(out, exist_ok=True)
    emu = launch(tag="m42", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(20)
        t.settle()
        check(b.peek16(syms["sh_ncpx"]) == 3 and b.peek16(syms["sh_cpxbad"]) == 0,
              f"three modules loaded, none refused "
              f"({b.peek16(syms['sh_ncpx'])}, {b.peek16(syms['sh_cpxbad'])})")

        open_color(t)
        d = Dialog(t, "m42-open")
        c = d.swatch_colour(2, "m42-open")
        check(c == RED, f"pen 2's swatch shows the screen's red: {c}")

        step_red_down(t, d, 4)
        c = d.swatch_colour(2, "m42-stepped")
        check(c == DARK_RED, f"four steps down and it is (187, 0, 0) at once: {c}")

        t.click(d.button(27, 13, 8))            # Cancel
        b.frames(30)
        t.click(ROW3)
        b.frames(20)
        t.click(CPX_OPEN)
        b.frames(80)
        t.go((600, 220))
        c = d.swatch_colour(2, "m42-cancelled")
        check(c == RED, f"...and Cancel put it back: {c}")

        step_red_down(t, d, 4)
        t.click(d.button(15, 13, 8))            # OK: saved
        b.frames(60)
        b.key("RETURN")                         # the panel's own OK
        b.frames(60)
        t.settle()

        b.ok("COLD_RESET")
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(20)
        t.settle()
        open_color(t)
        c = d.swatch_colour(2, "m42-rebooted")
        check(c == DARK_RED, f"after OK and a cold reset, the saved palette "
                             f"is back at boot: {c}")
    finally:
        emu.stop()
    print(f"gem4xe-m42: {'FAIL' if problems else 'PASS'} -- the Color "
          f"module, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
