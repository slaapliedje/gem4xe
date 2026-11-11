# Phase 148 -- offscreen bitmaps (VDI step 3)

The first item of step 3 of [vdi-plan.md](vdi-plan.md), what is not
there: EdDI's `v_opnbm` and `v_clsbm`, a workstation that draws into a
bitmap rather than on the screen.  Until phase 142 `v_opnbm` opened a
screen workstation, so a program drew on the screen believing it drew
off it.  Since then it was refused with handle 0.

| | was | now |
|---|---|---|
| `v_opnbm` on the VBXE | refused, handle 0 | a workstation drawing into a bitmap in VRAM, the MFDB filled in |
| `v_clsbm` | -- | closes it and gives the bitmap back |
| `v_opnbm` on ANTIC | refused | refused: bank $00 has no room for a bitmap |
| the screen after a virtual workstation closed | drawn through the closed one's device | the screen's |
| the pointer while another workstation is current | drawn by that workstation's device | always the screen's |

## In VRAM

A bitmap lives in VRAM nothing else uses: `VR_BM0`, which is
`VR_SCREEN1` and was only ever written by test-m2, and `VR_BM1`, the
first page after the bold glyphs.  Each holds a whole screen of the
widest overlay, and `dev_vbxe.c` checks at compile time that they clear
what is beside them.  Being VRAM, a bitmap is drawn by the same blitter
as the screen, and a `vro_cpyfm` between the two is a blit, or the
CPU's row path at differing parities.

## A workstation with its own device

The device table has two new fields at its end:

- `surface`, the VRAM address every primitive draws at;
- `bitmap[2]`, the slots a bitmap may have (0 on ANTIC and the page).

The VBXE device's drawing primitives draw at `SURF`, the current
device's surface, where they named `VR_SCREEN0`.  The pointer's save and
restore do not, and stay on the screen.

`v_opnbm` makes a far copy of the screen's table with the bitmap's width,
height and surface, and opens a workstation on it, as a printer
workstation is opened on the page's table.  Every primitive then draws
into the bitmap and clips to it without knowing.  `vro_cpyfm` with a
screen MFDB (fd_addr 0) on that workstation means the bitmap, as EdDI has
it.

## What gem4xe offers of EdDI

- **The VDI allocates the bitmap** (the MFDB's `fd_addr` is 0); a
  bitmap in the program's own memory is refused.
- **Its size** is `work_in[11]` and `[12]`, each one less, or the
  screen's when they are not given.  No bigger than the screen.
- **Two at once**, at the screen's depth and stride.
- **The MFDB is filled in**: `fd_addr` is the bitmap's VRAM address, for
  `vro_cpyfm`, not one a program can read through.  `fd_wdwidth` is the
  screen's.
- **Cleared to pen 0**, as `v_clrwk` would.
- **Its table copy is the program's.**  `v_clsbm` (or `v_clsvwk`) gives
  it back, and so does the program's end.  A slot is free whenever no
  open workstation draws there, so there is no state to keep in step.

## Two old faults it found

**The screen's device after a close.**  `vwk_to_phys`, which makes the
physical workstation current when a virtual one closes, reloaded slot
0's attributes but not its device.  The next call on the screen took
`vwk_select`'s "already current" path and drew through the closed
workstation's device: a bitmap's freed table here.  Since printer
workstations arrived, closing one left everything after it drawing on
the page.  Nothing in the tree prints through a workstation, so it went
unseen.  `test-m3`'s second case failed on it.

**The pointer.**  The input loop redraws the pointer through whatever
device the last VDI call made current.  With a bitmap's or a printer's
workstation current, the pointer was drawn by that device, which for
the page's means not at all.  The pointer's show, hide and form now go
through the physical workstation's device and put the current one back.
No gate drives the pointer with another workstation current.

## B9 again

The first `v_opnbm` passed `&w` to `far_put`, where `w` had come from a
`?:`, a join, into a variable whose address is taken.  That is Calypsi's
B9 (tools/ccbug): the width arrived as whatever the stack held, a
different value every run, and the size check refused it.  The fields
are written by value now (`far_put16`, `far_put32`).

## Gate

`test-m3` gains two cases (417 over the three widths), through a new
runner op, 26, that opens, selects and closes a bitmap and makes the
script's calls draw on it:

- **A bitmap drawn on** -- a fill, text, a diagonal corner to corner and
  a fill partly past its edge, which must clip -- and copied to the
  screen at an odd x and an even one.
- **The screen copied into a bitmap**, drawn over there in XOR, and
  copied back; a bitmap bigger than the screen refused, so what follows
  is drawn on the screen; and a bitmap closed and opened again in the
  same place.

The model (`tools/vdiref.py`) carries a device per workstation; a
bitmap's is the screen's with another base and size, sharing VRAM.  The
MFDB `v_opnbm` fills in is read back and compared.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| `dev_fill_rect` drawing on the screen, not the surface | 12,460 pixels |
| the MFDB given one plane | the MFDB check |
| (before the fix) `vwk_to_phys` leaving the device | the second case, 800 pixels |
