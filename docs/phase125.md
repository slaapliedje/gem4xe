# Phase 125 -- AES 4's window messages

Three messages an AES 4 program may be told about its windows, which
gem4xe declared and never sent, and one window mode it set and never read.
They are MultiTOS's (GEMWMLIB.C, GEMDISP.C and GEMCTRL.C, read as
specification), and `appl_getinfo` now says so.

| | sent | |
|---|---|---|
| `WM_UNTOPPED` (30) | to the owner of the window that was on top, when another is **opened or topped over it** -- even by the same program | not when it closes or goes to the back |
| `WM_ONTOP` (31) | to the owner of the window now on top, when the top window **closed or went to the back** -- even when that program did it | not when a window is topped or opened: topping never sends it |
| `WM_BOTTOMED` (33) | Shift held and a window's frame clicked: the one behind, or the top one's mover | the program answers `wind_set(WF_BOTTOM)`, as it answers `WM_TOPPED` with `WF_TOP`; gemlib's other name for it, `WM_BOTTOM`, is in the kit too |
| `wind_get(WF_NEWDESK)` | the desk's tree, high word first, and its root | as `wind_set` takes them |

**Which message depends on how the top changed, not on who changed it**
-- MultiTOS's rule (`w_top` sends the first, `wm_close` and `WF_BOTTOM`
the second).  The first version of this phase had "WM_ONTOP unless its
owner did it", and its own gate agreed with it.  The suite's desktop and
window gates then fell out of step, because their models (`tools/aesref.py`,
`tools/deskref.py`) knew neither message; writing the rule into the model
meant reading MultiTOS's source for it, and that found the first version
wrong (the "model and target agreeing wrongly" lesson, again).

Both come from one place, `w_topchanged` in `src/aes/wind.c`, called
where the top changes: `draw_change2`, which every open, close and top
goes through, and `wm_mkbottom`, which says it bottomed.  Whether the old
top was covered or went away is read from the window tree, not from
`VF_ISOPEN`: `wm_close` clears the flag only after its redraw.  The Shift
is read where the control manager takes the press (`hctl_window`,
`src/aes/ctrl.c`) with `gsx_kstate()`: either Shift key, POKEY's own.

`appl_getinfo`: `AES_MESSAGE` adds bits 1, 2 and 6 to phase 123's 3 and
4; `AES_WINDOW` adds bit 1 (`WF_NEWDESK` get) to bits 0 and 6, and its
third word says Shift-click sends to the back (bit 2).

## The gate

`make test-m52` (`tests/emu/m52_winmsg.py`): `src/m52_app.c` with two
windows, A under B, logs every window message it is sent and answers
`WM_TOPPED` and `WM_BOTTOMED` as an AES 4 program does; the gate
accessory (`M50.ACC`) can now open a window of its own and close it; and
the gate holds the real Shift key in POKEY's matrix (`KEYRAW`) for a click.

Every step checks the whole log, not its first message:

1. `appl_getinfo`'s new bits, and `WF_NEWDESK` read back as set.
2. The program tops A: B is told `WM_UNTOPPED`, nobody `WM_ONTOP`.
3. The accessory's window opens over A: A `WM_UNTOPPED`.  It closes: A is
   uncovered, `WM_ONTOP`.
4. B clicked from behind: `WM_TOPPED`; topped, and A `WM_UNTOPPED`.
5. Shift and B's mover, B on top: `WM_BOTTOMED`; answered with
   `WF_BOTTOM`, A is uncovered and told `WM_ONTOP`, B nothing.
6. Shift and B at the back: `WM_BOTTOMED`, not `WM_TOPPED`, and nothing
   else -- the top did not change.

Shown to fail: with both messages sent on every change, steps 2 and 4;
with the bottoming not told apart, step 5; with the Shift ignored, step 6.

## Not yet: iconify, and why

Iconify -- the `SMALLER` gadget, `WF_ICONIFY` / `WF_UNICONIFY` /
`WF_UNICONIFYXYWH` and `WM_ICONIFY` / `WM_UNICONIFY` / `WM_ALLICONIFY` --
is AES **4.1**, not 4.0, and a program finds it through `appl_getinfo`
(`AES_WINDOW` bits 7 and 8, `AES_MESSAGE` 7 to 9), which says no.  MultiTOS
is the specification (`GEMWMLIB.C`, `GEMCTRL.C`: a 72 x 72 icon in a slot
along the desk's foot, the window's kind cut to NAME and MOVER, the old
rectangle kept for `WM_UNICONIFY`, a double-click on its title to bring it
back).

**Bank $00 is what stops it.**  `W_ACTIVE`, the gadget tree, is in the
window (`zwin`), which has 20 bytes free -- a twentieth object is 24 --
and the iconified state is a few words per window in `gl_win`, which is in
LoRAM, at its 256-byte floor (`make memcheck`, 2026-11-04).  Making room
is moving one of those tables to far memory, where every frame drawn
reaches it through a far pointer, or finding the bytes elsewhere; either
is a phase of its own, and a program without iconify loses nothing it
did not ask `appl_getinfo` about first.
