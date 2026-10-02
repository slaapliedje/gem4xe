"""src/sys/muldiv.s in the vendor's simulator: umuldiv against Python,
flit_scan against the C it replaced.

tests/host/muldiv_sim.c calls umuldiv(a, b, c) = floor(a * b / c) under
its contract -- c not zero, a <= c, as clc_flit calls it -- on edge values
and on pseudo-random triples, folds the quotients into a checksum and
keeps the first eight whole.  This computes the same from the same
generator.  It then holds flit_scan, the polygon filler's scan line, to
flit_ref, the same loop in C, on random polygons and on one that crosses
a line more often than MAX_INTERSECT allows.  m3's polygon and curve cases
check the whole filler against tools/vdiref.py (docs/phase93.md).
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
MULDIV_S = os.path.join(ROOT, "src", "sys", "muldiv.s")
SIM_C = os.path.join(ROOT, "tests", "host", "muldiv_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug                      # noqa: E402  (the simulator driver)

N = 3000
EDGE_C = [1, 2, 3, 255, 256, 32766, 32767, 65535]
EDGE_B = [0, 1, 2, 12345, 32768, 65532, 65535]
M = 0xffffffff


def expected():
    """What muldiv_sim.c computes, computed here: (sum, first eight, n)."""
    xs = [0x2545f491]

    def nxt():
        x = xs[0]
        x ^= (x << 13) & M
        x ^= x >> 17
        x ^= (x << 5) & M
        xs[0] = x
        return x

    out = []
    for c in EDGE_C:
        for b in EDGE_B:
            for a in (0, 1, c // 2, c - 1, c):
                out.append(a * b // c)
    for _ in range(N):
        c = nxt() & 0xffff
        if nxt() % 3 == 0:
            c &= 0xff
        c = c or 1
        b = nxt() & 0xffff
        a = nxt() & 0xffff
        if c != 0xffff:
            a %= c + 1
        out.append(a * b // c)
    s = 0
    for q in out:
        s = (((s << 7) | (s >> 25)) & M) ^ q
    return s, out[:8], len(out)


class Muldiv(unittest.TestCase):
    def test_against_python(self):
        cc, asm, ld, db = (os.path.join(CALYPSI, "bin", t)
                           for t in ("cc65816", "as65816", "ln65816", "db65816"))
        if not os.path.exists(cc):
            self.skipTest("Calypsi not installed")
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        with tempfile.TemporaryDirectory() as d:
            obj, mobj, elf = (os.path.join(d, f) for f in
                              ("sim.o", "muldiv.o", "sim.elf"))
            subprocess.run([cc, "-g", "--code-model=large",
                            "--data-model=small", "-O2", "-o", obj, SIM_C],
                           check=True, capture_output=True)
            subprocess.run([asm, "-o", mobj, MULDIV_S], check=True,
                           capture_output=True)
            subprocess.run([ld, "-g", scm, obj, mobj, "-o", elf,
                            "clib-lc-sd.a", "--rtattr", "exit=simplified"],
                           check=True, capture_output=True)
            names = (["md_sum", "md_count", "fl_bad", "fl_rows", "fl_hits"]
                     + [f"md_first[{i}]" for i in range(8)])
            got = ccbug.simulate(db, elf, names)
        s, first, n = expected()
        self.assertEqual(got["md_count"] & 0xffff, n & 0xffff)
        self.assertEqual([got[f"md_first[{i}]"] & 0xffff for i in range(8)],
                         first)
        self.assertEqual(got["md_sum"] & M, s, f"the checksum of {n} quotients")
        rows = 60 * 24 + len(range(40, 160, 7))
        self.assertEqual(got["fl_rows"] & 0xffff, rows)
        self.assertGreater(got["fl_hits"] & 0xffff, rows,
                           "the polygons crossed too few lines to test")
        self.assertEqual(got["fl_bad"] & 0xffff, 0,
                         "scan lines where flit_scan and flit_ref differ")

    def test_max_intersect_is_vdi_cs(self):
        """muldiv.s carries vdi.c's MAX_INTERSECT; they must agree."""
        with open(MULDIV_S) as f:
            asm = re.search(r"^MAX_INTERSECT\s+\.equ\s+(\d+)", f.read(), re.M)
        with open(os.path.join(ROOT, "src", "vdi", "vdi.c")) as f:
            c = re.search(r"^#define MAX_INTERSECT (\d+)", f.read(), re.M)
        with open(SIM_C) as f:
            sim = re.search(r"^#define MAX_INTERSECT (\d+)", f.read(), re.M)
        self.assertEqual(asm.group(1), c.group(1))
        self.assertEqual(sim.group(1), c.group(1))


if __name__ == "__main__":
    unittest.main()
