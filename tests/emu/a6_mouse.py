#!/usr/bin/env python3
"""6502 gate: the pointer GEM4XE.CFG names, and the sampler's rate for it.

src/a6_cfg.c reads MOUSE= and MOUSEPORT= on a stock 6502; src/a6_tree.c
keeps the kind in ptr_state for a6_events' ptr_init and, for a quadrature
mouse, halves the sampler's divisor (IRQ6_DIV_QUAD, src/sys/irq.h).  Two
boots of build/a6-boot.atr, which carries no GEM4XE.CFG:

  as it is      an ST mouse, the standard port (2), divisor 63 -- and the
                timer counted at that rate, ~1 kHz
  with a file   written as somebody on a PC would -- CR LF, lower case,
                blanks, a comment, a key this build does not read -- that
                names a trak-ball in port 1: kind, port and divisor 127,
                ~500 Hz, as it says

    python3 tests/emu/a6_mouse.py
"""
import os
import re
import shutil
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
from atr import ATRImage, Dos2              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6-boot.atr"))
CDISK = os.path.abspath(os.path.join(ROOT, "build", "a6m-cfg.atr"))
MAP = os.path.join(ROOT, "build", "a6.map")
STATUS = 0x0600
# src/vdi/pointer.h
PTR_ST_MOUSE, PTR_TRAKBALL = 1, 3
PTR_PORT_1, PTR_PORT_2 = 0, 1
KIND_AT = 6                     # PTR_STATE: x, y, buttons, kind (WORDs)
DIV_AT, PAL_AT = 7, 8           # IRQ_INFO: timer_div, pal
CFG = (b"# written on a PC\r\n"
       b"  mouse = TrakBall   ; the CX80\r\n"
       b"VIDEO=ANTIC\r\n"
       b"MousePort=1\r\n")
# POKEY's 64 kHz clock, PAL and NTSC; frames a second
BASE = {1: 63337, 0: 63920}
FPS = {1: 49.86, 0: 59.92}


def run(disk, sym, check, label, want_kind, want_port, want_div):
    emu = launch(tag="a6m", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", disk])
    b = emu.bridge
    try:
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        st = bytes(b.memdump(STATUS, 3))
        if not check(st == b"A6K", f"{label}: A6 ran to its end (status {st!r})"):
            return
        kind = b.peek(sym("ptr_state") + KIND_AT)
        port = b.peek(sym("ptr_port"))
        div = b.peek(sym("irq") + DIV_AT)
        pal = b.peek(sym("irq") + PAL_AT)
        check((kind, port, div) == (want_kind, want_port, want_div),
              f"{label}: pointer kind {kind}, port {port + 1}, sampler divisor {div}; "
              f"want {want_kind}, {want_port + 1}, {want_div}")
        t = sym("irq_timer")

        def tick():
            return int.from_bytes(bytes(b.memdump(t, 4)), "little")
        t0 = tick()
        b.frames(100)
        got = tick() - t0
        want = BASE[pal] / (want_div + 1) * 100 / FPS[pal]
        check(abs(got - want) <= want * 0.03 + 2,
              f"{label}: the timer counted {got} in 100 frames; {want:.0f} at "
              f"divisor {want_div} ({BASE[pal] / (want_div + 1):.0f} Hz)")
    finally:
        emu.stop()


def main():
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-a6m: the pointer GEM4XE.CFG names, on a stock 6502")
    text = open(MAP).read()

    def sym(n):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", text, re.M).group(1), 16)

    run(DISK, sym, check, "no GEM4XE.CFG", PTR_ST_MOUSE, PTR_PORT_2, 63)

    shutil.copyfile(DISK, CDISK)
    img = ATRImage.load(CDISK)
    Dos2(img).add_file("GEM4XE.CFG", CFG)
    img.save(CDISK)
    run(CDISK, sym, check, "MOUSE=TRAKBALL, MOUSEPORT=1", PTR_TRAKBALL, PTR_PORT_1, 127)
    os.remove(CDISK)

    print(f"gem4xe-a6m: {'PASS' if not fails else 'FAIL'} -- the pointer GEM4XE.CFG "
          f"names, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
