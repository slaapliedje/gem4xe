# Phase 87 -- the desktop's icons from DESKICON.RSC

Phase 86 drew colour icons; the desktop still drew its own eight mono
ones.  Now, when there is a DESKICON.RSC beside DESKTOP.RSC, the desktop
draws its drives, trash, folders, programs and documents with that
file's colour icons -- the Falcon's, from a Falcon's own disk, is what
this was written against.  Without the file nothing changes.

The Falcon's DESKICON.RSC is Atari's and still under copyright.  It is
not in this tree, in a release, or in any gate: a user who has a Falcon
disk copies the file into the GEM folder themselves.  The check that it
works is a private one (the screenshots were taken from a scratch copy
of `gem-shots.atr`).

## The AES: a new-format resource loads far

rs_load kept a resource with colour icons in the pool, because
rs_cicons patched its objects through near pointers.  DESKICON.RSC is
10.6 KB before its icons, more than a launched program's share of the
pool, so the desktop could never have loaded it.  rs_cicons now reaches
the objects through far addresses (addr_at, rd_native, wr_native) and
takes the RSHDR and the resource's base from its caller, so a new-format
resource goes far for any program that can take far trees -- the desktop
among them.  Only the near records (CICON_NEAR, one per icon) come into
the pool: the 33 Falcon icons cost 1,848 bytes there.

A colour icon's text in the file is twelve bytes and need not end in a
0; the loader zeroed the twelfth, so "program file" came back "program
fil".  The near record has room for fourteen, and the 0 goes after the
twelfth now (CICON_FTEXT, CICON_TEXT, aes.h).

## The desktop: taken, not kept

The AES gives a program two resource slots, and the desktop needs the
second for PREFS.RSC (Set preferences and the rest).  So desk_cicons
(desktop.c) loads DESKICON.RSC into it at start, copies the icons the
desktop uses into one far block of its own (Malloc) -- record, mono
image and mask, colour image and selected image, each with its mask --
and gives the slot back.

Icons are chosen BY NAME, spaces and case aside: the first HARD DISK,
FLOPPY DISK, TRASH CAN, FOLDER, PROGRAM FILE and TEXT FILE in the tree.
A NEWDESK.INF names icons by number instead; reading one is for later.
A kind the file does not have keeps its mono icon.

A desktop icon's record (SCREENINFO) grew a pad byte and the two colour
form pointers, so that col4 sits at offset 48 as in the AES's
CICON_NEAR: obj_icon makes the object a G_CICON and objc_draw reads
either record the same way.  G grew to 2,202 bytes; tools/deskref.py
lays it out the same way and makes the extra rsrc_load call, which the
gate disks answer with "not there".

**The cost:** the desktop reads the 64 KB file every time it starts,
and it starts again after every program.  From an emulated floppy that
is about six seconds.  Keeping the icons across a program's run is for
later.

## B21, a second form

ci_named folded a `char` to upper case, and at -O2 the folding path
fell into the comparison with the accumulator 8 bits wide.  The first
thing there was a far pointer's low word, copied -- a byte at a time.
Only `HARD DISK`, already in capitals, ever matched.  Every instruction
at the join decodes the same in either width, so mscan's joins() had
nothing to flag.  mscan.mixed() asks the wider question: any instruction
whose effect depends on the accumulator's width, at a point both widths
reach.  It finds this one in `tools/ccbug/mscan_b21m.s` (the listing,
with the fixed function beside it as a silent control, a `check-cc`
fixture) and nothing else in the build.  The fix is B21's rule: every
character a WORD.  tools/ccbug/README.md has the account.

## Not yet

- NEWDESK.INF's icon numbers, and the Falcon's other kinds (printer,
  CD-ROM, cartridge, TOS file).
- Our own colour icons -- a 1050 and an XF551 for the drives -- which
  can ship, where the Falcon's cannot.
- The 3D look on windows.  EmuTOS raises the closer, fuller, sizer,
  arrows, elevators and title (gemwmlib.c, gl_3dflags); gem4xe's
  window manager draws them flat.

## Gates

`test-host`, `test-m4`, and the desktop's: `m17`, `m18`, `m19`, `m23`,
`m38`, `m41` -- every desktop gate runs the new start-up path without
the file.  `make check-cc` proves mscan.mixed can report; `make mscan`
runs it over the build.
