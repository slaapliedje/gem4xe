#!/usr/bin/env python3
"""Phase 4/7 gate: the AES object library.

Builds real GEM object trees, pokes them to the target, runs a script of
objc_* calls on both sides and compares three things against tools/aesref.py:

  * every returned value, call for call (objc_find hits, objc_offset,
    objc_edit's cursor index, form_center's rectangle);
  * the screen, pixel for pixel;
  * the tree and everything it points at, byte for byte -- objc_change writes
    ob_state, ob_center writes the root's position and objc_edit writes back
    through te_ptext, and a wrong write there is invisible on screen.

The trees are the shapes GEM actually uses -- a dialog with a default button,
a menu bar with a dropped menu, nested boxes, a form with editable fields --
rather than synthetic ones, so a failure is something a real .RSC would trip
over.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
import vbxeref, vdiref, aesref, symfile     # noqa: E402
from vdiref import V_OPNWK, V_CLRWK, WORK_IN    # noqa: E402
from aesref import (Obj, Layout, Text, NIL, G_BOX, G_IBOX, G_BUTTON,   # noqa: E402
                    G_STRING, G_TEXT, G_BOXTEXT, G_FTEXT, G_FBOXTEXT, G_IMAGE,
                    G_BOXCHAR, G_TITLE, G_ICON, G_CICON, Rect, LASTOB, DEFAULT,
                    SELECTABLE, EXIT, NORMAL,
                    EDITABLE, INDIRECT, SELECTED, DISABLED, SHADOWED, OUTLINED,
                    CHECKED, CROSSED, HIDETREE, TE_LEFT, TE_RIGHT, TE_CNTR,
                    EDINIT, EDCHAR, EDEND, BACKSPACE, DELETE, ESCAPE,
                    ARROW_LEFT, ARROW_RIGHT,
                    GSX_START, OBJC_DRAW, OBJC_FIND, OBJC_OFFSET, OBJC_EDIT,
                    OBJC_CHANGE, OBJC_ADD, OBJC_DELETE, FORM_CENTER,
                    RBUTTON, FL3DIND, FL3DACT, FL3DBAK, SV_SET, SV_INQUIRE,
                    G4_3DLOOK, AD3DVALUE, BACKGRCOL, INDBUTCOL, LK3DIND, LK3DACT)
OBJC_SYSVAR = 1048

DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
SYMS = os.path.join(ROOT, "build", "m3.sym")
SHOTDIR = os.path.join(ROOT, "build", "shots")
STATUS, ST_GO, ST_DONE = 0x0600, 3, 4
FULL = (0, 0, 640, 240)


def key(c):
    """A keyboard word the way the AES delivers one: scancode high, ASCII low.
    The scancode is not looked at by objc_edit, so any non-zero one will do."""
    return 0x1E00 | ord(c)


# -- trees ------------------------------------------------------------------
# Each builder takes a Layout and returns the object list; the Layout hands
# out the addresses the ob_specs hold.  LASTOB goes on the last object in
# the array, as RCS puts it: objc_draw and objc_find walk the links and
# never look at it, but form_do's field search walks the array and stops
# there.

def dialog(L):
    """A GEM alert-style dialog: shadowed outer box, text, three buttons."""
    return [
        #    next head tail type      flags          state      spec        x   y   w   h
        Obj(NIL,  1,   4,  G_BOX,    0,             SHADOWED,  0x00021100, 160, 60, 320, 110),
        Obj(2,  NIL, NIL,  G_STRING, 0,             0,         L.text("Delete FLOPPY.TXT?"),  16, 16, 288,  8),
        Obj(3,  NIL, NIL,  G_BUTTON, SELECTABLE | EXIT | DEFAULT, 0, L.text("OK"),  24, 72,  72, 20),
        Obj(4,  NIL, NIL,  G_BUTTON, SELECTABLE | EXIT, 0,     L.text("Cancel"), 120, 72,  72, 20),
        Obj(0,  NIL, NIL,  G_BUTTON, SELECTABLE | EXIT | LASTOB, DISABLED, L.text("Help"), 216, 72,  72, 20),
    ]


def menubar(L):
    """A menu bar with one dropped menu and a selected item -- the shape the
    AES builds and the geometry RCS guarantees."""
    return [
        Obj(NIL,  1,   6, G_BOX,    0,      0, 0x00001100,   0,  0, 640, 240),
        Obj(2,  NIL, NIL, G_TITLE,  0,      0, L.text("Desk"),   8,  3,  32,   8),
        Obj(3,  NIL, NIL, G_TITLE,  0,      0, L.text("File"),  56,  3,  32,   8),
        Obj(4,  NIL, NIL, G_TITLE,  0,      0, L.text("View"), 104,  3,  32,   8),
        Obj(5,  NIL, NIL, G_STRING, SELECTABLE, 0,        L.text("  Open"),  56, 20, 112,   8),
        Obj(6,  NIL, NIL, G_STRING, SELECTABLE, CHECKED,  L.text("  Info..."),  56, 30, 112,   8),
        Obj(0,  NIL, NIL, G_STRING, SELECTABLE | LASTOB, SELECTED, L.text("  Quit"),  56, 40, 112,   8),
    ]


def nested(L):
    """Nested boxes: children are positioned relative to their parent, which is
    the single easiest thing to get wrong in ob_offset().  The outer box is
    solid colour 15; the IBOX draws its border only; the OUTLINED box is
    reached through an INDIRECT spec."""
    return [
        Obj(NIL,  1,   1, G_BOX,     0,      0, 0x0002117F,  40, 40, 400, 160),
        Obj(0,    2,   3, G_IBOX,    0,      0, 0x00011100,  20, 20, 340, 120),
        Obj(3,  NIL, NIL, G_BOXCHAR, 0,      CROSSED, 0x41011108,  16, 16,  40,  40),
        Obj(1,    4,   4, G_BOX,     INDIRECT, OUTLINED, L.indirect(0x00021100), 80, 30, 200,  60),
        Obj(3,  NIL, NIL, G_STRING,  LASTOB, 0, L.text("deep"), 24, 26,  32,   8),
    ]


def borders(L):
    """Outward borders: a negative thickness byte in ob_spec.  The byte is
    signed, and a compiler that masks it to 0..255 draws a 254-pixel border
    inward instead of a 2-pixel one outward -- which is why the boxes here
    sit well inside the root, with room around them."""
    return [
        Obj(NIL,  1,   3, G_BOX,     0,      0, 0x00FE1100,  60, 30, 500, 180),
        Obj(2,  NIL, NIL, G_BOX,     0,      0, 0x00FF1130,  40, 30, 120,  40),
        Obj(3,  NIL, NIL, G_IBOX,    0,      0, 0x00FD1100, 200, 30, 120,  40),
        Obj(0,  NIL, NIL, G_BOXCHAR, LASTOB, 0, 0x42FC1108, 360, 30,  60,  40),
    ]


ICON_ROWS = bytes([
    0x00, 0x7F, 0xFE, 0x00,
    0x01, 0x80, 0x01, 0x80,
    0x02, 0x00, 0x00, 0x40,
    0x04, 0x18, 0x18, 0x20,
    0x04, 0x18, 0x18, 0x20,
    0x04, 0x00, 0x00, 0x20,
    0x04, 0x20, 0x04, 0x20,
    0x04, 0x1F, 0xF8, 0x20,
    0x02, 0x00, 0x00, 0x40,
    0x01, 0x80, 0x01, 0x80,
    0x00, 0x7F, 0xFE, 0x00,
    0xFF, 0xFF, 0xFF, 0xFF,
])


def form(L):
    """A form: an FTEXT with a template, an FBOXTEXT, centred and right-
    justified TEXT/BOXTEXT, an image and an OK button."""
    return [
        Obj(NIL,  1,   6, G_BOX,      0,      0, 0x00021100, 120, 40, 400, 150),
        Obj(2,  NIL, NIL, G_FTEXT,    EDITABLE, 0,
            L.ted("GEM4XE", "Name: __________", "X", just=TE_LEFT, color=0x1180),
            16, 16, 200, 8),
        Obj(3,  NIL, NIL, G_FBOXTEXT, EDITABLE, 0,
            L.ted("12", "Count: ___", "9", just=TE_LEFT, color=0x1180, thickness=-1),
            16, 40, 120, 16),
        Obj(4,  NIL, NIL, G_TEXT,     0, 0,
            L.ted("centred", "", "", just=TE_CNTR, color=0x1180),
            16, 70, 200, 8),
        Obj(5,  NIL, NIL, G_BOXTEXT,  0, 0,
            L.ted("right", "", "", just=TE_RIGHT, color=0x1180, thickness=2),
            16, 90, 200, 16),
        Obj(6,  NIL, NIL, G_IMAGE,    0, 0, L.bitblk(ICON_ROWS, 4, 12, color=1),
            300, 20, 32, 12),
        Obj(0,  NIL, NIL, G_BUTTON,   SELECTABLE | EXIT | DEFAULT | LASTOB, 0, L.text("OK"),
            300, 110, 72, 20),
    ]


ICON_MASK = bytes([
    0x00, 0xFF, 0xFF, 0x00,
    0x03, 0xFF, 0xFF, 0xC0,
] + [0x07, 0xFF, 0xFF, 0xE0] * 8 + [
    0x03, 0xFF, 0xFF, 0xC0,
    0x00, 0xFF, 0xFF, 0x00,
])


def icons(L):
    """G_ICON: the mask under the image, the character in the icon's own
    colours, the label under it.  Two of them, one SELECTED, which swaps
    the icon's colours instead of XORing the object (gr_gicon)."""
    ib1 = L.iconblk(ICON_MASK, ICON_ROWS, "DISK", char=ord('A'), xchar=12,
                    ychar=2, icon=Rect(0, 0, 32, 12), text=Rect(0, 14, 64, 8),
                    wb=4, hl=12)
    ib2 = L.iconblk(ICON_MASK, ICON_ROWS, "TRASH", char=0, xchar=0, ychar=0,
                    icon=Rect(0, 0, 32, 12), text=Rect(0, 14, 64, 8),
                    wb=4, hl=12)
    return [
        Obj(NIL,  1,   2, G_BOX,  0,      0, 0x00021100,  80, 40, 400, 120),
        Obj(2,  NIL, NIL, G_ICON, 0,      0,        ib1,  40, 20,  64,  24),
        Obj(0,  NIL, NIL, G_ICON, LASTOB, SELECTED, ib2, 200, 20,  64,  24),
    ]


def cicons(L):
    """G_CICON: a colour icon draws its mono form.  All objc_draw reads of
    a CICONBLK is the ICONBLK it begins with (rsrc_load points the spec at
    a near copy of exactly that), so here the spec IS an ICONBLK.  One
    SELECTED, and objc_change on it swaps the icon's colours rather than
    XORing, as for G_ICON (gr_gicon)."""
    ib1 = L.iconblk(ICON_MASK, ICON_ROWS, "COLOUR", char=ord('C'), xchar=12,
                    ychar=2, icon=Rect(0, 0, 32, 12), text=Rect(0, 14, 64, 8),
                    wb=4, hl=12)
    ib2 = L.iconblk(ICON_MASK, ICON_ROWS, "MONO", char=0, xchar=0, ychar=0,
                    icon=Rect(0, 0, 32, 12), text=Rect(0, 14, 64, 8),
                    wb=4, hl=12)
    return [
        Obj(NIL,  1,   2, G_BOX,   0,      0, 0x00021100,  80, 40, 400, 120),
        Obj(2,  NIL, NIL, G_CICON, 0,      0,        ib1,  40, 20,  64,  24),
        Obj(0,  NIL, NIL, G_CICON, LASTOB, SELECTED, ib2, 200, 20,  64,  24),
    ]


def dialog3d(L):
    """The 3D kinds (AES 3.40) in one dialog: an OUTLINED background
    with a title on it, two indicators of each sort (radio BUTTONs, one
    selected, and a BOX toggle that is), a BOXTEXT indicator, and two
    activators.  With the 3D look off the flags change nothing; with it
    on, everything carrying one is drawn two pixels bigger, raised or
    sunken, on the light grey ground (src/aes/objc.c)."""
    return [
        Obj(NIL,  1,   7, G_BOX,     FL3DBAK, OUTLINED, 0x00021100, 140, 50, 360, 140),
        Obj(2,  NIL, NIL, G_TEXT,    FL3DBAK, 0,
            L.ted("Options", "", "", just=TE_CNTR, color=0x1180), 16, 10, 328, 8),
        Obj(3,  NIL, NIL, G_BUTTON,  SELECTABLE | RBUTTON | FL3DIND, SELECTED,
            L.text("Fast"), 24, 34, 80, 16),
        Obj(4,  NIL, NIL, G_BUTTON,  SELECTABLE | RBUTTON | FL3DIND, 0,
            L.text("Slow"), 120, 34, 80, 16),
        Obj(5,  NIL, NIL, G_BOX,     SELECTABLE | FL3DIND, SELECTED, 0x00011100, 232, 34, 16, 16),
        Obj(6,  NIL, NIL, G_BOXTEXT, FL3DIND, 0,
            L.ted("level", "", "", just=TE_CNTR, color=0x1180, thickness=1), 24, 62, 120, 16),
        Obj(7,  NIL, NIL, G_BUTTON,  SELECTABLE | EXIT | DEFAULT | FL3DACT, 0,
            L.text("OK"), 160, 106, 80, 20),
        Obj(0,  NIL, NIL, G_BUTTON,  SELECTABLE | EXIT | FL3DACT | LASTOB, 0,
            L.text("Cancel"), 256, 106, 80, 20),
    ]


def sysvar(mode, which, in1=0, in2=0):
    return (OBJC_SYSVAR, (), (mode, which, in1, in2))


def draw(start=0, depth=8, clip=FULL):
    return (OBJC_DRAW, clip, (start, depth))


def find(mx, my):
    return (OBJC_FIND, (mx, my), (0, 8))


def change(obj, state, redraw=1, clip=FULL):
    return (OBJC_CHANGE, clip, (obj, state, redraw))


def edit(obj, kind, idx, kchar=0):
    return (OBJC_EDIT, (), (obj, kchar, idx, kind))


# (name, builder, script).  Every script opens the workstation and starts
# the AES first -- gsx_start() is what caches the attribute state each
# case's V_OPNWK resets, so it has to come after it on both sides.
PRELUDE = [(V_OPNWK, (), WORK_IN), (V_CLRWK,), (GSX_START,)]

CASES = [
    ("dialog with default and disabled buttons", dialog,
     [draw()] + [find(x, y) for x, y in
                 [(320, 82), (60, 82), (156, 82), (5, 5), (170, 70)]]),
    ("menu bar with a dropped, selected item", menubar,
     [draw()] + [find(x, y) for x, y in
                 [(70, 24), (70, 44), (20, 5), (600, 200)]]),
    ("nested boxes, INDIRECT spec, relative offsets", nested,
     [draw()] + [find(x, y) for x, y in
                 [(60, 60), (140, 100), (300, 190), (10, 10)]]
     + [(OBJC_OFFSET, (), (o,)) for o in range(5)]),
    ("draw a subtree only", dialog,
     [draw(2, 0), find(60, 82)]),
    ("icons: mask, image, character and label; one selected", icons,
     [draw()] + [find(x, y) for x, y in [(140, 70), (300, 70), (90, 45)]]
     + [change(1, SELECTED), change(2, NORMAL)]),
    ("colour icons draw their mono form; one selected", cicons,
     [draw()] + [find(x, y) for x, y in [(140, 70), (300, 70)]]
     + [change(1, SELECTED), change(2, NORMAL)]),
    ("form: templates, justification, image", form,
     [draw()] + [find(x, y) for x, y in [(150, 60), (200, 88), (430, 65), (310, 25)]]),
    ("objc_change: select, deselect, disable, no redraw", dialog,
     [draw(), change(2, SELECTED), change(3, SELECTED), change(2, 0),
      change(1, DISABLED), change(3, SELECTED | DISABLED, redraw=0),
      change(4, DISABLED)]),
    ("objc_change clipped to a rectangle", dialog,
     [draw(), change(2, SELECTED, clip=(160, 60, 40, 110)),
      change(4, 0, clip=(300, 100, 100, 60))]),
    ("objc_edit: type, backspace, arrows, delete, escape", form,
     [draw(), edit(1, EDINIT, 0), edit(1, EDCHAR, 6, key('!')),
      edit(1, EDCHAR, 7, BACKSPACE), edit(1, EDCHAR, 6, ARROW_LEFT),
      edit(1, EDCHAR, 5, key('x')), edit(1, EDCHAR, 6, DELETE),
      edit(1, EDCHAR, 6, ARROW_RIGHT), edit(1, EDEND, 6),
      edit(2, EDINIT, 0), edit(2, EDCHAR, 2, key('a')),
      edit(2, EDCHAR, 2, key('7')), edit(2, EDCHAR, 3, key('8')),
      edit(2, EDCHAR, 3, ESCAPE), edit(2, EDCHAR, 0, key('4')),
      edit(2, EDEND, 1)]),
    ("objc_edit: fill a field to the end", form,
     [draw(), edit(2, EDINIT, 0), edit(2, EDCHAR, 2, key('9')),
      edit(2, EDCHAR, 3, key('5')), edit(2, EDCHAR, 3, BACKSPACE),
      edit(2, EDCHAR, 2, key('1')), edit(2, EDEND, 3)]),
    # The 3D look.  The switch is the AES's and outlives a case on the
    # target, so each case sets it, and the last puts it back off.
    ("3D look off: the 3D flags draw flat, and objc_sysvar says so", dialog3d,
     [sysvar(SV_SET, G4_3DLOOK, 0), draw(),
      sysvar(SV_INQUIRE, G4_3DLOOK), sysvar(SV_INQUIRE, AD3DVALUE),
      sysvar(SV_INQUIRE, BACKGRCOL), sysvar(SV_INQUIRE, LK3DACT)]),
    ("3D look on: raised, sunken, grey, and pressed", dialog3d,
     [sysvar(SV_SET, G4_3DLOOK, 1),
      sysvar(SV_INQUIRE, G4_3DLOOK), sysvar(SV_INQUIRE, AD3DVALUE),
      sysvar(SV_INQUIRE, INDBUTCOL), sysvar(SV_INQUIRE, LK3DIND),
      sysvar(SV_INQUIRE, LK3DACT), sysvar(SV_SET, BACKGRCOL, 99),
      draw(), change(6, SELECTED), change(2, NORMAL), change(3, SELECTED),
      change(4, NORMAL), change(5, DISABLED),
      sysvar(SV_SET, G4_3DLOOK, 0)]),
    ("form_center then draw", dialog,
     [(FORM_CENTER,), draw(), find(320, 120), (OBJC_OFFSET, (), (2,))]),
    ("form_center of an outlined, shadowed root", nested,
     [(FORM_CENTER,), draw(), (OBJC_OFFSET, (), (4,))]),
    # Every defined branch of the two, with a draw after each so the links
    # are checked on the screen as well as in the tree's own memory
    # (mem_diff).  Deleting an object that is ALREADY out of the chain is
    # not here on purpose: ob_get_par walks ob_next until it finds the
    # object, and on a detached one that walk reaches NIL and indexes
    # tree[-1] -- out of bounds in the C and the last object in Python, so
    # the donor is no more defined there than we are.
    ("objc_add and objc_delete: every branch of the chain", dialog,
     [draw(),
      (OBJC_DELETE, (), (2,)), draw(),      # a middle child: the chain closes
      (OBJC_DELETE, (), (1,)), draw(),      # the head: ob_head moves on
      (OBJC_DELETE, (), (4,)), draw(),      # the tail: ob_tail moves back
      (OBJC_DELETE, (), (3,)), draw(),      # the last one left: both go NIL
      (OBJC_ADD, (), (0, 1)), draw(),       # a first child: head AND tail
      (OBJC_ADD, (), (0, 3)), draw(),       # a second: on the end of the chain
      (OBJC_DELETE, (), (0,))]),            # the root cannot go: 0
    ("outward borders: negative spec thickness", borders,
     [draw()] + [find(x, y) for x, y in [(110, 80), (98, 58), (390, 90)]]),
]


def mem_diff(L, objs, dump):
    """Compare the target's copy of the tree and the Layout's items with the
    reference's.  A Text is compared up to its NUL only: the C writes a
    string, not a buffer, and the bytes past the terminator are whatever
    was there before."""
    want = L.pack(objs)
    if dump[:len(want)] == want:
        return None
    n = len(objs) * aesref.OBJ_SIZE
    if dump[:n] != want[:n]:
        for i, o in enumerate(objs):
            a, b = dump[i * 24:(i + 1) * 24], want[i * 24:(i + 1) * 24]
            if a != b:
                return f"object {i}: target {a.hex()} != {b.hex()}"
    for addr, size in L.items:
        o = addr - L.base
        thing = L.mem[addr]
        blob = L.blob_of(thing)
        got = dump[o:o + size]
        if isinstance(thing, Text):
            got = got.split(b"\0", 1)[0]
            blob = blob.split(b"\0", 1)[0]
        if got != blob:
            return f"item at ${addr:04X} ({type(thing).__name__}): " \
                   f"target {got!r} != {blob!r}"
    return None


def main(argv):
    keep = "--shot" in argv
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    sa, sc = syms["vdi_script"], syms["vdi_scratch"]
    results_addr, count_addr = syms["vdi_results"], syms["vdi_result_count"]
    # The scratch area's size is whatever the linker left between it and
    # the next symbol -- not a number copied out of the C.
    scratch_room = min(a for a in syms.values() if a > sc) - sc
    script_room = min(a for a in syms.values() if a > sa) - sa

    emu = launch(tag="m4", memsize="1088K", extra_args=["--disk", DISK])
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

        for idx, (name, build, body) in enumerate(CASES):
            script = PRELUDE + body
            # The reference runs first so its Layout is untouched by the
            # run when the target's copy is poked.
            L = Layout(sc)
            objs = build(L)
            image = L.pack(objs)
            assert len(image) <= scratch_room, (name, len(image), scratch_room)
            b.memload(sc, image)

            ref_v, ref_a, want = aesref.run(script, objs, L.mem)

            words = aesref.encode(script, sc)
            assert len(words) * 2 <= script_room, (name, len(words), script_room)
            b.memload(sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                                   for w in words))
            b.poke(STATUS + ST_DONE, 0)
            b.poke(STATUS + ST_GO, 1)
            ok = False
            for _ in range(300):
                if b.peek(STATUS + ST_DONE) == 0xA5:
                    ok = True
                    break
                b.frames(4)
            if not ok:
                out.append((idx, name, "timed out"))
                continue
            b.frames(4)

            err = None
            n = b.peek16(count_addr)
            if n != len(want):
                err = f"{n} calls recorded, expected {len(want)}"
            else:
                got = vdiref.decode(
                    b.memdump(results_addr, n * vdiref.RESULT_WORDS * 2), n)
                for i, rec in enumerate(got):
                    if rec != want[i]:
                        err = (f"call {i} (op {script[i][0]}) returned {rec}, "
                               f"expected {want[i]}")
                        break
            if not err:
                err = mem_diff(L, objs, bytes(b.memdump(sc, len(image))))

            shot = os.path.join(SHOTDIR, f"m4-{idx:02d}.png")
            b.screenshot(shot)
            bad, shown = vbxeref.compare_to_shot(ref_v.to_rgb(), shot)
            if bad and not err:
                err = f"{bad} px differ; first {shown[:3]}"
            out.append((idx, name, err))
            if not err and not keep:
                os.remove(shot)
            print(f"  [{idx}] {name:<50s} {'ok' if not err else 'FAIL'}")
    finally:
        emu.stop()

    fails = [r for r in out if r[2]]
    print()
    for idx, name, e in fails:
        print(f"   FAIL [{idx}] {name}: {e}")
    print(f"gem4xe-m4: {len(out) - len(fails)}/{len(out)} AES cases passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
