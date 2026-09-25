#!/usr/bin/env python3
"""The ANTIC device, timed: text and a big rectangle (src/bench_antic.c).

    make bench-antic

Boots the runner on a machine with no VBXE, switches the CPU once the DOS
is idle at its prompt (a switch mid-boot is lost: tests/emu/m1_toolchain.py),
starts it, and then for each case sets GO and counts frames until DONE.
The runner draws each case REPS times over, so one frame of granularity is
a percent or two.  Not a gate: docs/phase54.md has what it measured.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
from m14_sparta import wait_prompt, screen    # noqa: E402
import collections                            # noqa: E402
import symfile                                # noqa: E402
import bench_vdi                              # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DISK = os.path.abspath(os.path.join(ROOT, "build", "bench-antic.atr"))
SYMS = os.path.abspath(os.path.join(ROOT, "build", "bench_antic.sym"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "bench_antic.map"))
PROF = "--profile" in sys.argv
STATUS = 0x0600
REPS = 4                                      # src/bench_antic.c
CASES = [(0, "text, replace, x=0   (26 lines x 53 chars)"),
         (1, "text, transparent, x=0"),
         (2, "text, replace, x=3 (unaligned)"),
         (3, "vr_recfl 300x150 solid")]


def profile(b, frames):
    """Where the case's time went, by function (the bank put back from the
    map: the profiler drops it; tests/emu/bench_desk.py says more)."""
    b.ok("PROFILE_STOP")
    r = b.ok("PROFILE_DUMP top=4096")
    syms = symfile.load(SYMS)
    ranges = bench_vdi.far_ranges(MAP)
    place = bench_vdi.placements(MAP)
    cyc = collections.Counter()
    for h in r["hot"]:
        a = int(str(h["addr"]).lstrip("$"), 16)
        fn = bench_vdi.where(place, syms, ranges, a)
        if 0xC000 <= a < 0xD000 or a >= 0xD800:
            fn = "OS ROM|" + fn
        cyc[fn] += h["cycles"]
    total = sum(cyc.values())
    print(f"      {total / frames:.0f} cycles a frame profiled")
    for fn, c in cyc.most_common(14):
        print(f"      {fn:44s} {100 * c / total:5.1f}%")


def main():
    emu = launch(tag="benchantic", memsize="1088K", vbxe=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        if wait_prompt(b) < 0:
            print("FAIL: no DOS prompt")
            return 1
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(50)
        if wait_prompt(b) < 0:
            print("FAIL: no DOS prompt after the switch")
            return 1
        for k in ("B", "E", "N", "C", "H", "A", "RETURN"):
            b.key(k)
            b.frames(6)
        for _ in range(0, 3000, 25):
            b.frames(25)
            if bytes(b.memdump(STATUS, 3)) == b"ABK":
                break
        else:
            print("FAIL: the runner did not come up", bytes(b.memdump(STATUS, 3)))
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        mcr = b.peek(STATUS + 6)
        print(f"  MCR after rapidus_speedup: ${mcr:02X}")
        if mcr == 0xFF:
            print("FAIL: bank $00 is still on the slow bus")
            return 1
        for case, what in CASES:
            b.poke(STATUS + 5, 0)
            b.poke(STATUS + 3, case)
            if PROF:
                b.ok("PROFILE_START mode=insns")
            b.poke(STATUS + 4, 1)
            f = 0
            while f < 20000:
                b.frames(1)
                f += 1
                if b.peek(STATUS + 5) == 0xA5:
                    break
            per = f * 20.0 / REPS
            print(f"  {what:44s} {per:8.1f} ms each")
            if PROF:
                profile(b, f)
    finally:
        emu.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
