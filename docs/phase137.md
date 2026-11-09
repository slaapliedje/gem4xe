# Phase 137 -- the CPX toolkit: events

Step 3 of [cpanel-plan.md](cpanel-plan.md), its first half: what
XControl does for a module besides the form -- the events, the
rectangle list and the small calls.  Phase 138 is the widgets: `Popup`
and the sliders.

| | was | now |
|---|---|---|
| `cpx_init`'s XCPB | always 0 | the panel's, when the panel loads the module to open it |
| `cpx_hook` | never called | first, with the event; non-zero takes it |
| `cpx_m1`, `cpx_m2` | never called | for the rectangles asked for with `Set_Evnt_Mask` |
| the timer | 100 ms, the panel's choice | XControl's 30 s, or what `Set_Evnt_Mask` asks |
| `cpx_close` | every time an event CPX ended, saying nothing | when the window goes, with `keep`: 1 the closer, 0 AC_CLOSE |
| `CT_KEY` | -- | `Xform_do` answers -1 with it for a key with no character |
| `GetFirstRect` / `GetNextRect`, `getcookie`, `MFsave` | -- | in the XCPB |

## Read out of XControl's code, not its notes

Its sources (Atari's, specification only) part from its own notes and
from the Compendium in places, and where they do, what real modules ran
against is the code:

- **`cpx_close`'s flag** is FALSE for the window's closer and TRUE for
  AC_CLOSE in the code; the notes and the Compendium say the reverse.
  So the parameter block has `keep` -- 1 for the closer, keep what was
  set, as OK; 0 for AC_CLOSE, put it back, as Cancel -- which cannot be
  read backwards.
- **`cpx_close` comes when the window goes**, not when a module ends
  itself.
- **The timer always runs** -- 30 seconds unless asked -- whatever the
  mask; only the mouse rectangles depend on it.  `Xform_do` ignores the
  mask.
- **`MFsave`** does not read the MFORM its prototype takes: it is
  `graf_mouse` M_SAVE / M_RESTORE, which this AES serves.
- **`GetFirstRect`** hands back a piece the area misses with a width of
  0 or less; this passes over it, which a caller that checked still
  works with.
- **XControl takes the update lock around its whole dispatch**, and a
  hook that takes an event leaves it held.  The panel takes it only to
  draw.

## How the XCPB gets to cpx_init

The AES loads a module that asks to be booted before the panel exists,
so at boot `cpx_init`'s block is 0, and the panel hands its block over
at `cpx_call` with `booting` set, as before.  When the panel loads a
module to open it, it first writes its block's address into the first
four bytes of the slot header's `reserved`, and the kit's glue
(`src/app/cpxmain.c`) reads it back for `cpx_init` -- so a module ported
from the ST, whose `cpx_init` calls the toolkit, finds it there.

## The calls

Each is a one-block callback, as cpx.h's ABI requires, with an inline
in cpx.h that reads like XControl's call: `cpx_set_evnt_mask`,
`cpx_first_rect` / `cpx_next_rect`, `cpx_getcookie`, `cpx_mfsave`.  A
MOBLK is copied field by field, since a near <-> far struct copy over
eight bytes is an internal compiler error (B11).  `getcookie` answers 0
for every cookie, honestly: this machine has no jar.

General and Color now end only on WM_CLOSED and AC_CLOSE; a CT_KEY goes
by them.

## Gate

`test-m58`, new.  The gate module (`src/m35_cpx.c`) goes onto the shots
disk a second time as FORM.CPX, its header's buffer starting 'F'
(`tools/mkcpx.py` takes a `buffer` field now), and counts what the panel
does for it into its own 64 settings bytes -- the buffer in the AES's
table, which outlives the module when it is freed -- where the gate
reads them.  Opened, TEST.CPX had its XCPB at `cpx_init`, drew through
the rectangle list, heard there is no 'NVDI', had `MFsave`; the pointer
onto its box is a `cpx_m1` and its 50 ms timer ticks; the hook takes the
key 'h' and `cpx_key` never sees it; the closer brings `cpx_close` with
keep 1.  FORM.CPX gets CT_KEY for Help and goes on, ends on its Done
button, and ends again on the closer with WM_CLOSED.  Fails with
`Set_Evnt_Mask` doing nothing, with no CT_KEY, and with no hook.

test-m44 and test-m42 count four modules now.
