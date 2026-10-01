#!/usr/bin/env python3
"""DESKICON.RSC: gem4xe's own colour icons for the desktop, from tools/a8icons.py.

    python3 tools/deskiconrsc.py build/deskicon.rsc [--png preview.png]

A new-format resource of one tree: a box, and a G_CICON for each of the
six kinds the desktop draws (src/desk/desktop.c, desk_cicons), labelled
as the desktop finds them.  Each icon carries all three forms:

  * the MONO form, for a two-colour screen and for the drag outline: a
    pixel is set where its colour is dark (luminance under half);
  * the 4-plane COLOUR form, in the ST's plane order, each pixel's
    planes being its HARDWARE colour -- the VDI pen through the same
    permutation the VDI applies (src/vdi/dev_vbxe.c, map_col), because
    that is what rs_chunky reads them as;
  * a SELECTED form: every colour one step darker, as a pressed icon.

The art is the only place the pictures are; everything else follows
from the colours (docs/phase89.md).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a8icons                                  # noqa: E402
import rsc                                      # noqa: E402
from rsc import ch, NIL                         # noqa: E402
from aesref import G_BOX, G_CICON, LASTOB       # noqa: E402

# the legend's pens (VDI numbers), and their colours (src/vdi/vdi.c gem_rgb)
PEN = {"W": 0, "K": 1, "r": 2, "G": 3, "b": 4, "c": 5, "y": 6, "m": 7,
       "g": 8, "d": 9, "R": 10, "n": 11, "B": 12, "C": 13, "Y": 14, "M": 15}
RGB = [(0xFF, 0xFF, 0xFF), (0, 0, 0), (0xFF, 0, 0), (0, 0xFF, 0),
       (0, 0, 0xFF), (0, 0xFF, 0xFF), (0xFF, 0xFF, 0), (0xFF, 0, 0xFF),
       (0xBB, 0xBB, 0xBB), (0x77, 0x77, 0x77), (0xBB, 0, 0), (0, 0xBB, 0),
       (0, 0, 0xBB), (0, 0xBB, 0xBB), (0xBB, 0xBB, 0), (0xBB, 0, 0xBB)]
# pen -> hardware colour: src/vdi/dev_vbxe.c's map_col, the ST's order
MAP_COL = (0, 15, 1, 2, 4, 6, 3, 5, 7, 8, 9, 10, 12, 14, 11, 13)
# selected: one step darker -- white to grey to dark grey to black, a
# bright colour to its dark one; the dark ones stay
DARKER = {"W": "g", "g": "d", "d": "K", "r": "R", "G": "n", "b": "B",
          "c": "C", "y": "Y", "m": "M"}
SIZE = 32
WB = SIZE // 8                                  # bytes a row, one plane


def lum(k):
    r, g, b = RGB[PEN[k]]
    return 0.299 * r + 0.587 * g + 0.114 * b


def plane_bits(rows, test):
    """One plane, MSB the leftmost pixel: the pixels `test` is true of."""
    out = bytearray()
    for r in rows:
        for x0 in range(0, SIZE, 8):
            v = 0
            for x in range(8):
                if test(r[x0 + x]):
                    v |= 0x80 >> x
            out.append(v)
    return bytes(out)


def colour_planes(rows):
    """The four planes, whole and one after the other, of each pixel's
    hardware colour; clear pixels are 0, which the mask leaves alone."""
    return b"".join(
        plane_bits(rows, lambda k, p=p: k != "." and (MAP_COL[PEN[k]] >> p) & 1)
        for p in range(4))


def forms(rows):
    """(mono data, mask, colour data, selected data) for one icon."""
    for r in rows:
        assert len(r) == SIZE and all(k == "." or k in PEN for k in r), r
    assert len(rows) == SIZE
    mask = plane_bits(rows, lambda k: k != ".")
    mono = plane_bits(rows, lambda k: k != "." and lum(k) < 128)
    sel_rows = ["".join(DARKER.get(k, k) for k in r) for r in rows]
    return mono, mask, colour_planes(rows), colour_planes(sel_rows)


def build():
    r = rsc.Rsc()
    objs = []
    n = len(a8icons.ICONS)
    for i, (label, _, digit, rows) in enumerate(a8icons.ICONS):
        mono, mask, col, sel = forms(rows)
        # the letter is the desktop's to fill in, in the digit's pen on
        # the pen under it (a8icons.py); the text rectangle is EmuTOS's,
        # which the desktop sets again for its own grid (deskobj.c)
        xchar, ychar, pen = digit if digit else (0, 0, "K")
        # The background is WHITE, always: the colour form's mask goes
        # down in it and the image is ORed over it (src/aes/objc.c), so
        # any other colour shows through every pixel; and the mono form is
        # drawn in the foreground, so a white digit would hide the icon on
        # a two-colour screen.
        fg = PEN[pen]
        assert fg != PEN["W"], (label, "a white digit hides the mono form")
        char = (fg << 12) | (PEN["W"] << 8)
        idx = r.cicon(mask, mono, label, SIZE, SIZE,
                      forms=[(4, col, mask, sel, mask)],
                      char=char, xchar=xchar, ychar=ychar,
                      xicon=20, yicon=0, xtext=0, ytext=32, wtext=72, htext=8)
        last = i == n - 1
        objs.append((0 if last else i + 2, NIL, NIL, G_CICON,
                     LASTOB if last else 0, 0, idx,
                     ch(1 + 9 * i), ch(1), ch(9), ch(5)))
    r.tree([(NIL, 1, n, G_BOX, 0, 0, 0x00001100,
             ch(0), ch(0), ch(2 + 9 * n), ch(7))] + objs)
    return r


def preview(path, scale=4):
    """The icons as the desktop would draw them, normal and selected,
    on its green, at `scale`."""
    from PIL import Image, ImageDraw
    n = len(a8icons.ICONS)
    cell = SIZE * scale + 16
    img = Image.new("RGB", (n * cell, 2 * cell), (0, 0xBB, 0))
    d = ImageDraw.Draw(img)
    for i, (_, _, _, rows) in enumerate(a8icons.ICONS):
        for j, rr in enumerate((rows, ["".join(DARKER.get(k, k) for k in r) for r in rows])):
            for y, row in enumerate(rr):
                for x, k in enumerate(row):
                    if k != ".":
                        X, Y = i * cell + 8 + x * scale, j * cell + 8 + y * scale
                        d.rectangle([X, Y, X + scale - 1, Y + scale - 1], fill=RGB[PEN[k]])
    img.save(path)


def main(argv):
    out = argv[0]
    r = build()
    data = r.file()
    with open(out, "wb") as f:
        f.write(data)
    print(f"{out}: {len(data)} bytes, {len(a8icons.ICONS)} colour icons")
    if "--png" in argv:
        preview(argv[argv.index("--png") + 1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
