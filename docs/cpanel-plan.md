# A better control panel: XControl's shape, on gem4xe

Status: step 1 **built** in phase 133.  Decisions taken 2026-11-08: one
window that the open CPX fills (XControl's shape, not COPS's window per
CPX), and the 512-byte header moves in front of the module, as on the ST.

## Why

The gap test (2026-11-08) set CONTROL.ACC beside Atari's XControl 1.2
and COPS 1.07.  The modules are fine; the host is not:

| | XControl | COPS | gem4xe before this plan |
|---|---|---|---|
| shape | a window, 256x176, closer and mover | a window, and a window per open CPX | a modal dialog that holds the screen (`form_do` inside `BEG_UPDATE`) |
| the list | 4 slots of icon and coloured title, a scroll bar, 10 or more slots | an icon grid, sorted by name | 6 rows of title text, no icons, no scrolling; `CPX_MAX` 6 |
| opening | double-click; the CPX fills the window | double-click, or from a desktop | pick a row, then Open; a form CPX puts up a second dialog on top |
| managing | About, Setup (folder, 12/24 h, Reload), CPX Info, Unload, activate/deactivate (`.CPX`/`.CPZ`) | the same, saved in `COPS.INF` | none: a new CPX needs a reboot |
| clock | time and date strip, click to edit | -- | only inside General |
| toolkit | 25 entries: `Xform_do`, `Popup`, six slider calls, the rectangle list, an event mask, `MFsave`, `getcookie` | the same | `CPX_Save`, `XGen_Alert`, the buffer, `booting` |
| boot | reads 540 bytes of each file; runs only bootinit, resident and set-only modules | the same | runs every module to fill a header kept inside it (phase 118) |

Ahead of both, and kept: a module's 64 bytes are saved to a `.CFG` beside
it, not written into the module, so a module is never written while it is
loaded and works from read-only media.

Sources: XControl 1.0's release notes and the 1.2 sources from
`~/Documents/Atari/atari_src.zip` (Atari's, All Rights Reserved:
**specification only**, nothing transcribed); the Compendium's chapter 10
(with its known errata: `cpx_close` returns nothing, `cpx_m1` takes
`WORD *event`); COPS's manual.  `src/app/cpx.h` already records why the
callbacks take one block address rather than argument lists, and why
there is no stack per CPX.

## The shape

One window, titled " Control Panel ", closer and mover, opened from the
Desk menu.  A strip along the top shows the time and the date.  Under it,
the list: one slot per CPX, its 32x24 icon with `i_text` beneath and its
title beside, a scroll bar when there are more than fit.  Double-click or
Return opens the selected CPX, which then fills the work area until it
ends; the window stays a window throughout, so the desktop and other
windows go on redrawing and can be clicked.  Arrow keys move the
selection, Escape or the closer shuts the panel.

The work area is sized in character cells, not pixels: XControl's 256x176
is 32x11 cells of the VBXE's 8x16 font, and the same 32 columns fit
ANTIC's 320x192 with fewer rows -- three slots there, four on the VBXE.

## The steps

Each says how it is tested; a check is believed only once it has failed.

1. **The header in front** -- BUILT, phase 133
   ([phase133.md](phase133.md)).  A `.CPX` becomes the 512-byte header
   followed by the `.G4A`.  `tools/mkcpx.py` builds the header from a
   small text file beside each module (id, version, flags, title,
   `i_text`, colours, and the icon as a 32x24 picture of `#` and `.`), so
   an icon is drawn in a text editor and reviewed in a diff.  The AES
   scans by reading each header -- no module runs to be listed -- lays
   the `.CFG` over its buffer, and loads at boot only the modules that
   ask (bootinit, resident, set-only; a set-only module leaves the list
   after its boot init).  The loader skips the header when it loads a
   module.  `cpx_init` loses its header argument; the module no longer
   fills one.  `CPX_MAX` rises from 6 to 16, the table sized to what the
   scan found.  General, Color and the test module get icons.
   *Gates*: `tests/host/test_cpx.py` for the tool (offsets, the icon's
   bit order, a short or foreign file refused); test-m35 that a module
   with no bootinit flag is listed but not loaded at boot, and is loaded
   on open; test-m36 and test-m42 unchanged; a seventh-and-more module
   listed.  Every list of what ships changes from `.g4a` to `.cpx`:
   the Makefile's disks, `mkcf`'s APPS, `mkdist`'s SYSTEM.

2. **The window.**  CONTROL.ACC opens the window above, with the clock
   strip and the slot list, and opens a CPX inside it.  A form CPX runs
   `Xform_do`: the panel's form loop over the module's tree, placed in the
   work area, that handles redraws through the rectangle list, moves, the
   closer and `AC_CLOSE`, and keys (edit fields included), and returns as
   XControl's does (-1 with the message, the object with bit 15 for a
   double click).  General and Color move from their own `form_dial`
   onto `Xform_do`, and their trees are reshaped to the work area.  The
   panel's own double-click and sub-menu controls go: General has both.
   *Gates*: test-m44 rewritten for the window (opens, a CPX opens inside
   it, the desktop redraws around it, the closer and `AC_CLOSE` both
   end it); a gate that moves the window with a CPX open; `make shots`
   pictures of the panel and of General and Color inside it, on ANTIC
   and on the VBXE.

3. **The toolkit.**  The rest of XControl's XCPB, each a one-block
   callback in cpx.h's ABI: `Popup`, `Sl_size`, `Sl_x`, `Sl_y`,
   `Sl_arrow`, `Sl_dragx`, `Sl_dragy`, `GetFirstRect`/`GetNextRect`,
   `Set_Evnt_Mask`, `MFsave`, `getcookie`, `rsh_obfix`, and the panel's
   XCPB at `cpx_init`.  The host calls `cpx_close` for every module, with
   XControl's flag (1 for the closer, 0 for `AC_CLOSE`), and dispatches
   `cpx_wmove`, `cpx_hook`, `cpx_m1` and `cpx_m2`; `CT_KEY` reaches a form
   CPX.  Color's R/G/B steppers become sliders, to use them.  *Gates*:
   the test module grows a page per call and a gate drives each; Color's
   gate drags a slider.

4. **Managing them.**  An Options pop-up on the panel: About; Setup (12
   or 24 hour clock, Reload); CPX Info (file, version, id, the flags);
   Activate and Deactivate (`.CPX` <-> `.CPZ`, by rename: SDX 4.49e's
   rename is broken, `docs/` records it, and on that DOS the panel says
   so rather than half-doing it); Unload, which refuses a resident module.
   Settings in `CONTROL.INF` beside the modules.  *Gates*: Reload finds a
   module added after boot; Deactivate then Reload drops it; Info shows
   the header's fields.

5. **Later, if wanted.**  COPS's window per CPX, and opening a `.CPX`
   from the desktop.  Not before the above, and not without measuring
   what a second module's stack costs bank $00.
