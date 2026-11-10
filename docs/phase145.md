# Phase 145 -- text on the VBXE a run at a time (VDI step 2)

The first speed-up of step 2 of [vdi-plan.md](vdi-plan.md): a string's
visible run is drawn on the VBXE as one raster, not as a blit per
character.

| `v_gtext`, 40 characters | before | after | |
|---|---|---|---|
| even x | 14.4 ms | **6.4 ms** | -55% |
| odd x | 15.2 ms | **9.0 ms** | -41% |

(`python3 tests/emu/bench_gem.py text`, the emulated Rapidus at 11x.
docs/bench.md's September figures, 19.0 and 19.3 ms, were already stale;
step 4 brings that page up to date.)

## Where the time was

Profiled first (`bench_gem.py --profile text`).  A string of 40 cost
58,000 instructions, and the glyphs' pixels were hardly any of it.  Each
character was a blit, and each blit a control block written into VRAM
through the MEMAC window: `vram_write` alone was a third of the time,
with `bcb_common`, `vbd_glyph`, `scr_row` and `blit_mask` after it.

## One raster for the run

The VBXE device now has a `text_run`, the entry ANTIC has had since
phase 54.  It lays the run's glyph rows side by side in a one-plane
buffer, a byte a cell since the face is eight pixels wide, and hands
the buffer to `raster_1bpp`.  That expands it into VRAM's strip and
puts it on the screen with one blit, or two.  The pixels are the ones
`dev_glyph` drew a cell at a time, mode for mode:

- replace: set bits the ink, clear bits pen 0;
- transparent: set bits the ink;
- XOR: set bits inverted;
- erase: clear bits the ink.

Thickened text, which `v_gtext` hands to a run in transparent mode only,
ORs each row with itself one pixel right.  The spill carries into the
next cell and one column past the last.

The buffer is 85 cells by the face's height, far, and the system's
([phase 144](phase144.md)).  It is taken at `v_opnwk`, which calls the
device's `invalidate`, so it is taken at boot.  The first version took
it at the first string, and `test-m12` failed: a block appeared during
a program and outlived it, and the allocators after the program's free
were not what they had been before.  Its address is in the direct page,
which has room where LoRAM has two bytes.  A run longer than the
buffer, or no buffer at all, goes a cell at a time as before.

## The buffer in assembler

Built in C, the buffer was the biggest single cost: Calypsi gave some
thirty-five instructions and a call for each byte.  `text_row` in
`src/vdi/nibs.s` copies one row of the run in twelve: a character from
`intin`, a long indexed load from the face's row, a long store into the
buffer.  It is in `nibs.s` because every build with the VBXE device
already links that file.  The face's row is read through a 24-bit
address, which is only safe while the row's 256 bytes are in one bank.
The built-in faces are (font8x8 is at $017C2E), and so is a loaded one,
whose strip comes from `far_alloc`.  A row that were not, and a
thickened row, go through the C loop at full addresses.

## What is left

At odd x `raster_1bpp` itself is now the largest cost.  Its edge and
remainder bytes read the source a bit at a time through a far pointer
(`SRC_BIT`), at 17,500 instructions a run against 5,000 at even x.  That
is the next speed-up, and it would help icons as much as text.

## Gate

`test-m3`'s text cases now go through the run, and one case is new:
thickened text in transparent mode built from glyphs with ink in their
last column -- `*` and some above 127 -- at even and odd x.  A word of
letters never reaches the carry into the next cell.  360 cases.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| `text_row` reading the glyph of the next lower even code | eleven text cases |
| the thickening's carry into the next cell dropped | the new case, 21 pixels; case 43, of letters, passes with it -- which is why the case was added |
