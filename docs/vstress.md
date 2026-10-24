# VSTRESS: the VBXE path on its own

`make vstress` builds one DOS 2 floppy per mode (`build/vstress-X.atr`). Each
boots straight into gem4xe's own Rapidus, interrupt, VBXE and pointer code,
started the way `GEM.COM` starts it, with nothing above it: no AES, no desktop,
and no DOS call after start-up. `src/vstress.c` lists the modes.

It is for a real machine that freezes under gem4xe's VBXE screen. The emulator
never freezes, so this is not a gate; every mode is still run once in AltirraSDL
before it goes on a card, which caught two mistakes of its own (below).

## What a frozen screen still says

- **A quiet beep once a second** while the loop and the vertical blank are running.
- **A steady tone** if a blit list has not finished two seconds after it was
  started: `src/vbxe/vbxe.c` built with `BLIT_WATCHDOG` (high when only
  BCB_LOAD is set, middle for BUSY, low for both). `GEM.COM` is never built
  with it; its VBXE code compiles identically to a build without the option.
- **Silence**: the CPU, or the vertical blank, has stopped.

## What the user's 130XE did (October 2026)

The machine is a 130XE with a Rapidus, a U1MB, a VBXE (core 1.26) and a SIDE2.
gem4xe froze on it in VBXE mode on every build back to 0.8.2, and never in ANTIC mode.

| Mode | What it does to the VBXE | Result |
|---|---|---|
| P | the pointer only, rare small blits | ran |
| C | CPU writes through MEMAC, no blitter | ran indefinitely |
| R | BLITTER_BUSY read in a loop, no blits | ran |
| W | a blit, then two frames without touching the VBXE | ran for minutes |
| L | four full-screen fills a list, then three idle frames | ran |
| M | upload, stop and start, no BUSY read, ~0.5 ms apart | ran |
| N, D | the VDI's bars, polled by `blit_idle` | froze in 1–2 s |
| B | one rectangle a list, polled | froze in about 1 s; once ran 38 s |
| I | B with the VBXE interrupt off and acknowledged | crashed, POKEY static |
| F | B's rate, one BUSY read after each blit | froze in about 1 s |
| S | BLITTER_START rewritten ~0.5 ms apart, nothing else | static after ~3 s |
| G | F with ten times the wait | ran for hours, then stopped |
| H | S with ten times the wait | static after ~4 s |

The freeze tracks how often the CPU touches the VBXE soon after a blit, not
any one register; heavy blitting with the CPU kept away (L) is fine. Runs
from a cold machine lasted longer than runs after a warm one, which with the
Rapidus known-issues sheet (`ref/Rapidus_known_issues.pdf`: turbo-mode
instability with temperature, put down to the 6502) points at the machine.
A tester's VBXE machine runs the same builds without freezing. Exec816, which
draws with gem4xe's VBXE code, froze on this machine too, once its desktop drew.

## Two mistakes the emulator caught

- The first build drew mode N like mode C with the pointer on. cc65816 5.18.2
  gets a branch on constant comparisons joined by `||` or `&&` backwards:
  `if ('N' == 'P' || 'N' == 'D')` is taken. The modes are chosen by the
  preprocessor now. Nothing in the product has that shape; a scan of every
  source said so.
- The test set up the 512-pixel screen with the 640-pixel stride, which drew
  smeared rows; it uses `OVATT_WIDTH_NORMAL` and the device's stride now.
