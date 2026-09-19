#!/usr/bin/env python3
"""Phase 8 gate, step 3: the menu library against tools/aesref.py.

A desktop-shaped menu tree -- the bar, four titles, four drop-downs in the
order and geometry Atari's RCS lays them out (EmuTOS's desk_rsc.c, in 8x8
character units) -- is laid out in vdi_scratch, and the cases run menu_bar,
menu_icheck, menu_ienable, menu_tnormal, menu_text and menu_register
through the runner, then hover and click through the bar from the host's
input plan while the application waits in evnt_multi: the drop-down pulled
by a hover, the walk from title to title, a press outside that ends the
menu with nothing, a press on an item that ends it with MN_SELECTED at the
press (the release is the application's, handed back), a disabled item, a
disabled title.

What a drop-down looks like while it is down can only be seen inside the
wait, so the plans carry ("shot", fn) steps: no frame runs, the harness
screenshots the target where the reference keeps a copy of its own
screen, and the pairs are compared after the case like the final screen.
The final screen shows the drop-down restored -- the save buffer's work.
"""
import copy
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a8test.launcher import launch          # noqa: E402
import vbxeref, aesref, symfile             # noqa: E402
from aesref import (Layout, Obj, NIL, G_IBOX, G_BOX, G_TITLE, G_STRING,  # noqa: E402
                    LASTOB, DISABLED, CHECKED, MU_MESAG, MU_TIMER, MU_BUTTON,
                    MENU_BAR, MENU_ICHECK, MENU_IENABLE, MENU_TNORMAL,
                    MENU_TEXT, MENU_REGISTER, MENU_POPUP, MN_SELECTED,
                    OBJC_DRAW, MAX_DEPTH)
from m4_aes import mem_diff, PRELUDE                                # noqa: E402
from m7_form import (desk, F, M, B, multi, poke16, drive, compare,  # noqa: E402
                     NOT_STARTED, STATUS, ST_GO, ST_DONE, DISK, SYMS, SHOTDIR)
from m8_wind import Script, RELEASE                                 # noqa: E402

# The tree, by index: the AES's fixed positions and this test's names.
BAR, ACTIVE = 1, 2
T_DESK, T_FILE, T_VIEW, T_OPTS = 3, 4, 5, 6
DESKBOX, ABOUT, DESKSEP = 8, 9, 10
FILEBOX, OPEN, INFO, FILESEP, QUIT = 17, 18, 19, 20, 21
VIEWBOX, ICONS, TEXT = 22, 23, 24
OPTBOX, SET, SAVE = 25, 26, 27
N_OBJS = 28


def menu(L):
    """The desktop's menu tree as RCS builds one, in pixels for the 8x8
    font: the bar is gl_hchar+2 high and the titles gl_hchar+3, the
    drop-downs hang from y = gl_hchar+3, each box under its title (with
    the RCS's 2-character indent for the first) and one pixel of outward
    border (thickness 0xFF).  The Desk box carries the eight children the
    AES relinks for accessories; a separator is a disabled string of
    dashes the width of its box.  Strings that menu_text will replace
    are laid out with room to grow."""
    return [
        #   next  head  tail  type      flags   state     spec            x    y    w    h
        Obj(NIL,     1,    7, G_IBOX,   0,      0,        0,              0,   0, 640, 240),  # 0 the screen
        Obj(7,       2,    2, G_BOX,    0,      0,        0x00001100,     0,   0, 640,  10),  # 1 the bar
        Obj(1,       3,    6, G_IBOX,   0,      0,        0,             16,   0, 232,  11),  # 2 the titles
        Obj(4,     NIL,  NIL, G_TITLE,  0,      0,        L.text(" Desk "),     0, 0, 48, 11),
        Obj(5,     NIL,  NIL, G_TITLE,  0,      0,        L.text(" File "),    48, 0, 48, 11),
        Obj(6,     NIL,  NIL, G_TITLE,  0,      0,        L.text(" View "),    96, 0, 56, 11),
        Obj(2,     NIL,  NIL, G_TITLE,  0,      DISABLED, L.text(" Options "), 152, 0, 72, 11),
        Obj(0,       8,   25, G_IBOX,   0,      0,        0,              0,  11, 640, 184),  # 7 the drop-downs
        Obj(17,      9,   16, G_BOX,    0,      0,        0x00FF1100,    16,   0, 160,  64),  # 8 Desk
        Obj(10,    NIL,  NIL, G_STRING, 0,      0,        L.text("  About gem4xe...", 24), 0, 0, 160, 8),
        Obj(11,    NIL,  NIL, G_STRING, 0,      DISABLED, L.text("-" * 20),   0,  8, 160, 8),
        Obj(12,    NIL,  NIL, G_STRING, 0,      0,        L.text("1"),        0, 16, 160, 8),
        Obj(13,    NIL,  NIL, G_STRING, 0,      0,        L.text("2"),        0, 24, 160, 8),
        Obj(14,    NIL,  NIL, G_STRING, 0,      0,        L.text("3"),        0, 32, 160, 8),
        Obj(15,    NIL,  NIL, G_STRING, 0,      0,        L.text("4"),        0, 40, 160, 8),
        Obj(16,    NIL,  NIL, G_STRING, 0,      0,        L.text("5"),        0, 48, 160, 8),
        Obj(8,     NIL,  NIL, G_STRING, 0,      0,        L.text("6"),        0, 56, 160, 8),
        Obj(22,     18,   21, G_BOX,    0,      0,        0x00FF1100,    64,   0, 152,  32),  # 17 File
        Obj(19,    NIL,  NIL, G_STRING, 0,      0,        L.text("  Open", 24), 0, 0, 152, 8),
        Obj(20,    NIL,  NIL, G_STRING, 0,      0,        L.text("  Info..."), 0, 8, 152, 8),
        Obj(21,    NIL,  NIL, G_STRING, 0,      DISABLED, L.text("-" * 19),   0, 16, 152, 8),
        Obj(17,    NIL,  NIL, G_STRING, 0,      0,        L.text("  Quit"),    0, 24, 152, 8),
        Obj(25,     23,   24, G_BOX,    0,      0,        0x00FF1100,    96,   0, 104,  16),  # 22 View
        Obj(24,    NIL,  NIL, G_STRING, 0,      CHECKED,  L.text("  Icons"),   0,  0, 104, 8),
        Obj(22,    NIL,  NIL, G_STRING, 0,      0,        L.text("  Text"),    0,  8, 104, 8),
        Obj(7,      26,   27, G_BOX,    0,      0,        0x00FF1100,   152,   0,  96,  16),  # 25 Options
        Obj(27,    NIL,  NIL, G_STRING, 0,      0,        L.text("  Set..."),  0,  0,  96, 8),
        Obj(25,    NIL,  NIL, G_STRING, LASTOB, 0,        L.text("  Save"),    0,  8,  96, 8),
    ]


# -- records ----------------------------------------------------------------

def backdrop(L2):
    return (OBJC_DRAW, (0, 0, 640, 240), (0, MAX_DEPTH), L2.base)


def bar(showit):
    return (MENU_BAR, (), (showit,))


def icheck(item, check):
    return (MENU_ICHECK, (), (item, check))


def ienable(item, enable, redraw=False):
    return (MENU_IENABLE, (), (item | (0x8000 if redraw else 0), enable))


def tnormal(title, normal):
    return (MENU_TNORMAL, (), (title, normal))


def text(item, addr):
    return (MENU_TEXT, (), (item, addr))


def register(addr):
    return (MENU_REGISTER, (), (0, addr))


def popup(box, start, x, y, scroll=0):
    """menu_popup, the MENU block spelled out: the box, the item to put
    under the pointer, the scroll word it must hand straight back, and
    where the item goes."""
    return (MENU_POPUP, (), (box, start, scroll, x, y))


def wait(ms):
    """An application waiting for a message with a timer as the way out:
    the menu runs inside it, and the timer ends the case after the menu.
    A plan ends with more frames than the timer needs: the frames after
    the tick are dropped on both sides, and the target counts one tick
    more than the reference when the wait begins in the frame that ended
    the wait before it, so the tick must land in that last step on
    either count."""
    return multi(MU_MESAG | MU_TIMER, ms=ms)


def SHOT():
    """A screenshot between frames; main() fills the function in."""
    return ("shot", None)


# -- cases ------------------------------------------------------------------
# (name, body): body(L, L2, s) returns a Script; strings it needs go in
# L2, the desk tree's Layout (L is the menu tree's, laid out and closed --
# L2 follows it), and s is the scratch reference for positions.

def case_calls(L, L2, s):
    """menu_bar shows the bar -- the Desk drop-down relinked to its one
    item, the bar stretched to the screen, the line under it -- and the
    calls that change the tree: a check moved, an item disabled, a title
    that will not select while disabled, enabled with a redraw and then
    selected, its text replaced, an accessory refused; then normal again,
    disabled again, and menu_bar(0), after which the pointer in the bar
    pulls nothing down."""
    b = Script()
    b.extend([backdrop(L2), bar(1),
              icheck(ICONS, 0), icheck(TEXT, 1),
              ienable(QUIT, 0),
              tnormal(T_OPTS, 0),
              ienable(T_OPTS, 1, redraw=True),
              tnormal(T_OPTS, 0),
              text(OPEN, L2.text("  Close")),
              register(L2.text("  Acc")),
              wait(100)])
    b.plan[len(b) - 1] = [F(9)]
    b.extend([tnormal(T_OPTS, 1),
              ienable(T_OPTS, 0, redraw=True),
              bar(0)])
    b.op(wait(200), F(3), M(*s.centre(b, T_FILE)), F(3), M(400, 150), F(12))
    return b


def case_hover(L, L2, s):
    """Into the bar: File drops, View replaces it (the check mark showing),
    the pointer leaves the bar with View still down, and a press out
    there ends the menu with nothing to say; the timer ends the wait."""
    b = Script()
    b.extend([backdrop(L2), bar(1)])
    b.op(wait(600),
         F(3), M(*s.centre(b, T_FILE)), F(3), SHOT(),
         M(*s.centre(b, T_VIEW)), F(3), SHOT(),
         M(300, 100), F(3), SHOT(),
         B(1), *RELEASE, F(20))
    b.op(bar(0))
    return b


def case_select(L, L2, s):
    """Items: Desk's one item (the fixup's), then a click on the File
    title (the menu stays down through it) and a press on Open.  Each
    press ends the menu at once with MN_SELECTED, the title left
    selected for menu_tnormal to clear and the button still down: the
    application's wait for the release is completed by the hand-back."""
    b = Script()
    b.extend([backdrop(L2), bar(1)])
    b.op(wait(2000),
         F(3), M(*s.centre(b, T_DESK)), F(3), SHOT(),
         M(*s.item(b, T_DESK, ABOUT)), F(3), SHOT(), B(1))
    b.append(tnormal(T_DESK, 1))
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(wait(2000),
         F(3), M(*s.centre(b, T_FILE)), F(3), B(1), F(2), B(0), F(2),
         M(*s.item(b, T_FILE, OPEN)), F(3), SHOT(), B(1))
    b.append(tnormal(T_FILE, 1))
    b.op(multi(MU_BUTTON, 1, 1, 0), *RELEASE)
    b.op(wait(200), F(3), M(400, 150), F(12))
    b.op(bar(0))
    return b


def case_disabled(L, L2, s):
    """A press on a separator ends the menu with nothing and the title
    cleared.  Then Options, disabled: View's drop-down is put back as the
    pointer reaches it, nothing drops, and going down from it -- to where
    no drop-down is -- ends the menu without a message."""
    b = Script()
    b.extend([backdrop(L2), bar(1), text(OPEN, L2.text("  Close"))])
    b.op(wait(600),
         F(3), M(*s.centre(b, T_FILE)), F(3), SHOT(),
         M(*s.item(b, T_FILE, FILESEP)), F(3), SHOT(),
         B(1), *RELEASE, F(20))
    opts = s.centre(b, T_OPTS)
    b.op(wait(600),
         F(3), M(*s.centre(b, T_VIEW)), F(3),
         M(*opts), F(3), SHOT(),
         M(opts[0], 100), F(3), SHOT(), F(20))
    b.op(bar(0))
    return b


def case_popup(L, L2, s):
    """menu_popup, with no menu bar anywhere: the View box put up at a
    place the application chose, walked, and clicked.

    The box is BORROWED OUT OF THE MENU TREE, which is the case the
    donors get wrong: their clamp writes ob_x/ob_y straight and compares
    them with the screen, and this box hangs off the drop-down IBOX
    eleven pixels down, so it would land eleven pixels high.  Here the
    parent's origin comes off first.

    Three of them.  One chosen, where the out block gets all five words;
    one where the press lands outside the box, where the answer is FALSE
    and ONLY the keystate is written -- the runner seeds the other four
    with numbers the call cannot produce, so a word it touched shows.
    And one placed hard against the right edge, which clamps.

    The screen after each is the backdrop again: what the box covered is
    the save buffer's to put back, and the shots inside the wait are
    where the box itself is checked."""
    b = Script()
    b.extend([backdrop(L2)])
    # chosen: the pointer starts on Icons, moves to Text, presses there
    b.op(popup(VIEWBOX, ICONS, 300, 100),
         F(3), M(300, 100), F(3), SHOT(),
         M(300, 108), F(3), SHOT(), B(1), F(2), B(0))
    b.extend([backdrop(L2)])
    # nothing chosen: the press is outside the box
    b.op(popup(VIEWBOX, ICONS, 300, 100),
         F(3), M(300, 100), F(3), M(500, 200), F(3), SHOT(),
         B(1), F(2), B(0))
    b.extend([backdrop(L2)])
    # against the right edge: the box is stepped back a character at a time
    b.op(popup(VIEWBOX, ICONS, 620, 100),
         F(3), M(620, 100), F(3), SHOT(), B(1), F(2), B(0))
    b.extend([backdrop(L2)])
    return b


CASES = [
    ("menu_bar, icheck, ienable, tnormal, text, register; hide", case_calls),
    ("hover: File down, View across, off the bar, a press outside", case_hover),
    ("select: Desk's fixup item, a click on File, Open -> MN_SELECTED", case_select),
    ("disabled: a separator pressed, a title that will not drop", case_disabled),
    ("menu_popup: chosen, nothing chosen, and clamped to the edge", case_popup),
]


def plan_for(body):
    return dict(getattr(body, "plan", {}))


class Scratch:
    """The reference run over a case's records so far, on copies of the
    trees, so that a case asks the model where a title or an item is
    instead of restating the tree's geometry."""

    def __init__(self, objs, L, L2, objs2):
        self.objs, self.L, self.L2, self.objs2 = objs, L, L2, objs2

    def aes(self, script):
        mem = dict(self.L.mem)
        mem.update(self.L2.mem)
        objs, mem, objs2 = copy.deepcopy((self.objs, mem, self.objs2))
        plan = {k + len(PRELUDE): v for k, v in plan_for(script).items()}
        a = aesref.run(PRELUDE + list(script), objs, mem, plan=plan,
                       trees={self.L2.base: objs2})[1]
        a.tree = objs
        return a

    def centre(self, script, obj):
        r = self.aes(script).ob_actxywh(obj)
        return (r.x + r.w // 2, r.y + r.h // 2)

    def item(self, script, title, obj):
        """The centre of item obj of the drop-down under title, as the
        AES finds the drop-down: by the title's place in the bar."""
        a = self.aes(script)
        assert obj in self.children(a, a.menu_sub(title)), (title, obj)
        r = a.ob_actxywh(obj)
        return (r.x + r.w // 2, r.y + r.h // 2)

    @staticmethod
    def children(a, parent):
        kids, k = [], a.tree[parent].ob_head
        while k != NIL and k != parent:
            kids.append(k)
            k = a.tree[k].ob_next
        return kids


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

    emu = launch(tag="m9", memsize="1088K", extra_args=["--disk", DISK])
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
            L = Layout(sc, max_objs=N_OBJS)
            objs = menu(L)
            L2 = Layout(L.next, max_objs=1)
            objs2 = desk(L2)
            body = build(L, L2, Scratch(objs, L, L2, objs2))
            layouts = [(L, objs, L.pack(objs)), (L2, objs2, L2.pack(objs2))]
            assert L2.next - sc <= scratch_room, (name, L2.next - sc, scratch_room)
            for lay, _, img in layouts:
                b.memload(lay.base, img)
            mem = dict(L.mem)
            mem.update(L2.mem)
            script = PRELUDE + body
            plan = {k + len(PRELUDE): v for k, v in plan_for(body).items()}
            pointer = (b.peek16(ptr), b.peek16(ptr + 2))

            # the shots the plan asks for, in order, and where they go
            shots = []

            def take(bridge, shots=shots, idx=idx):
                path = os.path.join(SHOTDIR, f"m9-{idx:02d}-{len(shots)}.png")
                bridge.screenshot(path)
                shots.append(path)
            for steps in plan.values():
                for i, st in enumerate(steps):
                    if st[0] == "shot":
                        steps[i] = ("shot", take)

            ref_v, ref_a, want = aesref.run(script, objs, mem, plan=dict(plan),
                                            pointer=pointer,
                                            trees={L2.base: objs2})

            words = aesref.encode(script, sc)
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

            shot = os.path.join(SHOTDIR, f"m9-{idx:02d}.png")
            b.screenshot(shot)
            shots.append(shot)
            images = ref_a.shots + [ref_v.to_rgb()]
            if len(images) != len(shots):
                err = err or f"{len(shots)} shots taken, reference has {len(images)}"
            for k, (rgb, path) in enumerate(zip(images, shots)):
                bad, shown = vbxeref.compare_to_shot(rgb, path)
                if bad and not err:
                    err = f"shot {k}: {bad} px differ; first {shown[:3]}"
            out.append((idx, name, err))
            if not err and not keep:
                for path in shots:
                    os.remove(path)
            print(f"  [{idx}] {name:<66s} {'ok' if not err else 'FAIL'}")
    finally:
        emu.stop()

    fails = [r for r in out if r[2]]
    print()
    for idx, name, e in fails:
        print(f"   FAIL [{idx}] {name}: {e}")
    want = len(CASES) if only is None else len(only)
    print(f"gem4xe-m9: {len(out) - len(fails)}/{want} menu cases passed")
    return 1 if fails or len(out) < want else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
