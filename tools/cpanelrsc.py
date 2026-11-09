#!/usr/bin/env python3
"""CPANEL.RSC: the control panel's resource, built on the host.

    tools/cpanelrsc.py build/cpanel.rsc build/cpanelrsc.h

One tree, ADCPANEL: what the panel's WINDOW shows (phase 135,
docs/cpanel-plan.md step 2) -- XControl's shape.  A strip along the top
with the time and the date; under it the list, one slot per extension,
its icon with the icon's text beneath and its title beside; a scroll bar
when there are more extensions than slots.  When a module is opened it
fills the window until it ends.

THE PLACES ARE THE PANEL'S, not this file's.  A slot is as tall as a
32x24 icon and a line of text, which is pixels and characters at once,
and the icon block's own offsets are pixels that rsrc_obfix never
touches; so src/apps/cpanel.c lays every object out at run time from the
character cell, and the sizes here are placeholders.  What this file
fixes is the tree -- which object is whose child, its type and flags --
and the words, which are translatable here and nowhere else.

N_VIS SLOTS, and the panel shows as many as fit: four on both screens,
which is XControl's four.  The rows beyond are reached by scrolling.

The settings this panel used to carry itself -- the double-click rate
and the sub-menu delay -- are General's (GENERAL.CPX), which has had
both since phase 48; two places for one setting is one too many.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BOXCHAR, G_ICON,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, TOUCHEXIT, LASTOB)

ADCPANEL = 0

# ---- XGen_Alert's canned alerts ---------------------------------------
#
# THE POINT OF A CANNED ALERT is that every module says the same thing in
# the same words: a person who has seen "that file was not found" once
# should not have to read a second module's version of it.  So the text
# belongs to the PANEL, not to the module, and a module names an alert by
# number instead of carrying a sentence of its own.
#
# WHICH ALSO MAKES IT TRANSLATABLE, which is the other reason it is here.
# A string in the module's C could not be reached by a translator at all;
# these are free strings of CPANEL.RSC beside everything else the panel
# says (docs/shipping.md, "no reader-visible string in the C").
#
# THE NUMBERS ARE ATARI'S, from the Compendium's table for
# (*xcpb->XGen_Alert)(): SAVE_DEFAULTS 0, MEM_ERR 1, FILE_ERR 2,
# FILE_NOT_FOUND 3.  That table has four entries and no others, so the
# free strings are laid out at those indices and the panel indexes
# straight into them -- CPXAL0 exists so that stays true if a string is
# ever added in front.
#
# ONLY ALERT 0 ASKS A QUESTION.  The Compendium: "returns TRUE if 'OK'
# was selected or FALSE if 'Cancel' was selected.  Alerts 1-3 always
# returns TRUE."  So the other three get one button, and a module that
# checks the answer after one of them gets the same TRUE an ST gives it.
XALSAVE, XALMEM, XALFILE, XALNOFILE = range(4)
CPXAL0 = XALSAVE

XALERTS = [
    (XALSAVE, "XALSAVE",
     "[2][Save these settings|as the defaults?][Save|Cancel]"),
    (XALMEM, "XALMEM",
     "[3][There is not enough|memory to do that.][ OK ]"),
    (XALFILE, "XALFILE",
     "[1][The file could not be|read or written.][ OK ]"),
    (XALNOFILE, "XALNOFILE",
     "[1][That file was|not found.][ OK ]"),
]
N_XALERT = len(XALERTS)

# The window's own words, after the alerts so the alerts keep Atari's
# numbers: its title (the two spaces are GEM's, a title clear of the
# closer) and what the list says when there is nothing in it.
CPWTITLE = N_XALERT
CPNONE = N_XALERT + 1
WTITLE = " Control Panel "
NONE_TEXT = "No extensions are installed"

N_VIS = 4                       # slots in the tree

(CPROOT, CPTIME, CPDATE, CPLIST) = range(4)
CPSLOT0 = 4                     # each slot: a box, its icon, its title
SLOT_OBS = 3
CPSBAR = CPSLOT0 + N_VIS * SLOT_OBS
CPUP, CPTRACK, CPSLIDER, CPDOWN = CPSBAR + 1, CPSBAR + 2, CPSBAR + 3, CPSBAR + 4
CPEMPTY = CPDOWN + 1
NOBS_CPANEL = CPEMPTY + 1

# the arrows are the system font's, as the window manager's are
UPCHAR, DOWNCHAR = 0x01, 0x02


def cpanel_tree(r):
    # a slot's icon block: placeholders, filled from the module's header
    # by the panel (its picture, its text, its colours)
    blank = bytes(96)
    objs = [
        # the work area, white and frameless: the window is the frame
        (NIL, CPTIME, CPLIST, G_BOX, NONE, NORMAL, 0x00001170,
         ch(0), ch(0), ch(32), ch(20)),
        (CPDATE, NIL, NIL, G_STRING, NONE, NORMAL, r.string("00:00"),
         ch(1), ch(0), ch(5), ch(1)),
        (CPLIST, NIL, NIL, G_STRING, NONE, NORMAL, r.string("00/00/00"),
         ch(23), ch(0), ch(8), ch(1)),
        # the list: a box with a one-pixel frame inside it
        (CPROOT, CPSLOT0, CPEMPTY, G_BOX, NONE, NORMAL, 0x00011170,
         ch(0), ch(1), ch(32), ch(19)),
    ]
    for k in range(N_VIS):
        box = CPSLOT0 + k * SLOT_OBS
        nxt = box + SLOT_OBS if k < N_VIS - 1 else CPSBAR
        objs.append((nxt, box + 1, box + 2, G_IBOX, SELECTABLE | TOUCHEXIT,
                     NORMAL, 0x00000000, ch(0), ch(k * 4), ch(30), ch(4)))
        objs.append((box + 2, NIL, NIL, G_ICON, NONE, NORMAL,
                     r.iconblk(blank, blank, " " * 12, 32, 24, char=0x1000,
                               xicon=28, yicon=0, xtext=0, ytext=24,
                               wtext=88, htext=8),
                     ch(0), ch(0), ch(11), ch(4)))
        objs.append((box, NIL, NIL, G_STRING, NONE, NORMAL,
                     r.string(" " * 17), ch(12), ch(1), ch(17), ch(1)))
    # the scroll bar: arrows at the ends, a track between with the slider
    objs += [
        (CPEMPTY, CPUP, CPDOWN, G_IBOX, NONE, NORMAL, 0x00000000,
         ch(30), ch(0), ch(2), ch(18)),
        (CPTRACK, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL,
         (UPCHAR << 24) | 0x00011100, ch(0), ch(0), ch(2), ch(1)),
        (CPDOWN, CPSLIDER, CPSLIDER, G_BOX, TOUCHEXIT, NORMAL, 0x00011111,
         ch(0), ch(1), ch(2), ch(16)),
        (CPTRACK, NIL, NIL, G_BOX, TOUCHEXIT, NORMAL, 0x00011100,
         ch(0), ch(0), ch(2), ch(4)),
        (CPSBAR, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL,
         (DOWNCHAR << 24) | 0x00011100, ch(0), ch(17), ch(2), ch(1)),
        (CPLIST, NIL, NIL, G_STRING, LASTOB, NORMAL, r.string(NONE_TEXT),
         ch(2), ch(2), ch(len(NONE_TEXT)), ch(1)),
    ]
    assert len(objs) == NOBS_CPANEL, (len(objs), NOBS_CPANEL)
    return r.tree(objs)


INDICES = [("ADCPANEL", ADCPANEL), ("CPROOT", CPROOT), ("CPTIME", CPTIME),
           ("CPDATE", CPDATE), ("CPLIST", CPLIST), ("CPSLOT0", CPSLOT0),
           ("SLOT_OBS", SLOT_OBS), ("N_VIS", N_VIS), ("CPSBAR", CPSBAR),
           ("CPUP", CPUP), ("CPTRACK", CPTRACK), ("CPSLIDER", CPSLIDER),
           ("CPDOWN", CPDOWN), ("CPEMPTY", CPEMPTY),
           ("CPXAL0", CPXAL0), ("N_XALERT", N_XALERT),
           ("CPWTITLE", CPWTITLE), ("CPNONE", CPNONE),
           ("NOBS_CPANEL", NOBS_CPANEL)]


def build():
    r = rsc.Rsc()
    assert cpanel_tree(r) == ADCPANEL
    for i, name, text in XALERTS:
        assert r.free_string(text) == i, (name, i)
    assert r.free_string(WTITLE) == CPWTITLE
    assert r.free_string(NONE_TEXT) == CPNONE
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
