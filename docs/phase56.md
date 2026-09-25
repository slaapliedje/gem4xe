# Phase 56 -- boot: the unpacker was on the slow bus

Fifth round of the 0.8.x line (optimisation and stability only), and the
first about load time, which every user waits through at every boot and
nothing had measured.

## Measured first

`make bench-boot` (`tests/emu/bench_boot.py`) cold-boots each product
floppy with nothing typed, as `test-boot` does, and times three stretches
in frames:

- **A**, reset to the CPU switch: the DOS boots and starts `GEM.COM` on the
  6502, whose loader finds the Rapidus and switches it -- which resets, so
  the DOS starts `GEM.COM` again from the top;
- **B**, the switch to the boot screen: `GEM.COM` read and its far image
  unpacked, and GEM starting up to the screen that says what it found;
- **C**, the boot screen to the desktop: the screen is held three seconds
  ON PURPOSE (`src/sys/bootinfo.c`), then `DESKTOP.PRG` is read and drawn.

`ARGS=--profile` profiles B and splits it into the loader's unpacker, the
OS ROM, the DOS, and the rest.

| | before | after |
|---|---|---|
| DOS 2 floppy | A 115 + B 730 + C 220 = 1,065 frames, **21.3 s** | A 110 + B 340 + C 220 = 675 frames, **13.5 s** |
| SpartaDOS X floppy | A 465 + B 1,500 + C 390 = 2,355 frames, **47.1 s** | A 465 + B 1,110 + C 395 = 1,970 frames, **39.4 s** |

**A caution about the disk half of these.**  The gates' drive is Altirra's
generic one with its SIO patch, which serves the OS's SIO routine at once
-- and DOS 2 reads through the OS's routine, while SpartaDOS X has its own.
So the DOS 2 floppy's disk time here is far faster than a real 1050's, and
on real floppies the disk is a much larger share than this says.  What the
change below saved is CPU time, the same on any drive.

## What was slow

Before the change, B on the DOS 2 floppy was **57% unpacker** -- eight
seconds.  The far image travels packed, and `src/farload.s` unpacks each
chunk as DOS loads it.  It ran in `StageCode`, at `$9A05`, in the
Rapidus's window 2, and until GEM's own `rapidus_speedup()` runs, EVERY
window of bank `$00` is on the 1.79 MHz bus, and window 2 always is.  So
the unpacker fetched each instruction, and reached each of its zero-page
pointers, at 1.79 MHz -- and it was a byte-at-a-time loop through
`[dp],y` pointers with page-run bookkeeping around every token: about 88
machine cycles an output byte.

## What it is now

On the first chunk the loader copies a second unpacker up into the bank
above the far image -- the accelerator's fast SRAM, which GEM's far heap
takes back later -- at the same 16-bit address it was linked at, so its
jumps need nothing done to them, and calls it there for every chunk:

- in **native mode**, sixteen-bit, its state beside its code in fast RAM
  and the packed bytes read with long addressing out of the staging
  buffer;
- every copy one **`MVN`** per piece.  MVN moves a byte at a time upwards,
  so a match that overlaps its own output -- a run -- repeats the way the
  format means; a piece stops at the end of either bank, since MVN's
  addresses wrap within one;
- with **both kinds of interrupt out** for the few milliseconds a chunk
  takes: IRQ by `sei`, and ANTIC's NMI by `NMIEN`, because the native
  vectors are ones the OS never filled.  NMIEN goes back to the OS's `$40`.

Which bank that is, the loader cannot know from its first chunk:
`tools/mkxex.py` writes it (`fl_fastbank`) in a segment ahead of the first
chunk, from where the image really ends.  RAM there is probed like every
chunk's destination, and a machine without it gets the loader's existing
"no RAM at bank" message -- GEM needs RAM there for its far heap anyway.
The unpacker's share of B fell from 57% to under 5%.

The old byte loop is gone, not kept as a fallback, because `StageCode` is
507 bytes and both did not fit: `fl_finish`'s "raise the top to a
maximum" went too, since `mkxex.py` emits the chunks in address order --
it now refuses to do otherwise -- and the last chunk's end IS the top.

## The packing, and the floppy

The change added a five-byte segment and the file packed a little worse,
and the DOS 2 floppy fell to 19 sectors free, under its floor of 20
(phase 55).  `mkxex.py`'s parse is now OPTIMAL rather than greedy: the
longest earlier match at every position first, then, working back from
the end, each position's cheapest way on -- a literal, or a match of any
length it could take.  The same format, so the loader did not change:
the far image packs to 111,778 bytes where it was 112,693, and the floppy
has 23 free.  `mkxex.py` still unpacks every chunk it writes and compares.

That is about all this format has in it.  Its limit is the format itself:
every match costs a two-byte offset, and nothing is packed below a byte.
Exomizer packs the same far image to 84,775 bytes (51%, against 67%), and
a simple bit-packed design with a repeat-offset match, estimated with a
greedy parse, to 61.5%.  That is the next step -- a new format, its
packer and a native decoder -- and on real floppies, where the disk is
most of the load, it is the one that matters most.
