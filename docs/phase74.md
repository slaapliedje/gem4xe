# Phase 74 -- Install icon: a drive on the desk

A 0.9 tester keeps SpartaDOS X on an APT partition at D5:, so the SIO2IDE
is left undisturbed, and MyDOS images from a SIDE2 at D1: and D2:.  The
desk showed D1: and D2: only, and there was no way to put D5: there.
SpartaDOS, SDX and MyDOS keep no drive map, and asking each unit costs
an SIO timeout for every one that is absent, so the desk shows D1: and
D2: and leaves the rest to DESKTOP.INF (`src/sys/gemdos.c`,
`gd_drvmap`) -- but nothing let a person write that part of it.

**Options -> Install icon** does now (the item was in the menu, greyed,
since the desktop first ran).  With a drive icon selected the dialog is
that icon's -- change its drive or its label, or Remove it; with none
it adds one.  The drive is typed as its digit, D5: as 5, and a label
left empty becomes "DISK D5:".

The first change takes the set over from the desk as it stood -- the
map's icons with the labels they show -- so installing D5: adds to D1:
and D2: rather than replacing them.  From then on the desk is that set,
and Save desktop keeps it as "#M" lines in EmuTOS's form
(`#M 00 00 00 FF E apt@ @` -- the letter, because it is a GEMDOS path's).
An INF with no "#M" lines is the map again, so a desk nobody has changed
is exactly the one it was: the same G, which `make test-m17` holds to
its model byte for byte, and the same INF text, which `test-m19` reads
back.  The set lives outside G for that reason, beside the installed
applications.

`make test-m43` installs D5: as "apt", saves, cold-resets and finds it
again, then removes it.
