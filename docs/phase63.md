# Phase 63 -- Show info on a drive

The second of item 4's small desktop items (`docs/roadmap-0.9.md`).
File -> Show info (^I) with a drive selected on the desk puts up the
TOS desktop's disk information: the drive's name, how many folders and
files are on it and the bytes they hold, and how many bytes are free.

The counts are the walk a delete counts with before it asks (`OP_COUNT`,
`src/desk/deskfun.c`), over the drive's root; the free bytes are what
GEMDOS's `Dfree` answers -- the DOS's own free-sector count -- and a DOS
that cannot say leaves the line empty rather than making a number up.
The dialog lives in `PREFS.RSC` with the others that are only up for a
moment.

One ordering matters: **the walk runs before the dialog's resource is
loaded.**  The walk puts up the desktop's own alerts when a path is too
deep, and an alert's text is fetched from whichever resource is current --
which, once `PREFS.RSC` is loaded over `DESKTOP.RSC`, would be the wrong
file's string at the right index.

The first picture showed `DISK A__`: a TEDINFO's template shows its
underscores wherever the text stops short, so the name is padded to the
field's width.  And every count is ten places wide, so the numbers line
up.

`make test-m41` selects DISK A, presses ^I, and checks the resource
loaded (the far heap, as `test-m40` watches it) and that what the desktop
counted -- read out of its `G` by field name -- is what the host counts
in the disk image itself: 2 folders, 23 files, 210,603 bytes, on the day
it was written.
