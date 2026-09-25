#!/usr/bin/env python3
"""Host test for the ANTIC device's whole-rectangle fill (src/antic/antic.c,
antic_fill_rect).

A rectangle on the ANTIC screen used to be one span a row, and each span
set itself up again; it is one call now, and the covered middle of each
row is a plain store where the op allows (docs/phase55.md).  The pixels
must be the ones the spans drew -- every mode, both pens, solid and
patterned, every edge alignment, both parities of the first byte, and
rectangles hanging off every edge.  tests/host/rect_sim.c does both and
compares, in the compiler's own simulator at the product's flags.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
ANTIC_C = os.path.join(ROOT, "src", "antic", "antic.c")
SIM_C = os.path.join(ROOT, "tests", "host", "rect_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug                      # noqa: E402  (the simulator driver)

CASES = 4 * 2 * 2 * 8 * 4                   # rect_sim.c


class TestFillRect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "rectsim")
        os.makedirs(out, exist_ok=True)
        objs = []
        for src in (ANTIC_C, SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "rect.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        cls.v = ccbug.simulate(db, elf, ["rs_cases", "rs_bad", "rs_first",
                                         "rs_first_x1", "rs_first_x2",
                                         "rs_first_mode", "rs_first_patt"])

    def test_every_case_ran(self):
        self.assertEqual(self.v["rs_cases"], CASES)

    def test_a_rectangle_is_its_spans(self):
        v = self.v
        self.assertEqual(v["rs_bad"], 0,
                         f"{v['rs_bad']} of {CASES} rectangles differ; the first is "
                         f"case {v['rs_first']}: x {v['rs_first_x1']}..{v['rs_first_x2']}, "
                         f"mode {v['rs_first_mode']}, patterned {v['rs_first_patt']}")


if __name__ == "__main__":
    unittest.main()
