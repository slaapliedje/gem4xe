# Phase 76 -- Help and Undo: the 1200XL's function keys

The ST has Help and Undo keys and GEM programs answer them -- QED runs
its help on Help (`menu.c`, scan `$62`) and undoes the last edit on Undo
(`tasten.c`, `NK_UNDO`, scan `$61`).  The Atari 8-bit has neither, but
the 1200XL has four function keys that almost nothing uses, and every
XL and XE has a HELP key that gem4xe threw away (its entry in the OS's
key table is above `$80`, which `kb_translate` drops).

    1200XL F1   KBCODE $03   ->  $6200  Help
    HELP        KBCODE $11   ->  $6200  Help
    1200XL F2   KBCODE $04   ->  $6100  Undo

`kb_translate` (`src/vdi/vdi.c`) catches them by the code, before the OS
table, in every row: the ST's Help is Help with SHIFT held too.  Being
below the AES, it is every program's without a change to any of them.
F3 and F4 are left alone: they are not the ST's F3 and F4 while F1 and
F2 are something else, and nothing asks for them yet.

The codes are Altirra's (`ui_keyboard_customize_tables.cpp`: F1 `$03`,
F2 `$04`, F3 `$13`, F4 `$14`), and the bridge presses them by name.

`make test-m7` case 2 presses F1, F2, HELP and SHIFT-F1 through POKEY
and checks the word `evnt_keybd` hands back.  On the VDI before this
change it fails: the keys never arrive.

Not done: the desktop does nothing with either key.  The Falcon's
desktop opens a list of its keyboard shortcuts on Help (`DESKMENU.C`)
and stops a copy, a delete or a Show on Undo (`DESKACT.C` `ch_undo`);
gem4xe's copy and delete cannot be interrupted at all yet.
