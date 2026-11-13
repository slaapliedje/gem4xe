# Phase 159 -- a bootable disk, and Dfree on double density

Step 5 of `docs/disk-plan.md`, DUP's last missing item: **Write DOS
files**.  DISKUTIL's dialog has a **Bootable** switch on the Label row.
A G4DOS format with it on makes a system disk, which boots to G4DOS's
prompt.

DOS 2 greys the switch.  No DOS 2 or MyDOS DOS file is gem4xe's to put
on a disk; part two of the plan is where a DOS.SYS might come from.

## What makes a disk boot G4DOS

The way `tools/mkfloppy.py` makes the system floppy (`tools/atr.py
boot_gem4xe`):
1. **Two files**, `G4DOS.SYS` and `SHELL.SYS`, copied through GEMDOS
   from the root of a G4DOS disk in another drive.  That is the first
   drive the DOS has with both, not the destination.  With none, an alert
   says so before anything is erased.
2. **The boot**, from that disk: sector 1's header (bytes 0-8: three
   sectors to $3000, DOSINI $0700, JMP $3080), its code from byte 48, and
   sectors 2 and 3.
3. **Sector 1's bytes 40-41**: the map sector of the new disk's own
   `G4DOS.SYS`, found by reading its root directory, which the boot loads
   it by.

Everything else in sector 1 is the new disk's own:
- the geometry;
- the volume name;
- the serial number and random ID;
- the sector size fields (31-37).

`atr.py`'s `boot_from` takes bytes 31-37 from the donor, which only works
between disks of one shape.  Here the donor is double density and a
bootable disk may be single.

## Dfree said 0 on every double-density SDFS disk

The free bytes DISKUTIL showed after a bootable format were 0.  GEMDOS's
`Dfree` asks the file system first (`gd_dfree_fs`): it reads sector 1 and
takes the free count from bytes 13-14.  It read sector 1 at the disk's
sector size, 256 bytes, but sector 1 is 128 bytes on a 256-byte disk,
like sectors 2 and 3.  The read failed.  The fallback parses the DOS's
directory listing, and on G4DOS it found nothing it could read, so the
answer was 0.  G4DOS's own system floppy is a 256-byte disk.

`test-m15g` checked `Dfree` on 128- and 512-byte disks, never on 256.
It now checks D3:, the applications floppy, 256-byte, against the image.
With the old read put back, it reads "0 free of 128".

## Gate

**`test-m63`**, DISKUTIL's gate, makes two disks bootable:
- D3:, double density, G4DOS, label TESTDISK, as before;
- a new D6:, single density.

The appliance floppy in D1: carries `SHELL.SYS` for this, so it is the
donor.  Afterwards each image must hold `G4DOS.SYS` and `SHELL.SYS`,
name the first in sector 1, check clean, and show the free bytes on the
status line that the image has.  Then each is **booted alone**, and must
come to G4DOS's prompt: 400 frames at either density.

| broken on purpose | result |
|---|---|
| sector 1 not naming the new G4DOS.SYS | both images name map 0, and both boots stop at "G4DOS.SYS did not load." |
| Dfree reading sector 1 as 256 bytes (the old code) | test-m15g: 0 free of 128 on D3: |
