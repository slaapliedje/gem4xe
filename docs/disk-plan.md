# Plan: a window-based DUP

Asked for (2026-11-12): "a window-based DUP.SYS" -- someone's phrase.
DUP.SYS is the menu half of Atari DOS 2 and MyDOS: A. Disk directory,
C. Copy file, D. Delete, E. Rename, F/G. Lock and unlock, H. Write DOS
files, I. Format disk, J. Duplicate disk, and the 8-bit chores (binary
load and save, run at an address, MEM.SAV, run the cartridge).  Two
readings, both wanted, in this order:

1. **DUP's work done the GEM way.** The desktop already does the
   directory, copy, delete, rename and lock (Show info's read-only box).
   What it lacks is Format, Duplicate disk and Write DOS files.  This
   plan is about those three.
2. **The real DUP.SYS in a window**, as TOSWIN hosts a text program on
   the ST.  A plan of its own, after this one; notes at the end.

## How TOS did it

TOS's desktop has one dialog for both jobs (the Falcon's `DESKDISK.C`,
read as a specification only): `fc_start(source, op)`, opened by File ->
Format... and by dragging floppy A onto floppy B.  Copy or Format, the
source and destination drives, the density, a label, a progress bar, and
the bytes free at the end.  Underneath are the XBIOS floppy calls
(`Flopfmt`, `Floprd`, `Flopwr`).  EmuTOS's desktop (`desksupp.c`
`do_format`, GPL-2) has Format only; a disk dropped on a disk copies its
files.

## Where it goes

**Not in the desktop.** The desktop's code must fit one place in a
512 KB machine's three banks, and 1.4 KB of it broke that boot in phase
152; the margin is about 4 KB.  So the dialog is a program of its own,
**DISKUTIL**, in `\GEM\`.  The desktop runs it with arguments, the way
Show's Return runs EDIT.  Run on its own, it opens on Format.

**Underneath, gem4xe's own calls**, not an XBIOS.  `Flopfmt` formats one
track with a chosen skew; an Atari 8-bit drive formats the whole disk to
its own layout in one command, so there is nothing honest to map
`Flopfmt` onto.  The new calls go in gem4xe's GEMDOS range after Dcaps
(0x1F7).

## Steps

### 1. The drive's calls (kernel) -- done, phase 155

- **SIO**, beside `dsk_read`/`dsk_write`/`dsk_percom` (`src/sys/cio.c`):
  - format: `!` ($21), and `"` ($22) for a 1050's enhanced density;
  - PERCOM write: `O` ($4F), to choose the density before `!`;
  - the bad sectors a format answers with, a list ended by $FFFF;
  - the drive's own format timeout, from its status reply, as DOS 2 uses it.
- **`Dgeom(drive, buf)`**: what the drive is now, and what it can be made:
  - sector size and count, from its PERCOM block, or from its status
    where it has none (an 810, a stock 1050);
  - whether it is a floppy at all.  A hard disk partition reached
    through a PBI device answers SIOV too, and must never be formatted
    by mistake.
- **`Dformat(drive, density, badbuf)`**: the density chosen, the disk
  formatted, the bad sectors returned, and the DOS told the disk changed:
  - G4DOS: `sd_forget`;
  - SpartaDOS X: a new disk's random number tells it;
  - DOS 2 and MyDOS: they read the VTOC again.
- **`Drwsec(drive, rw, sector, count, buf)`**: whole sectors to or from a
  FAR buffer, bounced through bank $00 where the OS can reach them.
- **Gate**: D2: formatted in every density the emulator's drive modes
  allow -- `810` single, `1050` enhanced, `generic` double and
  double-sided -- checked by `tools/atr.py`, bad list included.  Refused
  on a partition.  Altirra's drive emulation takes `!`, `"` and `O`
  (`disk.cpp`); whether the SIO patch every gate runs accelerates them is
  checked first: no gate drives the real serial bus.

### 2. The file systems (the program's, host-tested)

A C library the program links and `tests/host` builds with gcc:
- **SDFS**: G4DOS's and SpartaDOS's, with folders, on 128-, 256- and
  512-byte sectors (`tools/atr.py Sdfs.format`, which follows Altirra's
  `diskfssdx2.cpp InitNew`);
- **DOS 2**: 2.0S on single density, 2.5's VTOC2 on enhanced, MyDOS's on
  double and double-sided (`tools/atr.py`'s DOS 2 `format`).

Three witnesses, not two, because a model and a target can agree and both be wrong:
- the C output diffed against `atr.py`'s;
- `atr.py`'s checker;
- and in the emulator, the DOS that owns the format reading the disk and
  writing to it: G4DOS and SpartaDOS X for SDFS, MyDOS and DOS 2.5 for
  DOS 2.

### 3. DISKUTIL

One dialog, TOS's shape:
- **Format or Copy**;
- **drives**: the source for a copy, the destination for both;
- **density**: single, enhanced, double, double-sided, each greyed where
  `Dgeom` says the drive cannot;
- **file system**: G4DOS/SpartaDOS (the default) or DOS 2;
- **a label**;
- **a progress bar**, and at the end the bytes free.

Copy disk:
- the destination is formatted to the source's geometry when it differs;
- on one drive, the whole disk is read into far memory and you are asked
  once to swap disks. A 360 KB disk fits in a 1 MB machine.

An alert before anything is erased: "Everything on D2: will be erased."

### 4. The desktop

- **File -> Format disk...** runs DISKUTIL on the selected drive, or on
  D1: when none is selected.
- **A floppy dropped on a floppy** asks "Copy disk D1: to D2:?", TOS's
  rule, and runs it.  A partition dropped on a floppy, or any drop with a
  window as its source, copies files as now.
- Both items grey where DISKUTIL is not on the disk; the DOS 2 floppy has
  17 sectors free, so it may not carry it.
- Windows open on a drive that changed are read again.

### 5. Write DOS files

DUP's H: a formatted SDFS disk made bootable with G4DOS.SYS and
SHELL.SYS, which makes it a system disk -- the boot sectors
`tools/atr.py` already writes for `gem-sys.atr`.

## Part two, for later: DUP.SYS in a window

- A text window that hosts an 8-bit program, as TOSWIN does on the ST:
  E: and K: through the window, the program run in bank $00.
- The program: DUP.SYS from the OSS DOS 2.5 sources (on AtariWiki,
  licence unknown), or MyDOS 4.5's (source published; free to
  distribute provided the source goes with any binary).  DUP needs its
  own DOS.SYS underneath, which G4DOS is not.  Settling which one, and
  its licence, is the first step of that plan.
