#!/usr/bin/env python3
"""The window ORDER, as wind_get reports it: WF_OWNER and WF_BOTTOM.

WHY THIS IS A HOST TEST AND NOT ONLY test-m8.  m8 compares the target
against tools/aesref.py, and tools/aesref.py is the specification -- so
if the model were wrong the target would be required to be wrong with
it, and the gate would pass.  That is exactly how WF_OWNER got its
wrong answer in the first place: it handed back the TOP and BOTTOM of
the window list where the contract asks for the window directly ABOVE
and the one directly BELOW, and both sides agreed for four phases.

So these numbers are written here from the Compendium (p.455 for
WF_OWNER, p.456 for WF_BOTTOM) rather than from either implementation,
and the model is made to answer them:

    WF_OWNER  parm1 the owner's AES id
              parm2 the open status, 0 closed / 1 open
              parm3 the handle of the window directly ABOVE it
              parm4 ...and of the one directly BELOW it
    WF_BOTTOM parm1 the bottom window, the DESK not counted

"Neither" is the desk, handle 0, which is what is there.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests", "emu"))

import aesref                                           # noqa: E402
from aesref import (WF_OWNER, WF_BOTTOM, WF_TOP, NAME, MOVER,  # noqa: E402
                    CLOSER)
from m4_aes import PRELUDE                              # noqa: E402

DESKWH = 0
KIND = NAME | CLOSER | MOVER


class TestWindowOrder(unittest.TestCase):
    def setUp(self):
        """An AES with the desk up and nothing else, from the model's own
        start-up, so the tree is built the way every gate builds it."""
        _, self.a, _ = aesref.run(PRELUDE, [], {})
        self.a.wm_init()

    def open(self, n):
        """n windows, created and opened in order, so window 1 is at the
        bottom and window n on top."""
        out = []
        for _ in range(n):
            wh = self.a.wm_create(KIND, aesref.Rect(0, 0, 640, 240))
            self.a.wm_open(wh, aesref.Rect(20, 20, 300, 150))
            out.append(wh)
        return out

    def owner(self, wh):
        rc, out = self.a.wm_get(wh, WF_OWNER)
        self.assertEqual(rc, 1, f"wind_get(WF_OWNER) refused window {wh}")
        return out

    def test_one_window_has_the_desk_on_both_sides(self):
        (w1,) = self.open(1)
        self.assertEqual(self.owner(w1)[2:], [DESKWH, DESKWH],
                         "the only window has nothing above and nothing below")

    def test_two_windows_are_each_others_neighbours(self):
        w1, w2 = self.open(2)
        self.assertEqual(self.owner(w1)[2:], [w2, DESKWH],
                         "the bottom window has the other above it")
        self.assertEqual(self.owner(w2)[2:], [DESKWH, w1],
                         "...and the top one has it below")

    def test_the_middle_of_three_has_a_neighbour_each_way(self):
        """The case that tells the contract from the old answer: with
        three open, the middle window's neighbours are NOT the top and
        the bottom of the list."""
        w1, w2, w3 = self.open(3)
        self.assertEqual(self.owner(w2)[2:], [w3, w1])
        self.assertEqual(self.owner(w1)[2:], [w2, DESKWH])
        self.assertEqual(self.owner(w3)[2:], [DESKWH, w2])

    def test_topping_a_window_reorders_the_neighbours(self):
        w1, w2, w3 = self.open(3)
        self.a.wm_mktop(w1)                 # w1 goes to the top
        self.assertEqual(self.a.wm_get(0, WF_TOP)[1][0], w1)
        self.assertEqual(self.owner(w1)[2:], [DESKWH, w3])
        self.assertEqual(self.owner(w3)[2:], [w1, w2])
        self.assertEqual(self.owner(w2)[2:], [w3, DESKWH])

    def test_the_owner_and_the_open_status(self):
        (w1,) = self.open(1)
        self.assertEqual(self.owner(w1)[0], 0,
                         "the application created it, and it is process 0")
        self.assertEqual(self.owner(w1)[1], 1, "it is open")
        self.a.wm_close(w1)
        self.assertEqual(self.owner(w1)[1], 0, "...and now it is not")

    def test_a_closed_window_is_out_of_the_order(self):
        """Closing takes the window out of the tree, so the one that was
        above it closes up."""
        w1, w2, w3 = self.open(3)
        self.a.wm_close(w2)
        self.assertEqual(self.owner(w1)[2:], [w3, DESKWH])
        self.assertEqual(self.owner(w3)[2:], [DESKWH, w1])

    def test_wf_bottom_is_the_bottom_window_not_the_desk(self):
        self.assertEqual(self.a.wm_get(0, WF_BOTTOM)[1][0], DESKWH,
                         "with no window open, the desk is what is there")
        w1, w2 = self.open(2)
        self.assertEqual(self.a.wm_get(0, WF_BOTTOM)[1][0], w1)
        self.a.wm_mktop(w1)
        self.assertEqual(self.a.wm_get(0, WF_BOTTOM)[1][0], w2,
                         "topping the bottom window makes the other one it")

    def test_wf_bottom_answers_without_a_window_of_its_own(self):
        """It is a question about the AES, not about the handle the
        binding still has to pass -- so a handle that names nothing must
        not refuse it, the way WF_TOP does not."""
        (w1,) = self.open(1)
        rc, out = self.a.wm_get(9, WF_BOTTOM)
        self.assertEqual((rc, out[0]), (1, w1))


if __name__ == "__main__":
    unittest.main()
