#!/usr/bin/env python3
"""How long gem4xe takes to boot, and where the time goes.

    make bench-boot

Each way in is cold-booted with nothing typed, as test-boot does
(tests/emu/product_boot.py): the DOS 2 floppy, the system floppy on its own
G4DOS, the same floppy under SpartaDOS X when fixtures.toml names the
cartridge, and gem4xe's own cartridge.  Three stretches are timed in frames:

  A  reset to the CPU switch: the DOS boots and starts GEM.COM on the 6502,
     whose loader finds the Rapidus and switches it -- a reset, so the DOS
     starts GEM.COM again from the top
  B  the switch to the boot screen: GEM.COM read and its far image
     unpacked, then GEM starting up to the screen that says what it found
  C  the boot screen to the desktop: the screen is HELD three seconds on
     purpose (src/sys/bootinfo.c), then DESKTOP.PRG is read and drawn

With --profile, B is profiled and split into the loader's unpacker
(src/farload.s: its bank-$00 part, and everything above bank $00, which is
the fast copy -- given the bank, from the patched emulator), the OS ROM, and
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
SYMS = {b: symfile.load(os.path.join(BUILD, b + ".sym")) for b in ("gem", "gem-dos2")}
PROF = "--profile" in sys.argv
STEP = 5


def cpu(b):
    return b.cmd("HWSTATE").get("cpu", {}).get("mode")


def phase_b_profile(b, frames):
    b.ok("PROFILE_STOP")
    r = b.ok("PROFILE_DUMP top=4096")
    lo, hi = SYMS["gem"]["_fl_copy"] & 0xFFFF, 0x9B88
    cyc = collections.Counter()
    for h in r["hot"]:
        a = int(str(h["addr"]).lstrip("$"), 16)
        # With the bank (the patched emulator's addr24), the unpacker is
        # simply anything running above bank $00 while the image loads: it
        # runs in the fast bank above the image (src/farload.s).
        bank = int(str(h.get("addr24", "$0")).lstrip("$"), 16) >> 16
        if bank or lo <= a <= hi:
            k = "unpacker (farload.s)"
        elif a >= 0xD800 or 0xC000 <= a < 0xD000:
            k = "OS ROM (SIO, CIO)"
        elif 0xA000 <= a < 0xC000:
            k = "cartridge ROM (its D1:)"
        elif a < 0x2000:
            k = "DOS and page 6-7"
        else:
            k = "everything else"
        cyc[k] += h["cycles"]
    total = sum(cyc.values())
    print(f"      B profiled: {total / max(frames, 1):.0f} machine cycles a frame")
    for k, c in cyc.most_common():
        print(f"        {k:28s} {100 * c / total:5.1f}%")


def one(label, name, cart):
    """name is the floppy in D1, or None; cart is a .car, or None."""
    base = product_boot.gem_build(name) if name else "gem"
    size = os.path.getsize(os.path.join(BUILD, base + ".xex"))
    args = ["--disk", os.path.join(BUILD, name)] if name else []
    emu = launch(tag="benchboot", memsize="1088K",
                 extra_args=args + (["--cart", cart] if cart else []))
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
        calls = SYMS[base]["app_calls"]
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
        print(f"  {label}: A {a} + B {bb} + C {c} = {last} frames "
              f"({last / 50:.1f} s PAL); GEM.COM {size} bytes, "
              f"{size / max(bb, 1):.0f} bytes a frame through B")
    finally:
        emu.stop()


def main():
    sdx = next((a[6:] for a in sys.argv if a.startswith("--sdx=")), "")
    print("gem4xe boot time (not a gate)")
    one("DOS 2.0S, gem-boot.atr", "gem-boot.atr", None)
    one("G4DOS, gem-sdx.atr alone", "gem-sdx.atr", None)
    if sdx:
        one("SpartaDOS X, gem-sdx.atr", "gem-sdx.atr", sdx)
    one("the cartridge, gem4xe-sys.car", None,
        os.path.join(BUILD, "gem4xe-sys.car"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
