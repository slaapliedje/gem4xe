# Phase 55 -- ANTIC rectangles in one call; the desk level with VBXE

Fourth round of the 0.8.x line (optimisation and stability only).  With
text done (phase 54), the desk's own costs on the ANTIC screen were
rectangles: one `antic_span` or `antic_patt_span` a row.

| `make bench-antic` | before | after |
|---|---|---|
| `vr_recfl` 300x150, solid | 60 ms | **18.8 ms** |
| the desk's pattern, whole screen | 110 ms | **21.2 ms** |
| 200 small rectangles, 24x8 | 165 ms | **116 ms** |
| `vr_recfl` 300x150, XOR | 70 ms | **55 ms** |

and the desktop itself (`make bench-desk`):

| | ANTIC before | ANTIC after | VBXE |
|---|---|---|---|
| open DISK A | 360 ms | **280 ms** | 280 ms |
| full the window | 440 ms | **320 ms** | 320 ms |
| unfull -- the desk redraws | 440 ms | **320 ms** | 320 ms |

**The ANTIC desktop is as fast as the VBXE one now.**  Phase 52 started it
at 600 / 600 / 720.

The bench draws each case sixteen times over now, not four: at four, one
frame was 5 ms of the result, which is a quarter of a rectangle.  The
small-rectangle case includes the bench's own `i % 12` and `i / 12`, about
a tenth of it.

## What it is now

`antic_fill_rect` draws a whole rectangle, solid or patterned, in one
call.  The clip, the op and both edge masks are worked out once, and the
covered middle of each row takes the cheapest path its op allows:

- **a constant.**  An op that does not read the destination (replace), or
  any op but XOR over a solid source, makes every byte's new value one of
  two constants, the even and the odd byte of the pattern row.  They are
  stored **two bytes at a time**: an odd byte first if there is one, then
  the pair as a word (the 65816 is little-endian, so the even byte is the
  low one), then an even byte if one is left.  The edges are one read and
  `(d & ~m) | (v & m)`, rather than the whole of `AN_PUT`.
- **XOR** reads each byte and inverts the source's bits in it.
- anything else goes through `AN_PUT`, as before.

A patterned rectangle reaches the device as sixteen rows: every GEM fill
pattern repeats within sixteen (`pat_bits` indexes by `y & patmsk`, and no
mask is wider than 15), so `dev_patt_rect` asks the VDI for sixteen rows
instead of one a scanline.  `antic_rect_mode`, which the solid fill and
XOR go through, is `antic_fill_rect` with no pattern.

The per-byte parity branch and a byte store cost about 120 fast cycles a
byte, most of it the loop; the word loop halved the solid rectangle again
on its own (35 ms to 20).

## Checked

`tests/host/rect_sim.c` (`test_rect.py`) draws 512 rectangles both ways
in the compiler's simulator at the product's flags: the new call, and the
spans a row it replaced, over the same random screen.  Every mode, both
pens, solid and patterned, every alignment of the left edge, one byte wide
to most of the row, and rectangles hanging off all four edges of the
screen.  It was made to fail by swapping the even and odd constants (46 of 512).

**And then it caught a real one.**  The word loop went in after that, and
its "odd byte first" step ran even when there was no middle: a rectangle
two bytes wide whose second byte is odd had its right EDGE written whole,
mask ignored -- 13 of 512.  The first failing case, bytes 12 and 13 in
replace mode, pointed straight at it.  The assembly was read first on the
theory of another width-join miscompile (B21's shape was there: a branch
to a shared join in 8-bit mode); it was not the compiler.  Both paths
arrived narrow, and the fault was one missing `last > 1`.
`test-m24`, `test-m25` and `test-m26` hold the ANTIC VDI and desktop to
their models pixel for pixel.

## The floppy had no room for it

The DOS 2 floppy (`gem-boot.atr`) keeps 20 sectors free, enough for the
largest `DESKTOP.INF` a person can save (`tests/emu/product_boot.py`).
Before phase 54 it had 23; phase 54's text left it at exactly 20; this
round's rectangle took it to 18 -- although the far code was SMALLER
than at phase 54's commit, it packed 297 bytes worse.  Two sectors came
back without giving up any of the speed:

- `antic_patt_span` is not linked any more.  A styled horizontal line is
  one row of a rectangle -- `antic_fill_rect` reads only `rows[y & 15]`
  -- and a solid one is a solid rectangle, now with word stores too.
- `antic_glyph` is not linked any more.  `dev_glyph` draws its one cell
  as a run of one through `antic_text`, which `text_sim.c` already holds
  to `antic_glyph`'s pixels, and now tests at a length of one.  So
  `antic_text` draws only the 6-wide face, the device's own; the generic
  packer is gone.  `antic_glyph` stays in the source as the test's
  reference.

It is back at exactly 20.  The next change that adds far code to the
product will need to find its own room, and this is where to look first.

## What is left

On the desk: `antic_vline` (window borders, a read and a write a row) and
the raster path for icons.  And one thing that is not drawing at all:
while a menu is down, the menu loop spends almost the whole CPU in a
32-bit multiply.  It costs no time anybody sees -- the menu is waiting for
the mouse -- but it is work done for nothing, and worth finding.
