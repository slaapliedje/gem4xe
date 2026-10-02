"""src/sys/mul32.s against the library's _Mul32 and against Python.

tests/host/mul32_sim.c folds 8,400 products -- the edge cases, and
pseudo-random pairs made without a multiply, a third of them 16-bit and a
third 8-bit so every path through the routine is taken -- into a
checksum, and keeps the first eight whole.  It is linked twice and run in
the vendor's simulator: once with the library's _Mul32 and once with
ours (`--override _Mul32`, as the Makefile links it).  Both must equal
what Python computes from the same generator, which is the third view:
two 65816 routines that agreed on a wrong answer would not pass.

The table, f(n) = floor(n * n / 4) for n = 0..510, is made by the
routine's first call in the program's far variables (`zfar`); the vendor's
example link has none, so this one adds a bank for them, and
test_the_table reads back what was made.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
MUL32_S = os.path.join(ROOT, "src", "sys", "mul32.s")
SIM_C = os.path.join(ROOT, "tests", "host", "mul32_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug                      # noqa: E402  (the simulator driver)

N = 4000
EDGE = [0, 1, -1, 2, 255, 256, 65535, 65536, 65537, 0x7fffffff,
        -0x80000000, -65536, -65535, 0x12345678, -0x12345678,
        0x00ff00ff, 0x0100ff01, 46341, -46341, 0xffff * 3]
M = 0xffffffff


def expected():
    """What mul32_sim.c computes, computed here: (sum, first eight)."""
    xs = [0x2545f491]
    out = []

    def nxt():
        x = xs[0]
        x ^= (x << 13) & M
        x ^= x >> 17
        x ^= (x << 5) & M
        xs[0] = x
        return x

    for a in EDGE:
        for b in EDGE:
            out.append((a * b) & M)
    for _ in range(N):
        a, b, k = nxt(), nxt(), nxt() % 3
        if k == 1:
            a, b = a & 0xffff, b & 0xffff
        elif k == 2:
            a = a & 0xff
            b = (b & 0xff) if (b & 1) else b
        out.append((a * b) & M)
        sa = a - (1 << 32) if a & 0x80000000 else a
        sb = b - (1 << 32) if b & 0x80000000 else b
        out.append((sa * sb) & M)
    s = 0
    for p in out:
        s = (((s << 7) | (s >> 25)) & M) ^ p
    return s, out[:8], len(out)


# the far variables, which the vendor's example link has no memory for
FAR_BSS = "(memory FarRAM (address (#x30000 . #x3ffff)) (section zfar))"


class Mul32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc, asm, ld, db = (os.path.join(CALYPSI, "bin", t)
                           for t in ("cc65816", "as65816", "ln65816", "db65816"))
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        with open(os.path.join(CALYPSI, "example", "minimal",
                               "linker.scm")) as f:
            vendor = f.read()
        scm = os.path.join(d, "linker.scm")
        with open(scm, "w") as f:
            f.write(vendor.replace("(memory LoRAM", FAR_BSS + "\n    (memory LoRAM", 1))
        mobj = os.path.join(d, "mul32.o")
        subprocess.run([asm, "-o", mobj, MUL32_S], check=True,
                       capture_output=True)
        names = (["m32_sum", "m32_count"]
                 + [f"m32_first[{i}]" for i in range(8)])
        cls.got = {}
        for tag, extra, defs in (("lib", [], []),
                                 ("ours", [mobj, "--override", "_Mul32"],
                                  ["-DTABLE"])):
            obj = os.path.join(d, f"sim-{tag}.o")
            subprocess.run([cc, "-g", "--code-model=large",
                            "--data-model=small", "-O2"] + defs
                           + ["-o", obj, SIM_C], check=True,
                           capture_output=True)
            elf = os.path.join(d, f"{tag}.elf")
            subprocess.run([ld, "-g", scm, obj]
                           + [e for e in extra if e.endswith(".o")]
                           + ["-o", elf, "clib-lc-sd.a", "--rtattr",
                              "exit=simplified"]
                           + [e for e in extra if not e.endswith(".o")],
                           check=True, capture_output=True)
            v = ccbug.simulate(db, elf,
                               names + (["m32_tsum"] if defs else []))
            cls.got[tag] = {k: val & M for k, val in v.items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, tag):
        s, first, n = expected()
        g = self.got[tag]
        self.assertEqual(g["m32_count"] & 0xffff, n & 0xffff)
        self.assertEqual([g[f"m32_first[{i}]"] for i in range(8)], first)
        self.assertEqual(g["m32_sum"], s, f"{tag}: the checksum of {n} products")

    def test_the_library_agrees_with_python(self):
        """The harness itself, against the library: a fault here is in
        the test, not in mul32.s."""
        self.check("lib")

    def test_ours_agrees_with_python(self):
        self.check("ours")

    def test_the_table(self):
        """What the first call made, read back after the products."""
        t = 0
        for n in range(511):
            t = (((t << 5) | (t >> 27)) & M) ^ (n * n // 4)
        self.assertEqual(self.got["ours"]["m32_tsum"], t)


if __name__ == "__main__":
    unittest.main()
