#!/usr/bin/env python3
"""shr2png.py -- render an Apple IIGS Super Hi-Res dump to a PNG.

The dump is the 32 KB at $E1:2000-$E1:9FFF: 200 lines of 160 bytes of
pixels, then 200 SCBs at +$7D00, then 16 palettes of 16 colours at +$7E00
(each colour a little-endian word, $0RGB).  Each line's SCB picks its
palette (low nibble) and its mode (bit 7: 640, else 320); bit 5 (fill
mode) is not rendered.

640 mode is four 2-bit pixels a byte, and each position in the byte draws
from its own quarter of the palette (IIGS Hardware Reference, "Super
Hi-Res graphics"): bits 7-6 from colours 8-11, 5-4 from 12-15, 3-2 from
0-3 and 1-0 from 4-7.  320 mode is two 4-bit pixels a byte, high nibble
first, each doubled across to keep the image 640 wide.

    shr2png.py DUMP OUT.png
"""
import struct
import sys
import zlib

W, H = 640, 200


def colour(w):
    r, g, b = (w >> 8) & 15, (w >> 4) & 15, w & 15
    return bytes((r * 17, g * 17, b * 17))


def render(shr):
    scbs = shr[0x7D00:0x7D00 + H]
    pals = [[colour(struct.unpack_from("<H", shr, 0x7E00 + p * 32 + c * 2)[0])
             for c in range(16)] for p in range(16)]
    rows = []
    for y in range(H):
        scb = scbs[y]
        pal = pals[scb & 15]
        line = shr[y * 160:(y + 1) * 160]
        px = bytearray()
        if scb & 0x80:
            for b in line:
                for base, sh in ((8, 6), (12, 4), (0, 2), (4, 0)):
                    px += pal[base + ((b >> sh) & 3)]
        else:
            for b in line:
                for v in (b >> 4, b & 15):
                    px += pal[v] * 2
        rows.append(bytes(px))
    return rows


def png(rows, path):
    raw = b"".join(b"\0" + r for r in rows)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def main():
    with open(sys.argv[1], "rb") as f:
        shr = f.read()
    if len(shr) != 0x8000:
        raise SystemExit(f"{sys.argv[1]}: {len(shr)} bytes, not 32768")
    png(render(shr), sys.argv[2])


if __name__ == "__main__":
    main()
