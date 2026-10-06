# Phase 108 -- the touch tablets, as they are

A tester could not get a CX77 Touch Tablet to work.  There were two
reasons.  `MOUSE=AUTO` is the ST mouse, not a detection, so a tablet
needs `MOUSE=CX77` in `GEM4XE.CFG`.  And with it, the driver was not the
device: the one `PTR_TABLET` was written against the paddle lines, not
against a tablet.

## What a tablet is

Altirra models both, and the model is what this phase follows
(`inputcontroller.cpp`, `ATTabletController`; `inputmanager.cpp` builds
the CX77 as `(228, invertY)` and the KoalaPad as `(0, no invert)`):

- the position is the port's two pot lines, x then y, 0 to 228;
- with the stylus lifted both read a fixed value -- **228 on the CX77, 0
  on the KoalaPad** -- which is not a place;
- **the CX77's y runs the other way**: 228 at the top;
- **the buttons are the port's direction lines**, active low, not its
  trigger: the stylus button the up line, the pad's left button the left
  line, its right button the right line.

## What was wrong

`poll_absolute` (`src/vdi/pointer.c`):

- read POT0/POT1, port 1's, whatever `MOUSEPORT` said;
- took the left and right buttons from TRIG0 and TRIG1 -- both ports'
  triggers, where a tablet has no button;
- had no stylus-up value, so lifting the stylus threw the pointer to a
  corner (a CX77's to the bottom right);
- had one tablet, with the KoalaPad's y, so a CX77 was upside down.

## The change

- **Two kinds**: `PTR_CX77` (the old `PTR_TABLET`'s number) and
  `PTR_KOALA` (appended, so no number moves).  `MOUSE=CX77` or `TABLET`
  is the CX77, `KOALA` or `KOALAPAD` the KoalaPad, and the boot screen's
  Pointer line names which ("touch tablet" / "KoalaPad", the latter a new
  `LANG.RSC` string in all five languages).
- `ptr_decode_tablet` turns a pot pair into a position, or into nothing
  while the stylus is up, so the pointer stays where the stylus left it;
  the CX77's y is turned the right way up.  `ptr_tablet_buttons` reads
  the direction nibble: the stylus button or the left button is the left
  click, the right button the right one.
- **The port**: the tablet's pots and lines are its port's (port 2:
  POT2/POT3 and PORTA's high nibble).  With no `MOUSEPORT` a tablet is on
  **port 1**, where Atari's tablet software reads it and where gem4xe
  always read its position; a mouse keeps port 2.  `MOUSEPORT` says which
  when it is given (a direct-page flag, `ptr_port_given`: LoRAM is at its
  reserve).
- The vertical blank's click ring (phase 95) holds triggers, so it has
  nothing of a tablet's buttons; `ptr_buttons_at` answers -1 for both
  tablets and the poll reads their lines as before.  A click made while a
  program is busy can still be lost on a tablet.

One reading belongs to two things and nothing can part them: the
stylus-up value is also a corner -- the CX77's top right, the KoalaPad's
top left.  The pointer stops a pixel short of that corner rather than
being thrown to it.

## Proof

The bridge can neither attach Altirra's tablet controllers nor set a
pot, so the real devices cannot be run in a gate.  What is held instead:

- **`tests/host/test_pointer.py` `TestTablets`**: a model of
  `ATTabletController` forward -- where the stylus is, to what the port
  reads -- and the target's own `ptr_decode_tablet` and
  `ptr_tablet_buttons`, compiled for the simulator (`tablet_sim.c`), over
  every value of each pot against the other's edges and middle, both
  kinds, and every state of the four lines.  Dropping the CX77's y
  inversion fails it, and so does reading the wrong line for the right
  button.
- **`make test-m10`**, "touch tablets": an empty port reads 228 on both
  pots, which is a lifted CX77 stylus -- the pointer must stay at
  (300, 100) -- and `JOY` sets port 1's direction lines: up and left are
  the left button, right the right one, and port 2's lines are nothing.
  The same empty port is a KoalaPad touch at the bottom right.  Against
  the old driver four of these fail: the pointer at (639, 239) and no
  button at all.
- `test-m20`, `test-boot`, the host tests for the language file, the
  docs and the dist pass; `make memcheck` ok; `mscan --build` reports
  none of its shapes.

## Not done

Telling the devices apart by themselves (`MOUSE=AUTO` detecting a
tablet, an Amiga mouse, a trak-ball) -- by the first sustained movement
or touch, since at rest they all read alike -- is a feature, for 0.13.
