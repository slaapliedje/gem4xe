#!/usr/bin/env python3
"""Phase 2 gate: VDI conformance.

Each case is a script of VDI calls.  The host runs it through tools/vdiref.py
(the specification) and pokes the identical script to the Atari, which runs it
through src/vdi/vdi.c.  The two framebuffers must match pixel for pixel.

The cases lean hard on 4bpp odd-pixel edges, because a rectangle whose left or
right edge falls in the middle of a byte is exactly where VDI drivers on
packed-pixel devices historically went wrong -- and it is silent when wrong.

Usage: m3_vdi.py [--case N] [--shot]
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch     # noqa: E402
import vbxeref                         # noqa: E402
import devref                          # noqa: E402
import vdiref                          # noqa: E402
import symfile                         # noqa: E402
from vdiref import (V_CLRWK, V_PLINE, VSL_TYPE, VSL_COLOR, VSF_INTERIOR,      # noqa: E402
                    VSF_COLOR, VR_RECFL, VS_CLIP, VRO_CPYFM, V_GTEXT,
                    VS_COLOR, VQ_COLOR, VST_ALIGNMENT, VST_EFFECTS,
                    VST_POINT, VQT_EXTENT, VQT_WIDTH,
                    V_FILLAREA, V_PMARKER, VSM_TYPE, VSM_HEIGHT, VSM_COLOR,
                    VQL_ATTRIBUTES, VQM_ATTRIBUTES, VQF_ATTRIBUTES,
                    VSF_PERIMETER, VST_ROTATION, V_GET_PIXEL, V_GDP,
                    GDP_BAR, GDP_ARC, GDP_PIE, GDP_CIRCLE, GDP_ELLIPSE,
                    GDP_ELLARC, GDP_ELLPIE, GDP_RBOX, GDP_RFBOX,
                    GDP_JUSTIFIED, V_CONTOURFILL, VSL_ENDS)
from vdiref import (VST_COLOR, VSWR_MODE, VRT_CPYFM, pack_mfdb,           # noqa: E402
                     VSC_FORM, V_SHOW_C, V_HIDE_C, V_LOCATOR,
                     VSIN_MODE, VQIN_MODE, VEX_TIMV, VSL_UDSTY, VQ_MOUSE,
                     VST_HEIGHT, VQT_ATTRIBUTES, V_ESCAPE, VSF_STYLE, VSF_UDPAT)

# A user fill pattern with every row different -- a diagonal -- so that a
# fill anchored to the wrong row, or to the rectangle instead of the screen,
# cannot pass.
UD_DIAG = tuple(0x8000 >> i for i in range(16))

# A GEM-style arrow: mask is the outline+body, data is the white interior.
# Painted mask-then-data, so a mask bit with no data bit is the outline.
ARROW_MASK = (0x8000, 0xC000, 0xE000, 0xF000, 0xF800, 0xFC00, 0xFE00, 0xFF00,
              0xFF80, 0xFC00, 0xEC00, 0xCE00, 0x0600, 0x0700, 0x0300, 0x0000)
ARROW_DATA = (0x0000, 0x4000, 0x6000, 0x7000, 0x7800, 0x7C00, 0x7E00, 0x7F00,
              0x7800, 0x6C00, 0x4600, 0x0600, 0x0300, 0x0300, 0x0000, 0x0000)


def cursor_form(xhot=0, yhot=0, bg=1, fg=0):
    """The 37 intin words vsc_form takes."""
    return (xhot, yhot, 1, bg, fg) + ARROW_MASK + ARROW_DATA

DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
SYMS = os.path.join(ROOT, "build", "m3.sym")
SHOTDIR = os.path.join(ROOT, "build", "shots")

STATUS, ST_STAGE, ST_GO, ST_DONE = 0x0600, 2, 3, 4

def make_icon():
    """A 32x24 one-plane form: frame, diagonal, dotted row, solid block.
    wdwidth is 2 WORDS (= 4 bytes) per row, MSB-first, as the VDI defines."""
    w, h, wdw = 32, 24, 2
    rows = [[0] * (wdw * 2) for _ in range(h)]

    def setpx(x, y):
        rows[y][x >> 3] |= 0x80 >> (x & 7)

    for x in range(w):
        setpx(x, 0); setpx(x, h - 1)
    for y in range(h):
        setpx(0, y); setpx(w - 1, y)
    for i in range(min(w, h)):
        setpx(i, i)
    for x in range(2, w - 2, 2):
        setpx(x, 4)
    for y in range(14, 20):
        for x in range(20, 28):
            setpx(x, y)
    bits = bytes(b for r in rows for b in r)
    return bits, w, h, wdw


ICON_BITS, ICON_W, ICON_H, ICON_WDW = make_icon()

# --- the cases ----------------------------------------------------------
# Every case starts from a cleared screen so each is independent.
CASES = [
    ("rect byte-aligned", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 63, 31), ())]),

    ("rect odd left edge", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (1, 2, 40, 20), ())]),

    ("rect odd right edge (x2 even)", [
        (VSF_COLOR, (), (3,)), (VR_RECFL, (10, 5, 50, 25), ())]),

    ("rect both edges odd", [
        (VSF_COLOR, (), (7,)), (VR_RECFL, (7, 3, 41, 19), ())]),

    ("one-pixel column, even x", [
        (VSF_COLOR, (), (1,)), (VR_RECFL, (100, 10, 100, 60), ())]),

    ("one-pixel column, odd x", [
        (VSF_COLOR, (), (1,)), (VR_RECFL, (101, 10, 101, 60), ())]),

    ("rect entirely inside one byte", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (200, 8, 201, 40), ())]),

    ("adjacent rects must not bleed", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (20, 20, 29, 40), ()),
        (VSF_COLOR, (), (4,)), (VR_RECFL, (30, 20, 39, 40), ()),
        (VSF_COLOR, (), (3,)), (VR_RECFL, (40, 20, 40, 40), ())]),

    # A hollow fill is a pattern with no bits set, and what a clear bit does
    # is the writing mode's decision: replace paints pen 0 (white -- GEM
    # dialogs are opaque because of this), erase paints the pen, and the
    # transparent and XOR modes leave the screen alone.
    ("hollow fill: white in replace, pen in erase, else nothing", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (10, 10, 100, 100), ()),
        (VSF_INTERIOR, (), (0,)),
        (VR_RECFL, (21, 20, 80, 60), ()),
        (VSWR_MODE, (), (2,)), (VR_RECFL, (30, 70, 90, 95), ()),
        (VSWR_MODE, (), (3,)), (VR_RECFL, (0, 0, 15, 15), ()),
        (VSWR_MODE, (), (4,)), (VSF_COLOR, (), (5,)),
        (VR_RECFL, (0, 90, 120, 110), ()),
        (VSWR_MODE, (), (1,)), (VSF_INTERIOR, (), (1,))]),

    # Pattern fills.  The pattern is anchored to the screen (row y AND mask,
    # bit 15 at every 16th pixel), so two fills that abut must tile as one.
    ("dither fill, replace, odd edges, abutting fills tile", [
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (4,)), (VSF_COLOR, (), (1,)),
        (VR_RECFL, (3, 5, 200, 90), ()),
        (VSF_COLOR, (), (3,)), (VR_RECFL, (201, 5, 300, 90), ()),
        (VSF_STYLE, (), (2,)), (VR_RECFL, (7, 91, 13, 108), ()),
        (VSF_INTERIOR, (), (1,))]),

    ("OEM pattern over a coloured field in all four modes", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 319, 119), ()),
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (9,)), (VSF_COLOR, (), (1,)),
        (VSWR_MODE, (), (1,)), (VR_RECFL, (10, 10, 79, 50), ()),
        (VSWR_MODE, (), (2,)), (VR_RECFL, (90, 10, 159, 50), ()),
        (VSWR_MODE, (), (3,)), (VR_RECFL, (170, 10, 239, 50), ()),
        (VSWR_MODE, (), (4,)), (VR_RECFL, (250, 10, 319, 50), ()),
        (VSF_STYLE, (), (17,)), (VSF_COLOR, (), (7,)),
        (VSWR_MODE, (), (2,)), (VR_RECFL, (11, 60, 78, 100), ()),
        (VSWR_MODE, (), (4,)), (VR_RECFL, (91, 60, 158, 100), ()),
        (VSWR_MODE, (), (1,)), (VSF_INTERIOR, (), (1,))]),

    # Pen 0 is hardware nibble 0, which the blitter's stencil mode cannot
    # write: transparent and erase fills in pen 0 take a different path.
    ("pattern fill in pen 0 clears pixels in transparent and erase", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 0, 199, 99), ()),
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (12,)), (VSF_COLOR, (), (0,)),
        (VSWR_MODE, (), (2,)), (VR_RECFL, (5, 5, 90, 60), ()),
        (VSWR_MODE, (), (4,)), (VR_RECFL, (101, 5, 190, 60), ()),
        (VSWR_MODE, (), (2,)), (VR_RECFL, (20, 70, 20, 95), ()),
        (VSWR_MODE, (), (4,)), (VR_RECFL, (23, 70, 23, 95), ()),
        (VSWR_MODE, (), (1,)), (VR_RECFL, (30, 70, 180, 95), ()),
        (VSF_INTERIOR, (), (1,))]),

    # The expansion holds 16 rows; taller fills go in bands, and a band
    # boundary must not show.  Fine hatches have 16 distinct rows.
    ("hatch fills across the 16-row band boundaries", [
        (VSF_INTERIOR, (), (3,)), (VSF_STYLE, (), (9,)), (VSF_COLOR, (), (6,)),
        (VR_RECFL, (0, 0, 639, 239), ()),                # the whole screen, 15 bands
        (VSF_STYLE, (), (7,)), (VSF_COLOR, (), (1,)),
        (VR_RECFL, (10, 13, 100, 70), ()),
        (VSF_STYLE, (), (3,)), (VSF_COLOR, (), (2,)),
        (VR_RECFL, (110, 31, 200, 33), ()),
        (VSF_STYLE, (), (12,)), (VR_RECFL, (210, 47, 300, 48), ()),
        (VSF_INTERIOR, (), (1,))]),

    ("user pattern: XOR twice restores, and clips", [
        (VSF_COLOR, (), (3,)), (VR_RECFL, (0, 0, 159, 79), ()),
        (VSF_UDPAT, (), UD_DIAG),
        (VSF_INTERIOR, (), (4,)), (VSF_COLOR, (), (5,)),
        (VS_CLIP, (21, 9, 140, 60), (1,)),
        (VSWR_MODE, (), (3,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (VR_RECFL, (60, 30, 200, 100), ()),
        (VS_CLIP, (0, 0, 639, 239), (0,)),
        (VSWR_MODE, (), (1,)), (VR_RECFL, (160, 0, 319, 79), ()),
        (VSF_INTERIOR, (), (1,))]),

    ("vsf_udpat takes 16 words and nothing else", [
        (VSF_UDPAT, (), UD_DIAG),
        (VSF_UDPAT, (), (0xFFFF,) * 8),                 # refused: pattern stays
        (VSF_INTERIOR, (), (4,)), (VSF_COLOR, (), (1,)),
        (VR_RECFL, (0, 0, 63, 47), ()),
        (VSF_UDPAT, (), (0x00FF,) * 16),                # a new one takes effect
        (VR_RECFL, (64, 0, 127, 47), ()),
        (VSF_INTERIOR, (), (1,))]),

    ("clipping to an odd-edged window", [
        (VS_CLIP, (15, 12, 84, 51), (1,)),
        (VSF_COLOR, (), (5,)), (VR_RECFL, (0, 0, 639, 239), ()),
        (VS_CLIP, (0, 0, 639, 239), (0,))]),

    ("horizontal and vertical polylines", [
        (VSL_COLOR, (), (1,)),
        (V_PLINE, (5, 5, 300, 5), ()),
        (V_PLINE, (5, 5, 5, 200), ()),
        (V_PLINE, (7, 199, 301, 199), ()),
        (V_PLINE, (301, 6, 301, 199), ())]),

    ("box as a closed polyline", [
        (VSL_COLOR, (), (4,)),
        (V_PLINE, (11, 11, 90, 11, 90, 70, 11, 70, 11, 11), ())]),

    ("diagonal lines (Bresenham)", [
        (VSL_COLOR, (), (2,)), (V_PLINE, (0, 0, 200, 100), ()),
        (VSL_COLOR, (), (3,)), (V_PLINE, (200, 0, 0, 100), ()),
        (VSL_COLOR, (), (7,)), (V_PLINE, (10, 120, 400, 130), ())]),

    ("dotted and dashed line styles", [
        (VSL_COLOR, (), (1,)),
        (VSL_TYPE, (), (3,)), (V_PLINE, (10, 20, 400, 20), ()),
        (VSL_TYPE, (), (5,)), (V_PLINE, (10, 40, 400, 40), ()),
        (VSL_TYPE, (), (6,)), (V_PLINE, (10, 60, 400, 60), ()),
        (VSL_TYPE, (), (2,)), (V_PLINE, (10, 80, 400, 80), ()),
        (VSL_TYPE, (), (1,))]),

    ("all sixteen pens", [
        (VSF_COLOR, (), (i,)) if False else rec
        for i in range(16)
        for rec in ((VSF_COLOR, (), (i,)),
                    (VR_RECFL, (i * 40, 0, i * 40 + 39, 100), ()))]),

    ("edges at the screen boundary", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 0, 239), ()),
        (VSF_COLOR, (), (3,)), (VR_RECFL, (639, 0, 639, 239), ()),
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 239, 639, 239), ())]),

    ("off-screen rect is clipped, not wrapped", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (600, 200, 700, 300), ())]),

    # --- raster copy.  The blitter has no shifter, so a 4bpp copy is one blit
    # only when source and destination x share parity AND both are even; every
    # other case falls back to the CPU.  Both paths must produce identical
    # pixels, which is the point of testing them side by side.
    ("cpyfm aligned (both even, even width)", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 39, 19), ()),
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 20, 39, 39), ()),
        (VRO_CPYFM, (0, 0, 39, 39, 100, 100, 139, 139), (3,))]),

    ("cpyfm unaligned: odd source x", [
        (VSF_COLOR, (), (3,)), (VR_RECFL, (0, 0, 60, 30), ()),
        (VSF_COLOR, (), (7,)), (VR_RECFL, (10, 5, 20, 25), ()),
        (VRO_CPYFM, (1, 0, 40, 30, 200, 60, 239, 90), (3,))]),

    ("cpyfm unaligned: parities differ", [
        (VSF_COLOR, (), (5,)), (VR_RECFL, (0, 0, 60, 30), ()),
        (VSF_COLOR, (), (1,)), (VR_RECFL, (3, 3, 9, 27), ()),
        (VRO_CPYFM, (0, 0, 39, 30, 101, 120, 140, 150), (3,))]),

    ("cpyfm odd width", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (0, 0, 40, 20), ()),
        (VSF_COLOR, (), (2,)), (VR_RECFL, (5, 5, 8, 15), ()),
        (VRO_CPYFM, (0, 0, 30, 20, 300, 40, 330, 60), (3,))]),

    # --- text.  One 4bpp glyph mask serves every ink colour: AND clears the
    # ink pixels (mode 4 is the one mode that writes 0 rather than skipping),
    # then OR paints them.  Ink 0 needs no OR at all, which is why no inverted
    # mask is kept -- and why mode 6's nibble stencil is not used, since it
    # cannot write colour 0.
    ("text, transparent, black on white", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (16, 20), tuple(b"GEM for the Atari 8-bit"))]),

    # -- what an application asks the VDI for, and the AES never does ----
    ("fill: a triangle, a concave polygon, and one that crosses itself", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (0,)),
        (V_FILLAREA, (60, 20, 20, 100, 100, 100), ()),
        # a chevron: two spans on the scan lines through the notch
        (VSF_COLOR, (), (2,)),
        (V_FILLAREA, (140, 20, 180, 100, 220, 20, 220, 110, 140, 110), ()),
        # a bow tie: the edges cross, so the middle is two spans
        (VSF_COLOR, (), (4,)),
        (V_FILLAREA, (260, 20, 380, 110, 380, 20, 260, 110), ()),
        # and a degenerate one: every point on the same row
        (VSF_COLOR, (), (3,)),
        (V_FILLAREA, (420, 60, 500, 60, 460, 60), ())]),

    ("fill: the perimeter is the FILL colour, over the edge pixels", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (8,)),
        (VSL_COLOR, (), (2,)), (VSL_TYPE, (), (3,)),   # neither is used
        (VSF_PERIMETER, (), (1,)),
        (V_FILLAREA, (60, 20, 20, 100, 100, 100), ()),
        # hollow with a perimeter: the outline alone, in the fill colour
        (VSF_INTERIOR, (), (0,)), (VSF_COLOR, (), (1,)),
        (V_FILLAREA, (180, 20, 140, 100, 220, 100), ()),
        # and the line attributes must be back as they were
        (VQL_ATTRIBUTES,), (VQF_ATTRIBUTES,)]),

    ("fill: patterned and hatched interiors take the screen anchor", [
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (4,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (0,)),
        (V_FILLAREA, (100, 20, 20, 120, 180, 120), ()),
        (VSF_INTERIOR, (), (3,)), (VSF_STYLE, (), (2,)), (VSF_COLOR, (), (2,)),
        (V_FILLAREA, (300, 20, 220, 120, 380, 120), ()),
        (VSF_INTERIOR, (), (4,)), (VSF_UDPAT, (), UD_DIAG),
        (VSF_COLOR, (), (4,)),
        (V_FILLAREA, (500, 20, 420, 120, 580, 120), ())]),

    ("fill: clipped, off the top, and off both side edges", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (1,)),
        (VS_CLIP, (100, 40, 300, 160), (1,)),
        (V_FILLAREA, (200, 10, 60, 200, 340, 200), ()),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        # off the top edge and off the left edge, unclipped
        (VSF_COLOR, (), (2,)),
        (V_FILLAREA, (420, -40, 380, 60, 460, 60), ()),
        (VSF_COLOR, (), (4,)),
        (V_FILLAREA, (-30, 150, 60, 120, 60, 200), ()),
        (VSF_COLOR, (), (3,)),
        (V_FILLAREA, (620, 150, 700, 120, 700, 200), ())]),

    ("markers: all six, at three scales, coloured and clipped", [
        (VSM_COLOR, (), (1,)),
        (VSM_TYPE, (), (1,)), (V_PMARKER, (40, 30), ()),
        (VSM_TYPE, (), (2,)), (V_PMARKER, (80, 30), ()),
        (VSM_TYPE, (), (3,)), (V_PMARKER, (120, 30), ()),
        (VSM_TYPE, (), (4,)), (V_PMARKER, (160, 30), ()),
        (VSM_TYPE, (), (5,)), (V_PMARKER, (200, 30), ()),
        (VSM_TYPE, (), (6,)), (V_PMARKER, (240, 30), ()),
        # several points in one call, at scale 2, in another colour
        (VSM_HEIGHT, (0, 22), ()), (VSM_COLOR, (), (2,)), (VSM_TYPE, (), (3,)),
        (V_PMARKER, (40, 90, 100, 90, 160, 90, 220, 90), ()),
        # a height below the minimum and one above the maximum
        (VSM_HEIGHT, (0, 1), ()), (V_PMARKER, (300, 90), ()),
        (VSM_HEIGHT, (0, 999), ()), (VSM_COLOR, (), (4,)),
        (V_PMARKER, (450, 120), ()),
        # clipped, and off the screen edge
        (VSM_HEIGHT, (0, 11), ()), (VS_CLIP, (0, 160, 200, 200), (1,)),
        (VSM_TYPE, (), (4,)), (V_PMARKER, (100, 160, 100, 200, 100, 220), ()),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (V_PMARKER, (2, 220, 637, 220), ()),
        # out of range on both, which become the defaults
        (VSM_TYPE, (), (9,)), (VSM_COLOR, (), (99,)),
        (VQM_ATTRIBUTES,)]),

    ("the inquiries answer with what was set, not what was asked", [
        (VSL_TYPE, (), (4,)), (VSL_COLOR, (), (3,)), (VSWR_MODE, (), (3,)),
        (VQL_ATTRIBUTES,),
        (VSM_TYPE, (), (5,)), (VSM_COLOR, (), (6,)), (VSM_HEIGHT, (0, 30), ()),
        (VQM_ATTRIBUTES,),
        (VSF_INTERIOR, (), (3,)), (VSF_STYLE, (), (7,)), (VSF_COLOR, (), (9,)),
        (VSF_PERIMETER, (), (0,)), (VQF_ATTRIBUTES,),
        (VSF_PERIMETER, (), (1,)), (VQF_ATTRIBUTES,),
        (VST_ROTATION, (), (900,)),
        (VSWR_MODE, (), (1,))]),

    ("gdp: bar, with and without its perimeter", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (VSF_PERIMETER, (), (0,)),
        (V_GDP, (20, 20, 140, 80), (), None, GDP_BAR),
        # patterned, with the perimeter: the outline is solid, the fill is not
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (6,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (1,)),
        (V_GDP, (180, 20, 300, 80), (), None, GDP_BAR),
        # given backwards, and clipped
        (VS_CLIP, (340, 40, 500, 100), (1,)),
        (V_GDP, (560, 120, 360, 20), (), None, GDP_BAR),
        (VS_CLIP, (0, 0, 0, 0), (0,))]),

    ("gdp: circles and ellipses, filled and hollow", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (VSF_PERIMETER, (), (0,)),
        (V_GDP, (80, 60, 0, 0, 40, 0), (), None, GDP_CIRCLE),
        (VSF_INTERIOR, (), (0,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (1,)),
        (V_GDP, (200, 60, 0, 0, 50, 0), (), None, GDP_CIRCLE),
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (3,)), (VSF_COLOR, (), (4,)),
        (VSF_PERIMETER, (), (0,)),
        (V_GDP, (360, 70, 90, 40), (), None, GDP_ELLIPSE),
        # a tiny one, and one bigger than the screen
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (3,)),
        (V_GDP, (500, 30, 0, 0, 3, 0), (), None, GDP_CIRCLE),
        (VSF_COLOR, (), (9,)),
        (V_GDP, (560, 120, 0, 0, 200, 0), (), None, GDP_CIRCLE)]),

    ("gdp: arcs and pie slices, every quadrant", [
        (VSL_COLOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (VSF_INTERIOR, (), (1,)), (VSF_PERIMETER, (), (0,)),
        # an open arc is a polyline in the LINE colour and style
        (V_GDP, (100, 60, 0, 0, 0, 0, 50, 0), (0, 900), None, GDP_ARC),
        (VSL_COLOR, (), (4,)), (VSL_TYPE, (), (3,)),
        (V_GDP, (100, 60, 0, 0, 0, 0, 50, 0), (1800, 2700), None, GDP_ARC),
        (VSL_TYPE, (), (1,)),
        # a wedge is a polygon in the FILL colour
        (V_GDP, (280, 70, 0, 0, 0, 0, 60, 0), (300, 1500), None, GDP_PIE),
        (VSF_COLOR, (), (4,)),
        (V_GDP, (280, 70, 0, 0, 0, 0, 60, 0), (2100, 3300), None, GDP_PIE),
        # elliptical, and one whose angles wrap past 360
        (VSF_COLOR, (), (3,)),
        (V_GDP, (480, 70, 90, 45), (3300, 600), None, GDP_ELLPIE),
        (VSL_COLOR, (), (1,)),
        (V_GDP, (480, 180, 100, 40), (450, 1350), None, GDP_ELLARC)]),

    ("gdp: rounded boxes, outlined and filled, and degenerate ones", [
        (VSL_COLOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (VSF_INTERIOR, (), (1,)), (VSF_PERIMETER, (), (0,)),
        (V_GDP, (20, 20, 200, 90), (), None, GDP_RBOX),
        (V_GDP, (220, 20, 400, 90), (), None, GDP_RFBOX),
        # given backwards, patterned, and with a perimeter
        (VSF_INTERIOR, (), (3,)), (VSF_STYLE, (), (5,)), (VSF_COLOR, (), (1,)),
        (VSF_PERIMETER, (), (1,)),
        (V_GDP, (600, 100, 430, 20), (), None, GDP_RFBOX),
        # one narrower than two corner radii, and one clipped
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (4,)),
        (VSF_PERIMETER, (), (0,)),
        (V_GDP, (40, 140, 55, 190), (), None, GDP_RFBOX),
        (VS_CLIP, (100, 150, 300, 200), (1,)),
        (V_GDP, (80, 130, 340, 220), (), None, GDP_RFBOX),
        (VS_CLIP, (0, 0, 0, 0), (0,))]),

    ("gdp: justified text, by word, by character, and by both", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (VSL_COLOR, (), (2,)),
        (V_PLINE, (20, 10, 20, 230), ()), (V_PLINE, (500, 10, 500, 230), ()),
        # neither: the string is drawn as it comes
        (V_GDP, (20, 30, 480, 0), (0, 0) + tuple(b"neither of the two"),
         None, GDP_JUSTIFIED),
        # between words only
        (V_GDP, (20, 50, 480, 0), (1, 0) + tuple(b"between the words only"),
         None, GDP_JUSTIFIED),
        # between characters only
        (V_GDP, (20, 70, 480, 0), (0, 1) + tuple(b"between characters"),
         None, GDP_JUSTIFIED),
        # both, which caps what a word gap may take
        (V_GDP, (20, 90, 480, 0), (1, 1) + tuple(b"both of them at once"),
         None, GDP_JUSTIFIED),
        # narrower than the string: the gaps go negative
        (V_GDP, (20, 110, 100, 0), (1, 1) + tuple(b"squeezed up tight"),
         None, GDP_JUSTIFIED),
        # centred and right-aligned on the JUSTIFIED width, underlined
        (VST_ALIGNMENT, (), (1, 5)),
        (V_GDP, (260, 130, 300, 0), (1, 0) + tuple(b"centred on it"),
         None, GDP_JUSTIFIED),
        (VST_ALIGNMENT, (), (2, 5)), (VST_EFFECTS, (), (9,)),
        (V_GDP, (500, 160, 300, 0), (0, 1) + tuple(b"right, and thick"),
         None, GDP_JUSTIFIED),
        (VST_ALIGNMENT, (), (0, 0)), (VST_EFFECTS, (), (0,)),
        # one character, and none at all
        (V_GDP, (20, 200, 200, 0), (1, 1, ord("x")), None, GDP_JUSTIFIED),
        (V_GDP, (20, 220, 200, 0), (1, 1), None, GDP_JUSTIFIED)]),

    ("contour fill: bounded by a colour, and by the seed's own", [
        # a box outline in black, filled from inside up to it
        (VSL_COLOR, (), (1,)),
        (V_PLINE, (20, 20, 200, 20, 200, 120, 20, 120, 20, 20), ()),
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (V_CONTOURFILL, (100, 70), (1,)),
        # the same box drawn again further right, filled by the seed's own
        # colour instead -- white, up to anything that is not white
        (V_PLINE, (240, 20, 420, 20, 420, 120, 240, 120, 240, 20), ()),
        (V_PLINE, (300, 20, 300, 120), ()),      # a wall down the middle
        (VSF_COLOR, (), (4,)),
        (V_CONTOURFILL, (350, 70), (-1,)),       # only the right half fills
        # a patterned bucket, and one whose seed is already the boundary
        (V_PLINE, (460, 20, 620, 20, 620, 120, 460, 120, 460, 20), ()),
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (8,)), (VSF_COLOR, (), (1,)),
        (V_CONTOURFILL, (540, 70), (1,)),
        (V_CONTOURFILL, (460, 20), (1,)),        # on the wall: nothing
        # clipped: the bucket may not leave the clip rectangle
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (3,)),
        (VS_CLIP, (40, 150, 300, 220), (1,)),
        (V_CONTOURFILL, (100, 180), (-1,)),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (V_CONTOURFILL, (500, 200), (99,))]),    # no such pen: fills to nothing

    ("line ends: arrowheads at either end, and lines too short for one", [
        (VSL_COLOR, (), (1,)),
        (VSL_ENDS, (), (1, 0)), (V_PLINE, (40, 30, 200, 30), ()),
        (VSL_ENDS, (), (0, 1)), (V_PLINE, (40, 60, 200, 60), ()),
        (VSL_ENDS, (), (1, 1)), (V_PLINE, (40, 90, 200, 90), ()),
        # every direction, from one centre
        (V_PLINE, (320, 120, 420, 120), ()),
        (V_PLINE, (320, 120, 320, 220), ()),
        (V_PLINE, (320, 120, 240, 60), ()),
        (V_PLINE, (320, 120, 400, 200), ()),
        # a polyline of several segments: the head follows the last one
        (V_PLINE, (460, 30, 520, 90, 600, 40), ()),
        # too short to carry a head, and a single point
        (V_PLINE, (40, 200, 45, 200), ()),
        (V_PLINE, (100, 200), ()),
        # rounded and out of range, which the driver answers with what it did
        (VSL_ENDS, (), (2, 9)), (V_PLINE, (140, 200, 240, 200), ()),
        (VSL_ENDS, (), (0, 0))]),

    ("v_get_pixel reads back the pen that was drawn", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (2,)),
        (VR_RECFL, (10, 10, 100, 50), ()),
        (VSF_COLOR, (), (9,)), (VR_RECFL, (101, 10, 200, 50), ()),
        (V_GET_PIXEL, (50, 30), ()),      # the red field
        (V_GET_PIXEL, (150, 30), ()),     # the grey one
        (V_GET_PIXEL, (101, 10), ()),     # the first pixel of the second
        (V_GET_PIXEL, (100, 10), ()),     # and the last of the first: odd x
        (V_GET_PIXEL, (400, 200), ()),    # untouched: pen 0
        (V_GET_PIXEL, (-1, 0), ()),       # off the screen: 0
        (V_GET_PIXEL, (0, 999), ())]),

    ("text: vst_alignment, every horizontal against every vertical", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (VSL_COLOR, (), (1,)),
        # a cross through the point each string is aligned to, so where the
        # string lands is visible and not merely returned
        (V_PLINE, (320, 0, 320, 239), ()), (V_PLINE, (0, 40, 639, 40), ()),
        (VST_ALIGNMENT, (), (0, 0)), (V_GTEXT, (320, 40), tuple(b"left/base")),
        (VST_ALIGNMENT, (), (1, 5)), (V_GTEXT, (320, 60), tuple(b"centre/top")),
        (VST_ALIGNMENT, (), (2, 3)), (V_GTEXT, (320, 90), tuple(b"right/bottom")),
        (VST_ALIGNMENT, (), (1, 2)), (V_GTEXT, (320, 120), tuple(b"centre/ascent")),
        (VST_ALIGNMENT, (), (0, 1)), (V_GTEXT, (320, 150), tuple(b"left/half")),
        (VST_ALIGNMENT, (), (2, 4)), (V_GTEXT, (320, 180), tuple(b"right/descent")),
        # out of range on both, which the driver answers with the default
        (VST_ALIGNMENT, (), (9, 9)), (V_GTEXT, (320, 210), tuple(b"refused"))]),

    ("text: vst_effects -- thickened, underlined, both, and one it cannot do", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (VST_EFFECTS, (), (0,)), (V_GTEXT, (16, 20), tuple(b"plain")),
        (VST_EFFECTS, (), (1,)), (V_GTEXT, (16, 40), tuple(b"thickened")),
        (VST_EFFECTS, (), (8,)), (V_GTEXT, (16, 60), tuple(b"underlined")),
        (VST_EFFECTS, (), (9,)), (V_GTEXT, (16, 80), tuple(b"both of them")),
        # skewed and outlined are asked for and not applied: the answer says so
        (VST_EFFECTS, (), (0x3F,)), (V_GTEXT, (16, 100), tuple(b"all six asked")),
        (VST_EFFECTS, (), (0,)),
        (VST_ALIGNMENT, (), (1, 5)), (VST_EFFECTS, (), (1,)),
        (V_GTEXT, (320, 140), tuple(b"thick and centred")),
        (VST_ALIGNMENT, (), (0, 0)), (VST_EFFECTS, (), (0,))]),

    ("text: the metrics an application measures with", [
        (VQT_EXTENT, (), tuple(b"a string")),
        (VQT_WIDTH, (), (ord("M"),)),
        (VST_POINT, (), (10,)),
        (VST_EFFECTS, (), (1,)), (VQT_EXTENT, (), tuple(b"a string")),
        (VST_EFFECTS, (), (0,)),
        (VQT_EXTENT, (), ()),                     # the empty string
        (VQT_ATTRIBUTES,)]),

    ("colour: vs_color and vq_color, asked for and actual", [
        (VS_COLOR, (), (2, 1000, 0, 0)),          # pen 2 pure red
        (VQ_COLOR, (), (2, 0)), (VQ_COLOR, (), (2, 1)),
        (VS_COLOR, (), (3, 333, 666, 999)),       # a value the DAC rounds
        (VQ_COLOR, (), (3, 0)), (VQ_COLOR, (), (3, 1)),
        (VS_COLOR, (), (4, -50, 1500, 500)),      # out of range, clamped
        (VQ_COLOR, (), (4, 0)),
        (VQ_COLOR, (), (99, 0)),                  # no such pen
        (VS_COLOR, (), (99, 0, 0, 0)),            # ignored
        # and the screen, so the new colours are seen and not just reported
        (VSF_COLOR, (), (2,)), (VR_RECFL, (10, 10, 200, 60), ()),
        (VSF_COLOR, (), (3,)), (VR_RECFL, (210, 10, 400, 60), ()),
        (VSF_COLOR, (), (4,)), (VR_RECFL, (410, 10, 600, 60), ())]),

    ("text, every printable ASCII row", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (0, 20), tuple(range(32, 112))),
        (V_GTEXT, (0, 40), tuple(range(112, 192)))]),

    ("text, ink 0 (white) on a filled field -- the AND-only path", [
        (VSF_COLOR, (), (1,)), (VR_RECFL, (0, 0, 400, 60), ()),
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (0,)),
        (V_GTEXT, (16, 20), tuple(b"INVERTED MENU ITEM"))]),

    ("text, replace mode paints its own background", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 400, 60), ()),
        (VSWR_MODE, (), (1,)), (VST_COLOR, (), (4,)),
        (V_GTEXT, (16, 20), tuple(b"OPAQUE")),
        (VSWR_MODE, (), (2,))]),

    ("text at odd x (CPU fallback) must match", [
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (16, 20), tuple(b"even x")),
        (V_GTEXT, (17, 40), tuple(b"odd x"))]),

    ("text clipped, whole and partial glyphs", [
        (VS_CLIP, (40, 16, 143, 39), (1,)),
        (VSWR_MODE, (), (2,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (8, 22), tuple(b"clipping test line")),
        (V_GTEXT, (8, 34), tuple(b"second line here")),
        (VS_CLIP, (0, 0, 639, 239), (0,))]),

    # XOR, erase and a glyph the screen edge cuts all take the 1bpp raster
    # path (raster_1bpp in vdi.c), the same one vrt_cpyfm uses.
    ("text in XOR and erase modes, and cut by the screen edge", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (3,)),
        (VR_RECFL, (0, 0, 200, 60), ()),
        (VSWR_MODE, (), (3,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (16, 20), tuple(b"XOR text")),
        (VSWR_MODE, (), (4,)), (VST_COLOR, (), (5,)),
        (V_GTEXT, (16, 40), tuple(b"erase text")),
        (VSWR_MODE, (), (1,)), (VST_COLOR, (), (1,)),
        (V_GTEXT, (-3, 100), tuple(b"left edge")),
        (V_GTEXT, (600, 120), tuple(b"right edge")),
        (V_GTEXT, (300, 3), tuple(b"top")),
        (V_GTEXT, (300, 243), tuple(b"bottom")),
        (VSWR_MODE, (), (3,)),
        (VS_CLIP, (21, 131, 100, 145), (1,)),
        (V_GTEXT, (16, 140), tuple(b"XOR clipped")),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (VSWR_MODE, (), (1,))]),

    ("text in every pen", [
        (VSWR_MODE, (), (2,))] + [
        rec for i in range(16)
        for rec in ((VST_COLOR, (), (i,)),
                    (V_GTEXT, (8, 16 + i * 10), tuple(b"pen %02d ABCdef" % i)))]),

    # --- vrt_cpyfm: a ONE-PLANE form expanded into device colours.  This is
    # how the AES draws icons.  The source lives in RAM, out of the blitter's
    # reach: the CPU expands it into AND/OR strips in VRAM and the blitter
    # applies them (it was plotted pixel by pixel until Phase 8b measured
    # that at three frames an icon).
    ("vrt_cpyfm replace: fg and bg both painted", [
        (VSF_COLOR, (), (8,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 16, 0, 0),
         (1, 2, 6), "icon")]),

    ("vrt_cpyfm transparent: background survives", [
        (VSF_COLOR, (), (5,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 16, 0, 0),
         (2, 1, 0), "icon")]),

    ("vrt_cpyfm reverse-transparent paints the clear pixels", [
        (VSF_COLOR, (), (3,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 16, 0, 0),
         (4, 1, 7), "icon")]),

    ("vrt_cpyfm XOR inverts under the set pixels", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 16, 0, 0),
         (3, 0, 0), "icon")]),

    ("vrt_cpyfm at odd destination x", [
        (VSF_COLOR, (), (8,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 17, 9, 0, 0),
         (1, 1, 6), "icon")]),

    ("vrt_cpyfm sub-rectangle of the form", [
        (VSF_COLOR, (), (0,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (8, 4, 23, 19, 40, 20, 0, 0), (1, 4, 6), "icon")]),

    # The strip path clips to the pixel: a clip edge at odd x lands inside a
    # byte, and every mode has its own "leave alone" pair.
    ("vrt_cpyfm clipped by vs_clip at odd edges, every mode", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (0, 0, 300, 80), ()),
        (VS_CLIP, (19, 18, 140, 41), (1,)),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 16, 0, 0),
         (1, 4, 6), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 50, 16, 0, 0),
         (2, 1, 0), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 84, 20, 0, 0),
         (4, 0, 7), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 118, 30, 0, 0),
         (3, 0, 0), "icon"),
        (VS_CLIP, (0, 0, 639, 239), (0,))]),

    ("vrt_cpyfm transparent in pen 0: the AND strip alone", [
        (VSF_COLOR, (), (8,)), (VR_RECFL, (0, 0, 200, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 17, 16, 0, 0),
         (2, 0, 0), "icon")]),

    ("vrt_cpyfm at the screen corners", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (0, 0, 639, 239), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, -5, -3, 0, 0),
         (1, 1, 0), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 621, 226, 0, 0),
         (2, 1, 0), "icon")]),

    # Blitter mode 6, the nibble stencil, cannot write hardware 0, so white
    # takes the other blits: a replace with a white pen is a plain copy of
    # the strip when every strip byte lies inside the clip, and an OR strip
    # under a one-row AND blit when the first or the last does not; a raster
    # that writes only white is an AND strip.  Each of those, at even and odd
    # x, from a shifted source, and cut by a clip.
    ("vrt_cpyfm with white: the copy, the AND row, the AND strip", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (0, 0, 300, 80), ()),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 16, 4, 0, 0),
         (1, 1, 0), "icon"),
        (VRT_CPYFM, (3, 2, 24, 21, 60, 4, 0, 0), (1, 0, 1), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 101, 4, 0, 0),
         (1, 1, 0), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 150, 30, 0, 0),
         (4, 3, 0), "icon"),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 201, 30, 0, 0),
         (1, 0, 0), "icon"),
        (VS_CLIP, (251, 33, 278, 50), (1,)),
        (VRT_CPYFM, (0, 0, ICON_W - 1, ICON_H - 1, 248, 30, 0, 0),
         (1, 0, 1), "icon"),
        (VS_CLIP, (0, 0, 639, 239), (0,))]),

    # --- mouse cursor.  The pointer is placed with v_locator, which is how
    # GEM itself sets the locator's initial position (gsx_setmousexy), so no
    # test-only back door is needed.  Everything below the seam in
    # src/vdi/pointer.h is irrelevant here: the VDI only ever sees an
    # absolute position.
    ("cursor on a plain background", [
        (V_LOCATOR, (100, 60), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,))]),

    ("cursor over drawn content, then hidden again -- must restore exactly", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (80, 40, 200, 120), ()),
        (VSF_COLOR, (), (4,)), (VR_RECFL, (100, 55, 130, 75), ()),
        (V_LOCATOR, (110, 60), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ())]),

    ("cursor moved across content leaves no trail", [
        (VSF_COLOR, (), (6,)), (VR_RECFL, (0, 0, 300, 120), ()),
        (VSC_FORM, (), cursor_form()),
        (V_LOCATOR, (40, 40), ()), (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ()), (V_LOCATOR, (41, 41), ()), (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ()), (V_LOCATOR, (77, 53), ()), (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ()), (V_LOCATOR, (150, 90), ()), (V_SHOW_C, (), (0,))]),

    ("cursor at odd x (save span is 9 bytes, not 8)", [
        (VSF_COLOR, (), (3,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (V_LOCATOR, (101, 51), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,))]),

    ("cursor with a hotspot offset", [
        (VSF_COLOR, (), (5,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (V_LOCATOR, (60, 50), ()),
        (VSC_FORM, (), cursor_form(7, 7)),
        (V_SHOW_C, (), (0,))]),

    ("cursor clipped at the screen edges", [
        (VSF_COLOR, (), (8,)), (VR_RECFL, (0, 0, 639, 239), ()),
        (VSC_FORM, (), cursor_form()),
        (V_LOCATOR, (2, 2), ()), (V_SHOW_C, (), (0,)), (V_HIDE_C, (), ()),
        (V_LOCATOR, (634, 234), ()), (V_SHOW_C, (), (0,))]),

    # Real GEM's pointer is drawn wherever it is, whatever vs_clip says.
    # Both the target and the model once clipped it -- and agreed.
    ("cursor ignores vs_clip: drawn whole under a clip that excludes it", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (VS_CLIP, (300, 150, 400, 200), (1,)),
        (V_LOCATOR, (95, 45), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,)),
        (VS_CLIP, (0, 0, 639, 239), (0,))]),

    ("hide nesting: two hides need two shows", [
        (VSF_COLOR, (), (7,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (V_LOCATOR, (90, 50), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ()), (V_HIDE_C, (), ()),
        (V_SHOW_C, (), (1,)),          # still hidden: one show, two hides
        ]),

    ("hide nesting: the matching second show brings it back", [
        (VSF_COLOR, (), (7,)), (VR_RECFL, (0, 0, 200, 100), ()),
        (V_LOCATOR, (90, 50), ()),
        (VSC_FORM, (), cursor_form()),
        (V_SHOW_C, (), (0,)),
        (V_HIDE_C, (), ()), (V_HIDE_C, (), ()),
        (V_SHOW_C, (), (1,)), (V_SHOW_C, (), (1,))]),

    # --- returned values.  These opcodes draw nothing, so the pixel check
    # cannot see them at all; they are verified by comparing what each call
    # RETURNS against the reference, call for call.
    ("attribute setters report what they selected", [
        (VSL_COLOR, (), (7,)), (VSL_COLOR, (), (99,)),      # out of range -> 1
        (VSF_COLOR, (), (3,)), (VSF_COLOR, (), (-4,)),
        (VSF_INTERIOR, (), (2,)), (VSF_INTERIOR, (), (9,)),  # -> 0
        (VSF_INTERIOR, (), (2,)), (VSF_STYLE, (), (24,)),
        (VSF_STYLE, (), (25,)), (VSF_STYLE, (), (0,)),       # -> 1, 1
        (VSF_INTERIOR, (), (3,)), (VSF_STYLE, (), (12,)),
        (VSF_STYLE, (), (13,)),                              # -> 1
        (VSF_INTERIOR, (), (1,)), (VSF_STYLE, (), (20,)),    # solid: hatch range -> 1
        (VST_COLOR, (), (5,)),
        (VSWR_MODE, (), (3,)), (VSWR_MODE, (), (7,))]),      # -> replace

    ("input modes round-trip through vsin/vqin", [
        (VSIN_MODE, (), (1, 1)), (VQIN_MODE, (), (1,)),
        (VSIN_MODE, (), (1, 2)), (VQIN_MODE, (), (1,)),
        (VSIN_MODE, (), (4, 1)), (VQIN_MODE, (), (4,)),
        (VQIN_MODE, (), (2,)),                               # untouched: 2
        (VSIN_MODE, (), (9, 1)), (VQIN_MODE, (), (1,))]),    # bad dev ignored

    ("locator and vq_mouse agree on position", [
        (V_LOCATOR, (123, 45), ()),
        (VQ_MOUSE, (), ()),
        (V_LOCATOR, (700, 300), ()),                         # clamped
        (VQ_MOUSE, (), ()),
        (V_LOCATOR, (-5, -5), ()),
        (VQ_MOUSE, (), ())]),

    # Axis-aligned styled lines are pattern blits (style_line in vdi.c): the
    # style anchored to the line's first point, in either direction, at odd
    # ends, in every writing mode, and clipped without losing its phase.
    ("styled lines: backwards, vertical, odd ends, every mode, clipped", [
        (VSL_COLOR, (), (1,)), (VSL_TYPE, (), (3,)),
        (V_PLINE, (401, 20, 11, 20), ()),
        (V_PLINE, (11, 22, 401, 22), ()),
        (V_PLINE, (20, 30, 20, 199), ()),
        (V_PLINE, (23, 199, 23, 30), ()),
        (VSL_UDSTY, (), (0x5555,)), (VSL_TYPE, (), (7,)),
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (4,)),
        (VR_RECFL, (40, 40, 200, 120), ()),
        (VSWR_MODE, (), (3,)),
        (V_PLINE, (30, 60, 300, 60), ()),
        (V_PLINE, (100, 30, 100, 150), ()),
        (V_PLINE, (300, 62, 30, 62), ()),
        (V_PLINE, (300, 62, 30, 62), ()),
        (VSWR_MODE, (), (2,)), (VSL_COLOR, (), (6,)),
        (V_PLINE, (30, 80, 300, 80), ()),
        (V_PLINE, (101, 30, 101, 150), ()),
        (VSWR_MODE, (), (4,)),
        (V_PLINE, (30, 100, 300, 100), ()),
        (V_PLINE, (102, 30, 102, 150), ()),
        (VSWR_MODE, (), (2,)), (VSL_COLOR, (), (0,)),
        (V_PLINE, (30, 110, 300, 110), ()),
        (V_PLINE, (103, 30, 103, 150), ()),
        (VSWR_MODE, (), (4,)),
        (V_PLINE, (30, 112, 300, 112), ()),
        (V_PLINE, (104, 30, 104, 150), ()),
        (VSWR_MODE, (), (1,)), (VSL_COLOR, (), (1,)),
        (VS_CLIP, (50, 50, 150, 150), (1,)),
        (V_PLINE, (0, 55, 639, 55), ()),
        (V_PLINE, (61, 239, 61, 0), ()),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (VSL_TYPE, (), (1,))]),

    # Diagonals step pixel by pixel through the MEMAC window (line_diag in
    # vdi.c): the style rotates with the pixel count from the first point --
    # and restarts at every vertex -- the writing mode decides what a clear
    # style bit does, and the clip is applied per pixel without disturbing
    # the phase, including the pixels a line spends off the screen.
    ("diagonals: styled, every mode, clipped, off the screen", [
        (VSF_INTERIOR, (), (1,)), (VSF_COLOR, (), (4,)),
        (VR_RECFL, (40, 40, 300, 160), ()),
        (VSL_COLOR, (), (1,)), (VSL_TYPE, (), (3,)),
        (V_PLINE, (10, 10, 330, 90), ()),
        (V_PLINE, (330, 95, 10, 15), ()),
        (V_PLINE, (10, 200, 60, 230, 110, 200, 160, 235), ()),
        (VSL_TYPE, (), (1,)), (VSWR_MODE, (), (2,)),
        (V_PLINE, (20, 170, 200, 30), ()),
        (VSL_TYPE, (), (5,)),
        (V_PLINE, (25, 170, 205, 30), ()),
        (VSWR_MODE, (), (3,)),
        (V_PLINE, (30, 170, 210, 30), ()),
        (VSWR_MODE, (), (4,)),
        (V_PLINE, (35, 170, 215, 30), ()),
        (VSWR_MODE, (), (1,)), (VSL_TYPE, (), (1,)),
        (V_PLINE, (-20, -10, 120, 60), ()),
        (V_PLINE, (600, 200, 700, 260), ()),
        (VS_CLIP, (51, 61, 250, 141), (1,)),
        (VSL_TYPE, (), (3,)),
        (V_PLINE, (0, 0, 400, 200), ()),
        (V_PLINE, (400, 0, 0, 200), ()),
        (VSWR_MODE, (), (3,)),
        (V_PLINE, (0, 200, 400, 0), ()),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (VSWR_MODE, (), (1,)), (VSL_TYPE, (), (1,))]),

    ("vex_timv reports the tick length", [
        (VEX_TIMV, (), ())]),

    # vsl_udsty installs the pattern used by line type 7, which the AES uses
    # for rubber-band outlines -- so this one IS visible.
    ("user-defined line style", [
        (VSL_COLOR, (), (1,)),
        (VSL_UDSTY, (), (0xF0F0,)), (VSL_TYPE, (), (7,)),
        (V_PLINE, (10, 20, 400, 20), ()),
        (VSL_UDSTY, (), (0xAAAA,)),
        (V_PLINE, (10, 40, 400, 40), ()),
        (VSL_UDSTY, (), (0xFFFF,)),
        (V_PLINE, (10, 60, 400, 60), ()),
        (VSL_TYPE, (), (1,))]),

    ("text metrics report the real cell, not what was asked for", [
        (VST_HEIGHT, (0, 13), ()),          # a size this driver does not have
        (VST_HEIGHT, (0, 8), ()),
        (VST_COLOR, (), (9,)),
        (VQT_ATTRIBUTES, (), ()),
        (VSWR_MODE, (), (2,)),
        (VQT_ATTRIBUTES, (), ()),
        (VSWR_MODE, (), (1,)),
        (V_ESCAPE, (), ())]),               # sub 2/3: nop on a graphics driver

    ("cpyfm overlapping, moving right and down", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (20, 20, 79, 59), ()),
        (VSF_COLOR, (), (6,)), (VR_RECFL, (30, 30, 49, 49), ()),
        (VRO_CPYFM, (20, 20, 79, 59, 40, 40, 99, 79), (3,))]),

    # --- forms in VRAM.  An MFDB with fd_addr != 0 names a form off the
    # screen; the AES's menu and alert save buffer (bb_save / bb_restore) is
    # one.  "to_save" copies screen -> buffer, "from_save" buffer -> screen.
    ("cpyfm to the save form and back", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (20, 20, 79, 59), ()),
        (VSF_COLOR, (), (6,)), (VR_RECFL, (30, 30, 49, 49), ()),
        (VRO_CPYFM, (20, 20, 79, 59, 20, 20, 79, 59), (3,), "to_save"),
        (VSF_COLOR, (), (0,)), (VR_RECFL, (0, 0, 99, 99), ()),
        (VSF_COLOR, (), (3,)), (VR_RECFL, (40, 40, 44, 44), ()),
        (VRO_CPYFM, (20, 20, 79, 59, 20, 20, 79, 59), (3,), "from_save")]),

    ("cpyfm save form at odd x, odd width: the pixel path into a form", [
        (VSF_COLOR, (), (5,)), (VR_RECFL, (21, 20, 79, 59), ()),
        (VSF_COLOR, (), (1,)), (VR_RECFL, (33, 30, 49, 49), ()),
        (VRO_CPYFM, (21, 20, 79, 59, 21, 20, 79, 59), (3,), "to_save"),
        (VSF_COLOR, (), (0,)), (VR_RECFL, (0, 0, 99, 99), ()),
        (VRO_CPYFM, (21, 20, 79, 59, 21, 20, 79, 59), (3,), "from_save"),
        (VRO_CPYFM, (21, 20, 79, 59, 200, 100, 258, 139), (3,), "from_save")]),

    ("cpyfm from a form, destination clipped by the screen edge", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 0, 39, 19), ()),
        (VSF_COLOR, (), (7,)), (VR_RECFL, (10, 5, 29, 14), ()),
        (VRO_CPYFM, (0, 0, 39, 19, 0, 0, 39, 19), (3,), "to_save"),
        (VRO_CPYFM, (0, 0, 39, 19, 620, 230, 659, 249), (3,), "from_save")]),

    # The workstation's clip rectangle applies to the screen only: a save
    # under a clip that excludes it must still take the whole rectangle,
    # or the restore after the clip is lifted comes back short.
    ("cpyfm to a form ignores the clip rectangle", [
        (VSF_COLOR, (), (2,)), (VR_RECFL, (100, 50, 179, 89), ()),
        (VS_CLIP, (0, 0, 9, 9), (1,)),
        (VRO_CPYFM, (100, 50, 179, 89, 100, 50, 179, 89), (3,), "to_save"),
        (VS_CLIP, (0, 0, 0, 0), (0,)),
        (VSF_COLOR, (), (0,)), (VR_RECFL, (90, 40, 189, 99), ()),
        (VRO_CPYFM, (100, 50, 179, 89, 100, 50, 179, 89), (3,), "from_save")]),

    # A source past the edge of its form is clipped, and the destination
    # loses the same span.  The donor reads on past the edge instead.
    ("cpyfm source off the screen edge is clipped", [
        (VSF_COLOR, (), (4,)), (VR_RECFL, (0, 0, 29, 19), ()),
        (VSF_COLOR, (), (2,)), (VR_RECFL, (610, 220, 639, 239), ()),
        (VRO_CPYFM, (-10, -10, 29, 19, 100, 100, 139, 129), (3,)),
        (VRO_CPYFM, (620, 230, 659, 269, 200, 100, 239, 139), (3,))]),
]


def poke_script(b, addr, script, mfdb_addr=0, room=None, screen_mfdb=0):
    words = vdiref.encode(script, mfdb_addr, screen_mfdb)
    data = b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                    for w in words)
    # The runner stops at the end of its buffer, mid-script, and the words
    # past it land on whatever follows.
    assert room is None or len(data) <= room, (len(data), room)
    b.memload(addr, data)


def wait_done(b, timeout_frames=4000):
    n = 0
    while n < timeout_frames:
        if b.peek(STATUS + ST_DONE) == 0xA5:
            return True
        b.frames(4)
        n += 4
    return False


# Sys op 17: the screen again, at another width (src/m3_vdi.c).  intin[0]
# is the width index; it answers 0 and the w/h/stride it came up with.
SCREEN_OP = 3017


def run_sys(b, script_addr, op, ints=()):
    """One sys op, on its own, and its record back.  None if it hung."""
    poke_script(b, script_addr, [(op, (), tuple(ints), None, 0)])
    b.poke(STATUS + ST_DONE, 0)
    b.poke(STATUS + ST_GO, 1)
    if not wait_done(b):
        return None
    b.frames(4)
    n = b.peek16(_COUNT_ADDR[0])
    if n < 1:
        return None
    return vdiref.decode(
        b.memdump(_RESULTS_ADDR[0], n * vdiref.RESULT_WORDS * 2), n)[0]


# Filled by main(); run_sys is called from there and from run_cases and
# would otherwise want four more arguments to say the same thing.
_RESULTS_ADDR, _COUNT_ADDR = [0], [0]


def main(argv):
    only = None
    keep_shots = "--shot" in argv
    # Every width by default.  --width 640 runs one, for a bisect.
    widths = None
    if "--width" in argv:
        widths = {int(argv[argv.index("--width") + 1])}
    if "--case" in argv:
        only = int(argv[argv.index("--case") + 1])
    os.makedirs(SHOTDIR, exist_ok=True)

    syms = symfile.load(SYMS)
    script_addr = syms["vdi_script"]
    script_room = min(a for a in syms.values() if a > script_addr) - script_addr
    scratch_addr = syms["vdi_scratch"]
    results_addr = syms["vdi_results"]
    count_addr = syms["vdi_result_count"]
    scratch_room = min(a for a in syms.values() if a > scratch_addr) - scratch_addr
    _RESULTS_ADDR[0], _COUNT_ADDR[0] = results_addr, count_addr
    assert 552 + 20 <= scratch_room, "the MFDBs must fit vdi_scratch"

    emu = launch(tag="m3", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    results = []
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        # Ready is STATUS[2] == 1, not the signature: the runner raises
        # 'VD' early and finishes starting up (farmem_probe among it) some
        # frames later, and how many moves with the size of the image.
        for _ in range(200):
            tag = bytes(b.memdump(STATUS, 3))
            if tag[:2] == b"VD" and tag[2] == 1:
                break
            b.frames(4)

        tag = bytes(b.memdump(STATUS, 3))
        print(f"runner: {tag[:2]!r} stage=${tag[2]:02X}  "
              f"vdi_script=${script_addr:04X} vdi_scratch=${scratch_addr:04X}")
        if tag[:2] != b"VD" or tag[2] != 1:
            print("FAIL: runner did not come up")
            return 1

        # EVERY CASE AT EVERY WIDTH.  The overlay has three
        # (src/vbxe/vbxe.h) and a 4bpp rasteriser's hard parts -- the
        # partial byte at each end of a rectangle, the clip, the stride a
        # blit steps by -- are exactly the parts a different width
        # moves.  Sys op 3017 re-brings the screen up at one, which is
        # what main() does at boot and not a mode switch; every case
        # opens its own workstation after it.  One pass is ~40 seconds.
        for wi, px in enumerate(vbxeref.SCR_WIDTHS):
            if widths is not None and px not in widths:
                continue
            rec = run_sys(b, script_addr, SCREEN_OP, (wi,))
            # A record is [contrl[2], contrl[4], intout[0..14], ptsout...]
            # (src/m3_vdi.c record_vdi), so intout[n] is at n + 2.
            if rec is None or rec[2 + 6] != 0:
                results.append((-1, f"screen {px}", "the runner refused it"))
                break
            gw, gh, gstride = rec[2 + 7], rec[2 + 8], rec[2 + 9]
            if (gw, gstride) != (px, px // 2):
                results.append((-1, f"screen {px}",
                                f"the runner came up {gw}x{gh} stride {gstride}"))
                break
            print(f"  -- {gw}x{gh}, stride {gstride} "
                  f"(shot column {vbxeref.shot_x0(gw)} on) --")
            save = vdiref.VramForm.save_buffer(scratch_addr + 552, w=gw, h=gh)
            FORMS = {"icon": (ICON_BITS, ICON_WDW),
                     "to_save": (None, save), "from_save": (save, None)}
            run_cases(b, px, gw, gh, save, FORMS, results, only, keep_shots,
                      script_addr, scratch_addr, results_addr, count_addr,
                      script_room)
    finally:
        emu.stop()

    fails = [r for r in results if r[2]]
    print()
    for idx, name, err in fails:
        print(f"   FAIL [{idx}] {name}: {err}")
    print(f"gem4xe-m3: {len(results) - len(fails)}/{len(results)} VDI cases passed")
    return 1 if fails else 0


def run_cases(b, px, gw, gh, save, FORMS, results, only, keep_shots,
              script_addr, scratch_addr, results_addr, count_addr, script_room):
    """The whole suite once, on whatever screen is up."""
    if True:
        for idx, (name, script) in enumerate(CASES):
            if only is not None and idx != only:
                continue
            # v_opnwk first, with the AES's work_in: it resets driver state
            # (cursor included), which the host reference gets for free by
            # constructing a new VDI and the target must be told to do.
            full = [(vdiref.V_OPNWK, (), vdiref.WORK_IN), (V_CLRWK,)] + script

            resolved = [
                (r[0], r[1] if len(r) > 1 else (), r[2] if len(r) > 2 else (),
                 FORMS[r[3]] if len(r) > 3 and r[3] is not None else None,
                 r[4] if len(r) > 4 else 0)
                for r in full]
            ref = vdiref.VDI(devref.Vbxe(width=gw, height=gh))
            ref.run(resolved)

            # Stage the forms' MFDBs where the driver will read them: the
            # icon's, the screen's (fd_addr 0) and the save buffer's.
            b.memload(scratch_addr, ICON_BITS)
            b.memload(scratch_addr + 512,
                      pack_mfdb(scratch_addr, ICON_W, ICON_H, ICON_WDW))
            b.memload(scratch_addr + 532, pack_mfdb(0, 0, 0, 0))
            b.memload(scratch_addr + 552, save.pack())
            poke_script(b, script_addr, resolved, scratch_addr + 512, script_room,
                        screen_mfdb=scratch_addr + 532)
            b.poke(STATUS + ST_DONE, 0)
            b.poke(STATUS + ST_GO, 1)
            if not wait_done(b):
                results.append((idx, name, "timed out"))
                continue
            b.frames(4)

            # Returned values, call for call.  Skipped for the two opcodes
            # whose result depends on live hardware (v_string, vq_key_s) and
            # for vex_* , whose "old vector" is a target address.
            err = None
            nres = b.peek16(count_addr)
            if nres != len(ref.results):
                err = f"{nres} calls recorded, expected {len(ref.results)}"
            else:
                got = vdiref.decode(
                    b.memdump(results_addr, nres * vdiref.RESULT_WORDS * 2), nres)
                for i, rec in enumerate(got):
                    if rec != ref.results[i]:
                        err = (f"call {i} (op {full[i][0]}) returned {rec}, "
                               f"expected {ref.results[i]}")
                        break

            shot = os.path.join(SHOTDIR, f"m3-{px}-{idx:02d}.png")
            b.screenshot(shot)
            bad, shown = vbxeref.compare_to_shot(ref.to_rgb(), shot)
            if bad and not err:
                err = f"{bad} px differ; first {shown[:3]}"
            results.append((idx, f"{name} @{px}", err))
            if not err and not keep_shots:
                os.remove(shot)
            print(f"  [{idx:2d}] {name:<38s} {'ok' if not err else 'FAIL'}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
