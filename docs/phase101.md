# Phase 101 -- the calculator and the clock hold the screen

Phase 97 made `wind_update` a lock between processes and had the
Control Panel hold it, and left the other two accessories with a dialog
for later: "a program's redraw can still land on them while they are
up, which is what this phase fixed for the panel."

## The change

`calc_panel` (`src/apps/calc.c`) and `clock_panel` (`src/apps/clock.c`)
take `wind_update(BEG_UPDATE)` before `FMD_START` and give it back after
`FMD_FINISH`, as `src/apps/cpanel.c` does.  The program and the
accessory are built from the same file, so `CALC.PRG` and `CLOCK.PRG`
hold it too.  That is what a GEM program with a dialog up does anyway.

The clock redraws its time every tick while it holds the lock.  Those
are the holder's own calls and do not wait.

## Proof

`make test-m44` opens each from the Desk menu, reads `wind_update`'s
count (`wu_count`) while it is up, and closes it: the calculator with
its Quit, the clock with a key.  The count must go 0, 1, 0.

- Before the change it read 0, 0, 0 for both.
- The calculator's `RETURN` is its `=`, not Quit.  The first version of
  the check pressed it and saw the lock held for ever, because the
  calculator never closed.  The check clicks Quit, measured off the
  panel as the Control Panel's places are.

`make test-m22`, which runs both as programs and compares their panels
with the model, is unchanged: `wind_update` draws nothing.

## Also

`tools/mkcf.py`'s `--add` makes the folders an added file's path names.
A test card can then carry `GEM>LANG>DE>LANG.RSC` beside the product's
own.  The product card is byte for byte the same.
