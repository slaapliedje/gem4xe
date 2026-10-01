#!/usr/bin/env python3
"""CALC.RSC: the calculator's resource, built on the host.

    tools/calcrsc.py build/calc.rsc build/calcrsc.h

One tree, ADCALC, and the shape is a GEM control panel rather than a
window: every key is a SELECTABLE|EXIT button, so `form_do` returns the
one that was pressed and the program acts and goes back in.  That is
the donor's own idiom for a keypad dialog and it is why the whole
program is an event loop of six lines.

The display is a G_BOXTEXT over a TEDINFO, right-aligned, and the
program writes into `te_ptext` in place -- the desktop's `inf_numset`
does the same to the counters of its delete dialog.  Ten places is what
a 32-bit signed value needs, and the sign takes an eleventh.

Every reader-visible string is here and none is in the C
(docs/shipping.md): the title, the keys, and the two words on the
buttons that are words.  The digits are not translated but they are
still the resource's, because a translation that moves the keypad
should be able to move them together.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_STRING, G_BUTTON, G_BOXTEXT,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, DEFAULT, EXIT, LASTOB,
                    TE_RIGHT, IBM)

ADCALC = 0

# The tree, object by object.  ROOT, the title, the display, then the
# keys in reading order -- which is also the order a translation would
# read them in, and the order the C's key table is in (src/apps/calc.c).
(CROOT, CTITLE, CDISP, C7, C8, C9, CDIV, C4, C5, C6, CMUL,
 C1, C2, C3, CSUB, C0, CSIGN, CCLR, CADD, CEQ, CQUIT) = range(21)
NOBS_CALC = 21

KW, KH = 4, 2                               # a key
KX, KY = 2, 5                               # where the keypad starts
GAP = 1                                     # between keys
# The panel is sized FROM the keypad rather than beside it: four columns
# and five rows of keys, the last row being = and Quit, plus a margin.
# Written as two numbers it was wrong -- the last row sat a character
# below the box and the AES clipped it away, which draws the same on
# both sides of a gate and answers no click on either.
W = KX * 2 + 4 * KW + 3 * GAP
H = KY + 5 * (KH + GAP)

TITLE = "CALCULATOR"
DISP_PLACES = 11                            # a sign and ten digits
KEYS = [("7", C7), ("8", C8), ("9", C9), ("/", CDIV),
        ("4", C4), ("5", C5), ("6", C6), ("*", CMUL),
        ("1", C1), ("2", C2), ("3", C3), ("-", CSUB),
        ("0", C0), ("+/-", CSIGN), ("C", CCLR), ("+", CADD)]


def key_pos(i):
    """Where key i sits, in characters: four to a row."""
    return KX + (i % 4) * (KW + GAP), KY + (i // 4) * (KH + GAP)


def calc_tree(r):
    objs = [(NIL, CTITLE, CQUIT, G_BOX, NONE, NORMAL, 0x00021100,
             ch(0), ch(0), ch(W), ch(H)),
            (CDISP, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TITLE),
             ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1)),
            (C7, NIL, NIL, G_BOXTEXT, NONE, NORMAL,
             r.ted(" " * DISP_PLACES, "_" * DISP_PLACES, "9",
                   font=IBM, just=TE_RIGHT, thickness=-1),
             ch(2), ch(3), ch(DISP_PLACES + 2), ch(1))]
    for i, (label, obj) in enumerate(KEYS):
        x, y = key_pos(i)
        objs.append((obj + 1, NIL, NIL, G_BUTTON, SELECTABLE | EXIT, NORMAL,
                     r.string(label), ch(x), ch(y), ch(KW), ch(KH)))
    objs.append((CQUIT, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT,
                 NORMAL, r.string("="), ch(KX), ch(KY + 4 * (KH + GAP)),
                 ch(KW * 2 + GAP), ch(KH)))
    objs.append((CROOT, NIL, NIL, G_BUTTON, SELECTABLE | EXIT | LASTOB,
                 NORMAL, r.string("Quit"),
                 ch(KX + 2 * (KW + GAP) + GAP), ch(KY + 4 * (KH + GAP)),
                 ch(KW * 2), ch(KH)))
    assert len(objs) == NOBS_CALC, (len(objs), NOBS_CALC)
    return r.tree(objs, look3d=True)


INDICES = [("ADCALC", ADCALC), ("CROOT", CROOT), ("CTITLE", CTITLE),
           ("CDISP", CDISP), ("C7", C7), ("C8", C8), ("C9", C9),
           ("CDIV", CDIV), ("C4", C4), ("C5", C5), ("C6", C6),
           ("CMUL", CMUL), ("C1", C1), ("C2", C2), ("C3", C3),
           ("CSUB", CSUB), ("C0", C0), ("CSIGN", CSIGN), ("CCLR", CCLR),
           ("CADD", CADD), ("CEQ", CEQ), ("CQUIT", CQUIT),
           ("NOBS_CALC", NOBS_CALC), ("DISP_PLACES", DISP_PLACES)]


def build():
    r = rsc.Rsc()
    assert calc_tree(r) == ADCALC
    return r


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: CALC.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_CALC_RSC_H", "#define GEM4XE_CALC_RSC_H",
             f"#define CALC_RSC_SIZE {len(data)}"]
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
    print(f"{argv[1]}: {len(data)} bytes, {NOBS_CALC} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
