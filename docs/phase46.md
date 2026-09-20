# Phase 46 -- the last ten opcodes, and 79 of 79

`tools/opcodes.py` audits what the ENGINE serves rather than what the
kit declares, and after Phase 45 it had ten names left.  This phase
closed them.  The AES now serves every opcode it has: **79 of 79**.

The goal was never the number.  It was that a program ported from an ST
should not stop on a call this AES had simply never got round to -- and
a refusal is the worst kind of missing feature, because it arrives at
run time in somebody else's program.

The ten: `appl_read` (11), `appl_tplay` (14), `appl_trecord` (15),
`menu_popup` (36), `menu_attach` (37), `menu_istart` (38),
`menu_settings` (39), `scrp_clear` (82), `shel_rdef` (126),
`shel_wdef` (127).

## Three of them are not Atari's calls at all

Worth saying plainly, because "the AES serves all 79" could otherwise
imply a fidelity that is not the claim.

**`scrp_clear` (82) is PC-GEM's.**  The Falcon ROM's `CRYSBIND.H`
declares `SCRP_READ` 80 and `SCRP_WRITE` 81 and stops; the Compendium
documents the same two and gives 82 no reference page; EmuTOS serves it
only under `CONF_WITH_PCGEM`.  A program ported from an ST will never
call it -- the Compendium's own cut recipe tells the *application* to
delete `SCRAP.*` itself, because on an ST there is nothing else it
could do.  It is served here for gem4xe's own desktop, and for a program
that asks.

**`shel_rdef` (126) and `shel_wdef` (127) are not Atari's either.**  The
Falcon ROM puts `SHEL_SPATH` at 126 and never dispatches it; 127 is not
in the header at all; the Compendium's binding table leaves both blank.
The only place Atari's own documentation admits they exist is
`appl_getinfo`'s `AES_PCGEM` subject, whose fourth word asks whether
they are implemented -- which is why that word is now 1.

They were served rather than stored because **both halves actually do
something**, which was not a given.  The directory is where the desktop
is run from in place of the system's -- exactly what the donor's
`sh_chdef` does for `DESKTOP_APP` -- and the name is the program the
shell runs as the desktop.

## A real bug found on the way in

`appl_read` (11) could not be written without looking at `appl_write`,
and `appl_write` was wrong in both directions: it copied eight words
**whatever length it was told**.  A longer message lost everything past
the first sixteen bytes in silence; a shorter one was read past the end
of the caller's buffer.

Both calls now take sixteen bytes and refuse anything else, and that
refusal is a deliberate divergence.  The donor's queue is a 128-byte
buffer with a byte count, so its `ap_rdwr` blocks for any length.
gem4xe's is slots of eight words, because **the window manager
coalesces** -- a second `WM_REDRAW` for a window already waiting is
unioned into the one already in the queue -- and only something that
knows where a message begins can do that.  The pipe is messages, not
bytes, and the length check is the price.

## The menu calls, and what was read rather than copied

**`menu_popup` (36)** is the drop-down machinery with the bar taken
out: the same `menu_sr` to save what it covers, the same `ob_draw`, the
same `menu_select` to move the highlight.  `appl_getinfo(AES_MENU)` now
answers 1 for popups, and still 0 for sub-menus and scrolling.

One divergence: **the box is clamped to the screen in both
directions.**  The ROM clamps neither -- `AdjustMenuPosition` takes a
horizontal flag that only the submenu path sets.  An unclamped popup is
the `menu_sr`/`bb_save` landmine in a new place, and this tree has
already paid for that once.

**`menu_attach` (37)** gives an item a menu of its own.  The mark is
the ROM's exactly -- a right-arrow character two bytes from the end of
the item's own string, the `SUBMENU` flag in `ob_flags`, the slot
number in `ob_type`'s high byte from 128 up -- so a tree marked here
reads the same to anything that inspects it.

That also means it **writes into the application's string**, as the ROM
does.  The ROM never checks the length.  This one does, because the
check is two lines and the alternative is a corruption in somebody
else's memory.

`MN_SELECTED` now carries words 5, 6 and 7 -- the tree the item came
from and the box it is a child of, as MultiTOS's `GEMCTRL.C` sends
them.  Not an extension for its own sake: with a submenu the item may
not be in the tree the application thinks it is.

**`menu_settings` (39)** is five numbers the AES runs its sub-menus by.
Four of them this machine cannot act on -- no drag tracking, nothing
scrolls -- so they are kept, clamped the way the ROM clamps them, and
handed back.  A program that sets one and reads it back is told the
truth rather than the default.

**The fifth is live, and it is why the call is served rather than
stubbed.**  Until now a submenu opened the instant the pointer reached
its item, and the comment in `menu.c` defended that by saying a delay
nobody could change was only in the way.  `menu_settings` *is* the way
to change it, so the ROM's display delay is back: `MU_TIMER` armed in
`INITEM_STATE` with `mn_display`, and the submenu opens on the tick.

The argument is worth keeping: a behaviour that cannot be configured
and a behaviour that can are different features, and serving the
configuration call changed which one was correct.

## The tape, and a struct measured rather than assumed

**`appl_trecord` (15)** files the AES's own input into the caller's
`EVNTREC` array; **`appl_tplay` (14)** plays it back.

The ROM does this through its fork queue -- `ap_trecd` sets `gl_recd`
and the forker files every post.  gem4xe has no fork queue, so the
three places input actually *arrives* do the filing: the VDI's motion,
button and timer vectors, and the one call that takes a key.

`EVNTREC` is the Compendium's, six bytes with a LONG at offset two.
That it **is** six was read out of the generated code rather than
assumed, because this compiler pads some structs to four
(`calypsi-pads-structs-to-four`) -- `sizeof` and an array bound are two
different numbers here, and a tape format that disagreed with the
caller's array by two bytes per record would have been a slow thing to
find.

A follow-up commit says why 0 is a safe "no key" for the tape rather
than leaving it to be re-derived.

## Where it left the disk

The ten opcodes put the DOS 2 floppy at 52 sectors against a floor of
64, and **the floor moved rather than the code** -- for the third time,
which is what finally settled the question instead of the number.

That floppy is a third-party-DOS tester.  A DOS 2 cannot read
`gem-apps.atr`, so nobody puts a program of their own on it; the way in
is `INSTALL.BAT` and a drive.  The floor had been guarding a use the
tree had already written off, which is why it produced a conversation
every two hundred bytes.

It guards one real thing now: `DESKTOP.INF`, which is what a *person*
can write to that disk when they arrange the desktop and save it.  Its
size is bounded rather than guessed -- `inf_write` builds the text in
the shell buffer and `SIZE_SHELBUF` is 4,192 bytes, seventeen
double-density sectors plus one for the directory entry.  **The floor
is 20**, and the rest of the margin was given back.
`docs/shipping.md` carries the full reasoning.
