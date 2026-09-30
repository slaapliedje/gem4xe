#!/usr/bin/env python3
"""Host tests for the far allocator (src/sys/farmem.c).

One script of requests goes through farmem.c in the compiler's own
simulator and through tools/farref.py, the model the desktop gates place
things with, and every answer must agree.  The script is written to hit
what an allocator gets wrong: a bank's edge, a block exactly the rest of
one and a byte more, a page request against the $D5 page, whole banks
from the top down, frees out of order and by owner, a shrink, the
largest gap -- and a heap run out.

**A block from far_alloc may not cross a bank.**  Calypsi's `__far`
arithmetic is sixteen bits within a bank, so a buffer that straddles one
wraps to the bottom of its own bank when indexed past the edge; it
corrupted the file selector once (docs/phase24.md).  The simulator
checks every block, and the table's order and overlap, after every step.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
FARMEM_C = os.path.join(ROOT, "src", "sys", "farmem.c")
SIM_C = os.path.join(ROOT, "tests", "host", "farmem_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check as ccbug                      # noqa: E402  (the simulator driver)
import farref                              # noqa: E402

FIRST, LAST = 2, 9                         # eight banks
ALLOC, SPAN, PAGE, BANKS, FREE, FREE_OWNER, SHRINK, OWNER, LARGEST = range(1, 10)

# (op, a, b); a FREE or SHRINK's `a` is the index of an earlier step
SCRIPT = [
    (ALLOC, 900, 0),            # 0  above the table, in bank 2
    (OWNER, 5, 0),              # 1
    (BANKS, 2, 0),              # 2  the lowest free two: banks 3-4
    (ALLOC, 0xF000, 0),         # 3  fits in bank 2 still? no: 3 bank
    (ALLOC, 0x10000, 0),        # 4  exactly a bank
    (ALLOC, 0x10001, 0),        # 5  a byte more: refused
    (PAGE, 0x3000, 0xD500),     # 6  page-aligned below $D5
    (PAGE, 0xD000, 0xD500),     # 7  a whole low part: next free bank
    (SPAN, 0x18000, 0),         # 8  crosses banks
    (OWNER, 7, 0),              # 9
    (ALLOC, 0x200, 0),          # 10
    (ALLOC, 0x200, 0),          # 11
    (FREE, 10, 0),              # 12 out of order
    (ALLOC, 0x100, 0),          # 13 into the hole 10 left
    (SHRINK, 8, 0x8000),        # 14
    (LARGEST, 0, 0),            # 15
    (LARGEST, 1, 0),            # 16
    (FREE_OWNER, 5, 0),         # 17 the banks and 3..8 go
    (BANKS, 3, 0),              # 18 three again, as low as they fit
    (LARGEST, 1, 0),            # 19
    (FREE, 0, 0),               # 20 the first block (owner 0): freed
    (BANKS, 9, 0),              # 21 more than there is: refused
    (FREE_OWNER, 0, 0),         # 22 the system's: nothing happens
    (ALLOC, 0x10000, 0),        # 23
    (ALLOC, 0x10000, 0),        # 24 until it runs out
    (ALLOC, 0x10000, 0),        # 25
    (ALLOC, 0x10000, 0),        # 26
    (ALLOC, 0x10000, 0),        # 27
    (ALLOC, 0x10000, 0),        # 28
    (ALLOC, 0x10000, 0),        # 29
    (LARGEST, 0, 0),            # 30
]


def model():
    h = farref.Heap(FIRST, LAST)
    out = []
    for op, a, b in SCRIPT:
        r = 0
        if op == ALLOC:
            r = h.alloc(a)
        elif op == SPAN:
            r = h.alloc_span(a)
        elif op == PAGE:
            r = h.alloc_page(a, b)
        elif op == BANKS:
            r = h.alloc_banks(a)
        elif op == FREE:
            r = h.free(out[a])
        elif op == FREE_OWNER:
            h.free_owner(a)
        elif op == SHRINK:
            r = h.shrink(out[a], b)
        elif op == OWNER:
            h.owner = a
        elif op == LARGEST:
            r = h.largest(a)
        out.append(r)
    return out


class TestFarAlloc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "farmem")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "farmem_script.h"), "w") as f:
            f.write(f"#define STEPS {len(SCRIPT)}\n#define FIRST {FIRST}\n"
                    f"#define LAST {LAST}\n"
                    "static const uint32_t script[STEPS][3] = {\n")
            for op, a, b in SCRIPT:
                f.write(f"    {{ {op}, {a:#x}UL, {b:#x}UL }},\n")
            f.write("};\n")
        objs = []
        for src in (FARMEM_C, SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"), "-I", out,
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "farmem.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        names = (["fm_bad", "fm_crossed"]
                 + [f"fm_out[{i}]" for i in range(len(SCRIPT))])
        cls.v = ccbug.simulate(db, elf, names)
        cls.want = model()

    def test_every_answer_is_the_models(self):
        bad = []
        for i, (op, a, b) in enumerate(SCRIPT):
            got, want = self.v[f"fm_out[{i}]"], self.want[i]
            if got != want:
                bad.append(f"[{i}] op {op}({a:#x}, {b:#x}): target "
                           f"${got:06X}, model ${want:06X}")
        self.assertEqual(bad, [])

    def test_the_table_stays_sorted_and_whole(self):
        self.assertEqual(self.v["fm_bad"], 0,
                         f"the table was wrong after step {self.v['fm_bad'] - 1}")

    def test_no_block_crosses_a_bank(self):
        self.assertEqual(self.v["fm_crossed"], 0)

    def test_the_script_says_something(self):
        """The cases the script is FOR, in the model: a check that passes
        by agreeing on nothing is not believed."""
        w = self.want
        self.assertEqual(w[2], 3, "whole banks: the lowest free run")
        self.assertEqual(w[5], 0, "a block bigger than a bank is refused")
        self.assertTrue(w[6] and (w[6] & 0xFF) == 0 and (w[6] & 0xFFFF) + 0x3000 <= 0xD500)
        self.assertNotEqual(w[8] >> 16, (w[8] + 0x17FFF) >> 16, "the span crosses")
        self.assertEqual(w[13], w[10], "a freed hole is used again")
        self.assertEqual(w[21], 0, "more banks than there are: refused")
        self.assertIn(0, w[23:30], "the heap does run out")


if __name__ == "__main__":
    unittest.main()
