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
(ALLOC, SPAN, PAGE, BANKS, FREE, FREE_OWNER, SHRINK, OWNER, LARGEST, TOP, CLAIM,
 TAG, FREE_SUB, SIZE, PURGE, PURGED) = range(1, 17)

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
    (FREE, 24, 0),              # 31 a bank free in the middle ($07)
    (FREE, 26, 0),              # 32 ...and the top one ($09)
    (TOP, 0x100, 0),            # 33 the top of the highest hole: $09FF00
    (TOP, 0x10000, 0),          # 34 no longer fits there: the lower one
    (FREE, 33, 0),              # 35
    (TOP, 0x1FFFC, 0),          # 36 bigger than any gap: refused
    (TOP, 0xFFFE, 0),           # 37 an odd length: rounded down to 4
    (FREE, 34, 0),              # 38
    (FREE, 23, 0),              # 39 $06 and $07 free together
    (TOP, 0x18000, 0),          # 40 across the bank: $068000
    (FREE, 40, 0),              # 41 banks $06-$07 free again
    (CLAIM, 0x06A000, 0x8000),  # 42 exactly there: $06A000-$071FFF
    (CLAIM, 0x06C000, 0x100),   # 43 inside the last: refused
    (CLAIM, 0x069F00, 0x200),   # 44 runs into it: refused
    (CLAIM, 0x069F00, 0x100),   # 45 ends where it starts: fits
    (CLAIM, 0x0B0000, 0x100),   # 46 above the heap: refused
    (CLAIM, 0x07BFFE, 0x4),     # 47 rounded down: $07BFFC
    (FREE, 42, 0),              # 48
    (ALLOC, 0x3000, 0),         # 49 still the lowest gap first
    # SUB-POOLS (phase 119): the tag rides in len's top byte
    (OWNER, 9, 0),              # 50
    (TAG, 0x10, 0),             # 51 a program, its own memory
    (ALLOC, 0x100, 0),          # 52
    (TAG, 0x13, 0),             # 53 ...its sub-pool 3
    (ALLOC, 0x100, 0),          # 54
    (ALLOC, 0x200, 0),          # 55
    (SHRINK, 55, 0x80),         # 56 smaller, and still sub-pool 3
    (SIZE, 55, 0),              # 57 the length, without the tag
    (OWNER, 10, 0),             # 58 another program's sub-pool 3
    (ALLOC, 0x100, 0),          # 59
    (FREE_SUB, 9, 3),           # 60 owner 9's sub-pool 3 goes...
    (TAG, 0x10, 0),             # 61
    (ALLOC, 0x100, 0),          # 62 ...so its hole is the lowest again
    (FREE_SUB, 9, 0),           # 63 sub-pool 0 is not one: nothing
    (SIZE, 52, 0),              # 64 owner 9's own block is there
    (SIZE, 59, 0),              # 65 ...and owner 10's sub-pool 3
    (FREE_OWNER, 9, 0),         # 66 the owner, whatever the tags
    (SIZE, 52, 0),              # 67 gone
    # PURGING (phase 120): everything freed but the table, the heap filled
    # with whole banks, four of them marked purgeable, then more asked for
    (FREE_OWNER, 7, 0),         # 68
    (FREE_OWNER, 10, 0),        # 69 only the table is left, in bank 2
    (OWNER, 11, 0),             # 70
    (TAG, 0, 0),                # 71
    (ALLOC, 0x10000, 0),        # 72 bank 3
    (ALLOC, 0x10000, 0),        # 73 4
    (ALLOC, 0x10000, 0),        # 74 5
    (ALLOC, 0x10000, 0),        # 75 6
    (ALLOC, 0x10000, 0),        # 76 7
    (ALLOC, 0x10000, 0),        # 77 8
    (ALLOC, 0x10000, 0),        # 78 9
    (ALLOC, 0x10000, 0),        # 79 none left
    (PURGE, 73, 3),             # 80 two banks the first to go
    (PURGE, 75, 3),             # 81
    (PURGE, 74, 2),             # 82 one after them
    (PURGE, 76, 1),             # 83 and one last of all
    (PURGE, 77, 0),             # 84 (0: not purgeable)
    (ALLOC, 0x10000, 0),        # 85 no room: level 3 goes, then it fits
    (PURGED, 0, 0),             # 86 2
    (ALLOC, 0x10000, 0),        # 87 the other level-3 bank: no purge
    (ALLOC, 0x10000, 0),        # 88 no room again: level 2 goes
    (PURGED, 0, 0),             # 89 3
    (SIZE, 76, 0),              # 90 level 1 is still there
    (BANKS, 2, 0),              # 91 two banks: everything purgeable
                                #    goes, and they are still not there
    (PURGED, 0, 0),             # 92 4: the level-1 bank went too
]


def model():
    h = farref.Heap(FIRST, LAST)
    out = []
    model.heap = h
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
        elif op == TOP:
            r = h.alloc_top(a)
        elif op == CLAIM:
            r = h.claim(a, b)
        elif op == TAG:
            h.tag = a
        elif op == FREE_SUB:
            h.free_sub(a, b)
        elif op == SIZE:
            i = h._find(out[a])
            r = h.blocks[i][1] if i else 0
        elif op == PURGE:
            r = h.set_purge(out[a], b)
        elif op == PURGED:
            r = len(h.purged)
        out.append(r)
    return out


class TestFarAlloc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        out = os.path.join(ROOT, "build", "farmem")
        os.makedirs(out, exist_ok=True)
        # the minimal example's map, with somewhere for farmem.c's zwin
        with open(os.path.join(CALYPSI, "example", "minimal", "linker.scm")) as f:
            scm_text = f.read().replace("(section stack data zdata heap)",
                                        "(section stack data zdata heap zwin)")
        assert "zwin" in scm_text
        scm = os.path.join(out, "linker.scm")
        with open(scm, "w") as f:
            f.write(scm_text)
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
        names = (["fm_bad", "fm_crossed", "fm_nhook"]
                 + [f"fm_out[{i}]" for i in range(len(SCRIPT))]
                 + [f"fm_hooked[{i}]" for i in range(16)])
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

    def test_the_hook_is_told_what_went_in_order(self):
        purged = model.heap.purged
        got = [self.v[f"fm_hooked[{i}]"] for i in range(min(self.v["fm_nhook"], 16))]
        self.assertEqual(self.v["fm_nhook"], len(purged))
        self.assertEqual(got, purged[:16])

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
        self.assertEqual(w[42], 0x06A000, "a claim lands exactly where asked")
        self.assertEqual((w[43], w[44], w[46]), (0, 0, 0),
                         "a claim over a block, or past the heap, is refused")
        self.assertEqual(w[45], 0x069F00, "a claim may end where a block starts")
        self.assertEqual(w[47], 0x07BFFC, "a claim's start rounds down to 4")
        self.assertEqual(w[57], 0x80, "a shrunk block's length has no tag in it")
        self.assertEqual(w[62], w[54], "a freed sub-pool's hole is used again")
        self.assertEqual((w[64], w[65]), (0x100, 0x100),
                         "the owner's own block and another owner's sub-pool 3 "
                         "outlive the free of this owner's sub-pool 3")
        self.assertEqual(w[67], 0, "freeing the owner frees it whatever the tag")
        self.assertEqual(w[78], 0x090000, "whole banks to the top")
        self.assertEqual(w[79], 0, "the heap did run out of whole banks")
        self.assertEqual(w[85], w[73], "the request lands where level 3 was")
        self.assertEqual(w[86], 2, "both level-3 banks went, and nothing else")
        self.assertEqual(w[87], w[75])
        self.assertEqual((w[88], w[89]), (w[74], 3), "then level 2, alone")
        self.assertEqual(w[90], 0x10000, "level 1 outlives levels 3 and 2")
        self.assertEqual((w[91], w[92]), (0, 4),
                         "a request nothing can satisfy purges level 1 too, "
                         "and is still refused; level 0 is never purged")


if __name__ == "__main__":
    unittest.main()
