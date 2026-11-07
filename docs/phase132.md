# Phase 132 -- what was short

Step 5 of [switcher-plan.md](switcher-plan.md), the last.  When there
is no room, the switch is refused with an alert that says what was
short, and the machine is never left half-switched.  Each case is
forced in its gate.

| short of | was | now |
|---|---|---|
| a place in the ring: a seventh program | the generic "cannot be loaded" | **TOOMANY**, then the desktop; the six stay loaded |
| far memory for a program's record | CONTROL-TAB did nothing, silently | **NOASIDE**, and the program stays in front |
| its bank-$00 memory, on the way back | the generic alert | **NORESUME**, then the desktop; the program stays aside, to be resumed when the memory is free |
| memory to load the desktop again, with programs aside | GEM ended, leaving them where they were | **NODESK**, and the program put aside last is resumed in the desktop's place |

The four alerts are `LANG.RSC`'s, in German, French, Spanish and Polish
too.  `shel_write(SWM_G4SUSPEND)` and `SWM_G4SWITCH` still answer a
program 0 for every refusal, without an alert: a program that asks can
say so itself.

## Never at the desktop's cost

A program put aside keeps all its far memory.  Its record and the park
buffer were taken like any other block, so a heap with no room left
**purged** to make room.  It purges level 3, then 2, then 1, and level 1
is the dormant desktop and its file (phases 120, 121), level 2 the AES's
copies of the desktop's resource files.  The program was put aside, and
the desktop then had to be read again with the program's memory still
held.  When that failed the shell ended GEM, with the program still
aside and its files still open.

So the shell now takes a record with `far_keep1` set
(`src/sys/farmem.c`), and only level 3 may be purged for it.  If there
is no room without purging, it is NOASIDE.

## When the desktop cannot come back anyway

A program may itself have purged the dormant desktop while it ran:
asking for memory is what purge levels are for.  Then putting it aside
leaves the desktop to be loaded from the disk, into whatever is left.
If it cannot be, the shell no longer ends GEM.  It resumes a program
aside, with the NODESK alert (`sh_nodeskgo`): the one just put aside,
which first joins the ring, since the desktop's turn of it never ran;
otherwise the ring's first.  It does this once.  If that resume fails
too, the desktop's next failure ends GEM (`sh_nodesk`), so there is no
loop of alerts.

## A real way to lose a program's memory

A program aside keeps its near region as a copy and frees the pool for
whoever runs next.  It is claimed back at the same addresses when it is
resumed.  Anything that takes pool memory at run time can be put there
in between: a control-panel module opened on demand (phase 118), or an
accessory loading a resource.  The pool hands out the lowest free place,
which is just above the desktop's region, where every program's region
was.  Until it is freed the program cannot come back.  That is NORESUME,
and the gate forces it with M50.ACC loading a resource at run time.

## Found on the way

- **A refused resume or load left `sh_term` set.**  Then the desktop,
  running next, found `AP_TERM` waiting and quit.  It also left a Quit's
  round going.  Any failure to start now clears both.
- **The alerts are read back.**  `lang_str`'s one buffer holds the text
  `fm_alert` was given.  It is called `lang_buf` now, since `buf` was
  another file's name too, and `test-m56` and `test-m57` check the exact
  alert, not only that one is up.

## What it costs

One byte of the window section (`sh_nodesk`, plus `far_keep1` in
`farmem.c`: four left), four `LANG.RSC` alerts, and three `APP_E_*`
codes the shell reports like a failed load.

## The gate

`make test-m57` (`tests/emu/m57_short.py`), on two machines.  On the
Rapidus, with M53.PRG as M54A to M54G and M50.ACC with a resource of its
own:

1. Six programs started and put aside, and a seventh refused with
   TOOMANY.
2. M50.ACC loads its resource into the pool, and resuming a program is
   refused with NORESUME.  Once it is freed, the program resumes.

On a plain 65C816 with a megabyte, where far memory can be filled in a
dozen `Malloc`s:

3. The program takes every free byte (step 6), and CONTROL-TAB is
   refused with NOASIDE.  The dormant desktop is still kept, not purged
   for the record.
4. It makes the heap purge the desktop and takes that too (step 8), then
   gives back 12 KB (step 7): room for a record, none for the desktop's
   file.  It is put aside, the desktop cannot be loaded, and the program
   comes back with NODESK.  GEM goes on, the same program, its count
   going on.
5. It quits, and its memory freed, the desktop loads.

On the slow machine the desktop reads the disk at 1.79 MHz, and the
tour's `settle()` (no AES call for thirty frames) returns while the
desktop is still in the DOS.  So the gate waits for the window, the
drive icon and the item it wants, and tries a double-click again rather
than taking a missed one as a failure.

Shown to fail five ways:

- **The seventh program given the old status**: the alert read "This
  application cannot be loaded".
- **The taken memory given the old status**: the same.
- **`far_keep1` never set**: the record was made by purging the dormant
  desktop.  The program was put aside instead of refused, and no
  NOASIDE.
- **The NOASIDE alert removed**: no alert, CONTROL-TAB silent as
  before.
- **The desktop's fallback removed**: GEM ended with the program aside.
