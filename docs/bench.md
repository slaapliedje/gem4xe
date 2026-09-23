# The benchmark — GEMBench's tests, on this machine

Status: **running**, not a gate. `make bench` prints the table below in
about four minutes; `python3 tests/emu/bench_gem.py --profile dialog text`
adds Altirra's instruction profiler per row. The first two runs found the
two hottest functions in the AES and cut every drawing row by a third to
two fifths, and pinned a seventh compiler defect on the way.

Everything here is measured in Altirra — a Rapidus at 11×, VBXE FX 1.26,
PAL — and not on hardware. The emulator's bus model is the emulator's;
where a number below says more about Altirra than about the boards, it
says so.

## What it is, and what it is not

GEMBench (Exxos) times a GEM dialog box, VDI text (plain, with effects,
small), VDI graphics, a GEM window, integer division, float maths, RAM
and ROM access and blitting, and prints each as a percentage of a stock
ST. Its source is not public and no ST is measured here, so the numbers
cannot be relative: `tests/emu/bench_gem.py` keeps GEMBench's headings
and reports **milliseconds per unit of work and units per second**. Two
of the headings do not apply — `vst_effects` is a no-op in this driver,
as in DRI's own, and there is one font — and are printed as such rather
than dropped.

The VDI and AES rows are the harness's own scripts (`tests/emu/m3..m8`)
run for time instead of for pixels: the same `objc_draw` of the same
five-object dialog that `make test-m4` compares against `tools/aesref.py`,
the same window that `make test-m8` opens with every gadget. The CPU and
memory rows are ops in the runner (`src/m3_vdi.c`, `bench_op`, opcodes
`2000+n`): two divides, a float expression, and read/write/copy loops over
256 bytes through a far pointer whatever the space, so the rows differ
only in the bus behind them.

## Timing

A frame is too coarse — the smallest rows take a fifth of one — and a
watchpoint is too fine: a halt inside a bridge `FRAME` leaves the gate
closed and the session wedged. So the clock is the VCOUNT tick, two
scanlines, 0.13 ms:

- the runner stamps `VCOUNT` into `STATUS[5]` when it sees `GO` and into
  `STATUS[6]` just before it sets `DONE`, and reports how many values a
  frame has in `STATUS[7]` (156 on PAL — measured, not assumed);
- the host reads the emulator's cycle counter at the frame boundary
  before `GO` and at the one where `DONE` is seen, and takes the idle
  tail between `DONE` and that boundary off using the two stamps;
- an empty script costs 203 cycles (125 µs) and comes off every row.

One correction that cost a run to find: the cycle counter Altirra exposes
leaves out the cycles ANTIC halts the CPU for — 32,520 a PAL frame on
2 September, not 35,568 — so converting cycles to milliseconds through
the clock rate under-reports. Cycles become milliseconds through the
frame instead: a frame is `period` ticks of two 114-cycle lines at the
machine clock, 20.06 ms, and `ms = cycles / cycles_per_frame × frame_ms`.
The bench prints the figure it measured as its `clock:` line, and how
much that figure moved between runs turned out to be the third run's
whole story (below): 32,520 was not a text screen's number.

Each row is repeated until its measured total reaches 300 ms or 40
runs, so the tick's resolution does not show in the ms column.

## The first run

The memory rows came out identical everywhere — 1,952 cycles per 256
bytes in fast SRAM, in SDRAM, in the OS ROM — which meant the loop, not
the bus, was being measured: a byte loop with stack locals is 24
instructions a byte on this compiler. The loops now move words, counting
down, with the counter and the sum in the direct page (`do ... while
(--n)`, unsigned: a signed compare costs six instructions), and the bus
shows. That is the baseline:

| Row | ms | rate | cycles/unit |
|---|---:|---:|---:|
| form_dial START, objc_draw of 5 objects, form_dial FINISH | 77.7 | 12.9 /s | 126,034 |
| objc_draw of the dialog alone | 66.9 | 15.0 /s | 108,425 |
| v_gtext, 40 characters, even x | 26.6 | 37.6 /s | 43,120 |
| v_gtext, 40 characters, odd x | 27.0 | 37.0 /s | 43,819 |
| vr_recfl 100×50, solid | 0.85 | 1,178 /s | 1,376 |
| vr_recfl 100×50, pattern 4 | 4.34 | 231 /s | 7,036 |
| box 100×50 as a 5-point v_pline | 2.49 | 402 /s | 4,034 |
| diagonal 100×100 v_pline | 2.31 | 432 /s | 3,753 |
| wind_create, open (400×160, every gadget), close, delete | 119.3 | 8.4 /s | 193,418 |
| 16-bit signed divide (`_Div16`) | 0.040 | 25,091 /s | 65 |
| 32-bit signed divide (`_Div32`) | 0.133 | 7,512 /s | 216 |
| float32: multiply, add, divide | 0.260 | 3,839 /s | 422 |
| read, bank $00 / far bank $02 / far bank $EF | 0.376 | 665 KB/s | 610 |
| read, bank $00 $A000 (the slow block) | 0.537 | 465 KB/s | 871 |
| read, VRAM through the MEMAC window | 0.554 | 451 KB/s | 899 |
| write, bank $00 / far bank $02 | 0.469 | 533 KB/s | 760 |
| write, bank $00 $A000 (the slow block) | 0.671 | 373 KB/s | 1,088 |
| write, VRAM through the MEMAC window | 0.687 | 364 KB/s | 1,113 |
| copy, bank $00 ↔ bank $00 / far bank $02 | 0.658 | 380 KB/s | 1,066 |
| copy, bank $00 to VRAM through the window | 0.858 | 292 KB/s | 1,390 |
| vram_write, the driver's upload, 256 bytes | 1.404 | 178 KB/s | 2,276 |
| **MVN**, any bank to any bank (`$00`↔`$00`, `$00`↔far, far↔far incl. `$EF`) | **0.105** | **2,386 KB/s** | **173** |
**The block move is 6.3× the C loop, and the bank does not matter.**  The
`copy` row above is what the language offers -- a loop through a far
pointer, `src/sys/farmem.c` -- and the `MVN` row is the CPU's own block
move (`src/sys/blkmove.s`), measured 2026-09-22.  173 base-clock cycles
for 256 bytes is **7.4 cycles a byte at the 65816's clock**, against the
datasheet's 7, which is the sign that the number is the instruction and
not the harness.

Every bank pair measures the same to three digits, `$00` to `$00` and
bank `$04` to bank `$EF` alike, so **the 14.9 MB is uniformly fast and
there is no penalty for parking something high in it**.

The number exists because it decides something: whether a near region can
be parked in far memory and fetched back often enough to hold more than
one application (`docs/multitasking.md`).  A 6 KB region is 2.5 ms, so a
switch -- park one, restore another -- is about **5 ms**, or a tenth of a
50 ms slice.  Through the C loop the same switch is 32 ms, which is two
thirds of the slice and not a design.

| read, the OS ROM at $E000 | 0.377 | 664 KB/s | 611 |
| vro_cpyfm 320×100 screen to screen, aligned | 2.28 | 439 /s | 3,690 |
| vro_cpyfm 320×100 screen to screen, odd x (the pixel path) | 3,486 | 0.3 /s | 5,652,125 |
| vrt_cpyfm 32×24 icon, transparent | 1.59 | 630 /s | 2,576 |
| vrt_cpyfm 32×24 icon, replace | 1.56 | 640 /s | 2,534 |

Two things the memory rows say, both about Altirra rather than the
boards. The OS ROM reads as fast as the accelerator's SRAM, and SRAM bank
`$02` reads exactly as SDRAM bank `$EF` does: the emulator's fast-bus
layers have one speed. Hardware will not agree on the first and may not
on the second. The slow block at `$A000` — the 16 KB window `rapidus.c`
leaves on the motherboard bus because the MEMAC window lives there — costs
about one machine cycle per bus byte over the fast bus (871 against 610
for a 256-byte read), and the MEMAC window itself costs the same as the
slow RAM around it. So the CPU reads VRAM at 450 KB/s and writes it at
360 KB/s, which is what the driver's whole architecture assumes; the
driver's own upload managed half that, and that is the first find.

## What the profile named

`--profile` runs Altirra's instruction profiler across one script of a
row and sums it per function, the attribution `tests/emu/bench_vdi.py`
already had. Over the dialog, the text and the window rows the top three
were the same three functions:

    form_dial START, objc_draw, FINISH      364,927 insns/unit
      bcb_common       102,030 insns/unit    28%
      vram_write        68,446               19%
      _Mul16            33,164                9%
    v_gtext, 40 characters                  124,644 insns/unit
      bcb_common        42,960               34%
      vram_write        34,280               28%
      _Mul16            13,600               11%

`bcb_common` builds a blitter control block. It was 537 instructions a
block: it started by zeroing the 21 bytes in a loop through a stack
pointer, which this compiler renders at 20 instructions a byte, then
stored the fields through the same pointer. A glyph is two blocks (the
AND strip and the OR strip), so 1,074 instructions a character went into
laying out 42 bytes — a third of the text row.

`vram_write` copies a block into VRAM through the MEMAC window; every
block goes through it, 21 bytes at a time, and it was a byte loop at 20
instructions a byte.

`_Mul16` is the compiler's 16-bit multiply, 42 instructions; eight of
them a glyph, from the row-base arithmetic in `v_gtext` and `blit_mask`.

## Two rewrites

**`bcb_common`** (`src/vbxe/vbxe.c`) now overlays the 21 bytes with a
struct of the fields they are and stores each once, no zero loop: 40
instructions a block, from 537. Nothing changes on the wire — the
callers still set the mask, pattern and mode bytes after it, as before.

**`vram_write`** moves words, counting down, with the pointers and the
count in the direct page — 15 instructions a word, from 40 — and the
window pointer is deliberately *not* `volatile`: the compiler will not
store a word through a volatile pointer without a stack temporary, and a
store through a pointer it cannot see past is not one it can drop. The
driver's upload row is the check: 1,117 cycles per 256 bytes, from 2,276,
which is now the benchmark's own write loop (1,113) — the bus, not the
code.

After both:

| Row | before | after | |
|---|---:|---:|---|
| form_dial START, objc_draw, FINISH | 77.7 ms | **50.7 ms** | −35% |
| objc_draw of the dialog alone | 66.9 | **41.0** | −39% |
| v_gtext, 40 characters, even x | 26.6 | **15.4** | −42% |
| v_gtext, 40 characters, odd x | 27.0 | **15.8** | −42% |
| vr_recfl 100×50, solid | 0.85 | **0.70** | −18% |
| vr_recfl 100×50, pattern 4 | 4.34 | **3.18** | −27% |
| box 100×50 as a 5-point v_pline | 2.49 | **1.63** | −34% |
| diagonal 100×100 v_pline | 2.31 | 2.31 | the line stepper, unchanged |
| wind_create, open, close, delete | 119.3 | **80.8** | −32% |
| vram_write, 256 bytes | 1.40 | **0.69** | 178 → 363 KB/s |
| vro_cpyfm 320×100 aligned | 2.28 | **2.15** | |
| vrt_cpyfm 32×24 icon | 1.59 / 1.56 | **1.49 / 1.47** | |

The memory and arithmetic rows did not move, as they should not have.
`make test-m3` is 68/68 and `make check-cc` passes with the change, so
the seam under every gate is the same seam, faster.

A 40-character line is now 0.38 ms — 623 cycles — a character. The
profile after the rewrite puts the rest where it was expected:
`vram_write` at 450 instructions a character (two blocks, 15 a word plus
the mapping), `_Mul16` at 340, `vdi_v_gtext` itself at 238.

## Compiler bug B7, found by the rewrite

The struct overlay was guarded with
`_Static_assert(sizeof(BCB) == 21, ...)`, and the assertion failed —
while the generated code laid the struct out in 21 bytes and every gate
passed. `sizeof` of a struct with 16-bit members after a byte member
evaluates to the padded size (26 for the BCB, 6 for a `{u16, u8, u16}`) *where an
integer constant expression is required* — an enum, an array bound, a
static assertion — and to the unpadded size everywhere else, and the
code generator uses the unpadded layout throughout. So an array of such
structs indexed through an enum stride reads the wrong element.

That is the seventh defect this tree has met and the first in the front
end's constant arithmetic rather than in code generation;
`tools/ccbug/bugs.c` reproduces it in the vendor's simulator (bug 17411,
fix 801) and `make check-cc` reports "9 of 9 bug shapes still present".
Rule 7 in `tools/ccbug/README.md`: never `sizeof` a struct where a
constant expression is required; write the byte count out. `BCB_SIZE`
is 21 by name and the assertion is gone.

## The third run, 10 September: the display list under the runner

The suite had grown eight phases since the table above, and the audit
re-ran the benchmark to see what they cost. Every drawing row was a
quarter to a third slower, and the clock line was the clue:

    2 September   clock: 32520 cycles per frame
    9 September   clock: 24280 cycles per frame

Altirra's counter leaves out the cycles ANTIC halts the CPU for, so a
frame with fewer counted cycles is a frame with more DMA in it. 24,280
is a PAL frame with a 40-column GR.0 text screen on it — DOS's screen,
which the runner never turns off because the VBXE overlay hides it. And
32,520 is a frame with almost nothing on it: on 2 September the runner's
staging buffers (`teststage`, then at `$A800-$BFFB`) sat on top of the
OS display list at `$BC20`, and a display list of zeros is 240 halted
cycles a frame. Phase 14 moved the buffers into the U1MB window on
4 September, the display list survived from then on, and every run since
has drawn under a text screen it could not see. `scratchpad`'s probe
confirmed it on the bridge: DMACTL `$22`, DLIST `$BC20`, and `HWPOKE
$D400 $00` takes the clock straight to 32,760.

Which is a bus finding, not a counting one. On Altirra's Rapidus the
fast-bus CPU runs on through a halt, so counted cycles per unit fell
while wall time rose; but every byte the VDI writes through the MEMAC
window and every VBXE register it touches waits on the chip bus, and a
text screen takes some 8,500 of that bus's 35,568 cycles a frame. The
overlay is opaque and ANTIC's picture is under it, so the picture was
buying nothing.

**The remedy is in the product, not the bench:** `antic_suspend()` and
`antic_resume()` (`src/antic/antic.c`). When the VBXE surface comes up,
`gem.c` and the runner save `SDMCTL` and write zero to it and to
`DMACTL` — the shadow, because the OS VBI writes the shadow back every
frame — and put both back on the way out, so DOS gets its screen as it
left it. The ANTIC device does not go through this: its playfield *is*
the screen. Whether the real VBXE overlay is as content with the
playfield off as Altirra's is has not been tried on hardware; it is
assumed from the overlay being a thing of VBXE's own, and from the whole
of the first suite having run that way by accident for two weeks.

Like for like — DMA off, or as good as, both times — the three columns are:

| Row | 2 Sep | 9 Sep, DMA on | 10 Sep, DMA off | 10 vs 2 |
|---|---:|---:|---:|---:|
| form_dial START, objc_draw, FINISH | 50.7 ms | 64.4 | **60.0** | +18% |
| objc_draw of the dialog alone | 41.0 | 53.5 | **49.2** | +20% |
| v_gtext, 40 characters, even x | 15.4 | 20.8 | **19.0** | +24% |
| v_gtext, 40 characters, odd x | 15.8 | 21.1 | **19.3** | +22% |
| vr_recfl 100×50, solid | 0.70 | 0.84 | **0.79** | +12% |
| vr_recfl 100×50, pattern 4 | 3.18 | 3.65 | **3.44** | +8% |
| box 100×50 as a 5-point v_pline | 1.63 | 2.06 | **1.88** | +15% |
| diagonal 100×100 v_pline | 2.31 | 2.70 | **2.42** | +5% |
| wind_create, open, close, delete | 80.8 | 101.7 | **94.0** | +16% |
| read, bank $00 (fast SRAM) | 0.376 | 0.402 | **0.392** | +4% |
| write, bank $00 | 0.469 | 0.526 | **0.488** | +4% |
| read, VRAM through the window | 0.554 | 0.687 | **0.576** | +4% |
| write, VRAM through the window | 0.687 | 0.809 | **0.716** | +4% |
| vram_write, the driver's upload | 0.69 | 0.83 | **0.72** | +4% |
| vro_cpyfm 320×100 aligned | 2.15 | 2.26 | **2.23** | +4% |
| vrt_cpyfm 32×24 icon, transparent | 1.49 | 1.71 | **1.52** | +2% |

The display list was a third of the drawing rows' loss. The rest is
three things that arrived since 2 September, and the table separates
them by where they show:

- **Interrupts, about 4% of everything.** The 2 September run predates
  Phase 9 by ten hours; there were no handlers then. Now a VBI and the
  pointer's IRQ take their share of every frame, and every row — the
  memory rows included, which touch nothing the phases changed — is 4%
  slower. That is the price of a live pointer, and it is paid.
- **The blit list lives in the write-through window.** Phase 14 moved
  the 252-byte BCB stage (`bcb[]`, `src/vbxe/vbxe.c`) out of bank `$00`'s
  data into `zwin`, `$4000-$47FF`, to give the stack its 2 KB; the map's
  own note says what moved there "is read far more than written, and a
  write costs one bus cycle". True of the window trees and the message
  queue. Not true of the blit list, which is *built* — 21 stores a
  block, two blocks a glyph — and read once. Yesterday's profile has
  `bcb_common` at 1.3 counted cycles an instruction against 0.4 for the
  fast-bus code around it, and 1,680 write-through stores a 40-character
  line is a good part of what separates 19.0 ms from 15.4. The fix is a
  placement, not a rewrite, and it is the first item below.
- **The device seam** (Phases 33–35): `v_gtext` executes 12% more
  instructions a line than it did (77,860 a unit against ~69,200), and
  the VDI now reaches its device through `vdev->` for every raster
  operation. Not separated from the other two by measurement yet; the
  profile after the blit list moves will say.

## What is left, in order

- **The blit list out of the write-through window.** 252 bytes that
  want a home in window 0, which runs at full speed both ways. In
  GEM.COM's map `LoRAM` has 47 bytes free and `Near` 324, so either the
  boundary between them moves and leaves the near code with seventy, or
  the stage shrinks — and a shorter list is not free, because a full
  list drops the blit (`bcb_new` returns 0) and the callers' longest
  chains would need counting first.
- **`_Mul16`, eight a glyph.** The row base (`y × stride`) is computed
  per glyph in `v_gtext` and again in `blit_mask`; hoisting it to once a
  string and stepping by the stride would take ~300 instructions off each
  character, a fifth of the row.
- **The upload loop in assembly.** 15 instructions a word is the
  compiler's; `lda [s],y / sta [d],y` with a DP count is 5, and every
  block passes through it. Bounded, ~30 lines, and the second fifth.
- **`vro_cpyfm` at odd x.** 3.4 *seconds* for 320×100 — 98 µs a pixel
  through the window. The AES never takes this path (window x snaps to
  even, Phase 8) but an application can, and it should be a nibble-mode
  blit with a pre-shifted copy, like the odd-x glyph strips, not a pixel
  loop.
- The dialog and window rows are dominated by what they draw, not by the
  AES: `objc_draw` alone is 41 of the 51 ms. After the two items above
  the next profile decides, not this list.

## Running it

    make bench                                     # every row, ~4 min
    python3 tests/emu/bench_gem.py text blit       # groups by substring
    python3 tests/emu/bench_gem.py --profile --top 12 dialog
    python3 tests/emu/bench_gem.py --json out.json # for diffing runs
    python3 tests/emu/bench_gem.py --list

It uses the m3 runner's disk (`build/m3-boot.atr`) and cannot share the
emulator with another gate; `make bench` waits for the build, not for a
running `AltirraSDL`.
