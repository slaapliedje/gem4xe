#!/usr/bin/env python3
"""The Control Panel, a window (phase 135, docs/cpanel-plan.md step 2) --
and, while the disk is up, 0.12's item 14: tools/memreport.py's pool
floor is the machine's, and the calculator and the clock hold the screen.

Until phase 135 the panel was a dialog that held the screen (0.12's item
9, phase 97); now it is XControl's shape, a window beside the desktop's,
and this gate drives it as a person would:

  1. Desk -> Control Panel opens a window, on top, listing the disk's
     four modules -- General, the gate's TEST.CPX, Color, and the same
     gate module as FORM.CPX (test-m58's) -- each slot
     with the icon from the header in front of its file (phase 133).
  2. A double-click on General's slot opens it IN THE WINDOW (phase 136,
     the panel's Xform_do); the window is dragged with it up, and Look ->
     3D clicked where it now is and OK switch the look -- and the panel's
     window is still open afterwards with the list back, its work area
     the size it was, though the 3D frame is thicker (WM_SIZED).
     Opened again, its sub-menu delay is a Popup (phase 138): a slow
     click on the button leaves the delay, a click on "Instant" sets it,
     and Cancel puts it back.
  3. THE DESKTOP GOES ON WORKING BESIDE IT: drive D1's icon double-clicked
     opens the desktop's window on top, with the panel's still open --
     which the AES's input rule (phase 134) is what allows.
  4. Its title bar, from behind, tops it again; then the arrow keys move
     the selection.
  5. Dragged by its title bar, it moves, and the slots with it: the event
     CPX opened there draws in the window where it now is, and its
     canned alert and its close come back to the list.
  6. Escape shuts it; reopened, its close box shuts it.
  7. A program started from the desktop with the panel open: AC_CLOSE,
     and the AES takes the window -- the panel says it has none -- and
     after the program the panel opens again.

The places clicked are the panel's own (tests/emu/shots.py, Tour.panel):
it says where its window and slots are, so nothing is measured off a
picture.  General's "3D" is its work area's corner and General's own
layout (tools/generalrsc.py), since General fills the work area.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from PIL import Image                         # noqa: E402
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import (Tour, boot, poke16, PTR_NONE, SYMS, DISK, obj,   # noqa: E402
                   middle, placed, FOLDER, PROGRAM, cstring)
from deskrsc import DESKMENU                  # noqa: E402
from calcrsc import CQUIT                     # noqa: E402
from m7_form import K, F, M, B                # noqa: E402
from aesref import RETURN, ESCAPE, ARROW_DOWN  # noqa: E402
import memreport                              # noqa: E402
import generalrsc as gr                       # noqa: E402

OUT = os.path.join(HERE, "..", "..", "build", "shots", "m44")
CELL = 8                    # the 8-pixel cell, both ways
D1_ICON = (40, 38)          # drive D1's icon on the desk (Tour.desk_icon
                            # reads the flat look's label, and General has
                            # just switched to 3D)
CALC_QUIT = (363, 188)      # the calculator accessory's Quit
RAW_X0 = 16                 # a raw screenshot's left border

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def main():
    print("gem4xe-m44: the Control Panel, a window")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    emu = launch(tag="m44", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        # THE POOL'S FLOOR, while this disk is up anyway: what
        # tools/memreport.py predicts for the product's accessories and
        # modules -- this disk carries the gate's TEST.CPX too, which
        # since phase 133 is listed and not loaded, and the tool reads
        # that from its header -- must be where a running machine puts
        # it.  The model had a stale size for the process records and
        # was a page out (phase 100).
        want = memreport.main([], extra_modules=("m35_cpx",), want_floor=True)
        got = b.peek16(syms["pool_low"])
        check(got == want, f"the pool's permanent floor: the machine's "
                           f"${got:04X}, tools/memreport.py's ${want:04X}")
        # Only the two modules that ask are loaded at boot -- General and
        # Color are CPX_BOOTINIT, TEST.CPX is not (phase 133) -- and both
        # are freed once the panel has boot-initialised them (phase 118).
        n, drops = b.peek16(syms["sh_ncpx"]), b.peek16(syms["sh_cpxdrops"])
        runs = b.peek16(syms["sh_cpxruns"])
        check(n == 4, f"{n} module(s) listed, the disk's 4")
        check(runs == 2, f"{runs} module(s) loaded at boot: General and Color")
        check(drops == runs, f"{drops} of the {runs} module(s) loaded at "
                             f"boot freed after it")
        # ...and every block says what owns it (phase 119): the desktop's
        # near region is the desktop's kind, and each accessory's near
        # region an accessory's -- the tag's top nibble (OWN_*).
        nb = b.peek16(syms["pool_blocks"])
        at = b.memdump(syms["pb_at"], 2 * nb)
        tg = b.memdump(syms["pb_tag"], nb)
        kinds = {at[2 * i] | at[2 * i + 1] << 8: tg[i] >> 4 for i in range(nb)}
        desk = kinds.get(b.peek16(syms["app_near"]))
        accs = sum(1 for k in kinds.values() if k == 2)
        check(desk == 4, f"the desktop's near region is of kind {desk} "
                         f"(4 is OWN_DESK)")
        check(accs >= 3, f"{accs} pool block(s) of kind 2, OWN_ACC (the "
                         f"disk has three accessories)")
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        # THE DESKTOP'S G, kept from here.  Tour.G finds it through
        # app_vars, which is the LAST program loaded's -- and opening a
        # module loads one (Cpxload), so after General the tour would read
        # the module's variables as the desktop's and find no windows.
        # The desktop is not loaded again until step 7's program.
        g0 = t.G()
        t.G = lambda: g0

        # THE OTHER ACCESSORIES WITH A DIALOG hold the screen, from their
        # panel's FMD_START to its FMD_FINISH (phase 101): the calculator
        # closed with its Quit, the clock with any key.
        for name, close in (("Calculator", ("click", CALC_QUIT)),
                            ("Clock", K("SPACE", 0x20))):
            before = b.peek16(syms["wu_count"])
            t.choose(DESKMENU, t.desk_acc(name))
            b.frames(80)
            held = b.peek16(syms["wu_count"])
            if close[0] == "click":
                t.click(close[1])
                b.frames(80)
            else:
                t.run([close, F(80)])
            after = b.peek16(syms["wu_count"])
            check((before, held, after) == (0, 1, 0),
                  f"the {name} holds the screen while it is up "
                  f"(wind_update's count {before} -> {held} -> {after})")

        wtree = b.peek24(syms["gl_wtree"])

        def frame(wh):
            o = obj(b, wtree, wh)
            return o["x"], o["y"], o["w"], o["h"]

        def top():
            return b.peek16(syms["gl_wtop"])

        def inside(p, r):
            return r[0] <= p[0] < r[0] + r[2] and r[1] <= p[1] < r[1] + r[3]

        def shot(name):
            path = os.path.abspath(os.path.join(OUT, f"{name}.png"))
            b.screenshot(path)
            return path

        # ---- 1. the window ------------------------------------------------
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(80)
        t.go((630, 235))
        t.settle()
        p = t.panel()
        print(f"  opened: {p}")
        check(p["wh"] > 0 and top() == p["wh"],
              f"Desk -> Control Panel opened a window on top (window "
              f"{p['wh']}, gl_wtop {top()})")
        check(p["rows"] == 4, f"it lists {p['rows']} module(s), the disk's 4")
        if p["wh"] <= 0:
            return 1
        size0 = p["work"][2:]
        im = Image.open(shot("1-open")).convert("L")
        for k, name in enumerate(("General", "Test", "Color", "Form")):
            sx, sy = p["slots"][k][:2]
            # the icon: 32 x 24 at the slot's icon column, centred in it
            ix, iy = sx + 2 + (88 - 32) // 2, sy + 2
            black = sum(1 for y in range(iy, iy + 24) for x in range(ix, ix + 32)
                        if im.getpixel((x + RAW_X0, y)) < 64)
            check(black > 40, f"{name}'s slot shows its icon ({black} black "
                              f"pixels in its 32 x 24)")

        # ---- 2. a form CPX, from the window --------------------------------
        look0 = b.peek16(syms["gl_3d"])
        t.dclick(middle(p["slots"][0]))           # General
        b.frames(60)
        wx, wy = p["work"][:2]
        im = Image.open(shot("2-general")).convert("L")
        # General's OK button, at the foot of the work area: its frame,
        # which for a DEFAULT button is drawn outside the object -- so the
        # darkest of the rows just above the object's top
        okx, oky = wx + 6 * CELL, wy + gr.BTN_Y * CELL
        edge = max(sum(1 for x in range(okx + 2, okx + 9 * CELL - 2)
                       if im.getpixel((x + RAW_X0, y)) < 64)
                   for y in range(oky - 4, oky + 2))
        check(edge > 50, f"General opened in the panel's window: its OK at "
                         f"the work area's foot ({edge} black pixels along "
                         f"its top edge)")
        # the window dragged with General up: Xform_do moves General's
        # tree with it, or the click below lands on nothing
        fx, fy, fw, fh = frame(p["wh"])
        grab = (fx + fw // 2, fy + 4)
        t.go(grab)
        t.run([B(1), F(6)] + [M(grab[0] - 8 * k, grab[1] + 4 * k)
                              for k in range(1, 5)] + [F(6), B(0), F(10)])
        b.frames(60)
        t.settle()
        wx, wy = t.panel()["work"][:2]
        check((wx, wy) != tuple(p["work"][:2]),
              f"dragged with General up, the window moved "
              f"({tuple(p['work'][:2])} -> {(wx, wy)})")
        gn3d = (wx + (gr.LOOK_X + gr.LOOK_STEP + gr.LOOK_W // 2) * CELL,
                wy + gr.LOOK_Y * CELL + CELL // 2)
        t.click(gn3d)
        b.frames(60)
        t.run([K("RETURN", RETURN), F(100)])      # General's OK
        t.settle()
        p = t.panel()
        check((look0, b.peek16(syms["gl_3d"])) == (0, 1),
              f"General, opened from its slot and its window moved, switched "
              f"the look where it now is ({look0} -> "
              f"{b.peek16(syms['gl_3d'])})")
        check(p["wh"] > 0 and p["opens"] == 1 and p["sel"] == 0,
              f"...and the window is still open with General picked "
              f"(window {p['wh']}, {p['opens']} opened, row {p['sel']})")
        im = Image.open(shot("2-back")).convert("L")
        sx, sy = p["slots"][0][:2]
        black = sum(1 for y in range(sy + 2, sy + 26)
                    for x in range(sx + 30, sx + 62)
                    if im.getpixel((x + RAW_X0, y)) < 64)
        check(black > 40, f"...and the list is back over General's form "
                          f"({black} black pixels in General's icon)")
        # the 3D frame is thicker: the AES sends WM_SIZED, and the panel
        # makes the window the size its contents need again
        check(p["work"][2:] == size0,
              f"...its work area the size it was, in the new look "
              f"({size0} -> {p['work'][2:]})")

        # ---- 2a. General's sub-menu delay, a Popup (phase 138) ------------
        # a click on the button brings the menu up over it; a click on
        # "Instant", its first item, picks it -- the slow click on the
        # button alone must not (src/app/cpx.h, Popup)
        t.dclick(middle(p["slots"][0]))           # General again
        b.frames(60)
        wx, wy = t.panel()["work"][:2]
        ms0 = b.peek16(syms["mn_display"])       # a LONG; 400 at most

        def delay_label():
            # the button's text, out of General's own tree, which the
            # panel's Xform_do is running (Tour.panel's form)
            o = obj(b, t.panel()["form"], gr.GNMNBTN)
            return cstring(b, o["spec"] & 0xFFFFFF, 12)
        lab0 = delay_label()
        btn = (wx + (gr.GROUP_X + gr.MN_W // 2) * CELL, wy + 7 * CELL + CELL // 2)
        # held well past the menu coming up, then let go without moving:
        # a plain CLICK lets go before the menu samples the button, and
        # proved nothing (it passed with the rule taken out)
        t.go(btn)
        t.run([B(1), F(60), B(0), F(30)])
        t.settle()
        ms1 = b.peek16(syms["mn_display"])
        shot("2a-popup")
        t.click((wx + (gr.GROUP_X + 2) * CELL, wy + 7 * CELL - 1 + 2 + 4))
        b.frames(30)
        t.settle()
        ms2 = b.peek16(syms["mn_display"])
        lab2 = delay_label()
        check((lab0, lab2) == ("Normal", "Instant"),
              f"its button names the delay: {lab0!r}, then {lab2!r}")
        check((ms0, ms1, ms2) == (200, 200, 0),
              f"General's sub-menu delay, a Popup: the button's slow click "
              f"left it, a click on Instant set it ({ms0} -> {ms1} -> {ms2} ms)")
        t.click((wx + 21 * CELL, wy + gr.BTN_Y * CELL + CELL // 2))  # Cancel
        b.frames(60)
        t.settle()
        check(b.peek16(syms["mn_display"]) == 200,
              f"...and Cancel put it back ({b.peek16(syms['mn_display'])} ms)")

        # ---- 3. the desktop beside it -------------------------------------
        calls = b.peek16(syms["app_calls"])
        t.dclick(D1_ICON)
        b.frames(200)
        t.settle()
        dwh = top()
        p = t.panel()
        check(dwh not in (0, p["wh"]) and p["wh"] > 0,
              f"with the panel open, D1's icon opened the desktop's window "
              f"on top (gl_wtop {dwh}, the panel's {p['wh']} still open)")
        check(b.peek16(syms["app_calls"]) != calls,
              "the desktop worked while the panel was up")
        shot("3-beside")

        # ---- 4. topped from behind, then the keys -------------------------
        fx, fy, fw, fh = frame(p["wh"])
        d = frame(dwh)
        bar = next(((x, fy + 4) for x in range(fx + 24, fx + fw - 8, 8)
                    if not inside((x, fy + 4), d)), None)
        check(bar is not None, "some of the panel's title bar shows")
        if bar:
            t.click(bar)
            b.frames(60)
            t.settle()
        check(top() == p["wh"], f"its title bar topped it (gl_wtop {top()})")
        sels = []
        for _ in range(2):
            t.run([K("EQUALS", ARROW_DOWN, ctrl=True), F(40)])
            t.settle()
            sels.append(t.panel()["sel"])
        check(sels == [1, 2], f"the down arrow moved the selection 0 -> "
                              f"{sels} (wanted [1, 2])")

        # ---- 5. moved, and the event CPX where it now is ------------------
        fx, fy, fw, fh = frame(p["wh"])
        grab = (fx + fw // 2, fy + 4)
        t.go(grab)
        t.run([B(1), F(6)] + [M(grab[0] + 12 * k, grab[1] + 4 * k)
                              for k in range(1, 6)] + [F(6), B(0), F(10)])
        b.frames(60)
        t.settle()
        q = t.panel()
        print(f"  dragged: work {p['work']} -> {q['work']}")
        check(q["work"][:2] != p["work"][:2]
              and q["slots"][1][0] - q["work"][0] == p["slots"][1][0] - p["work"][0],
              f"dragged by its bar, the window and its slots moved "
              f"({p['work'][:2]} -> {q['work'][:2]})")
        t.dclick(middle(q["slots"][1]))           # the gate's event CPX
        b.frames(80)
        im = Image.open(shot("5-event")).convert("L")
        wx, wy = q["work"][:2]
        # TEST.CPX draws its outlined box at the work area's (24, 96)
        edge = sum(1 for x in range(wx + 30, wx + 120)
                   if im.getpixel((x + RAW_X0, wy + 96)) < 64)
        check(edge > 60, f"the event CPX drew in the window where it is now "
                         f"({edge} black pixels along its box's top edge)")
        t.run([K("RETURN", RETURN), F(60)])       # its canned alert
        t.run([K("RETURN", RETURN), F(80)])       # ...and it closes
        t.settle()
        q = t.panel()
        check(q["wh"] > 0 and q["opens"] == 3,       # General twice, TEST
              f"...and the list came back ({q['opens']} opened, window "
              f"{q['wh']})")

        # ---- 6. Escape, then the close box ---------------------------------
        t.run([K("ESC", ESCAPE), F(80)])
        t.settle()
        check(t.panel()["wh"] == -1 and top() == dwh,
              f"Escape shut it (window {t.panel()['wh']}, gl_wtop {top()})")
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(80)
        t.settle()
        p = t.panel()
        if p["wh"] > 0:
            fx, fy, _, _ = frame(p["wh"])
            t.click((fx + 4, fy + 4))
            b.frames(60)
            t.settle()
        check(p["wh"] > 0 and t.panel()["wh"] == -1,
              f"reopened (window {p['wh']}), its close box shut it")

        # ---- 7. a program started: AC_CLOSE --------------------------------
        t.dclick(t.item(FOLDER))
        b.frames(120)
        t.settle()
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(80)
        t.settle()
        p = t.panel()
        # out of the program's way: the folder's window is under it
        fx, fy, fw, fh = frame(p["wh"])
        grab = (fx + fw // 2, fy + 4)
        t.go(grab)
        t.run([B(1), F(6)] + [M(grab[0] + 30 * k, grab[1] + 10 * k)
                              for k in range(1, 6)] + [F(6), B(0), F(10)])
        b.frames(60)
        t.settle()
        fwh = top()
        fr = frame(dwh if fwh == p["wh"] else fwh)
        spot = (fr[0] + 40, fr[1] + 4)            # the folder window's bar
        t.click(spot)
        b.frames(60)
        t.settle()
        closes = t.panel()["wh"]
        t.launch(lambda: t.dclick(t.item(PROGRAM)), "the calculator")
        b.frames(60)
        gone = t.panel()["wh"]
        check(closes > 0 and gone == -1,
              f"a program started with the panel open: AC_CLOSE, and the "
              f"panel has no window (it had {closes}, now {gone})")
        del t.G                                   # the calculator is loaded
        calc = b.peek16(t.csym["tree"] + b.peek16(syms["app_near"]) - t.clink)
        keys = placed(b, calc)
        t.launch(lambda: t.click(middle(keys[CQUIT])), "the desktop", t.bar_up)
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(80)
        t.settle()
        p = t.panel()
        check(p["wh"] > 0 and top() == p["wh"],
              f"after the program, the panel opened again (window {p['wh']})")
        shot("7-again")
        check(b.peek16(syms["gem_bad"]) == 0,
              f"{b.peek16(syms['gem_bad'])} call(s) refused")
    finally:
        emu.stop()
    print(f"gem4xe-m44: {'PASS' if not problems else 'FAIL'} -- the Control "
          f"Panel, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
