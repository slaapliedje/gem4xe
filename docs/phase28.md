# Phase 28 — two programs that are not tests

    make test-m22   the calculator driven at its keypad, the clock left
                    to tick, both through the shell loop

The application ABI has had a gate since phase 10 and an SDK since
phase 21, and the only programs written to it were the desktop and the
things that test it.  These two are neither: a **calculator** and a
**clock**, each one C file and one resource, each launched by name and
each returning to what launched it.

## What they are for

They are the answer to "could something real be ported to this?", asked
in the cheapest possible way.  Between them they use both shapes an
application takes, so what they prove is not one path but the choice
between paths:

- **CALC.PRG is a form.**  Every key of the panel is a `SELECTABLE|EXIT`
  button, so the whole program is `form_do` returning the object that
  was pressed, an eight-case switch, and back in.  A GEM keypad dialog,
  as the donor writes one.
- **CLOCK.PRG is an event loop.**  A clock cannot sit in `form_do`,
  because `form_do` does not return until something is pressed and a
  clock has to say something every second.  So it runs the loop a GEM
  program normally runs: `evnt_multi` with a timer and the button,
  `objc_find` for what was under the pointer, and its own redraw of the
  field that changed.

Neither links a line of gem4xe.  Both reach the AES, the VDI and GEMDOS
through the three call gates and nothing else.

## The calculator counts in whole numbers

There is no floating point anywhere in gem4xe -- no FPU on this machine,
and an application links no libc -- so the accumulator is a LONG and a
division truncates towards zero.  A calculator that quietly rounded
would be worse than one that is exact about what it is: ten places hold
2,147,483,647, entry stops there, and an operation that would pass it
leaves the display alone rather than wrapping.

## The clock is two halves, and so is its check

GEMDOS answers `Tgettime` and `Tgetdate`, and on this machine that is
the Ultimate 1MB's DS1305.  A machine without one answers the ST's
dead-clock epoch -- midnight on 1 January 1980 -- and answers it again a
second later, so a clock that only asked GEMDOS would never move.  This
one asks once, counts its own seconds off the AES's timer, and asks
again every minute to correct the drift: the right time on a machine
that knows it, a stopwatch from midnight on one that does not.  The
picture in the gate is the second kind, because `make test` has no
Ultimate 1MB.

That makes the clock the one thing whose right answer depends on how
long the run took, so its check is in two halves that cannot prop each
other up.  The **timekeeping** half reads the program's own `second` out
of memory by symbol and requires it to have advanced by the number of
seconds the frames driven are worth, within one.  The **drawing** half
then renders the model's panel from that same number and compares the
screen: what it proves is that the program drew what it believed, and
the first half is what says the belief was right.

## Both panels are the resource's, down to the separators

`tools/calcrsc.py` and `tools/clockrsc.py` build the files on the host,
the way `tools/deskrsc.py` builds the desktop's, and the gate draws from
the same description -- so what is compared is the target against what
the description MEANS, not against a picture kept from a previous run.

The clock fills its fields through their TEMPLATES: `__:__:__` and
`__/__/__`, whose runs of underscores take the numbers in the order the
resource puts them.  A translation may write the date the other way
round and no C changes.  It is the desktop's text-view rule
(`docs/phase27.md`) in a smaller place, and it is now the third time
that shape has paid, which makes it the house style rather than a trick.

## What the gate caught

The first run drew the calculator's panel **pixel for pixel identical to
the model** and then would not answer the `=` key.  The panel was sized
by two numbers written beside the keypad rather than derived from it,
and the bottom row -- `=` and `Quit` -- sat one character below the box.
The AES clipped it away, which draws the same on both sides of a gate
and answers no click on either.

**A model catches what a program gets wrong; it cannot catch what a
description gets wrong**, because both sides read the same description.
What caught this was the other half of the gate: driving the keypad and
requiring the program's own accumulator to reach 42.  The panel's size
is now computed from the keypad it has to hold.

## Standing

    CALC.PRG    5,796 bytes    3.2 KB of code in a far bank, 2 KB near
    CLOCK.PRG   5,309 bytes    and a resource each, 650 and 268 bytes

*(no longer true since Phase 47 -- `docs/phase47.md`: `CALC.PRG` is
5,703 bytes and `CLOCK.PRG` is 5,195.)*

Both are on `test-m22`'s disk and neither is on the product's yet: the
desktop has no way to put an application anywhere but a window, and
`Install application` is still in `NOT_YET`.  *(no longer true since
Phase 47 -- `docs/phase47.md`: both ship on the product media now, and
the calculator ships twice from the one source -- `APPS>CALC.PRG` and
`GEM>CALC.ACC`.)*
