# Phase 111 -- a joystick, and the keyboard as the pointer

Two things from the same week.  The user's Rapidus freezes on the VBXE
screen with an ST mouse, a CX77 tablet and a KoalaPad alike, and once
with only the `1` key pressed.  Every one of those devices is read
through POKEY's paddle scan, or through the 4 kHz timer that samples a
mouse's lines.  A device that uses neither would say whether the freeze
lives there.  And TOS 2.06 lets the keyboard drive the pointer (Alt and
the arrows), which an Atari with no mouse plugged in has no other way to
do.

## MOUSE=JOY

`MOUSE=JOY` (or `JOYSTICK`) in `GEM4XE.CFG`: hold the stick to move the
pointer, fire is the left button, and there is no right one.  On port 1
unless `MOUSEPORT` says otherwise, where every joystick program expects
it, as a tablet is.  It reads PORTA's four switches and the trigger once
a poll.  It never writes POTGO, and `lines_select` leaves the 4 kHz
sampler off for it (`irq_ptr_on` is set for the quadrature devices
only).

The pointer moves for every vertical blank since the last poll: a pixel
a frame for the first ten frames held, three until the thirtieth, then
six -- the width of the 640 screen in about two seconds.  A gap of more
than four frames counts as four, so a long system call does not throw
the pointer across the screen.

## Pointer mode

The Atari has no Alt, and holding one key while typing others on this
keyboard is awkward, so the **INVERSE** key turns the mode on and off.
`kb_queue` (`src/vdi/vdi.c`) hands every key code to `ptr_key`
(`src/vdi/pointer.c`) before it is typed.  INVERSE is the mode's always.
In the mode, the arrows (`-` `=` `+` `*`, with CONTROL or without),
RETURN, TAB and SPACE are swallowed, and every other key types as
before.

The poll then reads what is HELD -- SKSTAT bit 2 and KBCODE -- not what
was typed:

- an arrow moves the pointer through the same code as the joystick, a
  pixel a frame with SHIFT (SKSTAT bit 3) however long it is held;
- RETURN is the left button and TAB the right, while held;
- SPACE presses the left button and leaves it down until SPACE again.

POKEY reports one held key, so a button key and an arrow cannot be held
together; SPACE's latch is what makes a drag or a rubber band possible.
The buttons are added to the device's, so the mode works beside a mouse,
a joystick, or with `MOUSE=NONE`.

## The model's GEM4XE.CFG was a sector too long

The longer `MOUSE=` comment in `GEM4XE.CFG` failed `test-m26`'s safe
mode: the desktop sat in call 75, and the model put its first wait at 76.
The desktop reads the file 128 bytes a call for a `DESKINF=` line
(`src/desk/deskwin.c` `inf_name`), and the model's Fread stops where the
disk listing says the file ends.  On a DOS 2 disk, `dos2_listing`
(`tests/emu/product_boot.py`) gave that size as the file's sectors times
253: 3,229 bytes in 13 sectors is 26 reads either way, but 3,349 bytes is
27 reads and 14 sectors said 28.  The listing now gives each file's own
length.

## Proof

`test-m10`, on the VBXE conformance target:

- the joystick: centred, it stays; right held for 22 frames, x moves
  52 and y does not; up moves y only; fire is button 1; port 2 pushed
  and fired does nothing;
- pointer mode, held through the patched emulator's KEYRAW, which drives
  the keyboard matrix and so SKSTAT and KBCODE as a held key does: off,
  an arrow held moves nothing; on, down held moves y 54 in 22 frames;
  SHIFT and left move x 26; RETURN and TAB are buttons 1 and 2 while
  held, and nothing when let go; SPACE then right held is a drag, the
  left button down and x moving; SPACE again lets go; INVERSE again
  turns the mode off.

No gate has a real joystick or keyboard; `tests/emu/m10_irq.py` says
what the bridge's JOY and KEYRAW can and cannot drive.
