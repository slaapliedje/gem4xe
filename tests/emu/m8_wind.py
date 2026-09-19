#!/usr/bin/env python3
"""Phase 8 gate: the window manager against tools/aesref.py's model of it.

Three things are compared per case, as in m7: every returned word --
handles, wind_get's rectangles, the WM_REDRAW messages the application
would be handed, in the order the queue's coalescing leaves them -- the
screen after the last call, and the trees' memory.  The screen is where
the two standing warnings are checked: an uncover redraws only the
uncovered rectangles (the desktop's and each window's rectangle list),
and a move of the top window is one blit from an even x to an even x,
after w_snap has rounded an odd one down.

The first six cases drive nothing but time: an evnt_multi(MU_MESAG |
MU_TIMER) that finds the queue empty and must time out.  The rest drive
the pointer at the control manager: a press on a window's frame is the
window manager's until the button comes up -- it works the gadget and
sends the application one message, and the application's own button
waits see nothing of it -- while a press on the desktop or the top
window's work area is the application's.  Where a gadget is comes from
the reference's layout of the active window (Scratch), not from here.

A wait that is satisfied at entry -- evnt_mesag with a message queued --
takes no plan; a plan for it would be an error, because the reference
would then have steps left over.  A planned wait must complete on its
plan's last step, so a release that ends the manager's hold goes into
the plan of the next wait it completes.
"""
import copy
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import vbxeref, vdiref, aesref, symfile     # noqa: E402
from aesref import (Layout, MU_MESAG, MU_TIMER, MU_BUTTON, RETURN,  # noqa: E402
                    NAME, CLOSER, FULLER, MOVER, INFO, SIZER, UPARROW, DNARROW,
                    VSLIDE, LFARROW, RTARROW, HSLIDE, WC_BORDER, WC_WORK,
                    BEG_UPDATE, END_UPDATE,
                    W_CLOSER, W_NAME, W_FULLER, W_WORK, W_SIZER, W_UPARROW,
                    W_DNARROW, W_VSLIDE, W_VELEV, W_RTARROW, W_HSLIDE, W_HELEV,
                    WF_KIND, WF_NAME, WF_INFO, WF_WXYWH, WF_CXYWH, WF_PXYWH,
                    WF_FXYWH, WF_HSLIDE, WF_VSLIDE, WF_TOP, WF_FIRSTXYWH,
                    WF_NEXTXYWH, WF_NEWDESK, WF_HSLSIZ, WF_VSLSIZ, WF_OWNER,
                    WF_BOTTOM,
                    WM_REDRAW, WM_ARROWED, NUM_MSGS,
                    APPL_WRITE, EVNT_MESAG, EVNT_BUTTON, WIND_CREATE, WIND_OPEN,
                    WIND_CLOSE, WIND_DELETE, WIND_GET, WIND_SET, WIND_FIND,
                    WIND_UPDATE, WIND_CALC, FORM_DO, GRAF_RUBBOX, GRAF_DRAGBOX,
                    GRAF_MKSTATE)
from m4_aes import dialog, draw, mem_diff, PRELUDE                  # noqa: E402
from m7_form import (desk, F, M, B, K, multi, poke16, drive, compare,  # noqa: E402
                     NOT_STARTED, STATUS, ST_GO, ST_DONE, DISK, SYMS, SHOTDIR)

ALL = (NAME | CLOSER | FULLER | MOVER | INFO | SIZER | UPARROW | DNARROW
       | VSLIDE | LFARROW | RTARROW | HSLIDE)
AC_OPEN = 40
# What the cases hand wind_create as a window's full size: the desk's
# work area, as the desktop would.
FULL = (0, 11, 640, 229)


# -- records ----------------------------------------------------------------

def create(kind, x=FULL[0], y=FULL[1], w=FULL[2], h=FULL[3]):
    return (WIND_CREATE, (), (kind, x, y, w, h))


def wopen(wh, x, y, w, h):
    return (WIND_OPEN, (), (wh, x, y, w, h))


def get(wh, field):
    return (WIND_GET, (), (wh, field))


def wset(wh, field, *words):
    return (WIND_SET, (), (wh, field) + tuple(words) + (0,) * (4 - len(words)))


def setaddr(wh, field, addr):
    """WF_NAME, WF_INFO, WF_NEWDESK: a 32-bit address high word first."""
    return wset(wh, field, 0, addr, 0)


def rects(wh, n):
    """Walk wh's rectangle list: FIRSTXYWH, then n-1 NEXTXYWH; the last
    is expected to be the empty rectangle that ends the walk."""
    return [get(wh, WF_FIRSTXYWH)] + [get(wh, WF_NEXTXYWH)] * (n - 1)


def mesag(n):
    return [(EVNT_MESAG, (), ())] * n


def write(msg):
    """appl_write to this one process; the message is 8 words."""
    return (APPL_WRITE, (), (0, 16) + tuple(msg) + (0,) * (8 - len(msg)))


def timeout():
    """A MESAG wait on an empty queue that the timer ends: 100 ms is 5
    ticks, so the plan's 9 frames end it with room to spare."""
    return multi(MU_MESAG | MU_TIMER, ms=100)


def queued():
    """A MESAG wait with a message already queued: satisfied at entry, so
    no plan -- and a timer long enough that the harness would notice if
    it were not."""
    return multi(MU_MESAG | MU_TIMER, ms=2000)


# -- cases ------------------------------------------------------------------
# (name, body) where body(L) returns the records and may lay strings out
# in L, the desk tree's Layout, whose base is the WF_NEWDESK address.
# Plans are keyed by body index; the one wait that needs one is timeout().

def case_open(L, s):
    return [
        setaddr(0, WF_NEWDESK, L.base),
        (WIND_CALC, (), (WC_WORK, ALL, 100, 50, 300, 150)),
        (WIND_CALC, (), (WC_BORDER, ALL, 101, 71, 287, 118)),
        (WIND_CALC, (), (WC_WORK, NAME | MOVER, 10, 20, 100, 60)),
        (WIND_CALC, (), (WC_WORK, 0, 10, 20, 100, 60)),
        create(ALL),
        setaddr(1, WF_NAME, L.text("A Window")),
        setaddr(1, WF_INFO, L.text("with everything on it")),
        get(1, WF_CXYWH), get(1, WF_FXYWH), get(1, WF_OWNER), get(0, WF_TOP),
        wopen(1, 101, 50, 301, 150),
        get(1, WF_CXYWH), get(1, WF_WXYWH), get(1, WF_PXYWH),
        get(1, WF_OWNER), get(0, WF_TOP), get(9, WF_CXYWH),
    ] + rects(1, 2) + rects(0, 6) + [queued(), timeout()]


def case_two(L, s):
    return [
        create(ALL), wopen(1, 100, 50, 300, 150),
        setaddr(1, WF_NAME, L.text("Under")),
        create(NAME | MOVER), wopen(2, 200, 100, 300, 120),
        setaddr(2, WF_NAME, L.text("Over")),
        # The order, both ways round and from both ends: window 1 is at
        # the bottom with 2 above it, so WF_OWNER's neighbours are each
        # other and the desk, and WF_BOTTOM is 1 (tests/host/
        # test_wind_order.py writes those numbers out of the Compendium).
        get(0, WF_TOP), get(1, WF_OWNER), get(2, WF_OWNER), get(0, WF_BOTTOM),
    ] + rects(1, 3) + rects(2, 2) + rects(0, 7) + mesag(2) + [
        wset(1, WF_TOP),
        get(0, WF_TOP), get(1, WF_OWNER), get(2, WF_OWNER), get(0, WF_BOTTOM),
    ] + rects(1, 2) + rects(2, 3) + [
        wset(1, WF_TOP),                        # already on top: nothing
        wset(2, WF_TOP),
    ] + rects(1, 3) + mesag(2) + [timeout()]


def case_move(L, s):
    # The dialog drawn inside the window is what the blit has to carry.
    return [
        create(ALL), wopen(1, 100, 30, 440, 170),
        draw(),
    ] + mesag(1) + [
        wset(1, WF_CXYWH, 121, 40, 440, 170),   # odd x: snapped, one blit
        get(1, WF_CXYWH), get(1, WF_PXYWH),
        wset(1, WF_CXYWH, 120, 40, 440, 170),   # the same place: nothing
        wset(1, WF_CXYWH, 300, 60, 440, 170),   # off the right edge: clipped
        get(1, WF_CXYWH),
        wset(1, WF_CXYWH, 200, 50, 440, 170),   # back: redrawn, not blitted
        get(1, WF_CXYWH),
    ] + rects(0, 6) + mesag(1) + [timeout()]


def case_size(L, s):
    return [
        create(ALL), wopen(1, 100, 50, 300, 150),
        create(NAME | MOVER | SIZER), wopen(2, 300, 120, 200, 80),
    ] + mesag(2) + [
        wset(2, WF_CXYWH, 300, 120, 260, 100),  # grows in place
        get(2, WF_CXYWH), get(2, WF_WXYWH),
    ] + rects(1, 4) + [
        wset(2, WF_CXYWH, 300, 120, 150, 60),   # shrinks: an uncover
        get(2, WF_CXYWH),
    ] + rects(1, 3) + [
        (WIND_FIND, (), (310, 130)), (WIND_FIND, (), (150, 100)),
        (WIND_FIND, (), (5, 5)), (WIND_FIND, (), (700, 5)),
        (WIND_UPDATE, (), (BEG_UPDATE,)), (WIND_UPDATE, (), (END_UPDATE,)),
        (WIND_CLOSE, (), (2,)), get(2, WF_OWNER), get(0, WF_TOP),
        (WIND_CLOSE, (), (2,)),                 # already closed
    ] + rects(1, 2) + [
        (WIND_DELETE, (), (2,)), get(2, WF_CXYWH),
        create(NAME), get(2, WF_KIND), (WIND_DELETE, (), (2,)),
        (WIND_DELETE, (), (2,)),                # already deleted
        (WIND_FIND, (), (310, 130)),
    ] + mesag(2) + [timeout()]


def case_sliders(L, s):
    return [
        create(ALL), wopen(1, 100, 50, 400, 160),
        setaddr(1, WF_NAME, L.text("Sliders")),
        setaddr(1, WF_INFO, L.text("size and position")),
        wset(1, WF_VSLSIZ, 250), wset(1, WF_VSLIDE, 500),
        wset(1, WF_HSLSIZ, 1200), wset(1, WF_HSLIDE, -5),
        get(1, WF_VSLSIZ), get(1, WF_VSLIDE), get(1, WF_HSLSIZ), get(1, WF_HSLIDE),
        wset(1, WF_VSLIDE, 500),                # unchanged: no redraw
        wset(1, WF_HSLSIZ, -1), get(1, WF_HSLSIZ),
        wset(1, WF_HSLIDE, 1000), get(1, WF_HSLIDE),
        wset(1, WF_VSLSIZ, 0), get(1, WF_VSLSIZ),
        wset(1, WF_VSLIDE, 1000), wset(1, WF_VSLSIZ, 30),
        setaddr(1, WF_NAME, L.text("Renamed")),
        setaddr(1, WF_INFO, L.text("")),
    ] + mesag(1) + [timeout()]


def case_queue(L, s):
    fill = [write((AC_OPEN, 0, 0, i, 0, 0, 0, 0)) for i in range(NUM_MSGS - 2)]
    return [
        write((WM_REDRAW, 0, 0, 1, 10, 10, 20, 20)),
        write((WM_REDRAW, 0, 0, 1, 15, 15, 30, 30)),    # joins the first
        write((WM_REDRAW, 0, 0, 2, 5, 5, 5, 5)),
        write((WM_ARROWED, 0, 0, 1, 3, 0, 0, 0)),
        write((WM_ARROWED, 0, 0, 2, 4, 0, 0, 0)),       # replaces
    ] + fill + [queued()] + mesag(NUM_MSGS - 1) + [timeout()]  # one dropped


# -- the control manager ----------------------------------------------------

class Script(list):
    """A case's records with the plan for each: op(record, *steps)."""

    def __init__(self):
        super().__init__()
        self.plan = {}

    def op(self, rec, *steps):
        self.append(rec)
        if steps:
            self.plan[len(self) - 1] = list(steps)


class Scratch:
    """The reference run over a case's records so far, on copies of the
    trees, so that a case can ask where a gadget is or what the last
    message said instead of restating the frame's geometry here.  The
    target is then checked against the same model in main()."""

    def __init__(self, objs, L, L2, objs2):
        self.objs, self.L, self.L2, self.objs2 = objs, L, L2, objs2

    def run(self, script):
        mem = dict(self.L.mem)
        mem.update(self.L2.mem)
        objs, mem, objs2 = copy.deepcopy((self.objs, mem, self.objs2))
        plan = {k + len(PRELUDE): v for k, v in plan_for(script).items()}
        return aesref.run(PRELUDE + list(script), objs, mem, plan=plan,
                          trees={self.L2.base: objs2})

    def aes(self, script):
        return self.run(script)[1]

    def rect(self, script, wh, obj):
        """Window wh's gadget obj on the screen, as w_bldactive lays the
        active window out -- for a window that is not on top, without
        the closer and fuller."""
        a = self.aes(script)
        a.tree = a.W_ACTIVE
        a.w_bldactive(wh)
        return a.ob_actxywh(obj)

    def gadget(self, script, wh, obj):
        """Where a press on window wh's gadget obj lands: its centre."""
        r = self.rect(script, wh, obj)
        return (r.x + r.w // 2, r.y + r.h // 2)

    def message(self, script):
        """The message the last record -- an evnt_mesag, or an evnt_multi
        that delivered one -- returned."""
        rec = self.run(script)[2][-1]
        return rec[2:10] if script[-1][0] == EVNT_MESAG else rec[9:17]


MESAG = (EVNT_MESAG, (), ())
RELEASE = (F(2), B(0))          # the release, two frames after the last step


def case_topped(L, s):
    """A press on a window under: WM_TOPPED, and the manager keeps the
    mouse through the application's WF_TOP until the release; then the
    presses that are the application's -- the top window's work area,
    the desktop -- and the one nobody's: the empty menu strip."""
    b = Script()
    b.extend([create(ALL), wopen(1, 100, 50, 300, 150),
              create(NAME | MOVER), wopen(2, 200, 100, 300, 120)])
    b.extend(mesag(2))
    r = s.rect(b, 1, W_WORK)
    under = (r.x + 8, r.y + 8)              # window 1 where 2 does not cover it
    menu = s.aes(b).gl_rmenu
    strip = (menu.w // 2, menu.h // 2)
    b.op(multi(MU_BUTTON | MU_MESAG | MU_TIMER, 1, 1, 1, ms=2000),
         F(3), M(*under), B(1))             # WM_TOPPED 1 by MU_MESAG, not the press
    b.op(wset(1, WF_TOP))                   # button still down: no hand-back
    b.op(MESAG)                             # WM_REDRAW 1
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)   # completed by the hand-back
    b.op((GRAF_MKSTATE,))
    b.op(multi(MU_BUTTON, 1, 1, 1), F(3), M(*s.gadget(b, 1, W_WORK)), B(1))
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(multi(MU_BUTTON, 1, 1, 1), F(3), M(600, 200), B(1))    # the desktop
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(multi(MU_BUTTON | MU_TIMER, 1, 1, 1, ms=200),
         F(3), M(*strip), B(1), F(12))      # swallowed: the timer ends it
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(timeout())
    return b


def case_gadgets(L, s):
    """The closer and the fuller: selected while the button is down on
    them, the message on a release inside; a release outside sends
    nothing.  The application answers WM_FULLED with the full size."""
    b = Script()
    b.extend([create(ALL), wopen(1, 100, 50, 300, 150),
              setaddr(1, WF_NAME, L.text("Gadgets"))])
    b.extend(mesag(1))
    closer, fuller = s.gadget(b, 1, W_CLOSER), s.gadget(b, 1, W_FULLER)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*closer), B(1), *RELEASE)  # WM_CLOSED at the release
    b.op(multi(MU_MESAG | MU_TIMER, ms=300),
         F(3), M(*closer), B(1), F(2), M(600, 200), *RELEASE, F(14))
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*fuller), B(1), *RELEASE)  # WM_FULLED
    b.op(get(1, WF_FXYWH))
    b.op(wset(1, WF_CXYWH, *FULL))
    b.op(MESAG)                             # WM_REDRAW: the new area
    b.extend(rects(0, 2))
    b.op(timeout())
    return b


def case_drag(L, s):
    """The mover: WM_MOVED carries the drag's own x, odd or not, and the
    application's wind_set snaps it.  The sizer: WM_SIZED from the two
    rubber boxes, and the minimums when the drag goes inside them."""
    b = Script()
    x, y, w, h = 100, 50, 300, 150
    b.extend([create(ALL), wopen(1, x, y, w, h)])
    b.extend(mesag(1))
    name = s.gadget(b, 1, W_NAME)
    dx, dy = 21, 30
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*name), B(1), F(2), M(name[0] + dx, name[1] + dy), *RELEASE)
    x, y = x + dx, y + dy                   # WM_MOVED 1 x y w h
    b.op(wset(1, WF_CXYWH, x, y, w, h))     # odd x: snapped, one blit
    b.op(get(1, WF_CXYWH))
    b.op(timeout())                         # a blit: no redraw message
    sizer = s.gadget(b, 1, W_SIZER)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*sizer), B(1), F(2), M(sizer[0] - 40, sizer[1] - 30), *RELEASE)
    b.op(wset(1, WF_CXYWH, *s.message(b)[4:8]))     # WM_SIZED 1 x y w' h'
    b.op(get(1, WF_WXYWH))
    sizer = s.gadget(b, 1, W_SIZER)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*sizer), B(1), F(2), M(sizer[0] - 200, sizer[1] - 100), *RELEASE)
    b.op(wset(1, WF_CXYWH, *s.message(b)[4:8]))     # WM_SIZED at the minimums
    b.op(get(1, WF_CXYWH))
    b.op(timeout())
    return b


def sliders(b):
    """A window with both sliders, part way along."""
    b.extend([create(ALL), wopen(1, 100, 50, 400, 160),
              wset(1, WF_VSLSIZ, 250), wset(1, WF_VSLIDE, 500),
              wset(1, WF_HSLSIZ, 500), wset(1, WF_HSLIDE, 0)])
    b.extend(mesag(1))


def case_arrows(L, s):
    """The arrows: WM_ARROWED at the press; a held arrow sends another
    after the double-click time and then one every time the application
    asks."""
    b = Script()
    sliders(b)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*s.gadget(b, 1, W_UPARROW)), B(1))     # WA_UPLINE at the press
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)   # before the repeat
    b.op(timeout())
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*s.gadget(b, 1, W_DNARROW)), B(1))     # WA_DNLINE
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000), F(14))    # the repeat, 11 ticks on
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000))   # refilled at the entry poll
    b.op((EVNT_BUTTON, (), (1, 1, 0)), *RELEASE)    # completed by the hand-back
    b.op(MESAG)                             # the last one, queued before it
    b.op(timeout())
    return b


def case_elevators(L, s):
    """The slide areas page; the elevators, dragged, send WM_VSLID and
    WM_HSLID with the new position, which the application applies."""
    b = Script()
    sliders(b)
    v = s.rect(b, 1, W_VSLIDE)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(v.x + v.w // 2, v.y + 2), B(1))        # WA_UPPAGE
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(v.x + v.w // 2, v.y + v.h - 3), B(1))  # WA_DNPAGE
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    hs = s.rect(b, 1, W_HSLIDE)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(hs.x + hs.w - 3, hs.y + hs.h // 2), B(1))  # WA_RTPAGE
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*s.gadget(b, 1, W_RTARROW)), B(1))     # WA_RTLINE
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    ve = s.gadget(b, 1, W_VELEV)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*ve), B(1), F(2), M(ve[0], ve[1] + 20), *RELEASE)
    b.op(wset(1, WF_VSLIDE, s.message(b)[4]))   # WM_VSLID's position
    he = s.gadget(b, 1, W_HELEV)
    b.op(multi(MU_MESAG | MU_TIMER, ms=2000),
         F(3), M(*he), B(1), F(2), M(he[0] + 60, he[1]), *RELEASE)
    b.op(wset(1, WF_HSLIDE, s.message(b)[4]))   # WM_HSLID's
    b.op(get(1, WF_VSLIDE))
    b.op(get(1, WF_HSLIDE))
    b.op(timeout())
    return b


def case_form(L, s):
    """form_do owns the whole screen: a click on the closer behind the
    dialog is the form's and sends nothing.  Then graf_rubbox and
    graf_dragbox as the application calls them, with the button down."""
    b = Script()
    b.extend([create(ALL), wopen(1, 100, 50, 300, 150), draw()])
    b.extend(mesag(1))
    closer = s.gadget(b, 1, W_CLOSER)
    b.op((FORM_DO, (), (0,)),
         F(3), M(*closer), B(1), F(14), B(0), F(2), K("RETURN", RETURN))
    b.op(timeout())                         # no WM_CLOSED
    work = s.gadget(b, 1, W_WORK)
    b.op(multi(MU_BUTTON, 1, 1, 1), F(3), M(*work), B(1))
    b.op((GRAF_RUBBOX, (), (work[0], work[1], 20, 10)),
         F(3), M(work[0] + 100, work[1] + 65), *RELEASE)
    b.op(multi(MU_BUTTON, 1, 1, 1), F(3), M(*work), B(1))
    b.op((GRAF_DRAGBOX, (), (40, 30, work[0] - 10, work[1] - 5) + FULL),
         F(3), M(600, 230), *RELEASE)       # constrained to FULL
    b.op(timeout())
    return b


CASES = [
    ("wind_calc, create and open: the frame, the lists, WM_REDRAW", case_open),
    ("two windows: rectangle lists, WF_TOP, the redraw messages", case_two),
    ("moves: an odd x snaps and blits, off the edge clips, back redraws", case_move),
    ("sizes, wind_find, close and delete: uncovers", case_size),
    ("WF_NAME, WF_INFO and the sliders", case_sliders),
    ("appl_write and evnt_mesag: union, replace, a full queue", case_queue),
    ("a press under tops; the work area, the desktop and the strip", case_topped),
    ("the closer and the fuller: selected, released inside or out", case_gadgets),
    ("the mover and the sizer: WM_MOVED unsnapped, WM_SIZED, minimums", case_drag),
    ("the arrows: at the press, then repeating while held", case_arrows),
    ("the slide areas and the elevators", case_elevators),
    ("form_do owns the screen; graf_rubbox and graf_dragbox", case_form),
]


def plan_for(body):
    """A timeout() needs 9 frames of input; a Script carries the rest."""
    plan = {i: [F(9)] for i, rec in enumerate(body) if rec == timeout()}
    plan.update(getattr(body, "plan", {}))
    return plan


def main(argv):
    keep = "--shot" in argv
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = {int(x) for x in a[7:].split(",")}
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    sa, sc = syms["vdi_script"], syms["vdi_scratch"]
    results_addr, count_addr = syms["vdi_results"], syms["vdi_result_count"]
    ptr = syms["ptr_state"]
    scratch_room = min(a for a in syms.values() if a > sc) - sc
    script_room = min(a for a in syms.values() if a > sa) - sa

    emu = launch(tag="m8", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    out = []
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        # "VD" says the runner is alive; STATUS[2] == 1 says it is
        # ready for scripts, which is what staging one needs.
        for _ in range(200):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1

        for idx, (name, build) in enumerate(CASES):
            if only is not None and idx not in only:
                continue
            L = Layout(sc, max_objs=12)
            objs = dialog(L)
            L2 = Layout(L.next, max_objs=1)
            objs2 = desk(L2)
            # build lays its strings out in L2 and may ask the scratch
            # reference where things are
            body = build(L2, Scratch(objs, L, L2, objs2))
            layouts = [(L, objs, L.pack(objs)), (L2, objs2, L2.pack(objs2))]
            assert L2.next - sc <= scratch_room, (name, scratch_room)
            for lay, _, img in layouts:
                b.memload(lay.base, img)
            mem = dict(L.mem)
            mem.update(L2.mem)
            script = PRELUDE + body
            plan = {k + len(PRELUDE): v for k, v in plan_for(body).items()}
            pointer = (b.peek16(ptr), b.peek16(ptr + 2))

            ref_v, ref_a, want = aesref.run(script, objs, mem, plan=dict(plan),
                                            pointer=pointer,
                                            trees={L2.base: objs2})

            words = aesref.encode(script, sc)
            # The runner stops at the end of its buffer, mid-script, and
            # the words past it land on whatever follows -- a case that
            # simply blocks at its last op is what that looks like.
            assert len(words) * 2 <= script_room, (name, len(words), script_room)
            b.memload(sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                                   for w in words))
            b.poke(STATUS + ST_DONE, 0)
            poke16(b, count_addr, NOT_STARTED)
            b.poke(STATUS + ST_GO, 1)
            err = drive(b, count_addr, ptr, plan)
            if err:
                n = b.peek16(count_addr)
                err += "; " + (compare(b, results_addr, n, script, want)
                               or f"the {n} records so far match")
                out.append((idx, name, err))
                print(f"  [{idx}] {name:<66s} FAIL")
                print(f"   target blocked: {err}; cannot continue")
                break
            ok = False
            for _ in range(300):
                if b.peek(STATUS + ST_DONE) == 0xA5:
                    ok = True
                    break
                b.frames(4)
            if not ok:
                out.append((idx, name, "timed out"))
                break
            b.frames(4)

            n = b.peek16(count_addr)
            if n != len(want):
                err = f"{n} calls recorded, expected {len(want)}"
            else:
                err = compare(b, results_addr, n, script, want)
            if not err:
                for lay, lobjs, img in layouts:
                    err = mem_diff(lay, lobjs, bytes(b.memdump(lay.base, len(img))))
                    if err:
                        break

            shot = os.path.join(SHOTDIR, f"m8-{idx:02d}.png")
            b.screenshot(shot)
            bad, shown = vbxeref.compare_to_shot(ref_v.to_rgb(), shot)
            if bad and not err:
                err = f"{bad} px differ; first {shown[:3]}"
            out.append((idx, name, err))
            if not err and not keep:
                os.remove(shot)
            print(f"  [{idx}] {name:<66s} {'ok' if not err else 'FAIL'}")
    finally:
        emu.stop()

    fails = [r for r in out if r[2]]
    print()
    for idx, name, e in fails:
        print(f"   FAIL [{idx}] {name}: {e}")
    want = len(CASES) if only is None else len(only)
    print(f"gem4xe-m8: {len(out) - len(fails)}/{want} window cases passed")
    return 1 if fails or len(out) < want else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
