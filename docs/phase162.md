# Phase 162 -- a plain Atari program from the desktop, on G4DOS

Step 1 of `docs/run8-plan.md`.  A game or a tool written for the 8-bit
Atari itself opens from the desktop like a GEM program.  GEM ends, the
program runs with the whole machine, and GEM starts again after it.
The choice was **restart GEM**: such a program loads at $2000 or so,
which is gem4xe's own memory, so nothing of GEM can stay.

## How

**The desktop** gives `.COM`, `.XEX`, `.EXE` and `.OBJ` the program icon,
beside the ST's `.PRG`, `.APP`, `.TOS` and `.TTP`.  Opening one is the
same `shel_write` as opening a GEM program.

**The AES** (`sh_isplain`, `sh_plain` in `src/aes/shel.c`):
- for one of those four names, it opens the file and reads two bytes;
- `$FF $FF`, the Atari's binary format, is a plain program;
- anything else goes to the G4A loader, which refuses it as before;
- a `.PRG` is never opened twice.

For a plain program, GEM writes a note and ends as Quit ends it.  Any
program can ask for one this way, not just the desktop.

**The note** (`src/sys/runnote.h`) is 60 bytes in the cassette buffer's
tail, $0444-$047F, after the shell's own record of where it was:

| bytes | holds |
|---|---|
| 0-1 | `RQ` |
| 2 | the step: 1 run the program, 2 run GEM |
| 3-58 | the program in the shell's form, `D2:\GAMES\PROG.XEX` |
| 59 | a sum, the shell's record's rotation |

**G4DOS's shell** (`note_go` in `src/shell/shell.c`):
- At step 1, it turns the note to step 2 and runs the program through its
  own command line.  So the shell's checks apply: a file G4DOS would
  find another of first, or one too deep, is said, and a key goes on to
  GEM.
- At step 2, it clears the note and runs `D1:GEM.COM`, as G4DOS boots it.

The program ends through DOSVEC, which loads the shell.  A RESET does
the same.  So GEM comes back either way.

A cold start clears the page, and a program that writes over the note
breaks its sum.  Either way there is no note, and the shell is its
prompt, as before.

**Programs put aside** would be lost.  So GEM refuses with an alert
(`LS_PLAINASIDE`, five languages): quit them first.

On SpartaDOS X, MyDOS and DOS 2 the file still goes to the G4A loader,
which refuses it, as before.  Those are steps 2 and 3.

## Gate

**`test-m67`**: the system floppy, and in D2: `\GAMES\PROG.XEX` (prints a
line, returns) and `LOOP.XEX` (prints a line, loops).  All of it through
the desktop's own windows and the pointer:
- PROG.XEX double-clicked: its line on the screen, then GEM's boot
  screen and the desktop; the note gone.
- LOOP.XEX: its line, then RESET, then GEM again.
- M53.PRG started and put aside with CONTROL-TAB, then LOOP.XEX: refused.
  `sh_lastrc` is APP_E_PLAIN, the alert reads "needs all", and after
  RETURN the desktop is back.  No note, and LOOP.XEX has not run.
- RESET with no note: the shell's prompt.

| broken on purpose | result |
|---|---|
| the shell not running GEM at step 2 | the shell's prompt after PROG.XEX; "GEM came back" fails |
| the AES's check for programs aside | LOOP.XEX runs with M53 aside; five checks fail |

## Also: test-m36 waited a fixed time

`test-m36` failed in this phase's suite and passed alone, as it once did
before.  It read the module settings after a fixed 2600 frames, and they
land between frames 2500 and 2600, when the panel boot-inits its modules.
A GEM.COM a few sectors longer reads the defaults.  It waits for the
desktop to settle now, as `shots.boot` does.  Its control boot, with no
saved file, still has to show the defaults, so the gate cannot pass on a
machine that restored nothing.
