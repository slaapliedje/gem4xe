#!/usr/bin/env python3
"""MINES.RSC: the mine game's resource, built on the host.

    tools/minesrsc.py build/mines.rsc build/minesrsc.h

Two trees -- the menu bar and the About box -- and the free strings:
the window's title, its information line and the two alerts at the end
of a game.  None of them is in the C (docs/shipping.md).

The menu is laid out as RCS lays one out, the way tools/editrsc.py's is:
titles packed on the bar, a drop-down per title at the title's column,
the Desk box with eight children for the AES to put accessories in.
The three sizes of field are menu items, ticked by the program for the
one in play.
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


GAME_W = 18
MENU = [
    (" Desk ", 2, 20, ["  About Mines...", "-", "1", "2", "3", "4", "5", "6"]),
    (" Game ", 8, GAME_W, [keyed("New game", "N", GAME_W), "-",
                           "  Beginner", "  Intermediate", "  Expert", "-",
                           keyed("Quit", "Q", GAME_W)]),
]
TITLE_X = [0, 6]
ACTIVE_W = 12                               # " Desk " and " Game "

ROOT, THEBAR, THEACTIVE = 0, 1, 2
DESKMENU, GAMEMENU = 3, 4
THEDROPS = 5
DESKBOX, ABOUITEM = 6, 7                    # 8 separator, 9..14 accessories
GAMEBOX, NEWITEM = 15, 16                   # 17 separator
BEGITEM, INTITEM, EXPITEM = 18, 19, 20      # 21 separator
QUITITEM = 22
NOBS_MENU = 23


def menu_tree(r):
    objs = [
        (NIL, THEBAR, THEDROPS, G_IBOX, NONE, NORMAL, 0, ch(0), ch(0), ch(80), ch(30)),
        (THEDROPS, THEACTIVE, THEACTIVE, G_BOX, NONE, NORMAL, 0x00001100,
         ch(0), ch(0), ch(80), ch(1, 2)),
        (THEBAR, DESKMENU, GAMEMENU, G_IBOX, NONE, NORMAL, 0,
         ch(2), ch(0), ch(ACTIVE_W), ch(1, 3)),
    ]
    for i, (title, _, _, _) in enumerate(MENU):
        nxt = THEACTIVE if i == len(MENU) - 1 else DESKMENU + i + 1
        objs.append((nxt, NIL, NIL, G_TITLE, NONE, NORMAL, r.string(title),
                     ch(TITLE_X[i]), ch(0), ch(len(title)), ch(1, 3)))
    objs.append((ROOT, DESKBOX, GAMEBOX, G_IBOX, NONE, NORMAL, 0,
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
    assert objs[NEWITEM][6].s.startswith("  New")
    assert objs[BEGITEM][6].s.startswith("  Beginner")
    assert objs[INTITEM][6].s.startswith("  Intermediate")
    assert objs[EXPITEM][6].s.startswith("  Expert")
    assert objs[QUITITEM][6].s.startswith("  Quit")
    assert objs[DESKBOX][2] - objs[DESKBOX][1] == 7    # eight children
    return r.tree(objs)


def _version():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "VERSION")) as f:
        return f.read().strip()


ABOUT_W, ABOUT_H = 34, 12


def _mid(text):
    return (ABOUT_W - len(text)) // 2


ABOUT_LINES = [
    ("Mines", 1),
    ("Clear the field without", 3),
    ("opening a mine.", 4),
    ("A click opens a square;", 6),
    ("the right button or Shift", 7),
    ("and a click flags one.", 8),
    ("from gem4xe " + _version(), 9),
]
ABOUT = [(t, _mid(t), y) for t, y in ABOUT_LINES]
NOBS_ABOUT = len(ABOUT) + 2
ABOK = NOBS_ABOUT - 1


def about_tree(r):
    objs = [(NIL, 1, ABOK, G_BOX, NONE, OUTLINED, 0x00021100,
             ch(0), ch(0), ch(ABOUT_W), ch(ABOUT_H))]
    for i, (text, x, y) in enumerate(ABOUT):
        objs.append((i + 2, NIL, NIL, G_STRING, NONE, NORMAL, r.string(text),
                     ch(x), ch(y), ch(len(text)), ch(1)))
    objs.append((ROOT, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT | LASTOB,
                 NORMAL, r.string("OK"), ch((ABOUT_W - 8) // 2), ch(ABOUT_H - 2),
                 ch(8), ch(1)))
    assert len(objs) == NOBS_ABOUT
    return r.tree(objs)


# The free strings, in order: (index name, text).  '#' is a number the
# program puts there, in order.
STRINGS = [
    ("ST_TITLE", " Mines "),
    ("ST_INFO", " Mines left #     Time #"),
    ("ST_WON", "[0][The field is clear,|in # seconds.][New game| OK ]"),
    ("ST_LOST", "[3][That was a mine.][New game| OK ]"),
]


def build():
    r = rsc.Rsc()
    assert menu_tree(r) == ADMENU
    assert about_tree(r) == ADABOUT
    for i, (name, text) in enumerate(STRINGS):
        assert r.free_string(text) == i, (name, i)
    return r


INDICES = [("ADMENU", ADMENU), ("ADABOUT", ADABOUT),
           ("DESKMENU", DESKMENU), ("GAMEMENU", GAMEMENU),
           ("ABOUITEM", ABOUITEM), ("NEWITEM", NEWITEM),
           ("BEGITEM", BEGITEM), ("INTITEM", INTITEM), ("EXPITEM", EXPITEM),
           ("QUITITEM", QUITITEM), ("ABOK", ABOK),
           *[(name, i) for i, (name, _) in enumerate(STRINGS)]]


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: MINES.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef MINES_RSC_H", "#define MINES_RSC_H"]
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
