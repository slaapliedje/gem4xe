"""No C file but the two seams may name the compiler.

WHAT THIS PROTECTS.  gem4xe's 35,000 lines of C contain no Calypsi
syntax at all.  Every address-space qualifier, calling convention and
attribute the '816 needs goes through ONE header -- `FAR`, `NEAR`,
`TINY`, `SIMPLE_CALL`, `TASK`, `SECTION`, `memcpy_far` in src/portab.h,
about fifty lines -- so what ties this tree to a toolchain is the 2,480
lines of assembly and linker map under src/, which is the board support
and is SUPPOSED to be tied.  The engine is not.

That is worth something concrete: it is why the tree could be measured
against 816-tcc and ORCA/C at all, and it is what a second compiler
would cost -- a BSP, not a rewrite.

IT IS ALSO A PROPERTY NOBODY WAS CHECKING.  It is true today because it
was written that way one file at a time, and a single `__far` in a new
file would end it quietly: the build would be perfectly happy, and the
fact would only be discovered by somebody trying to port and finding it
was no longer true.  A property that holds by habit holds until the
habit lapses.

WHAT IS ALLOWED.  The two seams below, each of which exists to name the
compiler.  Comments anywhere: the tree explains WHY a shape is what it
is, and naming `__huge` in a sentence about why a buffer must not
straddle a bank is documentation, not a dependency.  And the .s and .scm
files, which are the toolchain's own languages.

This does NOT claim the tree would compile elsewhere unchanged.  The
data models are a design assumption, not a spelling: a compiler with one
pointer width would build this and make every pointer 32 bits, which is
correct and costly.  What it claims is narrower and checkable -- that
the C never says the compiler's name.
"""
import os
import re
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SRC = os.path.join(ROOT, "src")

# THE SEAMS.  Two files may name the compiler, and each is an adapter
# whose entire job is to name it -- which is the point: the tie is two
# files you could rewrite, not a spelling spread through the engine.
#
#   src/portab.h     the address-space and calling-convention macros.
#   src/app/gemstub.c  the nine routines Calypsi's C library asks the
#                    BOARD to provide (calypsi/stubs.h), answered over
#                    GEMDOS.  It cannot avoid the include: implementing
#                    that header is what the file IS.
#
# Anything else added here should be argued for in the commit, not just
# listed -- a third seam is a real change to how tied the tree is.
SEAMS = {
    os.path.join("src", "portab.h"),
    os.path.join("src", "app", "gemstub.c"),
}

# Calypsi spellings that must not appear in a C declaration anywhere else.
VENDOR = re.compile(r"__(?:far|near|huge|tiny|simple_call|task|attribute__"
                    r"|memcpy_far)\b|\bcalypsi/")


def strip_comments(text):
    """Code only.  A comment may name the compiler; a declaration may not."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def offenders(root=None, base=None):
    """Every (file, line, spelling) in `root` that names the compiler.

    `root` and `base` are parameters so that test_it_can_fail can point
    the REAL walk at a tree it has broken on purpose, rather than
    re-testing the regex on its own -- a check whose failing case does
    not exercise the same code as its passing case has not been shown
    to fail."""
    SRC_ = root or SRC
    ROOT_ = base or ROOT
    out = []
    for dirpath, _, names in os.walk(SRC_):
        for name in sorted(names):
            if not name.endswith((".c", ".h")):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, ROOT_)
            if rel in SEAMS:
                continue
            with open(path, "r", errors="replace") as f:
                code = strip_comments(f.read())
            for n, line in enumerate(code.split("\n"), 1):
                m = VENDOR.search(line)
                if m:
                    out.append((rel, n, m.group(0), line.strip()[:70]))
    return out


class Portab(unittest.TestCase):
    def test_the_c_never_names_the_compiler(self):
        bad = offenders()
        self.assertEqual(
            bad, [],
            "these say Calypsi in C code rather than going through "
            "src/portab.h:\n  "
            + "\n  ".join(f"{f}:{n}: {w} -- {ln}" for f, n, w, ln in bad)
            + "\n\nUse the macro from src/portab.h (FAR, NEAR, TINY, "
              "SIMPLE_CALL, TASK, SECTION, memcpy_far), or add one there "
              "if the spelling you need has none yet.")

    def test_the_scan_reaches_the_tree(self):
        """A regex that matched nothing would pass the test above by
        looking at nothing.  This tree has shipped a vacuous check twice,
        so the scan says how much it read."""
        seen = sum(1 for dp, _, ns in os.walk(SRC) for n in ns
                   if n.endswith((".c", ".h")))
        self.assertGreater(seen, 100, f"only {seen} C files found under src/")

    def test_the_seam_really_is_the_seam(self):
        """...and it is only worth exempting one file if that file is
        where the spellings actually live."""
        seam = os.path.join(ROOT, "src", "portab.h")
        with open(seam, "r", errors="replace") as f:
            text = f.read()
        for macro in ("FAR", "NEAR", "TINY", "SIMPLE_CALL"):
            self.assertRegex(text, rf"#define\s+{macro}\b",
                             f"src/portab.h no longer defines {macro}")

    def test_it_can_fail(self):
        """Put a raw qualifier into a copy of a REAL file, in a tree of
        its own, and require the same walk that passes above to name it."""
        with open(os.path.join(SRC, "aes", "objc.c"), "r",
                  errors="replace") as f:
            text = f.read()
        with tempfile.TemporaryDirectory() as d:
            aes = os.path.join(d, "src", "aes")
            os.makedirs(aes)
            with open(os.path.join(aes, "objc.c"), "w") as f:
                f.write(text + "\nstatic __far char *probe;\n")
            bad = offenders(root=os.path.join(d, "src"), base=d)
        self.assertEqual([(f, w) for f, n, w, ln in bad],
                         [(os.path.join("src", "aes", "objc.c"), "__far")],
                         f"the walk did not report the planted __far: {bad}")

    def test_a_comment_is_not_a_dependency(self):
        """farmem.c explains __huge in prose and must stay legal, or the
        check would push the tree towards documenting itself less."""
        with tempfile.TemporaryDirectory() as d:
            sysd = os.path.join(d, "src", "sys")
            os.makedirs(sysd)
            with open(os.path.join(sysd, "x.c"), "w") as f:
                f.write("/* what __huge is for: a buffer that straddles */\n"
                        "int n;  // and __far here too\n")
            self.assertEqual(offenders(root=os.path.join(d, "src"), base=d), [])


if __name__ == "__main__":
    unittest.main()
