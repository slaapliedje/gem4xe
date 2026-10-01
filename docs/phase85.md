# Phase 85 -- the 3D look, behind a switch

The Falcon AES's and MagiC's look (AES 3.40): raised buttons, pressed
ones sunk, grey dialogs, a three-line outline round a dialog box.  Off
by default -- gem4xe draws exactly as it did -- and on with the control
panel's General module, Look: Flat | 3D, saved with the module's other
settings and put back at boot.  The first feature of the 0.11 line;
master as it stood before it is the branch `release-0.10`.

## Drawing

src/aes/objc.c follows EmuTOS's CONF_WITH_3D_OBJECTS (GPL, the same
donor as the rest of the AES).  Only an object with a 3D flag changes,
and only while the look is on:

- FL3DIND, an indicator (a radio or toggle button): grows ADJ3DSTD, two
  pixels, on every side; its colour changes when selected, its text
  stays put.
- FL3DACT, an activator (an EXIT button): grows the same; its text
  moves down and right when pressed, its colour does not.
- FL3DBAK, a background (a dialog's box): the grey ground, and the
  three-line outline when OUTLINED.
- A 3D object shows SELECTED by its edge and colour, never by XOR; so
  objc_change redraws it rather than inverting it.

**One difference from EmuTOS, chosen:** a background TEXT -- a value
printed on a dialog, Drive information's counts -- takes the grey
ground and nothing else.  EmuTOS gives it an edge and the growth too,
and on an 8-pixel cell every value became a raised strip.

The ground is light grey (pen 8) where there are more than eight pens,
white on the two-colour ANTIC screen (ob_3dinit, at gsx_start).

## Asking

objc_sysvar and appl_getinfo(13) answer for the look in force: flat,
AD3DVALUE 0 and white grounds; or EmuTOS's answers, AD3DVALUE 2.  cflib
lays its dialogs out by AD3DVALUE, so QED's follow the switch.  The six
standard settings can be set, as on the ST; G4_3DLOOK (100) is gem4xe's
own and turns the look on and off.

## Which dialogs

tools/rsc.py's flags3d gives a dialog its flags by what each object is:
the box a background, an EXIT button an activator, a selectable button
or box an indicator, a plain text on the box a background.  The
generators ask for it with `r.tree(objs, look3d=True)`: the desktop's
dialogs, the control panel, General, Color, the calculator, the clock
and the file selector.  Menus and the desktop's icons stay flat, and so
do the control panel's extension rows (a list).  The AES's alerts get
FL3DBAK and FL3DACT where alert.c builds them.

**Room for the edges.**  Two pixels a side is a quarter of a cell: the
radio rows ran into the labels above them and buttons a cell apart
touched.  The control panel's and General's labels moved up three
pixels and their named radio buttons narrowed by a cell.
tests/host/test_look3d.py holds every shipped dialog to no overlaps
(rsc.overlaps3d), and makes the check fail on a fixture first.

## Compiler bug B24

`icol = d3 == FL3DACT ? actbutcol : indbutcol;` in just_draw stored the
choice at 1,s and the join read icol from 10,s -- at -O1 and -O2, with
?: or with if, bytes or words, and when moved into a function the
compiler inlined it and made the same join.  The 3D buttons drew white
and the ground yellow.  The colours are a table read by index now,
which has no join (tools/ccbug/README.md, B24; no minimal case yet).

## The engine stack

test-m32's Pexec had 1,039 bytes of the engine stack left, fifteen over
GEMDOS's 1,024-byte guard (src/sys/gemdos.c), and the look's few bytes
more took it under: every Pexec answered ENSMEM.  The stack is 2,080
bytes now, which is all LoRAM's reserve allows; see src/gem4xe.scm.

## Gates

- **m4**: the 3D dialog drawn flat (the flags change nothing) and in 3D,
  pixel for pixel against tools/aesref.py, with objc_change on each kind
  and the objc_sysvar answers both ways.
- **m36**: the look saved in GENERAL.CFG is on after a reboot, and the
  disk without one boots flat.
- **m11**: objc_sysvar refuses a pen that is not there (setting a real
  one succeeds now).
- **tests/host/test_look3d.py**: every dialog fits.
