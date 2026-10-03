# Phase 106 -- MyDOS: the disk was broken, not the quit

Item 8 of `roadmap-0.12.md`: "MyDOS 4.50: Quit and DOS commands stall on
the way back to MyDOS".  0.9.1's notes said more: "Any AUTORUN program
does this on MyDOS 4.50T, even without gem4xe loaded."

## Finding it

`build/gem-mydos.atr`, File -> Quit: the screen went blank and stayed
blank.  The CPU was in the OS's SIO wait at `$EB16-$EB24`, MyDOS asking
drive after drive for its status, a timeout each.

The same fixture swept the same way with a one-byte AUTORUN.SYS (`RTS`)
stalled the same way, and so did one with **no** AUTORUN.SYS at all.
The fixture as it comes, untouched, booted to MyDOS's menu in 100
frames.  So the 0.9.1 note was right about the symptom and wrong about
why: the disks it was tried on were all made by `tools/mkdisk.py`.

Read back, the swept disk's `DUP.SYS` was 1,531 bytes; the fixture's is
6,638.

## The cause: extended links

The fixture is a 1,440-sector double-density MyDOS volume.  Over 1,023
sectors MyDOS chains a file by **extended links**: a sector's link is
the next sector's whole number, high byte first, with no file number in
it, and the file carries `$04` in its directory flag.  The volume says
so with a VTOC code above 2; this one's is 3.  (Altirra's
`diskfsdos2.cpp`: `WriteFile`'s `extFile`, `GetNextSector`.)

`tools/atr.py`'s `Dos2` read every link as DOS 2's: a file number in the
top six bits, the sector in the low ten.  For a link to sector 1,030
(`$0406`) that is "file 1, sector 6".  Every one of the fixture's files
is `$46` or `$66`, extended.  `--sweep` deleted them by following their
chains that way, freed sectors that were `DOS.SYS`'s and `DUP.SYS`'s
(README.1ST's chain alone ran into DUP.SYS's sectors 28-32), and wrote
AUTORUN.SYS over them.  It also left about 340 sectors of the deleted
files allocated: the disk had 479 free where it has 822 now.

Booting never reads `DUP.SYS`: MyDOS runs AUTORUN.SYS and gem4xe came
up, which is why `make test-mydos` stayed green.  Quit leaves through
`DOSVEC`, MyDOS loads `DUP.SYS`, and ran what was left of it.

## The fix

`Dos2` knows extended links (`tools/atr.py`):

- `ext` is set for a MyDOS volume whose VTOC code is above 2;
- `read` and `delete` follow a file's chain as its flag says: extended
  when it has `$04`;
- `add_file` writes extended links on such a volume and sets `$04`;
- a VTOC code above 3 (a bitmap over more than one sector) is refused
  rather than misread.

Nothing in gem4xe changed.  No product disk is MyDOS (its licence is
unchecked), so no shipped disk was ever broken by this.

## Proof

- **`tests/host/test_atr.py`, `MyDOSExtendedLinks` (new).**  A 1,440-sector
  volume laid out by hand from Altirra's rules, not by `Dos2`, so the
  writer is not marking its own homework.  File A runs 4 -> 1030 -> 5,
  so a DOS 2 reading of its middle link lands on B's first sector.
  - The files read back.
  - Deleting A frees A's three sectors and none of B's.
  - A new file on the volume gets `$04` and a link above 1,023.
  - The fixture itself, swept as the build sweeps it, keeps `DOS.SYS`
    and `DUP.SYS` byte for byte.
  - All four fail with the old `atr.py`.
- **`make test-mydos`** now holds the disk's `DOS.SYS` and `DUP.SYS` to
  the fixture's.  After the desk it quits with Ctrl+Q.  MyDOS's menu
  must come up (in 25 frames).  Then it gives MyDOS a command, A and
  RETURN, its directory, which must list `AUTORUN.SYS`.  On a disk built
  with the old `atr.py` it fails twice: "DUP.SYS on the disk is 7084
  bytes that are not the fixture's 6638" and "MyDOS's menu never came
  up".
- `make test-m37`, whose overlay floppy is swept from the same fixture,
  passes.

## Not shown

- Whether a MyDOS user's own disk stalls on real hardware.  Such a disk
  was made by MyDOS, not by `mkdisk.py`, so this cause cannot apply to
  it.  If a tester still sees a stall there, it is a different fault,
  and this gate is the place to reproduce it.
- On the way, an apparent dead keyboard after Quit, on DOS 2 as well,
  was the probe's own last RETURN redrawing DUP's menu over the
  directory.  The keyboard works on both.
