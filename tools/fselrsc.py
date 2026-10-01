#!/usr/bin/env python3
"""The file selector's tree, as a resource built into gem4xe.

    python3 tools/fselrsc.py build/fsel_rsc.c build/fsel_rsc.h

The donor keeps the selector in its own resource (EmuTOS aes/gem_rsc.c,
FSELECTR) and fixes it up at start-up like any other; gem4xe has no
resident resource, so the tree travels as a .RSC file's bytes in the far
image (`fs_rsc`, big-endian, offsets, character rectangles) and
src/aes/fsel.c has rs_fixit() make objects of it in the pool each time
the selector opens -- the same loader that reads an application's
resource, so the selector proves it twice over.  The object indices go
out as a header, so fsel.c and this file cannot disagree on them.

The geometry is the donor's, less the 3D dressing, with one change: a
column of eight drive buttons, A to H, where the donor has three columns
of twenty-six.  DOS 2 has D1: to D8:, and A..H is how sh_cioname maps
them (src/aes/shel.c).

`build()` is the description; tools/aesref.py's fs_input draws from
what tools/rsc.py says the AES makes of it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                              # noqa: E402
from rsc import ch, NIL                                 # noqa: E402
from aesref import (G_BOX, G_IBOX, G_STRING, G_BUTTON, G_BOXCHAR, G_BOXTEXT,
                    G_FBOXTEXT, NONE, SELECTABLE, EXIT, DEFAULT, EDITABLE,
                    LASTOB, TOUCHEXIT, NORMAL, OUTLINED, IBM, TE_LEFT,
                    TE_CNTR)                            # noqa: E402

# The objects, in tree order.  The drive buttons and the name lines are
# runs: FSDRIVES + 1 .. FSDRIVES + NM_DRIVES, F1NAME .. F9NAME.
NM_DRIVES, NM_NAMES = 8, 9
ROOT, FSTITLE, FSDIRTXT, FSDIRECT, FSDRVTXT, FSSELECT, FSDRIVES = range(7)
FS1STDRV = FSDRIVES + 1
FSLSTDRV = FS1STDRV + NM_DRIVES - 1
FILEAREA = FSLSTDRV + 1
FCLSBOX, FTITLE, SCRLBAR, FUPAROW, FDNAROW, FSVSLID, FSVELEV, FILEBOX = \
    range(FILEAREA + 1, FILEAREA + 9)
F1NAME = FILEBOX + 1
F9NAME = F1NAME + NM_NAMES - 1
FSOK, FSCANCEL = F9NAME + 1, F9NAME + 2
NOBS = FSCANCEL + 1

# The editable fields' buffers, as RCS sizes them: the template's
# underscores, and a text of '@'s of that length so that the loader's
# strlen + 1 comes out as the buffer (ob_format reads a leading '@' as an
# empty field).  The lengths are the donor's TEDINFOs'.
LEN_DIRECT, LEN_SELECT, LEN_NAME = 39, 12, 13

INDICES = [
    ("ROOT", ROOT), ("FSTITLE", FSTITLE), ("FSDIRTXT", FSDIRTXT),
    ("FSDIRECT", FSDIRECT), ("FSDRVTXT", FSDRVTXT), ("FSSELECT", FSSELECT),
    ("FSDRIVES", FSDRIVES), ("FS1STDRV", FS1STDRV), ("FSLSTDRV", FSLSTDRV),
    ("FILEAREA", FILEAREA), ("FCLSBOX", FCLSBOX), ("FTITLE", FTITLE),
    ("SCRLBAR", SCRLBAR), ("FUPAROW", FUPAROW), ("FDNAROW", FDNAROW),
    ("FSVSLID", FSVSLID), ("FSVELEV", FSVELEV), ("FILEBOX", FILEBOX),
    ("F1NAME", F1NAME), ("F9NAME", F9NAME), ("FSOK", FSOK),
    ("FSCANCEL", FSCANCEL), ("NM_DRIVES", NM_DRIVES), ("NM_NAMES", NM_NAMES),
    ("LEN_DIRECT", LEN_DIRECT), ("LEN_SELECT", LEN_SELECT),
    ("LEN_NAME", LEN_NAME),
]


def build():
    r = rsc.Rsc()
    at = "@"
    name_tmplt = r.string("_ ________.___ ")     # shared by the nine lines
    name_valid = r.string("xF")
    objs = [
        #  next head tail type flags state spec x y w h
        (NIL, FSTITLE, FSCANCEL, G_BOX, NONE, OUTLINED, 0x00021100,
         ch(0), ch(0), ch(40), ch(22)),
        (FSDIRTXT, NIL, NIL, G_STRING, NONE, NORMAL, r.string("ITEM SELECTOR"),
         ch(1), ch(1), ch(13), ch(1)),
        (FSDIRECT, NIL, NIL, G_STRING, NONE, NORMAL, r.string("Directory:"),
         ch(1), ch(2), ch(10), ch(1)),
        (FSDRVTXT, NIL, NIL, G_FBOXTEXT, EDITABLE, NORMAL,
         r.ted(at * (LEN_DIRECT - 1), "_" * (LEN_DIRECT - 1), "P",
               font=IBM, just=TE_LEFT, color=0x1100, thickness=0),
         ch(1), ch(3, 4), ch(38), ch(1)),
        (FSSELECT, NIL, NIL, G_STRING, NONE, NORMAL, r.string("Drive:"),
         ch(27), ch(5), ch(11), ch(1)),
        (FSDRIVES, NIL, NIL, G_FBOXTEXT, EDITABLE, NORMAL,
         r.ted(at * (LEN_SELECT - 1), "Selection: ________.___", "F",
               font=IBM, just=TE_LEFT, color=0x1100, thickness=0),
         ch(1), ch(5), ch(24), ch(1)),
        (FILEAREA, FS1STDRV, FSLSTDRV, G_IBOX, NONE, NORMAL, 0x00001100,
         ch(27), ch(6), ch(11), ch(9)),
    ]
    for i in range(NM_DRIVES):
        nxt = FSDRIVES if i == NM_DRIVES - 1 else FS1STDRV + i + 1
        # "D1" to "D8", the Atari's names for the drives -- the path the
        # program gets back still says A: to H: (src/aes/fsel.c dir_sset)
        objs.append((nxt, NIL, NIL, G_BOXTEXT, TOUCHEXIT, NORMAL,
                     r.ted(f"D{i + 1}", "", "", just=TE_CNTR, color=0x1100,
                           thickness=-1),
                     ch(0), ch(i), ch(3), ch(1)))
    objs += [
        (FSOK, FCLSBOX, FILEBOX, G_IBOX, NONE, NORMAL, 0x00001100,
         ch(3), ch(7), ch(22), ch(12)),
        (FTITLE, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL, 0x05FF1100,
         ch(0), ch(0), ch(2), ch(1)),
        (SCRLBAR, NIL, NIL, G_BOXTEXT, TOUCHEXIT, NORMAL,
         r.ted("", "", "", font=IBM, just=TE_CNTR, color=0x11A1,
               thickness=-1),
         ch(2), ch(0), ch(20), ch(1)),
        (FILEBOX, FUPAROW, FSVSLID, G_BOX, TOUCHEXIT, NORMAL, 0x00FF1100,
         ch(19), ch(1), ch(3), ch(11)),
        (FDNAROW, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL, 0x01FF1100,
         ch(0), ch(0), ch(3), ch(1)),
        (FSVSLID, NIL, NIL, G_BOXCHAR, TOUCHEXIT, NORMAL, 0x02FF1100,
         ch(0), ch(10), ch(3), ch(1)),
        (SCRLBAR, FSVELEV, FSVELEV, G_BOX, TOUCHEXIT, NORMAL, 0x00FF1111,
         ch(0), ch(1), ch(3), ch(9)),
        (FSVSLID, NIL, NIL, G_BOX, TOUCHEXIT, NORMAL, 0x00FF1100,
         ch(0), ch(0), ch(3), ch(1)),
        (FILEAREA, F1NAME, F9NAME, G_BOX, TOUCHEXIT, NORMAL, 0x00FF1100,
         ch(0), ch(1), ch(19), ch(11)),
    ]
    for i in range(NM_NAMES):
        nxt = FILEBOX if i == NM_NAMES - 1 else F1NAME + i + 1
        objs.append((nxt, NIL, NIL, G_FBOXTEXT, TOUCHEXIT, NORMAL,
                     r.ted(at * (LEN_NAME - 1), name_tmplt, name_valid,
                           font=IBM, just=TE_LEFT, color=0x1100, thickness=0),
                     ch(2), ch(1 + i), ch(15), ch(1)))
    objs += [
        (FSCANCEL, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT, NORMAL,
         r.string("OK"), ch(7), ch(20), ch(9), ch(1)),
        (ROOT, NIL, NIL, G_BUTTON, SELECTABLE | EXIT | LASTOB, NORMAL,
         r.string("Cancel"), ch(23), ch(20), ch(9), ch(1)),
    ]
    assert len(objs) == NOBS, (len(objs), NOBS)
    r.tree(objs, look3d=True)
    return r


def c_source(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: the file selector's .RSC, "
             f"{len(data)} bytes.  Generated -- do not edit. */",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"const uint8_t FAR fs_rsc[{len(data)}] = {{"]
    for i in range(0, len(data), 12):
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in data[i:i + 12])
                     + ",")
    lines.append("};")
    return "\n".join(lines) + "\n"


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: the file selector's "
             "object indices.  Generated -- do not edit. */",
             "#ifndef GEM4XE_FSEL_RSC_H", "#define GEM4XE_FSEL_RSC_H",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"#define FS_RSC_SIZE {len(data)}",
             f"extern const uint8_t FAR fs_rsc[FS_RSC_SIZE];"]
    lines += [f"#define FS_{name:<10s} {value}" for name, value in INDICES]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    data = build().file()
    for path, text in ((argv[1], c_source(data)), (argv[2], c_header(data))):
        with open(path, "w") as f:
            f.write(text)
    print(f"{argv[1]}, {argv[2]}: {len(data)} bytes, {NOBS} objects")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
