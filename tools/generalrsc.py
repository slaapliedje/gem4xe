#!/usr/bin/env python3
"""GENERAL.RSC: the General control panel extension's dialog.

    tools/generalrsc.py build/general.rsc build/generalrsc.h

WHAT GOES IN A "GENERAL" CPX is the ST's answer, not one invented here:
the everyday settings a person changes once and forgets, and the clock.
On an ST that is the keyboard repeat, the double-click speed, the mouse,
and the date and time; here it is the two settings this AES actually
honours plus the clock, because a control that moves and changes nothing
teaches a wrong model of the machine.

  Double-click speed   evnt_dclick, 1..5
  Sub-menu delay       menu_settings' mn_display.  The other four
                       numbers that call carries are kept and handed
                       back rather than obeyed -- there is no drag
                       tracking and nothing scrolls, which
                       appl_getinfo(AES_MENU) says out loud -- so they
                       are not offered.
  Date and time        Tsetdate/Tsettime, which reach the Ultimate 1MB's
                       DS1305 when there is one (docs/phase16.md).

THE DATE AND TIME ARE EDITABLE FIELDS, not a row of buttons, because
they have too many values for buttons and a person typing 25/12 knows
exactly what they meant.  The templates are the ST's order, and the
validation is digits only: the module checks the RANGES itself, since a
template cannot say that September has thirty days.

This is a MODULE, so its tree belongs to it and not to the panel -- the
host draws nothing of this and knows only the title in the header.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON, G_FTEXT,  # noqa: E402
                    NONE, NORMAL, OUTLINED, SELECTABLE, RBUTTON,
                    TOUCHEXIT, EDITABLE, DEFAULT, EXIT, LASTOB)

ADGENRL = 0

N_DC = 5
N_MN = 4

(GNROOT, GNTITLE, GNDCLBL, GNDCBOX,
 GNDC0, _D1, _D2, _D3, _D4,
 GNMNLBL, GNMNBOX,
 GNMN0, _M1, _M2, _M3,
 GNDTLBL, GNDATE, GNTMLBL, GNTIME,
 GNOK, GNCNCL) = range(21)
NOBS_GENRL = 21

W, H = 38, 17
TITLE = "General"
DCLBL = "Double-click speed"
MNLBL = "Sub-menu delay"
DTLBL = "Date"
TMLBL = "Time"

DC_W, DC_STEP = 4, 5
MN_W, MN_STEP = 8, 8
MN_NAMES = ("Instant", "Fast", "Normal", "Slow")
GROUP_X = 3

# The ST's order, and a template a person reads as the order to type in.
DATE_TMPL = "__/__/__"
TIME_TMPL = "__:__"
DIGITS = "999999"               # rsc's validation: 9 is "a digit"

RADIO = SELECTABLE | RBUTTON | TOUCHEXIT


def general_tree(r):
    dtmpl = r.string(DATE_TMPL)
    objs = [
        (NIL, GNTITLE, GNCNCL, G_BOX, NONE, OUTLINED, 0x00021100,
         ch(0), ch(0), ch(W), ch(H)),
        (GNDCLBL, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TITLE),
         ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1)),
        (GNDCBOX, NIL, NIL, G_STRING, NONE, NORMAL, r.string(DCLBL),
         ch(GROUP_X), ch(3), ch(len(DCLBL)), ch(1)),
        (GNMNLBL, GNDC0, GNDC0 + N_DC - 1, G_IBOX, NONE, NORMAL, 0x00000000,
         ch(GROUP_X), ch(4), ch((N_DC - 1) * DC_STEP + DC_W), ch(1)),
    ]
    for i in range(N_DC):
        objs.append((GNDC0 + i + 1 if i < N_DC - 1 else GNDCBOX,
                     NIL, NIL, G_BUTTON, RADIO, NORMAL, r.string(str(i + 1)),
                     ch(i * DC_STEP), ch(0), ch(DC_W), ch(1)))
    objs.append((GNMNBOX, NIL, NIL, G_STRING, NONE, NORMAL, r.string(MNLBL),
                 ch(GROUP_X), ch(6), ch(len(MNLBL)), ch(1)))
    objs.append((GNDTLBL, GNMN0, GNMN0 + N_MN - 1, G_IBOX, NONE, NORMAL,
                 0x00000000,
                 ch(GROUP_X), ch(7), ch((N_MN - 1) * MN_STEP + MN_W), ch(1)))
    for i in range(N_MN):
        objs.append((GNMN0 + i + 1 if i < N_MN - 1 else GNMNBOX,
                     NIL, NIL, G_BUTTON, RADIO, NORMAL, r.string(MN_NAMES[i]),
                     ch(i * MN_STEP), ch(0), ch(MN_W), ch(1)))
    objs.append((GNDATE, NIL, NIL, G_STRING, NONE, NORMAL, r.string(DTLBL),
                 ch(GROUP_X), ch(9), ch(len(DTLBL)), ch(1)))
    objs.append((GNTMLBL, NIL, NIL, G_FTEXT, EDITABLE, NORMAL,
                 r.ted("", dtmpl, DIGITS),
                 ch(GROUP_X + 6), ch(9), ch(len(DATE_TMPL)), ch(1)))
    objs.append((GNTIME, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TMLBL),
                 ch(GROUP_X + 18), ch(9), ch(len(TMLBL)), ch(1)))
    objs.append((GNOK, NIL, NIL, G_FTEXT, EDITABLE, NORMAL,
                 r.ted("", TIME_TMPL, DIGITS),
                 ch(GROUP_X + 24), ch(9), ch(len(TIME_TMPL)), ch(1)))
    objs.append((GNCNCL, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT,
                 NORMAL, r.string("OK"), ch(8), ch(14), ch(9), ch(1)))
    objs.append((GNROOT, NIL, NIL, G_BUTTON, SELECTABLE | EXIT | LASTOB,
                 NORMAL, r.string("Cancel"), ch(21), ch(14), ch(9), ch(1)))
    assert len(objs) == NOBS_GENRL, (len(objs), NOBS_GENRL)
    return r.tree(objs)


INDICES = [("ADGENRL", ADGENRL), ("GNROOT", GNROOT), ("GNTITLE", GNTITLE),
           ("GNDC0", GNDC0), ("GNMN0", GNMN0), ("GNDATE", GNDATE),
           ("GNTIME", GNTIME), ("GNOK", GNOK), ("GNCNCL", GNCNCL),
           ("N_DC", N_DC), ("N_MN", N_MN), ("NOBS_GENRL", NOBS_GENRL)]


def build():
    r = rsc.Rsc()
    assert general_tree(r) == ADGENRL
    return r


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: GENERAL.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_GENERAL_RSC_H", "#define GEM4XE_GENERAL_RSC_H",
             f"#define GENERAL_RSC_SIZE {len(data)}"]
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
    print(f"{argv[1]}: {len(data)} bytes, {NOBS_GENRL} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
