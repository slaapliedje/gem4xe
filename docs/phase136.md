# Phase 136 -- General and Color in the window

Step 2 of [cpanel-plan.md](cpanel-plan.md), its second half.  A form CPX
runs in the Control Panel's window now, as XControl's do, through the
panel's `Xform_do` -- the first of XControl's toolkit callbacks after
`CPX_Save` and `XGen_Alert`.

| | was | now |
|---|---|---|
| General, Color | their own dialog, `form_center`'d over the panel | in the panel's window, filling its work area |
| their loop | `form_do`, which takes the screen | the panel's `Xform_do`, which does not: the desktop goes on working |
| the window while one is up | -- | redrawn, topped, moved (the form with it) and closed by the panel |
| the closer, AC_CLOSE | -- | -1 and the message: the closer keeps what was set, AC_CLOSE puts it back (XControl's rule) |
| their size | 38 columns | 32 x 20 cells, 256 x 160: the work area |

## Xform_do

`src/app/cpx.h` adds it to the XCPB with its block -- the tree, the field
to start in, the answer and the message -- and `cpx_xform_do`, an inline
that fills the block, calls, and hands back what came, so a module writes
`cpx_xform_do(xcpb, tree, edit, msg)` as an XControl module writes
`(*xcpb->Xform_do)(tree, edit, msg)`.  The callbacks keep the one-block
ABI cpx.h explains; the inline is what makes it read like a call.

The panel's `cp_xform_do` (`src/apps/cpanel.c`) is form_do's loop
(`src/aes/form.c` fm_do) with what is around it changed.  It does not
take the screen -- no `fm_own`, no `BEG_UPDATE` while it waits -- so the
window's own messages come to it between a person's clicks: a redraw is
the form through the rectangle list, a move moves the tree's root with
the window (the module reads its place back from `tree[ROOT]`), WM_SIZED
refits, and the closer and AC_CLOSE come back to the module as -1 with
the message.  Presses and keys reach it only while the window is on top
(phase 134), so `form_button`, `form_keybd` and `objc_edit` draw on a
window nothing covers, each inside the screen lock.

A module whose panel has no `Xform_do` -- an older one -- has nowhere to
put a form, and returns; `cpx_xform_do` answers 0 then.

## General and Color

Both size their tree's root to the rectangle `cpx_call` gives them and
draw it there, frameless: the window is the frame.  `tools/generalrsc.py`
and `tools/colorrsc.py` lay them out in 32 columns.  General's "Instant"
is "None", which with the 3D look's cell between buttons is what fits the
delay row; Color's sixteen swatches are 14 pixels each rather than two
cells, written as cells and pixels since a rectangle word carries at most
128 pixels past its cells.  Color's columns are named, and test-m42
clicks by the names.

## Gates

- `test-m44`: General opens in the window -- its OK at the work area's
  foot; the window is dragged with General up and Look -> 3D clicked
  where it now is switches the look; the list comes back over the form.
  Fails with Xform_do not moving the tree's root.
- `test-m42`: Color in the window, placed from the panel's work area and
  Color's named columns, the red swatch red where they say; Cancel, OK,
  and the palette back after a cold reset as before.
- `make shots`: General and Color in the window, `12-color-cpx.png` new;
  the pictures after it renumbered.
