# Phase 127 -- a program put aside, and resumed

Step 2 of [switcher-plan.md](switcher-plan.md): one program at a time,
XM/GEM's way.  A program calls `shel_write(SWM_G4SUSPEND)` (71, gem4xe's
own mode, in the kit's `gem.h`); the desktop comes back; and when the
program is **started again** from the desktop -- the same name -- it is
not loaded but resumed, inside that call, which answers 1.  Its windows
are back on the screen with their own handles, it is sent a `WM_REDRAW`
for what shows and `WM_ONTOP` for the top one, its files are still open
and its memory is as it left it.  No desktop change was needed: it
starts a program the way it always did, and the shell decides.

Phase 126 is what made it possible: a program runs in a context of its
own, so it can stop in the middle of an AES call and the shell carry on.

## What is put aside

One far record, the system's, written in sequence (the layout is in
`src/aes/shel.c` above `sh_suspend`):

| | how |
|---|---|
| its engine stack | parked, as at any switch, in the park buffer it keeps; the shell takes a new one |
| its context and its `APP` | written by the shell after the switch -- both are the shell's to see |
| process 0's record | everything after the context: waits, resources, open files, DTA, name, messages; then the record is made fresh (`proc_fresh`) for whatever runs next |
| the application queue | its sixteen messages |
| its bank-$00 blocks | near region, a near resource -- every pool block it owns (`pool_owned`), address, length, tag and bytes; then **freed**, so the desktop takes its own region back.  Resuming claims each where it was (`pool_claim`); if one's place is taken, nothing is changed and it stays aside |
| its windows | `wm_save`: each one's handle, record and rectangle, bottom first; `wm_restore` makes them again at the same handles and reopens them -- quietly, without the `WM_UNTOPPED`s reopening would queue -- then `WM_ONTOP` to the top one |
| its menu bar | if the bar was its: shown again with `mn_bar` |
| its directories | the current drive and every drive's directory (`gemdos_dirsave`) |
| its workstations | stay open; they are owned by CONTEXT, and process 0's is shared, so they are kept under a marker until it runs again (`vdi_retag_virtuals`) |
| its far blocks | where they are, its own |

The desktop is never put aside: it ends, kept dormant (phase 121), as
it does to run any program.  The accessories close their windows when a
program is put aside, as they do between programs.

## What it costs

Six bytes of the window section (the record's address, a flag, and the
window manager's quiet flag: 14 left), nothing of LoRAM, and while a
program is aside one far record -- its pool blocks' size plus about
1.4 KB -- and a second 2 KB park buffer.

## Refused

A program that is not process 0, the desktop, a second program while one
is aside (step 3 makes a list), or no far memory for the record: 0, at
once, and it carries on.

## The gate

`make test-m53` (`tests/emu/m53_suspend.py`, `src/m53_app.c`); see
`docs/gates.md`.  Shown to fail: with the program loaded again instead of
resumed, and with its windows not put back.

## A B9 caught on the way

`w_save1` first built its handle word as `wh | (open ? 0x8000 : 0)` and
then took its address for `far_put` -- B9's shape exactly, and
`make qscan` refused it before anything ran (phase 125 added the rule).
