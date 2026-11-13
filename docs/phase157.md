# Phase 157 -- DISKUTIL

Step 3 of `docs/disk-plan.md`.  DUP.SYS's Format disk and Duplicate
disk, which the desktop lacked, now exist as a GEM program.  TOS's
desktop does both from one dialog (the Falcon's `DESKDISK.C`, read as a
specification), and DISKUTIL follows its shape:

- **Format or Copy**;
- **From** and **To**, D1: to D8:;
- **Density**: Single, Enhanced, Double, 2 sides;
- **Files**: G4DOS (SDFS, with folders; SpartaDOS X reads it too) or
  DOS 2 (2.0S, 2.5 or MyDOS, by the density);
- **Label**, for an SDFS disk;
- a progress bar, and a status line that says what the destination is
  and what came of it.

It fits the ANTIC screen's 40 columns.  The step 1 calls reach the drive
(`Dgeom`, `Dformat`, `Drwsec`), and the step 2 writers lay the file
system (`src/apps/mkfs.c`).  `\APPS\DISKUTIL.PRG` and `DISKUTIL.RSC`
are on the applications floppy, the CF card and in the release folder.

It is a program of its own and not part of the desktop: the desktop's
code must fit one place in a 512 KB machine's three banks, with about
4 KB to spare.  The desktop will run it with a tail (step 4): `F 2`
formats D2:, `C 1 2` copies D1: to D2:.

## What it does

- **Choosing a destination asks the drive** (`Dgeom`) and offers only
  the densities that drive can make, the disk's current one chosen.  A
  partition says it is not a floppy and offers none.  A drive that is
  not there says so.
- **All eight drives are offered.** The DOS's map says D1: and D2: until
  somebody runs `Dprobe`, which costs a second for every drive that is
  absent, so a drive is asked when it is chosen instead.
- **The default destination** is the first drive that is not the one
  DISKUTIL was run from.  A formatter's default should not be its own
  disk.
- **Format** asks first: "Everything on the disk in D3: will be erased",
  with Cancel as the default.  `Dformat`, then the file system, then
  "D3: formatted, 182784 bytes free".  The free bytes count 125 to a
  single-density DOS 2 sector, whose last three bytes are its link.
- **Copy** asks first too, then reads as much of the source as memory
  holds.  A destination of another shape is formatted to the source's
  first.  On one drive it asks for the other disk at each swap, as many
  times as memory needs; a 1 MB machine holds a whole 360 KB disk.  A
  source that is not a floppy's shape is refused.
- **Errors** are the alerts that say them: write-protected, no drive,
  not a floppy, a density the drive cannot make, bad sectors, not
  enough memory, or a failure part way.

The SDFS volume's serial number and random ID, by which SpartaDOS X
tells one disk from another, come from the clock and the label.

## The label field held seven

The gate's first runs typed TESTDISK and got TESTDIK: the eighth key
replaced the seventh.  The AES makes an editable field's room the length
of the text it loads with, `strlen(te_ptext) + 1`.  TOS's AES does
exactly that (`GEMRSLIB.C`, `fix_tedinfo`), and the resource's text was
"NEWDISK", seven letters.  The text in the file is now eight `@`s, which
GEM shows as empty, and DISKUTIL puts its default label, a free string,
in at start.

## Gate

**`test-m63`** is an appliance floppy, G4DOS starting DISKUTIL in the
desktop's place, plus four disks:

| drive | holds | what is done |
|---|---|---|
| D2: | a partition's shape | the dialog opens on it: not a floppy |
| D3: | double-density SDFS with a file | formatted double, G4DOS, label TESTDISK |
| D4: | blank, double-sided | formatted single, DOS 2 |
| D5: | blank, enhanced | D3: copied onto it |

The dialog is read off the screen.  Its buttons are found where its
labels are: a row's buttons start six columns after its label, three
apart.  Each alert's button is the one below its message.

Afterwards, the emulator's working copies:
- D3: is an SDFS called TESTDISK, empty, 714 free, and checks clean;
- D4: is DOS 2.0S with 707 free;
- D5: was formatted from enhanced to double density, then made the same
  as D3: sector for sector;
- D2: was never written.

| broken on purpose | result |
|---|---|
| a destination of another shape not formatted first | the copy fails part way, and D5: is not D3: |
