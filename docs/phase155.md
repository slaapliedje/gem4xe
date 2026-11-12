# Phase 155 -- the drive itself

Step 1 of `docs/disk-plan.md`, the window-based DUP: what a program needs
to format a disk and copy one whole.  Nothing a program can call reached a
drive's sectors before this.  GEMDOS answers in files and folders,
through the DOS, and gem4xe has no BIOS or XBIOS.  Three calls of
gem4xe's own now go to the drive through SIO, past whatever DOS runs:

| call | does |
|---|---|
| `Dgeom` (0x1F8) | what the drive is: the disk's sector size and count, a floppy or not, whether it takes a geometry, write-protected, which densities it can be asked for, and its PERCOM block |
| `Dformat` (0x1F9) | the disk formatted at a density: single (720 x 128), enhanced (1040 x 128), double (720 x 256), double-sided (1440 x 256), or as it is; the drive's list of bad sectors back |
| `Drwsec` (0x1FA) | whole sectors read into a far buffer or written from one |

They answer with the BIOS's errors, as TOS's floppy calls do: EDRVNR when
nothing answered, EWRPRO, EUNCMD for a density the drive cannot make,
EUNDEV for a drive that is not a floppy, ESECNF for a sector past the end,
EREADF and EWRITF.  A drive is D1: to D8: and never 0 for "the current
one", unlike every other GEMDOS call, because these erase disks.

## Why not the XBIOS

TOS formats with `Flopfmt`: one track, a skew table and a fill value.  An
Atari 8-bit drive formats the whole disk in one command, to a layout of
its own, so there is nothing honest to map `Flopfmt` onto.  `Floprd` and
`Flopwr` address sectors by track and side, which SIO never sees either.
The three calls take the drive's own terms instead: densities and sector
numbers.

## Densities

A drive that tells its geometry (`N`, the PERCOM block) is told the one to
make (`O`), then formatted (`!`).  That covers XF551s, US Doublers, Indus
GTs, FujiNets and the emulators.  Enhanced density is the 1050's own
command (`"`) on every drive.  An 810 or a stock 1050 takes no geometry:
`!` makes single density there, and double is refused before anything is
sent.  The format's timeout is the drive's own, from byte 2 of its status
reply, as DOS 2 takes it; the sector calls keep the OS's.

## A floppy, and not a partition

A hard disk's partition reached through a PBI device answers SIOV like a
floppy, and formatting one by mistake would be the worst thing this code
could do.  `Dgeom` calls a drive a floppy only when its geometry is a
floppy's: 35 to 80 tracks, at most 26 sectors a track, at most 256 bytes a
sector, one side or two.  A partition, or a FujiNet's big image, says one
track of thousands (Altirra's for a 4,096-sector image: `01 01 10 00 ...`).
A drive that tells no geometry is taken for an 810 or a 1050.  **On real
hardware, unverified:** whether a U1MB or SIDE 2 PBI BIOS answers `N` for
its partitions.  If one does not, its partition would be taken for an
810.  The next step's program shows the drive's geometry and asks before
it erases anything, but this wants checking on the rig.

## Telling G4DOS

After a format or a write, G4DOS's folders forget the disk (`sdc_forget`):
its cached sectors, the files open on it and its sector size.  The engine
already looked at a disk again at every open: it reads sector 1 and
forgets a disk that is not the one it had.  So a path named after the
format was always safe.  A handle opened before it was not: its next write
and its close never look, and went where the old disk had room, which is
the new disk's root and bitmap.  Without `sdc_forget`, the gate's
reformatted disk came back listing OLD.TXT and OPEN.TXT.  With it, the old
handle answers EIHNDL.

SpartaDOS X keeps its own buffers.  A disk with a new random number in its
superblock is a disk it has not seen, which the next step's SDFS writer
must give it.  DOS 2 and MyDOS read the VTOC again.

## Gate

**`test-m62`**: the runner on G4DOS, scratch disks in D2: and D3:, the
calls made through the runner as test-m15 makes GEMDOS's.  The emulator's
drive is switched between kinds while the machine runs (the bridge's
`CONFIG diskemu`):
- generic: every density made, each read back by `Dgeom`;
- 810: enhanced and double refused;
- 1050: enhanced made, double refused.

The edges are refused: drive 0 and 9, an empty drive, density 7, and the
partition-shaped D3:, whose image is untouched afterwards.  Sectors are
written and read across a 256-byte disk's 128-byte boot sectors, and one
past the end is ESECNF.  A file is left open across a format.  The new
disk, laid with an SDFS through `Drwsec`, lists empty, takes a file and
checks clean.

| broken on purpose | result |
|---|---|
| `sdc_forget` doing nothing | the old handle's write succeeds, and the new disk lists OLD.TXT and OPEN.TXT |
| every drive a floppy | D3:, the partition's shape, is formatted, and its image changes |

A first version of the forgetting check formatted a disk and listed it.
It passed with `sdc_forget` taken out, because the open re-check already
caught that case.  The open handle is the case only `sdc_forget` covers.

## Room

The DOS 2 floppy has 13 sectors free, against 17 at 0.15; its floor is 6.
