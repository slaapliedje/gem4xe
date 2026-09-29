# Roadmap -- 1.0

1.0 is **stability and speed** on top of 0.9's features (the numbering
is the old Linux kernel's: odd adds features, even does not).  Every
speed item is measured by G4BENCH (`make g4bench`, `docs/phase59.md`),
whose reference must be beaten and must never be lost by more than 10%.

The figures are milliseconds a call, from the 0.9 reference
(`tests/emu/g4bench_ref.json`), on the emulated Rapidus.

## Speed

| | | VBXE | ANTIC | status |
|---|---|---|---|---|
| 1 | **The 32-bit multiply.**  The compiler's `_Mul32` is about 6,000 cycles; three of them an iteration are why a 64x40 Mandelbrot takes 40 seconds.  Our own, as `_Div16` and `_Mod16` already are (`--override`), reaches the VDI's curves, the menu loop, a program's arithmetic -- everything built with the kit | Mandelbrot 40,058 | 45,522 | |
| 2 | **A screen-to-screen copy on VBXE** at odd x -- the pixel path through the MEMAC window, not the blitter -- which is every window scroll | 772 | 35 | |
| 3 | **Screen to memory and back on VBXE**, still a pixel at a time (ANTIC's went by the row in phase 66) | 648 | 23 | |
| 4 | **Bold text at twice plain**: the thickening pass is a second whole glyph | 31 vs 16 | 33 vs 9 | |
| 5 | **Filled curves and polygons**, re-measured after 1: circles, ellipses, polygons, rounded boxes | 106 / 84 / 68 / 54 | 86 / 72 / 52 / 40 | |
| 6 | **A dialog, and a window opened and closed** | 37, 75 | 45, 81 | |
| 7 | **Programs packed** as GEM.COM is (G4Z, phase 57): QED is 328 KB unpacked, which is load time on every run and the reason it has no floppy | | | |

## Stability

| | | status |
|---|---|---|
| 8 | **`wind_set(WF_BOTTOM)`** -- asking for the bottom window is served; sending one there is not | |
| 9 | **The accessory slots proven**: the sixth loads, the seventh is refused and says so | |
| 10 | **`WM_*` messages reach an accessory's own window**, gated | |
| 11 | **SpartaDOS 3.2's root fallback in `Fdelete`**: its "is it still there?" open can find the root's file too (phase 65 fixed `Fopen`'s) | |
| 12 | **`memreport`'s pool model** is a page under the live machine (7,168 against 7,424, phase 69): find the page | |
| 13 | **MyDOS**, measured for the same root fallback | |

## Not in the tree's hands

Real hardware: 0.9 and QED have run only in the emulator.  The testers'
machines -- the Rapidus and VBXE rig, the Antonia 2 on ANTIC -- are what
1.0 is declared on.
