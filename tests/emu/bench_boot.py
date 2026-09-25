#!/usr/bin/env python3
"""How long the product floppies take to boot, and where the time goes.

    make bench-boot

Each product floppy is cold-booted with nothing typed, as test-boot does
(tests/emu/product_boot.py), and three stretches are timed in frames:

  A  reset to the CPU switch: the DOS boots and starts GEM.COM on the 6502,
     whose loader finds the Rapidus and switches it -- a reset, so the DOS
     starts GEM.COM again from the top
  B  the switch to the boot screen: GEM.COM read and its far image
     unpacked, then GEM starting up to the screen that says what it found
  C  the boot screen to the desktop: the screen is HELD three seconds on
     purpose (src/sys/bootinfo.c), then DESKTOP.PRG is read and drawn

With --profile, B is profiled and split into the loader's unpacker
(src/farload.s, bank $00 $9A05-$9B88 by the map), the OS ROM (SIO), and
everything else -- which says whether a smaller file or a faster unpacker
is the lever.  Not a gate.
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import product_boot                           # noqa: E402

BUILD = os.path.abspath(os.path.join(HERE, "..", "..", "build"))
SYMS = symfile.load(os.path.join(BUILD, "gem.sym"))
PROF = "--profile" in sys.argv
STEP = 5


def cpu(b):
    return b.cmd("HWSTATE").get("cpu", {}).get("mode")


def phase_b_profile(b, frames):
    b.ok("PROFILE_STOP")
    r = b.ok("PROFILE_DUMP top=4096")
    lo, hi = SYMS["_fl_copy"] & 0xFFFF, 0x9B88
    cyc = collections.Counter()
    for h in r["hot"]:
        a = int(str(h["addr"]).lstrip("$"), 16)
        if lo <= a <= hi:
            k = "unpacker (farload.s)"
        elif a >= 0xD800 or 0xC000 <= a < 0xD000:
            k = "OS ROM (SIO, CIO)"
        elif a < 0x2000:
            k = "DOS and page 6-7"
        else:
            k = "everything else"
        cyc[k] += h["cycles"]
    total = sum(cyc.values())
    print(f"      B profiled: {total / max(frames, 1):.0f} machine cycles a frame")
    for k, c in cyc.most_common():
        print(f"        {k:28s} {100 * c / total:5.1f}%")


def one(name, cart):
    disk = os.path.join(BUILD, name)
    size = os.path.getsize(os.path.join(BUILD, "gem.xex"))
    emu = launch(tag="benchboot", memsize="1088K",
                 extra_args=["--disk", disk] + (["--cart", cart] if cart else []))
    b = emu.bridge
    try:
        b.ok("COLD_RESET")
        f = 0
        while cpu(b) == "6502" and f < 20000:
            b.frames(STEP)
            f += STEP
        a = f
        if PROF:
            b.ok("PROFILE_START mode=insns")
        while not product_boot.boot_screen(b) and f < 30000:
            b.frames(STEP)
            f += STEP
        bb = f - a
        if PROF:
            phase_b_profile(b, bb)
        calls = SYMS["app_calls"]
        n, still, last = b.peek16(calls), 0, f
        while f < 40000:
            b.frames(STEP)
            f += STEP
            now = b.peek16(calls)
            if now != n:
                n, last = now, f
            elif now and f - last >= 100:
                break
        c = last - a - bb
        print(f"  {name}: A {a} + B {bb} + C {c} = {last} frames "
              f"({last / 50:.1f} s PAL); GEM.COM {size} bytes, "
              f"{size / max(bb, 1):.0f} bytes a frame through B")
    finally:
        emu.stop()


def main():
    sdx = next((a[6:] for a in sys.argv if a.startswith("--sdx=")), "")
    print("gem4xe boot time (not a gate)")
    one("gem-boot.atr", None)
    if sdx:
        one("gem-sdx.atr", sdx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
