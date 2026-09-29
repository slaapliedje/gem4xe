# Phase 70 -- a tester's first week on 0.9

Three faults from a tester on real hardware (an ANTIC machine with an
Antonia 2, and a switchable ST/Amiga mouse), fixed for 0.9.1.

## A document from an ST or a PC showed as one line

Show, on a document the desktop cannot open, draws the file a line at
a time (`src/desk/deskcmd.c`).  A line ended only at the Atari's EOL,
`$9B` -- right for what a DOS command prints, wrong for a text file off
an ST or a PC, whose lines end in CR LF and which has no `$9B` in it at
all.  The whole file was one line, cut at eighty columns.  `cmd_eol`
now answers for every ending a file may carry -- `$9B`, CR LF (one
ending), a bare LF, a bare CR -- and the count, the seek and the drawing
all ask it, so the slider and the text agree.  A tab is spaces to the
next eighth column rather than one space.

`make test-m41` shows a CR LF file with a tab: three lines, and
"SECOND LINE" drawn as its own row.

## A mouse whose right button reads held from power-on

The right button is the port's first paddle line, and a low count is a
press (`src/vdi/pointer.c`).  An ST mouse leaves the line open when the
button is up.  The tester's switchable mouse, in ST mode, moved the
pointer but no menu would drop and no double-click registered, and in
Amiga mode the desktop stopped as it started: the signature of a right
button read as held.  The menu bar takes over only with every button up
(`src/aes/menu.c`), a double-click never matches with another button
down, and a desktop that starts with a button down starts a rubber-band
drag that waits for a release.

So the right button is not believed until its line has been seen free:
a line that reads low from power-on is the mouse's wiring, not a press.
**Not reproduced here** -- the emulator's mice leave the line open, as a
real ST mouse does -- so the tester's mouse is the proof.

## MOUSE=CX77 was silently the ST mouse

`GEM4XE.CFG` described the tablet as "TABLET (CX77 or KoalaPad; KOALA
works)", and the tester wrote `MOUSE=CX77` -- which was not a word the
file knew, and an unknown word leaves AUTO, the ST mouse.  Atari's part
numbers are accepted now: `CX77` is the tablet, `CX80` and `CX22` the
trak-ball, and the file says so plainly.
