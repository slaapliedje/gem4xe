# Phase 164 -- a plain Atari program from the desktop, under SpartaDOS X

Step 3 of `docs/run8-plan.md`.  G4DOS has its shell, DOS 2 and MyDOS get
GEM's stub.  SpartaDOS X already has the answer itself: batch files.

## What SDX does, measured

The User Guide 4.50, section 5.2.1, says the command processor reads the
environment variable `BATCH` just before it prints its prompt, runs the
batch file it names, and deletes the variable.  On SDX 4.50, in the
emulator:
- `SET BATCH=D1:T.BAT` typed at the prompt ran T.BAT at once.  Its first
  line ran a program, and when that program returned, the batch went on
  to its second line.
- The same SET from inside GEM, through File -> DOS command (XCOMLI),
  followed by Quit: the batch ran after GEM had ended, not inside the
  XCOMLI call.

## How

`run8_sdx` in `src/aes/run8sdx.c`:
- finds GEM's own file, as on DOS 2 (`sh_ourfile`): `D1:GEM.COM` in the
  current directory first, because AUTOEXEC.BAT changes into `\GEM` and
  runs GEM there; then `D1:>GEM>GEM.COM` and `D1:>GEM.COM`;
- writes a batch file beside it, two lines: the program as CIO names it,
  then GEM;
- sets `BATCH` to it with `SET`, through the same `dos_command` that
  File -> DOS command uses;
- and GEM ends.

SDX loads the program itself, so `sh_isplain` also takes SDX's own
relocatable format (`$FA $FF`) under SDX.

**Two names, RUN8.BAT and RUN9.BAT, in turn.**  The first version wrote
RUN8.BAT every time, and the second program from the same desktop said
"This application cannot be found".  The GEM a batch starts runs while
SDX still has that batch open, reading it, so the file cannot be opened
for writing again.  Now, when one name will not open, the other is used.
By the time SDX reads `BATCH`, it has closed the older one.

**RESET.**  SDX abandons a batch file at RESET (the User Guide's CLR,
4.12, is for what "a batch file aborted with <RESET>" leaves).  So a
RESET during the program leaves you at SDX's prompt; type GEM.  On G4DOS,
MyDOS and DOS 2, RESET comes back to GEM.

**Not in the DOS 2 build.**  `build/gem-dos2.xex` leaves `run8sdx.o` out,
as it leaves out G4DOS's half of GEMDOS.  `src/sys/nog4.c` has a
`run8_sdx` that refuses, because a DOS 2 floppy never boots SDX.  The
floppy keeps its 8 free sectors.

## Gate

**`test-m69`** runs the system floppy with the SDX cartridge, booted as
anybody with that cartridge boots it.  D2: holds `\GAMES\PROG.XEX` and
`LOOP.XEX`, and everything is done through the desktop's own windows:
- PROG.XEX: its line, then GEM again from the batch's second line.
- PROG.XEX again, from that GEM, through RUN9.BAT, and GEM back.
- LOOP.XEX, through RUN8.BAT again.  Then RESET: SDX's prompt.
- GEM typed at the prompt, then File -> Quit: SDX's prompt, and no batch
  runs a second time.
- D1:'s working copy: RUN8.BAT holds LOOP.XEX and GEM, RUN9.BAT holds
  PROG.XEX and GEM, and the SDFS checks clean.

| broken on purpose | result |
|---|---|
| one name only (the first version) | the second program: "cannot be found" |
| the batch without GEM's line | after PROG.XEX, SDX's prompt and no GEM |

## Also: the tests' leftovers in /tmp

`tests/host/test_sdfs.py` made a temporary folder for every disk it
tested and never removed it.  That came to 18,785 folders, 12 GB of the
RAM disk every session on the machine shares.  It now removes each disk's
folder when the disk is done (`weakref.finalize`).  Five more scripts left
smaller leftovers, and each removes its folder at exit now:
- the same file's card-image helper;
- `test_kit_install.py`;
- `tools/ccbug/qscan.py`;
- `m15_gdos.py`, `m60_move.py`, `m61_kitcpx.py`.
