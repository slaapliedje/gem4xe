# Phase 163 -- a plain Atari program from the desktop, on MyDOS and DOS 2

Step 2 of `docs/run8-plan.md`.  Phase 162 ran a plain program on G4DOS,
whose shell reads GEM's note.  MyDOS and DOS 2 have DUP.SYS instead,
which reads nothing.  So GEM brings its own way back.

## The stub

`src/run8.s` is 379 bytes of 6502 code, linked at $0400
(`src/run8.scm`).  It uses the cassette buffer and the free bytes after
it, up to BASIC's line buffer at $0580; MyDOS 4.50 keeps to $0700-$2949
and DOS 2 lower still.  `tools/run8stub.py` turns the link into
`build/run8_stub.h`, a C array GEM.COM carries.  The tool checks the
header offsets against the link, so a header that moved fails the build
rather than having GEM write a name over the code.

As GEM ends (`sh_stub` in `src/aes/shel.c`), it copies the stub to $0400
and fills in the header:

| offset | holds |
|---|---|
| +0 | `JMP r8_go` |
| +3 | the DOS's own DOSVEC |
| +5 | the program as CIO names it, `D2:>GAMES>X.XEX`, 48 bytes |
| +53 | GEM's own file, 20 bytes |

It then points DOSVEC at the stub.  GEM's way out of the machine is
`JMP (DOSVEC)` on these DOSes (`src/crt_atari.s`), so it lands there.

The stub's loader is G4DOS's (`src/fdos.s`), on the DOS's CIO:
- IOCB 1 opened, `$FF $FF`;
- each segment read to where it goes;
- INITAD after each segment, RUNAD at the end as a subroutine.

MyDOS has its own binary load, but DOS 2's is in DUP.SYS, gone, so one
loader serves both.

**The way back.** The program returns from RUNAD, or jumps through
DOSVEC, or the user presses RESET.  All three reach `r8_back`, which puts
DOSVEC and DOSINI back as the DOS had them and loads GEM.  For RESET the
stub hooks DOSINI: the DOS's own init runs first, then DOSVEC is pointed
back at the stub.

**GEM's own file.**  The AES looks for `D1:GEM.COM` or `D1:AUTORUN.SYS`
(`sh_ourfile`), whichever begins with the code running now:
- the file's first segment is GEM's near code;
- that code is loaded where it runs and never written;
- so 32 bytes of it in the file and in memory agree only for this very
  GEM, not for another program of the same name.

When neither matches, GEM refuses with an alert (`LS_PLAINGEM`, five
languages).  No gate reaches that path: a disk that boots GEM without
GEM's own file on it is the case it guards, and that disk is awkward to
make.

## What RESET does, measured

The gate's first RESET check passed with the DOSINI hook taken out, so it
proved nothing.  A probe showed why.  GEM started as AUTORUN.SYS runs
inside the OS's boot, and the boot never finishes:
- **COLDST** is still $FF, so any RESET is a cold start.  The disk
  boots again, and GEM comes back only because it is that disk's
  AUTORUN.SYS.
- **BOOT?** never gets its disk bit.  So once COLDST is cleared, a warm
  start calls no DOSINI at all.  The D: handler is gone, the stub cannot
  open GEM's file, and DUP fails to load with error 130.

The stub now leaves both as a finished boot leaves them: COLDST 0,
BOOT? bit 0.  A RESET is warm and comes through the hook, whichever way
GEM was started.  On G4DOS, GEM.COM is run through DOSVEC after the boot
has finished, so COLDST was already 0 there: phase 162's RESET did go
through the shell's note.

## The DOS 2 floppy's room

The stub and its code are 769 bytes of the DOS 2 build of GEM, and the
new alert is 112 bytes of `LANG.RSC`.  That took `gem-boot.atr` to 5 free
sectors, under its floor of 6 (the longest DESKTOP.INF), and test-boot
said so.  `LANG.RSC` now goes on the disks a DOS 2 or MyDOS boots
squeezed, as DESKTOP.RSC has been since phase 152:
- 10 sectors to 6;
- the AES unpacks it as it reads it (`lang_unsqueeze` in
  `src/aes/lang.c`);
- the floppy has 8 free.

A LANG.RSC that will not load falls back to the identical English built
into GEM.COM, so a broken unpack would look fine on the screen.
test-boot checks that the boot screen says Language LANG.RSC, and with
the unpack broken on purpose it reads "built in" and fails.

## Gate

**`test-m68`** runs two DOSes, each with its own GEM floppy in D1: and a
disk of its own format in D2: holding PROG.XEX and LOOP.XEX:
- MyDOS 4.50 (`build/gem-mydos.atr`, double-density D2:);
- a double-density DOS 2 (`build/gem-boot.atr`, single-density D2:).

On each:
- PROG.XEX double-clicked: its line, then GEM's boot screen and the
  desktop.
- LOOP.XEX, with COLDST 0 while it runs.  Then RESET: WARMST $FF, a
  warm start, and GEM back.
- File -> Quit: the DOS's own DUP menu, so the stub gave DOSVEC back.

| broken on purpose | result |
|---|---|
| no DOSINI hook | RESET lands in DUP on both |
| `r8_back` not giving DOSVEC back | File -> Quit loads GEM again instead of DUP, on both |
