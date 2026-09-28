"""QED ships whole, with its notice, in every place it ships.

QED (0.9, item 5) is built outside this tree, in the port, and taken
from there (the Makefile's QED_FILES).  It reaches a user three ways --
the card (tools/mkcf.py, QED), its own image (tools/mkfloppy.py,
build_qed) and the release folder (tools/mkdist.py, SYSTEM) -- and each
is a list of its own.  What must hold in all three is the same: the
program, its resource, and QED.TXT with the two licences it names,
because QED's terms forbid selling it and the NOTICE is how a copy says
so.  A program that went out without it would be the one thing this
port must not be.

The image's capacity is checked too: QED and its resource are 361 KB,
which is why the image is 720 KB and not a floppy; if QED grows past
it, this says so instead of the release build dying half-way.
"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mkcf        # noqa: E402
import mkdist      # noqa: E402
import mkfloppy    # noqa: E402

WANT = {"QED.PRG", "QED.RSC", "QED.TXT", "QEDLGPL.TXT", "QEDAPACH.TXT"}


class QedShips(unittest.TestCase):
    def test_the_card_and_the_image_carry_all_of_it(self):
        names = {n.split(">")[1] for _p, n in mkcf.QED}
        self.assertEqual(names, WANT)
        self.assertTrue(all(n.startswith("APPS>") for _p, n in mkcf.QED),
                        "QED goes in \\APPS\\, where INSTALL.BAT copies from")

    def test_the_release_folder_carries_all_of_it(self):
        names = {n for _p, n in mkdist.SYSTEM}
        self.assertTrue(WANT <= names, f"missing from system/: {WANT - names}")
        for n in WANT:
            self.assertIn(n, mkdist.WHAT_IT_IS, f"{n} has no line on the page")

    def test_the_three_lists_name_the_same_files(self):
        card = {p for p, _n in mkcf.QED}
        release = {"build/" + p for p, n in mkdist.SYSTEM if n in WANT}
        self.assertEqual(card, release)

    def test_the_page_says_it_may_not_be_sold(self):
        self.assertIn("NOT SOLD", mkdist.WHAT_IT_IS["QED.PRG"])
        disk = [d for d in mkdist.DISKS if d[0] == "gem-qed.atr"]
        self.assertEqual(len(disk), 1, "gem-qed.atr is not on the page")
        self.assertIn("not sold", disk[0][3])

    def test_the_image_has_room(self):
        built = [os.path.join(ROOT, p) for p, _n in mkcf.QED]
        if not all(os.path.isfile(p) for p in built):
            self.skipTest("QED is not built (make -C the port)")
        need = sum((os.path.getsize(p) + mkfloppy.SECTOR - 3)
                   // (mkfloppy.SECTOR - 2) for p in built)
        self.assertLess(need, mkfloppy.QED_SECTORS - 64,
                        f"QED wants {need} sectors of {mkfloppy.QED_SECTORS}")


if __name__ == "__main__":
    unittest.main()
