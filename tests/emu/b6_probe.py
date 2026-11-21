#!/usr/bin/env python3
"""gem4xe-b6probe: the 6502 bank probe on every PORTB size.

src/sys6502/bank6502.s finds the banks at load time.  Every other 6502
gate runs a 1088K machine, where all six free PORTB bits are bank bits;
on a smaller board BASIC (bit 1) and the self-test ROM (bit 7) are not,
so each bank answers to several candidates, some of which the probe must
refuse.  It once wrote a refused candidate's index into a bank already
kept, and so found one bank on a 130XE.

Boots build/a6-boot.atr on each size and reads b6_count once the probe
has run.  The program needs 16 banks and stops without them, and under
--siopatch that stop and the self test it leads to come before the first
look, so a 130XE (4 banks) cannot be read this way; it is the board in
Calypsi-6502-Atari's own probe gate.  Before the fix 320K found one bank
and stopped there, so it read as "no probe".
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6-boot.atr"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
# memsize: PORTB banks (main memory not counted)
SIZES = [("320K", 16), ("320KCOMPY", 16), ("576K", 32), ("1088K", 64)]


def main():
    text = open(MAP).read()

    def sym(n):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", text, re.M).group(1), 16)
    count, kind = sym("b6_count"), sym("b6_kind")
    fails = []
    print("gem4xe-b6probe: the 6502 bank probe on each PORTB size")
    for mem, want in SIZES:
        emu = launch(tag=f"b6probe{mem}", memsize=mem, vbxe=False, rapidus=False,
                     extra_args=["--disk", DISK])
        b = emu.bridge
        try:
            got, seen = None, False
            for _ in range(120):
                b.frames(50)
                if b.peek(kind) == ord("P"):
                    seen = True
                    b.frames(100)           # the probe is well over by now
                    got = b.peek(count)
                    break
            mode = b.cmd("HWSTATE")["cpu"]["mode"]
        finally:
            emu.stop()
        ok = seen and got == want and mode == "6502"
        print(f"  {'ok' if ok else 'FAIL'}: {mem}: {got if seen else 'no probe'} "
              f"banks, want {want} (CPU {mode})")
        if not ok:
            fails.append(mem)
    print(f"gem4xe-b6probe: {'PASS' if not fails else 'FAIL ' + ' '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
