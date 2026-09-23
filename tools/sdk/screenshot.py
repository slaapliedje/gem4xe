#!/usr/bin/env python3
"""Boot a gem4xe disk under AltirraSDL and photograph it.

    python3 tools/screenshot.py gem4xe-0.6.1.atr desk.png
    python3 tools/screenshot.py gem4xe-0.6.1.atr late.png --frames 4000

WHAT IT IS FOR.  Testing a program on this machine otherwise means
watching a screen, and a person watching a screen is not a mechanism.
This boots the machine with nothing typed, waits, and writes a PNG --
which is enough to run in a loop, keep beside a known-good picture, and
diff.  Four of gem4xe's own bugs were found by looking at a picture and
by nothing else, so this is not a lesser kind of test.

IT IS ALSO THE SMALLEST WORKED EXAMPLE of the harness in tools/a8test/,
which is the whole thing gem4xe's own gates are built on: launch() puts
up a machine with the right boards and a control socket, and the Bridge
drives it -- frames(), key(), joy(), peek(), poke(), memdump(),
screenshot(). Read this, then read a gate in the gem4xe source tree.

THE MACHINE IT MAKES is the one gem4xe requires: PAL 800XL, 1088K, a
VBXE at FX 1.26 and a Rapidus, with `--diskemu generic` and
`--nofastboot` because the SpartaDOS disk will not boot without them.
launch() sets all of that; you do not pass it.

YOU NEED AltirraSDL, and a build with the 65C816 native-mode fixes --
the release page says which, and points `ALTIRRASDL` at it:

    ALTIRRASDL=~/dev/altirra-patched/AltirraSDL python3 tools/screenshot.py ...

A BLUE SCREEN OF "BOOT ERROR" IS NOT A BUG.  The release's own
`gem-sdx.atr` carries no DOS on purpose -- it boots under SpartaDOS X,
which lives in the machine rather than on the disk -- so it needs
`--cart` pointing at an SDX cartridge image.  The release page says
where to get one.

THE FRAME COUNT IS THE THING TO TUNE.  A Rapidus cold-boots as a 6502;
gem4xe's loader notices, switches the CPU and restarts, so the desktop
is some thousands of frames away.  2600 is enough for the desk on this
machine.  If you get a black picture, ask for more frames before you
suspect your program.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch                      # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(__doc__.splitlines()[1:]))
    ap.add_argument("image", help="a gem4xe .atr to boot")
    ap.add_argument("out", help="where to write the PNG")
    ap.add_argument("--frames", type=int, default=2600,
                    help="how long to wait before the picture (default 2600)")
    ap.add_argument("--disk2", help="a second drive, for your own work")
    ap.add_argument("--cart", help="a cartridge image -- SpartaDOS X, if "
                                   "you are booting the release's own "
                                   "gem-sdx.atr, which carries no DOS")
    a = ap.parse_args(argv[1:])

    extra = ["--disk", os.path.abspath(a.image)]
    if a.disk2:
        extra += ["--disk", os.path.abspath(a.disk2)]
    if a.cart:
        extra += ["--cart", os.path.abspath(a.cart)]

    emu = launch(tag="shot", memsize="1088K", extra_args=extra)
    try:
        emu.bridge.frames(a.frames)
        emu.bridge.screenshot(os.path.abspath(a.out))
    finally:
        emu.stop()
    print(f"{a.out}: written after {a.frames} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
