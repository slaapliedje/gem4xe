#!/usr/bin/env python3
"""The CPX toolkit (phases 137 and 138, docs/cpanel-plan.md step 3).

The shots disk carries the gate's module twice: TEST.CPX, an event CPX,
and FORM.CPX, the same module under a header whose buffer starts 'F', a
form CPX (src/m35_cpx.c).  The module counts what the panel does for it
into its own 64 settings bytes -- the buffer in the AES's table, which
outlives the module when it is freed at its close -- and this gate reads
them there (K_* below, the module's).

  1. TEST.CPX opened from its slot: cpx_init came with the panel's XCPB;
     it drew its box through GetFirstRect / GetNextRect; getcookie said
     there is no 'NVDI'; MFsave was there.
  2. Set_Evnt_Mask: the pointer onto its box is a cpx_m1, and its 50 ms
     timer ticks.
  3. cpx_hook first: the key 'h' is taken there, and cpx_key never sees
     it.
  4. The window's closer: cpx_close, with keep 1 -- and the panel shut.
  5. FORM.CPX: Help is a key with no character, so Xform_do answers -1
     with CT_KEY, and the form goes on.  Its Popup of seven items (phase
     138): held on its down arrow until it scrolls no further, its last
     item shown is picked -- the seventh.  Its list slider: the thumb
     dragged to the bottom is the last first row, 7, with foo called; the
     up arrow, once, is 6.  Its Done button ends it.
  6. FORM.CPX again, ended by the window's closer: Xform_do's -1 with
     WM_CLOSED.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK, obj, middle   # noqa: E402
from deskrsc import DESKMENU                  # noqa: E402
from m7_form import K, F, M, B                # noqa: E402

OUT = os.path.join(ROOT, "build", "shots", "m58")
SHEL_C = os.path.join(ROOT, "src", "aes", "shel.c")
TEST_SLOT, FORM_SLOT = 1, 3     # the shots disk's order: GENERAL, TEST,
                                # COLOR, FORM (Makefile, SP_APPS)
BUF = 142                       # the header's settings bytes (cpx.h's map)

# src/m35_cpx.c's record, and its box and button
(K_MODE, K_INITX, K_HOOK, K_TAKEN, K_KEY, K_M1, K_TIMER, K_CLOSE, K_KEEP,
 K_RECTS, K_COOKIE, K_CTKEY, K_FORMX, K_MFSAVE, K_CALL,
 K_POPUP, K_SLVAL, K_FOO) = range(18)
BOX = (24, 96, 27 * 8, 24)      # BOX_X, BOX_Y, the message's cells, BOX_H
DONE = (96, 120, 64, 12)        # DONE_X, DONE_Y, DONE_W, DONE_H
POP = (24, 20, 80, 12)          # POP_X, POP_Y, POP_W, POP_H
SLX, SLY, SLW, SLAH, SLTH = 200, 20, 16, 12, 64   # the slider's (SL_*)
PU_ROW = 8 + 4                  # a Popup slot: the cell and 4 (cpanel.c)

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def define(name):
    src = open(SHEL_C).read()
    m = re.search(rf"^#define\s+{name}\s+(\S+)", src, re.M)
    return int(m.group(1), 0)


CPX_MAX = define("CPX_MAX")
CPXE_HDR = define("CPXE_HDR")
CPXE_SIZE = CPXE_HDR + define("CPX_HDR_SZ")


def main():
    print("gem4xe-m58: the CPX toolkit's events")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    emu = launch(tag="m58", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        far = b.peek24(syms["sh_cpx_far"])

        def record(slot):
            at = far + CPX_MAX + slot * CPXE_SIZE + CPXE_HDR + BUF
            return list(b.memdump(at, 18))

        def frame(wh):
            o = obj(b, b.peek24(syms["gl_wtree"]), wh)
            return o["x"], o["y"], o["w"], o["h"]

        def opened():
            t.choose(DESKMENU, t.desk_acc("Control Panel"))
            b.frames(80)
            t.settle()
            return t.panel()

        n = b.peek16(syms["sh_ncpx"])
        check(n == 4, f"{n} module(s) listed: the disk's four")
        check(record(FORM_SLOT)[K_MODE] == ord("F"),
              "FORM.CPX's header says 'F' in its buffer")

        # ---- 1. opened: the XCPB at cpx_init, the list, the cookie ------
        p = opened()
        wx, wy = p["work"][:2]
        t.dclick(middle(p["slots"][TEST_SLOT]))
        b.frames(60)
        r = record(TEST_SLOT)
        print(f"  TEST.CPX opened: {r}")
        check(r[K_CALL] == 1, f"its cpx_call ran once ({r[K_CALL]})")
        check(r[K_INITX] >= 1, f"its cpx_init came with the panel's XCPB "
                               f"({r[K_INITX]})")
        check(r[K_RECTS] >= 1, f"it drew its box through GetFirstRect / "
                               f"GetNextRect: {r[K_RECTS]} piece(s)")
        check(r[K_COOKIE] == 0, "getcookie says there is no 'NVDI': this "
                                "machine has no jar")
        check(r[K_MFSAVE] == 1, "MFsave was there to call")

        # ---- 2. Set_Evnt_Mask: the rectangle and the timer ---------------
        t.go((wx + BOX[0] + 40, wy + BOX[1] + BOX[3] // 2))
        b.frames(30)
        t.go((wx + BOX[0] + 40, wy + BOX[1] - 30))
        b.frames(60)
        r = record(TEST_SLOT)
        check(r[K_M1] >= 1, f"the pointer onto its box was a cpx_m1 "
                            f"({r[K_M1]})")
        check(r[K_TIMER] >= 5, f"its 50 ms timer ticked ({r[K_TIMER]} in "
                               f"about 1.5 s; XControl's own is 30 s)")

        # ---- 3. the hook first ------------------------------------------
        t.run([K("H", ord("h")), F(40)])
        r = record(TEST_SLOT)
        check(r[K_TAKEN] == 1 and r[K_KEY] == 0,
              f"cpx_hook took the key 'h' and cpx_key never saw it "
              f"({r[K_TAKEN]} taken, {r[K_KEY]} key(s))")
        check(r[K_HOOK] >= 3, f"cpx_hook saw every event ({r[K_HOOK]})")

        # ---- 4. the closer: cpx_close, keep 1 ----------------------------
        fx, fy, _, _ = frame(p["wh"])
        t.click((fx + 4, fy + 4))
        b.frames(60)
        t.settle()
        r = record(TEST_SLOT)
        check(r[K_CLOSE] == 1 and r[K_KEEP] == 1,
              f"the window's closer: cpx_close with keep 1 ({r[K_CLOSE]} "
              f"close(s), keep {r[K_KEEP]})")
        check(t.panel()["wh"] == -1, "...and the panel shut")

        # ---- 5. a form: CT_KEY, then its button ---------------------------
        p = opened()
        wx, wy = p["work"][:2]
        t.dclick(middle(p["slots"][FORM_SLOT]))
        b.frames(60)
        t.run([K("HELP", 0x6200), F(40)])
        r = record(FORM_SLOT)
        check(r[K_CTKEY] == 1, f"Help, a key with no character: Xform_do "
                               f"answered CT_KEY ({r[K_CTKEY]})")
        check(r[K_FORMX] == 0, "...and the form went on")

        # the Popup: past five items, so an up arrow, three items, a down
        # arrow, at the button's corner less a pixel
        t.click((wx + POP[0] + POP[2] // 2, wy + POP[1] + POP[3] // 2))
        b.frames(20)
        bx, by = wx + POP[0] - 1, wy + POP[1] - 1
        slot = lambda i: (bx + 40, by + (i - 1) * PU_ROW + 2 + 4)
        t.go(slot(5))                           # the down arrow
        t.run([B(1), F(120), B(0), F(10)])      # held: to the end
        t.go(slot(4))                           # the last item shown
        b.frames(10)
        t.run([B(1), F(6), B(0), F(30)])
        t.settle()
        r = record(FORM_SLOT)
        check(r[K_POPUP] == 7, f"the Popup scrolled to its end and its last "
                               f"item was picked: item {r[K_POPUP]} (7 wanted)")

        # the list slider: its thumb at the top (row 0), dragged below the
        # track's foot, is the last first row; the up arrow once is 6
        tx = wx + SLX + SLW // 2
        top = wy + SLY + SLAH + 4
        t.go((tx, top))
        t.run([B(1), F(24)] + [M(tx, top + 14 * k) for k in range(1, 7)]
              + [F(10), B(0), F(20)])
        t.settle()
        r = record(FORM_SLOT)
        check(r[K_SLVAL] == 7 and r[K_FOO] >= 1,
              f"the thumb dragged to the foot: row {r[K_SLVAL]} (7 wanted), "
              f"foo called {r[K_FOO]} time(s)")
        t.click((tx, wy + SLY + SLAH // 2))     # the up arrow
        b.frames(20)
        t.settle()
        r = record(FORM_SLOT)
        check(r[K_SLVAL] == 6, f"the up arrow, once: row {r[K_SLVAL]} "
                               f"(6 wanted)")
        t.click((wx + DONE[0] + DONE[2] // 2, wy + DONE[1] + DONE[3] // 2))
        b.frames(60)
        t.settle()
        r = record(FORM_SLOT)
        check(r[K_FORMX] == 1, f"its Done button ended it ({r[K_FORMX]})")
        check(t.panel()["wh"] > 0, "...with the panel still open")

        # ---- 6. a form ended by the window's closer -----------------------
        p = t.panel()
        t.dclick(middle(p["slots"][FORM_SLOT]))
        b.frames(60)
        fx, fy, _, _ = frame(p["wh"])
        t.click((fx + 4, fy + 4))
        b.frames(60)
        t.settle()
        r = record(FORM_SLOT)
        check(r[K_FORMX] == 2, f"the closer ended the form: Xform_do's -1 "
                               f"with WM_CLOSED ({r[K_FORMX]})")
        check(b.peek16(syms["gem_bad"]) == 0,
              f"{b.peek16(syms['gem_bad'])} call(s) refused")
    finally:
        emu.stop()
    print(f"gem4xe-m58: {'PASS' if not problems else 'FAIL'} -- the CPX "
          f"toolkit's events, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
