#!/usr/bin/env python3
"""The kit's ST compatibility layer (src/app/gemcompat.c).

WHY THE KIT CARRIES THIS.  qed -- 37 files of real ST application -- had
to write opendir/readdir/closedir and the non-ISO string functions in its
own port shim before they were here, and so would every port after it.
An SDK whose job is "an ST developer recompiles rather than rewrites"
should hand them over.

Compiled by the REAL compiler and run under Calypsi's simulator, with the
four GEMDOS calls stubbed in tests/host/compat_sim.c.  Stubbing them is
not a weakness here: what goes wrong in a directory walk is the search
spec built from the caller's path, the caller's DTA not being put back,
two walks losing each other's place, and a pool running out -- and a run
against a real disk shows none of those as clearly as a fake one can.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CALYPSI = os.environ.get("CALYPSI", os.path.expanduser("~/dev/toolchains/calypsi-65816"))
GEMCOMPAT_C = os.path.join(ROOT, "src", "app", "gemcompat.c")
COMPAT_SIM_C = os.path.join(ROOT, "tests", "host", "compat_sim.c")


class TestGemCompat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "gemcompat")
        os.makedirs(out, exist_ok=True)
        objs = []
        for src in (GEMCOMPAT_C, COMPAT_SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"),
                            "-I", os.path.join(ROOT, "src", "app"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "gemcompat.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        names = ["csim_ran", "csim_spec_plain", "csim_spec_slash",
                 "csim_spec_drive", "csim_names", "csim_count",
                 "csim_dta_restored", "csim_a3", "csim_b1", "csim_pool_full",
                 "csim_pool_reuse", "csim_missing_null", "csim_empty_ok",
                 "csim_empty_read", "csim_close_twice", "csim_stricmp",
                 "csim_stricmp_ne", "csim_strnicmp", "csim_lwr", "csim_upr"]
        script = "run\n" + "".join(f"print {n}\n" for n in names) + "quit\n"
        p = subprocess.run([db, "--nh", "--nx", "--exit-breakpoint", elf],
                           input=script, capture_output=True, text=True,
                           timeout=180)
        txt = p.stdout + p.stderr
        # db65816 prints an array as a multi-line block, so slice between
        # the `$n = ` markers rather than reading line by line.
        marks = list(re.finditer(r"\$\d+ = ", txt))
        vals = [txt[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(txt))]
                for i, m in enumerate(marks)]
        if len(vals) < len(names):
            raise AssertionError(f"the simulator said too little:\n{txt[-2000:]}")
        cls.by = dict(zip(names, vals))

    def num(self, key):
        return int(re.search(r"(-?\d+)", self.by[key]).group(1))

    def text(self, key):
        """A char array, however the debugger chose to print it."""
        m = re.search(r'"((?:[^"\\]|\\.)*)"', self.by[key])
        if m:
            return m.group(1)
        out = ""
        for c in (int(v) for v in re.findall(r"=\s*(-?\d+)", self.by[key])):
            if c == 0:
                break
            out += chr(c & 0xFF)
        return out

    def texts(self, key):
        """csim_names: an array OF arrays, flattened by the debugger."""
        bytes_ = [int(v) & 0xFF for v in re.findall(r"=\s*(-?\d+)", self.by[key])]
        out, i = [], 0
        while i + 14 <= len(bytes_):
            row = bytes_[i:i + 14]
            s = ""
            for c in row:
                if c == 0:
                    break
                s += chr(c)
            out.append(s)
            i += 14
        return out

    def test_it_ran(self):
        self.assertEqual(self.num("csim_ran"), 1, "the program did not finish")

    def test_the_search_spec_is_built_from_the_path(self):
        """The separator is added when it is needed and not when it is
        not -- `A:` already ends in one, `A:\\SUB\\` has one."""
        self.assertEqual(self.text("csim_spec_plain"), "A:\\SUB\\*.*")
        self.assertEqual(self.text("csim_spec_slash"), "A:\\SUB\\*.*")
        self.assertEqual(self.text("csim_spec_drive"), "A:*.*")

    def test_every_name_comes_back_once_and_in_order(self):
        self.assertEqual(self.num("csim_count"), 5)
        self.assertEqual(self.texts("csim_names")[:5],
                         ["AUTOEXEC.BAT", "GEM.COM", "QED.RSC", "SUB", "X32G.DOS"])

    def test_the_callers_dta_is_put_back(self):
        """A walk here must not break a walk somewhere else -- the file
        selector's, or cflib's fsexists."""
        self.assertEqual(self.num("csim_dta_restored"), 1,
                         "opendir/readdir left its own DTA set")

    def test_two_walks_keep_their_own_places(self):
        """d has yielded entries 0 and 1, e none.  Then e must yield its
        own entry 0 and d must carry on at entry 2 -- if the two shared a
        search, d would restart or e would skip."""
        self.assertEqual(self.text("csim_b1"), "AUTOEXEC.BAT")   # e's first
        self.assertEqual(self.text("csim_a3"), "QED.RSC")        # d's third

    def test_the_pool_runs_out_and_a_close_refills_it(self):
        self.assertEqual(self.num("csim_pool_full"), 1,
                         "a DIRENT_MAX+1'th opendir should answer NULL")
        self.assertEqual(self.num("csim_pool_reuse"), 1,
                         "closedir should give the slot back")

    def test_a_path_that_names_nothing_is_null(self):
        self.assertEqual(self.num("csim_missing_null"), 1)

    def test_an_empty_directory_still_opens(self):
        """ENMFIL from Fsfirst means "no entries", not "no directory"."""
        self.assertEqual(self.num("csim_empty_ok"), 1,
                         "an empty directory must open")
        self.assertEqual(self.num("csim_empty_read"), 1,
                         "...and read as nothing")

    def test_closing_twice_is_an_error(self):
        self.assertEqual(self.num("csim_close_twice"), 1)

    def test_the_non_iso_string_functions(self):
        self.assertEqual(self.num("csim_stricmp"), 1, "stricmp ignores case")
        self.assertEqual(self.num("csim_stricmp_ne"), 1, "...and still orders")
        self.assertEqual(self.num("csim_strnicmp"), 1, "strnicmp honours n")
        self.assertEqual(self.text("csim_lwr"), "mixed.txt")
        self.assertEqual(self.text("csim_upr"), "MIXED.TXT")


if __name__ == "__main__":
    unittest.main()
