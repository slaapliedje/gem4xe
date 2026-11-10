# Phase 141 -- managing the modules (control panel step 4)

The second half of step 4 of [cpanel-plan.md](cpanel-plan.md), after the
Options of [phase 140](phase140.md): Reload, Unload, Activate and
Deactivate -- and the modules' files named where the boot found them.

| | was | now |
|---|---|---|
| Reload | -- | Setup's button, XControl's place: the folder read again, the list with it, a module that has just come boot-initialised |
| Unload CPX | -- | a module out of the list until the next reload, XControl's; refused for one that stays loaded |
| Deactivate | -- | NAME.CPX renamed NAME.CPZ and the folder read again: on the disk, gone from the list (COPS's convention) |
| Activate... | -- | the .CPZ files in a pop-up, the one picked renamed back -- offered when there is one |
| NAME.CFG, CONTROL.INF | written by GEMDOS's path: the root on G4DOS | beside the modules, where the AES reads them at boot |

## Cpxfile

`Cpxfile(op, i, a, b)`, GEMDOS 0x1F6 and gem4xe's own, does for the panel
what the panel could not do properly itself: `CF_RELOAD` reads the folder
again into a table of its own (refused while a module that is not
resident is open; a resident one keeps its slot, vtable, owner and live
settings), `CF_UNLOAD` takes a slot out, and `CF_READ`, `CF_WRITE`,
`CF_RENAME` and `CF_FIND` read, write and rename a small file of the
modules' folder and find the n-th name matching a pattern.  The table's
old block is given back on a reload and the new one is the system's.

## Named as the boot found them

At boot the AES finds the modules by a bare name, which goes to the DOS:
on SpartaDOS X the folder AUTOEXEC.BAT changed into, on G4DOS its flat
view of the root and every folder.  At run time the same calls went
through GEMDOS's path instead, which the desktop sets to the folder of
the last program it ran, and the panel's own files went that way too.
So the module's file, its settings and CONTROL.INF could be looked for,
or written, somewhere else.  Every module file the AES names now goes
the boot's way (`sh_cpxcio`): the scan, the header, the settings, the
runtime load, and Cpxfile.  `app_load_file`, which loads a module at
boot, already did.

## Beside the modules on G4DOS

G4DOS is flat by design (`src/fdos.s`): a name is found in the root or a
folder one level down, root first, and a file made under a bare name is
made in the root.  That is right for the system -- GEM.COM is found
wherever it is -- but it put every module's settings and CONTROL.INF in
the root, beside no module.  G4DOS's handler under GEM answers a new
question now, `sdc_folder`: in which folder does its search find a name?
The AES makes NAME.CFG in the folder NAME.CPX is in, and CONTROL.INF in
the first module's -- and then deletes a copy an older gem4xe left in the
root, which the search would read first.  Nothing about G4DOS's own
model changes: reads still search, and its shell and kernel are as they
were.  (A current folder for G4DOS was tried and taken out: its kernel
runs GEM.COM directly, so there is no folder to start from at boot.)

The DOS 2 floppy's GEM.COM, built without G4DOS's half (`src/sys/
nog4.c`), has an `sdc_folder` that finds nothing.  And `make mscan`
found a B21 in the new code: the loop that capitalises the name changed
a `char` in place, and the join after it could be reached with the
accumulator in either width.  An `int` now, as the tree's rule says.

## The pop-up scrolls

With a module picked and a deactivated one on the disk, Options offers
seven items, so the panel's pop-up scrolls -- an up arrow, three items,
a down arrow -- as XControl's does past five.

## Three banks

The panel's code grew to 23,849 bytes; the three-bank boot still runs
and settles (`test-m37`).

## Gate

`test-m59` grows.  Its disk now carries the gate's module a third time,
as EXTRA.CPZ, and the gate seeds its copy of the disk with a GENERAL.CFG
in the root, as an older gem4xe would have left it, saying Slow.  The
boot reads it -- the delay is 400 ms -- and once General's delay is set
to Instant and OK'd, a cold reset brings Instant back: the root's copy
went.  Then: Options offers Activate; EXTRA.CPZ activated, three are
listed; EXTRA deactivated, two; TEST unloaded, one; Setup's Reload, two
again.  On the disk afterwards CONTROL.INF and GENERAL.CFG are in GEM
beside the modules, nothing is left in the root, and EXTRA.CPZ is
deactivated again.

Fails with the root's old copy left (the delay Slow again after the
reset, the copy still in the root), with writes not placed beside the
modules (CONTROL.INF and GENERAL.CFG in the root), and with Reload and
Unload doing nothing (EXTRA never listed, TEST never out of the list).
