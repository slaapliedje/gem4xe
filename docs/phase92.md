# Phase 92 -- a 32-bit multiply for programs

The first item of `roadmap-0.12.md`.  The compiler's `_Mul32` is a
shift-and-add loop of about 6,000 cycles, and G4BENCH's Mandelbrot, three
multiplies an iteration, spent most of its 40 seconds in it.  Every
`long` product in a program goes through the same routine.

## How

`src/sys/mul32.s` multiplies by quarter squares.  The 65C816 has no
multiply instruction, but for two bytes

    x * y = f(x + y) - f(|x - y|),   f(n) = floor(n * n / 4)

so a byte product is two reads of a 511-word table and a subtract.  The
low 32 bits of a 32 x 32 product, in 16-bit halves, are

    aL * bL                      in full: four byte products
    + (aL * bH + aH * bL) << 16  only their low 16 bits: three each

and a cross term whose high half is zero is skipped, which is every
product of two numbers under 65,536.  Signed and unsigned products have
the same low 32 bits, so one routine serves both, as the library's does.

The call is the library's, read off the compiler's own output: the
operands in `_Dp+0..7`, the product in A and X, the flags unused.  The
routine moves the direct page onto the stack for the length of the call,
so every temporary is a direct-page operand.  That is safe because no
interrupt handler addresses through D (`src/sys/irq.s` sets nothing and
assumes nothing of it).

## The table is made, not shipped

The first version carried the table as 1,022 bytes of constants.  Squares
do not pack, and the suite stopped at the gate's ANTIC floppy: GEM.COM
and the desktop had each grown by 1,289 bytes, and the shipped DOS 2
floppy had gone from 16 free sectors to 7 against a floor of 6 (phase 90).

So the table is now made on the first call, in the program's far
variables (`zfar`, which the crt zeroes):

    f(0) = 0,  f(n) = f(n - 1) + floor(n / 2)

f(510) is written last, so its being nonzero means the table is whole;
every call tests it, which costs Mandelbrot 0.4%.  Making the table takes
about a millisecond.  The routine is 303 bytes, and the shipped floppy
has 15 free sectors.

GEM.COM has no zeroed far section: its far heap begins where the loader
stopped writing, so a far variable placed by the linker could be handed
out again.  **So this is a program's multiply, and the system keeps the
library's.**  The VDI's curves are the system's, and they gained 6 to 8%
from the first version; item 2 reworks the fill loop that does their
multiplying and dividing.

## Where it is linked

`--override _Mul32` replaces the library's in:

- every program the tree builds (`G4A_LIB`, the `g4a` rule): the
  desktop, the accessories, G4BENCH;
- the application kit: `lib/mul32.s` is in the kit and its Makefile
  links it, so a program somebody else builds gets it too.  It is tagged
  LGPL-2.1-or-later like the rest of the kit's library
  (`tests/host/test_licence.py` asked).

QED is not among them yet: its port links with its own line in its own
tree, and takes the kit's objects by name.

## Proof

`tests/host/test_mul32.py` builds a harness twice in the vendor's
simulator, once with the library's `_Mul32` and once with this one.  It
checks both against Python on 8,400 products: 400 from 20 edge values
paired with each other, and 4,000 random pairs taken signed and
unsigned.  It reads back the table the first call made, through a link
file that adds a bank for `zfar`.  Skipping the build, or one cross term,
makes it fail.

## What it bought

G4BENCH's Mandelbrot, ms a call:

| | before | after |
|---|---|---|
| VBXE | 40,057 | 17,356 (-57%) |
| ANTIC | 46,561 | 19,308 (-59%) |

Nothing else moved by more than noise.  The whole run, once, now takes
37.3 s on VBXE and 34.9 s on ANTIC.  The reference
(`tests/emu/g4bench_ref.json`) is rewritten from this build.
