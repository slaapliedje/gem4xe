# Phase 65 -- Copying onto a taken name, and what to confirm

The last of item 4's small desktop items (`docs/roadmap-0.9.md`), which
finishes it.

**NAME CONFLICT.**  A copy or a move whose destination already has a file
of that name stops and asks: the name there, the copy's name in a field
to edit, and **Copy** (under the name in the field -- left as it is, the
file there is replaced), **Skip** (this one file; the rest go on) or
**Stop**.  A new name is tested in its turn, so typing another taken name
asks again.  The dialog is `ADCNFBOX` in PREFS.RSC, loaded over the
desktop's resource while it is up; the operation's own dialog is drawn
again under it afterwards.

**Options -> Set preferences** gains three checkboxes, *Confirm deletes*,
*Confirm copies* and *Confirm overwrites*.  All three start on, as TOS
has them.  With deletes or copies off, the counts dialog is shown and the
operation goes ahead; with overwrites off, a taken name is replaced
without asking.  Save desktop keeps them in the second byte of the `#E`
line, stored as what is NOT confirmed, so an INF from before this phase
(a 0 there) asks everything.  They live outside `G` (`desk_confirm`),
which `make test-m17` compares byte for byte.

## And SpartaDOS 3.2's root fallback

The gate's first copy of `STARTUP.BAT` into `GEM` reported a conflict
when `GEM` had no such file.  Typing `X32G.DOS` into the dialog, another
root file, got the same answer.  The desktop tests a name with `Fopen`,
and SpartaDOS 3.2 opens `>GEM>X32G.DOS` for reading from the ROOT when
`GEM` has no `X32G.DOS`.  SDX 4.50 does not; the same copy under the SDX
cartridge went straight through.

A GEM program sees the same fault: it reads the wrong file, or is told a
name is taken when it is not.  So the fix is in GEMDOS, not the desktop.
On SpartaDOS 3.x, an open for reading of a file below the root first
looks for the name in its own directory, read as raw entries the way
`Fsfirst` reads it, and answers EFILNF if it is not there (`gd_in_dir`,
`src/sys/gemdos.c`).  An open at the root, or on any other DOS, is
unchanged.  MyDOS is not measured.

## The gate

`make test-m41` now also, on the product disk with everything confirmed,
masks the root to `*.BAT` (GEM's are past the window's edge otherwise),
drags `STARTUP.BAT` into `GEM` and answers the counts, drags it again and
gets NAME CONFLICT, and types `AGAIN.BAT`: both files are then in `GEM`.
That check failed on the root fallback before the GEMDOS fix.

A second boot uses a copy of the disk whose `DESKTOP.INF` says
`#E 00 07` -- confirm nothing.  The same copy goes through with no dialog
to answer, copying it again replaces it with no conflict, and ^D deletes
it with no confirmation.  That also shows the INF's byte was read.
