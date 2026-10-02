# Roadmap -- 0.12

0.12 is **speed and stability** on top of 0.11's features: an even
release adds none (odd ones do).  It takes over `roadmap-1.0.md`, written
when this line was to be called 1.0, with its figures measured again.

Every speed item is measured by G4BENCH (`make g4bench`,
`docs/phase59.md`), whose reference must not be lost by more than 10%,
and the desktop's by `make bench-desk`.  The figures are milliseconds a
call on the emulated Rapidus, from the 0.11 release build.

## Speed

| | | VBXE | ANTIC | status |
|---|---|---|---|---|
| 1 | **The 32-bit multiply.**  The compiler's `_Mul32` is about 6,000 cycles, and three of them an iteration are why G4BENCH's 64 x 40 Mandelbrot takes 40 of its 60 seconds.  Our own, as `_Div16` and `_Mod16` already are (`--override`), for every program and the kit | Mandelbrot 40,070 | 46,564 | **done for programs**, phase 92: 17,356 and 19,308; GEM.COM keeps the library's |
| 2 | **Filled curves and polygons**, measured again after 1: circles, ellipses, polygons, rounded boxes | 106 / 84 / 68 / 54 | 87 / 72 / 53 / 40 | **done**, phase 93: 69 / 56 / 44 / 37 and 49 / 44 / 28 / 23 |
| 3 | **Screen to memory and back on VBXE**: five times ANTIC's | 113 | 23 | |
| 4 | **Bold text at twice plain**: the thickening pass is a second whole glyph | 31 vs 16 | 34 vs 9 | |
| 5 | **A dialog, and a window opened and closed**; and the 3D frame, which costs a window open about 40 ms on the desktop (`docs/phase88.md`) | 38, 74 | 45, 85 | |
| 6 | **Programs packed** as GEM.COM is (G4Z, phase 57): QED is 328 KB unpacked, which is load time on every run and why it has no floppy of its own | | | **done**, phase 94: the desktop 211 sectors to 109, the DOS 2 floppy 14 free to 114 |

## Stability

| | | status |
|---|---|---|
| 7 | **A click made while a program is busy is lost**: queue the button's changes in the interrupt, as the ST does, rather than sampling it | **done**, phase 95 |
| 8 | **MyDOS 4.50: Quit and DOS commands stall** on the way back to MyDOS | |
| 9 | **The Control Panel after a live look switch** shows General's buttons until it closes: the panel's dialog is not redrawn | |
| 10 | **`wind_get` answers `WF_KIND`, `WF_NAME` and `WF_INFO`**, and **`wind_set(WF_BOTTOM)`** sends a window to the bottom (`docs/api.md`) | |
| 11 | **The accessory slots proven**: the sixth loads, the seventh is refused and says so | |
| 12 | **`WM_*` messages reach an accessory's own window**, gated | |
| 13 | **SpartaDOS 3.2's root fallback in `Fdelete`**: its "is it still there?" open can find the root's file too (phase 65 fixed `Fopen`'s); and MyDOS measured for the same | |
| 14 | **`memreport`'s pool model** is a page under the live machine (7,168 against 7,424, phase 69): find the page | |

Done before 0.12 began: the cartridge's white screen in Altirra
(`docs/phase78.md`).

## Not in the tree's hands

Real hardware.  The desktop has run on the user's Rapidus, VBXE and
Ultimate 1MB machine, but 0.9's features, QED and 0.11's look and icons
only in the emulator.  The testers' machines are what a stable release
is declared on.
