# Phase 75 -- VBXE copies: a program's form is the program's

G4BENCH on real hardware showed a white screen for most of a minute
(a tester's video).  Two of its tests were the cause: "blit screen to
screen" at 772 ms a call and "blit screen to memory, back" at 648 ms.

## What was wrong

`dev_copy_form` (`src/vdi/dev_vbxe.c`) took every raster form for VRAM.
The two the system uses -- the screen and the AES's save buffer -- are,
so nothing inside gem4xe noticed.  A program's own form is not: its
`fd_addr` is the program's memory, and the driver read and wrote the
VRAM at that address instead -- which is the screen, since VRAM starts
with it.  G4BENCH's form at `form_bits` was never written at all; its
copies went across the top of the screen, a pixel at a time, each pixel
a window map, a read and a read-modify-write on the 1.79 MHz bus.

And the one path that was not per-pixel wanted BOTH ends even and a
whole number of bytes.  A screen-to-screen copy at an odd x -- G4BENCH's
work area starts at one -- went pixel by pixel even when the two ends
shared their parity and the blitter could have moved all but a column.

## What it does now

A form in VRAM says so in its address: `VR_FORM_TAG`, bit 31, which
`dev_screen_form` and `dev_save_form` set (`src/vbxe/vbxe.h`).  An address
without it is the program's -- bank `$00` directly, anything above
through `far_get` / `far_put`.

    both in VRAM, same parity   the even middle blitted; the column at
                                either edge by rows, the edge on the side
                                of the move first
    anything else               by rows through a 24-byte buffer on the stack: a byte
                                copy when the parities match, a nibble at
                                a time when not; the partial byte at each
                                end merged with the destination's

Rows run bottom-up and chunks right-to-left when the destination is
below or right of the source, so a move inside one form never reads a
pixel it has written.  The per-pixel path and `rform_plot` are gone.

    G4BENCH on VBXE, ms per call     before    after
      blit screen to screen            772.3     26.3
      blit screen to memory, back      648.1    110.0
      all of it, once                  —       59.8 s

## The gate

`make test-m3` has four new cases (84-87), and the model learnt the tag:
`devref.Vbxe` keeps the program's bank `$00` beside VRAM
(`Vbxe.cpu`), and `vdiref.MemForm` is a form there.  For a memory form
the gate compares the form's BYTES with the model's as well as the
screen, since no screenshot shows them.

Each case was made to fail first.  84 and 85 fail on the old driver
(the form stayed zero).  86 and 87 pass on it -- the old path was right,
only slow -- so they were checked against the new code broken: 86 with
the right edge column dropped, 87 with the chunks always left-to-right.
87 passed that at first: its stripe covered both sides of a buffer
boundary, so reading a pixel already written gave the same colour.  It
now has single pixels where the buffers meet (x = 66 and 158).

The buffers were 40 bytes each and static at first, which took LoRAM to
210 bytes free against `test_memory`'s floor of 256.  They are locals
now, 24 bytes a pass, the way `dev_antic.c`'s row buffer already was.
