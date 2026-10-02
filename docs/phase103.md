# Phase 103 -- six accessories, and an accessory's own window

Items 11 and 12 of `roadmap-0.12.md`, carried since `roadmap-0.9.md`:
"proving the sixth accessory slot and the seventh refused, and
confirming that `WM_*` messages reach an accessory's own window".
Phase 47 had said the slots were "not yet proven -- three is what has
been run".  Neither had a gate.  Both needed one, and both found
something.

## The gate accessory

`src/m45_acc.c` is the smallest accessory that has a window.  It has no
workstation and a near region of a few hundred bytes, so six of them fit
the pool beside the desktop.

- On `AC_OPEN` it creates and opens a window (name bar, close box,
  mover).
- It answers `WM_REDRAW` by painting its work area white through its own
  rectangle list, `WM_TOPPED` with `WF_TOP`, `WM_MOVED` with
  `WF_CURRXYWH`, and `WM_CLOSED` by closing and deleting the window.
- It counts each one.  A message about a window not its own is counted
  apart, as a misdelivery.

`build/m45-boot.atr` is the product system with seven copies of it,
`A1.ACC` to `A7.ACC`, and no other accessory.

## 11: the seventh was never seen

Six loaded and registered: the Desk drop-down was eight items long, with
seven processes.  The slots were fine.  But the seventh was not
"refused".  `sh_accs` (`src/aes/shel.c`) stopped reading the directory
once it had six names, so the seventh was never read.  It was not
counted in `sh_accfull` and nothing was said.  Someone who copies a
seventh accessory in would be left to wonder why it is not in the Desk
menu.

Now:

- the whole directory is read, and an accessory past the slots is
  counted with the ones the pool had no room for;
- before the first desktop, when that count is not zero, the shell puts
  up `LANG.RSC`'s new `ACCFULL` alert on the bare desk and waits for it:

      Not every desk accessory could be loaded.  There are six places
      for them, and memory may allow fewer.             [ OK ]

TOS says nothing in this case; gem4xe says it once, at boot.
`docs/differences.md` and the kit's accessory section say so.  The
alert is in German, French, Spanish and Polish too, held by
`tools/langrsc.py`'s `check()` like the rest: 107 to 124 bytes, inside
`LANG_MAXLEN`, which is still 130.

## 12: every window's messages went to the desktop

All the `WM_` messages the AES sends were addressed to `proc_app`, the
application, whoever had created the window:

- `w_redraw`'s `WM_REDRAW` and `w_look`'s `WM_SIZED`, in
  `src/aes/wind.c`;
- the control manager's `WM_TOPPED`, `WM_ARROWED`, and each gadget's
  message (`WM_CLOSED`, `WM_MOVED`, `WM_FULLED`, `WM_SIZED`, the
  slider messages), in `src/aes/ctrl.c`.

So an accessory's window was never told to redraw; it was only drawn
when something else wrote over it.  A click on it from behind went to
the desktop, which had no window of that handle, so it did nothing.  Its
close box and its mover did nothing either.  The window
records its owner already (`w_owner`, `WF_OWNER`).  `wm_owner(wh)` now
answers that process, or the application when the record is gone, and
every one of those sends goes to it.  That is the donor's rule:
EmuTOS's `w_redraw` and `ct_msgup` send to
`D.w_win[w_handle].w_owner`.

Nothing in the product changes behaviour: every window it opens is the
application's.  An accessory's window now works.

Not done: a click in the WORK AREA of an accessory's window still goes
to whichever process is waiting for a button, not to the window's
owner.  That is the input-ownership rule (`proc_input`), which follows
the Desk menu and not the pointer.  It is the next step for an
accessory with a window that takes clicks.

## Proof

`make test-m45` (new):

- **Slots.**  Six started, six registered, seven processes, one turned
  away.  The desktop has not started while the shell's alert is up.  The
  alert is compared with `tools/aesref.py`'s `fm_alert` on the bare desk
  and matches pixel for pixel.  RETURN answers it, and the desktop then
  starts.  The Desk drop-down is About, the line, and six "Window gate".
- **Window.**  Desk -> the first "Window gate": one `AC_OPEN` and one
  `WM_REDRAW`.  Drive D1's window is opened over it.  A click on the
  accessory's title bar from behind sends it `WM_TOPPED`; its `WF_TOP`
  puts it on top, and the uncovered part comes back as a `WM_REDRAW`.  A
  drag of its bar sends `WM_MOVED`, and the window moves.  Its close box
  sends `WM_CLOSED`, and it closes and deletes the window.  No message
  about another window reaches it, and the desktop's window is on top at
  the end.

Run on the tree before the change, the gate failed eleven checks:

- `sh_accfull` was 0, and the desktop had started with nothing said;
- the accessory got 0 `WM_REDRAW`, `WM_TOPPED`, `WM_MOVED` and
  `WM_CLOSED`.  The window still went to the top, because the
  desktop, sent `WM_TOPPED` for a handle it does not have, topped it
  anyway.
