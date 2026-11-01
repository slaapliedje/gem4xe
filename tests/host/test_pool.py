#!/usr/bin/env python3
"""Host tests for the bank-$00 pool (src/sys/pool.c).

One script of requests goes through pool.c in the compiler's own
simulator and through tools/poolref.py, and every answer -- and the top
after every step -- must agree.  The script is the product's own shape
first (the process records, an accessory, the floor, the desktop), then
what the bump cursor could not do: a block freed out of order, a program
loaded into the hole another left below a module, an accessory's block
surviving a program's release, a release cut through a block, the floor
refusing, and the table running out.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
POOL_C = os.path.join(ROOT, "src", "sys", "pool.c")
SIM_C = os.path.join(ROOT, "tests", "host", "pool_sim.c")

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check as ccbug                      # noqa: E402  (the simulator driver)
import poolref                             # noqa: E402

LO, HI = 0x4800, 0x6000
(ALLOC, TAKE, MARK, RELEASE, FREE, FREE_OWNER, OWNER, KEEP, ROOM, REFUSED,
 FULL, RELEASE_AT, TAG, FREE_SUB, CLAIM) = range(1, 16)
SLOTS = 32                                 # POOL_MAX (src/sys/pool.h)

# (op, a, b); RELEASE's and FREE's `a` is the index of an earlier step
SCRIPT = [
    (ALLOC, 644, 2),            # 0  the process records: $4800
    (TAKE, 1024, 0x100),        # 1  an accessory's near region: $4B00
    (OWNER, 3, 0),              # 2
    (TAKE, 1536, 0x100),        # 3  another's: $4F00
    (ALLOC, 268, 2),            # 4  its resource: $5500
    (OWNER, 0, 0),              # 5
    (KEEP, 0, 0),               # 6  the floor: $560C
    (OWNER, 5, 0),              # 7  the desktop
    (MARK, 0, 0),               # 8  $560C
    (TAKE, 1280, 0x100),        # 9  its near region: $5700
    (MARK, 0, 0),               # 10 $5C00
    (ALLOC, 300, 2),            # 11 a selector's work: $5C00
    (OWNER, 6, 0),              # 12 a switch to an accessory...
    (ALLOC, 100, 2),            # 13 ...which takes a block: $5D2C
    (OWNER, 5, 0),              # 14
    (RELEASE, 10, 0),           # 15 the selector's goes, the accessory's stays
    (ROOM, 0, 0),               # 16 above $5D90
    (ALLOC, 0x400, 2),          # 17 more than that: refused
    (OWNER, 6, 0),              # 18
    (FREE, 13, 0),              # 19 the accessory frees its own: 1
    (FREE_OWNER, 5, 0),         # 20 the desktop goes, by owner
    (OWNER, 7, 0),              # 21 a program
    (TAKE, 2048, 0x100),        # 22 $5700
    (OWNER, 8, 0),              # 23 a module, loaded while it runs
    (TAKE, 256, 0x100),         # 24 above it: $5F00
    (FREE_OWNER, 7, 0),         # 25 the program ends FIRST: a hole below
    (OWNER, 9, 0),              # 26 the next program
    (TAKE, 1024, 0x100),        # 27 into the hole: $5700
    (ALLOC, 100, 2),            # 28 the top is full: an alloc never holes
    (TAKE, 100, 2),             # 29 a take does: the records' tail, $4A84
    (RELEASE_AT, 0x4000, 0),    # 30 under the floor: refused
    (REFUSED, 0, 0),            # 31 1
    (OWNER, 8, 0),              # 32
    (FREE, 24, 0),              # 33 the module closes: the top drops
    (OWNER, 9, 0),              # 34
    (ALLOC, 200, 2),            # 35 $5B00
    (RELEASE_AT, 0x5B64, 0),    # 36 through it: cut to 100 bytes
    (FREE_OWNER, 0, 0),         # 37 the system's: nothing
    (OWNER, 0, 0),              # 38
    (FREE, 0, 0),               # 39 the records, singly: 1
    (TAKE, 600, 2),             # 40 below the first block now: $4800
    (FREE, 17, 0),              # 41 a refused take's 0 is no block: 0
    (ALLOC, 0, 0x100),          # 42 a zero size is a place: the top, aligned
    (ROOM, 0, 0),               # 43 ...and took nothing
    # SUB-POOLS (phase 119)
    (OWNER, 9, 0),              # 44
    (TAG, 0x15, 0),             # 45 owner 9's sub-pool 5
    (ALLOC, 64, 2),             # 46 $5B64
    (TAG, 0x10, 0),             # 47
    (ALLOC, 64, 2),             # 48 $5BA4, its own
    (FREE_SUB, 9, 5),           # 49 sub-pool 5 goes; the top stays
    (FREE, 46, 0),              # 50 ...so 46 is no block now: 0
    (FREE, 48, 0),              # 51 ...and 48 still is: 1
    # CLAIM (phase 121): a dormant program's near region, exactly where
    (CLAIM, 0x4A58, 0x2C),      # 52 the gap between 40's take and $4A84
    (CLAIM, 0x4A58, 0x2C),      # 53 ...and now it is taken: 0
    (CLAIM, 0x4A00, 0x100),     # 54 across a block: 0
    (CLAIM, 0x5F00, 0x80),      # 55 a free stretch below the top: fits
]
# ...and then the table runs out
SCRIPT += [(ALLOC, 2, 2)] * SLOTS + [(FULL, 0, 0), (ROOM, 0, 0)]


def model():
    p = poolref.Pool(LO, HI, SLOTS)
    out = []
    tops = []
    for op, a, b in SCRIPT:
        r = 0
        if op == ALLOC:
            r = p.alloc(a, b)
        elif op == TAKE:
            r = p.take(a, b)
        elif op == MARK:
            r = p.mark()
        elif op == RELEASE:
            p.release(out[a])
        elif op == FREE:
            r = p.free(out[a])
        elif op == FREE_OWNER:
            p.free_owner(a)
        elif op == OWNER:
            p.owner = a
        elif op == KEEP:
            p.keep_mark()
        elif op == ROOM:
            r = p.room()
        elif op == REFUSED:
            r = p.refused
        elif op == FULL:
            r = p.full
        elif op == RELEASE_AT:
            p.release(a)
        elif op == TAG:
            p.tag = a
        elif op == FREE_SUB:
            p.free_sub(a, b)
        elif op == CLAIM:
            r = p.claim(a, b)
        out.append(r)
        tops.append(p.top())
    return out, tops


class TestPool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        out = os.path.join(ROOT, "build", "pool")
        os.makedirs(out, exist_ok=True)
        # the minimal example's map, with somewhere for pool.c's zwin
        with open(os.path.join(CALYPSI, "example", "minimal", "linker.scm")) as f:
            scm_text = f.read()
        scm_text = scm_text.replace("(section stack data zdata heap)",
                                    "(section stack data zdata heap zwin)")
        assert "zwin" in scm_text
        scm = os.path.join(out, "linker.scm")
        with open(scm, "w") as f:
            f.write(scm_text)
        with open(os.path.join(out, "pool_script.h"), "w") as f:
            f.write(f"#define STEPS {len(SCRIPT)}\n#define LO {LO:#x}\n"
                    f"#define HI {HI:#x}\n"
                    "static const uint16_t script[STEPS][3] = {\n")
            for op, a, b in SCRIPT:
                f.write(f"    {{ {op}, {a:#x}, {b:#x} }},\n")
            f.write("};\n")
        objs = []
        for src in (POOL_C, SIM_C):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            "-O2", "-I", os.path.join(ROOT, "src"), "-I", out,
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(out, "pool.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        names = (["pl_bad"] + [f"pl_out[{i}]" for i in range(len(SCRIPT))]
                 + [f"pl_top[{i}]" for i in range(len(SCRIPT))])
        cls.v = ccbug.simulate(db, elf, names)
        cls.want, cls.tops = model()

    def test_every_answer_is_the_models(self):
        bad = []
        for i, (op, a, b) in enumerate(SCRIPT):
            got, want = self.v[f"pl_out[{i}]"], self.want[i]
            top, wtop = self.v[f"pl_top[{i}]"], self.tops[i]
            if (got, top) != (want, wtop):
                bad.append(f"[{i}] op {op}({a:#x}, {b:#x}): target "
                           f"${got:04X} top ${top:04X}, model ${want:04X} "
                           f"top ${wtop:04X}")
        self.assertEqual(bad, [])

    def test_the_table_stays_sorted_and_whole(self):
        self.assertEqual(self.v["pl_bad"], 0,
                         f"the table was wrong after step {self.v['pl_bad'] - 1}")

    def test_the_script_says_something(self):
        """The cases the script is FOR, in the model: a check that passes
        by agreeing on nothing is not believed."""
        w, t = self.want, self.tops
        self.assertEqual((w[0], w[1], w[3], w[4]), (0x4800, 0x4B00, 0x4F00, 0x5500),
                         "with nothing freed out of order: the cursor's places")
        self.assertEqual((w[9], w[11], w[13]), (0x5700, 0x5C00, 0x5D2C))
        self.assertEqual(t[15], 0x5D90, "the accessory's block outlives the release")
        self.assertEqual(w[17], 0, "an alloc bigger than the top's room: refused")
        self.assertEqual(w[19], 1)
        self.assertEqual(t[20], 0x560C, "the desktop freed by its owner")
        self.assertEqual(w[24], 0x5F00)
        self.assertEqual(w[27], 0x5700, "a program loads into the hole below a module")
        self.assertEqual(w[28], 0, "an alloc never goes into a hole")
        self.assertEqual(w[29], 0x4A84, "a take does: the lowest that fits")
        self.assertEqual(w[31], 1, "a release under the floor is refused")
        self.assertEqual(t[33], 0x5B00, "the module freed: the top comes down")
        self.assertEqual(t[36], 0x5B64, "a release cuts a block it goes through")
        self.assertEqual(w[39], 1)
        self.assertEqual(w[40], 0x4800, "the gap below the first block")
        self.assertEqual(w[41], 0, "freeing what is not a block")
        self.assertEqual((w[42], w[43]), (0x5C00, HI - 0x5B64))
        self.assertGreater(w[-2], 0, "the table runs out, and says so")
        self.assertEqual((w[46], w[48]), (0x5B64, 0x5BA4))
        self.assertEqual(t[49], 0x5BE4, "a sub-pool freed below the top")
        self.assertEqual((w[50], w[51]), (0, 1),
                         "the sub-pool's block went, the owner's own stayed")
        self.assertEqual((w[53], w[54]), (0, 0), "a claim over a block is refused")
        self.assertEqual((w[52], w[55]), (0x4A58, 0x5F00),
                         "a claim of free memory lands exactly, a gap filled to the byte")


if __name__ == "__main__":
    unittest.main()
