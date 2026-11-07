# Phase 130 -- the Desk menu's list of programs

Step 4 of [switcher-plan.md](switcher-plan.md), its other half: while a
program besides the desktop is loaded, the Desk menu lists every program,
the desktop first and then the order they were started in, with the one
in front checked.  Choosing one switches to it, as CONTROL-TAB does
(phase 129).  The desktop on its own keeps the Desk menu its resource
drew, exactly as before.

## MultiTOS's shape

MultiTOS's `menu_bar` builds the Desk drop-down in an object array of
the AES's own and draws and tracks that in place of the program's Desk
box (`GEMMNLIB.C`'s `mn_addr`; `MN_MBAR.C`, `imenu == gl_cdabox`, read as
specification).  Its rows are the program's About line, a line and the
accessories, then a line and every application, with the one that has
the keyboard `CHECKED`.  gem4xe does the same (`src/aes/menu.c`,
`dt_build`):

| | |
|---|---|
| built | when the Desk title drops, in far memory, the system's; freed when the menu goes up |
| when | only while a program besides the desktop is loaded (`sh_nprogs`): with the desktop alone nothing is built, so every gate and picture of the desktop's menu is unchanged |
| its box | the resource's Desk box, where it is and as wide; About and the line are the resource's own objects, copied |
| tracked | `mn_do` keeps the tree that holds the open drop-down's items (`itree`) beside the bar's; every item lookup, highlight, save and restore uses it |

What a choice does is kept beside each row:

- **About** reaches the program as `MN_SELECTED` for its own About item.
- **An accessory** gets `AC_OPEN` with its own menu id.

`hctl_rect` sees both as if they came from the resource's box.

- **A program** is asked for (`sh_request`) and switched to at the next
  poll that may, the way the key is (`sh_hotkey`). A choice is kept
  until then rather than dropped, because the menu ends with the button
  still down. It is checked against the ring when acted on.
- **The one in front** does nothing.

At the desktop the choice reaches the desktop as **`AP_G4SWITCH`** with
msg[3] 0 and the program's eight characters in msg[4..7].  The desktop
passes them to `shel_write(SWM_G4SWITCH, 0, 0, name, "")`.  `isgr` 0 is
new: switch to the program `cmd` names, for any program.

## Each program's name

Each row shows the title the program gave `menu_register` (phase 124),
or else its own eight characters.  The desktop's row is `LANG.RSC`'s new
`MENU_DESKTOP`, "  Desktop" (Bureau, Escritorio, Pulpit), the first of a
new kind of string: a menu line, two spaces where the check mark goes
and a title's 23 columns, which `tools/langrsc.py` and `test_lang`
check.  A program put
aside keeps its title in its record (`SU_TITLE`), a copy, because the
string may be in its own bank-$00 memory, which is not there while it is
aside.  It also keeps the pointer (`SU_TPTR`), which is valid again when
it runs: `mn_init` forgets the title between programs, and resuming puts
it back.

## Found on the way

**Two programs aside shared their workstations.**  A program put aside
keeps its VDI workstations open, re-tagged from process 0's context to a
marker until it runs again (phase 127).  There was one marker, which is
right for one program aside and wrong for two.  Resuming either one
re-tagged both programs' workstations to process 0, the context every
program runs in.  When that program ended, `vdi_close_virtuals` closed
the other's under it, and the other came back drawing through handles
that were no longer open.  It was a bug since phase 129, invisible to
`test-m54` because its program opened no workstation.  The marker is now
the program's owner: a number no context's address can be (they are all
above $2000) and one no other loaded program has.  The program opens a
workstation now, and `test-m54` checks every loaded program's after
every switch.  The running one's must be process 0's, and each one
aside must be under a marker of its own.  With the single marker put
back, the check fails.

`ring_find` named process 0 after the program it looked for: it called
`proc_name(proc_app, cmd)` to normalise the name.  That was harmless
when the shell was the only caller, between programs.  But with
`shel_write(SWM_G4SWITCH, 0, ...)` a running program asks, and
`sh_suspend` then saves `proc_app->p_name` into the record.  The program
put aside would have been filed under the name of the one it switched
to.  `proc_nameto` normalises into the caller's buffer now.

## What it costs

Four bytes of the window section (`sh_want`; eight left), the
`LANG.RSC` string, and while the Desk menu is down a far block of 644
bytes: 17 objects, a word of meaning each, and seven titles.

## The gate

`make test-m55` (`tests/emu/m55_desklist.py`), with two copies of
phase 127's program (`src/m53_app.c`).  Asked, each puts up `EDIT.RSC`'s
menu bar and registers "  Gate N".  M50.ACC is installed, and now counts
its `AC_OPEN`s.  The gate reads the list out of far memory while it is
down, and checks:

- the desktop alone builds no list;
- in a program, and on the desktop with a program aside, the rows are
  About, the accessory, then Desktop and the programs in order, with the
  one in front checked and an aside program under its own title;
- choosing the desktop from a program, a program from the desktop, and
  one program from another each switches, with the menu bar back;
- About reaches the program as its own About item, and the accessory
  gets `AC_OPEN` with its slot;
- the list's block is gone after every menu.

Shown to fail four ways:

- **The list's block never freed**: four failures.
- **The title not kept** in the record: the desktop listed "  M54A".
- **The running program first** instead of the desktop: the order was
  wrong in every list.
- **About mapped to the line under it**: the program was sent item 8,
  not 7.

## Not yet

- Closing a program from the list (MultiTOS: CONTROL held while
  choosing; here SHIFT, since POKEY cannot report CONTROL on its own),
  and quitting the desktop with programs aside: phase 131.
- What was short (step 5): phase 132.
