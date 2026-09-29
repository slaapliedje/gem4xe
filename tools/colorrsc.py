"""COLOR.RSC: the Color control panel extension's dialog.

    tools/colorrsc.py build/color.rsc build/colorrsc.h

THE ST'S COLOR PANEL, in its shape: a row of the screen's pens to pick
one from, the pen's red, green and blue as sixteen steps each with a
button either side and a bar that shows the level, and Reset, OK and
Cancel.  Sixteen steps because the standard palette is exactly
expressible in them -- FF, BB and 77 are 15, 11 and 7 -- so Reset puts
back the palette gem4xe starts with and not an approximation of it.

The row has sixteen swatches; the module hides the ones the screen does
not have (two on ANTIC, src/apps/color.c).  A swatch is filled with its
own pen, so the row IS the palette, and it changes as the pens do.  The
one being edited is marked by a bar under it rather than by SELECTED,
which would invert its colour and show the wrong one.

The links are computed from each object's parent (`build_tree`), so the
tree cannot be threaded wrongly by hand.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON,       # noqa: E402
                    NONE, NORMAL, OUTLINED, SELECTABLE, TOUCHEXIT,
                    DEFAULT, EXIT, LASTOB)

ADCOLOR = 0

N_PENS = 16
N_LEVELS = 16                   # 0..15 a channel
CHANNELS = ("Red", "Green", "Blue")

W, H = 38, 15
TITLE = "Color"

CLROOT, CLTITLE, CLSWBOX = 0, 1, 2
CLSW0 = 3                       # ..CLSW0 + 15
CLMARK = CLSW0 + N_PENS         # 19
CLCH0 = CLMARK + 1              # 20: the first channel's first object
CH_LBL, CH_MINUS, CH_VALUE, CH_PLUS, CH_FRAME, CH_BAR = range(6)
CH_STEP = 6
CLRESET = CLCH0 + CH_STEP * len(CHANNELS)   # 38
CLOK = CLRESET + 1
CLCNCL = CLOK + 1
NOBS_COLOR = CLCNCL + 1         # 41

SW_X, SW_Y, SW_W = 3, 3, 2      # the swatch row: 16 x 2 cells = 32
CH_Y, CH_DY = 6, 2
BAR_X = 21

# ob_spec colour words: border, text, opaque/pattern, interior
SOLID = 7 << 4
BLACK_BAR = 0x00001000 | 0x100 | SOLID | 1     # no border, solid black
FRAME = 0x00011100                             # a one-pixel black frame


def swatch(pen):
    return (1 << 16) | (1 << 12) | (1 << 8) | SOLID | pen


def build_tree(objs):
    """objs: (parent, type, flags, state, spec, x, y, w, h).  Returns the
    rsc tuples (next, head, tail, ...), children in list order."""
    kids = {i: [] for i in range(len(objs))}
    for i, o in enumerate(objs):
        if o[0] != NIL:
            kids[o[0]].append(i)
    out = []
    for i, (parent, typ, flags, state, spec, x, y, w, h) in enumerate(objs):
        mine = kids[i]
        head, tail = (mine[0], mine[-1]) if mine else (NIL, NIL)
        if parent == NIL:
            nxt = NIL
        else:
            sibs = kids[parent]
            k = sibs.index(i)
            nxt = sibs[k + 1] if k + 1 < len(sibs) else parent
        if i == len(objs) - 1:
            flags |= LASTOB
        out.append((nxt, head, tail, typ, flags, state, spec, x, y, w, h))
    return out


def color_tree(r):
    objs = [None] * NOBS_COLOR
    objs[CLROOT] = (NIL, G_BOX, NONE, OUTLINED, 0x00021100,
                    ch(0), ch(0), ch(W), ch(H))
    objs[CLTITLE] = (CLROOT, G_STRING, NONE, NORMAL, r.string(TITLE),
                     ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1))
    objs[CLSWBOX] = (CLROOT, G_IBOX, NONE, NORMAL, 0,
                     ch(SW_X), ch(SW_Y), ch(SW_W * N_PENS), ch(1))
    for p in range(N_PENS):
        objs[CLSW0 + p] = (CLSWBOX, G_BOX, TOUCHEXIT, NORMAL, swatch(p),
                           ch(SW_W * p), ch(0), ch(SW_W), ch(1))
    objs[CLMARK] = (CLROOT, G_BOX, NONE, NORMAL, BLACK_BAR,
                    ch(SW_X), ch(SW_Y + 1, 1), ch(SW_W), ch(0, 2))
    for c, name in enumerate(CHANNELS):
        b, y = CLCH0 + c * CH_STEP, CH_Y + c * CH_DY
        objs[b + CH_LBL] = (CLROOT, G_STRING, NONE, NORMAL, r.string(name),
                            ch(SW_X), ch(y), ch(len(name)), ch(1))
        objs[b + CH_MINUS] = (CLROOT, G_BUTTON, TOUCHEXIT, NORMAL,
                              r.string("-"), ch(10), ch(y), ch(3), ch(1))
        objs[b + CH_VALUE] = (CLROOT, G_STRING, NONE, NORMAL, r.string("15"),
                              ch(14), ch(y), ch(2), ch(1))
        objs[b + CH_PLUS] = (CLROOT, G_BUTTON, TOUCHEXIT, NORMAL,
                             r.string("+"), ch(17), ch(y), ch(3), ch(1))
        objs[b + CH_FRAME] = (CLROOT, G_BOX, NONE, NORMAL, FRAME,
                              ch(BAR_X), ch(y), ch(N_LEVELS - 1), ch(1))
        objs[b + CH_BAR] = (b + CH_FRAME, G_BOX, NONE, NORMAL, BLACK_BAR,
                            ch(0), ch(0), ch(N_LEVELS - 1), ch(1))
    objs[CLRESET] = (CLROOT, G_BUTTON, SELECTABLE | EXIT, NORMAL,
                     r.string("Reset"), ch(3), ch(13), ch(8), ch(1))
    objs[CLOK] = (CLROOT, G_BUTTON, SELECTABLE | DEFAULT | EXIT, NORMAL,
                  r.string("OK"), ch(15), ch(13), ch(8), ch(1))
    objs[CLCNCL] = (CLROOT, G_BUTTON, SELECTABLE | EXIT, NORMAL,
                    r.string("Cancel"), ch(27), ch(13), ch(8), ch(1))
    assert all(o is not None for o in objs)
    return r.tree(build_tree(objs))


INDICES = [("ADCOLOR", ADCOLOR), ("CLROOT", CLROOT), ("CLSWBOX", CLSWBOX),
           ("CLSW0", CLSW0), ("CLMARK", CLMARK), ("CLCH0", CLCH0),
           ("CH_MINUS", CH_MINUS), ("CH_VALUE", CH_VALUE),
           ("CH_PLUS", CH_PLUS), ("CH_FRAME", CH_FRAME), ("CH_BAR", CH_BAR),
           ("CH_STEP", CH_STEP), ("CLRESET", CLRESET), ("CLOK", CLOK),
           ("CLCNCL", CLCNCL), ("N_PENS", N_PENS), ("N_LEVELS", N_LEVELS),
           ("N_CHANNELS", len(CHANNELS)), ("NOBS_COLOR", NOBS_COLOR)]


def build():
    r = rsc.Rsc()
    assert color_tree(r) == ADCOLOR
    return r


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: COLOR.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_COLOR_RSC_H", "#define GEM4XE_COLOR_RSC_H",
             f"#define COLOR_RSC_SIZE {len(data)}"]
    lines += [f"#define {name:<12s} {value}" for name, value in INDICES]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    data = build().file()
    with open(argv[1], "wb") as f:
        f.write(data)
    with open(argv[2], "w") as f:
        f.write(c_header(data))
    print(f"{argv[1]}: {len(data)} bytes, {NOBS_COLOR} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
