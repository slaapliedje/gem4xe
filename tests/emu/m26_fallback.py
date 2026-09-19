#!/usr/bin/env python3
"""Phase 34 gate: ONE BINARY, TWO SCREENS.

GEM.COM carries both VDI devices (src/vdi/vdidev.h) and decides which
one draws when it starts.  There is no second build, no second disk and
no second desktop: the same 120 KB image comes up at 640x240 in sixteen
colours on a machine with a VBXE and at 320x168 in two on one without,
and a line in GEM4XE.CFG overrides either way.

Three boots, and nothing is typed in any of them -- the disks start GEM
themselves, the way a user's would:

  auto-vbxe   the shipped disk, a machine WITH a VBXE.  Every setting in
              GEM4XE.CFG is commented out, so this is what the common
              machine does with no file at all: 640x240, four planes,
              the 8x8 face.
  auto-antic  the shipped disk, a machine WITHOUT one.  Nothing on the
              disk changed; the machine did.  320x168, one plane,
              Atari's condensed 6x6.
  safe-mode   the same disk with VIDEO=ANTIC in GEM4XE.CFG, on a machine
              that HAS a VBXE.  This is the case the file exists for: a
              monitor that will not lock to the VBXE's output leaves the
              user with no screen to put a dialog on, so the way out has
              to be a plain text file they can edit from the DOS prompt.
              The override has to beat a working VBXE, or it is not a way
              out.

What is checked, in the order it is worth checking:

  WHICH DEVICE the VDI is actually on -- `vdev` against the two tables'
  own addresses, read out of the linker's symbols.  This is the claim
  itself and everything else is a consequence of it;

  WHAT THE AES MADE OF IT -- gl_width, gl_height, gl_nplanes, gl_wchar
  and gl_hchar, which gsx_start asks the VDI for and every dialog,
  window and menu on the screen is laid out from.  A GEM that reached
  the right device and then laid out for the other one would draw off
  the edge of the screen and this is what would say so;

  WHAT THE FILE SAID -- `config` itself, so that a safe-mode boot that
  came up on ANTIC because the parser silently failed and something else
  fell back cannot pass as a safe-mode boot that worked;

  THE DESK ITSELF, pixel for pixel against tools/deskref.py -- the
  desktop's own model, run on tools/devref.py's ANTIC device.  It is the
  same model test-boot compares the VBXE desks against and the same one
  test-m17 drives through a whole session; what changes is one argument.
  Neither deskref, aesref nor vdiref was written for a 320x168 screen
  with two colours and neither was edited for one: they ask the VDI what
  the device is, the way src/aes/graf.c's gsx_start does, and lay out on
  the answer;

  and the two ANTIC screens AGAINST EACH OTHER, pixel for pixel.  Same
  binary, same disk, same device, reached two different ways: if the
  override is really just "pick the other table", they are identical,
  and any difference is the override doing something else as well.

The VBXE case is not compared here -- tests/emu/product_boot.py already
does that, against the same model, on the same disk.

  python3 tests/emu/m26_fallback.py [--shot]
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import atr, devref, symfile                 # noqa: E402
from anticref import AN_W, AN_H             # noqa: E402
from product_boot import (desk_model, dos2_listing,   # noqa: E402
                          DRVBYT, DOS_2, FARMEM_BRK)
from vbxeref import (SCR_W as VB_W, SCR_H as VB_H,   # noqa: E402
                     SHOT_X0 as VB_X0, SHOT_Y0 as VB_Y0)

BUILD = os.path.join(ROOT, "build")
SYMS = os.path.join(BUILD, "gem.sym")
SHOTDIR = os.path.join(BUILD, "shots")

# The playfield's top left in a screenshot.  The two devices do not put it
# in the same place -- the VBXE's overlay starts at the border's edge and
# ANTIC's playfield is inset -- so each is taken from the gate that already
# compares pixels there (tests/emu/m25_antic_vdi.py, tools/vbxeref.py).
AN_X0, AN_Y0 = 8, 24

CFG_VIDEO_AUTO, CFG_VIDEO_VBXE, CFG_VIDEO_ANTIC = 0, 1, 2

# (tag, disk, is there a VBXE in the machine, what GEM4XE.CFG says,
#  which device must win, and what the AES must lay out for)
#
#   width, height, planes, cell width, cell height
ANTIC_GEOM = (AN_W, AN_H, 1, 6, 6)
VBXE_GEOM = (VB_W, VB_H, 4, 8, 8)

CASES = [
    ("auto-vbxe",  "gem-boot.atr",  True,  CFG_VIDEO_AUTO,  "vbxe",  VBXE_GEOM),
    ("auto-antic", "gem-boot.atr",  False, CFG_VIDEO_AUTO,  "antic", ANTIC_GEOM),
    ("safe-mode",  "gem-antic.atr", True,  CFG_VIDEO_ANTIC, "antic", ANTIC_GEOM),
]

STEP = 20                       # frames between CPU reads while it switches
SETTLE = 250                    # ...and between call-counter reads after


# THE MACHINE CHANGES THE SCREENSHOT, NOT THE SCREEN.  With a VBXE fitted
# Altirra emits a 672-pixel-wide frame -- the overlay's widest HR mode --
# whether or not the overlay is on, so an ANTIC playfield pixel is TWO
# screenshot pixels wide there and one on a machine without.  The picture
# is the same picture; only the sampling differs, which is exactly what
# the safe-mode case has to see through to compare itself with the
# auto case.
NARROW = 336                    # the frame's width with no VBXE in the machine


def sampling(im, dev):
    """(x0, xstep) for reading the device's playfield out of this shot."""
    step = 2 if im.width >= 2 * NARROW else 1
    return (VB_X0, 1) if dev == "vbxe" else (AN_X0 * step, step)


def colours(px, x0, y0, w, h, step=1):
    return {px[x0 + x * step, y0 + y] for y in range(h) for x in range(w)}


def pixels(px, x0, y0, w, h, step=1):
    return [px[x0 + x * step, y0 + y] for y in range(h) for x in range(w)]


def one(tag, disk, has_vbxe, want_cfg, want_dev, geom, syms, keep, check):
    """One boot, start to desk, with nothing typed."""
    path = os.path.abspath(os.path.join(BUILD, disk))
    print(f"{tag}: {disk}, VBXE {'in' if has_vbxe else 'NOT in'} the machine")
    emu = launch(tag=f"m26-{tag}", memsize="1088K", vbxe=has_vbxe,
                 extra_args=["--disk", path])
    b = emu.bridge
    try:
        # The disk boots on the 6502, the DOS starts GEM, and the loader
        # switches the CPU and lets the machine come up again
        # (src/farload.s; tests/emu/product_boot.py has the long version).
        # The machine runs free until the bridge connects -- some 50 to
        # 100 frames, on the phase of a 300 ms poll -- and the switch
        # comes about 100 frames in, so the first look is taken from a
        # cold reset, which the Rapidus always comes out of as a 6502.
        b.ok("COLD_RESET")
        was = b.cmd("HWSTATE").get("cpu", {}).get("mode")
        check(was == "6502", f"{tag}: the machine did not start as a 6502 ({was})")
        for t in range(0, 20000, STEP):
            b.frames(STEP)
            if b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502":
                break
        else:
            check(False, f"{tag}: the loader never switched the CPU")
            return None

        n, still = b.peek16(syms["gem_calls"]), 0
        for t in range(0, 20000, SETTLE):
            b.frames(SETTLE)
            now = b.peek16(syms["gem_calls"])
            still = still + 1 if now == n else 0
            n = now
            if still >= 2 and now:
                break
        else:
            check(False, f"{tag}: GEM never settled ({n} calls)")
            return None
        fault = b.peek(syms["irq_fault"])
        check(fault == 0, f"{tag}: irq_fault {fault} (src/sys/irq.s)")
        print(f"  the machine switched itself and GEM settled, {n} calls in")

        # -- what the file said ------------------------------------------
        got_cfg = b.peek16(syms["config"])
        check(got_cfg == want_cfg,
              f"{tag}: config.video is {got_cfg}, not {want_cfg} -- "
              f"GEM4XE.CFG was not read the way it reads")

        # -- which device ------------------------------------------------
        # A far pointer, four bytes with the top one unused.
        raw = bytes(b.memdump(syms["vdev"], 4))
        got = int.from_bytes(raw, "little") & 0xFFFFFF
        # WHICH table, and it is no longer one symbol each: the VBXE has
        # nine (three widths by three heights, src/vdi/dev_vbxe.c) and
        # `vdev` points at one of them.  So the check is on the table
        # ITSELF rather than on its address -- the first three words of a
        # VDIDEV are the width, the height and the stride -- plus that it
        # lies inside the right object.  That is exact without the gate
        # having to know sizeof(VDIDEV), and it is the property that
        # actually matters: the seam reports the screen it is on.
        tab = syms["vdev_vbxe_tab"]
        antic = syms["vdev_antic"]
        w, h, stride = (int.from_bytes(bytes(b.memdump(got + 2 * i, 2)),
                                       "little") for i in range(3))
        if want_dev == "vbxe":
            check(tab <= got < tab + 0x1000 and got != antic,
                  f"{tag}: vdev is ${got:06X}, outside the VBXE tables at "
                  f"${tab:06X} (the ANTIC one is at ${antic:06X})")
        else:
            check(got == antic,
                  f"{tag}: vdev is ${got:06X}, not the ANTIC table at "
                  f"${antic:06X}")
        check((w, h) == geom[:2] and stride * (2 if want_dev == "vbxe" else 8) >= w,
              f"{tag}: the table vdev points at says {w}x{h} stride {stride}, "
              f"and the AES was told {geom[:2]}")
        print(f"  the VDI is on the {want_dev} device, vdev = ${got:06X} "
              f"-> {w}x{h}, stride {stride}")

        # -- and what the AES laid out for -------------------------------
        aes = tuple(b.peek16(syms[k]) for k in
                    ("gl_width", "gl_height", "gl_nplanes", "gl_wchar", "gl_hchar"))
        check(aes == geom,
              f"{tag}: the AES laid out for {aes}, not {geom} -- it asks the "
              f"VDI for these at gsx_start and every menu, window and dialog "
              f"on the screen comes off them")
        print(f"  the AES laid out on {aes[0]}x{aes[1]}, {aes[2]} plane(s), "
              f"cell {aes[3]}x{aes[4]}")

        # -- the desk against its own model -------------------------------
        # Everything the model needs that is not on the disk is read off
        # the machine, the way tests/emu/product_boot.py reads it: the
        # model has to hand the desktop's Malloc a real address and put
        # its tree where the loader put the target's.
        if want_dev == "antic":
            # The desktop's own calls, not every process's: gem_calls
            # counts an accessory's too, and the DOS 2 floppy carried
            # CLOCK.ACC from phase 38 to phase 42 -- seven calls past the
            # first wait, none of them the desktop's (src/sys/abi.c).
            calls = syms["app_calls"]
            kind = b.peek(syms["dos"])
            drvmap = 0x03 if kind != DOS_2 else (b.peek(DRVBYT) or 1)
            mark = b.peek16(syms["app_pool_lo"])
            brk = int.from_bytes(
                bytes(b.memdump(syms["farmem"] + FARMEM_BRK, 4)), "little")
            pointer = (b.peek16(syms["ptr_state"]),
                       b.peek16(syms["ptr_state"] + 2))
            fs = atr.open_fs(atr.ATRImage.load(path))
            ref_v, ref_a, d = desk_model(mark, brk, pointer, drvmap,
                                         dos2_listing(fs),
                                         dev=devref.Antic())
            check(len(ref_a.shots) == 1,
                  f"{tag}: the model took {len(ref_a.shots)} shots")
            # The ABI's counter is the desktop's own, so the call the
            # target is sitting in must be the model's first wait.
            got = (b.peek16(calls) - 1) & 0xFFFF
            check(got == d.waits[0],
                  f"{tag}: the desktop is in call {got}, not its first wait "
                  f"{d.waits[0]}")
            print(f"  the model laid out on {ref_a.gl_width}x{ref_a.gl_height}, "
                  f"cell {ref_a.gl_wchar}x{ref_a.gl_hchar}, box "
                  f"{ref_a.gl_wbox}x{ref_a.gl_hbox}; {len(d.script)} calls to "
                  f"its first wait at {d.waits[0]}")
        else:
            ref_a = None

        # -- the screen ---------------------------------------------------
        os.makedirs(SHOTDIR, exist_ok=True)
        shot = os.path.join(SHOTDIR, f"m26-{tag}.png")
        b.frames(20)
        b.screenshot(shot)
        from PIL import Image
        im = Image.open(shot).convert("RGB")
        px = im.load()
        x0, step = sampling(im, want_dev)
        y0, w, h = ((AN_Y0, AN_W, AN_H) if want_dev == "antic"
                    else (VB_Y0, VB_W, VB_H))
        seen = colours(px, x0, y0, w, h, step)
        if want_dev == "antic":
            check(len(seen) == 2,
                  f"{tag}: the desk holds {len(seen)} colours, not 2: "
                  f"{sorted(seen)}")
            shape = pixels(px, x0, y0, w, h, step)
        else:
            check(2 <= len(seen) <= 16,
                  f"{tag}: the desk holds {len(seen)} colours")
            shape = None
        ink = min(seen, key=sum) if seen else None
        count = sum(1 for p in pixels(px, x0, y0, w, h, step) if p == ink)
        if ref_a is not None:
            # The model's picture is bits; the screenshot's two colours
            # are the machine's and are read off the shot rather than
            # assumed, because what a luminance comes out as is between
            # ANTIC and the monitor (tools/devref.py, Antic.PAPER).
            paper = max(seen, key=sum)
            bad, shown = 0, []
            want = ref_a.shots[0]
            for yy in range(h):
                for xx in range(w):
                    got = px[x0 + xx * step, y0 + yy] != paper
                    exp = tuple(want[yy][xx]) == devref.Antic.INK
                    if got != exp:
                        bad += 1
                        if len(shown) < 4:
                            shown.append((xx, yy, "ink" if exp else "paper"))
            check(not bad,
                  f"{tag}: the desk, {bad} of {w * h:,} pixels differ from "
                  f"deskref on the ANTIC device; first (x, y, wanted) {shown}")
            if not bad:
                print(f"  the desk is the model's, all {w * h:,} pixels")
        check(0 < count < w * h,
              f"{tag}: {count} ink pixels on a {w}x{h} desk -- one that drew "
              f"nothing, or one that drew everything")
        print(f"  {len(seen)} colour(s) on the desk, {count:,} of them ink"
              f"{'' if step == 1 else f' (the frame is {im.width} wide here)'}")
        if not keep and os.path.exists(shot):
            os.remove(shot)
        return shape
    finally:
        emu.stop()


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    shapes = {}
    for tag, disk, has_vbxe, want_cfg, want_dev, geom in CASES:
        shapes[tag] = one(tag, disk, has_vbxe, want_cfg, want_dev, geom,
                          syms, keep, check)

    # The two ways to reach ANTIC must reach the SAME screen: one binary,
    # one disk, one device, and the only difference is which of two
    # sentences chose it.  A difference here is the override doing
    # something besides choosing.  Note that one of the two shots is
    # twice as wide as the other because one machine has a VBXE in it --
    # see sampling(); the pictures still have to be equal.
    a, s = shapes.get("auto-antic"), shapes.get("safe-mode")
    if a and s:
        bad = sum(1 for p, q in zip(a, s) if p != q)
        check(not bad,
              f"the auto and the safe-mode ANTIC desks differ in {bad} of "
              f"{len(a):,} pixels")
        if not bad:
            print(f"  the two ANTIC desks are the same picture, all "
                  f"{len(a):,} pixels")

    ok = not fails
    print(f"gem4xe-m26: {'PASS' if ok else 'FAIL'} -- one binary, two "
          f"screens, {len(fails)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
