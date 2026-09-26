# Phase 59 -- G4BENCH, and what it found on its first run

The first item of 0.9 (`docs/roadmap-0.9.md`): a benchmark that is an
ordinary GEM program, so its numbers are the ones a program sees and it
runs as it is on real hardware.  `APPS\G4BENCH.PRG` on the applications
floppy, the card and the release.

## What it is

`src/apps/g4bench.c`, one C file and no resource.  It opens a window,
uses the work area as its canvas, and runs eighteen tests a fixed number
of times each, timed by `Tgettimeofday` -- the system's ~4 kHz timer,
exact to a quarter of a millisecond:

| | |
|---|---|
| Graphics | horizontal, vertical and diagonal lines; filled boxes solid and patterned; filled circles and ellipses; polygons; rounded boxes |
| Text | 40 characters; bold and underlined; cycling four heights |
| Blits | screen to screen; screen to memory and back; a 32x32 icon |
| AES | drawing a five-object dialog; opening and closing a window |
| CPU | a Mandelbrot, 64x40 at 32 iterations, 12-bit fixed point, drawn as it goes |

Every test is sized to the canvas, so the same program runs on the VBXE's
640 pixels and the ANTIC screen's 320.  The results go in the window --
milliseconds per call -- and into `G4BENCH.TXT` beside the program, so a
run on somebody's machine can be set beside another.

## The gate

`make g4bench` (in `make test`) boots a DOS 2 disk on which G4BENCH is
`DESKTOP.PRG`, once with a VBXE and once without, so the shell runs it
straight after the boot.  It reads the program's own `g4b_done` and
`g4b_us[]` by symbol -- the loader keeps where it put the program in
`app_near`, and a symbol translates as address minus link base plus that
-- with no test mode in the program.  Each result is held to
`tests/emu/g4bench_ref.json`: **more than 10% slower is a failure**,
seen red with one reference figure halved.  `ARGS=--update` rewrites the
reference.  Two runs gave the same microseconds for every test but one,
which is why ten per cent is not a tolerance that will cry wolf.

## What the first run found -- 1.0's first targets

Not fixed here, because 0.9 is features; recorded because they are the
largest numbers on the page.

- **`_Mul32` is about 6,000 cycles.**  The Mandelbrot at 160x100 took four
  minutes, and with the bank now in every profile row it was plain where:
  75% in the compiler's run-time 32-bit multiply, for the three
  16x16-to-32 products an iteration takes -- 25,000 cycles an iteration.
  A shift-and-add multiply on this CPU should be a few hundred.  The
  product already links its own `_Div16` and `_Mod16`; a `_Mul32` of its
  own would reach the VDI's diagonal lines, the menu loop's idle
  arithmetic (phase 55) and every program built with the kit.  The test
  was cut to 64x40 so a run takes a minute or two.
- **A screen-to-screen copy on VBXE is 772 ms** for 96x48 pixels, against
  35 on ANTIC.  The copies start at the window's work area, and a 4bpp
  copy at an odd x is the CPU's pixel path, not the blitter
  (`docs/phase7.md`) -- which, if that is what it is, is every window
  scroll a program does.
- **Screen to memory and back is 650-750 ms** on both screens, for 64x32.
- **Bold text is twice plain** on both.
