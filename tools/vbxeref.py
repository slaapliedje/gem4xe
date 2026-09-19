#!/usr/bin/env python3
"""Host-side reference model of the VBXE HR surface and blitter.

This is the specification the on-target code must match. It exists so a test
can say "these exact pixels" rather than "it looked right in a screenshot" --
the pattern that made vbxetxtadv's conformance suite worth having, and the
thing Phase 2's VDI opcode tests will be built on.

Models only what gem4xe uses: a 4bpp HR overlay (2 pixels per byte, high
nibble = LEFT pixel) and the blitter's BCB semantics.
"""
import os as _os
import re as _re

_VBXE_H = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                        "..", "src", "vbxe", "vbxe.h")


def vram_symbol(name):
    """A VRAM address from vbxe.h's map, read rather than restated, so no
    model's picture of VRAM can drift from the driver's."""
    m = _re.search(r"#define\s+%s\s+0x([0-9A-Fa-f]+)UL" % name,
                   open(_VBXE_H).read())
    if not m:
        raise KeyError(name)
    return int(m.group(1), 16)


# The DEFAULT screen: the VBXE's normal overlay, which is what every
# gate that has nothing to say about the width gets.  The width is not a
# global that anything rebinds -- it travels through construction, from
# devref.Vbxe(width=...) into the Surface -- because a module constant
# that changes underneath a `from vbxeref import SCR_W` somewhere else
# is exactly the silent disagreement this model exists to prevent.
SCR_W, SCR_H = 640, 240
STRIDE = SCR_W // 2                       # 320 bytes per row
# The three the overlay has: 128, 160 and 168 colour clocks at four HR
# pixels each (src/vbxe/vbxe.h).
SCR_WIDTHS = (512, 640, 672)

# Where the overlay lands in an Altirra screenshot, MEASURED at all three
# widths, not assumed: a 672-wide capture holds the wide overlay exactly
# (columns 0..671), the normal one at 16..655 and the narrow one at
# 80..591.  All three are centred in it, so the crop follows the width
# rather than being three constants that could disagree with each other.
SHOT_FULL_W, SHOT_FULL_H = 672, 240
SHOT_Y0, SHOT_H = 0, SCR_H


def shot_x0(width):
    """The first column of a `width`-pixel overlay in a full capture."""
    return (SHOT_FULL_W - width) // 2


SHOT_X0, SHOT_W = shot_x0(SCR_W), SCR_W


def dac(v):
    """Expand a written colour byte the way the VBXE DAC does.

    Only the top 7 bits are significant and the bit that comes back out is a
    copy of the top one, so $96 reads back as $97 and $7F as $7E.  Confirmed
    against a real screenshot on every one of 16 test colours.
    """
    return (v & 0xFE) | (v >> 7)


class Surface:
    """A VBXE VRAM region addressed as bytes; 4bpp pixels are packed 2/byte."""

    def __init__(self, size=0x80000, width=SCR_W, height=SCR_H):
        # The screen this VRAM is showing.  Everything above the blitter
        # is bytes and knows nothing about it; pixel() and to_rgb() are
        # the two that have to.
        self.w, self.h = width, height
        self.stride = width // 2        # HR is 4bpp: two pixels to a byte
        self.mem = bytearray(size)

    # -- blitter ---------------------------------------------------------
    def blit(self, src, sstride, dst, dstride, nbytes, rows,
             and_mask=0xFF, xor_mask=0x00, mode=0, sxstep=1, dxstep=1):
        """One BCB.  c = (source & and_mask) ^ xor_mask, then written per mode.

        and_mask == 0 is the constant-source fill: no source byte is read at
        all (and on hardware it costs 1 cycle/byte instead of 2).
        """
        if not 1 <= nbytes <= 512:
            raise ValueError(f"blit width {nbytes} outside the 9-bit field (1..512)")
        if not 1 <= rows <= 256:
            raise ValueError(f"blit height {rows} outside the 8-bit field (1..256)")
        for r in range(rows):
            sp = src + r * sstride
            dp = dst + r * dstride
            for i in range(nbytes):
                c = (0 if and_mask == 0 else self.mem[sp]) & and_mask
                c ^= xor_mask
                if mode == 0:
                    self.mem[dp] = c
                elif c:
                    d = self.mem[dp]
                    if mode == 1:
                        self.mem[dp] = c
                    elif mode == 2:
                        self.mem[dp] = (c + d) & 0xFF
                    elif mode == 3:
                        self.mem[dp] = c | d
                    elif mode == 4:
                        self.mem[dp] = c & d
                    elif mode == 5:
                        self.mem[dp] = c ^ d
                    elif mode == 6:                   # per-nibble stencil
                        hi, lo = c & 0xF0, c & 0x0F
                        self.mem[dp] = ((hi if hi else d & 0xF0) |
                                        (lo if lo else d & 0x0F))
                else:
                    # c == 0.  Every mode skips the write EXCEPT AND, which
                    # writes 0 -- so `x & 0` still clears, as it should.
                    # (vbxe.cpp BlitRow: the T_Mode == 4 branch of the else.)
                    if mode == 4:
                        self.mem[dp] = 0
                sp += sxstep
                dp += dxstep

    def fill(self, dst, stride, nbytes, rows, value):
        self.blit(0, 0, dst, stride, nbytes, rows, and_mask=0x00, xor_mask=value)

    def copy(self, src, sstride, dst, dstride, nbytes, rows):
        self.blit(src, sstride, dst, dstride, nbytes, rows, and_mask=0xFF)

    def move(self, src, sstride, dst, dstride, nbytes, rows):
        """An overlap-safe copy (vbxe.c blit_move): backwards, from the
        last byte of the last row, when the destination is higher."""
        if dst <= src:
            self.copy(src, sstride, dst, dstride, nbytes, rows)
            return
        self.blit(src + (rows - 1) * sstride + nbytes - 1, -sstride,
                  dst + (rows - 1) * dstride + nbytes - 1, -dstride,
                  nbytes, rows, and_mask=0xFF, sxstep=-1, dxstep=-1)

    def rmw(self, dst, stride, nbytes, rows, value, mode):
        """Constant-source read-modify-write: the 4bpp edge primitive."""
        self.blit(0, 0, dst, stride, nbytes, rows,
                  and_mask=0x00, xor_mask=value, mode=mode)

    # -- rendering -------------------------------------------------------
    def pixel(self, base, x, y):
        b = self.mem[base + y * self.stride + x // 2]
        return (b >> 4) if (x & 1) == 0 else (b & 0x0F)

    def to_rgb(self, base, palette):
        """Return [[(r,g,b), ...] ...] as the DAC would drive it."""
        pal = [tuple(dac(c) for c in palette[i * 3:i * 3 + 3]) for i in range(16)]
        return [[pal[self.pixel(base, x, y)] for x in range(self.w)]
                for y in range(self.h)]


def save_rgb(expected_rgb, path):
    """The model's own picture, written where it can be looked at beside
    the target's screenshot.  A gate that only reports how many pixels
    differ says nothing about WHAT differs; this is how the two are put
    side by side."""
    from PIL import Image
    im = Image.new("RGB", (len(expected_rgb[0]), len(expected_rgb)))
    im.putdata([px for row in expected_rgb for px in row])
    im.save(path)
    return path


def compare_to_shot(expected_rgb, shot_path, max_report=8):
    """Compare the reference image against an Altirra screenshot.

    Returns (n_mismatches, [(x, y, expected, got), ...]).
    """
    from PIL import Image
    im = Image.open(shot_path).convert("RGB")
    px = im.load()
    # The crop follows the picture the model produced: a narrower overlay
    # sits further into the capture, and the capture is the same size
    # whatever the width.  Taken from the data rather than from a
    # parameter so that a caller cannot compare a 512-pixel model against
    # a 640-pixel crop and be told the whole screen is wrong.
    h, w = len(expected_rgb), len(expected_rgb[0])
    x0 = shot_x0(w)
    bad, shown = 0, []
    for y in range(h):
        for x in range(w):
            got = px[x0 + x, SHOT_Y0 + y]
            want = expected_rgb[y][x]
            if got != want:
                bad += 1
                if len(shown) < max_report:
                    shown.append((x, y, want, got))
    return bad, shown
