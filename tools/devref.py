#!/usr/bin/env python3
"""The MODEL's side of the VDI's device seam -- src/vdi/vdidev.h, in Python.

tools/vdiref.py is the specification the target's src/vdi/vdi.c has to
agree with, and until now it was written to ONE surface: 640x240 at 4bpp,
with the VBXE's nibble packing and its `map_col` permutation inline in
the rasteriser.  That was true of vdi.c too until phase 32, and stopped
being true of it in phase 34.  This is the model catching up, and it is
what lets the AES model (tools/aesref.py) and the desktop model
(tools/deskref.py) be run against a SECOND screen without either of them
changing a line -- which is the same claim the C side makes, checked the
same way.

THE CONTRACT IS THE C's, name for name where the shapes allow it.  A
device declares its geometry and the system font's metrics as fields,
and answers the calls below.  Everything above the seam -- clipping,
writing modes, attributes, text placement, the workstation -- belongs to
vdiref and is device-independent.

    w, h, stride              the surface; SCR_W, SCR_H, SCR_STRIDE
    font_w .. font_point      the system font's cell and its head
    face                      the 1bpp strip that cell is drawn from

    clear()                   v_clrwk's screen
    fill_rect(x1,y1,x2,y2,pen)  solid, corners inclusive, already clipped
    xor_rect(x1,y1,x2,y2)       the same, complemented
    plot(x, y, pen)             one pixel, clipped to the SCREEN only
    plot_xor(x, y)
    pixel(x, y)                 what the device stores there
    pen_of(value)               ...and the VDI pen it means
    pen_value(pen)              the inverse

    screen_form()               the screen as a raster form
    copy(sb,ss,sx,sy, db,ds,dx,dy, w,h)   a rectangle moved, in PIXELS
    read_pixel(base, stride, x, y)        one pixel out of a form

    cursor_save(cx,cy) / cursor_restore() / cursor_discard()

    colours() / planes()
    palette_all(rgb) / palette_one(pen, rgb)
    to_rgb() / key()

THE PEN IS THE VDI'S, not the hardware's -- the same rule the C states.
A caller passes the pen it was given; `map_col` and the nibble packing
are the VBXE device's business and a device with two colours has neither
to map.
"""
import zlib

# GEM's standard palette order: pen 0 is WHITE, pen 1 is BLACK.  Here
# rather than in vdiref because what a device does with it -- permute it,
# reduce it to two luminances, ignore it -- is the device's business.
GEM_PAL = bytes((
    0xFF, 0xFF, 0xFF,  0x00, 0x00, 0x00,  0xFF, 0x00, 0x00,  0x00, 0xFF, 0x00,
    0x00, 0x00, 0xFF,  0x00, 0xFF, 0xFF,  0xFF, 0xFF, 0x00,  0xFF, 0x00, 0xFF,
    0xBB, 0xBB, 0xBB,  0x77, 0x77, 0x77,  0xBB, 0x00, 0x00,  0x00, 0xBB, 0x00,
    0x00, 0x00, 0xBB,  0x00, 0xBB, 0xBB,  0xBB, 0xBB, 0x00,  0xBB, 0x00, 0xBB))

import anticref
import fontref
import vbxeref


class Vbxe:
    """640x240, 4bpp, two pixels to a byte with the LEFT one in the high
    nibble -- so every rectangle has up to two partial ends, which is
    where 4bpp VDI drivers historically went wrong and why the
    conformance suite has eleven cases about edges alone.

    The code here was inline in vdiref until the seam was drawn; it is
    the same code, and the digests of all 99 model cases are what says
    so.
    """

    # -- the surface -----------------------------------------------------
    # Set per INSTANCE in __init__, not per class: the overlay has three
    # widths (src/vbxe/vbxe.h) and the target has a device table for each
    # (src/vdi/dev_vbxe.c, nine of them with the heights).  These are the
    # defaults, which is the normal 640-pixel screen.

    # -- the system font's cell, and the rest of its head ----------------
    font_w, font_h, font_top = 8, 8, 6
    font_ascent, font_half, font_descent, font_bottom = 6, 4, 1, 1
    font_point = 9

    # The VDI's pen order into this device's hardware indices.  XOR mode
    # complements pixel bits and the AES needs black <-> white to survive
    # that, so black is stored as 15 and white as 0; the palette is
    # loaded in hardware order (src/vdi/dev_vbxe.c, map_col).
    MAP_COL = (0, 15, 1, 2, 4, 6, 3, 5, 7, 8, 9, 10, 12, 14, 11, 13)

    def __init__(self, face=None, pal=None, width=vbxeref.SCR_W,
                 height=vbxeref.SCR_H):
        self.w, self.h = width, height
        self.stride = width // 2        # HR is 4bpp: two pixels to a byte
        # all 512 KB: forms live above the screen
        self.s = vbxeref.Surface(width=width, height=height)
        self.base = 0
        self.face = fontref.FONT_8X8 if face is None else face
        self.hw_pal = bytearray(48)
        self.palette_all(GEM_PAL if pal is None else pal)
        self.sv = None                  # (bx, y, nb, nr, bytes) under the cursor
        self.clear()

    # -- colours ---------------------------------------------------------
    @staticmethod
    def colours():
        return 16

    @staticmethod
    def planes():
        return 4

    def pen_value(self, pen):
        return self.MAP_COL[pen & 15]

    def pen_of(self, value):
        return self.MAP_COL.index(value)

    def palette_all(self, pal):
        """Sixteen VDI pens' worth of 8-bit RGB, in VDI PEN ORDER.  The
        device puts them wherever its hardware keeps them."""
        for pen in range(16):
            self.palette_one(pen, pal[pen * 3:pen * 3 + 3])

    def palette_one(self, pen, rgb):
        """Three 8-bit components for one VDI pen, permuted into the order
        the hardware holds them."""
        self.hw_pal[self.MAP_COL[pen] * 3:self.MAP_COL[pen] * 3 + 3] = bytes(rgb)

    def palette_of(self, pen):
        i = self.MAP_COL[pen] * 3
        return tuple(self.hw_pal[i:i + 3])

    # -- pixels ----------------------------------------------------------
    def clear(self):
        self.s.fill(self.base, self.stride, self.stride, self.h, 0x00)

    def fill_rect(self, x1, y1, x2, y2, pen):
        """Mirrors dev_fill_rect() in src/vdi/dev_vbxe.c exactly, edges
        included."""
        hwpen = self.MAP_COL[pen & 15]
        stride = self.stride
        base = self.base + y1 * stride
        rows = y2 - y1 + 1
        c = ((hwpen & 0x0F) << 4) | (hwpen & 0x0F)
        bl, br = x1 >> 1, x2 >> 1
        if bl == br:
            if (x1 & 1) == 0 and (x2 & 1) == 1:
                self.s.fill(base + bl, stride, 1, rows, c)
            elif x1 & 1:
                self.s.rmw(base + bl, stride, 1, rows, 0xF0, 4)
                self.s.rmw(base + bl, stride, 1, rows, c & 0x0F, 3)
            else:
                self.s.rmw(base + bl, stride, 1, rows, 0x0F, 4)
                self.s.rmw(base + bl, stride, 1, rows, c & 0xF0, 3)
            return
        if x1 & 1:
            self.s.rmw(base + bl, stride, 1, rows, 0xF0, 4)
            self.s.rmw(base + bl, stride, 1, rows, c & 0x0F, 3)
            bl += 1
        if (x2 & 1) == 0:
            self.s.rmw(base + br, stride, 1, rows, 0x0F, 4)
            self.s.rmw(base + br, stride, 1, rows, c & 0xF0, 3)
            br -= 1
        if br >= bl:
            self.s.fill(base + bl, stride, br - bl + 1, rows, c)

    def xor_rect(self, x1, y1, x2, y2):
        """Mirrors dev_xor_rect(): complement every pixel, edges by nibble."""
        stride = self.stride
        base = self.base + y1 * stride
        rows = y2 - y1 + 1
        bl, br = x1 >> 1, x2 >> 1
        if bl == br:
            m = 0x0F if (x1 & 1) else (0xF0 if (x2 & 1) == 0 else 0xFF)
            self.s.rmw(base + bl, stride, 1, rows, m, 5)
            return
        if x1 & 1:
            self.s.rmw(base + bl, stride, 1, rows, 0x0F, 5)
            bl += 1
        if (x2 & 1) == 0:
            self.s.rmw(base + br, stride, 1, rows, 0xF0, 5)
            br -= 1
        if br >= bl:
            self.s.rmw(base + bl, stride, br - bl + 1, rows, 0xFF, 5)

    def plot(self, x, y, pen):
        """One pixel in a VDI pen, clipped to the SCREEN only: the
        workstation's own clip belongs above the seam."""
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        hwpen = self.MAP_COL[pen & 15]
        a = self.base + y * self.stride + (x >> 1)
        b = self.s.mem[a]
        if x & 1:
            self.s.mem[a] = (b & 0xF0) | (hwpen & 0x0F)
        else:
            self.s.mem[a] = (b & 0x0F) | ((hwpen & 0x0F) << 4)

    def plot_xor(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        a = self.base + y * self.stride + (x >> 1)
        self.s.mem[a] ^= 0x0F if (x & 1) else 0xF0

    def pixel(self, x, y):
        """What the device stores at (x, y) -- a hardware pen here.  Zero
        off the screen, which is what v_get_pixel reports there."""
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        return self.read_pixel(self.base, self.stride, x, y)

    # -- raster forms ----------------------------------------------------
    def screen_form(self):
        return self.base, self.stride, self.w, self.h, True

    def save_form(self):
        """Where the AES saves what a menu or a dialog covers: a whole
        screen at VR_SAVE, laid out like the screen.  VRAM is the reason
        this is cheap here and the reason the other device has to find
        the room somewhere else."""
        return Form(vbxeref.vram_symbol("VR_SAVE"), self.w, self.h,
                    self.stride)

    def read_pixel(self, base, stride, x, y):
        v = self.s.mem[base + y * stride + (x >> 1)]
        return (v & 0x0F) if (x & 1) else (v >> 4)

    def write_pixel(self, base, stride, x, y, value):
        a = base + y * stride + (x >> 1)
        b = self.s.mem[a]
        if x & 1:
            self.s.mem[a] = (b & 0xF0) | value
        else:
            self.s.mem[a] = (b & 0x0F) | (value << 4)

    def copy(self, sb, ss, sx1, sy1, db, ds, dx1, dy1, w, h):
        """A rectangle moved between forms, in PIXELS, already clipped.

        The blitter has no shifter, so 4bpp pixels can only be moved
        between positions of the same parity: when they are -- and the
        run is a whole number of bytes -- it is one blit, and otherwise it
        is pixel by pixel through the MEMAC window.  Both paths must
        produce the same pixels, which is what the conformance cases
        check.  The direction is chosen so an overlapping move does not
        eat its own source.
        """
        if ((sx1 ^ dx1) & 1) == 0 and (sx1 & 1) == 0 and (w & 1) == 0:
            self.s.move(sb + sy1 * ss + (sx1 >> 1), ss,
                        db + dy1 * ds + (dx1 >> 1), ds, w >> 1, h)
            return
        for y in range(h):
            sy = (sy1 + h - 1 - y) if dy1 > sy1 else (sy1 + y)
            dy = (dy1 + h - 1 - y) if dy1 > sy1 else (dy1 + y)
            for i in range(w):
                sx = (sx1 + w - 1 - i) if dx1 > sx1 else (sx1 + i)
                dx = (dx1 + w - 1 - i) if dx1 > sx1 else (dx1 + i)
                self.write_pixel(db, ds, dx, dy,
                                 self.read_pixel(sb, ss, sx, sy))

    # -- the cursor ------------------------------------------------------
    # The VDI owns WHERE the pointer is and whether it is shown; the
    # device owns what was UNDER it.  Nine bytes at odd x, not eight
    # (docs/phase3a.md).
    def cursor_save(self, cx, cy):
        bx0, bx1 = cx >> 1, (cx + 15) >> 1
        y0, y1 = cy, cy + 15
        bx0 = max(bx0, 0); y0 = max(y0, 0)
        bx1 = min(bx1, self.stride - 1); y1 = min(y1, self.h - 1)
        if bx1 < bx0 or y1 < y0:
            self.sv = None
            return
        nb, nr = bx1 - bx0 + 1, y1 - y0 + 1
        buf = bytearray()
        for r in range(nr):
            a = self.base + (y0 + r) * self.stride + bx0
            buf += self.s.mem[a:a + nb]
        self.sv = (bx0, y0, nb, nr, bytes(buf))

    def cursor_restore(self):
        if not self.sv:
            return
        bx0, y0, nb, nr, buf = self.sv
        for r in range(nr):
            a = self.base + (y0 + r) * self.stride + bx0
            self.s.mem[a:a + nb] = buf[r * nb:(r + 1) * nb]
        self.sv = None

    def cursor_discard(self):
        self.sv = None

    # -- readback --------------------------------------------------------
    def to_rgb(self):
        return self.s.to_rgb(self.base, bytes(self.hw_pal))

    def key(self):
        return zlib.crc32(self.s.mem[self.base:
                                     self.base + self.stride * self.h])


# ---------------------------------------------------------------------
# Where an off-screen form lives on a device that has no VRAM.  The C
# calls far_alloc() and gets a 24-bit address; the model keeps one buffer
# and calls its base this, so that "is it the screen?" is the same test
# on both sides (src/vdi/dev_antic.c, form_get).
FAR_BASE = 0x10000

# The page, from src/vdi/print.h.  640 x 800 at one bit is 64,000 bytes,
# which is the largest page that still fits one far bank -- the argument
# is in docs/printing.md, and the numbers are here so the model and the C
# cannot drift apart without tests/host/test_print.py noticing.
PR_W, PR_H = 640, 800
PR_STRIDE = PR_W // 8
PR_DPI = 100


class Antic:
    """320x168, ONE bit a pixel, 40 bytes a line, in plain motherboard
    RAM -- ANTIC mode F (src/antic/antic.h).

    Everything the VBXE device has to think about twice, this one does
    not have at all: there is no nibble packing, no palette to permute,
    and no blitter whose alignment decides whether a copy is one blit or
    a pixel loop.  What it has instead is TWO COLOURS, and that is the
    interesting part -- GEM numbers its pens white 0 and black 1, and on
    a device with two of them pen 0 is the paper and anything else is the
    ink.  Nothing above the seam is told; it goes on asking for pen 7 and
    getting ink, which is the only sensible reading of "colour 7" here.
    """

    # -- the surface -----------------------------------------------------
    w, h = anticref.AN_W, anticref.AN_H
    stride = anticref.AN_STRIDE

    # -- Atari's condensed face (bios/fnt_st_6x6.c) ----------------------
    # 6 wide is 53 columns where 8 would be 40, and 6 tall is 28 rows
    # where 8 would be 21 (src/vdi/vdidev.h).
    font_w, font_h, font_top = 6, 6, 4
    font_ascent, font_half, font_descent, font_bottom = 4, 3, 1, 1
    font_point = 8

    # What Altirra renders for the two colours src/gem.c brings the
    # screen up in -- MEASURED, in tests/emu/m25_antic_vdi.py, not
    # computed: mode F gives set pixels COLPF1's LUMINANCE on COLPF2's
    # hue, and what that comes out as is the machine's business.  A gate
    # comparing against a real screenshot should take the two colours
    # from the shot and compare BITS; these are for to_rgb(), which
    # exists so that anything written for the other device still runs.
    PAPER, INK = (238, 238, 238), (0, 0, 0)

    def __init__(self, face=None, pal=None):
        self.a = anticref.Antic()
        self.face = fontref.FONT_6X6 if face is None else face
        self.off = bytearray(self.stride * self.h)   # one off-screen form
        self.sv = None
        self.clear()

    # -- colours ---------------------------------------------------------
    @staticmethod
    def colours():
        return 2                        # mode F is one bit

    @staticmethod
    def planes():
        return 1

    @staticmethod
    def pen_value(pen):
        return 1 if pen else 0

    @staticmethod
    def pen_of(value):
        return value                    # the same thing here

    def palette_all(self, pal):
        """The device takes what it can of sixteen colours: pen 0's and
        pen 1's, as luminances (src/vdi/dev_antic.c, an_lum)."""

    def palette_one(self, pen, rgb):
        """...and one of them, which on this device is COLPF1 or COLPF2.
        Neither changes a bit in the framebuffer, so there is nothing for
        the model to hold: what the two colours ARE is between the
        machine and the monitor, and a gate reads them off the screen."""

    # -- pixels ----------------------------------------------------------
    def clear(self):
        self.a.clear(0)

    def fill_rect(self, x1, y1, x2, y2, pen):
        self.a.rect_mode(x1, y1, x2, y2, anticref.MD_REPLACE, 1 if pen else 0)

    def xor_rect(self, x1, y1, x2, y2):
        self.a.rect_mode(x1, y1, x2, y2, anticref.MD_XOR, 1)

    def plot(self, x, y, pen):
        self.a.plot(x, y, 1 if pen else 0)

    def plot_xor(self, x, y):
        self.a.span(x, x, y, anticref.MD_XOR, 1)

    def pixel(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        return self.a.get_pixel(x, y)

    def bit(self, x, y):
        """The framebuffer, as a gate comparing with a screenshot reads
        it: 0 is paper and 1 is ink, whatever colours the machine gave
        them."""
        return self.a.bit(x, y)

    # -- raster forms ----------------------------------------------------
    def screen_form(self):
        return 0, self.stride, self.w, self.h, True

    def save_form(self):
        """Where the AES saves what a menu or a dialog covers.  VRAM on
        the other device; here it is far memory the driver allocates, and
        the model keeps one buffer at FAR_BASE for it."""
        return Form(FAR_BASE, self.w, self.h, self.stride)

    def _buf(self, base):
        return (self.a.mem, base) if base < FAR_BASE else (self.off,
                                                           base - FAR_BASE)

    def read_pixel(self, base, stride, x, y):
        buf, off = self._buf(base)
        return (buf[off + y * stride + (x >> 3)] >> (7 - (x & 7))) & 1

    def write_pixel(self, base, stride, x, y, value):
        buf, off = self._buf(base)
        a = off + y * stride + (x >> 3)
        bit = 0x80 >> (x & 7)
        buf[a] = (buf[a] | bit) if value else (buf[a] & ~bit & 0xFF)

    def copy(self, sb, ss, sx1, sy1, db, ds, dx1, dy1, w, h):
        """Mirrors dev_copy_form(): screen to screen is the window
        manager's move and the surface has a byte path for it; anything
        involving a form goes pixel by pixel, in the direction that stops
        an overlapping move eating its own source."""
        if sb < FAR_BASE and db < FAR_BASE:
            self.a.copy(sx1, sy1, dx1, dy1, w, h)
            return
        back_y, back_x = dy1 > sy1, dx1 > sx1
        for y in range(h):
            sy = (sy1 + h - 1 - y) if back_y else (sy1 + y)
            dy = (dy1 + h - 1 - y) if back_y else (dy1 + y)
            for i in range(w):
                sx = (sx1 + w - 1 - i) if back_x else (sx1 + i)
                dx = (dx1 + w - 1 - i) if back_x else (dx1 + i)
                self.write_pixel(db, ds, dx, dy,
                                 self.read_pixel(sb, ss, sx, sy))

    # -- the cursor ------------------------------------------------------
    # Five bytes at odd x, not four -- the same arithmetic as the VBXE's
    # nine, with eight pixels to a byte instead of two.
    def cursor_save(self, cx, cy):
        bx0, bx1 = cx >> 3, (cx + 15) >> 3
        y0, y1 = cy, cy + 15
        bx0 = max(bx0, 0); y0 = max(y0, 0)
        bx1 = min(bx1, self.stride - 1); y1 = min(y1, self.h - 1)
        if bx1 < bx0 or y1 < y0:
            self.sv = None
            return
        nb, nr = bx1 - bx0 + 1, y1 - y0 + 1
        buf = bytearray()
        for r in range(nr):
            a = (y0 + r) * self.stride + bx0
            buf += self.a.mem[a:a + nb]
        self.sv = (bx0, y0, nb, nr, bytes(buf))

    def cursor_restore(self):
        if not self.sv:
            return
        bx0, y0, nb, nr, buf = self.sv
        for r in range(nr):
            a = (y0 + r) * self.stride + bx0
            self.a.mem[a:a + nb] = buf[r * nb:(r + 1) * nb]
        self.sv = None

    def cursor_discard(self):
        self.sv = None

    # -- readback --------------------------------------------------------
    def to_rgb(self):
        return [[self.INK if self.a.bit(x, y) else self.PAPER
                 for x in range(self.w)] for y in range(self.h)]

    def key(self):
        return zlib.crc32(bytes(self.a.mem))


class Form:
    """An off-screen raster form, as vdiref's _rform reads one: an
    address, a stride and a shape.  vdiref.VramForm is the VBXE's, whose
    address is in VRAM; this is the shape a device with no VRAM hands
    back from save_form()."""

    def __init__(self, addr, w, h, stride):
        self.addr, self.w, self.h = addr, w, h
        self._stride = stride

    @property
    def stride(self):
        return self._stride


class Printer:
    """640 x 800 dots, one bit each, 80 bytes a row -- the page
    (src/vdi/print.h).  The THIRD device through the seam, and the first
    that is not a screen.

    It is a 1bpp surface like the ANTIC one and shares that surface's
    model, so almost everything here is geometry and the parts a printer
    has not got.  What it has not got is a cursor (nothing points at a
    page), a palette (a dot is on paper or it is not), and a save area
    (no menu ever comes down over one, so dev_save_form returns an MFDB
    with no address and the model returns None).

    The font is the 8x8 strip, not the condensed 6x6: 640 dots across is
    80 columns at 8, which is the width a line printer has had since
    before any of this, and the reason the page is 640 wide at all.
    """

    w, h = PR_W, PR_H
    stride = PR_STRIDE

    font_w, font_h, font_top = 8, 8, 6
    font_ascent, font_half, font_descent, font_bottom = 6, 4, 1, 1
    font_point = 8

    # Ink on paper.  Unlike the ANTIC device's pair these are not
    # measured off a screen -- there is no screen -- and to_rgb() exists
    # only so that a caller written for a screen still runs.
    PAPER, INK = (255, 255, 255), (0, 0, 0)

    def __init__(self, face=None, pal=None):
        self.a = anticref.Antic(self.w, self.h)
        self.face = fontref.FONT_8X8 if face is None else face
        self.off = bytearray(self.stride * self.h)
        self.clear()

    # -- colours ---------------------------------------------------------
    @staticmethod
    def colours():
        return 2

    @staticmethod
    def planes():
        return 1

    @staticmethod
    def pen_value(pen):
        return 1 if pen else 0

    @staticmethod
    def pen_of(value):
        return value

    def palette_all(self, pal):
        """Nothing.  dev_palette_all on this device is `(void)rgb;`."""

    def palette_one(self, pen, rgb):
        """The same."""

    # -- pixels ----------------------------------------------------------
    def clear(self):
        """A blank page is NO ink, and no ink is 0 -- the same value the
        ANTIC device clears to, for the opposite-looking reason."""
        self.a.clear(0)

    def fill_rect(self, x1, y1, x2, y2, pen):
        self.a.rect_mode(x1, y1, x2, y2, anticref.MD_REPLACE, 1 if pen else 0)

    def xor_rect(self, x1, y1, x2, y2):
        self.a.rect_mode(x1, y1, x2, y2, anticref.MD_XOR, 1)

    def plot(self, x, y, pen):
        self.a.plot(x, y, 1 if pen else 0)

    def plot_xor(self, x, y):
        self.a.span(x, x, y, anticref.MD_XOR, 1)

    def pixel(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        return self.a.get_pixel(x, y)

    def bit(self, x, y):
        return self.a.bit(x, y)

    # -- raster forms ----------------------------------------------------
    def screen_form(self):
        return 0, self.stride, self.w, self.h, True

    def save_form(self):
        return None

    def _buf(self, base):
        return (self.a.mem, base) if base < FAR_BASE else (self.off,
                                                           base - FAR_BASE)

    def read_pixel(self, base, stride, x, y):
        buf, off = self._buf(base)
        return (buf[off + y * stride + (x >> 3)] >> (7 - (x & 7))) & 1

    def write_pixel(self, base, stride, x, y, value):
        buf, off = self._buf(base)
        a = off + y * stride + (x >> 3)
        bit = 0x80 >> (x & 7)
        buf[a] = (buf[a] | bit) if value else (buf[a] & ~bit & 0xFF)

    def copy(self, sb, ss, sx1, sy1, db, ds, dx1, dy1, w, h):
        if sb < FAR_BASE and db < FAR_BASE:
            self.a.copy(sx1, sy1, dx1, dy1, w, h)
            return
        back_y, back_x = dy1 > sy1, dx1 > sx1
        for y in range(h):
            sy = (sy1 + h - 1 - y) if back_y else (sy1 + y)
            dy = (dy1 + h - 1 - y) if back_y else (dy1 + y)
            for i in range(w):
                sx = (sx1 + w - 1 - i) if back_x else (sx1 + i)
                dx = (dx1 + w - 1 - i) if back_x else (dx1 + i)
                self.write_pixel(db, ds, dx, dy,
                                 self.read_pixel(sb, ss, sx, sy))

    # -- the cursor a printer has not got --------------------------------
    def cursor_save(self, cx, cy):
        pass

    def cursor_restore(self):
        pass

    def cursor_discard(self):
        pass

    # -- readback --------------------------------------------------------
    def to_rgb(self):
        return [[self.INK if self.a.bit(x, y) else self.PAPER
                 for x in range(self.w)] for y in range(self.h)]

    def key(self):
        return zlib.crc32(bytes(self.a.mem))
