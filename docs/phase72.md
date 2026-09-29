# Phase 72 -- exit() ends a program; QED opens, quits, and takes a dropped file

## exit()

A program built with the kit that called `exit()` never came back.  The
kit gave the C library its board stubs (`src/app/gemstub.c`) but not
`exit`, so the link took Calypsi's simplified one, which ends in
`_Stub_exit` -- a wait that never returns, right for a board where the
program is the machine.  QED quits with `exit(0)`: File > Quit closed
its windows and left it spinning at `_Stub_exit` with its menu bar up,
and the desktop never came back.  It had never been tried; the port's
gate ended with QED still running.

The kit's `exit` and `_Exit` are GEMDOS `Pterm` now, which ends the
program and brings the shell back exactly as returning from `main`
does.  `make test-m32`'s child ends with `exit(5)` rather than
`Pterm(5)`, so the parent's `Pexec` answering 5 is the kit's exit
working; with Calypsi's it would hang there.

## QED (the port, slaapliedje/qed-gem4xe)

- **A document dropped on QED.PRG opened nothing.**  A gem4xe program
  starts with `argc` 0 -- its command tail arrives through `shel_read`,
  as the kit's README says -- and QED takes its files from `argv`.  QED's
  `main` is compiled as `qed_main`, and the port's `main` makes `argv`
  of the tail.
- **The file selector**, reported as not working: File > Open with the
  name typed, clicked, or double-clicked in the list all open the file
  in the emulator.  Not reproduced; the stuck right button of phase 70,
  which makes every double-click fail, is one explanation for it on a
  real machine.
- The port's gate now opens a CR LF document through the selector, quits
  with File > Quit back to the desktop, and drops the document on
  `QED.PRG`.
