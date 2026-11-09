# Phase 134 -- input follows the top window

Found on the way to step 2 of [cpanel-plan.md](cpanel-plan.md): the
Control Panel is to be a window that takes clicks and keys while the
desktop goes on working, and the AES had no way to keep an accessory's
input apart from the application's.

| | was | now |
|---|---|---|
| who gets a key | whichever process in a wait looked first | the input owner (`proc_input`) |
| who gets a press inside the top window | whichever process's poll saw it | the input owner's button wait |
| the input owner | the application, or an accessory from its `AC_OPEN` until it waits with no input events | the top window's owner; the application after a press on the bare desk; whoever has a dialog up, while it is up |

## Why it mattered now

`proc_input` existed, but only for the scheduler: the input owner is
always ready to run.  It did not decide who got the input.  An accessory
opened from the Desk menu becomes the owner, so it is always ready, and
whatever it waits for it takes -- the desktop's clicks and keys too.
That was harmless while every accessory put up a dialog and held the
screen until it was gone.  A window that takes input while the desktop
works is exactly the case it breaks.

## What changed

GEM's rule (`gl_mowner`, `geminput.c`): the keys and the presses inside
the top window go to its owner.

- **`in_mine()`** (`src/aes/event.c`): a process's waits see the input
  only if it is `proc_input`, or the control manager is running, since
  its waits are nested inside whichever process saw the press.
  `ev_multi`'s two checks, `ev_block` (`evnt_keybd`, `evnt_button`) and
  `ev_keyq` (the GEMDOS console) use it.
- **`bchange` and `ct_release`** complete the owner's button wait, not
  the running process's.  A transition is seen in whichever process's
  poll it lands in; the owner is always ready and finds it done.
- **A press on the bare desk** gives the input to the application.
- **`w_topchanged`** (`src/aes/wind.c`) hands the input to the new top
  window's owner, or the application when the desk is all that is left.
- **`fm_own`** (`src/aes/form.c`), which `form_do` and
  `wind_update(BEG_MCTRL)` share: the dialog's process takes the input
  for as long as it is up, as GEM's `BEG_MCTRL` makes its caller the
  mouse's owner, and the owner before it gets it back -- or the top
  window's owner, if that process has gone.  Without it an application's
  alert put up while an accessory's window is on top would wait for
  ever.

## Gate

`test-m45`, item 13.  The window gate accessory (`src/m45_acc.c`) waits
for a press and a key as well as messages while its window is open.  With
its window on top, a press inside it and a key are its own.  Then the
desktop's window is clicked and comes to the top, six keys are typed and
the bare desk is pressed: none of it reaches the accessory.  Its title
bar, from behind, tops it again for the close box.

Making it fail took three tries.  The first accessory waited with no
timer, so it never ran once it stopped being the owner, and the check
passed with `in_mine` removed.  A 20 ms timer gave it too few turns to
land on a key, and it still passed.  A 0 ms timer, all the time, slowed
the machine until the desktop missed its double-click on D1.  So it
polls only while its window is behind -- it learns that from
`WM_UNTOPPED` (phase 125) -- which is the case the rule exists for.
With `in_mine` removed it takes all six keys and the press.

## A note for programs

A wait for a button that is down is satisfied for as long as the button
is held.  The accessory first counted 111 presses for one click; a GEM
program waits for the button to come up again after a press, and the
accessory now does.
