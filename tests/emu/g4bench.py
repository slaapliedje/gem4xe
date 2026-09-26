#!/usr/bin/env python3
"""G4BENCH, run on both screens, and held to its reference.

    make g4bench            the numbers, and each against the reference
    make g4bench ARGS=--update   the reference rewritten from this run

src/apps/g4bench.c is an ordinary GEM program; this boots a DOS 2 disk on
which it IS the desktop (build/g4bench-boot.atr, DESKTOP.PRG), so the
shell runs it straight after the boot, once with a VBXE and once without.
The program's own g4b_done and g4b_us[] are read by symbol: its bank-$00
part lands where the loader says (`app_near`, src/sys/app.c), and a
symbol from its link translates as addr - link + base, as test-m22 reads
the clock's seconds.

A test more than TOLERANCE slower than tests/emu/g4bench_ref.json is a
failure: the reference is what 1.0's speed work has to beat, and what a
change must not lose (docs/roadmap-0.9.md).
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "g4bench-boot.atr")
G4A = os.path.join(BUILD, "g4bench.g4a")
REF = os.path.join(HERE, "g4bench_ref.json")
SHOTS = os.path.join(BUILD, "shots")
TOLERANCE = 0.10
NTESTS = 18                                   # src/apps/g4bench.c
NAMES = ["horizontal lines", "vertical lines", "diagonal lines",
         "filled boxes, solid", "filled boxes, pattern", "filled circles",
         "filled ellipses", "polygons", "rounded boxes",
         "text, 40 characters", "text, bold and underlined", "text, four heights",
         "blit screen to screen", "blit screen to memory, back", "icons",
         "draw a dialog", "open and close a window", "Mandelbrot"]
COUNTS = [200, 200, 100, 50, 50, 20, 20, 20, 20, 50, 50, 50, 50, 50, 100, 20, 10, 1]


def run(screen):
    gsym = symfile.load(os.path.join(BUILD, "gem.sym"))
    bsym = symfile.load(os.path.join(BUILD, "g4bench.sym"))
    with open(G4A, "rb") as f:
        link_near, = struct.unpack("<H", f.read(6)[4:6])
    emu = launch(tag=f"g4bench-{screen}", memsize="1088K", vbxe=(screen == "vbxe"),
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        f = 0
        while f < 20000:
            b.frames(50)
            f += 50
            if b.peek16(gsym["sh_runs"]) >= 1:
                break
        else:
            raise SystemExit(f"{screen}: the shell never ran G4BENCH")
        base = b.peek16(gsym["app_near"])
        done = bsym["g4b_done"] - link_near + base
        us = bsym["g4b_us"] - link_near + base
        while f < 60000:
            b.frames(50)
            f += 50
            if b.peek16(done) == 1:
                break
        else:
            raise SystemExit(f"{screen}: G4BENCH did not finish")
        b.frames(10)
        os.makedirs(SHOTS, exist_ok=True)
        b.screenshot(os.path.join(SHOTS, f"g4bench-{screen}.png"))
        raw = bytes(b.memdump(us, NTESTS * 4))
        return [struct.unpack_from("<i", raw, 4 * k)[0] for k in range(NTESTS)]
    finally:
        emu.stop()


def main(argv):
    update = "--update" in argv
    ref = json.load(open(REF)) if os.path.exists(REF) else {}
    new, slower = {}, []
    for screen in ("vbxe", "antic"):
        got = run(screen)
        new[screen] = got
        was = ref.get(screen)
        print(f"G4BENCH on {screen.upper()}, ms per call"
              f"{' (reference, change)' if was else ''}:")
        for k in range(NTESTS):
            ms = got[k] / COUNTS[k] / 1000
            line = f"  {NAMES[k]:30s} {ms:9.3f}"
            if was:
                r = was[k] / COUNTS[k] / 1000
                ch = (got[k] - was[k]) / was[k] * 100 if was[k] else 0
                line += f"   {r:9.3f}  {ch:+6.1f}%"
                if got[k] > was[k] * (1 + TOLERANCE):
                    slower.append(f"{screen} {NAMES[k]}: {ch:+.1f}%")
                    line += "  SLOWER"
            print(line)
        print(f"  {'all of it, once':30s} {sum(got) / 1000:9.0f} ms")
    if update:
        with open(REF, "w") as f:
            json.dump(new, f, indent=1)
        print(f"reference written: {REF}")
        return 0
    if slower:
        print("FAIL: slower than the reference by more than "
              f"{int(TOLERANCE * 100)}%: " + "; ".join(slower))
        return 1
    print("PASS: G4BENCH" + (" within the reference" if ref else ", no reference yet"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
