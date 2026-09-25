#!/usr/bin/env python3
"""style_anchor (src/vdi/vdi.c) is a rotation, and was a loop.

It anchors a 16-bit line style to the screen's 16-pixel grid: pixel j of
the result is pixel (j - from) of the mask going right and (from - j)
going left, counting pixels from bit 15.  It used to be computed exactly
that way -- sixteen trips round a loop, two variable shifts in each -- for
every line the VDI drew, and the VBXE bench put it near a tenth of opening
a window (docs/phase53.md).  Now it is a rotation right by `from`, or the
reversed mask rotated right by `from + 1`, with solid and empty masks
returned as they are.

This holds the formula to the loop it replaced, over every mask shape that
matters and a wide range of starting pixels, negative ones included.  The
C itself is held to the model by test-m3's styled lines.
"""
import random
import unittest


def loop(mask, frm, d):
    """The old C, transliterated."""
    p = 0
    for j in range(16):
        i = ((j - frm) if d > 0 else (frm - j)) & 15
        if mask & (1 << (15 - i)):
            p |= 1 << (15 - j)
    return p


def rotr(v, n):
    n &= 15
    return ((v >> n) | (v << (16 - n))) & 0xFFFF if n else v


def rotation(mask, frm, d):
    """The new C, transliterated."""
    if mask in (0xFFFF, 0x0000):
        return mask
    if d > 0:
        return rotr(mask, frm)
    r = 0
    m = mask
    for _ in range(16):
        r = ((r << 1) | (m & 1)) & 0xFFFF
        m >>= 1
    return rotr(r, frm + 1)


class TestStyleAnchor(unittest.TestCase):
    def test_every_single_bit_mask_at_every_phase(self):
        for bit in range(16):
            for frm in range(-32, 33):
                for d in (1, -1):
                    m = 1 << bit
                    self.assertEqual(rotation(m, frm, d), loop(m, frm, d),
                                     (hex(m), frm, d))

    def test_the_vdi_styles_and_random_masks(self):
        rnd = random.Random(53)
        masks = [0xFFFF, 0x0000, 0xFFF0, 0xE0E0, 0xFF18, 0xFF00, 0xF198,
                 0xAAAA, 0x5555] + [rnd.randrange(65536) for _ in range(400)]
        for m in masks:
            for frm in (-641, -17, -1, 0, 1, 7, 15, 16, 319, 639, 671):
                for d in (1, -1):
                    self.assertEqual(rotation(m, frm, d), loop(m, frm, d),
                                     (hex(m), frm, d))


if __name__ == "__main__":
    unittest.main()
