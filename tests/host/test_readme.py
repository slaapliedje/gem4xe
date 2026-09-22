"""The README's facts, against the tree they describe.

THE PAGE IS THE PRODUCT'S FRONT DOOR and it had stopped keeping up: the
gate table said `192/192` for a host suite that collects rather more
than that, and had no row at all for four gates `make test` had been
running for a whole release.  Nobody had broken anything -- the numbers
were maintained by remembering, and remembering is not a mechanism.

So they are checked here, where a wrong one is a red gate on the commit
that causes it instead of something noticed while reading the page
before a release.  `tools/readme.py --write` puts the numbers back;
`make readme` is that.

WHAT IS NOT CHECKED, deliberately: the third column, which says what
each gate proves and which bug it caught.  That is the value of the
table and no tool can generate it, so a gate the table has never heard
of is an error for a person -- never a row invented to go green.
"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import readme                                       # noqa: E402

HOW = "run `make readme`, which writes the numbers back"


class Readme(unittest.TestCase):
    def setUp(self):
        self.doc = readme.read(readme.README)

    def test_the_facts_are_current(self):
        """The host suite's size, the version, and how many compiler
        defects tools/ccbug knows about -- all three of which the tree
        can answer for itself."""
        for what, found, want, _fix in readme.facts(self.doc):
            self.assertEqual(found, want,
                             f"README.md: {what} says {found}, the tree says "
                             f"{want} -- {HOW}")

    def test_it_states_facts_at_all(self):
        """Each is found by matching the sentence that carries it, so an
        edit that rewords one would leave the check above passing by
        having nothing left to compare.  It has to find all three."""
        self.assertEqual(
            len(readme.facts(self.doc)), 3,
            "README.md no longer states its version, host-suite count and "
            "compiler-defect count in the shape tools/readme.py looks for, "
            "so one of them is unchecked again -- teach the tool the wording")

    def test_every_gate_make_test_runs_is_in_the_table(self):
        """A row of its own, or named inside another row's sentence --
        test-m15x and test-m15d are the same gate on two other disks and
        are named in test-m15's.  What matters is not being invisible.
        """
        mentioned = readme.table_mentions(self.doc)
        missing = [g for g in readme.gates_in_make_test()
                   if g not in mentioned]
        self.assertEqual(missing, [],
                         f"`make test` runs these and the gate table never "
                         f"mentions them: {missing}. Add a row saying what "
                         f"each one proves -- no tool can write that.")

    def test_the_table_is_not_empty(self):
        """The two checks above both pass for a table that failed to
        parse, which is how a silent check dies here."""
        self.assertGreater(len(readme.table_rows(self.doc)), 20)
        self.assertGreater(len(readme.gates_in_make_test()), 20)

    def test_no_row_names_a_gate_that_is_gone(self):
        phony = readme.phony_targets()
        self.assertGreater(len(phony), 20, "the Makefile's .PHONY did not "
                                           "parse, so this proves nothing")
        gone = [g for g in readme.table_rows(self.doc) if g not in phony]
        self.assertEqual(gone, [],
                         f"the gate table has rows for targets that no "
                         f"longer exist: {gone}")

    def test_every_picture_it_shows_is_one_the_tour_writes(self):
        """A renumbered tour leaves the old file in place, and a stale
        picture RENDERS -- so the page goes on showing something that
        was true two releases ago rather than breaking visibly."""
        shots = readme.tour_shots()
        if shots is None:
            self.skipTest("docs/shots/MANIFEST is absent: run `make shots`")
        stale = [s for s in readme.readme_shots(self.doc) if s not in shots]
        self.assertEqual(stale, [],
                         f"README.md shows pictures `make shots` does not "
                         f"write: {stale}")

    def test_no_picture_is_left_behind(self):
        shots = readme.tour_shots()
        if shots is None:
            self.skipTest("docs/shots/MANIFEST is absent: run `make shots`")
        have = {f for f in os.listdir(readme.SHOTS) if f.endswith(".png")}
        self.assertEqual(sorted(have - set(shots)), [],
                         "these are checked in and the tour no longer writes "
                         "them; `make shots` names them as STALE")


if __name__ == "__main__":
    unittest.main()
