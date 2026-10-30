# Phase 115 -- GSlayer: a IIGS Toolbox program on gem4xe

The first Apple IIGS program runs on gem4xe, unmodified, and draws what
Apple's own Toolbox draws -- `make test-gs1` holds the two Super Hi-Res
screens against each other byte for byte.  The whole design, the calls
served and what is next are in [gslayer.md](gslayer.md).

## What changed in gem4xe itself

**`Mclaim`, GEMDOS `$1F2`** -- memory at a fixed address.  The far heap
only ever chose where a block went; a IIGS program finds the Toolbox at
`$E1:0000` and the screen at `$E1:2000` by address, so GSlayer must have
exactly that range.  `far_claim(at, bytes)` (`src/sys/farmem.c`) takes it if
all of it is free heap, else 0; the block is the caller's and goes when it
ends.  `tools/farref.py` has the same rule and `tests/host/test_farmem.py`
holds the two together: a claim exactly where asked, one over a block or
past the heap refused, one ending where a block starts allowed, the start
rounded down to 4.  Breaking the overlap test in the C makes the host test
fail at step 44.

## The rest is a program

`src/gslayer` is an ordinary gem4xe program, `GSLAYER.PRG`; nothing else
in the system knows it is there.  `tools/prodos.py` and `tools/shr2png.py`
are new tools for the gate (a ProDOS volume's files, a Super Hi-Res dump as
a picture), and `tools/orca.sh` builds the test program with ORCA/C under
Wine -- built, never committed, because it carries ORCA/C's run-time.

## Found on the way

- cc65816 -O2 tested a byte's bit 7 in one half of a stack word and used
  the other half: B23's family, in GSlayer's relocation loop.  Bytes that
  are tested or compared are words there now.
- A `--stack-size` of 512 with two 128-byte buffers in `main` overran;
  they are static now.
