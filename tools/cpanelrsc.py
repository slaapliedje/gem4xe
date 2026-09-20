#!/usr/bin/env python3
"""CPANEL.RSC: the control panel's resource, built on the host.

    tools/cpanelrsc.py build/cpanel.rsc build/cpanelrsc.h

One tree, ADCPANEL: the settings the AES already honours at run time and
that no human being could reach until now -- the double-click rate
(evnt_dclick) and how long the pointer must rest on an item before its
sub-menu opens (menu_settings' mn_display).

NOTHING HERE IS A SETTING THAT DOES NOTHING.  menu_settings carries five
numbers and only mn_display is live -- there is no drag tracking and
nothing scrolls, which appl_getinfo(AES_MENU) says out loud -- so the
other four are not offered.  A control that moves and changes nothing is
worse than an absent one: it teaches the person a wrong model of the
machine, and they find out by being surprised later.

EACH RADIO GROUP SITS IN A G_IBOX OF ITS OWN because RBUTTON is exclusive
among SIBLINGS: with every button a child of the root, choosing a speed
would clear the delay (the same trap tools/deskrsc.py's pref_tree
records, and the reason that one has two boxes too).

THE TEST BOX IS THE POINT OF THE SPEED CONTROL.  A number from 1 to 5 is
meaningless on its own -- the only question a person actually has is
"can I double-click this fast?" -- so the box answers it: a real
double-click ticks it, a single click does not.  Because the panel
applies each pick immediately rather than on OK, the box is testing the
rate that is about to be kept.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON,   # noqa: E402
                    NONE, NORMAL, OUTLINED, SELECTABLE, RBUTTON,
                    TOUCHEXIT, DEFAULT, EXIT, LASTOB)

ADCPANEL = 0

N_DC = 5                        # evnt_dclick takes 0..4
N_MN = 4                        # the delays this panel offers

(CPROOT, CPTITLE, CPDCLBL, CPDCBOX,
 CPDC0, _DC1, _DC2, _DC3, _DC4,
 CPTSTLBL, CPTEST,
 CPMNLBL, CPMNBOX,
 CPMN0, _MN1, _MN2, _MN3,
 CPOK, CPCNCL) = range(19)
NOBS_CPANEL = 19

W, H = 40, 15
TITLE = "Control Panel"
DCLBL = "Double-click speed"
TSTLBL = "Test"
TEST = "Double-click here"
MNLBL = "Sub-menu delay"

DC_W, DC_STEP = 4, 5            # five numbered boxes, the donor's shape
MN_W, MN_STEP = 8, 8            # named, so they touch and read as one strip
MN_NAMES = ("Instant", "Fast", "Normal", "Slow")
GROUP_X = 4                     # both groups under their own label, not
                                # one of them two characters to its left

RADIO = SELECTABLE | RBUTTON | TOUCHEXIT


def cpanel_tree(r):
    objs = [
        (NIL, CPTITLE, CPCNCL, G_BOX, NONE, OUTLINED, 0x00021100,
         ch(0), ch(0), ch(W), ch(H)),
        (CPDCLBL, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TITLE),
         ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1)),
        (CPDCBOX, NIL, NIL, G_STRING, NONE, NORMAL, r.string(DCLBL),
         ch(GROUP_X), ch(3), ch(len(DCLBL)), ch(1)),
        (CPTSTLBL, CPDC0, CPDC0 + N_DC - 1, G_IBOX, NONE, NORMAL, 0x00000000,
         ch(GROUP_X), ch(4), ch((N_DC - 1) * DC_STEP + DC_W), ch(1)),
    ]
    # 1..5, the rate evnt_dclick takes as 0..4
    for i in range(N_DC):
        objs.append((CPDC0 + i + 1 if i < N_DC - 1 else CPDCBOX,
                     NIL, NIL, G_BUTTON, RADIO, NORMAL, r.string(str(i + 1)),
                     ch(i * DC_STEP), ch(0), ch(DC_W), ch(1)))
    objs.append((CPTEST, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TSTLBL),
                 ch(GROUP_X), ch(6), ch(len(TSTLBL)), ch(1)))
    # SELECTABLE|EXIT, not TOUCHEXIT: form_do must see the second click
    # before it answers, and it sets bit 15 when it did.
    objs.append((CPMNLBL, NIL, NIL, G_BUTTON, SELECTABLE | EXIT, NORMAL,
                 r.string(TEST), ch(11), ch(6), ch(len(TEST) + 3), ch(1)))
    objs.append((CPMNBOX, NIL, NIL, G_STRING, NONE, NORMAL, r.string(MNLBL),
                 ch(GROUP_X), ch(8), ch(len(MNLBL)), ch(1)))
    objs.append((CPOK, CPMN0, CPMN0 + N_MN - 1, G_IBOX, NONE, NORMAL,
                 0x00000000,
                 ch(GROUP_X), ch(9),
                 ch((N_MN - 1) * MN_STEP + MN_W), ch(1)))
    for i in range(N_MN):
        objs.append((CPMN0 + i + 1 if i < N_MN - 1 else CPMNBOX,
                     NIL, NIL, G_BUTTON, RADIO, NORMAL,
                     r.string(MN_NAMES[i]),
                     ch(i * MN_STEP), ch(0), ch(MN_W), ch(1)))
    objs.append((CPCNCL, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT,
                 NORMAL, r.string("OK"), ch(9), ch(12), ch(9), ch(1)))
    objs.append((CPROOT, NIL, NIL, G_BUTTON, SELECTABLE | EXIT | LASTOB,
                 NORMAL, r.string("Cancel"), ch(22), ch(12), ch(9), ch(1)))
    assert len(objs) == NOBS_CPANEL, (len(objs), NOBS_CPANEL)
    return r.tree(objs)


INDICES = [("ADCPANEL", ADCPANEL), ("CPROOT", CPROOT), ("CPTITLE", CPTITLE),
           ("CPDCLBL", CPDCLBL), ("CPDCBOX", CPDCBOX), ("CPDC0", CPDC0),
           ("CPTSTLBL", CPTSTLBL), ("CPTEST", CPTEST), ("CPMNLBL", CPMNLBL),
           ("CPMNBOX", CPMNBOX), ("CPMN0", CPMN0), ("CPOK", CPOK),
           ("CPCNCL", CPCNCL), ("N_DC", N_DC), ("N_MN", N_MN),
           ("NOBS_CPANEL", NOBS_CPANEL)]


def build():
    r = rsc.Rsc()
    assert cpanel_tree(r) == ADCPANEL
    return r


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: CPANEL.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_CPANEL_RSC_H", "#define GEM4XE_CPANEL_RSC_H",
             f"#define CPANEL_RSC_SIZE {len(data)}"]
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
    print(f"{argv[1]}: {len(data)} bytes, {NOBS_CPANEL} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
