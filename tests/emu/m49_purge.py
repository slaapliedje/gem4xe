#!/usr/bin/env python3
"""Phase 120 gate: purgeable far memory gives way to a request that needs it.

The runner's sys op 3022 fills the far heap with 256 KB spans of an owner
of its own until the allocator refuses -- every gap left smaller than one
-- and marks the last four spans purge level 3 and the four before them
level 1 (src/sys/farmem.h).  Then it asks for 512 KB, which no gap can
hold.  GS/OS's order (src/sys/farmem.c) says level 3 goes first and the
request is tried again before anything else is touched:

  the request succeeds, in the level-3 spans' place
  exactly those four were purged, and named to far_purge_hook
  the four level-1 spans are all still there

and with the owner freed afterwards the heap has its room back.

  python3 tests/emu/m49_purge.py
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

PURGE = 3022
FILL, ASK, FREE = 0, 1, 2
# a record's word i + 2 is intout[i]
N_I, GOT_HI, GOT_LO, PURGED_I, K1_I, K3_I, L3_HI, L3_LO = 8, 9, 10, 11, 12, 13, 14, 15


def main():
    print("gem4xe-m49: purgeable far memory under pressure")
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)

    emu = launch(tag="m49", memsize="1088K", extra_args=["--disk", DISK])
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
        for _ in range(1000):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1
        r = Runner(b, syms)

        def op(what):
            rec = r.run([(PURGE, (), (what,))])[0]
            check(rec[FAULT_I] == 0, f"op {what}: no fault (fault {rec[FAULT_I]})")
            return [x & 0xFFFF for x in rec]

        h0 = far_heap(b, syms)
        largest0 = h0.largest(1)
        rec = op(FILL)
        n = rec[N_I]
        l3 = rec[L3_HI] << 16 | rec[L3_LO]
        print(f"  filled: {n} spans of 256 KB; the level-3 run starts at ${l3:06X}")
        check(n >= 8, f"at least eight spans to mark ({n})")
        check(far_heap(b, syms).largest(1) < 0x80000,
              "no gap left holds 512 KB")

        rec = op(ASK)
        got = rec[GOT_HI] << 16 | rec[GOT_LO]
        print(f"  512 KB asked for: ${got:06X}; {rec[PURGED_I]} purged; "
              f"level 1 left {rec[K1_I]} of 4, level 3 left {rec[K3_I]} of 4")
        check(got != 0, "the request succeeds")
        check(got == l3, f"in the level-3 run's place (${got:06X}, run ${l3:06X})")
        check(rec[PURGED_I] == 4, f"exactly the four level-3 spans purged "
                                  f"({rec[PURGED_I]})")
        check((rec[K1_I], rec[K3_I]) == (4, 0),
              "every level-1 span still there, no level-3 one")

        op(FREE)
        largest1 = far_heap(b, syms).largest(1)
        check(largest1 >= largest0, f"the owner freed: the largest gap is "
                                    f"{largest1:,}, was {largest0:,}")
    finally:
        emu.stop()

    print(f"gem4xe-m49: {'PASS' if not fails else 'FAIL'} -- purgeable far "
          f"memory under pressure, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
