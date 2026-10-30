#!/usr/bin/env python3
"""Phase 117 gate: bank $00's pool frees in any order.

The runner's sys op 3020 loads the packed test program (the same blob
op 3004 runs) with the real loader, into one of four slots, without
running it -- or frees a slot with app_free.  Three programs are
loaded and freed out of order, which the bump cursor could not do:

  A, B loaded          two near regions, one above the other
  A freed              first, which a bump cursor cannot do: a hole
                       below B, and the top does not move
  D loaded             into A's hole, not above B
  B freed              the top comes down to D's end
  D freed              everything back

and after the last, the pool's table, its top, and the far
heap's blocks, must be exactly what they were before the first load --
every byte given back -- with no release refused (src/sys/pool.c).

  python3 tests/emu/m48_pool.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from farheap import far_heap                  # noqa: E402
from m7_form import STATUS, DISK, SYMS        # noqa: E402
from m12_file import Runner, FAULT_I          # noqa: E402

SLOTS = 3020
LOAD, FREE = 0, 1
# a record's word i + 2 is intout[i] (FAULT_I is intout[5])
ST_I, NEAR_I, TOP_I = 8, 9, 11
POOL_MAX = 32                   # src/sys/pool.h


def main():
    print("gem4xe-m48: bank $00's pool, freed in any order")
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)

    emu = launch(tag="m48", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        for _ in range(200):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1
        r = Runner(b, syms)

        def table():
            n = b.peek16(syms["pool_blocks"])
            at = b.memdump(syms["pb_at"], 2 * POOL_MAX)
            ln = b.memdump(syms["pb_len"], 2 * POOL_MAX)
            ow = b.memdump(syms["pb_own"], POOL_MAX)
            return tuple((at[2 * i] | at[2 * i + 1] << 8,
                          ln[2 * i] | ln[2 * i + 1] << 8, ow[i]) for i in range(n))

        def heap():
            return tuple((a, n) for a, n, _ in far_heap(b, syms).blocks)

        def op(what, slot):
            rec = r.run([(SLOTS, (), (what, slot))])[0]
            check(rec[FAULT_I] == 0, f"op {what} slot {slot}: no fault "
                                     f"(fault {rec[FAULT_I]})")
            return rec

        # the pool as the runner left it, before anything is loaded -- after
        # one free of an empty slot, which makes the slots' own far block
        op(FREE, 3)
        t0, h0 = table(), heap()
        top0 = b.peek16(syms["pool_brk"])
        print(f"  before: {len(t0)} block(s), top ${top0:04X}, "
              f"{len(h0)} far block(s)")

        hi = b.peek16(syms["app_pool_hi"])
        near = {}
        for s in (0, 1):                           # A, B
            rec = op(LOAD, s)
            check(rec[ST_I] == 0, f"slot {s} loads (status {rec[ST_I]})")
            near[s] = rec[NEAR_I] & 0xFFFF
        check(near[0] < near[1] and not (near[0] | near[1]) & 0xFF,
              f"A and B page-aligned, B above A (${near[0]:04X}, ${near[1]:04X}; "
              f"the pool ends at ${hi:04X})")
        top_b = b.peek16(syms["pool_brk"])

        rec = op(FREE, 0)                          # A, first: not LIFO
        check(rec[TOP_I] & 0xFFFF == top_b,
              f"A freed first: the top stays ${top_b:04X} "
              f"(reads ${rec[TOP_I] & 0xFFFF:04X})")
        check(all(near[0] != a for a, _, _ in table()), "A's near region is gone")

        rec = op(LOAD, 3)                          # D
        d = rec[NEAR_I] & 0xFFFF
        check(rec[ST_I] == 0 and d == near[0],
              f"D loads into A's hole at ${near[0]:04X} (status {rec[ST_I]}, "
              f"near ${d:04X})")
        check(rec[TOP_I] & 0xFFFF == top_b, "...and the top did not move")

        rec = op(FREE, 1)                          # B
        check(rec[TOP_I] & 0xFFFF == near[1],
              f"B freed: the top comes down to D's end, ${near[1]:04X} "
              f"(reads ${rec[TOP_I] & 0xFFFF:04X})")

        op(FREE, 3)                                # D
        t1, h1 = table(), heap()
        top1 = b.peek16(syms["pool_brk"])
        check(t1 == t0, f"the pool's table is what it was: {len(t1)} block(s), "
                        f"before {len(t0)}")
        check(top1 == top0, f"the top is back at ${top0:04X} (reads ${top1:04X})")
        check(h1 == h0, f"the far heap is what it was: {len(h1)} block(s), "
                        f"before {len(h0)}")
        check(b.peek16(syms["pool_refused"]) == 0, "no release refused")
        check(b.peek16(syms["pool_full"]) == 0, "the table never ran out")
    finally:
        emu.stop()

    print(f"gem4xe-m48: {'PASS' if not fails else 'FAIL'} -- the pool freed "
          f"in any order, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
