# Phase 105 -- a form to memory and back, and bold text

Items 3 and 4 of `roadmap-0.12.md`: on the VBXE, G4BENCH's "screen to
memory, back" took five times ANTIC's, and on both screens its bold line
took about twice its plain one.

## Where the copy went

G4BENCH copies a 64 x 32 form out of its window's work area into its
own memory, and back to another place in the window.  The work area's
x is odd, so the two ends of each copy are of different parity: every
pixel moves by half a byte.  `tests/emu/bench_vdi.py memcopy` does the
same copy (`memcopy-even` is the even one).  `--by-function`, on the
0.11 build:

- the even copy spent most of its time in the C library's `memcpy`.
  `copy_rows` (`src/vdi/dev_vbxe.c`) took 23 bytes at a time through
  two buffers on the stack: the window into one, a `memcpy` into the
  other, a `memcpy` out to the program's memory;
- the odd copy added a loop that moved one pixel at a time.

The slow bus was a small part of either.

## The copy

`rows_direct` (`src/vdi/dev_vbxe.c`) takes any copy between VRAM and a
program's bank $00 memory, at either parity:

- **The same parity.**  Each row's whole bytes move in one call,
  straight between the window and the program's bytes: `vram_write`,
  or `vram_read` (new, `src/vbxe/vbxe.c`).  `vram_read` is the same
  word loop as `vram_write`, with its pointers in the direct page.
- **A pixel out of step.**  Each destination byte is the low nibble of
  one source byte and the high nibble of the next.  `nib_shift`
  (`src/vdi/nibs.s`) does a byte with a word load, an `XBA` and four
  shifts:
  - into memory, the row's source bytes are read into the destination
    and shifted down in place.  The byte after the row, which the read
    borrowed, is put back;
  - out of memory, they are shifted through a 32-byte buffer on the
    stack.
- **The half bytes at either end** are one read, merge and write each,
  per row (`edge_px`).

In both cases one source byte past the rectangle's last pixel is read,
and never written.

Far memory, and a copy within one form, still go through `copy_rows`.
Its own pixel loop for ends out of step now calls `nib_shift`, and its
VRAM reads use `vram_read`.

## Bold

Bold was the glyph drawn twice, the second time one pixel to the right.
On the VBXE each pass is an AND blit and an OR blit, so a bold letter
cost four blits where a plain one costs two.

The union of the two passes is a mask of its own: each font row `b`
becomes the nine pixels `(b << 1) | b`.  So one AND/OR pair draws it,
and the pixels are the same:

- ORing two masks in, one after the other, is ORing in their union;
- the AND before each OR clears the same pixels either way.

**The seam.**  `dev_glyph`'s `overlay` gains `GLYPH_THICK`
(`src/vdi/vdidev.h`): the letter and its second pass in one call.
`draw_char` (`src/vdi/vdi.c`) asks for it wherever it made the two
calls before.

**The VBXE.**  The device keeps two more strips at `VR_FONT_BOLD`
(`src/vbxe/vbxe.h`), one per parity of x, each five bytes a glyph row.
It draws the letter from those when all nine columns are inside the
screen and the clip, and as the two passes when they are not.

The strips are not expanded by the CPU, which took a quarter of a
second through the window.  The blitter builds them out of the two
strips the font already has:

- the odd strip is every glyph one pixel right of its cell;
- so the even thickened strip is the odd one with the even one ORed
  over it, and the odd thickened strip is the same with the even one a
  byte further on;
- byte k of every glyph is a column of a strip, 256 bytes at X steps
  of 4 and 5 (`blit_xstep`, new);
- that is eighteen blits, the first time bold is drawn after the face
  changes.

**ANTIC.**  ANTIC draws a string's visible cells as one run, a row at a
time (`antic_text`, phase 54), but never thickened, so bold went a
glyph at a time. `antic_text` now takes `thick`. Each packed row is
ORed with itself one pixel to the right, with the bit that falls off
each byte carried into the next, and the run is one column wider.
`v_gtext` hands it a thickened run only:

- in transparent mode, where the order of the passes cannot matter;
- when the column after the run's last cell is visible.

A lone bold glyph is a run of one.

## Figures

G4BENCH, ms a call, against the 0.11 reference:

| | VBXE before | VBXE after | ANTIC before | ANTIC after |
|---|---|---|---|---|
| text, 40 characters | 16.4 | 16.5 | 8.8 | 8.6 |
| text, bold and underlined | 31.0 | 18.0 | 33.6 | 10.3 |
| blit screen to memory, back | 113.4 | 25.0 | 22.7 | 22.7 |

Nothing else moved by more than 2%.  `bench_vdi.py`'s new cases on the
VBXE, ms an op:

- `memcopy-even`: 47.5 before, 12.5 after;
- `memcopy` (odd x, as G4BENCH's): 26.2 after;
- `text-boldonly`: 31.2 before, 16.2 after, the same as `text`;
- `text-bold` the first time, the strips built: 17.5.

## Proof

- **`make test-m3`**, all three widths, adds a case for thickened text.
  It covers transparent mode at odd x, white ink over a fill, a clip
  that cuts letters at both ends, and the right edge of the narrowest
  screen.  Building the odd strip one byte short turns it red (542
  pixels).  No case before it put bold text at an odd x.
  - The memory-form cases (phase 75) already copy at every pairing of
    parities, and check the memory's bytes as well as the screen.
- **Replace mode, against the device before this phase.**  A scratch
  case drew thickened text in replace mode at odd and even x, in white
  ink, clipped and at the edge.  The screens before and after this
  phase are identical, pixel for pixel.  It is not a gate, because the
  model disagrees with both (below).
- **`tests/host/test_text.py`** holds `antic_text` to the glyphs it
  stands for. It adds 48 thickened runs, at every alignment and both
  pens, each against every cell drawn and then drawn again one pixel to
  the right. Leaving out the carry between bytes fails 37 of them.

## Found, not fixed

`tools/vdiref.py`'s `_draw_char` draws the thickening pass in the
string's writing mode.  In replace mode that repaints the cell's
background under the first pass and rubs part of it out.  Every device
draws that pass so that it adds ink:

- ANTIC and the printer say so;
- the VBXE has always drawn it as an AND/OR pair.

So no gate draws bold in replace mode yet. The model wants changing to
match.
