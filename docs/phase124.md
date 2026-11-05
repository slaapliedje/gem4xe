# Phase 124 -- AES 4.0

gem4xe told programs it was AES 1.40, TOS 1.04's, until now -- so a
program written for the ST's later AESes kept its AES 4 code switched off:
no `appl_getinfo` (stock gemlib and cflib ask only from 4.0, or when
`appl_find("?AGI")` answers), no `AP_TERM` registration, no `appl_search`.
gem4xe already had much of AES 3.40 -- the Falcon's 3D objects, colour
icons, popup menus, `objc_sysvar`, `appl_getinfo` itself -- and phase 123
added the shutdown.  This phase does what a program does on seeing 4.0,
and only then says 4.0.

## What 4.0 promises, and what it does not

`global[0]` is `0x0400`.  `global[1]` stays **1** -- one application at a
time, where MultiTOS says -1 -- and `appl_getinfo(AES_SHELL)` already says
`shel_write(1)` runs the program when the caller ends.  So a program can
tell it is on a single-tasking AES 4, as it could on MagiC in single mode.
`global[13]` and `[14]`, present from 4.0, are the largest and smallest
character heights the AES draws with: one face here, so both are its cell
height, as `AES_LARGEFONT` answers.  And `global[2]` is now the caller's
id for an accessory too; it said 0 for every process.

## The calls

| call | | |
|---|---|---|
| `appl_search` (18) | new | the processes, one a call: the application is `APP_APPLICATION`, and `APP_SHELL` too while it is the desktop (`sh_desk_running`); an accessory `APP_ACCESSORY`; 1 with an answer, 0 when there are no more.  No system process: the AES here is not one |
| `appl_find` | AES 4's forms | NULL is the caller; an upper word of `$FFFF` or `$FFFE` converts between MiNT and AES ids -- the same number, there being no MiNT.  **Only a NULL pointer means "me"**: every bank-$00 string has a zero upper word on this machine.  A `const char *` cannot carry the 32-bit forms, so the kit's binding cannot say them; a raw call can (`src/m51_app.c`) |
| `menu_register` | an application's title | takes **no Desk slot** -- it took one and never gave it back, and the Desk menu then pointed into freed memory -- and is kept (`mn_apptitle`) for a switcher's list, forgotten when the next program starts; the answer is 6, a menu id no accessory has.  `REG_NEWNAME` (-1) renames the caller's process for `appl_find` and `appl_search` |
| `menu_bar(0, MENU_INQUIRE)` | new | whose bar it is, or -1 -- answered before the ABI's check for a tree, which this call has none of |
| `rsrc_rcfix` (115) | new | a resource the program holds -- the `.RSC` file's bytes in its own memory, any bank -- fixed up and made its resource, as `rs_load` makes a file's; the images stay where they are and `rsrc_free` gives nothing back (the slot's mark is past the pool's top).  Refused: a third resource, and colour icons, whose extension `rs_cicons` reads from the open file.  Answers 1, as MultiTOS's dispatcher does; the Compendium's "0 is success" is the opposite of every other call |
| `wind_get(WF_TOP)` | three words | the top window, its owner's id, the window below |
| an opcode not served | 0 | it was -1, which a caller testing for success reads as done |

`appl_getinfo` follows: `AES_PROCESS` 0, 1, 1, 1; `AES_INQUIRE`'s third
word (the inquiry); `AES_WINDOW` bit 0 beside bit 6.  **gem4xe's own
subject, the control panel's table, moved from 64 to `0x4734`** ("G4"):
64 is gemlib's `AES_EXTENDED`, and a program asking it about extended
shutdown got the CPX table.  64 now answers FALSE.

## A compiler bug, found by the gate

`appl_search` first answered type 0 for both processes.  The code was

    type = (p == proc_app)
           ? (WORD)(APP_APPLICATION | (sh_desk_running() ? APP_SHELL : 0))
           : APP_ACCESSORY;

and cc65816 5.18.2 at -O2 computed the application's value into the
stack slot at `1,s`, then read the result from `7,s` where both arms meet
-- and reused `1,s` as the next loop's counter.  As an `if`, it is right.
It is **B9**, reduced in phase 125 to `t = c ? 2 : 4; take(&t);`: a join's
value given to a variable whose address is taken (here by `far_put`) is
wrong at every -O, and `qscan.py` now refuses the shape
(`tools/ccbug/README.md`, B9).

## The programs that look at the number

| | at 4.0 |
|---|---|
| QED (`gl_gem >= 0x400`) | registers its name with `menu_register` -- now harmless -- and `AP_TERM` with `shel_write(9)`; its AV/OLGA path (`av.c`, `olga.c`) expects `shel_write(1)` to start a helper alongside it and return its id, which a single-tasking AES cannot: the helper runs when QED ends.  The port should read `AES_SHELL`'s third word |
| RetroWP (`_AESversion >= 0x0399`) | its `AP_TERM` registration is compiled out of the gem4xe build (`#ifndef GEM4XE_APP_GEM_H`); it can be gated on `appl_getinfo(AES_MESSAGE)` bit 3 now |
| the desktop, gem4xe's apps | read no version |

## The gate

`make test-m51` (`tests/emu/m51_aes4.py`): `src/m51_app.c` on the G4DOS
system floppy beside the phase 123 gate accessory and two resources, the
answers to every call above read out of it by symbol: `global[]` (and the
accessory's `global[2]`); `appl_find`'s seven forms; `appl_search`'s two
processes; `menu_register`'s 6 and the Desk menu unchanged; `REG_NEWNAME`;
the getinfo words, 64 unanswered and `AES_CPX` answered; `rsrc_rcfix`
1, 0, 0 and the menu bar as wide as `rsrc_load` makes it; the inquiry
-1, 0, -1 around its own bar; `WF_TOP`'s three words; and 0 from an
unserved opcode.  Shown to fail: with an application's title taking a slot
again, two checks; with colour icons not refused, one.  `tools/aesref.py`
models the application's `menu_register` too, so `test-m9`'s registration
case still holds the target to it.
