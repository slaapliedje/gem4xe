# Phase 97 -- wind_update is a lock

Item 9 of `roadmap-0.12.md`, recorded in phase 88 as "for the moment
between General's OK and the control panel closing, the panel's dialog
shows leftovers".

## Finding it

A scratch tour (Desk -> Control Panel -> General -> Look: 3D -> OK)
showed nothing wrong on a bare desk, or with Cancel instead of OK.  It
went wrong only with a **window open under the panel**.  General's OK
redraws the whole screen, because everything on it was in the other
look, and the AES sends the window's owner a redraw.  The desktop then
repainted its window -- folders, white work area and all -- over the
panel while the panel was still up.  There it stayed until the panel
closed.

The panel is a dialog, not a window, so no window's rectangle list
knows to stay off it.  GEM's answer is `wind_update(BEG_UPDATE)`.  An
accessory with a dialog up holds it, and a process that asks for it
while another holds it **waits**.  The desktop asks for it around its
message handling (`src/desk/desktop.c`), so its redraw would wait for
the panel.

Here `wind_update` was a count (`wm_update`), and its comment said so:
"hold off other processes' screen updates -- none here".  That was true
when there was one process.  It stopped being true when accessories
took turns with the desktop (`src/sys/ctx.h`), and nothing noticed,
because no accessory took the lock either.  Adding `BEG_UPDATE` to the
panel alone changed nothing, which is how the count was found.

## The lock

`wm_lock` (`src/aes/wind.c`) is `wind_update` as a program calls it
(`src/sys/abi.c`, opcode 107):

- `BEG_UPDATE` while another process holds the lock parks the caller,
  as a wait parks it: `p_evwait` is `EVW_UPDATE`, and it polls and
  yields.  `proc_ready` (`src/aes/proc.c`) gives it no turn until the
  holder lets go.
- The lock nests for its holder, so a module's own dialog inside the
  panel is the same owner's.
- `BEG_UPDATE | 0x100`, AES 4's check-and-set, answers 0 instead of
  waiting.  It used to fall through to the mouse-control branch.
- `wind_new` releases the lock if the caller holds it, as it already
  unwound the count.

Its two variables are on the direct page (`TINY`), as phase 88's pressed
arrow is: LoRAM was exactly at its 256-byte reserve, and four bytes there
put `make memcheck` over.

Only a program's call is the lock.  The AES's own `wm_update` calls, in
the form library, the control manager and the window manager, count as
before, so nothing inside the AES can wait on it.

The Control Panel holds it from `FMD_START` to its final `FMD_FINISH`
(`src/apps/cpanel.c`).  Now the desktop's redraw waits for the panel to
close, and then draws the window once, in the new look.

## Proof

`make test-m44` (new) boots twice.  Each run switches General's look to
3D and presses OK; the second has drive D1's window open under the
panel.  The panel's rectangle must be the same pixels both times, and
the desktop must draw once the panel closes.  With `wind_update` put
back to the count, 7,423 of the panel's pixels differ.  The look
changing from 0 to 1 is what says the measured click on "3D" landed.

## Not done

The other accessories with dialogs, the calculator and the clock, do
not take the lock yet.  A program's redraw can still land on them while
they are up, which is what this phase fixed for the panel.
