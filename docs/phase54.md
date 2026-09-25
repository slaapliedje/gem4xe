# Phase 54 -- ANTIC text, a string at a time

Third round of the 0.8.x line (optimisation and stability only).  Phase 52
named text as the next candidate on the ANTIC screen; this is it.

## Measured on its own

The desktop tour (`make bench-desk`) cannot measure text: its disk holds
five files, and the desk's text is a handful of icon labels -- under 2% of
an ANTIC redraw.  So text has its own bench now, `make bench-antic`
(`src/bench_antic.c`, `tests/emu/bench_antic.py`): the product's VDI on
`vdev_antic`, drawing a screen of text -- 26 lines of 53 characters, every
cell the 6x6 face has -- as many times as the host asks, while the host
counts frames.  `ARGS=--profile` adds where the time went.

| a screen of text, 1,378 characters | before | after |
|---|---|---|
| replace, x = 0 | 510 ms | **230 ms** |
| transparent, x = 0 | 505 ms | **245 ms** |
| replace, x = 3 | 555 ms | **230 ms** |
| (`vr_recfl` 300x150, for scale) | 60 ms | 60 ms |

A line of 53 characters is about 9 ms now, at any alignment.  Phase 53 measured a line of
40 on the VBXE screen at 17.6 ms, so text on ANTIC is no longer the slow
side.  The desktop tour does not move (360 / 440 / 440 ms), because it
draws almost no text.

**The first version of the bench measured nothing useful**: its runner
never called `rapidus_speedup()`, so bank `$00` stayed on the 1.79 MHz
bus and every number was four times too large -- 2.2 seconds a screen.
The runner reports the MCR it ended up with now, and the host refuses a
machine still at `$FF`.  Every runner that times anything has to make the
same call the product does.

## What was slow

`antic_glyph` drew one cell: an op worked out, two edge masks, and for
each of six rows a font address computed from the row, a far read, and one
or two screen bytes.  That was 370 microseconds a character with the
screen bytes a few percent of it -- the rest was set-up paid 53 times a
line, variable shifts that this CPU does as loops, and the compiler's
outlined fragments called with `jsl` from inside the row loop.

## What it is now

`v_gtext` already worked out, for VBXE's background prefill, the run of
cells wholly inside the screen and the clip.  It now hands that run to the
device in one call when the device has a `text_run` (the new last field of
`VDIDEV`; NULL for any device whose initialiser stops short of it, so VBXE
and the printer did not change).  ANTIC's `antic_text`:

- works out the op and both edge masks **once a string**;
- packs each row of the whole run into a buffer in fast RAM **already
  shifted to the screen's alignment** -- the first byte carries `x & 7`
  pixels of nothing, which the left mask keeps off the screen -- so buffer
  byte k is screen byte k;
- and puts each screen byte down once through the same `AN_PUT` as
  everything else, so the whole bytes of a replace are written without
  being read.

The row buffer is on the stack, as `antic_copy`'s is: as a static it
took LoRAM to 254 bytes free, under the 256 `tests/host/test_memory.py`
holds bank `$00` to.  Stack-relative indexing costs about 10 ms a screen
against the static (220 ms), and bank `$00` has nothing to spare.

The system face is 6 wide and has a packer of its own, because a shift by
the constant 6 is a few instructions and a shift by `w` is a loop.  The
first version went through `antic_raster_row`, which is general in its
source alignment and so called `an_src8` for every byte; that version got
only to 360 ms.

Thickened text keeps the per-glyph path: its second pass spills a column
into the next cell.  So do cells outside the visible run, which the device
drops whole as it always did.

`v_gtext` also stopped multiplying: `x + i * FONT_W` read the device's
width through the far pointer and called `_Mul16` for every cell,
including the ones the run had already drawn.

## Checked

`tests/host/text_sim.c` (`test_text.py`) draws 192 runs both ways in the
compiler's simulator at the product's flags -- every writing mode, both
pens, every alignment of the first pixel, widths 6, 8 and 5, one cell to
a whole row, over random screen bytes and a font whose unused columns are
random too -- and requires the same bytes, with the rows and bytes either
side untouched.  It was made to fail twice: a wrong replace background
(48 of 192 runs) and the alignment forced to zero (168 of 192).
`test-m24`, `test-m25` and `test-m26` hold the ANTIC VDI and desktop to
their models pixel for pixel, and `test-m3`'s 261 cases hold the VBXE side,
since `v_gtext` is shared.

## B22

The packer met a new compiler defect: a `__far` table indexed by a
`(uint8_t)` cast of an array element, inside a loop, is `internal error:
anyIndOffset (1,s),y` at every `-O` level.  It looked at first like
register pressure -- the function crashed with both packing loops in it
and compiled with either -- and was not: one loop alone, in a function of
its own, crashed.  `& 0xFF` compiles, and is what the source says.
`tools/ccbug/b22.c` reproduces it and `check-cc` tracks it with B6 and
B11 (`tools/ccbug/README.md`).

## And a gate that read the wrong program

`test-m36` failed during the suite, on the committed tree as well:
"with no saved file the rate is 46080".  Its control boot is
`gem-shots.atr`, read through `build/gem.sym` -- and the gate depended
only on its own disk, so a control disk built from an older `gem.xex`
was read at the current build's addresses.  `$B400` was some other
program's byte.  It depends on both now, and passes.

## What is left

The packer is most of what remains -- about 75% of a text screen -- and
the variable shift that takes each finished byte out of the accumulator
is a loop.  A hand-written packer would take it a long way further; it
was not done here because the C now beats the VBXE screen at the same job.
On the desk itself the remaining cost is per-call `an_op` and one
`antic_span` a row for every rectangle.
