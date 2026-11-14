# Plan: plain Atari programs and the cartridge, from GEM

Asked for on 2026-11-13: run plain 8-bit programs from the desktop,
DUP's binary load and run cartridge, and a cartridge icon as EmuTOS has
(its `c`).  The choice was **restart GEM**: GEM ends, the program runs
with the whole machine, and GEM starts again when it is done.  Promised
for the next release with MyDOS 4.x, SpartaDOS X and G4DOS alike.

## Why GEM ends

A plain program -- a game, a DOS 2 utility, anything in the Atari's
binary format -- loads where it was built to load, $2000 or so.  That is
gem4xe's direct page, its stack and its near code.  Nothing can be kept
under it, and a 65C816 cannot fence a 6502 program off.  So GEM gets out
of the way completely, as Quit does, and leaves a note asking to come
back.

## What is a plain program

- **By name**, for the icon: `.COM`, `.XEX`, `.EXE` and `.OBJ` get the
  program icon.  A GEM program never has one of those names.
- **By content**, for the run: the AES opens a file with one of those
  names and reads two bytes.  `$FF $FF` is the Atari's binary format: a
  plain program.  Anything else goes to the G4A loader as today, which
  refuses what is not gem4xe's.  A `.PRG` costs nothing extra.

Any program can run one, not just the desktop: `shel_write(SHW_EXEC)`
with the file's name.

## The way back, DOS by DOS

| DOS | GEM ends to | the program is run by | GEM comes back from |
|---|---|---|---|
| G4DOS | its shell, `SHELL.SYS` | the shell, reading GEM's note | the shell, whom DOSVEC loads when the program ends -- or after a RESET |
| MyDOS 4.x, DOS 2 | a stub at $0400 | the stub's own CIO binary loader | the stub again, through DOSVEC |
| SpartaDOS X | its command processor | a batch file GEM writes: the program, then GEM | the batch file's next line |

**The note** (`src/sys/runnote.h`) sits in the cassette buffer's tail,
after the G4DOS shell's record of where it was:
- a mark, `RQ`;
- the step: 1 run the program, 2 run GEM;
- the program's path, `D2:\GAMES\X.XEX`;
- a sum.

A cold start clears the page.  A program that overwrites the note breaks
its sum.  Either way there is no note, and the shell is a prompt -- the
same as booting.

**Programs put aside** (the switcher) would be lost.  So GEM refuses,
and says to close them first.

## Steps

1. **G4DOS.** Done, phase 162.
   - The desktop's names.
   - The AES's check, the note, GEM ends.
   - The shell acts on the note: step 1 is the program, step 2 GEM.
   - Gate: a program run from the desktop prints its line and ends, and
     GEM is back.  A program that loops is RESET, and GEM is back.

2. **MyDOS 4.x and DOS 2.** Done, phase 163.
   - A stub of 379 bytes, copied to $0400 as GEM's last act.  It also
     marks the OS's boot done (COLDST 0, BOOT? bit 0), which a GEM
     started as AUTORUN.SYS never was, so RESET is warm.
   - The stub opens the file and loads it by segments through CIO, with
     INITAD after each and RUNAD at the end, as G4DOS's loader does.
   - DOSVEC points back at the stub, which then loads GEM.COM the same
     way.
   - MyDOS has its own binary load (XIO 39/40), but DOS 2's lives in
     DUP.SYS, so one loader serves both.
   - Gate: `test-m68`, on MyDOS 4.50 and a double-density DOS 2.

3. **SpartaDOS X.** Done, phase 164: RUN8.BAT and RUN9.BAT in turn.
   - SDX's command processor runs batch files (`-NAME`), a line at a
     time, and a program that ends returns to the batch.
   - Measured first: whether a batch started through XCOMLI from a
     running program keeps going after that program has ended.
   - Gate: `test-m69`.  Measured: it does, and a RESET abandons the batch.

4. **The cartridge.** Done, phase 165 (and the DOS 2 floppy went with it).
   Measured first (2026-11-13), and TRAMSZ is no use:
   it is 1 with no cartridge, with BASIC and with a cartridge alike,
   because the XL's BASIC counts at power-on and G4DOS then switches it
   out.  Under GEM, $A000-$BFFF is RAM unless a cartridge is in, and that
   RAM can read $BFFC = 0 just as a cartridge's header does.
   - **What there is**, found once at boot, before the Rapidus windows go
     fast, with interrupts off:
     - a cartridge: $BFFC is 0 and does not take a write;
     - else built-in BASIC: PORTB bit 1 cleared for a moment, and
       BASIC's header read ($BFFC 0, $BFFA in $A000-$BFFF);
     - else nothing.
   - **A cookie**, `G4CT`: 0 nothing, 1 BASIC, 2 a cartridge.  The
     desktop asks Ssystem, as it would any cookie, and touches no
     hardware.
   - **An icon on the desk**, labelled BASIC or CARTRIDGE, drawn for it
     in `tools/a8icons.py` (a Falcon DESKICON.RSC without one gets the
     removable-disk picture).  It is placed and saved like a drive icon.
   - **Opening it** is `shel_write(SHW_EXEC)` with the name `CAR:`, the
     name SDX gives the cartridge's device.  Any program may ask; DUP's
     B will.  GEM ends as for a plain program:
     - G4DOS: the note says `CAR:`.  The shell switches BASIC in if
       there is no cartridge, sets RAMTOP to $A0, opens E: again, and
       jumps through $BFFA, as DUP's B does.  BASIC's `DOS` goes through
       DOSVEC to the shell, which switches BASIC out before GEM.
     - DOS 2 and MyDOS: the stub, split in two -- what has to outlive
       the cartridge stays below $0580, and what runs once before it
       (`r8_go` and the cartridge start) goes in $0580-$05FF, which
       BASIC uses only once it is running.  `r8_back` switches BASIC out
       before GEM.
     - SDX: the batch's first line is `CAR` or `BASIC`, SDX's own
       commands (User Guide 4.7, 4.4).
   - Gates: our own 8 KB test cartridge (it prints a line and leaves
     through DOSVEC, as BASIC's DOS does) and the emulator's BASIC.  On
     G4DOS first, then the other DOSes.

5. **DUP's L and B.**
   - These are the same two calls, from DUP's menu.
   - K (binary save), M (run at an address) and N (MEM.SAV) stay
     refused: each needs memory GEM holds while it runs.

Each step is its own phase, with its gate, and the suite passes before
each commit.
