# Phase 135 -- the Control Panel, a window

Step 2 of [cpanel-plan.md](cpanel-plan.md), its first half.  CONTROL.ACC
is XControl's shape now: a window beside the desktop's, not a dialog that
holds the screen.  Phase 136 brings General and Color into it.

| | was | now |
|---|---|---|
| what opens | a modal dialog, `form_do` inside `BEG_UPDATE` | a window: title, closer, mover, 256 x 160 |
| while it is up | nothing else can be clicked or redrawn | the desktop and its windows go on working |
| the list | six rows of title text, select then Open | four slots, each the module's icon, its text and its title, and a scroll bar for more |
| opening | pick a row, press Open | double-click a slot, or the arrow keys and Return |
| the clock | -- | a strip with the time and the date |
| an event CPX | drawn into the dialog | drawn into the window, driven there; the window can be topped, moved and closed around it |
| shutting it | OK or Cancel | the closer, Escape, or AC_CLOSE when a program starts |
| the panel's own settings | double-click speed and sub-menu delay | gone: General has both |

## The window

`src/apps/cpanel.c` keeps the window open between Desk-menu choices and
runs it from the accessory's loop (`cp_wait`): while the window is shut
the accessory waits for a message, as before; while it is open, for its
presses, its keys and a one-second timer too.  The presses and the keys
only reach it while its window is on top, which is the AES's rule since
phase 134.

The tree is CPANEL.RSC's (`tools/cpanelrsc.py`): the structure and the
words, translatable there.  Every place is set at run time from the
character cell (`cp_layout`), because a slot is as tall as a 32 x 24 icon
and a line of text -- pixels and characters at once -- and an icon
block's offsets are pixels that `rsrc_obfix` never touches.  A slot's
icon points at the module's header in the AES's table (phase 133); a CPX
icon has no mask, so the slots share one that is all set, and SELECTED
swaps the colours as for any G_ICON.

Opening a module clears the work area and gives the module all of it, as
XControl does.  An event CPX is driven in the window: its redraws come
rectangle by rectangle, its `cpx_draw` clipping to each; a move calls its
`cpx_wmove`, or redraws the work area when it has none; the closer and
AC_CLOSE end it.  A form CPX still puts up its own dialog over the
window -- phase 136 gives it `Xform_do` and the window.

The clock strip reads `Tgettime` and `Tgetdate` every second and draws
only a change: HH:MM and DD/MM/YY, General's order.

## Found on the way

- **A window at x = $5C01.**  The first panel opened its window off the
  screen.  `x` and `y` had been handed to `wind_calc` by address and then
  set with `?:` -- B9 (`tools/ccbug`), wrong at every -O.  `make qscan`
  finds the shape and would have; it now runs clean, and `cp_open` keeps
  `wind_calc`'s outputs apart.
- **The 3D look took 4 pixels off the list.**  General's Look -> 3D with
  the panel open: the AES recalculates every window's work area for the
  thicker frame and sends WM_SIZED (`src/aes/wind.c`), which the panel
  ignored.  It now makes the window the size its tree needs again
  (`cp_fit`).
- **A gate read a module's variables as the desktop's.**  `Tour.G`
  finds the desktop's globals through `app_vars`, the last program
  loaded's -- and opening a module loads one.  test-m44 keeps the
  desktop's address from boot.
- **The places to click were measured off a picture.**  `CPX_ROW1` and
  `CPX_OPEN` in `tests/emu/shots.py` were pixels read off
  `10-cpanel.png`, so no layout could change without re-aiming every gate
  that opened a module.  `Tour.panel` now reads the panel's own
  variables -- its window, its work area and its slots -- through its
  title's address, which the AES holds (`gl_acctitle`), as test-m45 finds
  an accessory's.

## Gates

- `test-m44`, rewritten: Desk -> Control Panel opens a window on top
  listing the three modules, each slot showing its icon; General opened
  from its slot switches the look and the window stays, its work area the
  same size in the new look; D1's icon opens the desktop's window with the
  panel still open; the panel's title bar tops it again; the arrow keys
  move the selection; dragged, the window and its slots move and the event
  CPX draws where it now is; Escape and the close box each shut it; a
  program started with the panel open takes the window (AC_CLOSE), and the
  panel opens again afterwards.  The pool floor, the boot-loaded modules
  and the dialog accessories' screen hold are checked as before.  Fails
  with WM_SIZED ignored and with a move not placed.
- `test-m42`: Color opened from its slot, twice with the window up; the
  panel shut with Escape.
- `make shots`: the panel, General over it, the event CPX in it, its
  alert.
