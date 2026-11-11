# Phase 151 -- the two documents, measured again (VDI step 4)

The last step of [vdi-plan.md](vdi-plan.md): docs/differences.md and
docs/bench.md brought back to what the code does.  The plan is done.

| | was | now |
|---|---|---|
| differences.md | single-tasking; a module's header inside it; 71 VDI opcodes served; one blitter mode; no G4DOS | up to six programs put aside and switched; the header in front; 66 of 71 served and `v_escape` empty; the logic modes by the blitter; G4DOS's folders, bare names and `Dfree` |
| bench.md | September's tables; text effects and small text "n/a" | a fourth run; thickened, underlined and twice-size text timed |
| `make bench` | a row inherited what the rows before it left | each row starts from a reset, untimed |

## Rows that timed their neighbours

Measuring again found the bench measuring the wrong things.  A row set
only what it changed, and the AES's rows share the physical workstation
with the script:

- **The patterned fill.**  The dialog leaves transparent mode with fill
  colour 0.  A pen-0 transparent pattern is two passes on the VBXE, so
  the row took 2.05 ms where the replace-mode fill takes 1.11.  It looked
  like an 84% regression since phase 58; it was a different case.
- **The copies.**  The window leaves a clip, which cut the screen-to-
  screen copies and the icons short: 1.55 ms for an aligned 320x100 copy
  that takes 3.14 ms in full.
- **The XOR copy.**  The blitter skips a byte whose source is 0 in its
  combining modes, so the XOR's cost is what the source holds: 1.40 ms on
  a blank screen, 4.40 ms on a solid one, and anything between after the
  rows that drew there.

`tests/emu/bench_gem.py` now runs a reset before every row, untimed: replace
mode, colour 1, no clip, plain text at the face's own size.  A row that
needs something on the screen gets it laid down the same way: the
screen-to-screen copies copy a solid colour-1 rectangle.  Each row then
gives the same number alone, after any other group, or in the full run.

| broken on purpose | result |
|---|---|
| the reset without its `vs_clip` | the copies after the window row cut short again: 1.554 ms |
| no source laid down | the XOR copy 1.40 ms alone, 3.82 after the graphics rows |

## What two months did

Like for like with 10 September: the dialog 60.0 to 31.2 ms, the window
94.0 to 74.4, a 40-character line 19.0 to 6.42, a solid fill 0.79 to
0.497.  The memory rows did not move.  bench.md's fourth run has the
table, and which phases moved each row.

The new rows: thickened text 3.4 times a plain line, because in replace
mode it goes a cell at a time (its second pass spills into the next
cell); twice-size text 4.0 times, for four times the area.

## differences.md

Each row was checked against the code it names:

- **Multitasking**: phases 126-132.
- **Control panel modules**: phase 133.
- **The VDI's opcodes**: docs/api.md.
- **Raster copy**: phase 147.
- **Text effects**: `vdi_vst_effects`.
- **G4DOS's folders, bare names and `Psystem`**: phase 141 and
  docs/g4dos-plan.md.
- **`Dfree`'s count from the file system**: `gd_dfree_fs`.

`Psystem`'s note in the kit's gem.h now names G4DOS's commands too.

One thing the check found and did not change: Show info greys a
folder's name on every DOS, though G4DOS's file system renames and moves
folders.  `src/desk/deskfun.c` says "a DOS that can do it takes the flag
back", and no DOS does yet.
