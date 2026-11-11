# Phase 149 -- the face at twice its size (VDI step 3)

The second item of step 3 of [vdi-plan.md](vdi-plan.md): a second text
size.  The VDI had one size of one face, so `vst_height` and `vst_point`
could only answer with it.

| | was | now |
|---|---|---|
| text sizes | the face as it is (8x8 on the VBXE, 6x6 on ANTIC) | that, and the face at twice its size (16x16, 12x12) |
| `vst_height`, `vst_point` | the one size, whatever was asked | the largest size no bigger than asked, else the smallest |
| `vqt_attributes`, `vqt_extent`, `vqt_width`, `vqt_fontinfo` | the one size | the size in use |
| `work_out`'s character sizes | 8 x 8 on both screens | the smaller and the larger, widths and tops, as EmuTOS works them out; two heights |
| replace-mode thickened text in the model | the second pass painted the cell's background | it does not, as the driver's does not |

## Choosing a size

A workstation's text size is a new field, `t_scale`: 1, or 2 for the face
doubled.  `vst_height` picks the largest size whose height is no more
than the one asked for, and the smallest when none is, which is what the
ST's ROM and EmuTOS do with a font's sizes.  The height here is the
face's top, as `vst_height` has always reported it.  `vst_point` does
the same in points.  The AES asks for height 0 and so keeps the face as
it is: its layout does not move.

Every metric the text code uses -- the cell, the alignments, a string's
extent, a justified line's gaps -- goes through `TS()`, the metric at
the workstation's size.

## Drawing it

A glyph at twice the size is its rows doubled in width (a nibble's four
pixels to a byte, by a table) and in height: at most 16 x 16, 32 bytes
on the stack.  It goes to the screen through the device's
`raster_1bpp`, which applies the writing mode and clips.  Nothing in
either device changed.  The rules are the face's at its own size:
- in replace, set bits the ink and clear ones pen 0;
- in transparent, set bits the ink;
- in XOR, set bits inverted;
- in erase, clear bits the ink.

A thickened glyph's second pass, one pixel right, paints no background,
as `dev_glyph`'s does.  The underline is two rows at twice the size.

## A string as one raster

A glyph at a time through `raster_1bpp` was over two milliseconds each
on the VBXE, and G4BENCH's "four heights" went from 10.4 to 34 ms.  So a
string at twice the size is drawn as the face's own size draws one with
`text_run`: the visible cells' doubled rows side by side in one far
buffer, and one `raster_1bpp` for them all.  That is two bytes a cell of
the 8-wide face and three for two cells of the 6-wide.  It is used in
every mode, and thickened only in transparent mode, where the two passes
are an OR.  Otherwise it goes a glyph at a time.  The buffer is the
system's, taken at `v_opnwk`, its address in the direct page.

Two faults on the way, both mine:

- **B12.**  The run's stride was `(w + 7) >> 3` of a signed WORD, and
  Calypsi compiled it as the sign extension of a 3-bit field: -2 for 14,
  and the picture sheared two bytes a row.  `make mscan` said so, and I
  had run it with its output thrown away.  It is unsigned now.
- **m25 never reached the run.**  Its program opened the workstation
  before probing far memory, so there was no buffer and it went a glyph
  at a time.  It probes first now, as `src/gem.c` does, and a break of
  the run fails it.

## G4BENCH

"text, four heights" asks for heights 4, 6, 8 and 13 in turn.  Each used
to get the one size.  Now heights of twice the face's top get the
doubled face: on the VBXE one of the four (13), on ANTIC two (8 and 13),
each four times the area.  On the VBXE the test is within its reference
(15.8 ms against 16.7).  On ANTIC a doubled string costs what four times
the screen bytes cost, since writing ANTIC's screen is most of a
string's time there (6.2 ms for 40 characters at the face's size).  The
test went from 9.2 to 16.9 ms: different work, not a slower path.  That
one row of `tests/emu/g4bench_ref.json`, ANTIC's "text, four heights",
is re-measured.  Every other row is as it was.

## test-m32's first fit

`test-m32` failed after this phase:
- **What it checks:** after `Mxalloc`, `Mshrink` and `Mfree`, a 100-byte
  `Malloc` must reuse the freed block.
- **What happened:** the 100 bytes went to a 212-byte gap below it, the
  slack before a page-aligned block.
- **Why:** the size of that slack moves with every system block before
  it, and the workstation table grew 16 bytes (two a workstation).
- **What was still right:** the gate's heap model placed the 100 bytes
  in the same gap, so the allocator did what first fit says.
- **What was wrong:** the assertion assumed the layout; it had held by
  coincidence.

It now checks that the 100 bytes are not above the freed block, where
they would go if `Mfree` had not given it back.  The model still checks
the exact address.  In a layout with such a gap that check cannot see a
broken `Mfree`, but the gate's double free can: with `Mfree` made to
return 0 without freeing, the second `Mfree` answered 0, not -40.

## LoRAM

The new field is two bytes of the live workstation, which is in LoRAM,
and LoRAM was two bytes above its floor.  `vwk_cur` and `cur_drawn`
moved to the direct page, which had 75 free; the run buffer's address
took four more.  LoRAM has 260 free, the direct page 67.

## The model's thickening

`tools/vdiref.py` drew a thickened glyph's second pass in the writing
mode.  In replace that painted the cell's background again, one pixel
right, and erased the first pass's ink.  The driver's second pass paints
no background (`dev_glyph`'s overlay).  No case had thickened text in
replace mode, so the two disagreed without a gate saying so.  The new
case at the face's own size does.  With the model's old rule restored it
fails by 386 pixels.

## Gate

- **`test-m3`** gains two cases (423):
  - text at twice the size in all four modes, at an odd x, cut by the
    clip, and the size queries' answers;
  - thickened and underlined text at twice the size in transparent and
    replace; the size chosen by `vst_point` either side of the doubled
    face's points and by heights too big and too small; and replace mode
    thickened at the face's own size.
- **`test-m25`** draws a word at twice the size on ANTIC: 12x12.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| the doubled run drawing nothing | m3: 2,984 and 940 pixels; m25: 156 (once m25 reached it) |
| every second row of a glyph drawn alone (`glyph2`) left out | m3's thickened case: 549 pixels -- replace mode's thickened text goes a glyph at a time |
| `vst_height` never choosing twice the size | m3: its answer; m25: 149 pixels |
| the model's old thickening rule | m3: 386 pixels |
