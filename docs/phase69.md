# Phase 69 -- a Color panel, and the room QED is launched in

Item 6 of 0.9, the last (`docs/roadmap-0.9.md`): **COLOR.CPX**, the
screen's colours as a control panel extension beside GENERAL.CPX.

## What it is

The ST's Color panel in its shape (`src/apps/color.c`,
`tools/colorrsc.py`): a row of swatches that IS the palette -- each
filled with its own pen, so the row changes as the pens do -- the chosen
pen's red, green and blue as sixteen steps each with `-` and `+` and a
bar, and Reset, OK and Cancel.  A form CPX, like GENERAL.CPX.

- **Every step applies at once**, through `vs_color` on the AES's
  workstation, because a colour is judged on the screen.  Cancel puts
  back every pen from `vq_color`'s requested values (flag 0), so nothing
  drifts through the DAC's seven bits.
- **Sixteen steps a channel** express the standard palette exactly --
  FF, BB and 77 are 15, 11 and 7 -- so Reset is gem4xe's own palette.
- **OK saves** the palette as nibbles, 24 bytes behind a mark in the
  module's 64, and the panel puts it back at every boot (CPX_BOOTINIT),
  as it does GENERAL.CPX's settings.
- **On ANTIC** the row shows the screen's two pens, and the steps move
  their brightness, which is all mode F keeps (`src/vdi/dev_antic.c`).

It ships where GENERAL.CPX does: the card and the applications floppy in
`\GEM\`, and the release folder.

## The room QED is launched in

A module's near region comes out of the application pool for the life
of the machine.  Measured on a running machine with every accessory and
GENERAL.CPX loaded, a program launched from the desktop had **7,424
bytes**; QED asks for 6,144.  GENERAL.CPX was taking 2,048, and a second
module of the same shape would have left 5,376 -- **QED would no longer
have started on the full product**, and nothing would have said so:
`tools/memreport.py` did not count modules at all.

- Both modules now ask for what their maps say they use: GENERAL.CPX's
  1,024 bytes of bss were all stack, and a module's stack only carries
  its own frames at load -- `cpx_call` runs on the panel's.  512 of bss
  and 128 of bits, a 1,024-byte region each: two modules for the price
  GENERAL.CPX alone used to cost.
- `memreport` counts modules, says what a launched program gets, and
  **fails if QED would not fit** when QED is built.  Seen red with QED's
  request raised by 2,000.  It reports 7,168, a page under the live
  figure -- conservative, which is the right side to be wrong on.

## Three faults on the way, all the module's

- **One click stepped a channel seven times.**  `-` and `+` are
  TOUCHEXIT, so `form_do` returns while the button is still down and
  returns again at once.  The module now waits for the release.
- **Digits drew over digits.**  A G_STRING draws transparently, so
  redrawing the value alone left "15" under " 0".  It is redrawn from
  the dialog's background now, clipped to the value.
- **A saved white came back without its red.**  The nibble unpack was a
  signed 16-bit `byte >> 4`, which is compiler bug **B12**: a signed
  shift by 3 or more (not 8) sign-extends from the wrong bit, so `0xFF >>
  4` was -1.  Catalogued since phase 2 and a rule of the tree ("never
  right-shift a signed 16-bit value") -- and broken here anyway, because
  the one sweep for it was a sweep, not a check.  `mscan` checks for it
  now, in every build, and its first run found two more sites, both
  harmless only because their results are small (`SCR_W >> 6` in the
  rounded box, the INF's sort field `>> 5`); both are unsigned now.
  `tools/ccbug/README.md`, B12.

## The gate

`make test-m42` drives the Control Panel on the VBXE desk: three modules
loaded and none refused; pen 2's swatch (255, 0, 0); four steps down and
it is (187, 0, 0) at once; Cancel and it is back; the same and OK, a
**cold reset**, and it is (187, 0, 0) at boot.  The swatch is found by
its colour in the screenshot and every other place from the resource's
layout, so the gate does not depend on where `form_center` puts the
dialog.
