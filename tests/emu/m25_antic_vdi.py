#!/usr/bin/env python3
"""Phase 33 gate: the VDI itself, on the ANTIC device.

The same src/vdi/vdi.c the VBXE build uses -- its dispatcher, workstation
state, clipping and attributes -- compiled with GEM4XE_DEV_ANTIC and
linked against dev_antic.c instead of dev_vbxe.c.  NOTHING IN THE VDI
WAS CHANGED to make that possible, which is the claim the seam was built
to be able to make, and this gate is what makes it checkable.

The milestone drives the VDI through its own interface (contrl, intin,
ptsin and a call to vdi()) rather than calling the device: a filled
rectangle in pen 1, the same rectangle again in XOR so a hole appears in
it, and a line of text.  Then it hands an AES OBJECT TREE to ob_draw --
an outlined dialog box with a title, an edit field and a DEFAULT button
-- so the object library is on the screen too, and the whole stack from
objc_draw down through the VDI to the device is what the pixels prove.
THE MODEL IS THE MODELS.  tools/vdiref.py's rasteriser and
tools/aesref.py's object library -- the same code that answers for the
VBXE in test-m3 and test-m4 -- are run here with ONE argument changed:
the device (tools/devref.py), exactly as the target changes one pointer.
Neither model was written for this screen and neither was edited for it.
Every one of the 53,760 pixels has to agree.

WHAT THE PENS DO HERE IS WORTH READING.  GEM numbers its pens white 0,
black 1.  The device has two colours and no palette, so pen 0 is the
background and anything else is ink -- and mode F gives the background
its hue and set pixels COLPF1's luminance, so a GEM screen comes out
white with black ink without anything having to arrange it.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref                               # noqa: E402
import devref                               # noqa: E402
from aesref import (Obj, NIL, G_BOX, G_STRING, G_BUTTON,   # noqa: E402
                    OUTLINED, SELECTABLE, EXIT, DEFAULT, LASTOB)
from anticref import AN_W, AN_H              # noqa: E402
from m4_aes import Layout, GSX_START, OBJC_DRAW, FULL   # noqa: E402
from vdiref import (V_OPNWK, V_CLRWK, WORK_IN, VSF_COLOR,   # noqa: E402
                    VSF_INTERIOR, VSWR_MODE, VST_COLOR, VR_RECFL, V_GTEXT)

# Where the harness pretends the application pool starts: the model puts
# the tree's strings there and nothing on the target reads them back, so
# any address inside bank $00 will do (m4_aes.Layout).
POOL = 0x6800
FIS_SOLID, MD_REPLACE, MD_XOR = 1, 1, 3

# The milestone's own calls, in its order (src/m25_antic_vdi.c): a filled
# rectangle in pen 1, the same rectangle again in XOR so a hole appears in
# it, a line of text -- then gsx_start, where the AES learns what device
# it is on, and the dialog.
SCRIPT = [
    (V_OPNWK, (), WORK_IN),
    (V_CLRWK,),
    (VSF_COLOR, (), (1,)),
    (VSF_INTERIOR, (), (FIS_SOLID,)),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VR_RECFL, (20, 20, 200, 60), ()),
    (VSWR_MODE, (), (MD_XOR,)),
    (VR_RECFL, (60, 30, 160, 50), ()),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VST_COLOR, (), (1,)),
    (V_GTEXT, (20, 80), tuple(ord(c) for c in "GEM ON ANTIC")),
    (GSX_START,),
    (OBJC_DRAW, FULL, (0, 8)),
]

DISK = os.path.abspath(os.path.join(ROOT, "build", "m25-boot.atr"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "m25.png"))
STATUS = 0x0600
SHOT_X0, SHOT_Y0 = 8, 24
FONT_W, FONT_H = 6, 6                       # the ANTIC face (vdidev.h)


def model():
    """What the milestone draws, as the device sees it.

    THE MODEL IS THE MODELS, on the other device.  tools/vdiref.py's
    rasteriser and tools/aesref.py's object library are the same code
    that answers for the VBXE in test-m3 and test-m4; what changes here
    is one argument -- the device (tools/devref.py) -- exactly as the
    target changes one pointer.  Nothing in either model was written for
    this screen and nothing in either was edited for it, which is the
    claim, and 53,760 pixels are what check it.

    This used to be src/aes/objc.c transcribed by hand into anticref's
    primitives: sixty lines that had to be kept in step with the AES and
    that got OUTLINED's ring wrong the first time (h+4, not h+4-2).  The
    hand copy is gone.
    """
    L = Layout(POOL)
    v, a, _ = aesref.run(SCRIPT, tree(L), L.mem, dev=devref.Antic())
    return v.dev


# The milestone's last act (src/m25_antic_vdi.c): the text's rectangle
# through a form in bank $00 and the far save form and back onto the
# screen.  Each hop is pixel for pixel, so the three together are one
# copy from the first rectangle to the last.
COPY_FROM = (19, 78)
COPY_TO = (211, 85)
COPY_W, COPY_H = 100, 10


def model_copied(dev):
    """model()'s pixels, and the round trip through memory on top."""
    grid = [[dev.bit(x, y) for x in range(AN_W)] for y in range(AN_H)]
    sx, sy = COPY_FROM
    dx, dy = COPY_TO
    for y in range(COPY_H):
        for x in range(COPY_W):
            grid[dy + y][dx + x] = dev.bit(sx + x, sy + y)
    return grid


def tree(L):
    """The four objects src/m25_antic_vdi.c builds: an OUTLINED box with
    a 2px border and the colour word $1100, a title, an edit field, and a
    button whose thickness is computed -- -1, one more for EXIT and one
    more for DEFAULT, negative meaning outward."""
    return [
        Obj(NIL,  1,   3, G_BOX,    0, OUTLINED, 0x00021100, 30, 100, 160, 46),
        Obj(2,  NIL, NIL, G_STRING, 0, 0, L.text("A GEM dialog"),  8,  6,  72,  6),
        Obj(3,  NIL, NIL, G_BOX,    0, 0, 0x00011100,             8, 16, 144,  8),
        Obj(0,  NIL, NIL, G_BUTTON, SELECTABLE | EXIT | DEFAULT | LASTOB,
            0, L.text("  OK  "),                               56, 30,  36, 10),
    ]


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    emu = launch(tag="m25", memsize="1088K", vbxe=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)                # -> 65C816 (resets; DOS reboots)
        b.frames(500)
        for k in ("M", "2", "5", "RETURN"):
            b.key(k)
            b.frames(6)
        for t in range(0, 4000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"AVK":
                break
        st = bytes(b.memdump(STATUS, 3))
        if not check(st == b"AVK", f"the VDI did not draw (status {st!r})"):
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "65C816", f"CPU is {cpu}")
        print(f"  the VDI opened a workstation on the ANTIC device, {cpu}, "
              f"no VBXE in the machine")

        # -- what the AES made of the device -------------------------
        # gsx_start asks the VDI for the extent, the depth and the system
        # font's cell, and everything it lays out afterwards comes off
        # those.  The gate does the same arithmetic the AES does (graf.c
        # gsx_start) rather than checking numbers someone wrote down: the
        # claim is that a GEM ADAPTS to a second screen, and a constant
        # would not be evidence of it.
        g = [b.peek16(0x0610 + i * 2) for i in range(10)]
        (width, height, planes, wchar, hchar, wbox, hbox,
         menu_w, menu_h, full_h) = g
        check((width, height) == (AN_W, AN_H),
              f"the AES thinks the screen is {width}x{height}, not "
              f"{AN_W}x{AN_H}")
        check(planes == 1,
              f"the AES thinks the device has {planes} planes, not 1 -- it "
              f"sizes its menu save buffer from that")
        check((wchar, hchar) == (FONT_W, FONT_H),
              f"the system font's cell came back {wchar}x{hchar}, not "
              f"{FONT_W}x{FONT_H} -- this device carries Atari's condensed "
              f"face, because 8 wide would be forty columns")
        check(width // wchar >= 53,
              f"{width // wchar} columns; the point of the narrow face is to "
              f"have more than the forty an 8-wide cell gives")
        check(hbox == hchar + 3,
              f"a box is {hbox} tall, not the cell plus three ({hchar + 3})")
        check(wbox == max(hbox * 372 // 372, wchar + 4),
              f"a box is {wbox} wide; the pixels are square here so it is "
              f"the taller of hbox and wchar+4")
        check((menu_w, menu_h) == (width, hbox),
              f"the menu bar is {menu_w}x{menu_h}, not the screen's width "
              f"by a box's height")
        check(full_h == height - hbox,
              f"the desk under the menu is {full_h} tall, not {height - hbox}")
        print(f"  the AES laid out on {width}x{height}, {planes} plane: "
              f"cell {wchar}x{hchar}, box {wbox}x{hbox}, menu bar {menu_h} "
              f"tall, desk {full_h}")

        b.frames(20)
        b.screenshot(SHOT)
        from PIL import Image
        im = Image.open(SHOT).convert("RGB")
        px = im.load()

        check(bytes(b.memdump(STATUS + 3, 1)) == b"F",
              "the save form was not in far memory, so the far half of the "
              "round trip through memory was not tested")
        grid = model_copied(model())

        class want:                         # the model, with the copy
            @staticmethod
            def bit(x, y):
                return grid[y][x]
        seen = {px[SHOT_X0 + x, SHOT_Y0 + y]
                for y in range(AN_H) for x in range(AN_W)}
        check(len(seen) == 2,
              f"the playfield holds {len(seen)} colours, not 2: {sorted(seen)}")
        if len(seen) != 2:
            return 1
        clear = next((x, y) for y in range(AN_H) for x in range(AN_W)
                     if not want.bit(x, y))
        setpx = next((x, y) for y in range(AN_H) for x in range(AN_W)
                     if want.bit(x, y))
        bg = px[SHOT_X0 + clear[0], SHOT_Y0 + clear[1]]
        fg = px[SHOT_X0 + setpx[0], SHOT_Y0 + setpx[1]]
        check(bg != fg, f"pen 0 and pen 1 are the same colour {bg}")
        check(sum(bg) > sum(fg),
              f"pen 0 {bg} is not lighter than pen 1 {fg}: GEM's pen 0 is "
              f"WHITE and its 1 is black, and on this device that has to "
              f"come out of the luminance without anyone arranging it")
        print(f"  pen 0 (white) {bg}, pen 1 (black) {fg}")

        bad, first = 0, []
        for y in range(AN_H):
            for x in range(AN_W):
                exp = fg if want.bit(x, y) else bg
                if px[SHOT_X0 + x, SHOT_Y0 + y] != exp:
                    bad += 1
                    if len(first) < 4:
                        first.append((x, y, want.bit(x, y)))
        check(not bad, f"{bad} of {AN_W * AN_H} pixels differ from the model; "
                       f"first (x, y, wanted bit) {first}")
        print(f"  {AN_W * AN_H - bad:,} of {AN_W * AN_H:,} pixels as the "
              f"model has them")
    finally:
        emu.stop()

    if not fails and not keep and os.path.exists(SHOT):
        os.remove(SHOT)
    ok = not fails
    print(f"gem4xe-m25: {'PASS' if ok else 'FAIL'} -- the VDI on ANTIC, "
          f"{len(fails)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
