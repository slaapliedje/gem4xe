# Phase 66 -- ANTIC menus in a blink: screen to memory by the row

A tester on 0.8.1, on an ANTIC machine with an Antonia 2 at 14 MHz: the
menus take about five seconds to appear, "as if it is building the menu
entries first", and windows are quick.

## Why

A drop-down saves the screen under it before drawing and puts it back
after (`bb_save`/`bb_restore`, `src/aes/graf.c`).  On ANTIC the save
area is a far-memory copy of the screen (`dev_save_form`), and the copy
went through `dev_copy_form`'s pixel loop: for every pixel, `form_get`
and `form_put`, each working out a 32-bit address with a multiply --
the compiler's `_Mul32`, about 6,000 cycles -- and going through the far
accessors.  Windows were quick because moving one is screen to screen,
which already had a byte path (`antic_copy`).  G4BENCH had been showing
it all along, as screen to memory and back at 750 ms for 64x32
(`docs/phase59.md`).

## The fix

`copy_rows` (`src/vdi/dev_antic.c`): between two DIFFERENT forms, a row
is read once, shifted into the destination's bit positions, and
written back with the first and last bytes merged under a mask (the row shifted in place in one 50-byte buffer on the stack: bank $00 had no room to keep one), so not
a pixel outside the rectangle changes.  One address calculation a row
instead of two multiplies a pixel.  A copy within one form keeps the
pixel path, which knows which way an overlap runs; so does a row wider
than 64 bytes (512 pixels, wider than this screen).

| on the emulated Rapidus | before | after |
|---|---|---|
| the desktop's File menu, pointer on the title to drop-down drawn | 2,320 ms | 40 ms or less (the measurement's step) |
| G4BENCH, blit screen to memory and back (64x32) | 748.5 ms | 22.6 ms |

At the tester's 14 MHz the old figure scales to about 3.3 s to appear,
plus the same again to put the screen back when it closes.

## The gate

`make test-m25` (the VDI on ANTIC) now ends by copying its line of text
from the screen into a form in bank $00, from there into the far save
form, and back onto an empty part of the screen -- at a different bit
position each hop, so both directions' shifts and edge masks are in
the picture -- and the host model adds the same copy.  It requires the
save form to be in far memory, or the far half was not tested.  With
the shift broken on purpose (`7 - off` for `8 - off`) it fails on 96
pixels.

`make g4bench` holds the new ANTIC figure once the reference is
updated; a slower result than the reference fails it.
