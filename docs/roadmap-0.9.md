# Roadmap -- 0.9 and 1.0

The numbering is the old Linux kernel's: an odd minor adds features, an
even one is optimisation and stability only.  0.8.x was the second kind
(phases 52-58).  **0.9 is features**, chosen from a gap analysis on
2026-09-26 against what TOS and EmuTOS offer users and programs;
**1.0 is stability and speed** on top of it, measured by G4BENCH.

## Where the gaps were

The programming interface is essentially complete: all 79 AES opcodes,
every real VDI opcode from 1 to 131 (the four no-ops are DRI's own), and
the GEMDOS the ports so far have needed.  What is missing is mostly what a
PERSON sees -- the desktop's keyboard, a handful of the desktop's own
features, and applications to use it with.

## 0.9

| | | status |
|---|---|---|
| 1 | **G4BENCH** -- a GEM application that times drawing, text, blits, the AES and a Mandelbrot, on screen and in `G4BENCH.TXT`; a gate holds each result to a reference, so every later change has a number to beat | **done** (phase 59) |
| 2 | **The desktop's keyboard** -- the menu shortcuts (^O ^I ^N ^D ^S ^A ...), Alt-letter to open a drive, the arrows to scroll | **done** (phase 60) |
| 3 | **Install application**, and a file dropped on a program's icon -- so a document opens the program that edits it | **done** (phase 61) |
| 4 | **The small desktop items** -- Select all, Close folder (up a level), Cycle windows, Show info on a drive, Set file mask, the name-conflict dialog on copy and the confirm-delete/copy/overwrite preferences | |
| 5 | **QED shipped**, if its licence allows it -- ported and gated, not yet in the tree's distribution | |
| 6 | **A Color CPX** for the control panel, beside `GENERAL.CPX` | |

## Not 0.9

Kept for after 1.0 unless something moves them: two applications at once
(`docs/multitasking.md` -- the most asked-for, and a large allocator
job), font sizes (one fixed cell today), the 6502 build (`docs/6502.md`),
a minimal install and a U1MB flash slot, Rapidus OS integration (its
vectors and allocator), a MyDOS product disk (its licence first),
Format and Install icon, Search, printing a document through the VDI's
printer device, and a translator's reach into the file selector's width,
the keyboard layout and the date format.

Small API items found on the way, to fold into whichever phase is near
them: `vqt_real_extent`, `wind_set(WF_BOTTOM)`, proving the sixth
accessory slot and the seventh refused, and confirming that `WM_*`
messages reach an accessory's own window.

## 1.0's first targets

From G4BENCH's first run (`docs/phase59.md`): the compiler's `_Mul32` at
about 6,000 cycles, a screen-to-screen copy on VBXE at 772 ms for 96x48
(probably the odd-x pixel path), a copy to memory and back at 650-750 ms,
and bold text at twice plain.
