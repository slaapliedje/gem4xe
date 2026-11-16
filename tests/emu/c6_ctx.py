#!/usr/bin/env python3
"""6502 step 4d gate: two contexts taking turns on a stock 6502.

test-m27's claims (tests/emu/m27_ctx.py), on the 6502's two stacks --
page 1 and the compiler's C stack under _Vsp -- and its banks
(src/sys6502/ctx6502.s, src/sys6502/ctx6502.c).  build/c6-boot.atr
carries src/c6_ctx.c, its two contexts' programs in banks of their own
(src/c6_procs.c: proc_a in cxa, proc_b in cxb):

  - the turns are in the order asked for, and each ran in its own bank:
    a context resumed in the other's would have run the middle of its
    code, and b6_cur at each turn says which was mapped;
  - a frame survives a switch from underneath it: proc_a recurses six
    frames, its local in a saved register, yields from the deepest, and
    finds every level's value on the way back out;
  - no park was refused (ctx_over), and the record is the size
    src/sys/ctx.h says with the 6502's two words.

It prints what a park cost, both stacks, at the deepest.

    python3 tests/emu/c6_ctx.py
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "c6-boot.atr"))
MAP = os.path.join(ROOT, "build", "c6.map")
STATUS = 0x0600
ROUNDS, DEEP = 5, 6
BANK_A, BANK_B = 2, 3                       # tools/bsp6502/c6.scm
WANT_SEQ = [0] + [1, 2] * ROUNDS + [2, 0x11, 0]
# the bank each turn's note() saw: the root's main memory, then the
# contexts' own; 2 after the rounds is proc_b's turn from the deep yield
WANT_BANK = [0] + [BANK_A, BANK_B] * ROUNDS + [BANK_B, BANK_A, 0]

# src/sys/ctx.h, in order, the 6502's two words last
CTX_SP, CTX_SAVE, CTX_LEN, CTX_DEEP, CTX_ENTRY, CTX_LIVE = 0, 2, 6, 8, 10, 14
CTX_VSP, CTX_VLEN, CTX_SIZE = 30, 32, 34
CTX_DONE = 2


def symbols():
    out = {}
    for line in open(MAP):
        m = re.match(r"\s+(\w+) = ([0-9a-f]{4})\s*$", line)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


def main():
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-c6: two contexts taking turns, on a stock 6502")
    sym = symbols()
    emu = launch(tag="c6", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge

    def word(a):
        d = bytes(b.memdump(a, 2))
        return d[0] | (d[1] << 8)

    try:
        b.frames(300)
        for _ in range(0, 3000, 25):
            b.frames(25)
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"C6" and st[2]:
                break
        st = bytes(b.memdump(STATUS, 4))
        if not check(st[:3] == b"C6K", f"the program ran to its end (status {st[:3]!r}, "
                                       f"stage {chr(st[3]) if st[3] else '-'!r})"):
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "6502", f"the CPU is a 6502 ({cpu})")
        check(word(sym["ctx_regs_want"]) == 54,
              f"the register file is {word(sym['ctx_regs_want'])} bytes, what a switch carries")
        check(sym["c_a"] - sym["c_b"] == CTX_SIZE and sym["c_root"] - sym["c_a"] == CTX_SIZE,
              f"a CTX is {CTX_SIZE} bytes, as src/sys/ctx.h lays it out "
              f"({sym['c_a'] - sym['c_b']})")

        n = word(sym["nseq"])
        seq = [word(sym["seq"] + 2 * i) for i in range(n)]
        banks = list(bytes(b.memdump(sym["seqbank"], n)))
        check(seq == WANT_SEQ, f"the turns in order: {seq}")
        check(banks == WANT_BANK, f"each in its own bank: {banks}")
        check(word(sym["rounds_a"]) == ROUNDS + 0 and word(sym["rounds_b"]) == ROUNDS + 1,
              f"rounds {word(sym['rounds_a'])} and {word(sym['rounds_b'])}")

        put = [word(sym["deep_put"] + 2 * i) for i in range(DEEP)]
        got = [word(sym["deep_got"] + 2 * i) for i in range(DEEP)]
        want = [0xC000 + i * 7 for i in range(DEEP)]
        check(put == want and got == want and word(sym["deep_bad"]) == 0,
              f"six frames' locals survived the switch from the deepest "
              f"(put {[hex(x) for x in put]}, got {[hex(x) for x in got]})")
        check(word(sym["ctx_over"]) == 0, f"no park refused (ctx_over {word(sym['ctx_over'])})")
        check(word(sym["c_a"] + CTX_LIVE) == CTX_DONE, "proc_a's context is done")

        for name in ("c_root", "c_a", "c_b"):
            a = sym[name]
            print(f"  {name}: deepest park {word(a + CTX_DEEP)} bytes; last "
                  f"page 1 {word(a + CTX_LEN)} + C stack {word(a + CTX_VLEN)}")
        print(f"  page-1 S at its lowest in a turn: ${b.peek(sym['min_s']):02X}, "
              f"top ${b.peek(sym['ctx_hbase']):02X}")
    finally:
        emu.stop()
    print(f"gem4xe-c6: {'PASS' if not fails else 'FAIL'} -- two contexts taking turns, "
          f"on a stock 6502, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
