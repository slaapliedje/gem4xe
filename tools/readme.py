#!/usr/bin/env python3
"""README.md's facts, checked against the tree and written back into it.

    tools/readme.py --check     say what has drifted, and exit 1 if any
    tools/readme.py --write     put the facts back, and say what changed

WHY THIS EXISTS.  The README's gate table said `192/192` for a host
suite that collects 271 tests, and had no row at all for test-m33,
test-m34, test-m35 or test-m36 -- four gates `make test` had been
running for a whole release.  Nothing was wrong with the tree; the page
describing it had simply stopped keeping up, which is what a page
maintained by remembering does.

WHAT IT OWNS, and the line is deliberate: facts the tree can answer for
itself.  How many tests the host suite collects.  Which version this is.
Which gates exist, and whether the table mentions each one.  Which
pictures `make shots` writes, and whether the ones the README shows are
among them.

WHAT IT DOES NOT OWN: the prose.  The third column of that table is the
whole value of it -- what a gate actually proves and which bug it caught
-- and a generator that invented that would be worse than a stale
number, because a wrong number looks wrong and invented prose does not.
So a gate with no mention is an ERROR for a person to write a sentence
about, never a row this tool makes up.

THE CHECK MATTERS MORE THAN THE WRITE.  `make test-host` runs it, so the
drift above becomes a red gate on the commit that causes it rather than
something noticed while reading the page a release later.
"""
import argparse
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
MAKEFILE = os.path.join(ROOT, "Makefile")
VERSION = os.path.join(ROOT, "VERSION")
SHOTS = os.path.join(ROOT, "docs", "shots")

# The table runs from its header to the paragraph after it.  Found by
# the header rather than by a marker comment, so the page stays a page
# somebody can read and edit by hand.
TABLE_HEAD = "| Gate | | |\n|---|---|---|\n"


def read(path):
    with open(path, "r", errors="replace") as f:
        return f.read()


# ---- what the tree says -------------------------------------------------

def host_test_count():
    """What `make test-host` collects -- discovered, not run.

    countTestCases() on the discovered suite is the same number
    unittest's own "Ran N tests" prints, and asking for it costs no
    emulator and no tool chain.
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, "tests", "host"),
                            top_level_dir=os.path.join(ROOT, "tests", "host"))
    if loader.errors:
        raise SystemExit("tests/host does not import cleanly:\n  "
                         + "\n  ".join(str(e) for e in loader.errors))
    return suite.countTestCases()


def version():
    return read(VERSION).strip()


def compiler_defects():
    """How many compiler bug shapes tools/ccbug knows about.

    Counted the way `make check-cc` counts them, but from the TABLES
    rather than from a run -- the tables are module-level data and the
    run needs a tool chain this check must not require.  The README said
    "sixteen" for a good while after there were more; the number a
    person remembers and the number in the table are two different
    things, and only one of them is maintained by adding a bug.
    """
    sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
    import check                                  # noqa: E402
    return (sum(1 for v in check.RESULTS.values() if v[1] == "bug")
            + len(check.CRASHES) + len(check.LISTINGS) + len(check.LINKS)
            + len(check.REFUSALS) + len(check.HANGS))


def gates_in_make_test():
    """The gates `make test` runs, in the order the Makefile lists them."""
    m = re.search(r"^test:\s*(.*)$", read(MAKEFILE), re.M)
    if not m:
        raise SystemExit("the Makefile has no `test:` target")
    return [w for w in m.group(1).split()
            if w.startswith("test-") or w == "check-cc"]


def phony_targets():
    m = re.search(r"^\.PHONY:\s*(.*)$", read(MAKEFILE), re.M)
    return set(m.group(1).split()) if m else set()


def tour_shots():
    """The pictures `make shots` wrote, by name, in tour order -- or None
    if the tour has not run in this tree.

    OUT OF THE TOUR'S OWN MANIFEST, not out of its source.  The names
    are numbered by the order the shots happen in and one of them is not
    a literal at all (the accessory loop names its shot after the
    accessory), so reading shots.py would have to execute it to get the
    list right.  A first attempt did read the source, found nothing, and
    cheerfully reported every picture in the tree as an orphan -- which
    is the shape of a check that is confidently wrong rather than
    silent, and the reason this asks the thing that knows.
    """
    p = os.path.join(SHOTS, "MANIFEST")
    if not os.path.exists(p):
        return None
    return [ln.strip() for ln in read(p).splitlines()
            if ln.strip() and not ln.startswith("#")]


# ---- what the README says -----------------------------------------------

def table(doc):
    i = doc.index(TABLE_HEAD)
    j = doc.index("\n\n", i)
    return doc[i + len(TABLE_HEAD):j]


def table_mentions(doc):
    """Every `test-*` / `check-cc` the gate table names ANYWHERE -- as a
    row of its own or inside another row's prose.

    Both count, and that is not a loophole.  test-m15x and test-m15d are
    named in the middle of test-m15's sentence because they are the same
    gate on two other disks, and giving them rows would say less than
    the sentence does.  What matters is that a gate is not INVISIBLE.
    """
    return set(re.findall(r"\b(test-[a-z0-9-]+|check-cc)\b", table(doc)))


def table_rows(doc):
    """The gate each row is FOR: the first target in its first cell."""
    out = []
    for line in table(doc).splitlines():
        m = re.match(r"\|\s*`make ([a-z0-9-]+)`", line)
        if m:
            out.append(m.group(1))
    return out


def readme_shots(doc):
    return re.findall(r"docs/shots/([0-9a-z-]+\.png)", doc)


# ---- the facts, and putting them back -----------------------------------

def facts(doc):
    """Every (what, found, wanted, fix) the page states and the tree can
    answer.  `fix` rewrites the whole document."""
    out = []

    n = host_test_count()
    m = re.search(r"^\| `make test-host` \| (\d+)/(\d+) \|", doc, re.M)
    if m:
        out.append(("the host suite count", f"{m.group(1)}/{m.group(2)}",
                    f"{n}/{n}",
                    lambda d, n=n, m=m: d[:m.start(1)] + f"{n}/{n}"
                    + d[m.end(2):]))

    v = version()
    m = re.search(r"^Current version \*\*([^*]+)\*\*", doc, re.M)
    if m:
        out.append(("the version", m.group(1), v,
                    lambda d, v=v, m=m: d[:m.start(1)] + v + d[m.end(1):]))

    c = compiler_defects()
    m = re.search(r"has \*\*(\d+) defects\*\* this tree has met", doc)
    if m:
        out.append(("the compiler defect count", m.group(1), str(c),
                    lambda d, c=c, m=m: d[:m.start(1)] + str(c)
                    + d[m.end(1):]))

    return out


def problems(doc):
    """What a person has to fix, because no tool should invent it."""
    out = []

    mentioned = table_mentions(doc)
    for g in gates_in_make_test():
        if g not in mentioned:
            out.append(f"`make test` runs {g} and the gate table never "
                       f"mentions it -- add a row saying what it proves")

    phony = phony_targets()
    for g in table_rows(doc):
        if g not in phony:
            out.append(f"the gate table has a row for `make {g}`, which is "
                       f"not a target any more -- has it been renamed?")

    shots = tour_shots()
    if shots is None:
        # Said out loud rather than passed over.  A check that goes quiet
        # when its input is missing is one this tree has been caught by
        # twice, so the absence is reported even though it is not a fault.
        out.append("docs/shots/MANIFEST is not there, so nothing is known "
                   "about the pictures -- run `make shots` (NOT a failure "
                   "of the README, but this check is blind until then)")
        return out

    written = set(shots)
    for s in readme_shots(doc):
        if s not in written:
            out.append(f"the README shows docs/shots/{s}, which `make shots` "
                       f"does not write -- the tour renumbered")
    for s in sorted(set(os.listdir(SHOTS)) - written):
        if s.endswith(".png"):
            out.append(f"docs/shots/{s} is checked in and the tour no longer "
                       f"writes it -- a stale picture renders, so it is worse "
                       f"than a broken link")

    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="put the facts back into README.md")
    ap.add_argument("--check", action="store_true",
                    help="say what has drifted; exit 1 if anything has")
    a = ap.parse_args(argv[1:])
    if not (a.write or a.check):
        ap.error("say --check or --write")

    doc = read(README)
    stale = [f for f in facts(doc) if f[1] != f[2]]
    hard = problems(doc)

    for what, found, want, _fix in stale:
        print(f"  {what}: the README says {found}, the tree says {want}")
    for p in hard:
        print(f"  {p}")

    if a.write:
        for _what, _found, _want, fix in stale:
            doc = fix(doc)
        if stale:
            with open(README, "w") as f:
                f.write(doc)
            print(f"README.md: {len(stale)} fact(s) put back")
        else:
            print("README.md: the facts were already right")
        if hard:
            print(f"\n{len(hard)} thing(s) above need a person: this writes "
                  f"numbers, never prose.")
        return 1 if hard else 0

    n = len(stale) + len(hard)
    print(f"readme: {'ok' if not n else f'{n} stale'}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
