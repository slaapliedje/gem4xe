# Phase 83 -- after Show info on a folder, every name was AUTOEXEC.BAT

Reported from an Antonia with an IDEplus: open disk A, select the APPS
folder, File -> Show info (^I), close the dialog -- and from then on
every name in every window opened is AUTOEXEC.BAT, and shortly the
desktop cannot be used.  Every time.  Every machine: it has nothing to
do with the Antonia, and it has been there since Show info arrived
(0d9563b, 2026-09-07), so in every release from v0.1 to 0.9.2.

## The DTA

A folder's size in Show info is the delete's counting walk
(`walk(0, OP_COUNT)`, src/desk/deskfun.c), which gives each level of
the tree a DTA of its own with `Fsetdta`.  The window listing,
`pn_active` (src/desk/deskwin.c), reads entries out of `G.g_dta`, and
counted on that being the DTA set: the delete and Show info on a DRIVE
put it back after their walks (the drive one because test-m41 caught
it, phase 63), Show info on a FOLDER did not.  From then on GEMDOS
wrote each entry into the walk's DTA while the listing read the old
one, which still held the last name it had been given -- AUTOEXEC.BAT
in the root -- once for every entry the directory had.  The count was
right and every name the same, and a click or a drag acted on that
name.

## The fix

The listing sets the DTA it reads, just before its `Fsfirst`, instead
of trusting that whoever ran last put it back.  The other callers'
restores stay; none of them is needed for a listing any more.  The
desktop model (tools/deskref.py) makes the same call, or the gates that
predict every call the desktop makes (m17, m18, m19, m23) stall on it.

## The gate

test-m41 now does what the report did -- APPS selected, ^I, OK -- and
then lists APPS and the root again: both must be what they were before.
On the unfixed build, APPS listed AUTOEXEC.BAT four times and the root
five, and the file mask checks after it failed with them.
