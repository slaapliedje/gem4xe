# Phase 160 -- DUP, DOS 2's disk menu in a GEM window

Part two of `docs/disk-plan.md`.  The choice was our own DUP rather than
the real DUP.SYS: DUP's lettered menu in a GEM window, done by gem4xe,
with no licence question and working on every DOS.  `\APPS\DUP.PRG` is
a 40-column window of text.  It prints the menu; a letter asks DUP's
question; the answer is typed; what came of it is printed, then SELECT
ITEM OR RETURN FOR MENU.

| item | does |
|---|---|
| A. Disk directory | a search spec (D1:*.* by default): `*` for a locked file, the name in columns 1-8, its extension in 9-11, its sectors from 13 (DIR for a folder), the free sectors last |
| C. Copy file | from, to -- a file, or a spec of them onto a drive; COPYING---D2:A.TXT for each |
| D. Delete file(s) | DELETE FILE D2:E.TXT? for each, Y or N; /N for none asked |
| E. Rename file | old, new, in the old one's folder |
| F. Lock file, G. Unlock file | the read-only bit |
| H. Write DOS files | TYPE "Y" first; G4DOS onto an SDFS disk, from a G4DOS disk in another drive; under DOS 2 or MyDOS, that DOS's own DUP writes its files |
| I. Format disk | TYPE "Y" first; at the density the drive has -- an SDFS where the DOS has folders, DOS 2 where it has not |
| J. Duplicate disk | source, destination; INSERT BOTH DISKS, or on one drive SOURCE and DESTINATION in turn |
| O. Duplicate file | one file, read whole, the other disk put in, written |
| P. Format single | as I, at single density |
| B, K, L, M, N | the cartridge, binary save and load, run at an address, MEM.SAV: NOT UNDER GEM, WHICH HOLDS THE MEMORY |

A person who knows DUP finds the same letters asking the same things.
The banner is gem4xe's ("GEM4XE DUP 0.15, DOS 2'S DISK MENU, FOR GEM"),
not Atari's.  Errors are DUP's numbers, because a DUP user knows those:

| number | means |
|---|---|
| 170 | file not found |
| 167 | locked |
| 144 | the disk refused |
| 138 | no answer |
| 160 | no such drive |
| 173 | bad sectors at format time |

Every line DUP prints is in `DUP.RSC` (`tools/duprsc.py`).

## Shared with DISKUTIL

Formatting with a file system, copying a disk and making one bootable
moved out of `diskutil.c` into `src/apps/diskops.c`, which both programs
link (part two, step 1).  The program says what is happening through
hooks: DISKUTIL with its status line and alerts, DUP with lines of text.
`dk_bootable` is new: G4DOS onto a disk that is already formatted, which
is DUP's H.  DISKUTIL's gates (`test-m63`, `test-m64`) passed unchanged
after the move.

## What it met

`Fattrib` with `wflag` 0 is refused: gem4xe answers a search for the
attributes, not a read (`docs/differences.md`).  DUP's first F read the
attributes before setting the bit, and printed ERROR- 255.  It sets the
bit now, which is all gem4xe's Fattrib does.

## Gate

**`test-m65`**: an appliance floppy starting DUP, with `SHELL.SYS` on it
for H to write, and four disks.  Every item is typed, and what it prints
is read off the screen:
- A lists D2:;
- C copies, E renames, F locks (A shows the star), G unlocks;
- D deletes after its question;
- I formats D3: and P formats D4:, each asked first;
- H writes DOS to D3:, J duplicates D3: onto D5:, B refuses.

Then the disks:
- D2: is as it began;
- D3: holds `G4DOS.SYS` and `SHELL.SYS`, checks clean, and boots alone to
  G4DOS's prompt;
- D4: is single density;
- D5: is D3: sector for sector.

| broken on purpose | result |
|---|---|
| Y at DELETE FILE not deleting | D2: still holds E.TXT, and the gate says so |
