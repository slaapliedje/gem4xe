"""Every desk accessory the build makes must be on the product media.

WHY THIS EXISTS.  On 2026-09-20 CONTROL.ACC and CALC.ACC were built for
the card and the applications floppy and never copied onto either.  The
Makefile listed them in ACCP_DEPS, which is a PREREQUISITE -- it makes
them exist before the disk is written -- and `tools/mkcf.py`'s APPS
table, which is what actually gets copied, still named only the clock.
A prerequisite that is never used looks exactly like a prerequisite that
is, so the disk built green and shipped without them.

THE TWO LISTS ARE IN DIFFERENT LANGUAGES, which is the whole problem:
one is make syntax and one is Python, nothing reads both, and the only
thing that noticed was a person listing the floppy by hand.  This reads
both.

WHY test-install IS NOT THIS CHECK.  It boots the installed drive and
counts processes, and the count is a literal (4).  That catches an
accessory going MISSING from the media; it cannot catch a FOURTH one
being added to the build and not to the media, because the literal would
have to be updated for the new one anyway and updating it is the step
that gets forgotten.  This check needs no number.

\\GEM\\ AND NOT \\APPS\\ is asserted too: the AES scans the system
directory for *.ACC (src/aes/shel.c), so an accessory installed beside
the programs is not found and not loaded, which is a silent failure of
exactly the same shape.
"""
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mkcf                                             # noqa: E402


def accp_deps():
    """The build/ paths in the Makefile's ACCP_DEPS, continuations joined."""
    with open(os.path.join(ROOT, "Makefile"), "r", errors="replace") as f:
        text = f.read()
    m = re.search(r"^ACCP_DEPS\s*=\s*((?:[^\n\\]*\\\n)*[^\n]*)", text, re.M)
    assert m, "the Makefile has no ACCP_DEPS -- has it been renamed?"
    return set(m.group(1).replace("\\\n", " ").split())


class AccessoriesShip(unittest.TestCase):
    def setUp(self):
        self.deps = accp_deps()
        # A source may be carried to MORE THAN ONE destination -- calc.rsc
        # ships as both GEM>CALC.RSC and APPS>CALC.RSC, because \GEM\ and
        # \APPS\ install separately and either may be the only one there.
        # So this is a set per source, not one destination: a dict that
        # kept the last would hide the copy that matters.
        self.carried = {}
        for src, dst in mkcf.APPS:
            self.carried.setdefault(src, set()).add(dst)

    def test_accp_deps_is_not_empty(self):
        """The regex above could match nothing and pass every other test
        by having no accessories to check.  It has done that once in this
        tree, in another file, which is why it is asserted here."""
        self.assertGreaterEqual(len(self.deps), 2, self.deps)
        self.assertTrue(any(d.endswith("acc.g4a") for d in self.deps),
                        f"no accessory binary in ACCP_DEPS: {self.deps}")

    def test_every_built_accessory_is_on_the_media(self):
        missing = sorted(self.deps - set(self.carried))
        self.assertEqual(missing, [],
                         "the Makefile builds these for the product media and "
                         "tools/mkcf.py's APPS table never copies them:\n  "
                         + "\n  ".join(missing)
                         + "\n\nAdd each to APPS with its destination. An "
                           "accessory binary goes to GEM>NAME.ACC and its "
                           "resource beside it; see the CONTROL.ACC entries.")

    def test_accessories_land_in_the_system_directory(self):
        """\\GEM\\, because that is where the AES looks for *.ACC."""
        for src, dsts in self.carried.items():
            if not src.endswith("acc.g4a"):
                continue
            self.assertTrue(
                any(d.startswith("GEM>") and d.endswith(".ACC") for d in dsts),
                f"{src} is installed as {sorted(dsts)}; an accessory must be "
                f"GEM>NAME.ACC or the AES never scans it")

    def test_every_accessory_has_its_own_resource_beside_it(self):
        """An .ACC whose .RSC did not ship comes up and finds nothing --
        which happened to CALC.ACC once, and produced a picture that was
        wrong rather than an error.

        The pairing is NOT by installed name: CONTROL.ACC's resource is
        CPANEL.RSC, because an accessory is named for what it does and a
        resource for the source it is built from.  It is by BUILD name --
        build/<x>acc.g4a is built from src/apps/<x>.c and takes
        build/<x>.rsc -- which is the relationship the Makefile's own
        rules have, so this asks the question the build answers."""
        for dep in sorted(self.deps):
            base = os.path.basename(dep)
            if not base.endswith("acc.g4a"):
                continue
            want = f"build/{base[:-len('acc.g4a')]}.rsc"
            self.assertIn(want, self.carried,
                          f"{dep} ships but its resource {want} does not; "
                          f"the accessory will come up and find nothing")
            self.assertTrue(
                any(d.startswith("GEM>") for d in self.carried[want]),
                f"{want} is installed only as {sorted(self.carried[want])}, "
                f"not in \\GEM\\ beside the accessory that rsrc_load's bare "
                f"name resolves against")


if __name__ == "__main__":
    unittest.main()
