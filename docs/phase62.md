# Phase 62 -- Select all and Cycle windows

The first of item 4's small desktop items (`docs/roadmap-0.9.md`).

- **File -> Select all** (^A): every item the top window lists -- the
  listing's own flags, which Delete and a drag work from, so what has
  scrolled out of view is selected too -- and the ones showing drawn
  selected.
- **File -> Cycle windows** (^W): the window at the bottom comes to the
  top, through the desktop's own `WM_TOPPED`, exactly as a click on it
  would.  The desktop keeps its windows' roots in stacking order, bottom
  first, which is what finds it.
- **Set file mask...** is in the menu, greyed out until the phase that
  builds it.

Four objects went into the File menu, so every item after them has a new
index; the numbers are `tools/deskrsc.py`'s constants and nothing else
names them, so the C, the desktop's model and the gates all moved with
them -- `test-m17` and `test-m19` hold the model to the desktop and
passed unchanged.

`test-m38`, the keyboard gate, now also presses ^A and counts the
selected items in the top window, uses the up arrow to scroll back, opens
a second window with `1` and has ^W bring the first one up, and closes
both with ^U.
