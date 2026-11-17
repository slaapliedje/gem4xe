#!/usr/bin/env python3
"""P6PROG.RSC: the resource test-p6's program loads (docs/6502.md, 5b-3).

    tools/p6rsc.py build/p6prog.rsc

One tree, three objects -- a box, a string and a button -- and nothing
else: no images, no icons, no colour extension.  src/p6_prog.c loads it,
reads object 1 and the string its ob_spec points at through far_fetch,
draws that string in its window where it drew its own before (so a
string read wrongly shows in the gate's pixel check), stores a state
into object 2 and reads it back, and asks the AES where object 2 is.
The numbers the gate checks against are here, and only here.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_STRING, G_BUTTON,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, EXIT, LASTOB)

TEXT = "FROM A BANK"                        # what the program drew before
ROOT_X, ROOT_Y, ROOT_W, ROOT_H = 2, 3, 20, 4    # cells
OK_X, OK_Y, OK_W, OK_H = 12, 2, 6, 1


def build(r):
    objs = [
        (NIL, 1, 2, G_BOX, NONE, NORMAL, 0x00021100,
         ch(ROOT_X), ch(ROOT_Y), ch(ROOT_W), ch(ROOT_H)),
        (2, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TEXT),
         ch(1), ch(1), ch(len(TEXT)), ch(1)),
        (0, NIL, NIL, G_BUTTON, SELECTABLE | EXIT | LASTOB, NORMAL,
         r.string("OK"), ch(OK_X), ch(OK_Y), ch(OK_W), ch(OK_H)),
    ]
    return r.tree(objs)


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__)
    r = rsc.Rsc()
    assert build(r) == 0
    data = r.file()
    with open(argv[0], "wb") as f:
        f.write(data)
    print(f"{argv[0]}: {len(data)} bytes, 3 objects in 1 tree")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
