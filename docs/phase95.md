# Phase 95 -- a click made while a program is busy

Item 7 of `roadmap-0.12.md`, and one of 0.11's known issues.  A click
made while a program was computing, and not in an AES call, was lost.
An ST would have acted on it afterwards.

## Why it was lost

The button was **sampled**.  `vdi_input_poll` (`src/vdi/vdi.c`) reads
the pointer's state once a pass and calls the button vector when it
has changed since the last pass.  The passes come from the AES's event
calls.  A program busy for half a second makes none, and a press and
release inside that half second leave the button up, as it was.

The ST is different because its keyboard processor sends a packet for
every change, and the interrupt that receives it hands each one on.
Here, the timer interrupt already polls a quadrature mouse's lines
about 4,000 times a second, but the button was never part of that.

## The ring

Every pointer gem4xe supports has its **left button on a joystick
trigger**: the ST and Amiga mice, the trak-ball and the mouSTer.  A
tablet has both buttons on triggers.  So the vertical-blank interrupt
(`src/sys/irq.s`, `irq_nmi`) now reads `TRIG0` and `TRIG1` fifty times
a second.  When they differ from the last change it saw, it puts the
new state on a ring, `irq_tq`.  Fifty looks a second catch any press a
hand makes.

`vdi_input_poll` drains the ring before it looks at the button itself.
For each queued state it asks `ptr_buttons_at` (`src/vdi/pointer.c`)
what that means for the device in use: the trigger for the left button,
and the right button as it is now.  It then calls the button vector for
each change.  A press and release made while nothing polled reach the
AES in order, and its click logic (`b_click`, `b_delay`) counts them as
one click, or two.  The poll's own look at the button comes last, as
before, and delivers anything too recent for the ring.

The gates drive the pointer from the host under a kind with no
hardware behind it, and `ptr_buttons_at` answers -1 for that, so their
input is untouched.

The right button of a mouse is a paddle line that needs a full POKEY
scan to read, which an interrupt cannot wait for.  It stays sampled.

## Six bytes

The ring lives in bank $00 below the banked window, because an
interrupt handler writes it.  LoRAM had 244 bytes free against a floor
of 256 with a first version of 12 bytes, and Near, the other side of
the one boundary that can move, had 137 against 128.  So the ring was
made to cost six bytes:

- **Four slots hold three changes.**  That is a double click's press,
  release and press.  The poll's own look delivers the last release,
  so a full ring dropping the newest change loses nothing a hand does.
- **The slot before the tail is "the last change"**, consumed or not,
  so no byte holds it separately.
- **The handler's scratch byte is on the stack.**

The LoRAM/Near boundary moved up six bytes to `$37E6`
(`src/gem4xe.scm`, beside the earlier moves): LoRAM 256 free, Near 131.

## The bug that looked like a layout bug

The first suite failed **m3 at one screen width of three**.  At 512
pixels, `v_opnwk` answered a height of 2,144, and some cases timed out.
640 and 672 were fine.  Bisecting:

- with the LoRAM/Near boundary put back: still failing;
- without the runner's new sys op: still failing, with different garbage;
- with the old vertical-blank handler: passing;
- with the new handler, its logic skipped by a branch, in the same
  layout: failing;
- with the old handler padded to the new one's size: passing.

So the new handler's entry was at fault, not its logic and not the
layout.  To index the ring it did `rep #0x30; pha; phx; phb; sep #0x30`.
On a 65816, `sep` with bit 4 set **clears the high bytes of X and Y**.
X was saved; Y was not.  Every vertical blank that landed while the
interrupted code held a 16-bit Y took its high byte away.  Which code
that was, the layout and the moment decided.  The handler now saves Y
as the IRQ handler beside it always has, with a comment saying why.

## Proof

`make test-m10` selects the trak-ball and double-clicks its fire button
through the bridge while the target busy-waits and polls nothing.  One
poll afterwards must hand the button vector four changes: press,
release, press, release.  Three come from the ring and the last from
the poll's own look.  The runner's sys op 19 installs a vector that
logs what it is handed.  With the replay switched off the log is empty.
m3, all 273 cases at all three widths, is what caught the Y.
