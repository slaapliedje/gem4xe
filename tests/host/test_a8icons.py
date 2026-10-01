"""DESKICON.RSC, gem4xe's own colour icons (tools/a8icons.py, phase 89).

The art is checked against what the desktop and the AES will do with it,
each read from its own source rather than from the generator:

  * the labels are the ones desktop.c's ci_names looks for, spaces and
    case aside -- read out of src/desk/desktop.c;
  * a drive's digit lands on white: the desktop draws it in black,
    transparent, from the 8x8 font (src/aes/objc.c);
  * every pixel's colour planes, turned chunky as rs_chunky turns them,
    come out as the HARDWARE colour of its pen -- map_col read out of
    src/vdi/dev_vbxe.c, not the generator's copy of it;
  * the file parses the way rs_cicons steps it (deskref.deskicon_kinds),
    six kinds, each with its selected form.

test_the_check_speaks breaks the generator's colour map and requires the
plane check to notice, so a test that passes is not one that cannot fail.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import a8icons                                  # noqa: E402
import aesref                                   # noqa: E402
import deskiconrsc                              # noqa: E402
import deskref                                  # noqa: E402


def c_source(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def map_col():
    m = re.search(r"const uint8_t map_col\[16\] = \{([^}]*)\}",
                  c_source("src/vdi/dev_vbxe.c"))
    return [int(v) for v in m.group(1).split(",")]


def ci_names():
    m = re.search(r"ci_names\[N_IB\] = \{([^}]*)\}", c_source("src/desk/desktop.c"))
    return re.findall(r'"([^"]*)"', m.group(1))


def planes_ok(data, hw):
    """Every icon of `data` (a DESKICON.RSC) against the art: the chunky
    colour form's nibbles are hw[pen] where the art has a pen."""
    kinds = deskref.deskicon_kinds(data)
    bad = []
    for (label, _, _, rows), ic in zip(a8icons.ICONS, kinds):
        img = aesref.chunky(ic.col[0], 4, 32)
        for y, r in enumerate(rows):
            for x, k in enumerate(r):
                if k == ".":
                    continue
                b = img[y * 16 + x // 2]
                got = (b & 0x0F) if x & 1 else (b >> 4)
                if got != hw[deskiconrsc.PEN[k]]:
                    bad.append((label, x, y, k, got))
    return bad


class A8Icons(unittest.TestCase):
    def test_the_art(self):
        self.assertEqual(len(a8icons.ICONS), 6)
        for label, _, digit, rows in a8icons.ICONS:
            with self.subTest(icon=label):
                self.assertEqual(len(rows), 32)
                for r in rows:
                    self.assertEqual(len(r), 32, r)
                    self.assertTrue(all(k == "." or k in deskiconrsc.PEN for k in r), r)

    def test_the_labels_are_the_desktops(self):
        want = ci_names()
        got = ["".join(c for c in label.upper() if c != " ")
               for label, _, _, _ in a8icons.ICONS]
        self.assertEqual(got, want)
        for label, _, _, _ in a8icons.ICONS:
            self.assertLessEqual(len(label), 12, label)     # CICON_FTEXT

    def test_the_digit_lands_on_white(self):
        for label, _, digit, rows in a8icons.ICONS:
            if digit is None:
                continue
            x0, y0, pen = digit
            with self.subTest(icon=label):
                self.assertNotEqual(pen, "W", "a white digit hides the mono form")
                cell = {rows[y][x] for y in range(y0, y0 + 8) for x in range(x0, x0 + 8)}
                self.assertEqual(cell, {"W"}, f"{label}: the digit's cell is {cell}")

    def test_the_file(self):
        data = deskiconrsc.build().file()
        kinds = deskref.deskicon_kinds(data)
        self.assertTrue(all(kinds), kinds)
        for (label, _, digit, rows), ic in zip(a8icons.ICONS, kinds):
            with self.subTest(icon=label):
                self.assertEqual(ic.label, label)
                self.assertIsNotNone(ic.sel, "no selected form")
                self.assertEqual((ic.icon.w, ic.icon.h), (32, 32))
                self.assertEqual(ic.char & 0x0F00, 0, "the background is white")
                if digit:
                    self.assertEqual((ic.xchar, ic.ychar), digit[:2])
                mask = [ic.mask[y * 4 + x // 8] & (0x80 >> (x & 7)) != 0
                        for y in range(32) for x in range(32)]
                self.assertEqual(mask, [k != "." for r in rows for k in r])
        self.assertEqual(planes_ok(data, map_col()), [])

    def test_the_check_speaks(self):
        saved = deskiconrsc.MAP_COL
        try:
            m = list(saved)
            m[1], m[2] = m[2], m[1]             # black and red swapped
            deskiconrsc.MAP_COL = tuple(m)
            data = deskiconrsc.build().file()
        finally:
            deskiconrsc.MAP_COL = saved
        self.assertNotEqual(planes_ok(data, map_col()), [])


if __name__ == "__main__":
    unittest.main()
