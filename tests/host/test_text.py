#!/usr/bin/env python3
"""Host test for the ANTIC device's string-at-once text (src/antic/antic.c,
antic_text).

v_gtext on the ANTIC screen hands the device the run of a string's cells
that are wholly visible, and the device draws the whole run a row at a
time instead of a glyph at a time (docs/phase54.md).  The pixels must be
exactly the ones antic_glyph drew cell by cell -- in every writing mode,
with both pens, at every alignment, for runs of one cell (a lone glyph),
a few, and a whole row, over random screen bytes and a font whose unused
columns are random too.  tests/host/text_sim.c does both and compares, in
the compiler's own simulator at the product's flags.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
ANTIC_C = os.path.join(ROOT, "src", "antic", "antic.c")
SIM_C = os.path.join(ROOT, "tests", "host", "text_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug                      # noqa: E402  (the simulator driver)

CASES = 4 * 2 * 8 * 3                       # text_sim.c


class TestTextRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "textsim")
        os.makedirs(out, exist_ok=True)
        objs = []
        for src in (ANTIC_C, SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "text.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        cls.v = ccbug.simulate(db, elf, ["ts_cases", "ts_bad", "ts_first",
                                         "ts_first_x", "ts_first_n",
                                         "ts_first_mode", "ts_first_w"])

    def test_every_case_ran(self):
        self.assertEqual(self.v["ts_cases"], CASES)

    def test_a_run_is_its_glyphs(self):
        v = self.v
        self.assertEqual(v["ts_bad"], 0,
                         f"{v['ts_bad']} of {CASES} runs differ; the first is "
                         f"case {v['ts_first']}: x {v['ts_first_x']}, "
                         f"{v['ts_first_n']} cells {v['ts_first_w']} wide, "
                         f"mode {v['ts_first_mode']}")


if __name__ == "__main__":
    unittest.main()
