"""Every dialog fits the 3D look.

With the 3D look on (src/aes/objc.c) an indicator or activator is drawn
ADJ3DSTD pixels bigger on every side.  On an 8-pixel cell that is a
quarter of a character, which is enough for a radio row to run into the
label above it or for two buttons a cell apart to touch -- what the first
pictures of the look showed (docs/phase85.md).  tools/rsc.py's flags3d
gives a dialog its flags and overlaps3d measures what they would draw
over; this holds every dialog the system ships to none.
"""

import inspect
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import aesref                                   # noqa: E402
import rsc                                      # noqa: E402
from rsc import ch, NIL, flags3d, overlaps3d     # noqa: E402
import calcrsc, clockrsc, colorrsc, cpanelrsc   # noqa: E402,E401
import deskrsc, fselrsc, generalrsc             # noqa: E402,E401


def dialogs():
    """(name, objects as the resource gets them) for every tree a
    generator builds with look3d=True."""
    out = []
    for mod in (calcrsc, clockrsc, colorrsc, cpanelrsc, deskrsc, generalrsc):
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if not name.endswith("_tree") or fn.__module__ != mod.__name__:
                continue
            r = rsc.Rsc()
            got = {}

            def grab(objs, look3d=False, flat=(), got=got):
                if look3d:
                    got["objs"] = flags3d(objs, flat)
                return 0
            r.tree = grab
            try:
                fn(r)
            except TypeError:
                continue                        # a helper, not a tree
            if "objs" in got:
                out.append((f"{mod.__name__}.{name}", got["objs"]))
    r = fselrsc.build()
    first, n = r.trees[0]
    out.append(("fselrsc", [(o.nxt, o.head, o.tail, o.typ, o.flags, o.state,
                             o.spec, o.x, o.y, o.w, o.h)
                            for o in r.objects[first:first + n]]))
    return out


class Look3d(unittest.TestCase):
    def test_every_dialog_fits(self):
        seen = dialogs()
        self.assertGreaterEqual(len(seen), 15, [n for n, _ in seen])
        for name, objs in seen:
            with self.subTest(dialog=name):
                self.assertEqual(overlaps3d(objs), [],
                                 f"{name}: the 3D look draws one object over another")

    def test_the_check_speaks(self):
        # two buttons a cell apart, and a label right above one: both are
        # exactly what the first layouts had
        A = aesref
        objs = flags3d([
            (NIL, 1, 3, A.G_BOX, 0, 0, 0x00021100, ch(0), ch(0), ch(30), ch(6)),
            (2, NIL, NIL, A.G_STRING, 0, 0, 0, ch(2), ch(1), ch(10), ch(1)),
            (3, NIL, NIL, A.G_BUTTON, A.SELECTABLE, 0, 0, ch(2), ch(2), ch(8), ch(1)),
            (0, NIL, NIL, A.G_BUTTON, A.SELECTABLE | A.EXIT | A.LASTOB, 0, 0,
             ch(10), ch(2), ch(8), ch(1)),
        ])
        bad = overlaps3d(objs)
        self.assertIn((2, 1, "touches"), bad)
        self.assertIn((2, 3, "touches"), bad)

    def test_the_flags(self):
        A = aesref
        objs = flags3d([
            (NIL, 1, 3, A.G_BOX, 0, 0, 0x00021100, ch(0), ch(0), ch(30), ch(6)),
            (2, NIL, NIL, A.G_STRING, 0, 0, 0, ch(2), ch(1), ch(10), ch(1)),
            (3, NIL, NIL, A.G_BUTTON, A.SELECTABLE | A.RBUTTON, 0, 0, ch(2), ch(3), ch(8), ch(1)),
            (0, NIL, NIL, A.G_BUTTON, A.SELECTABLE | A.EXIT | A.LASTOB, 0, 0,
             ch(12), ch(3), ch(8), ch(1)),
        ], flat=())
        self.assertEqual([o[4] & A.FL3DMASK for o in objs],
                         [A.FL3DBAK, 0, A.FL3DIND, A.FL3DACT])


if __name__ == "__main__":
    unittest.main()
