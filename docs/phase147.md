# Phase 147 -- the logic modes by the blitter (VDI step 2 done)

The last item of step 2 of [vdi-plan.md](vdi-plan.md).
[Phase 142](phase142.md) made `vro_cpyfm`'s sixteen modes right on every
device and pair of forms, and left the VBXE doing them on the CPU a row
at a time.  That was correct, and measured here for the first time it
was far too slow to use.

| `bench_gem.py Blitting` | before | after |
|---|---|---|
| `vro_cpyfm` 320x100 screen to screen, aligned, XOR | 1,136 ms | **1.4 ms** |
| the same, a plain copy (unchanged) | 3.1 ms | 3.1 ms |

(Note, 11 November: the 1.4 ms was measured on a blank source.  The
blitter skips a byte whose source is 0 in its combining modes, so that
XOR wrote nothing.  On a solid source, where every byte is combined, it
is 4.4 ms (docs/bench.md, the fourth run).)

A program that drew a selection rectangle with XOR, or put a sprite
down with a mask and OR, would have taken a second for each.

## By the blitter, between VRAM forms

The VBXE blitter takes its source through an AND mask and an XOR mask,
then copies it, or ANDs, ORs or XORs it into the destination.  With the
masks at `$FF` or `$00` that is every logic mode but four in one pass.
The table `rop_code` in `src/vdi/dev_vbxe.c` gives each mode its masks
and its blitter mode:

| modes | how |
|---|---|
| 0, 15 (white, black) | a copy of `$00` or `$FF`: the source masked away |
| 1, 6, 7 | AND, XOR or OR of the source |
| 4, 9, 13 | the same of the inverted source (XOR mask `$FF`) |
| 10 (NOT D) | XOR of `$FF` |
| 12 (NOT S) | a copy of the inverted source |
| 8, 14 | OR or AND, then the destination inverted: a second pass |
| 2, 11 | the destination inverted, then AND or OR: a second pass first |

Modes 2 and 11 invert the destination before reading the source.  When
the two rectangles overlap, that pass would change the source, so they
then go by rows instead.  Modes 8 and 14 invert after the source has
been read, and go by the blitter either way.

This applies when source and destination are both VRAM forms (the
screen and the save buffer) at the same parity, since the blitter has
no shifter.  The odd column at either end goes through `copy_rows` a
pixel wide, in the order the plain copy uses for an overlapping move.
The middle is `blit_move_op`: `blit_move`, which already ran backwards
when the destination is the higher address, given the masks and the
mode.  `blit_move` itself is now `blit_move_op` with a copy's masks, the
same control block as before.

## On the CPU, a byte at a time

Everywhere else -- a memory form, or different parities -- the modes
still go by rows.  At the same parity, the row now combines whole bytes,
both pixels at once, since a mode is a function of each bit.  Only a
first pixel in a low nibble, or a last in a high one, is done alone.  It
was a nibble at a time before, about 700 cycles a pixel.

## Gate

`test-m3` gains seventeen cases (411 over the three widths).

- **Sixteen, one per mode, at the same parity.**  The source starts at
  an odd x and so does the destination, so both ends have an odd column
  and the middle goes to the blitter.  The pens are the complementary
  pairs of phase 142.
- **One with four copies:**
  - XOR over its own rectangle moved right and down by even amounts:
    the blitter backwards.
  - Mode 8 over itself, by the blitter.
  - Mode 11 over itself, which must go by rows.
  - A mode from the screen into a memory form at the same parity, and
    one back: the byte path.

  Phase 142's cases go across parities and still check the nibble path.

Each part was seen to fail first:

| broken on purpose | result |
|---|---|
| modes 2 and 4 given a wrong table entry | those two cases |
| the overlap guard removed | the overlap case (mode 11) |
| the byte path ignoring the destination | the two memory-form cases |
| `blit_move_op` running backwards as a plain copy | the overlap case |

The first version guarded all four two-pass modes, and its overlap case
used mode 8, which inverts after reading.  Removing the guard changed
nothing, and that showed the guard was too wide: only the
invert-before modes need it.

The DOS 2 floppy has 14 sectors free after this, against a floor of 6.
