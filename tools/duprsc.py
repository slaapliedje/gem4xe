#!/usr/bin/env python3
"""DUP.RSC: the resource of gem4xe's own DUP (docs/disk-plan.md, part two).

    tools/duprsc.py build/dup.rsc build/duprsc.h

DUP.SYS's lettered menu in a GEM window, done by gem4xe itself: the menu
bar (Desk with About and the accessories, File with Quit), the About box,
and every line DUP prints -- the menu, its questions, what it answers --
as free strings.  None of them is in the C (docs/shipping.md).  In a
string, `#` is a number the program puts there, `@` a name, and `|` the
end of a line.

The questions are DOS 2's DUP's in spirit, so that a person who knows it
finds the same letters asking the same things; the banner is gem4xe's,
not Atari's.
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
    return "  " + label.ljust(width - 5) + "^" + key + " "


FILE_W = 10
MENU = [
    (" Desk ", 2, 20, ["  About DUP...", "-", "1", "2", "3", "4", "5", "6"]),
    (" File ", 8, FILE_W, [keyed("Quit", "Q", FILE_W)]),
]
TITLE_X = [0, 6]
ACTIVE_W = 12

ROOT, THEBAR, THEACTIVE = 0, 1, 2
DESKMENU, FILEMENU = 3, 4
THEDROPS = 5
DESKBOX, ABOUITEM = 6, 7                    # 8 separator, 9..14 accessories
FILEBOX, QUITITEM = 15, 16
NOBS_MENU = 17


def menu_tree(r):
    """As tools/editrsc.py lays EDIT's out: RCS's shape."""
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
    assert objs[QUITITEM][6].s.startswith("  Quit")
    assert objs[DESKBOX][2] - objs[DESKBOX][1] == 7    # eight children
    return r.tree(objs)


def _version():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "VERSION")) as f:
        return f.read().strip()


ABOUT_W, ABOUT_H = 36, 10
ABOUT = [
    ("DUP", 16, 1),
    ("DOS 2's disk menu, for GEM", 5, 2),
    ("from gem4xe " + _version(), (ABOUT_W - len("from gem4xe " + _version())) // 2, 4),
    ("Its letters ask what DUP's", 5, 5),
    ("asked, on any DOS.", 9, 6),
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


MENU_TEXT = "|".join([
    "A. DISK DIRECTORY  I. FORMAT DISK",
    "B. RUN CARTRIDGE   J. DUPLICATE DISK",
    "C. COPY FILE       K. BINARY SAVE",
    "D. DELETE FILE(S)  L. BINARY LOAD",
    "E. RENAME FILE     M. RUN AT ADDRESS",
    "F. LOCK FILE       N. CREATE MEM.SAV",
    "G. UNLOCK FILE     O. DUPLICATE FILE",
    "H. WRITE DOS FILES P. FORMAT SINGLE",
])

STRINGS = [
    ("S_TITLE", " DUP "),
    ("S_BANNER", "GEM4XE DUP " + _version() + "|DOS 2'S DISK MENU, FOR GEM||"),
    ("S_MENU", MENU_TEXT + "||"),
    ("S_SELECT", "SELECT ITEM OR RETURN FOR MENU|"),
    ("S_LABEL", "NEWDISK"),
    ("Q_A", "DIRECTORY--SEARCH SPEC?|"),
    ("Q_C", "COPY--FROM, TO?|"),
    ("Q_D", "DELETE FILESPEC|"),
    ("Q_DCONF", "DELETE FILE @? "),
    ("Q_E", "RENAME, GIVE OLD NAME, NEW|"),
    ("Q_F", "WHAT FILE TO LOCK?|"),
    ("Q_G", "WHAT FILE TO UNLOCK?|"),
    ("Q_H", "DRIVE TO WRITE DOS FILES TO?|"),
    ("Q_HCONF", "TYPE \"Y\" TO WRITE DOS TO DRIVE #.|"),
    ("Q_I", "WHICH DRIVE TO FORMAT?|"),
    ("Q_ICONF", "TYPE \"Y\" TO FORMAT DISK #|"),
    ("Q_J", "DUP DISK--SOURCE,DEST DRIVES?|"),
    ("Q_JBOTH", "INSERT BOTH DISKS, TYPE RETURN|"),
    ("Q_SRC", "INSERT SOURCE DISK, TYPE RETURN|"),
    ("Q_DST", "INSERT DESTINATION DISK, TYPE RETURN|"),
    ("Q_O", "NAME OF FILE TO MOVE?|"),
    ("R_FREE", "# FREE SECTORS|"),
    ("R_ERROR", "ERROR- #|"),
    ("R_NOTGEM", "NOT UNDER GEM, WHICH HOLDS THE|MEMORY: QUIT GEM FOR THAT|"),
    ("R_NODOS", "THIS DOS'S OWN DUP WRITES ITS FILES|"),
    ("R_NOSYS", "NO G4DOS DISK IN ANOTHER DRIVE|TO COPY DOS FROM|"),
    ("R_WORKING", "WORKING ON D#: ...|"),
    ("R_DIR", " DIR"),
    ("R_COPYING", "COPYING---@|"),
    ("Q_L", "LOAD FROM WHAT FILE?|"),
    ("R_NOCART", "NO CARTRIDGE|"),
    ("R_NOTPLAIN", "GEM RUNS .COM .XEX .EXE AND .OBJ|FILES ONLY|"),
]


def build():
    r = rsc.Rsc()
    assert menu_tree(r) == ADMENU
    assert about_tree(r) == ADABOUT
    for i, (key, text) in enumerate(STRINGS):
        assert r.free_string(text) == i, key
    return r


INDICES = [("ADMENU", ADMENU), ("ADABOUT", ADABOUT), ("ABOUITEM", ABOUITEM),
           ("QUITITEM", QUITITEM), ("ABOK", ABOK)]


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: DUP.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_DUP_RSC_H", "#define GEM4XE_DUP_RSC_H",
             f"#define DUP_RSC_SIZE {len(data)}"]
    lines += [f"#define {name:<12s} {value}" for name, value in INDICES]
    lines += [f"#define {key:<12s} {i}" for i, (key, _) in enumerate(STRINGS)]
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
