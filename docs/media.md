# Storage: what an Atari can boot gem4xe from, and what to build for it

`make dist` produces four media today — three floppies and a 16 MB CF
card image — and the question this answers is whether that is the right
set, given what people actually have attached to an Atari in 2026.

The short of it: **it is, and one card image serves every modern
interface**, because the thing that differs between them is a driver
that lives in the machine, not on the card.

## The four classes of thing people have

**1. An APT interface.**  Ultimate 1MB and Incognito (their PBI BIOS),
SIDE and SIDE2 (a soft driver from the cartridge's own flash, loaded
through SDX's `CAR:` device), SIDE3, IDE Plus 2.0, MyIDE-II with the
APT drivers, and IDEa.  All of them read Konrad Kokoszkiewicz's
**Atari Partition Table**, which is what `build/gem-cf.img` carries.

This is the important part: **the card is the same for all of them.**
The driver that reads it is in the machine's flash or cartridge, so
gem4xe's card needs no `SIDE.SYS`, no driver file, no per-interface
build.  What a tester needs is an SDX (or PBI BIOS) that knows their own
interface, which is what their interface shipped with.

**2. A loader that reads FAT.**  The SIDE3 Loader has full read/write
FAT16/FAT32 on the SD card and runs `.ATR`, `.XEX`, `.CAR` and `.ROM`
from it; AVGCART and The!Cart are the same shape.  These people do not
want a card image at all -- they want the **`.ATR` floppies**, dropped
onto the FAT card they already have, next to their games.  We ship
those.

**3. A SIO device.**  SDrive-MAX, FujiNet, a real 1050.  Also `.ATR`,
also already shipped.  A FujiNet mounts ours over the network the same
way it mounts anything else.

**4. Something from the 1990s.**  MIO and BlackBox are SCSI with their
own partitioning and their own configuration tools; the original MyIDE
has its own scheme that predates APT.  Nothing here targets them, and
nothing needs to: they all also have a floppy drive, and the `.ATR`
disks work.

**Altirra emulates every one of these** -- `blackbox`, `kmkjzide`,
`kmkjzide2`, `mio`, `myide`, `myide2`, `side`, `side2`, `side3`, plus
the Ultimate 1MB -- so any of it can be gated here rather than argued
about.  `make test-cf` currently gates the one this project is for
(U1MB + SIDE), and the others are a device tag away.

## Why one card image is enough, read rather than assumed

Altirra's `ATDecodePartitionTable` (`src/ATIO/source/partitiontable.cpp`)
is the parser real APT disks are read by, and this is what it does
first:

    if (buf[510] == 0x55 && buf[511] == 0xAA) {
        for (int offset = 0x1BE; offset < 0x1FE; offset += 16)
            if (buf[offset + 4] == 0x7F) {
                aptLBA = LE32(&buf[offset + 8]);
                break;
            }
        ...
    }

Two things follow, and the second is the useful one.

- The APT table is found **through the MBR**, by an entry whose type
  byte is `$7F`.  Ours is entry 1, covering the card
  (`tools/apt.py`, `tests/host/test_apt.py` pins it).
- It scans **all four entries** and cares only about the `$7F` one's
  start block.  So **a FAT partition can sit on the same card as the
  APT system** -- one entry for FAT, one for `$7F`, and both drivers
  find what they are looking for.

That last is not built, and the decision is that it does not need to be.
Someone with an APT drive already has one, with their own partitions and
their own idea of where things go; what they want is not a card image
that would overwrite it but **the files, on floppies they can install
from**.  So that is what the two SDFS floppies are: the card's system
partition in two halves, each with an `INSTALL.BAT` that puts it on a
drive.

    the system floppy                           D2: (or wherever)
      GEM>GEM.COM  DESKTOP.PRG  DESKTOP.RSC  ---->  GEM>...
          PREFS.RSC  LANG.RSC  GEM4XE.CFG  816.COM
      AUTOEXEC.BAT, if the drive has none    ---->  AUTOEXEC.BAT
    the applications floppy, gem-apps.atr
      GEM>CLOCK.ACC  CLOCK.RSC  CONTROL.ACC  ---->  GEM>...
          CPANEL.RSC  CALC.ACC  CALC.RSC
      APPS>HELLO.PRG  CALC.PRG  CALC.RSC     ---->  APPS>...
          CLOCK.PRG  CLOCK.RSC

At the SpartaDOS X prompt -- quit GEM to get there -- on the drive the
floppy is in:

    -INSTALL D2:

once with each floppy.  One batch a disk rather than one that asks for
the next, because SpartaDOS X warns against changing the disk a batch
file is running from.  The system's gives the drive an `AUTOEXEC.BAT`
holding `CD >GEM` and `GEM` when it has none, and leaves one that is
there alone and says what it wants; installing a newer gem4xe is the
same again, over the old.  `make test-install` does exactly that under
SpartaDOS X 4.50 -- a blank drive, both floppies, the system a second
time over the first -- and then cold-starts the drive into the desktop
with all three desk accessories loaded beside it.  The gate counts the
processes, so that number is the media's to change: four is the desktop
and the three the applications floppy installed.

**Why two floppies and not one.**  Until phase 42 each SpartaDOS floppy
carried the applications and the accessories as well -- one accessory
then, and three of them since phase 47.  The rest of GEMDOS took the
smallest disk, the DOS 2 floppy, under its floor of free
sectors (`docs/phase42.md`), and the answer was not to squeeze it: a
floppy is where gem4xe starts, not where it lives, so every floppy became
the system and nothing else, and the rest went onto a floppy of its own
-- which is also what somebody running from floppies wants in a second
drive.

## The floppies the release can carry

`gem-boot.atr` boots a DOS 2, which is not gem4xe's to give away, so the
public release (`make release`) does not carry it.  A SpartaDOS 3.2
floppy, `gem-sp.atr`, was the same and was retired after phase 42: the
installer is SpartaDOS X's, and a machine with a drive to install onto
has SpartaDOS X in its flash, so a disk that boots 3.2 was one more thing
to build and gate for nobody.  **`gem-sdx.atr`** and
**`gem-apps.atr`** (`tools/mkfloppy.py`) are the two that can travel:
double-sided double-density SDFS disks, 1440 sectors of 256 bytes, with
**no DOS**, their boot sectors the blank disk's stub.  The first is the
system -- the card's `\GEM\` without the accessories, the card's
`AUTOEXEC.BAT` and `INSTALL.BAT` -- and the second the applications and
the three accessories, with an `INSTALL.BAT` of its own and nothing that
boots.

The system floppy boots under SpartaDOS X, which is the one DOS that
lives in the machine rather than on the disk: a cartridge, or an
Ultimate 1MB with it in flash.  SDX comes up, changes to D1: and runs the
disk's `AUTOEXEC.BAT`, and that is GEM; the loader switches the Rapidus
as it does from the other two.  `make test-boot` boots it under the
`[spartados].sdx_cart` fixture, nothing typed, compares the desk with the
model as it does the others, and reads the applications floppy file by
file.

Both stay double-sided, which the system alone -- about 150 KB -- no
longer needs, so that the pair is one geometry.  Every SIO emulator,
every FAT loader and an XF551 read it.

The evidence for the FAT-beside-APT card stays written down because it
is the obvious thing to build if someone asks for a single card a PC can
also drop files onto, and because the evidence for it being possible is
here rather than in a forum thread.

## So: which medium for whom

| If you have | Use | Why |
|---|---|---|
| U1MB / Incognito, SIDE, SIDE2, SIDE3, IDE Plus 2.0, MyIDE-II | `disks/gem-cf.img` written to a card | APT; the system installs to `\GEM\`, applications to `\APPS\` |
| An APT drive you have already partitioned | `disks/gem-sdx.atr` and `disks/gem-apps.atr`, and `-INSTALL` from each | the floppies are the card in two halves; nothing of yours is touched |
| SIDE3 / AVGCART / any FAT loader, with SpartaDOS X in the machine | `disks/gem-sdx.atr` on the card you have, `disks/gem-apps.atr` as a second drive | the loader mounts them; SDX boots the first; nothing to install -- and they are the floppies in the public release |
| SIDE3 / AVGCART / any FAT loader, without | `disks/gem-boot.atr` on the card you have | the loader mounts it and it boots its own DOS 2: the system, nothing else |
| SDrive-MAX, FujiNet, a real drive | `disks/gem-sdx.atr` with `disks/gem-apps.atr` in a second drive (SpartaDOS X in the machine), or `disks/gem-boot.atr` (DOS 2) | plain floppy images |
| A DOS you already like | `system/` -- the loose files | put them where you want; give the disk a start-up that runs `GEM` |
| MIO, BlackBox, original MyIDE | the floppies | their partitioning is their own; nothing here writes it |

## Writing the card image, and the warning that goes with it

`gem-cf.img` is a **whole-card image**, 16 MB of 512-byte blocks.
Writing it with `dd` or a disk imager **replaces everything on the
card**, and a card larger than 16 MB keeps only the first 16 MB in the
partition table -- the rest is unallocated until it is repartitioned
with the APT tools.

So it is for a card you are giving to gem4xe, not for the card with
your collection on it.  For that one, the floppies.

    dd if=disks/gem-cf.img of=/dev/sdX bs=1M conv=fsync    # sdX, not sdX1

## What would change if this grows

Two things are cheap and neither is needed yet:

- **A FAT partition beside the APT one**, as above: a card a PC can
  read and a SIDE3 Loader can browse, with the installed system behind
  it.  It wants a small FAT16 writer in `tools/`, in the shape of the
  SDFS and DOS 2 writers already in `tools/atr.py`.
- **A size other than 16 MB.**  `tools/mkcf.py` fixes the geometry; a
  knob is a few lines.  16 MB was chosen because it is the smallest
  thing that comfortably holds two 8 MB partitions, and because a
  16 MB file is a reasonable thing to put in a release.

Two more are wanted and are not built either:

- **A minimal install.**  The system is about 150 KB and nearly all of
  it is `GEM.COM`'s far image; what a small partition, a single-density
  floppy or a machine short of room wants is that image and the desktop,
  without `LANG.RSC`'s spare languages, without `\APPS\` and without the
  accessory, and a `DESKTOP.INF` that does not expect them.
  `tools/mkcf.py`'s tables are already the seam -- a third table beside
  `SYSTEM` and `APPS` -- so the work is deciding what comes out, not
  where to put the knob.
- **A slot in flash, rather than a file a DOS loads.**  Ultimate 1MB
  holds selectable OS images in its flash and so does Antonia 2, and the
  question worth answering is whether gem4xe can be one of them.  It is
  a question and not a plan: a slot holds a kernel that answers the
  machine's vectors out of `$C000-$FFFF`, while gem4xe is a program a
  DOS loads into far banks it probes for at run time, so a slot would
  hold a loader that finds the rest rather than the system itself --
  which is close to what `src/farload.s` already is.  The prior art to
  read first is flashjazzcat's, which boots its GUI from a flash
  cartridge on this same class of machine (`PLAN.md`, *Prior art*).
  What it would buy is a machine that comes up in the desktop with no
  disk at all, and what it costs is a second way in to keep working.
