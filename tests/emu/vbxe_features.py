#!/usr/bin/env python3
"""gem4xe clears the VBXE's FEATURE_CONTROL, and gives it back.

FX 1.27 added FEATURE_CONTROL ($D64B): the GTIA palette, XCOLOR, BLEND and
CLIP, which with D7 (PXGF) set survive a RESET -- so a program run before
gem4xe can leave them on.  gem4xe clears it when its screen goes on and
writes back what it found on the way out (src/vbxe/vbxe.c, features_*).

  1. the emulated VBXE is core 1.27, and FEATURE_CONTROL is set to $91
     (PXGF, XCOLOR, GTIA palette 1) before GEM.COM starts;
  2. with the desktop up, FEATURE_CONTROL reads 0;
  3. File -> Quit (Ctrl-Q) back to DUP, and it reads $91 again.

Without the change the desktop ran with $91 still set.

    python3 tests/emu/vbxe_features.py
"""
import os
import sys

os.environ["GEM4XE_VBXE"] = "127"      # before the launcher reads it
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile                              # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "gem-boot.atr")
SYMS = os.path.join(BUILD, "gem.sym")
FEATURE_CONTROL = 0xD64B
LEFT = 0x91                                 # PXGF | XCOLOR | GTIA palette 1


def wait_desk(b, syms):
    for _ in range(600):
        b.frames(10)
        if b.peek(syms["irq_cio_swap"]) in (1, 3) and b.peek16(syms["app_calls"]) > 30:
            b.frames(200)
            return True
    return False


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    syms = symfile.load(SYMS)
    emu = launch(tag="vbxefeat", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(5)
        core = (b.peek(0xD640) >> 4, b.peek(0xD641))
        print(f"  VBXE core {core[0]}.{core[1]:02X}")
        check(core == (1, 0x27), "the emulated VBXE is not core 1.27 "
              "(Altirra 4.50 test26 or later models it)")
        b.poke(FEATURE_CONTROL, LEFT)
        check(b.peek(FEATURE_CONTROL) == LEFT,
              f"FEATURE_CONTROL did not take ${LEFT:02X}")

        check(wait_desk(b, syms), "the desktop never started")
        on = b.peek(FEATURE_CONTROL)
        print(f"  with the desktop up: FEATURE_CONTROL ${on:02X}")
        check(on == 0, f"the desktop runs with FEATURE_CONTROL ${on:02X}, not 0")

        b.key("Q", ctrl=True)               # File -> Quit, back to DUP
        b.frames(900)
        off = b.peek(FEATURE_CONTROL)
        print(f"  back in DOS: FEATURE_CONTROL ${off:02X}")
        check(off == LEFT, f"on the way out it was left ${off:02X}, not "
              f"given back as ${LEFT:02X}")
    finally:
        emu.stop()

    print(f"gem4xe-vbxefeat: {'PASS' if not fails else 'FAIL'} -- FEATURE_CONTROL "
          f"cleared for the desktop and given back, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
