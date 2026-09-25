# Phase 53 -- the VBXE side: the blitter was never the slow part

Second round of the 0.8.x line (optimisation and stability only).  Phase
52 measured the ANTIC screen; this is the VBXE one, with the same bench,
`make bench-desk`:

| | VBXE before | VBXE after | ANTIC after |
|---|---|---|---|
| open DISK A | 360 ms | **280 ms** | 360 ms |
| full the window | 360 ms | **320 ms** | 440 ms |
| unfull -- the desk redraws | 400 ms | **320 ms** | 440 ms |

and, from GEMBench's rows (`tests/emu/bench_gem.py "VDI text"`), a line of
replace-mode text:

| 40 characters | before | after |
|---|---|---|
| even x | 19.9 ms | **17.6 ms** |
| odd x | 43.8 ms | **18.5 ms** |

## First, the profile was lying

`bench_desk.py --profile` names each hot address after the far function
at that offset in each bank, because Altirra's profiler reports the
address WITHOUT its bank.  It never offered bank `$00` -- and bank `$00`
is where the OS ROM is.  So a window opening spent a tenth of its time in
"`draw_arrow|sh_ldauto`", neither of which runs then: `$E5A4-$E5BF` is the
OS's SIO, reading the directory off the floppy.  The bench now names the
OS ROM and the near code as candidates too, so the ambiguity is on the
page instead of hidden in it.  "Open a window" includes a disk read on any
DOS; "full" and "unfull" are the honest drawing numbers.

(The profiler's `callgraph` mode was tried as a way to get banks and call
counts: it puts 83% of everything under the interrupt entry.  It follows
the 6502's JSR and not the 65816's `jsl`/`rtl`.)

## What it was

**A run of the blitter per glyph, and per rectangle.**  `dev_glyph` ended
with `blit_run()`, and so did every solid rectangle through `paint_rect`,
every styled line and every band of a pattern: upload the list, start the
blitter, wait on its busy bit over the slow bus.  A directory window was
hundreds of runs.  Now one rule, in `src/vbxe/vbxe.c`, where no caller can
forget it:

- blits queued are run **before any CPU access to VRAM** -- every one comes
  through `vram_map_page()`, which drains the queue first;
- a **full queue is run**, not refused -- `bcb_new` used to return 0, and
  every caller then silently DROPPED its blit, which was safe only while
  every primitive flushed at its end;
- and `vdi()` flushes **once, after each call**.

Program order is kept exactly, so nothing above the seam can tell -- which
test-m3's 261 cases and the rest of the VBXE gates confirm pixel for
pixel.  A call's blits now go as one list.

**A 32-bit multiply per primitive.**  `(uint32_t)y * SCR_STRIDE` opened
nearly every primitive, and because the stride is the device's, read at
run time, the compiler made it a `_Mul32` -- and folded the thirteen
sites into shared fragments, which is why they were hard to see.  All
three overlay strides (256, 320, 336) are multiples of 16, so `scr_row()`
computes `y * (stride / 16)` in a word with a few shifts and adds and
shifts it back; the build refuses a stride that is not.  An off-screen
form's row is `form_row()`, shifts and adds over the bits of y.  About a
tenth of a redraw.

**A replace-mode string painted each cell's background separately.**  At
an odd x a cell covers half a byte at each end, so its background was five
blits before its glyph.  `v_gtext` now paints the background of the run of
cells the blitter will draw ONCE, and draws each glyph over it -- when the
device says it wants that (`text_prefill`, the last field of `VDIDEV`, so
the devices that do not simply leave it zero; ANTIC touches each byte once
anyway and would only do more).  Not for thickened text: the second pass
spills a column into the next cell and it is the next cell's own
background that erases it.  The desktop draws in transparent mode, so the
desk tour does not move; replace-mode text -- editors, text views -- is
2.4 times faster at an odd x.  test-m3 gained a case for exactly this:
replace mode, an odd x, and a clip cutting cells off both ends -- seen red
first, with the background one pixel short.

**`style_anchor`** anchored a dash pattern with sixteen trips round a loop
and two variable shifts in each, which are loops themselves on this CPU.
It is a rotation now (`tests/host/test_style.py` holds it to the old
loop).  An honest note: solid lines never reach it -- they are
rectangles -- so it was not on the path the profile blamed it for; that
row was the OS ROM.  It is cheaper for dotted lines and that is all.

## What did not work, and why that is worth knowing

The control-block upload is now the largest single cost: 21 bytes a blit
through the MEMAC window, on the 1.79 MHz bus.  The obvious idea was to
upload only the bytes that changed since the last list -- consecutive
lists share strides, steps, masks and modes, and `bcb[]` could be its own
mirror of VRAM with a dirty bit per byte.

**It made a redraw nearly twice as slow**: 280 ms to 520.  A byte on the
slow bus costs about sixteen fast cycles, and the bookkeeping to skip one
-- a compare, a dirty bit, a variable shift that is a loop -- costs more
than the byte.  `vram_write`'s word loop, its pointers in the direct page,
is already about as fast as the bus allows.  It was taken out, and the
reason is written beside the upload so nobody tries it again without
cheaper bookkeeping.  The general rule for this machine: **saving a
slow-bus access only pays if the saving costs less than the access.**

## What is left

The per-blit upload, which only fewer blits can reduce: a partial nibble
at a rectangle's edge is two blits (AND, then OR) where mode 6 would be one
if it could write colour 0, which it cannot.  And on ANTIC, text: a fast
path for byte-aligned plain text, and the screen shadow phase 52 did not
try.
