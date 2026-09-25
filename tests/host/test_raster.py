#!/usr/bin/env python3
"""Host test for the ANTIC device's byte-wise raster (src/antic/antic.c,
antic_raster_row).

vrt_cpyfm on the ANTIC screen -- every icon on the desk -- used to be
drawn pixel by pixel through antic_plot, each pixel a call and a read and
a write on the 1.79 MHz bus.  It is drawn a byte at a time now
(docs/phase52.md), which is an optimisation of the kind that is right for
every case anybody looks at and wrong at one alignment nobody did.

So it is driven here, in the compiler's own simulator, through every
destination alignment, every source alignment and every writing mode
(256 rows, the pens cycling), and four runs across the whole screen --
and each row is
compared byte for byte with the same row worked out one pixel at a time
by the VDI's rules (tests/host/raster_sim.c).  The bytes either side of
the run must not move.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
ANTIC_C = os.path.join(ROOT, "src", "antic", "antic.c")
SIM_C = os.path.join(ROOT, "tests", "host", "raster_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug                      # noqa: E402  (the simulator driver)

CASES = 256 + 4                             # raster_sim.c: ALIGNED + LONG


class TestRasterRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "raster")
        os.makedirs(out, exist_ok=True)
        objs = []
        # the product's own flags for this file (Makefile): large code,
        # small data, -O2 -- a raster that is right at -O0 proves little
        for src in (ANTIC_C, SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "raster.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        cls.v = ccbug.simulate(db, elf, ["rr_cases", "rr_bad", "rr_first",
                                         "rr_first_x1", "rr_first_x2",
                                         "rr_first_mode", "rr_first_sbit"])

    def test_every_case_ran(self):
        self.assertEqual(self.v["rr_cases"], CASES)

    def test_every_row_matches_the_pixel_rules(self):
        v = self.v
        self.assertEqual(v["rr_bad"], 0,
                         f"{v['rr_bad']} of {CASES} rows differ; the first is "
                         f"case {v['rr_first']}: x {v['rr_first_x1']}..{v['rr_first_x2']}, "
                         f"mode {v['rr_first_mode']}, source bit {v['rr_first_sbit']}")


if __name__ == "__main__":
    unittest.main()
