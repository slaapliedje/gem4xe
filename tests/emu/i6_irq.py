#!/usr/bin/env python3
"""6502 step 4d gate: gem4xe's interrupt handlers on a stock 6502.

test-m10's checks (tests/emu/m10_irq.py) for src/sys6502/irq6502.s and
irq6502.c, which chain the OS's RAM vectors instead of copying its ROM.
build/i6-boot.atr carries src/i6_irq.c:

  the vectors    VVBLKI and VIMIRQ hold the handlers the linker placed
                 (build/i6.map), and what they held before is kept
  the VBI        irq_frames advances by exactly the frames the emulator ran
  the timer      irq_timer advances at POKEY's rate for the divisor the
                 runner reports, the frame's length from the machine's
                 video standard
  the keyboard   one KEY becomes one entry in the handler's ring, with
                 KBCODE's value, and never reaches the OS's CH
  the pointer    the CX80 trak-ball, selected through src/vdi/pointer.c,
                 counted by the handler while the runner polls nothing
  the cost       loop turns per frame with and without the handlers, the
                 pointer still: printed, and held under 10% of the machine
  the way back   asked to, the runner removes them: both vectors as they
                 were, timer 1 off, irq_frames still, and a typed key in
                 CH -- the OS's keyboard IRQ running again

What JOY can drive: see m10_irq.py -- +x pulses with the direction line
high.  The decode itself is tests/host/test_pointer.py's.

    python3 tests/emu/i6_irq.py
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "i6-boot.atr"))
MAP = os.path.join(ROOT, "build", "i6.map")
STATUS = 0x0600
VIMIRQ, VVBLKI, POKMSK, CH = 0x0216, 0x0222, 0x0010, 0x02FC
IRQ_OS_CHAINED = 3
# IRQ_INFO, src/sys/irq.h: how, fail, portb_before, mcr_before, fast, via,
# bad_byte, timer_div, pal
IRQ_HOW, IRQ_TIMER_DIV, IRQ_PAL = 0, 7, 8
KB_A = 0x3F
# CPU cycles in a frame: 114 a line, 262 lines NTSC, 312 PAL; POKEY's
# 64 kHz clock is the CPU's over 28
FRAME = {0: 114 * 262, 1: 114 * 312}


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

    print("gem4xe-i6: gem4xe's interrupt handlers, on a stock 6502")
    sym = symbols()
    emu = launch(tag="i6", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge

    def word(a):
        d = bytes(b.memdump(a, 2))
        return d[0] | (d[1] << 8)

    def long(a):
        d = bytes(b.memdump(a, 4))
        return int.from_bytes(d, "little")

    try:
        b.frames(300)
        for _ in range(0, 3000, 25):
            b.frames(25)
            if bytes(b.memdump(STATUS, 3)) == b"I6R":
                break
        if not check(bytes(b.memdump(STATUS, 3)) == b"I6R", "the runner installed and measured"):
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "6502", f"the CPU is a 6502 ({cpu})")
        irq = sym["irq"]
        check(b.peek(irq + IRQ_HOW) == IRQ_OS_CHAINED,
              f"irq.how is IRQ_OS_CHAINED ({b.peek(irq + IRQ_HOW)})")

        # -- the vectors ------------------------------------------------------
        old_vbi, old_irq = word(sym["irq6_old_vbi"]), word(sym["irq6_old_irq"])
        check(word(VVBLKI) == sym["irq6_vbi"], f"VVBLKI is the VBI handler "
              f"(${word(VVBLKI):04X}, ${sym['irq6_vbi']:04X})")
        check(word(VIMIRQ) == sym["irq6_irq"], f"VIMIRQ is the IRQ handler "
              f"(${word(VIMIRQ):04X}, ${sym['irq6_irq']:04X})")
        check(old_vbi >= 0xC000 and old_irq >= 0xC000,
              f"what they held kept: the OS's ${old_vbi:04X} and ${old_irq:04X}")
        check(b.peek(POKMSK) & 0x41 == 0x41, f"POKMSK has timer 1 and the keyboard "
              f"(${b.peek(POKMSK):02X})")

        # -- the VBI and the timer --------------------------------------------
        f0, t0 = word(sym["irq_frames"]), long(sym["irq_timer"])
        b.frames(100)
        f1, t1 = word(sym["irq_frames"]), long(sym["irq_timer"])
        check(((f1 - f0) & 0xFFFF) == 100, f"irq_frames advanced {(f1 - f0) & 0xFFFF} "
              f"in 100 frames")
        div, pal = b.peek(irq + IRQ_TIMER_DIV), b.peek(irq + IRQ_PAL)
        want = 100 * FRAME[pal] / (28 * (div + 1))
        got = t1 - t0
        check(abs(got - want) <= want * 0.02,
              f"irq_timer advanced {got} in 100 frames; POKEY's rate for divisor "
              f"{div} on {'PAL' if pal else 'NTSC'} is {want:.0f} "
              f"({want / 100 * (50 if pal else 60):.0f} Hz)")

        # -- the keyboard -----------------------------------------------------
        b.poke(CH, 0xFF)
        k0 = b.peek(sym["irq_kb_count"])
        b.key("A")
        b.frames(5)
        k1 = b.peek(sym["irq_kb_count"])
        tail = b.peek(sym["irq_kb_tail"])
        code = b.peek(sym["irq_kb"] + ((tail - 1) & 7))
        check(((k1 - k0) & 0xFF) == 1 and code == KB_A,
              f"KEY A: one key in the ring, KBCODE ${code:02X} (count +{(k1 - k0) & 0xFF})")
        check(b.peek(CH) == 0xFF, f"...and not in the OS's CH (${b.peek(CH):02X})")

        # -- the trak-ball ----------------------------------------------------
        b.joy(1, "centre")
        b.frames(2)
        x0, y0 = word(sym["irq_qlo"]), word(sym["irq_qhi"])
        # test-m10's pulses: 20 changes on the x pulse line, 10 on y's, one
        # a frame
        for i in range(20):
            b.joy(1, "down" if i % 2 == 0 else "centre")
            b.frames(1)
        for i in range(10):
            b.joy(1, "right" if i % 2 == 0 else "centre")
            b.frames(1)
        dx = (word(sym["irq_qlo"]) - x0) & 0xFFFF
        dy = (word(sym["irq_qhi"]) - y0) & 0xFFFF
        check((dx, dy) == (20, 10), f"the trak-ball counted by the handler, the runner "
              f"polling nothing: +{dx} on x, +{dy} on y (want +20, +10)")

        # -- the cost ---------------------------------------------------------
        a, g = word(sym["turns_os"]), word(sym["turns_gem"])
        share = 1 - g / a if a else 1
        check(a and share < 0.10, f"loop turns a frame: {a} under the OS alone, {g} "
              f"with gem4xe's handlers, the pointer still -- they take {share:.1%} "
              f"of the machine")

        # -- the way back -----------------------------------------------------
        b.poke(STATUS + 4, 1)
        b.frames(10)
        check(b.peek(STATUS + 5) == ord("X"), "the runner removed the handlers")
        check(word(VVBLKI) == old_vbi and word(VIMIRQ) == old_irq,
              f"both vectors as they were (${word(VVBLKI):04X}, ${word(VIMIRQ):04X})")
        check(b.peek(POKMSK) & 0x01 == 0, f"timer 1 off (POKMSK ${b.peek(POKMSK):02X})")
        f2 = word(sym["irq_frames"])
        b.frames(20)
        check(word(sym["irq_frames"]) == f2, "irq_frames no longer counts")
        b.poke(CH, 0xFF)
        b.key("A")
        b.frames(5)
        check(b.peek(CH) == KB_A, f"a typed key reaches the OS's CH again (${b.peek(CH):02X})")
    finally:
        emu.stop()
    print(f"gem4xe-i6: {'PASS' if not fails else 'FAIL'} -- gem4xe's interrupt handlers, "
          f"on a stock 6502, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
