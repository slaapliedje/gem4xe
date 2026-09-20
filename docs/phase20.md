# Phase 20 — the bindings an application actually links against

The engine has served a large surface for some time: 130 VDI opcodes
with six no-ops among them, about sixty AES calls, and GEMDOS behind a
third `COP` face.  The library an application links against reached
**nine** of the VDI's and about forty of the AES's.  Everything else
was reachable only by building a parameter block by hand.

That is not an API, and it is what this phase closes.

    make test-host    89 tests, seven of them the bindings.

## What went in

Every opcode the driver serves and every call the shim serves now has a
binding, in the names and the argument order the VDI and the AES have
had since 1984, so that GEM source written for an ST compiles against
`src/app/gem.h`:

- the **GDPs** as their ten names (`v_bar`, `v_arc`, `v_pieslice`,
  `v_circle`, `v_ellipse`, `v_ellarc`, `v_ellpie`, `v_rbox`, `v_rfbox`,
  `v_justified`), not as a raw `v_gdp` with a sub-function to fill in;
- the attribute setters and every inquiry (`vq*`), the marker calls, the
  raster calls with a real `MFDB` in the header, the cursor form, the
  four vector exchanges, the font calls, `vs_clip`;
- `fsel_input`/`fsel_exinput`, `objc_edit`, `form_keybd`/`form_button`,
  `graf_rubbox`/`graf_watchbox`, `menu_text`/`menu_register`,
  `appl_write`, `evnt_mouse`/`evnt_dclick`, `rsrc_saddr`/`rsrc_obfix`,
  `shel_read`/`shel_find`/`shel_envrn`;
- `Fdatime`, `Tgetdate` and `Tgettime`, which phase 16 implemented and
  the library never caught up with.

**`vs_clip` mattered more than its size suggests**: `docs/gacs.md`
measured GACS's VDI use at exactly three calls, and that was one of
them.  The first application this project exists for could not have
linked.

Four opcodes deliberately have **no** binding — 10 and 27 (cell array),
29 (the valuator) and 34 — because the driver answers them with
`v_nop`, and a binding that silently does nothing is worse than a name
that is not there.  `v_clswk` and `v_updwk` are nops too and do have
bindings, because every GEM program calls them and a screen driver has
nothing to close or write out; that is what DRI's own driver does with
them.

Two names depart from the ST, and both say so in the header: the string
device answers **one GEM key code per call** rather than a line, so it
is `v_string` and not `vsm_string`; and a vector is a `LONG` rather
than a function pointer, because a handler is 24 bits under the large
code model.

**The cost to an application that uses none of it is 61 bytes.**  The
linker drops what nothing calls: `DESKTOP.PRG` went from 28,117 bytes
to 28,178, and that is the `vdi()`/`vdi_sub()` refactor rather than the
seventy new functions.

## The gate: what a binding is FOR

A binding's whole job is to fill a parameter block — the opcode, the
sub-function, and the counts that say how many words travel in and out.
gem4xe reads those counts to decide how much to copy (`src/sys/abi.c`),
so **a binding that miscounts loses an argument**, silently, with
nothing in a compile or a link to say so.  Seventy new functions
written from a specification is exactly the shape of work where that
happens.

So `tests/host/test_bind.py` compiles the library for **Calypsi's own
simulator** together with `tests/host/bind_sim.c`, which replaces the
three call gates with recorders and calls every binding once.  What
each one built is read back out of the simulator and compared with a
table written from the VDI and AES contracts — the same source
`tools/vdiref.py` and `tools/aesref.py` are written from, and not from
the library.  It runs in under two seconds on the host, with no
emulator.

A second pass covers the other half of a binding's job.  An inquiry has
to read its answer out of the **right word**, and that is exactly the
shape of the defect this phase found in the driver.  So the gates
answer with a pattern -- `intout[i]` is 100+i, `ptsout[i]` is 200+i --
and the pass records what each inquiry handed back: `vqt_width` coming
back with 200, 202, 204 is the binding saying, in the record, that it
read the cell and the two deltas a point apart, as the VDI puts them.

Three more assertions keep the surface from drifting again, and they
read the sources rather than restating them:

- every function `gem.h` declares is called by `bind_sim.c`, so a
  binding cannot be added without being checked;
- every VDI opcode the driver's jump tables serve has a binding, the
  four `v_nop`s excepted by name;
- every AES opcode the shim's `switch` serves has one too.

## ⚠ What writing the bindings found

`vqt_width` returns three POINTS, and the VDI reads the two deltas out
of words a point apart: `ptsout[0]` the cell's width, `ptsout[2]` the
left delta, `ptsout[4]` the right one — which is what EmuTOS's
`vdi_text.c` writes.  **Our driver set `ptsout[0..2]` and declared
three points**, so the right delta a caller read was whatever the last
call had left in `ptsout[4]`.

The conformance gate could not see it, for two compounding reasons:
`tools/vdiref.py` had the same misreading, so both sides agreed; and a
result record carries only `ptsout[0..2]` (`vdiref.record`), so the
word in question is not compared at all even now.

Both sides are fixed to set all six words.  Nothing the gate compares
changed, which is the point: **the defect lived exactly in the gap
between what the model asserts and what the hardware returns**, and it
took writing the caller's side — from the manual rather than from the
driver — to see it.

That is the general lesson of the phase.  A reference model written
from the same reading as the code under test is a spelling checker,
not a specification.  The bindings are a second, independent statement
of the same contract, and the first thing they did was disagree.

## Debts

- The gate proves the **block** each binding builds and the **word**
  each inquiry reads its answer from -- not that the driver puts the
  right value in that word.  That is `test-m3`'s business, and it
  covers the calls the AES and the desktop make rather than the
  seventy.
- `vqt_width`'s right delta is still uncompared by any gate, because
  the result record stops at `ptsout[2]`.  Widening it is a change to
  every gate's record format, so it is written down here rather than
  done.
- There is still no packaged kit.  A `.G4A` is built by a macro inside
  this tree; an outside author needs Calypsi, `src/app/gemapp.scm`,
  three objects and `tools/mkg4a.py`, and would learn that by reading
  the Makefile.
