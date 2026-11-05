# Phase 129 -- several programs put aside, and CONTROL-TAB

Step 3 of [switcher-plan.md](switcher-plan.md), and the key from step 4.
Up to six programs can be loaded at once besides the desktop: one
running, the rest put aside where they stopped.  **CONTROL-TAB** goes to
the next one and **SHIFT-CONTROL-TAB** to the one before, the desktop
among them.  The Desk menu's list of programs is the other half of step 4
and is not here yet.

## The key

Alt-Tab is what people now expect, and MultiTOS had it as
Control-Alternate-Tab (its `hctl_keybd` in `GEMCTRL.C`, read as
specification: `$0C0F0009`, CONTROL and ALTERNATE with TAB, goes down the
list of processes, and with a SHIFT up it).  This keyboard has no
Alternate key.  INVERSE, which stands in for it elsewhere, already turns
pointer mode on and off (phase 111), and in pointer mode TAB is the right
button.  So the key is **CONTROL-TAB**, MultiTOS's chord without the key
that is not there.  It typed nothing before: the OS's table makes it CLR
TAB, `$9E`, which the VDI's translation drops.  So no program loses a key
it had.

| | |
|---|---|
| taken | by the VDI, before the key queue (`kb_queue`, `src/vdi/vdi.c`), so no program ever sees it; in pointer mode too, where TAB *without* CONTROL stays the right button (`src/vdi/pointer.c`) |
| acted on | at process 0's next poll (`sh_hotkey`, `src/aes/shel.c`, from `ev_poll`), if it is waiting in an `evnt_` call **of its own** (`ev_appwait`, set by `aes_entry` around opcodes 20-25), nothing is mid-gesture (`ct_idle`), the menu is not tracking, and nobody holds the screen (`wind_update`) |
| dropped | inside a `form_do`, a drag, an alert or anything else that waits inside another AES call -- what is on the screen then is in no window that a resume could redraw |
| left for later | while an accessory has its turn, or the shell is between two programs: so a second press goes one further |

A program is put aside exactly as `shel_write(SWM_G4SUSPEND)` puts it
aside (phase 127), and what runs in its place is the next one.  The
desktop is never put aside: it is sent **`AP_G4SWITCH`** (`0x4734`,
gem4xe's own message, msg[3] 1 next or 2 back), answers
`shel_write(SWM_G4SWITCH, msg[3], ...)`, and ends the way it ends to run
any program.  It stays dormant (phase 121), and the shell resumes the
program the call chose.

`shel_write(SWM_G4SWITCH)` (72, in the kit's `gem.h`) is there for a
program too.  `isgr` 1 puts the caller aside for the next program, and 2
for the one before.  It answers 1 when the caller is resumed, and 0 at
once when there is nothing to switch to.

## The ring

Everything loaded and not running, in far memory (`src/aes/shel.c`, the
ring after the desktop's directory): each program put aside by its record,
and the desktop, while it is not the one running, by `SH_DESKREC`.  The
one running is the gap between the last entry and the first.

- **CONTROL-TAB** runs the first entry, and SHIFT-CONTROL-TAB the last.
- **Whatever stops goes into the gap**: put aside, it is an entry; ended,
  it is gone.  What starts leaves its entry, and the entries before it go
  round to the end.  So the circle keeps its order however it is gone
  round, which is the order the programs were started in, with the
  desktop after the last.  That is MultiTOS's list of processes, and it
  is what makes the key predictable.
- **A program the desktop starts comes in just before the desktop**, so
  one CONTROL-TAB from a program just started goes back to where it was
  started from.
- **Starting a program by name** from the desktop resumes it if it is in
  the ring, as in phase 127, so names in the ring are unique.  A program
  that ends asking for another to run (`shel_write(SHW_EXEC)`) is replaced
  in the circle by the new one.

Started A, B, C from the desktop and each put aside, the ring is A B C
with the desktop running.  CONTROL-TAB runs A and leaves B C D.  Another
runs B and leaves C D A.  SHIFT-CONTROL-TAB from B runs A again and leaves
B C D.

## How many

**Six** programs besides the desktop (`SH_PROGS`): the number the plan
suggested, as many as the Desk menu has accessory slots.  It is one
constant, and the decision is still open.  A seventh is refused when it
is started, with the alert a program that cannot be loaded gets; step 5
gives that case words of its own.  Far memory is what really runs out
first: every program aside keeps its code, its far data and its
resources, and a record of its bank-$00 blocks.

## A program started by a program

Found on the way: a program started with `Pexec` by another runs in its
parent's context, and nothing stopped it from being put aside on its
own, with its parent's frames under it.  It became reachable once a key
could do it.  The shell now keeps the owner of the program it started
(`sh_runown`) and refuses any other.

## What it costs

Two bytes of the window section (`ev_appwait`, `sh_runown`), one of the
direct page (`kb_switch`: LoRAM is at its floor), and 26 bytes of far
memory, added to the desktop-directory block rather than a block of
their own, so that no gate's model of the heap has one more block to
place.  `sh_susp`, phase 127's one record, became `sh_left`, what the
last program left for the ring.

## The gate

`make test-m54` (`tests/emu/m54_switch.py`).  It starts three copies of
phase 127's program (`src/m53_app.c`, which now shows the id the gate
gives it in its window's title, and switches when asked) and puts each
aside with the key.  Then it goes round with CONTROL-TAB and
SHIFT-CONTROL-TAB: from the desktop, from one program straight to the
next, and once by the program's own `shel_write(SWM_G4SWITCH)`.  After
every switch it checks:

- the right program is running, resumed (its count went on), with its
  window on top and a `WM_REDRAW` and a `WM_ONTOP` for it;
- the ring, read out of far memory, is in the order the circle says.

CONTROL-TAB with nothing aside does nothing.  It is dropped inside the
desktop's About box, and inside an alert a program puts up without
`wind_update`.  When all three have quit, the ring is empty
and the far heap holds the blocks it held at the start, by length and
kind.  It compares length and kind, not address: the shell takes a fresh
park buffer at every put-aside and gives one back at every resume, and
the desktop's blocks go wherever there is room while the programs hold
theirs.  So after a round the same blocks sit elsewhere.  The first
version compared addresses and failed for exactly that.

Shown to fail three ways:

- **The record not freed at a resume**: nine 3,493-byte system blocks
  were left behind.
- **The one that stopped put at the ring's front instead of in the
  gap**: 28 problems, the wrong program resumed from the second switch
  on.
- **The "in an evnt_ call of its own" test taken out**: the key put the
  program aside inside its own alert.

The last was not caught at first.  With only the About box, the gate
passed with the test removed.  The desktop holds the screen lock around
its menu handling, so the lock check dropped the key before the test
mattered.  The program's own alert takes no lock, and it is the case
that only this test covers, which is why the program learned to put one
up (`src/m53_app.c`, step 3).

## Not yet

- **The Desk menu's list** of programs (step 4's other half), and
  closing one from it with `AP_TERM`.
- **Quitting the desktop with programs aside** leaves them as they are,
  and GEM ends.  The plan's answer is to ask each to end first (phase
  123's shutdown).
- **What was short** (step 5): too many programs, or no far memory for a
  record, gets the generic alert or nothing.
- A program that draws **outside its windows** and is put aside is not
  redrawn there when it is resumed.  Only its windows are.
