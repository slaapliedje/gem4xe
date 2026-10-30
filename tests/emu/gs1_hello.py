#!/usr/bin/env python3
"""GSlayer milestone 1: an Apple IIGS Toolbox program runs on gem4xe and
draws what Apple's own Toolbox draws (docs/gslayer.md).

HELLO.S16 is tests/iigs/gshello.c built with ORCA/C -- an unmodified GS/OS
application.  It runs twice:

  - on MAME's apple2gs, booting System 6.0.4 with HELLO.S16 as its
    SYSTEM:START, against Apple's ROM Toolbox (tests/iigs/shrdump.lua);
  - on gem4xe, run by GSLAYER.PRG (src/gslayer), whose Toolbox is written
    from the Apple IIGS Toolbox Reference.

Both leave "GSDONE" at $E1:9DF0 when the drawing is finished, and the gate
compares the whole Super Hi-Res area, $E1:2000-$E1:9FFF:

  - every pixel outside the two lines of text, every SCB byte and palette
    0 must be EQUAL -- ClearScreen, PaintRect, FrameRect and QDStartUp's
    SCBs and colour table, byte for byte;
  - the two lines of text are compared by WHERE the ink is, not by its
    shape: GSlayer draws in gem4xe's 8x8 font, because Shaston 8 is
    Apple's, in Apple's ROM (src/gslayer/gsqd.c);
  - palettes 1-15 are not compared: QDStartUp sets only palette 0, and
    the rest hold what MAME's memory held at power-on ($DDDD).

No ORCA/C (tools/orca.sh), no MAME, no apple2gs ROM set or no System 6.0.4
disk image is a SKIP, said, not a pass.

    python3 tests/emu/gs1_hello.py
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import mkg4a                                  # noqa: E402

BUILD = os.path.join(ROOT, "build")
PROG = os.path.join(BUILD, "iigs", "HELLO.S16")
DISK = os.path.join(BUILD, "gs1-boot.atr")
SYSDISK = os.environ.get("GS_SYSDISK",
                         os.path.expanduser("~/dev/toolchains/iigs/sys604.hdv"))
ROMS = os.environ.get("GS_ROMPATH", os.path.expanduser("~/.mame/roms"))
MAME = shutil.which("mame")

SIG = b"GSDONE"
SIG_AT = 0x7DF0                     # $E1:9DF0, inside the dump
SCB, PAL = 0x7D00, 0x7E00
# The two lines of text in gshello.c: MoveTo(320, 60) and (320, 80),
# drawn inside the frame (300,30)-(600,150), whose edges are x 300 and
# 599 (FrameRect draws inside the rect).  The mask is the rows a font of up
# to 10 pixels above the baseline and 3 below could touch, and the whole
# bytes clear of the frame's edges -- so the edges stay compared exactly.
TEXT = [(60, 50, 63), (80, 70, 83)]   # baseline, first row, last row
TEXT_X = (304, 595)


def skip(why):
    print(f"gem4xe-gs1: SKIP -- {why}")
    return 0


def mame_reference():
    """Apple's Toolbox's screen for HELLO.S16, from MAME, cached by the
    program's and the system disk's contents."""
    key = hashlib.sha256(open(PROG, "rb").read()
                         + open(SYSDISK, "rb").read(1 << 20)).hexdigest()[:16]
    ref = os.path.join(BUILD, "iigs", f"hello-ref-{key}.shr")
    if os.path.exists(ref):
        return ref
    run = os.path.join(BUILD, "iigs", "mame-run")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    hdv = os.path.join(run, "sys.hdv")
    shutil.copyfile(SYSDISK, hdv)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "prodos.py"),
                    "put", hdv, "/SYSTEM/START", PROG, "--type", "0xB3",
                    "--aux", "0xDB03"], check=True, stdout=subprocess.DEVNULL)
    out = os.path.join(run, "shr.bin")
    env = dict(os.environ, GS_OUT=out, GS_LIMIT="120")
    subprocess.run([MAME, "apple2gs", "-rompath", ROMS, "-sl7", "cffa2",
                    "-hard1", hdv, "-video", "none", "-sound", "none",
                    "-nothrottle", "-skip_gameinfo", "-autoboot_script",
                    os.path.join(ROOT, "tests", "iigs", "shrdump.lua")],
                   env=env, cwd=run, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=600)
    if not os.path.exists(out):
        return None
    shutil.copyfile(out, ref)
    return ref


def ink_rows(shr, first, last, x0, x1):
    """Rows of a 640-mode screen with any pixel not white (3) in x0..x1."""
    rows = set()
    for y in range(first, last + 1):
        for x in range(x0, x1 + 1):
            b = shr[y * 160 + x // 4]
            if (b >> (6 - 2 * (x & 3))) & 3 != 3:
                rows.add(y)
                break
    return rows


def masked(o):
    if o >= PAL + 32:
        return True                 # palettes 1-15: MAME's power-on RAM
    if o < SCB:
        y, x0 = divmod(o, 160)
        for _, first, last in TEXT:
            if first <= y <= last and TEXT_X[0] // 4 <= x0 <= TEXT_X[1] // 4:
                return True
    return False


def main():
    print("gem4xe-gs1: an Apple IIGS Toolbox program on GSlayer")
    if not os.path.exists(PROG):
        return skip("no HELLO.S16: ORCA/C (Golden Gate, tools/orca.sh) is not installed")
    if not MAME:
        return skip("no MAME on PATH")
    if not os.path.exists(os.path.join(ROMS, "apple2gs.zip")):
        return skip(f"no apple2gs ROM set in {ROMS}")
    if not os.path.exists(SYSDISK):
        return skip(f"no System 6.0.4 disk image at {SYSDISK}")
    fails = []

    def check(ok, what):
        print(f"  {'ok' if ok else 'FAIL'}: {what}")
        if not ok:
            fails.append(what)

    ref_path = mame_reference()
    if not ref_path:
        check(False, "MAME never signalled GSDONE: no reference to compare with")
        return 1
    ref = open(ref_path, "rb").read()
    check(ref[SIG_AT:SIG_AT + 6] == SIG, "Apple's Toolbox ran HELLO.S16 to its end on MAME")

    g = symfile.load(os.path.join(BUILD, "gem.sym"))
    ps = symfile.load(os.path.join(BUILD, "gslayer.sym"))
    link_near, = struct.unpack("<H", mkg4a.read_file(
        os.path.join(BUILD, "gslayer.g4a"))[4:6])
    emu = launch(tag="gs1", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        f, near, shr = 0, 0, None
        while f < 6000:
            b.frames(100)
            f += 100
            near = b.peek16(g["app_near"])
            if bytes(b.memdump(0xE19DF0, 6)) == SIG:
                b.frames(50)        # as shrdump.lua waits a second
                shr = bytes(b.memdump(0xE12000, 0x8000))
                break
        sv = (lambda n: b.peek16(ps[n] - link_near + near)) \
            if 0x4000 <= near < 0x8000 else (lambda n: -1)
        why, what = sv("gs_why"), sv("gs_what")
        print(f"  GSlayer near ${near:04X}, stage {sv('gs_stage')}, "
              f"last call ${sv('gs_x') & 0xFFFF:04X}, stop reason {why} "
              f"(${what & 0xFFFF:04X})")
        check(shr is not None, f"HELLO.S16 drew to its end on gem4xe ({f} frames)")
        check(why == 0, "no call it made went unserved")
        check(b.peek(g["irq_fault"]) == 0, "nothing faulted (irq_fault 0)")
    finally:
        emu.stop()
    if shr is None:
        print(f"gem4xe-gs1: FAIL -- {len(fails)} problem(s)")
        return 1

    diff = [o for o in range(0x8000) if ref[o] != shr[o] and not masked(o)]
    pix = [o for o in diff if o < SCB]
    print(f"  {len(diff)} bytes differ outside the masks "
          f"({len(pix)} of pixels)")
    for o in diff[:8]:
        print(f"    +${o:04X}: Apple ${ref[o]:02X}, GSlayer ${shr[o]:02X}")
    check(not pix, "every pixel outside the text is Apple's: ClearScreen, "
          "PaintRect, FrameRect")
    check(shr[SCB:SCB + 0xF0] == ref[SCB:SCB + 0xF0],
          "QDStartUp's SCBs, all 256 bytes of the page as Apple's leaves them")
    check(shr[PAL:PAL + 32] == ref[PAL:PAL + 32],
          "palette 0: the standard 640-mode colour table")
    for base, first, last in TEXT:
        a = ink_rows(ref, first, last, *TEXT_X)
        s = ink_rows(shr, first, last, *TEXT_X)
        check(bool(a) and bool(s) and max(s) <= base and max(a) <= base + 3,
              f"the text at baseline {base} is drawn there on both "
              f"(Apple rows {min(a, default=0)}-{max(a, default=0)}, "
              f"GSlayer {min(s, default=0)}-{max(s, default=0)})")
    print(f"gem4xe-gs1: {'FAIL' if fails else 'PASS'} -- a IIGS Toolbox program "
          f"on gem4xe, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
