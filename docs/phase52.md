# Phase 52 -- the ANTIC screen, measured, and a compiler bug already in the product

Several people reported that gem4xe on the ANTIC screen -- the 320x168
fallback for a machine without a VBXE -- is pretty slow.  This is the
first round of the 0.8.x line, which after 0.8 is optimisation and
stability only; features wait for 0.9.

## Measured first

`tests/emu/bench_desk.py` (`make bench-desk`) boots the product on a
machine with a VBXE and on one without, drives the real desktop, and
times each action from the end of its input to the desktop's last call:

| | VBXE | ANTIC before | ANTIC after |
|---|---|---|---|
| open DISK A | 360 ms | 600 ms | **400 ms** |
| full the window | 360 ms | 600 ms | **480 ms** |
| unfull -- the desk redraws | 400 ms | 720 ms | **480 ms** |

Repeatable to the frame.  With `--profile` it also says where the time
went, and it takes the **idle loop** off first: a stretch with nothing to
do is profiled, and its cycles per frame, function by function, come off
every row.  Without that, half of every profile was the idle loop's own
16-bit divide and multiply, and read as the problem.

## The screen is not fast, and nothing had said so

`src/antic/antic.c` described its framebuffer as "plain motherboard RAM
the accelerator reaches at full speed".  It is at `$8100-$9B3F`, in the
Rapidus's window 2, which `rapidus_speedup()` keeps on the 1.79 MHz bus
**always** -- the VBXE's MEMAC window lives there on the other device.
So every screen byte read or written on this device is a slow-bus cycle.
The rule that follows is the one everything below obeys: **touch each
screen byte once, work out what goes in it in fast memory first, and do
not read a byte a write is about to cover.**

## What was slow, and what it is now

- **Icons went pixel by pixel.**  `vrt_cpyfm` -- every icon on the desk --
  called `antic_plot` for each pixel: a call, four bounds tests, a row
  multiply, and a read and a write on the slow bus.  A 32x32 icon was
  1,024 of those.  `antic_raster_row` now clips the row once, shifts the
  source into the screen's alignment, and touches each screen byte once --
  about 160 for the same icon -- and only WRITES a byte a replace covers
  whole.  That alone was 13-22%.
- **Moving a window went pixel by pixel.**  A window snaps to even x, and
  on a 1-bit screen that is usually not a byte boundary, so `antic_copy`
  took its per-pixel path -- a get and a plot for every pixel of the
  window.  Each source row is now read once into a buffer and put down
  through the raster path; reading the row before writing any of it is
  also what keeps an overlapping move on the same row safe.  A move now
  finishes 120 ms after the release.  (The committed version could not
  be timed the same way: in the input time the bench allows, its drag
  never registered at all.)
- **The pointer went pixel by pixel**: up to 256 plots every time the
  mouse moved.  It is three bytes a row now.
- **A vertical line called the whole patterned-span routine per pixel.**
  One read-modify-write a row now.
- **Every byte went through a `switch` on the writing mode.**  Each of the
  four modes is "what a set source bit does, and what a clear one does",
  and each of those is one of *paint 0, paint 1, leave, invert* -- all of
  which are `(d & X) ^ Y`.  So a mode is four bytes worked out once per
  call, a byte is one branch-free expression, and when both X are zero
  the destination is not read at all.  And it is a macro: as a function,
  the per-byte call was a third of a window redraw's work.

`tests/host/raster_sim.c` puts the new raster through every destination
alignment, every source alignment and every mode, in the compiler's own
simulator at `-O2`, against the same rows worked out one pixel at a time
-- and was seen red first, 84 rows of 260, with an edge mask broken on
purpose.  `test-m24`, `test-m25` and `test-m26` compare the primitives
and the whole desktop with their models, pixel for pixel.

## B21, found twice

The rewritten `antic_copy` made `test-m24` fail as a program that never
started drawing.  Run in the compiler's simulator, it stopped on a BRK at
`buf[k] = v;`.  cc65816 5.18.2 at `-O2` had outlined `sep #32 / ldy ##0 /
rtl`, called it on the one path through the loop that reads the screen,
and let that path fall into the join with the accumulator still 8 bits
wide, where `adc ##33` -- `69 21 00` -- ran as `adc #$21` and then BRK.
Reduced to thirty lines, `tools/ccbug/b21.c` stops at the same line.

The tree's scanner for this family, `mscan.py`, reported nothing, and the
reason is worth writing down: it asked only whether a named function is
CALLED narrow, it trusted a `?L` fragment to know what mode it left, and
it took `ldy ##0` as proof the accumulator was 16-bit -- but `ldy`'s width
is the X flag's.  `mscan.joins()` is a second check: the set of widths
that can reach each instruction, fragments followed to see what they
return in, and every accumulator immediate whose encoding one of those
widths contradicts.  It fires once on the buggy loop and never on the
fixed one.

**Pointed at the product, it found another.**  `make mscan` now rebuilds
with `CC_ASM=1`, so `tools/ccdep.sh` keeps the compiler's assembly for
every object, compiled with the flags and defines it really has -- the
VDI is compiled three times from one source with different prefixes, and
a scan that compiles each file once never sees the ANTIC instance.  The
first run found `src/sys/dos.c`'s `sdx_lookup`, shipping since phase 30:
two `sdx_asked = 1` stores merged into a tail assembled for 8 bits and
reached in 16 on the path where SpartaDOS X is usable.  The CPU ran the
variable's address, `D3 23`, as `cmp ($23,s),y` -- harmless, by the luck
of where the linker put it -- and the store never happened, so every DOS
command repeated both symbol lookups.  **No gate could have seen that.**
The build is clean now, `make mscan` is in `make test`, and `check-cc`
tracks B21 as the twenty-fourth shape.

## Prior art, and what may be taken from it

The request was to look at SymbOS, GEOS and GS/OS for ideas.  In short:

- **Keep a copy of the screen in fast RAM, read from it, write to both.**
  GEOS does it (`GetScanLine` returns the screen and a background buffer;
  its font code merges against the buffer); QuickDraw II on the IIgs --
  the same situation as ours, a fast 65816 in front of slow video memory
  -- shadows the screen into bank `$01`, and Apple's Toolbox Reference
  measures 8-20% on every operation.  **Not done yet, and not obviously a
  win here**: a slow read costs about 16 fast cycles on this machine, and
  a far read through this compiler can cost as much.  It wants measuring
  as its own step.
- **Special-case the common text.**  QuickDraw II's FASTFONT -- plain,
  black on white, rectangle-clipped -- "reduces text drawing time by more
  than half"; EmuTOS's `direct_screen_blit()` draws a whole string at
  once when it is byte-aligned and 8 pixels wide.  Text is now the
  largest single cost on ANTIC, so this is the next candidate.
- **Redraw exposed areas rather than saving under windows, and skip the
  overlap tests for the top window.**  SymbOS does both; flashjazzcat
  measured about 2x switching his GUI from regions to dirty rectangles.
  gem4xe already works this way.
- **Group operations by pattern and set up once** (QuickDraw II's "fast
  port"): relevant to the VBXE's blitter set-up, below.

Licences: SymbOS's kernel source is not published; its developer docs
are GPL-3.0 and may be read.  GEOS's reconstructed source is Berkeley
Softworks/GeoWorks copyright -- **read for ideas, never copied**.  Apple's
technical notes are Apple's -- ideas and documented behaviour only.
EmuTOS is GPL-2.0-or-later, so its code could be used with attribution.

## What is next

- **VBXE.**  Its 360 ms window open is not the blitter: `vram_write`
  (control blocks through the slow MEMAC window, 12%), a 32-bit multiply
  per blit (`_Mul32`, 8% -- almost certainly `y * stride` for a VRAM
  address) and control-block assembly (5%).
- **ANTIC text**: a byte-aligned fast path, and whole strings rather than
  a call per glyph.
- **The shadow**, measured as its own step.
