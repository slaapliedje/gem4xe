#!/usr/bin/env python3
"""GEMARC.RSC: GemARC's resource, built on the host.

    tools/gemarcrsc.py build/gemarc.rsc build/gemarcrsc.h

Two trees -- the menu bar and the About box -- and the free strings:
every alert, the file selector's titles, the list's heading and the
words its lines and the info line are made of.  None of them is in the
C (docs/shipping.md).  A '#' in a string is a number the program puts
there, an '@' a file's name.

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


FILE_W, ARCH_W = 21, 21
MENU = [
    (" Desk ", 2, 20, ["  About GemARC...", "-", "1", "2", "3", "4", "5", "6"]),
    (" File ", 8, FILE_W, [keyed("Open archive...", "O", FILE_W),
                           keyed("New archive...", "N", FILE_W), "-",
                           keyed("Close archive", "U", FILE_W), "-",
                           keyed("Quit", "Q", FILE_W)]),
    (" Archive ", 14, ARCH_W, [keyed("Extract...", "E", ARCH_W),
                               "  Extract all...",
                               keyed("Select all", "A", ARCH_W), "-",
                               keyed("Add files...", "I", ARCH_W)]),
]
TITLE_X = [0, 6, 12]
ACTIVE_W = 21                               # " Desk " to " Archive "

ROOT, THEBAR, THEACTIVE = 0, 1, 2
DESKMENU, FILEMENU, ARCHMENU = 3, 4, 5
THEDROPS = 6
DESKBOX, ABOUITEM = 7, 8                    # 9 separator, 10..15 accessories
FILEBOX, OPENITEM, NEWITEM = 16, 17, 18     # 19 separator
CLOSITEM = 20                               # 21 separator
QUITITEM = 22
ARCHBOX, XSELITEM, XALLITEM, SALLITEM = 23, 24, 25, 26   # 27 separator
ADDITEM = 28
NOBS_MENU = 29


def menu_tree(r):
    objs = [
        (NIL, THEBAR, THEDROPS, G_IBOX, NONE, NORMAL, 0, ch(0), ch(0), ch(80), ch(30)),
        (THEDROPS, THEACTIVE, THEACTIVE, G_BOX, NONE, NORMAL, 0x00001100,
         ch(0), ch(0), ch(80), ch(1, 2)),
        (THEBAR, DESKMENU, ARCHMENU, G_IBOX, NONE, NORMAL, 0,
         ch(2), ch(0), ch(ACTIVE_W), ch(1, 3)),
    ]
    for i, (title, _, _, _) in enumerate(MENU):
        nxt = THEACTIVE if i == len(MENU) - 1 else DESKMENU + i + 1
        objs.append((nxt, NIL, NIL, G_TITLE, NONE, NORMAL, r.string(title),
                     ch(TITLE_X[i]), ch(0), ch(len(title)), ch(1, 3)))
    objs.append((ROOT, DESKBOX, ARCHBOX, G_IBOX, NONE, NORMAL, 0,
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
    assert objs[QUITITEM][6].s.startswith("  Quit")
    assert objs[ADDITEM][6].s.startswith("  Add files")
    assert objs[DESKBOX][2] - objs[DESKBOX][1] == 7    # eight children
    return r.tree(objs)


def _version():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "VERSION")) as f:
        return f.read().strip()


ABOUT_W, ABOUT_H = 36, 11
ABOUT = [
    ("GemARC", 15, 1),
    ("ARC archives on gem4xe", 7, 2),
    ("from gem4xe " + _version(), (ABOUT_W - len("from gem4xe " + _version())) // 2, 4),
    ("Lists, takes out and makes", 5, 5),
    ("ARC archives: SEA's ARC,", 6, 6),
    ("PKARC's and the Atari's.", 6, 7),
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


# The free strings, in order: (index name, text).
STRINGS = [
    ("ST_NOMEM", "[3][There is not enough memory|for GemARC.][ Quit ]"),
    ("ST_NOTARC", "[3][That is not an ARC archive.][ OK ]"),
    ("ST_NOOPEN", "[3][The archive would not open.][ OK ]"),
    ("ST_FULL", "[1][The archive has more members|than GemARC lists.  The|first # are shown.][ OK ]"),
    ("ST_NOSEL", "[1][Select the files to take|out first, or choose|Extract all.][ OK ]"),
    ("ST_EXISTS", "[2][Some of these files are|there already.][Replace|Skip|Cancel]"),
    ("ST_DONE", "[1][# files taken out.][ OK ]"),
    ("ST_BAD", "[3][# files could not be taken|out: damaged, a method|GemARC does not know, or|no room on the disk.][ OK ]"),
    ("ST_ADDED", "[1][# files put in.][ OK ]"),
    ("ST_ADDFAIL", "[3][The files could not be put|in: a file would not open,|or no room on the disk.|The archive is as it was.][ OK ]"),
    ("ST_TOOMANY", "[1][Up to # files can be put|in at a time.][ OK ]"),
    ("ST_NOFILES", "[1][There are no files there|to put in.][ OK ]"),
    ("ST_TOPEN", "Open an archive"),
    ("ST_TNEW", "Name a new archive"),
    ("ST_TOUT", "Folder to take files out to"),
    ("ST_TADD", "Files to put in"),
    # the columns: name 0, sizes ending at 20 and 29, method 32, date 42
    # (src/apps/gemarc.c member_line)
    ("ST_HEAD", "Name" + " " * 13 + "Size" + " " * 3 + "Packed" + " " * 2
     + "Method" + " " * 4 + "Date"),
    ("ST_INFO", "# files, # bytes, packed to #%"),
    ("ST_NONE", "No archive: File > Open archive..."),
    ("ST_OUTING", "Taking out @"),
    ("ST_ADDING", "Putting in @"),
    ("ST_TITLE", "GemARC"),
    ("ST_TEMP", "GEMARC.TMP"),
    ("ST_M1", "Stored"), ("ST_M2", "Stored"), ("ST_M3", "Packed"),
    ("ST_M4", "Squeezed"), ("ST_M5", "Crunched"), ("ST_M6", "Crunched"),
    ("ST_M7", "Crunched"), ("ST_M8", "Crunched"), ("ST_M9", "Squashed"),
    ("ST_MX", "Method #"),
]


def build():
    r = rsc.Rsc()
    assert menu_tree(r) == ADMENU
    assert about_tree(r) == ADABOUT
    for i, (name, text) in enumerate(STRINGS):
        assert r.free_string(text) == i, (name, i)
    return r


INDICES = [("ADMENU", ADMENU), ("ADABOUT", ADABOUT),
           ("DESKMENU", DESKMENU), ("FILEMENU", FILEMENU), ("ARCHMENU", ARCHMENU),
           ("ABOUITEM", ABOUITEM), ("OPENITEM", OPENITEM), ("NEWITEM", NEWITEM),
           ("CLOSITEM", CLOSITEM), ("QUITITEM", QUITITEM),
           ("XSELITEM", XSELITEM), ("XALLITEM", XALLITEM),
           ("SALLITEM", SALLITEM), ("ADDITEM", ADDITEM), ("ABOK", ABOK),
           *[(name, i) for i, (name, _) in enumerate(STRINGS)]]


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: GEMARC.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEMARC_RSC_H", "#define GEMARC_RSC_H"]
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
