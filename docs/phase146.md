# Phase 146 -- ANTIC's text in assembler (VDI step 2)

The second speed-up of step 2 of [vdi-plan.md](vdi-plan.md): the two
routines a text screen on ANTIC spends its time in, in assembler, and a
shorter shift in the VBXE's raster expander.

| ANTIC, `make bench-antic` | before | after | |
|---|---|---|---|
| a text screen, replace (26 lines of 53) | 217.5 ms | **121.2 ms** | -44% |
| the same, transparent | 228.8 ms | **152.5 ms** | -33% |
| the same, replace at x = 3 | 217.5 ms | **120.0 ms** | -45% |

| G4BENCH on ANTIC | phase 144 | now | |
|---|---|---|---|
| text, 40 characters | 8.61 ms | **6.23 ms** | -28% |
| text, bold and underlined | 10.26 ms | **8.13 ms** | -21% |
| text, four heights | 8.98 ms | **6.60 ms** | -26% |
| draw a dialog | 32.52 ms | **31.29 ms** | -4% |
| open and close a window | 75.07 ms | **72.88 ms** | -3% |

The VBXE's figures after phase 145, from the same G4BENCH run against
phase 144's build:

| G4BENCH on the VBXE | phase 144 | now | |
|---|---|---|---|
| text, 40 characters | 16.45 ms | **10.09 ms** | -39% |
| text, bold and underlined | 18.02 ms | **13.99 ms** | -22% |
| text, four heights | 16.80 ms | **10.44 ms** | -38% |
| draw a dialog | 26.15 ms | **25.35 ms** | -3% |
| open and close a window | 63.93 ms | **60.80 ms** | -5% |

Icons, blits and the rest are unchanged on both screens.

## Where ANTIC's time was

`make bench-antic --profile` had a text screen's time in two routines of
`src/antic/antic.c`.  `an_pack6`, which packs a row of the run into a
buffer six bits a cell, had half of it.  `antic_text`, which puts the
buffer on the screen, had 30%.

## an_pack6

The C version shifted an accumulator right by the number of bits
pending, once for every byte it put out, and on the 65816 a shift by a
variable is a loop.  `an_pack6_s`, in the new `src/antic/anpack.s`, has
no variable shift at all.  Each glyph's six pixels go into the byte
being built one at a time, a shift, a rotate and a count each, and the
byte is stored when it is full.  The six are written out, not looped.

## The row onto the screen

`antic_text` put each byte through `AN_PUT`, the op's mix done in C:
about ten microseconds a byte, where the write itself is one access on
the 1.79 MHz bus.  `an_put_row_s` does the first and the last byte, with
their masks, through the same mix.  For a middle byte of an op that does
not read the screen (replace), the mix reduces to load, AND, EOR and
store.

`src/antic/anpack.s` is a new file, linked wherever `antic.o` is (the
M24, M25 and M3 object lists, and the product's two GEM.COMs, which come
from M3's).  The three host tests that compile `antic.c` for the
simulator assemble it too.  `tests/host/test_text.py`, which holds every
run to its glyphs drawn one at a time (four modes, plain and thickened,
every lead), is the check that the assembler draws the same pixels.

## The VBXE expander's shorter shift

`raster_1bpp` takes a byte from two source bytes that straddle the
strip's boundary by shifting right by `8 - sh`, a bit a turn.  The same
eight bits are the high byte of a left shift by `sh`.  The expander now
takes whichever is shorter: at an odd x that is one turn, not seven, and
four at the most.  A string at odd x went from 9.0 to 8.7 ms.  Most of
what is left there is the blitter's second pass, which a replace with a
partly covered first byte needs (the AND row, then the OR).

## Room

The DOS 2 floppy has 16 sectors free after this, against a floor of 6,
and the gate-only ANTIC floppy 15.

## Gate

`tests/host/test_text.py` and `test-m25`/`test-m24` on ANTIC, and the
suite.  Each part of the assembler was seen to fail first:

| broken on purpose | `test_text` |
|---|---|
| `an_pack6_s` dropping each glyph's sixth pixel | 226 of 240 runs differ |
| `an_put_row_s`'s fast path dropping a bit | runs differ |
| `an_put_row_s`'s mask ignored at the edges | runs differ |
