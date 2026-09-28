# Phase 67 -- a glyph the clip cuts, on ANTIC

The same 0.8.1 tester's video (ANTIC, Antonia 2) showed a second fault:
after the About box closed, the DISK A icon read "DIS  A" under an "F".
The "K" of the label and the right leg of the "A" on the disk were gone.

## Why

Closing a dialog redraws the desk under it (`fm_dial(FMD_FINISH)`,
`w_drawdesk`), clipped to the dialog's rectangle.  On ANTIC the About
box's left edge, x=37, runs through the DISK A icon.  Everything in the
icon redrew except its two pieces of text, because the ANTIC device's
`dev_glyph` drew a glyph "the cell, or none of it": a glyph the clip
cut was not drawn at all, so the part of it inside the clip stayed as
the dialog had left it -- white.  The VBXE device never had this; its
`draw_glyph_cpu` clips a cut glyph pixel by pixel.  The rule dates from
v0.1, and it showed now because the ANTIC screen is narrow enough for a
centred dialog to cross an icon.

The run path of phase 55 (`dev_text_run`) is not involved: it takes
only whole cells, and hands the cut ones to `dev_glyph`.

## The fix

A cut glyph, on either the clip or the screen edge, goes through
`dev_raster_1bpp` -- the same one-plane path the icons use, which clips
by the row and the column -- with the glyph's six rows as its source.
An uncut glyph is drawn as before.

## The gate

`make test-m25` now draws "CLIPPED" with the clip at x 213-244, through
the first glyph and the last.  `tools/vdiref.py`, the model, always
clipped a glyph by the pixel; the gate had simply never drawn text the
clip cut.  With the old rule put back it fails on 20 pixels, the cut
columns at x 213-214 and 240-241.  Opening and closing About on the
emulated ANTIC desk now leaves every pixel as it was (it left 14 wrong,
the tester's).
