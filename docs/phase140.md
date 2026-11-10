# Phase 140 -- the control panel's Options (control panel step 4)

The first half of step 4 of [cpanel-plan.md](cpanel-plan.md): XControl's
Options.  Reload, Unload, Activate and Deactivate are the second half.

| | was | now |
|---|---|---|
| Options | -- | a button in the strip between the time and the date, and its pop-up: About and Setup, and with a module picked Open CPX and CPX Info -- XControl's items |
| About | -- | an alert in CPANEL.RSC's words |
| CPX Info | -- | a form in the window: the module's file, version, id, whether it stays, and whether it is loaded at boot |
| Setup | -- | the clock 24- or 12-hour (a pop-up), Save, OK and Cancel |
| the clock | "13:05" | "13:05", or " 1:05p" |
| CONTROL.INF | -- | the panel's own settings, one line, "CLOCK 12" or "CLOCK 24", read at start |

## The forms

CPX Info and Setup are the panel's own trees in CPANEL.RSC, run in the
window as a module's form is run: the root sized to the work area and
driven by the panel's `Xform_do`.  The window's closer ends one as OK
and AC_CLOSE as Cancel, XControl's rule for its own forms, and the list
comes back afterwards.  The pop-ups are the panel's `Popup`, the one a
module calls, reached through the same block.

CPX Info prints the version as XControl does, four BCD digits: a
header's 1.00 is "01.00".

## Where CONTROL.INF goes

Where the modules' settings go: under a bare name, as `NAME.CFG` has
been since phase 47, so that GEMDOS's path decides it.  On G4DOS that is
the root, which is not the modules' folder.  Both are read back at boot,
because G4DOS, like SpartaDOS 3.2, falls back to the root for a read
that misses in its own folder; on SpartaDOS X a bare name lands in the
DOS's folder.  That two DOSes disagree is the question already open
about Dgetpath against bare names, and settling it would move both files
at once.  `test-m59` holds CONTROL.INF to the folder GENERAL.CFG is in,
whichever that is.

## Three banks, again

The Options cost the panel 2.5 KB of code, and the panel no longer fit
beside the rest of the boot on a machine with three far banks
([phase 139](phase139.md)): its code took the foot of bank 7, where the
desktop's code has to go, and the desktop was refused.  Two things, both
found by recording every block as it came and went during a three-bank
boot:

- **The pop-up was in the panel twice.**  Called by name from the
  Options code, Calypsi inlined all 1,900 bytes of `cp_popup` there.
  It is called through the block's pointer now, as a module calls it.
- **A program's own file sat under it.**  `far_read_file` reads a file
  into the foot of the largest free run, which is where that program's
  code then wants to go; the panel's code missed bank 6 by 74 bytes,
  its own squeezed file below it.  `app_load_cio` now moves a file it
  has read up out of the way before unpacking it, when there is room --
  it is gone again as soon as the program is placed.
- **Up, but not into SDRAM.**  "Out of the way" was `far_alloc_top`,
  the top of the highest gap, which on a Rapidus is bank $EF: SDRAM,
  where nothing is to go on purpose.  It now takes the top of the
  first megabyte -- the Rapidus's SRAM -- when the block fits there,
  and only then anything higher, as `far_alloc_banks` already stayed
  low.  Every user of it gains: the squeezed image's old path and a
  switched-out program's record too.  A heap that ends below the
  megabyte sees no difference.  Tested in the model on a heap that
  crosses $100000, since the simulator's never reaches it.

With both, the three-bank boot runs and settles.  On a 960K machine,
where nothing has to be purged, the boot now settles into four banks --
the desktop's later blocks take the fourth rather than purging a cache
-- so `test-m37`'s 960K check is held to four.  The three-bank guarantee
is `m37three`'s, which boots with the heap cut to three; the 960K check
catches what it was written for in phase 80, programs that stop sharing
banks.

## The boot screen's picture

`make shots` showed the boot screen's logo black, its rainbow gone, and
taking the file move out brought it back -- though the move runs long
after the boot screen.  The tour photographs the screen the moment its
hint appears, and the hint row is written just before `logo_on()` turns
the logo's rows to the rainbow; a picture in between shows them as plain
inverse blocks.  The move had shifted nothing but code addresses, and
with them which side of that the picture fell.  The tour now waits ten
frames after the hint.

## A tree's links, checked where it is built

The Options button went on the end of the panel's root, and the root's
`ob_tail` stayed on the list.  GEM keeps no parent link -- it finds a
parent by walking siblings to the one whose tail points back -- so every
offset under the root was measured from nowhere: the panel drew its list
twice and no click landed.  `tools/rsc.py` now checks every tree every
generator builds: each object below the root a child exactly once, in a
chain from its parent's head to its tail that ends back at the parent,
and LASTOB on the last object only.  It refused the broken tree, and
every other resource in the tree passed.

## Gate

`test-m59`, new, and the first gate of the control panel on G4DOS
(`build/cpx4.atr`: the system floppy with the panel, GENERAL.CPX and the
gate's module as TEST.CPX, on a disk the emulator may write).  The
Options pop-up offers two items with nothing picked and four with
TEST.CPX picked; About puts up an alert that Return takes down; CPX Info
shows TEST.CPX's file, version 01.00, id M35T, not resident, not loaded
at boot; Setup's clock set to 12 hour shows "12:00a"; General's delay
set to Instant and OK'd.  After a cold reset both are back -- the
12-hour clock from CONTROL.INF and the delay from GENERAL.CFG -- and the
disk holds CONTROL.INF, "CLOCK 12", beside GENERAL.CFG, with its bitmap,
chains and free count in agreement.

Fails with CONTROL.INF never read (the clock 24-hour after the reset),
with a pop-up that always offers four items, with Save writing nothing
(no CONTROL.INF, and the clock 24-hour after the reset), and with CPX
Info's file not shown.
