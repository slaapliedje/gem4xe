# Phase 86 -- colour icons are drawn in colour

A G_CICON drew its mono form: rsrc_load parsed a new-format resource's
colour icons (rs_cicons) and kept their colour forms in far memory, and
objc_draw never looked at them.  Now, on the VBXE's 16-colour screen, a
colour icon with a 4-plane form is drawn in it -- the Falcon's
DESKICON.RSC, all 33 icons, came up as they do on a Falcon (a private
check: the file is Atari's and is not in this tree or any release).

## At load: chunky, once

rs_cicons records each icon's 4-plane form and its selected form, if
any, in the icon's near record -- CICON_NEAR, now in aes.h and 54 bytes,
col4 and sel4 after the text -- and turns each 4-plane image from the
ST's plane order into this screen's chunky pixels in place (rs_chunky),
through two pool buffers it gives back.  The plane bits need no table:
the VDI keeps the ST's pen order in hardware (dev_vbxe.c, map_col), so a
pixel's four bits ARE its hardware pen.  EmuTOS transforms at load too.
A form wider than 32x32 keeps its mono drawing (CICON_BYTES).

## At draw: the mask, then OR

objc.c follows EmuTOS's gr_gicon: the colour form's mask goes down in
the background colour, and the image is ORed over it (gsx_cblt,
vro_cpyfm S_OR_D) -- white inside the mask takes the image's pens, the
screen outside it is left alone.  SELECTED uses the selected form; an
icon with none keeps its image and swaps only its label's colours
(EmuTOS darkens it with a dithered mask; not done here).  With no
4-plane form, or on the two-colour ANTIC screen, the mono form is drawn
as before.

## The VDI

vro_cpyfm honoured only replace.  RFORM carries `or_op` now, set for
S_OR_D, and the VBXE driver's row copy ORs nibble by nibble when it is
set (copy_rows, cr_or -- a direct-page byte: LoRAM was at its reserve).
The other twelve modes still replace, as they did; ANTIC and the printer
ignore the flag.

## Not yet: the desktop using them

The desktop's icons are its own DESKTOP.RSC's eight mono ones.  Using a
DESKICON.RSC there needs two more things: loading a NEW-FORMAT resource
into far memory (rs_load still refuses one that does not fit the pool,
and DESKICON.RSC's main part is 10.6 KB against the 5.9 KB a launched
program gets), and the desktop choosing icons by NEWDESK.INF's types.

## Gates

m4's colour icon case is a CICON_NEAR as rsrc_load leaves one: a 4-plane
form with a selected form, drawn and then selected, beside one with no
colour form -- pixel for pixel against tools/aesref.py, which converts
and ORs the same way (aesref.chunky, CiconNear, gsx_cblt; devref's copy
takes orop).
