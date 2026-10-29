# The system floppy boots by itself

`gem-sdx.atr` carries gem4xe's own small DOS, `G4DOS.SYS`, on its boot
sectors.  On a machine with no SpartaDOS X it loads GEM; under
SpartaDOS X it is never run, and the floppy is the ordinary SDX disk it
always was.

## Why

The release's floppies carry no third-party DOS, so that they can be
given away.  The system disk booted only under SpartaDOS X, and
anywhere else -- an emulator's default setup, a machine with no SDX --
it failed with `BOOT ERROR` over and over.  A tester in AltirraSDL met
exactly that.  `gem-boot.atr` boots anywhere, but its DOS 2 is not
gem4xe's to give away.

The cartridge had already answered this (docs/cartridge.md): gem4xe
needs a DOS only to READ its files, and reading is the small half of a
DOS.  This is the same answer on a floppy.

## What it is

Three pieces:

| | |
|---|---|
| `src/fdboot.s` | the boot sectors.  The OS loads sectors 1-3 to `$3000` and calls `$3006`; this follows the superblock's boot-file map (+40, the field a SpartaDOS's own boot sectors follow) and reads `G4DOS.SYS` to `$0700`, sector by sector in the map's order.  Sector 1 is the superblock and its fields are untouched; the code is sectors 2 and 3, and sector 1 from +48, where a SpartaDOS keeps boot code too. |
| `src/fdos.s` | `G4DOS.SYS`, 1,890 bytes at `$0700`.  A CIO `D:` handler over SDFS, read-only, and a loader that runs `D1:GEM.COM`.  The OS calls it as DOSINI after the boot and after every RESET, and jumps through DOSVEC to the loader. |
| `tools/atr.py`, `tools/mkfloppy.py` | `Sdfs.boot_gem4xe` writes the header, the boot code and the boot file onto a floppy; `mkfloppy.py` does it for the system disk.  The applications and QED disks keep the message instead: booted alone they say they have no DOS and name the system disk. |

### What gem4xe sees

A DOS 2.  `$0700` is neither SpartaDOS's `S` nor MyDOS's `M`
(src/sys/dos.h), and DRVBYT at `$070A` says D1: and D2:.  So GEMDOS
drops the directories from its paths, and the handler makes that work:
a name is found in the root or in any directory one level down, root
first, and a listing is every file of those, flat.  The system's
`\GEM\` and the applications' `\APPS\` and `\GEM\` look like one drive
each -- which is how the cartridge's D1: looks too.

Two things follow from being DOS 2-shaped:

- **A name that starts with a digit is not listed.**  DOS 2's names
  start with a letter, and `src/sys/dos.c` reads a line that does not
  as noise -- which is what DOS 2's own free-sectors line is.  The only
  such file on the disks is `816.COM`, SpartaDOS X's helper, which has
  no use here.
- **Two files of the same name in different folders are one.**  The
  root's wins, then the first folder's.  The disks have one: `CALC.RSC`
  in both `\APPS\` and `\GEM\`, the same file.

### Reading

Through the OS's SIO routine, never a driver of its own: one loader
that brought its own (exec816) did not work with a SIDE2's or an
Ultimate 1MB's drives.  Two 256-byte buffers, one for a map sector and
one for a data sector, each tagged with its unit and sector, so a file
read straight through costs one SIO call per sector.  Each IOCB keeps
a ten-byte cursor -- map sector, entry, data sector, offset, bytes left
-- and the one in use is kept in hand, so reading one file copies
nothing.  Every OPEN reads the unit's sector 1 again, because the disk
may have been changed.  The code handles 128-byte sectors as well as
256, but only 256 -- every disk gem4xe ships -- is tested.

### Writing

Refused.  An OPEN to write and a PUT answer read-only (`$A7`), and
gem4xe's three write sites -- *Options -> Save desktop*, a control
panel module's settings, a copy -- already put up an alert when a write
fails; `test-fdos` checks Save desktop's.  Writing is step 2: allocation
in SDFS's bitmap, directory entries, map chains.  `tools/atr.py` does
all of it in Python already, which is what a 6502 version would be held
to.

### What it costs

Bank $00 from `$0700` to `$16FF`: the handler and the loader to
`$0E61`, its variables at `$1400`, its two buffers at `$1500`, and
MEMLO at `$1700`.  gem4xe runs under SpartaDOS X with MEMLO at `$1C1D`,
and nothing GEM.COM loads is below `$3000`, so this costs gem4xe
nothing.  The loader stays resident; it is small, and below MEMLO
nothing else wants the room.

When GEM quits there is no DOS to go back to, so DOSVEC is the OS's cold
start and the machine boots the disk again.  RESET runs DOSINI, which
puts the handler back and points DOSVEC at the loader: GEM loads again.

## The gates

- `make test-fdos` (`tests/emu/fdos_boot.py`): the system floppy in D1:
  and the applications floppy in D2:, no SpartaDOS X.  The desk comes
  up, through the Rapidus switch and the reboot that follows it; GEMDOS
  took the DOS for a DOS 2; D1:'s window lists the system flat; Save
  desktop says it could not; D2:'s window lists `EDIT.PRG`, and
  double-clicked it runs.  The same disk built without the DOS fails at
  the boot.
- `make test-boot`, `test-install`, `test-m46`, `test-sdx816`: the same
  floppy under SpartaDOS X, booted, installed and probed as before; and
  the applications floppy booted alone says it has no DOS.
- `tests/host/test_floppy.py`: `G4DOS.SYS` is the superblock's boot
  file and is the link's bytes, the boot sectors are `src/fdboot.s`,
  DOSINI is `$0700`.
