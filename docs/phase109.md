# Phase 109 -- QED beside the accessories

Two reports, from the user's machine and a tester's: in QED, File > Open...
did nothing, and File > New text opened a window that was a stub in the
top-left corner, which could not be resized.  QED's own gate passed on 0.12.
Its disk carries no desk accessories; the product's carries three, and two
control-panel modules.

## Reproduced

The QED gate (`make check` in the port) on a disk that also carries
CLOCK.ACC, CONTROL.ACC, CALC.ACC, GENERAL.CPX and COLOR.CPX, as the card and
the floppies do: QED started and took typing, then Save as... and Open...
never brought the selector up (no names in its list, nothing saved), and
every window QED opened was the stub.  On the gate's own disk, everything
passes.  Renaming QED.PRG (to sort it into the desktop window's first
screenful) alone changed nothing.  The accessories were the difference,
and they cost QED two separate things.

## 1. The file selector's tree came out of the pool

`fs_input` copied its 1,780-byte tree and its 320-byte work area into the
application pool every time it opened (phase 11).  With the accessories
resident a launched program gets 6,912 bytes of the pool
(`tools/memreport.py`), and QED's near region takes 6,144: 768 left, read in
the machine while QED ran (`pool_brk` $7D00, `app_pool_hi` $8000).  The
selector asked for 2,100, got nothing, and answered FALSE with nothing
drawn, as its header comment says it does.  QED did nothing, correctly.

QED cannot give the room back.  Its 6,144 is 4,096 of stack and its near
data; a snapshot of the near region before and after the gate's whole run
(edit, save, open, a shortcut) shows the stack written down to offset 705
of the 4,096, and possibly to its very bottom.

**The tree is far now.**  `fs_start` takes a far block of `FS_RSC_SIZE`
once, beside the 64 name slots it already took, and each opening copies
the tree into it and fixes it up there (`rs_fixit` works through 32-bit
addresses already, which is how an application's far resource is fixed).
A far tree's TEDINFO strings are 32-bit, and the drawing and editing code
already reads them that way -- QED's own 33 KB resource is drawn and
edited from far memory.  What the selector itself read or wrote of its
strings through near casts goes through `far_strget` / `far_strput`:
`inf_sset`, `inf_sget`, `dir_sset`, `path_changed`, the title's width, and
the typed directory line and file name, which use the work area's spare
line as their near copy.  The pool now gives the selector only its work
area, 320 bytes.

## 2. Four workstations, and five wanted

QED's window size is its font's cell size times a number of rows and
columns (`src/edit.c`, `crt_edit`), and the cell size comes from its own
virtual workstation.  The VDI had four: the physical one and three
virtual.  Read in the machine while QED ran: one held by the clock
accessory, which keeps its own for the life of the machine, and two by
the running program's context -- the desktop's and QED's.  QED's CF-Lib
opens one more.  One `v_opnvwk` got handle 0, and a font query on handle
0 answers nothing, so the window was zero rows of zero columns, plus its
frame.

**Eight now, and the table is far.**  A `Vwk` is about 92 bytes, and the
four lived in `zwin`, which had 12 to spare.  The VDI already works on
one live copy, `vwk`, and copies to and from the table only when the
drawing changes hands (phase 104 made the common case not even look at
the table).  So the table moved to a far block taken by `v_opnwk`, and
only each slot's handle and owner stay near, in `zwin`, where the old
table's 368 bytes were.  `vwk_save` and `vwk_load` are `far_put` /
`far_get` of one record.  Until `v_opnwk` has run there is no table and
no virtual workstation -- a program that uses the VDI without probing
far memory (the ANTIC benchmark) still has the physical one, which is
`vwk` itself.  `v_clsvwk` now also clears the slot's owner.

## The check that should have spoken

`tools/memreport.py` checked that QED's near region fit the room a
launched program gets.  It now also checks what the AES takes from what
is left while that program runs -- the larger of the selector's work area
and an alert's tree, strings and icon, read from `src/aes/fsel.c`,
`src/aes/alert.c`, `build/fsel_rsc.h` and `build/gemdata.h`: 650 bytes,
an alert's.  Given 0.12's selector (1,780 + 320), it fails:

    FAIL: QED.PRG leaves 768 bytes of the pool and the AES wants 2100 for
    the file selector's tree and work area (0.12): it would start, and
    then its File > Open or its alerts would do nothing (docs/phase109.md)

## Proof

- The QED gate on the disk with the accessories: Save as... lists the
  directory and TEST.TXT lands in it; Open... DOC.TXT shows its first
  line at (24, 60); Ctrl-N's window title is at (289, 41); Quit returns
  to the desktop.  Before: none of those.
- `make test`.

## Not found

The same report said Show file on GEM4XE.CFG hung the machine, on the
ANTIC screen.  The same file, shown from the same desktop with the same
accessories on the ANTIC screen, opens its viewer in the emulator, on
0.12 and on this build.
