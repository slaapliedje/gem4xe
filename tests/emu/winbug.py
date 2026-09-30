"""The cartridge on Windows Altirra's 65C816 (make test-winbug).

Windows Altirra's 65C816, to 4.50-test21 at least, never clears the
IRQ shadow an SEI leaves in native mode: an IRQ that arrives as I is set
is taken at every fetch after, and the stack wraps through bank $00.
AltirraSDL fixed it in September (tools/altirra/README.md), which is why
no other gate can see it.  gem4xe 0.9.2 crashed on it within half a
minute on the AtariAge reporter's machine; since phase 82 gem4xe sets I
with a COP (src/sys/sei.s, irq_sei) and never with an SEI in native mode
(tests/host/test_sei.py holds the sources to that).

This boots the whole-system cartridge on that machine -- PAL 130XE,
1088K, VBXE, Rapidus, Atari's XL ROM -- in an AltirraSDL built with
tools/altirra/altirra-sdl-windows-irq-bug.patch (WINBUG), and asks for
the desktop, then two minutes more of it with the vertical blank, the
sampler and the shell all still counting and no fault.  0.9.2's
cartridge fails it; `WINBUG_CAR=build/gem4xe-0.9.2.car` shows that (the
symbols are this build's, so read the verdict, not the numbers).
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch  # noqa: E402
import symfile                      # noqa: E402

CAR = os.path.abspath(os.environ.get(
    "WINBUG_CAR", os.path.join(ROOT, "build", "gem4xe-sys.car")))
SYMS = os.path.join(ROOT, "build", "gem.sym")
SHOT = os.path.join(ROOT, "build", "shots", "winbug.png")


def main():
    exe = os.environ.get("WINBUG", "")
    if not os.path.isfile(exe):
        print(f"gem4xe-winbug: FAIL -- no emulator at WINBUG={exe!r}: build one "
              "with tools/altirra/altirra-sdl-windows-irq-bug.patch")
        return 1
    os.environ["ALTIRRASDL"] = exe          # read when the machine launches
    syms = symfile.load(SYMS)
    problems = []
    emu = launch(tag="winbug", memsize="1088K",
                 extra_args=["--hardware", "130xe", "--cart", CAR])
    b = emu.bridge
    try:
        runs = 0
        for _ in range(40):                 # 6,000 frames: two minutes
            b.frames(150)
            runs = b.peek16(syms["sh_runs"])
            if runs:
                break
        if not runs:
            problems.append("the desktop never ran")
        before = (b.peek16(syms["irq_frames"]),
                  int.from_bytes(bytes(b.memdump(syms["irq_timer"], 4)), "little"))
        b.frames(6000)
        after = (b.peek16(syms["irq_frames"]),
                 int.from_bytes(bytes(b.memdump(syms["irq_timer"], 4)), "little"))
        fault = b.peek(syms["irq_fault"])
        print(f"  shell runs {runs}; over 6,000 frames the VBI counted "
              f"{(after[0] - before[0]) & 0xFFFF}, the sampler "
              f"{after[1] - before[1]}; fault {fault}")
        if (after[0] - before[0]) & 0xFFFF < 5000:
            problems.append("the vertical blank stopped counting")
        if after[1] - before[1] < 6000:
            problems.append("the sampler stopped")
        if fault:
            problems.append(f"irq_fault {fault}")
        os.makedirs(os.path.dirname(SHOT), exist_ok=True)
        b.screenshot(SHOT)
    finally:
        emu.stop()
    for p in problems:
        print("  FAIL:", p)
    verdict = "FAIL" if problems else "PASS"
    print(f"gem4xe-winbug: {verdict} -- the cartridge on Windows Altirra's "
          f"65C816, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
