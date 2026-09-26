# Phase 58 -- the VDI's per-call cost: the CPU was waiting on the blitter

Seventh round of the 0.8.x line (optimisation and stability only).  The
question was what a VDI call costs apart from its pixels -- which
matters for the small things: buttons, gadgets, menu items.  The first
answer to come from the profile was wrong twice, and the right one was
not in the VDI at all.

| GEMBench (`make bench`), VBXE | before | after |
|---|---|---|
| `vr_recfl` 100x50, solid | 0.788 ms | **0.522 ms** |
| `vr_recfl` 100x50, pattern 4 | 1.735 ms | **1.114 ms** |
| box 100x50 as a 5-point `v_pline` | 1.692 ms | **1.440 ms** |
| `form_dial` + `objc_draw` of 5 objects | 50.4 ms | **46.3 ms** |
| `wind_create`, open, close, delete | 84.0 ms | **75.8 ms** |

and the desktop (`make bench-desk`), VBXE: open DISK A, full and unfull
**280 / 320 / 320 ms to 240 / 280 / 280**.  ANTIC does not change -- it
has no blitter to wait for.

## What the profile said first, and why it was wrong

- On ANTIC, 200 small rectangles looked like a tenth VDI overhead, but a
  tenth of the bench was its own `i % 12` and `i / 12`.  Stepped instead
  of divided, the VDI's dispatch, clipping and far device call are a
  fifth, and the device's own work, per ROW, is most of the rest.
- On VBXE, `vdi_key_poll` was a sixth of every `vr_recfl`.  It is the
  benchmark RUNNER's idle loop, draining the keyboard between scripts;
  the profile covers the whole measured window, and the runner's own
  waiting is in it.  Not the VDI.

(The bank each profile row is in is known now -- `tools/altirra/`, PR #95
upstream -- so these are the only two kinds of misreading left, and both
were the bench's.)

## What it was

**A multiply per blit.**  `bcb_new` found the next control block at
`&bcb[bcb_count * BCB_SIZE]`, and 21 is not a shift: a call to the
run-time library's `_Mul16` for every blit queued, and another for every
block `blit_start` chained.  The queue keeps a pointer to its end now and
steps it by 21.

**The CPU waited on the blitter after every call.**  `vdi()` flushes once
per call (phase 53), and the flush was `blit_run()`: upload the list,
start it, then spin on `BLITTER_BUSY` until it finished -- a 100x50 fill
is about 2,500 blitter cycles, and every read of the busy bit is a trip
over the 1.79 MHz bus.  The flush now STARTS the list and returns; the
CPU gets on with the caller's next thing, often the next call's clipping
and set-up, while the blitter works.  The wait moved to the two places
that need the blitter finished:

- **before the next list is uploaded**, because it goes where the running
  one is being read from;
- **before any CPU access to VRAM**, in `vram_map_page()` -- the one road
  every CPU access already takes, which phase 53 made drain the queue.
  The pattern and cursor strips, the raster strip and the screen are all
  things a running list may read or write; the guards before each CPU
  write to them (`if (blit_pending()) blit_run();`) now also wait out a
  list that is running, through the map.

A flag says a list was started and nobody has seen it end, so the idle
case costs no bus read.  The busy bit is read as a word, not spun on as
a byte (compiler bug B16).

The m3 runner now waits for the last list before it stamps DONE -- DONE
means the screen is drawn, for its pixels and for GEMBench's timing,
which would otherwise have left each script's last list out.  With the
wait, the numbers moved by a percent.

## Checked

`test-m3`'s 261 cases and `test-m2` compare the VBXE screen with their
models pixel for pixel after every case, and the rest of the suite --
the desktop, the applications, the cartridge -- runs on the same driver.

## What is left

On ANTIC, the per-call cost is small against the per-row cost of the
device; `antic_vline` (window borders, a read and a write a row) is 12%
of opening a window there, and the next obvious thing.  On VBXE, each
blit's 21-byte upload over the slow bus remains, and the partial-nibble
edges that take two blits where one would do.
