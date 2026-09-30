#!/usr/bin/env python3
"""Phase 36 gate: two contexts taking turns on one stack.

A desk accessory is a second program resident beside the first, and GEM's
answer to how it gets the processor is a process with its own stack that
blocks inside evnt_multi while the dispatcher runs somebody else.  gem4xe
cannot have a second engine stack -- 1,239 of the 2,048 bytes are used at
the low-water mark and LoRAM has 47 free -- so the contexts SHARE the one
stack: a parked context's extent of it lives in far memory and goes back
to THE SAME ADDRESSES when it runs again.  src/sys/ctx.h has the argument.

Everything downstream of this rests on the copy being exact, so this gate
runs before there is a desktop in the way:

  THE TURNS ARE IN THE ORDER THEY WERE ASKED FOR.  The runner writes who
  ran into a plain array; a switch that quietly did nothing, or came back
  to the wrong context, is a different array and not a crash.

  A FRAME SURVIVES A SWITCH FROM UNDERNEATH IT.  One context recurses six
  frames deep, writes a value derived from the depth into a local, yields
  from the deepest frame, and checks every local on the way back out.  A
  copy short by one byte fails this; nothing else here would notice.

The gate also prints what a park actually COST -- the high-water extent
each context copied -- because "a switch is cheap if it is shallow" is
the claim the design was chosen on and it should be a measurement.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile                              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m27-boot.atr"))
SYMS = os.path.join(ROOT, "build", "m27.sym")
STATUS = 0x0600

ROUNDS, DEEP = 5, 6
# src/m27_ctx.c: the root, then five turns each, then the deep yield, the
# recursing context's mark and the root again.
WANT_SEQ = [0] + [1, 2] * ROUNDS + [2, 0x11, 0]

# src/sys/ctx.h, in order.  The gate does not take these on trust: the
# three CTX records are consecutive in bss, so their spacing is the
# struct's real size and is checked against the last field's end.
CTX_SP, CTX_SAVE, CTX_LEN, CTX_DEEP, CTX_ENTRY = 0, 2, 6, 8, 10
CTX_LIVE, CTX_PB, CTX_API_SP, CTX_WHICH, CTX_DEPTH = 14, 16, 20, 22, 24
CTX_OWNER = 26                      # whose far blocks (phase 79)
CTX_SIZE = 28


def word(b, addr):
    d = bytes(b.memdump(addr, 2))
    return d[0] | (d[1] << 8)


def words(b, addr, n):
    d = bytes(b.memdump(addr, 2 * n))
    return [d[2 * i] | (d[2 * i + 1] << 8) for i in range(n)]


def main(argv):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    emu = launch(tag="m27", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)                # -> 65C816 (resets; DOS reboots)
        b.frames(500)
        for k in ("M", "2", "7", "RETURN"):
            b.key(k)
            b.frames(6)
        for _ in range(0, 3000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"CX\x01":
                break
        st = bytes(b.memdump(STATUS, 3))
        if not check(st == b"CX\x01",
                     f"the runner did not finish (status {st!r})"):
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "65C816", f"CPU is {cpu}")

        # The record's size, from the linker rather than from this file.
        c_root, c_a, c_b = syms["c_root"], syms["c_a"], syms["c_b"]
        span = sorted((c_root, c_a, c_b))
        check(span[1] - span[0] == CTX_SIZE and span[2] - span[1] == CTX_SIZE,
              f"CTX is not {CTX_SIZE} bytes: the records are at "
              f"{[hex(x) for x in span]}")

        # 1. the order of the turns
        nseq = word(b, syms["nseq"])
        seq = words(b, syms["seq"], min(nseq, 32))
        check(seq == WANT_SEQ,
              f"the turns ran {seq}, expected {WANT_SEQ}")
        print(f"  {nseq} turns, in order: "
              f"{' '.join('root' if s == 0 else 'A' if s == 1 else 'B'
                          if s == 2 else 'A-done' for s in seq)}")
        check(word(b, syms["rounds_a"]) == ROUNDS,
              f"context A took {word(b, syms['rounds_a'])} turns, not {ROUNDS}")
        check(word(b, syms["rounds_b"]) == ROUNDS + 1,
              f"context B took {word(b, syms['rounds_b'])} turns, "
              f"not {ROUNDS + 1}")

        # 2. the recursion's locals, level by level
        put = words(b, syms["deep_put"], DEEP)
        got = words(b, syms["deep_got"], DEEP)
        bad = word(b, syms["deep_bad"])
        check(put == got and bad == 0,
              f"{bad} frame(s) did not survive the switch: wrote {put}, "
              f"found {got}")
        print(f"  {DEEP} frames deep, every local intact across the yield "
              f"({put[0]:#06x}..{put[-1]:#06x})")

        # 3. nothing went wrong quietly
        check(word(b, syms["ctx_over"]) == 0,
              f"{word(b, syms['ctx_over'])} park(s) refused for want of room")
        check(word(b, syms["gem_reached"]) == 0,
              "a COP reached the gate's stub: the runner is not supposed "
              "to make one")

        # 4. what it cost
        for name, addr in (("root", c_root), ("A", c_a), ("B", c_b)):
            deep = word(b, addr + CTX_DEEP)
            live = word(b, addr + CTX_LIVE)
            print(f"  context {name}: {deep} bytes at its deepest park, "
                  f"live={live}")
        check(word(b, c_a + CTX_LIVE) == 2,
              "context A did not end marked done")
    finally:
        emu.stop()

    print(f"gem4xe-m27: {'PASS' if not fails else 'FAIL'} -- two contexts, "
          f"one stack, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
