"""The hand-written guides name only what is there.

docs/api.md, docs/guide.md and the README's numbers are generated, and
their own tests regenerate them.  The guides a person writes -- the
README, docs/developing.md, docs/differences.md -- cannot be generated,
but what they POINT AT can be checked: every repository path in
backticks, every relative link, and every `make` target they tell a
reader to run must exist.  A rename that leaves a guide behind fails here
instead of sending somebody to a file that is gone.  (Phase 91, which
found a page saying "320 x 168" two phases after the screen became
192 lines tall: what a sentence CLAIMS is a person's to keep, but where
it points is not.)
"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

GUIDES = ("README.md", "docs/developing.md", "docs/differences.md")
PATH = re.compile(r"`((?:src|tools|tests|docs|dist)/[A-Za-z0-9_./-]*)`")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
# a named target; one with a path in it (`make build/x.atr`, or another
# tree's file) is a file, which is not this check's business
MAKE = re.compile(r"`make ([a-z0-9][a-z0-9-]*)(?![/.\w])")


def targets():
    """Every target the Makefile defines: its rules, and .PHONY's."""
    with open(os.path.join(ROOT, "Makefile")) as f:
        mk = f.read()
    out = set(re.findall(r"^([a-z0-9][a-z0-9-]*)\s*:(?!=)", mk, re.M))
    for line in re.findall(r"^\.PHONY:(.*)$", mk, re.M):
        out |= set(line.split())
    return out


def broken(text, where, known):
    """What `text`, the page at `where` (relative to the root), names that
    is not there: (kind, name)."""
    out = []
    for p in PATH.findall(text):
        if not os.path.exists(os.path.join(ROOT, p.rstrip("/"))):
            out.append(("path", p))
    base = os.path.dirname(where)
    for link in LINK.findall(text):
        if re.match(r"[a-z]+:", link):          # http:, mailto:
            continue
        if not os.path.exists(os.path.normpath(os.path.join(ROOT, base, link))):
            out.append(("link", link))
    for t in MAKE.findall(text):
        if t not in known:
            out.append(("make target", t))
    return out


class Guides(unittest.TestCase):
    def test_everything_a_guide_names_is_there(self):
        known = targets()
        self.assertGreater(len(known), 50, "the Makefile did not parse")
        for g in GUIDES:
            with self.subTest(guide=g):
                with open(os.path.join(ROOT, g)) as f:
                    text = f.read()
                self.assertEqual(broken(text, g, known), [],
                                 f"{g} names what is not in the tree")

    def test_they_name_things_at_all(self):
        """A pattern that stopped matching would pass the test above by
        finding nothing; each guide must point at something."""
        for g in GUIDES:
            with open(os.path.join(ROOT, g)) as f:
                text = f.read()
            self.assertTrue(PATH.findall(text) or LINK.findall(text), g)

    def test_the_check_speaks(self):
        text = ("See `src/aes/no_such_file.c`, [this](nowhere.md), "
                "`make no-such-target`, and `src/aes/wind.c` which is there.")
        got = broken(text, "docs/x.md", targets())
        self.assertEqual(got, [("path", "src/aes/no_such_file.c"),
                               ("link", "nowhere.md"),
                               ("make target", "no-such-target")])


if __name__ == "__main__":
    unittest.main()
