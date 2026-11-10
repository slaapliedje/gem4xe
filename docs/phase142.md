# Phase 142 -- the sixteen copy modes (VDI step 1)

The first half of step 1 of [vdi-plan.md](vdi-plan.md): what the VDI
drew wrong, quietly.  `vrt_cpyfm`'s destination, `vr_trnfm` and Bezier
are the second half.

| | was | now |
|---|---|---|
| `vro_cpyfm` | replace (3) everywhere, and OR (7) from a memory form on the VBXE only; the other fourteen modes copied as a replace | all sixteen, on the VBXE, ANTIC and the printer, between any two forms.  D (5) changes nothing, and a number that is not a mode copies |
| `v_opnbm` | opened a workstation on the SCREEN | refused, handle 0, until step 3 builds offscreen bitmaps |
| `vqt_name`, the system face | "gem4xe system 8x8" on every screen | the screen's cell: "gem4xe system 6x6" on ANTIC |

## One truth table

A logic mode is a truth table: bit 3 - (2s + d) of the mode is what a
destination bit d becomes under a source bit s.  So 1 is S AND D, 6 S
XOR D, 7 S OR D, 12 NOT S.  The driver applies it as one function,
`rop4` in `src/vdi/vdidev.h`, to every bit of a pixel at once.  The
model does not use that arithmetic.  `tools/devref.py`'s `ROPS` writes
the sixteen out one by one from the TOS definitions -- `~(s | d)`,
`s | ~d` -- so the driver and the model cannot agree by being wrong the
same way.

## On each device

- **The VBXE.**  A plain copy keeps its paths: the blitter for the
  screen, the rows and the nibble shifter for the rest.  A logic mode
  goes a row at a time through `copy_rows`, which reads the source's
  row and the destination's, combines them a nibble at a time, and
  writes the result.  That loop used to OR, and only from a memory form.
  It now does every mode and every pair of forms, and keeps the order
  that lets a rectangle overlap itself: rows from the bottom and chunks
  from the right when the destination is below or to the right.
- **ANTIC and the printer.**  Each already had a pixel loop for copies
  between forms.  A logic mode now runs through it, each source bit
  combined with the destination's.  The byte paths are for plain copies.

The plan had the VBXE blitter do each mode in one or two passes.  That
is a speed-up, and it belongs to step 2.  Step 1 makes every mode right
on every pair of forms first, and that is what a blitter version will
be checked against.

`make mscan` found a B12 in the new row loop: a nibble taken from a
signed word by `>> 4`.  The loop's values are unsigned now.

## v_opnbm

`v_opnbm` is `v_opnvwk` with sub-function 1.  It is EdDI's, and the
Compendium does not have it.  gem4xe ignored the sub-function and
opened an ordinary workstation, so a program asking for a bitmap drew
on the screen believing it drew off it.  The call is refused now, as a
VDI without EdDI refuses it, and the program can fall back.  gem4xe's
binding sets `contrl[5]` on every call (`src/app/gemlib.c`), so a 1
left there by a `v_bar` is never read as a request for a bitmap.

## The face's name

`vqt_name` answers the system face's name with its cell, taken from the
device in use: 8x8 on the VBXE and the page, 6x6 on ANTIC.  The digits
go into the answer's words, and the name itself stays a constant.  A
writable copy of it cost LoRAM 18 bytes, and the host test of the
memory budget (`tests/host/test_memory.py`) caught it: 240 bytes free
against the 256 the engine keeps.

## Gate

- **`test-m3`** gains one case per mode.  The source is two pens side by
  side and the destination two pens one over the other.  Each pair is a
  pen and its complement (5 and 10, 3 and 12), so at every one of the
  four bits S and D are each both 0 and 1 against the other.  The copy
  lands at an odd x with an odd width.  Three more cases follow:
  - XOR from a memory form onto the screen;
  - AND from the screen into the form;
  - XOR, then S OR NOT D, each onto its own rectangle moved by odd
    amounts and wider than a row chunk.

  A system op opens a workstation by sub-function: 0 gets a handle, and
  1, `v_opnbm`, gets 0.  332 cases over the three widths.
- **`test-m25`** copies with XOR and AND on ANTIC's one-bit screen, and
  reads back `vqt_name`'s answer, "gem4xe system 6x6".
- **`test-m30`** copies with XOR and NOT S on the printer's page.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| two terms of the truth table swapped | modes 2, 4 and 10-13 fail |
| the safe order turned off for logic modes | the overlapping case: 2,580 pixels wrong |
| the refusal removed | sub-function 1 gets handle 2 |
| the name's digits not written | ANTIC's face is called 8x8 |
