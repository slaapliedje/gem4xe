# Phase 131 -- closing a program, and Quit with programs aside

The last part of step 4 of [switcher-plan.md](switcher-plan.md), and
the plan's decision 3.  A program in the Desk menu's list (phase 130)
chosen with **SHIFT** is asked to end.  The desktop's **Quit** with
programs aside asks each of them to end before GEM does.  It is
MultiTOS's shape on phase 123's rule: **asked, never forced.**

## SHIFT, not CONTROL

MultiTOS closes a program chosen from its Desk menu with CONTROL held
(`GEMCTRL.C`, `keyret & 0x04`, read as specification): `AP_TERM` if it
registered for it, `Pkill(SIGTERM)` if not.  POKEY reports CONTROL only
in the code of another key that is held, so a CONTROL-click cannot be
seen on this machine.  SHIFT is live in `SKSTAT`, and that is the key.

## Asked, never forced

A program that never said, with `shel_write(SWM_NEWMSG, NM_APTERM)`,
that it understands `AP_TERM` may be holding work it would lose.  Phase
123's shutdown refuses to ask such a program, and so does this
(`sh_takes_apterm`, `src/aes/shel.c`).  There is no `Pkill`.  The user
is told, in `LANG.RSC`'s new **NOTERM** alert, to quit it from its own
menu, and nothing else happens.

| chosen with SHIFT | |
|---|---|
| the program in front | `AP_TERM` to it (`sh_close`) |
| a program aside | resumed with `AP_TERM` waiting for it: `sh_term`, posted by `sh_ldapp` once it is put back and before it runs |
| the desktop | the same: it answers `AP_TERM` as Quit, below |
| one that cannot be asked | NOTERM, and no switch |

A program that refuses (`AP_TFAIL`) simply stays in front.

## Quit with programs aside

The desktop's Quit used to end GEM, leaving any program aside where it
was, its files open.  Now, when the desktop ends without asking for
anything and the ring holds programs (`sh_quitround`):

- If **one of them cannot be asked**, none is.  The **QUITLOADED**
  alert says so on the bare desk (`APP_E_LOADED`, as the shell reports a
  program it could not load), and the desktop comes back.
- Otherwise the desktop is **kept dormant** and the round begins
  (`sh_closing`).  The first program aside is resumed with `AP_TERM`
  waiting.  When it ends, the next one is asked (`sh_closenext`), and
  when none is left GEM ends, as the Quit asked.
- A program's **`AP_TFAIL` ends the round**, and it stays in front.  So
  does switching away, by key or by the list.  The desktop comes back
  as after any program.

## Two compiler faults

`sh_takes_apterm` reads `p_msgs` from the copy of the process record
that a program put aside keeps in far memory, so it needs the field's
offset.  Written as the usual difference of two `char` pointers, it
stopped Calypsi with an internal error.  Written as the member's address
cast to a number, it stopped Calypsi with another.  Both crash at every
`-O`, in both data models, even through a plain struct: **B28** and
**B29**, in `tools/ccbug` with `b28.c` and `b29.c`, which `check-cc`
compiles to see whether they still crash.  The source uses sizeof
arithmetic instead, since `p_msgs` is the record's last word.

## What it costs

Two bytes of the window section (`sh_term`, `sh_closing`; six left), two
`LANG.RSC` alerts in five languages, and `APP_E_LOADED`.  The test
program, `src/m53_app.c`, registers on request and answers `AP_TERM` by
quitting, or by refusing when the gate says so.  Its near constants
outgrew their 160 bytes, so it has 224.

## The gate

`make test-m56` (`tests/emu/m56_close.py`), with three copies of the
program.  A and B can be asked, and C cannot.  SHIFT is the real key,
held in POKEY's matrix with F4, which types nothing.

1. In C, A (aside) chosen with SHIFT: A is resumed and quits, and the
   desktop comes back.
2. On the desktop, C chosen with SHIFT: the alert is up and nothing
   switched.  It is answered, and nothing has changed.
3. Quit with C aside: refused, the alert on the bare desk, then the
   desktop again, with both programs still loaded.
4. C registers and B is to refuse.  Quit: the programs ahead of B are
   asked and go, B refuses and is in front, and the round is over.
5. In B, its own line chosen with SHIFT: `AP_TERM` to itself, and it
   quits.
6. Quit with C aside: C is asked, quits, and GEM ends, back to G4DOS's
   shell.

Shown to fail three ways:

- **The registration check skipped**: C was resumed and quit where the
  alert should have been, and the Quit was not refused.
- **`AP_TFAIL` not ending the round**: the round was still on with B in
  front.
- **`AP_TERM` not posted on resume**: A came back and stayed.

## Not yet

Step 5, what was short.  Too many programs, no far memory for a record,
or a pool place taken still get the generic alert or nothing: phase 132.
