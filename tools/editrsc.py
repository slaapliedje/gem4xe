#!/usr/bin/env python3
"""EDIT.RSC: EDIT's resource, built on the host.

    tools/editrsc.py build/edit.rsc build/editrsc.h

Two trees -- the menu bar and the About box -- and the free strings:
every alert, the file selector's title, and the words the info line is
made of.  None of them is in the C (docs/shipping.md).

The menu is laid out as RCS lays one out, the way tools/deskrsc.py's is:
titles packed on the bar, a drop-down per title at the title's column,
the Desk box with eight children for the AES to put accessories in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON, G_TITLE,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, DEFAULT, EXIT, DISABLED,
                    OUTLINED, LASTOB)

ADMENU, ADABOUT = 0, 1


def keyed(label, key, width):
    """An item with its CONTROL shortcut at the right, TOS-style."""
    return "  " + label.ljust(width - 5) + "^" + key + " "


FILE_W = 16
MENU = [
    (" Desk ", 2, 20, ["  About EDIT...", "-", "1", "2", "3", "4", "5", "6"]),
    (" File ", 8, FILE_W, [keyed("Open...", "O", FILE_W),
                           keyed("Save", "S", FILE_W), "-",
                           keyed("Quit", "Q", FILE_W)]),
]
TITLE_X = [0, 6]
ACTIVE_W = 12                               # " Desk " and " File "

ROOT, THEBAR, THEACTIVE = 0, 1, 2
DESKMENU, FILEMENU = 3, 4
THEDROPS = 5
DESKBOX, ABOUITEM = 6, 7                    # 8 separator, 9..14 accessories
FILEBOX, OPENITEM, SAVEITEM = 15, 16, 17    # 18 separator
QUITITEM = 19
NOBS_MENU = 20


def menu_tree(r):
    objs = [
        (NIL, THEBAR, THEDROPS, G_IBOX, NONE, NORMAL, 0, ch(0), ch(0), ch(80), ch(30)),
        (THEDROPS, THEACTIVE, THEACTIVE, G_BOX, NONE, NORMAL, 0x00001100,
         ch(0), ch(0), ch(80), ch(1, 2)),
        (THEBAR, DESKMENU, FILEMENU, G_IBOX, NONE, NORMAL, 0,
         ch(2), ch(0), ch(ACTIVE_W), ch(1, 3)),
    ]
    for i, (title, _, _, _) in enumerate(MENU):
        nxt = THEACTIVE if i == len(MENU) - 1 else DESKMENU + i + 1
        objs.append((nxt, NIL, NIL, G_TITLE, NONE, NORMAL, r.string(title),
                     ch(TITLE_X[i]), ch(0), ch(len(title)), ch(1, 3)))
    objs.append((ROOT, DESKBOX, FILEBOX, G_IBOX, NONE, NORMAL, 0,
                 ch(0), ch(1, 3), ch(80), ch(30 - 1)))
    box = THEDROPS + 1
    for i, (_, x, w, items) in enumerate(MENU):
        first, last = box + 1, box + len(items)
        nxt = THEDROPS if i == len(MENU) - 1 else last + 1
        objs.append((nxt, first, last, G_BOX, NONE, NORMAL, 0x00FF1100,
                     ch(x), ch(0), ch(w), ch(len(items))))
        for j, item in enumerate(items):
            state = NORMAL
            if item == "-":
                item, state = "-" * w, DISABLED
            flags = LASTOB if i == len(MENU) - 1 and j == len(items) - 1 else NONE
            nxt = box if j == len(items) - 1 else first + j + 1
            objs.append((nxt, NIL, NIL, G_STRING, flags, state, r.string(item),
                         ch(0), ch(j), ch(w), ch(1)))
        box = last + 1
    assert len(objs) == NOBS_MENU, (len(objs), NOBS_MENU)
    assert objs[ABOUITEM][6].s.startswith("  About")
    assert objs[SAVEITEM][6].s.startswith("  Save")
    assert objs[QUITITEM][6].s.startswith("  Quit")
    assert objs[DESKBOX][2] - objs[DESKBOX][1] == 7    # eight children
    return r.tree(objs)


def _version():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "VERSION")) as f:
        return f.read().strip()


ABOUT_W, ABOUT_H = 36, 11
ABOUT = [
    ("EDIT", 16, 1),
    ("A small text editor", 8, 2),
    ("from gem4xe " + _version(), (ABOUT_W - len("from gem4xe " + _version())) // 2, 4),
    ("Atari text with its own", 6, 5),
    ("characters, and ST and PC", 5, 6),
    ("text with theirs.", 9, 7),
]
NOBS_ABOUT = len(ABOUT) + 2
ABOK = NOBS_ABOUT - 1


def about_tree(r):
    objs = [(NIL, 1, ABOK, G_BOX, NONE, OUTLINED, 0x00021100,
             ch(0), ch(0), ch(ABOUT_W), ch(ABOUT_H))]
    for i, (text, x, y) in enumerate(ABOUT):
        objs.append((i + 2, NIL, NIL, G_STRING, NONE, NORMAL, r.string(text),
                     ch(x), ch(y), ch(len(text)), ch(1)))
    objs.append((ROOT, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT | LASTOB,
                 NORMAL, r.string("OK"), ch(14), ch(ABOUT_H - 2), ch(8), ch(1)))
    assert len(objs) == NOBS_ABOUT
    return r.tree(objs)


# The free strings, in order: (index name, text).  '#' is a number the
# program puts there, '@' a file's name or a kind of line end.
STRINGS = [
    ("ST_NOMEM", "[3][There is not enough memory|for EDIT.][ Quit ]"),
    ("ST_TOOBIG", "[1][@ is too big for EDIT,|which takes files of up|to # KB.][ OK ]"),
    ("ST_NOOPEN", "[3][@ would not open.][ OK ]"),
    ("ST_NOSAVE", "[3][@ could not be saved:|no room on the disk, or|it is locked.  The file|is as it was.][ OK ]"),
    ("ST_INTEMP", "[3][@ could not be written.|The text is in EDIT.TMP|beside it.][ OK ]"),
    ("ST_CHANGED", "[2][@ has changed.][Save|Discard|Cancel]"),
    ("ST_FULL", "[1][The text is as long as|EDIT can hold.][ OK ]"),
    ("ST_TOPEN", "Open a file"),
    ("ST_INFO", "Line #  Column #  @   ^S saves, Esc closes"),
    ("ST_TITLE", "EDIT"),
    ("ST_TEMP", "EDIT.TMP"),
    ("ST_EATARI", "Atari ($9B)"),
    ("ST_ECRLF", "CR LF"),
    ("ST_ELF", "LF"),
    ("ST_ECR", "CR"),
]


def build():
    r = rsc.Rsc()
    assert menu_tree(r) == ADMENU
    assert about_tree(r) == ADABOUT
    for i, (name, text) in enumerate(STRINGS):
        assert r.free_string(text) == i, (name, i)
    return r


INDICES = [("ADMENU", ADMENU), ("ADABOUT", ADABOUT),
           ("DESKMENU", DESKMENU), ("FILEMENU", FILEMENU),
           ("ABOUITEM", ABOUITEM), ("OPENITEM", OPENITEM),
           ("SAVEITEM", SAVEITEM), ("QUITITEM", QUITITEM), ("ABOK", ABOK),
           *[(name, i) for i, (name, _) in enumerate(STRINGS)]]


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: EDIT.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef EDIT_RSC_H", "#define EDIT_RSC_H"]
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
    print(f"{argv[1]}: {len(data)} bytes; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
