# 0.8.1 -- Set preferences, DOS command and .TTP programs work again

A point release on the stable line: one fix, and the speed work of
phases 52-58.

## The fix

On any disk with the control panel's `GENERAL.CPX` -- every release since
the control panel shipped -- **Options -> Set preferences, File -> DOS
command and the parameter prompt of a `.TTP` program** each put up
"PREFS.RSC is not on the disk".  The file was there.

`PREFS.RSC` is a NESTED resource, loaded over the desktop's while one of
those dialogs is up, and a process may have one resident resource and
one nested.  The AES runs control panel modules at boot (phase 48): each
is RUN as a program, in the process record the desktop is about to be
started in, and `GENERAL.CPX` loads `GENERAL.RSC` in its `cpx_init` and
keeps it -- rightly, since it holds pointers into it for the life of the
machine.  But that record went on CLAIMING it.  So the desktop's own
`DESKTOP.RSC` was already the nested one, and `PREFS.RSC` was a refused
third -- which the desktop reports the only way it can, as a missing
file.

`rs_hold` and `rs_unclaim` (`src/aes/rsrc.c`) take the running process's
resource slots before the shell runs a program that stays -- a control
panel module, or an AUTO program ending in `Ptermres` -- and put them
back after.  What it loaded stays where it is, below the keep mark, and
belongs to nobody, the way an accessory's resource belongs to the
accessory's own process and never to the desktop's.

Nothing had caught it: the one gate that loaded `PREFS.RSC` (`sdx816`)
booted a disk without the control panel.  `make test-m40` opens Set
preferences on the product disk and watches the far heap, where a
large-data program's resource goes: it rises while the chooser is up and
is back where it was once it is closed.  Seen red on 0.8.  It was found
while building 0.9's Install application, whose dialog lives in the same
file.

## Also in 0.8.1

The 0.8.x speed work since 0.8, phases 52 to 58: the ANTIC screen's
text, rectangles and redraws (the desk level with VBXE's), the VBXE
blitter started without waiting, the loader unpacking in fast RAM and a
packed format 18 KB smaller -- the DOS 2 floppy boots in 13.7 s where it
took 21.3.
