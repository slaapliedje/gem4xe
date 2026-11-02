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
needs a DOS only to READ its files to start, and reading is the small
half of a DOS.  This is the same answer on a floppy -- and since
2026-11-02 the other half too, so that what gem4xe saves stays saved
(*Writing*, below).

## What it is

Three pieces:

| | |
|---|---|
| `src/fdboot.s` | the boot sectors.  The OS loads sectors 1-3 to `$3000` and calls `$3006`; this follows the superblock's boot-file map (+40, the field a SpartaDOS's own boot sectors follow) and reads `G4DOS.SYS` to `$0700`, sector by sector in the map's order.  Sector 1 is the superblock and its fields are untouched; the code is sectors 2 and 3, and sector 1 from +48, where a SpartaDOS keeps boot code too. |
| `src/fdos.s` | `G4DOS.SYS`, 4,769 bytes at `$0700`.  A CIO `D:` handler over SDFS, reading and writing, a loader that runs `D1:GEM.COM`, and a sector entry for gem4xe's own SDFS engine (*Folders*, below).  The OS calls it as DOSINI after the boot and after every RESET, and jumps through DOSVEC to the loader. |
| `tools/atr.py`, `tools/mkfloppy.py` | `Sdfs.boot_gem4xe` writes the header, the boot code and the boot file onto a floppy; `mkfloppy.py` does it for the system disk.  The applications and QED disks keep the message instead: booted alone they say they have no DOS and name the system disk. |

### What a program sees

Through G4DOS's own handler -- a program run without GEM, and gem4xe's
own start-up reads before GEMDOS is up -- a DOS 2's shape.  A name is
found in the root or in any directory one level down, root first, and a
listing is every file of those, flat.  The system's `\GEM\` and the
applications' `\APPS\` and `\GEM\` look like one drive each -- which is
how the cartridge's D1: looks too.  Under GEM, folders (*Folders*,
below).

Two things follow from the flat view:

- **A name that starts with a digit is not listed** in a line listing.
  DOS 2's names start with a letter, and `src/sys/dos.c` reads a line
  that does not as noise -- which is what DOS 2's own free-sectors line
  is.  The only such file on the disks is `816.COM`, SpartaDOS X's
  helper, which has no use here.
- **Two files of the same name in different folders are one** to a bare
  name.  The root's wins, then the first folder's.  The disks have one:
  `CALC.RSC` in both `\APPS\` and `\GEM\`, the same file.

### Folders

From `gemdos_init` on, gem4xe does not hand G4DOS's disks to G4DOS's
handler at all.  Its own SDFS engine (`src/sys/sdfs.c`, the C that
`test-sdfs` runs on the host) serves CIO's `D:` for everything in gem4xe
that opens a file -- GEMDOS, the file selector, the shell, the loaders
-- with folders to any depth, and G4DOS only reads and writes sectors
for it, through an entry in its header:

| | |
|---|---|
| `$0706` | `G4`: G4DOS is there, and `src/sys/dos.c` says `DOS_G4DOS` |
| `$0708` | the unit |
| `$0709` | bit 0 write, bit 7 a 128-byte sector; bit 6 alone asks where G4DOS's data buffer is, answered in A and X |
| `$070B` | `JMP fd_xsec` |
| `$070E` | the sector |

`fd_xsec` reads or writes through the data buffer and keeps G4DOS's
tags true, so the handler and the engine never disagree about what a
buffer holds.  A bare name -- no folder in it -- still means what it
means to the handler (the root, then one level down), because that is
how gem4xe finds its own files.  [sdfs-plan.md](sdfs-plan.md) has the
rest: why it is at CIO's level, what is left.

### BASIC

Off, always.  `G4DOS.SYS`'s DOSINI banks an XL's BASIC out (PORTB bit 1)
and sets `BASICF`, so the OS finds no cartridge and goes through DOSVEC to
the loader, and a warm start keeps it out.  Without that, the machine
came up at BASIC's `READY` whenever OPTION was not held at a cold start --
and gem4xe's loader makes one: switching a Rapidus to its 65C816 is a
cold start, long after anybody let go of OPTION.  `test-fdos` found it
when a few frames' difference put that second cold start outside the
window in which the emulator holds OPTION for `--nobasic`.

### Reading

Through the OS's SIO routine, never a driver of its own: one loader
that brought its own (exec816) did not work with a SIDE2's or an
Ultimate 1MB's drives.  Two 256-byte buffers, one for a map sector and
one for a data sector, each tagged with its unit and sector, so a file
read straight through costs one SIO call per sector.  Each IOCB keeps
a ten-byte cursor -- map sector, entry, data sector, offset, bytes left
-- and the one in use is kept in hand, so reading one file copies
nothing.  Every OPEN reads the unit's sector 1 again, because the disk
may have been changed.  128-byte sectors and 256 both work, and
`test-fdosw` runs on both.

GET CHARACTERS is a burst (`fd_burst`), as DOS 2's is: all but the last
of the bytes CIO still wants go straight into the caller's buffer, CIO's
pointer and count moved on by as many -- a sector wanted whole is read
by SIO straight into it, anything less copied out of the data buffer --
and the last byte goes back in A for CIO to store.  A byte at a time,
G4DOS was two thirds of the boot and read GEM.COM at 74 bytes a frame;
in bursts it reads 329, faster than DOS 2's 292, and the system floppy
reaches the desktop in 17.6 seconds rather than 45.2 (`make bench-boot`).

### Writing

Since 2026-11-02.  *Save desktop*, a control panel module's settings and
a copy are written, and stay written:

- **OPEN to write** (aux1 8) empties a file of that name in the **root**,
  or makes one there.  The root is where the flat view looks first, so
  a file saved over one found a folder down -- `DESKTOP.INF` beside
  `GEM4XE.CFG` in `\GEM\` -- shadows it from then on.  Append (9) and
  update (12) answer `$92`; a second file open to write at once, `$A1`;
  a wildcard or no name, `$A5`; a locked file or a directory, `$A7`.
- **PUT** is a burst too, the other way: CIO's loop loads the byte at
  `ICBALZ`, calls PUT, then steps and counts, so `fd_put` takes as many
  of the bytes after it as fit the sector and moves CIO on by as many.
  PUT RECORD goes a byte at a time, because it stops at the EOL.
- **CLOSE** writes the last data sector, the last map page, the length
  into the entry, the bitmap sector in hand, and the superblock's free
  count -- in that order.
- **XIO 33** deletes and **XIO 32** renames (`D1:OLD.EXT,NEW.EXT`),
  wherever the flat view finds the name; a new name that is there
  already is refused.

What is written is SDFS as `tools/atr.py` writes it, the model the 6502
is held to: the first free sector at or after a hint, a map page of 126
references (62 on 128-byte sectors) linked both ways, a directory grown
a zeroed sector at a time with its header's length.  The order on the
disk is chosen so that a RESET at any point leaves a disk SpartaDOS will
read: a file's first map page and its entry, length 0, go down at OPEN
with the bitmap; its data sectors are only free sectors with something
in them until CLOSE writes the map that names them.

Its sectors are the read side's two buffers -- a directory is edited
through them, and their tags stay true -- and three of its own: the
data and the map page of the file being written, and a bitmap sector.

### What it costs

Bank $00 from `$0700` to `$1FFF`, MEMLO `$2000`: the handler, the
loader and the sector entry, 4,769 bytes; their variables, 347; five
sector buffers at `$1B00`.  That is the ceiling.  gem4xe's direct page
is `$2000` (`src/gem4xe.scm`) and nothing GEM.COM loads is below
`$3000`, so it still costs gem4xe nothing -- but the three memories in
`src/fdos.scm` are full to within four bytes, which is why the folders are
gem4xe's and not G4DOS's.  For scale: a
DOS 2.5 leaves MEMLO at `$1CFC`, SpartaDOS X at `$1C1D`, a SpartaDOS 3.2
near `$2000`.

When GEM quits there is no DOS to go back to, so DOSVEC is the OS's cold
start and the machine boots the disk again.  RESET runs DOSINI, which
puts the handler back and points DOSVEC at the loader: GEM loads again.

## The gates

- `make test-fdos` (`tests/emu/fdos_boot.py`): the system floppy in D1:
  and the applications floppy in D2:, no SpartaDOS X.  The desk comes
  up, through the Rapidus switch and the reboot that follows it; GEMDOS
  knows G4DOS, with folders; D1:'s window is the root, and its `GEM`
  folder opened lists the system; Save desktop saves, with no alert, and
  afterwards the emulator's working copy of the disk has `DESKTOP.INF`
  in its root and passes `atr.Sdfs.check()`; D2:'s `APPS` folder opened
  lists `EDIT.PRG`, and double-clicked it runs.  The same disk built
  without the DOS fails at the boot.
- `make test-m15g` (`tests/emu/m15_gdos.py --g4dos`): GEMDOS's own gate
  on a G4DOS disk, the conformance runner as `GEM.COM` -- every call
  against the disk image, down the tree, writes included -- and the
  emulator's working copy checked with `atr.Sdfs.check()` afterwards.
- `make test-sdfs` (`tests/host/test_sdfs.py`): the engine on the host.
- `make test-fdosw` (`tests/emu/fdos_write.py`): the write side on its
  own, through CIO.  A disk made by `tools/atr.py` holds G4DOS and, as
  `GEM.COM`, `tests/emu/fdwtest.s`, a plain 6502 program the loader runs
  in GEM's place: files made with PUT CHARACTERS and PUT RECORD, one of
  39,000 bytes over several map pages, one emptied and written again, a
  rename, a delete out of a folder, the refusals, and the files read
  back.  Every status is checked, then the disk itself: each file's
  bytes, and `atr.Sdfs.check()` -- every chain's sectors used once and
  marked used, every other sector free, the free count the bitmap's,
  which was made to fail on damaged copies before it was believed.
  Twice, on 256-byte sectors and on 128-byte ones.
- `make test-boot`, `test-install`, `test-m46`, `test-sdx816`: the same
  floppy under SpartaDOS X, booted, installed and probed as before; and
  the applications floppy booted alone says it has no DOS.
- `tests/host/test_floppy.py`: `G4DOS.SYS` is the superblock's boot
  file and is the link's bytes, the boot sectors are `src/fdboot.s`,
  DOSINI is `$0700`.
