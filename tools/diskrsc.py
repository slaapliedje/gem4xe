#!/usr/bin/env python3
"""DISKUTIL.RSC: the disk utility's dialog (docs/disk-plan.md, step 3).

    tools/diskrsc.py build/diskutil.rsc build/diskrsc.h

TOS's desktop has one dialog for formatting a disk and copying one, and
this is its shape (the Falcon's DESKDISK.C, read as a specification
only): Format or Copy, the drives, the density, a label, a progress bar,
and what it came to.  It fits the 40 columns of the ANTIC screen, the
narrowest gem4xe has.  Every word a person reads is here, none in the C
(docs/shipping.md): the alerts are free strings, and `#` in one is where
the program puts a drive's number.

The tree is written as a nesting of objects and linked here -- next,
head and tail -- rather than by hand: a 45-object tree linked by hand is
where a wrong index hides.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON, G_FTEXT, G_TEXT,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, RBUTTON, TOUCHEXIT, EDITABLE,
                    DEFAULT, EXIT, LASTOB, IBM, TE_LEFT)

ADDISK = 0
W, H = 38, 21
TITLE = "Format and copy disks"
RADIO = SELECTABLE | RBUTTON
ACT = RADIO | TOUCHEXIT             # the program acts on these at once
DENSITIES = ("Single", "Enhanced", "Double", "2 sides")
SYSTEMS = ("G4DOS", "DOS 2")
STATUS_W = 34
BAR_W = 34
LABEL_TMPL = "________"

# Free strings, in this order: the action button's two words, the
# status lines' words, then the alerts.
STRINGS = [
    ("S_FORMAT", "Format"),
    ("S_LABEL", "NEWDISK"),
    ("S_COPY", "Copy"),
    ("S_DRIVE", "D#: "),
    ("S_SECTORS", " sectors of "),
    ("S_FREE", " bytes free"),
    ("S_FORMATTING", "Formatting D#: ..."),
    ("S_WRITING", "Laying the file system ..."),
    ("S_READING", "Reading D#: ..."),
    ("S_COPYING", "Writing D#: ..."),
    ("S_FORMATTED", "D#: formatted, "),
    ("S_COPIED", "Copied, "),
    ("S_NODISK", "D#: does not answer"),
    ("S_NOTFLOPPY", "D#: is not a floppy drive"),
    ("A_ERASE", "[2][Everything on the disk in|D#: will be erased.][Format|Cancel]"),
    ("A_REPLACE", "[2][Everything on the disk in|D#: will be replaced.][Copy|Cancel]"),
    ("A_SOURCE", "[1][Put the disk to copy FROM|in D#:.][OK|Stop]"),
    ("A_DEST", "[1][Put the disk to copy TO|in D#:.][OK|Stop]"),
    ("A_WPROT", "[1][The disk in D#: is|write-protected.][OK]"),
    ("A_NODRIVE", "[1][D#: does not answer.][OK]"),
    ("A_NOTFLOPPY", "[1][D#: is not a floppy drive,|and is never formatted|here.][OK]"),
    ("A_DENSITY", "[1][The drive in D#: cannot|make that density.][OK]"),
    ("A_BAD", "[1][The disk in D#: has bad|sectors. Use another disk.][OK]"),
    ("A_FAILED", "[1][D#: failed. The disk may|be only partly written.][OK]"),
    ("A_NOMEM", "[1][There is not enough|memory to copy a disk.][OK]"),
    ("A_CANTCOPY", "[1][The disk in D#: has no|floppy's shape, so it is|not copied.][OK]"),
    ("A_NORSC", "[1][DISKUTIL.RSC is missing.][OK]"),
]


def node(name, typ, flags, state, spec, x, y, w, h, kids=()):
    return (name, typ, flags, state, spec, x, y, w, h, list(kids))


def link(top):
    """Depth-first indices, and each object's next/head/tail: a child's
    next is its next sibling, the last child's its parent."""
    flat, names = [], {}

    def walk(n):
        i = len(flat)
        names[n[0]] = i
        flat.append([n[1], n[2], n[3], n[4], n[5], n[6], n[7], n[8], NIL, NIL, NIL])
        kids = [walk(k) for k in n[9]]
        for a, b in zip(kids, kids[1:]):
            flat[a][8] = b
        if kids:
            flat[kids[-1]][8] = i
            flat[i][9], flat[i][10] = kids[0], kids[-1]
        return i

    walk(top)
    objs = []
    for k, (typ, flags, state, spec, x, y, w, h, nxt, head, tail) in enumerate(flat):
        if k == len(flat) - 1:
            flags |= LASTOB
        objs.append((nxt, head, tail, typ, flags, state, spec, x, y, w, h))
    return objs, names


def label(r, name, text, x, y):
    return node(name, G_STRING, NONE, NORMAL, r.string(text), ch(x), ch(y), ch(len(text)), ch(1))


def drives(r, prefix, y):
    return node(prefix + "BOX", G_IBOX, NONE, NORMAL, 0, ch(8), ch(y), ch(8 * 3 - 1), ch(1),
                [node(f"{prefix}{i + 1}", G_BUTTON, ACT, NORMAL, r.string(str(i + 1)),
                      ch(i * 3), ch(0), ch(2), ch(1)) for i in range(8)])


def disk_tree(r):
    x = 0
    dens = []
    for i, name in enumerate(DENSITIES):
        dens.append(node(("DKSD", "DKED", "DKDD", "DKDS")[i], G_BUTTON, RADIO, NORMAL,
                         r.string(name), ch(x), ch(0), ch(len(name) + 1), ch(1)))
        x += len(name) + 2
    top = node("DKROOT", G_BOX, NONE, NORMAL, 0x00021100, ch(0), ch(0), ch(W), ch(H), [
        node("DKTITLE", G_STRING, NONE, NORMAL, r.string(TITLE),
             ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1)),
        node("DKOPBOX", G_IBOX, NONE, NORMAL, 0, ch(2), ch(3), ch(17), ch(1), [
            node("DKFORMAT", G_BUTTON, ACT, NORMAL, r.string("Format"),
                 ch(0), ch(0), ch(8), ch(1)),
            node("DKCOPY", G_BUTTON, ACT, NORMAL, r.string("Copy"),
                 ch(10), ch(0), ch(7), ch(1)),
        ]),
        label(r, "DKFROMLBL", "From", 2, 5),
        drives(r, "DKFROM", 5),
        label(r, "DKTOLBL", "To", 2, 7),
        drives(r, "DKTO", 7),
        label(r, "DKDENLBL", "Density", 2, 9),
        # two pixels down: the 3D buttons' edge would cover the label's foot
        node("DKDENBOX", G_IBOX, NONE, NORMAL, 0, ch(2), ch(10, 2), ch(x - 1), ch(1), dens),
        label(r, "DKFSLBL", "Files", 2, 12),
        node("DKFSBOX", G_IBOX, NONE, NORMAL, 0, ch(9), ch(12), ch(16), ch(1), [
            node("DKSDFS", G_BUTTON, RADIO, NORMAL, r.string(SYSTEMS[0]),
                 ch(0), ch(0), ch(7), ch(1)),
            node("DKDOS2", G_BUTTON, RADIO, NORMAL, r.string(SYSTEMS[1]),
                 ch(9), ch(0), ch(7), ch(1)),
        ]),
        label(r, "DKLBLLBL", "Label", 2, 14),
        # the text as long as the field: the AES makes a field's room the
        # length of the text it loads with, as TOS's does (GEMRSLIB.C
        # fix_tedinfo) -- "NEWDISK" here held seven, and the eighth key
        # typed replaced the seventh.  The program puts S_LABEL in.
        node("DKLABEL", G_FTEXT, EDITABLE, NORMAL,
             r.ted("@" * len(LABEL_TMPL), LABEL_TMPL, "N" * len(LABEL_TMPL)),
             ch(9), ch(14), ch(len(LABEL_TMPL)), ch(1)),
        node("DKBAR", G_BOX, NONE, NORMAL, 0x00011100, ch(2), ch(16), ch(BAR_W), ch(1), [
            node("DKFILL", G_BOX, NONE, NORMAL, 0x00001171, ch(0), ch(0), ch(0), ch(1)),
        ]),
        node("DKSTATUS", G_TEXT, NONE, NORMAL,
             r.ted(" " * STATUS_W, "", "", font=IBM, just=TE_LEFT),
             ch(2), ch(17), ch(STATUS_W), ch(1)),
        node("DKEXIT", G_BUTTON, SELECTABLE | EXIT, NORMAL, r.string("Exit"),
             ch(6), ch(19), ch(9), ch(1)),
        node("DKGO", G_BUTTON, SELECTABLE | DEFAULT | EXIT, NORMAL, r.string("Format"),
             ch(23), ch(19), ch(9), ch(1)),
    ])
    objs, names = link(top)
    return r.tree(objs, look3d=True), names


def build():
    r = rsc.Rsc()
    t, names = disk_tree(r)
    assert t == ADDISK
    for i, (key, text) in enumerate(STRINGS):
        assert r.free_string(text) == i, key
    return r, names


def c_header(data, names):
    lines = [f"/* {os.path.basename(sys.argv[0])}: DISKUTIL.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_DISK_RSC_H", "#define GEM4XE_DISK_RSC_H",
             f"#define DISK_RSC_SIZE {len(data)}",
             f"#define ADDISK       {ADDISK}",
             f"#define DK_STATUS_W  {STATUS_W}",
             f"#define DK_NOBS      {len(names)}"]
    lines += [f"#define {name:<12s} {value}" for name, value in names.items()
              if not name.endswith("LBL")]
    lines += [f"#define {key:<12s} {i}" for i, (key, _) in enumerate(STRINGS)]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    r, names = build()
    data = r.file()
    with open(argv[1], "wb") as f:
        f.write(data)
    with open(argv[2], "w") as f:
        f.write(c_header(data, names))
    print(f"{argv[1]}: {len(data)} bytes, {len(names)} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
