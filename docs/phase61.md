# Phase 61 -- Install application; and PREFS.RSC, which had stopped loading

The third item of 0.9 (`docs/roadmap-0.9.md`): a document opens the
program that edits it.

## What it does

- **Options -> Install application**, with a program selected in a
  window: its name, and an editable **document type** -- an extension.
  Install, Remove or Cancel.  A program has one type and a type one
  program; installing either again replaces what was there.
- **A document of an installed type, double-clicked**, runs its program
  with the document's whole path as the command tail -- `A:\STARTUP.BAT`
  -- in the program's own directory, the TOS desktop's "default
  directory: application".  A document of any other type still asks Show
  / Print / Cancel.
- **A file dropped on a program's icon** runs that program with the
  file, whatever its type -- the TOS desktop's other way.
- The installs are kept as `#G` lines in `DESKTOP.INF` -- the type, then
  the path, each ended by `@` -- which is also how they survive the
  desktop exiting every time it runs a program.  With nothing installed
  there are no lines, and the file is what it was.

The table is deliberately **not** in the desktop's `G`: `test-m17` holds
`G` to its model byte for byte, and a desk with nothing installed is
exactly the desk it was.  The dialog lives in `PREFS.RSC` beside Set
preferences and DOS command, so it costs the pool nothing until it is
open.  One way to run a program now serves all three paths (`run_prog`,
`src/desk/deskwin.c`), and the two that build paths keep their frames
out of `do_open`'s, which is under every window the desktop opens --
the stack's low-water marks did not move.

Whether a program READS its command tail is the program's business: the
calculator ignores it.  QED, item 5, is the one that will not.

## PREFS.RSC could not be loaded -- in 0.8

The gate's first run put up "PREFS.RSC is not on the disk" instead of
the dialog -- and so did Set preferences, on the commit before any of
this.  Nothing gated it on the product disk: `sdx816` drives DOS command,
but on a disk without the control panel.

The file was there.  `rs_load` gave up at its first line -- **one
resident resource and one nested is all a process may have** -- because
the desktop already had two.  The AES runs control panel modules at boot
(phase 48): each is RUN as a program, in the process record the desktop
is about to be started in, and `GENERAL.CPX` loads `GENERAL.RSC` in its
`cpx_init` and keeps it -- rightly, since it holds pointers into it for
the life of the machine.  But record 0 went on CLAIMING it, so the
desktop's own `DESKTOP.RSC` became the nested one, and every nested load
after it was a refused third: **Set preferences, File -> DOS command, a
`.TTP`'s parameters** -- and Install application -- all said the file
was missing, on every machine with `GENERAL.CPX`, which is every release
since the control panel shipped.  And the pool grew by the failed
attempt each time.

`rs_hold` and `rs_unclaim` (`src/aes/rsrc.c`) take the running process's
slots before the shell runs a program that stays -- a module, an AUTO
program -- and put them back after.  What it loaded stays where it is,
below the keep mark, and belongs to nobody, as an accessory's resource
belongs to the accessory's own process and never to the desktop's.

## The gate

`make test-m39`, on the product disk at the mouse: `CALC.PRG` installed
for `BAT`; `STARTUP.BAT` double-clicked, and the shell's own buffers
(`sh_cmd_far`, `sh_tail_far`) checked for `A:\APPS\CALC.PRG` and
`A:\STARTUP.BAT`; the calculator quit and the same again, which only
works if the desktop that came back read the `#G` line; and
`GEM4XE.CFG` dropped on `DESKTOP.PRG` in `\GEM\`.  Being in `PREFS.RSC`,
it is also the gate for that file loading on a disk with the control
panel.
