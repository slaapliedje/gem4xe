# Phase 57 -- G4Z: the far image packed to 56%

Sixth round of the 0.8.x line (optimisation and stability only), and the
second about load time.  Phase 56 moved the unpacker into fast RAM; this
changes what it unpacks.

| | before | after |
|---|---|---|
| `GEM.COM` | 114,543 bytes | **96,438 bytes** |
| the far image, packed | 111,778 of 166,406 (67%) | **93,705 (56%)** |
| DOS 2 floppy, sectors free | 23 | **94** |
| boot, DOS 2 floppy (`make bench-boot`) | 675 frames, 13.5 s | 685 frames, 13.7 s |
| boot, SpartaDOS X floppy | 1,970 frames, 39.4 s | **1,915 frames, 38.3 s** |

On a real floppy the second half of that table is the wrong way to read
it.  The gates' drive serves DOS 2's reads, which go through the OS's SIO
routine, almost at once, so there the disk costs next to nothing and
only the decoder's extra CPU shows -- about a second across the whole
image.  On a 1050 at standard speed, 18 KB is on the order of ten seconds
of reading; with high-speed SIO, a few.  SpartaDOS X, whose SIO the
emulator does not shortcut, already shows the gain.

## Why a new format

Phase 56 made the old format's parse optimal and it gained 1%: the limit
was the format.  Every match cost a nibble pair and a two-byte offset,
and nothing was packed below a byte.  For scale, Exomizer packs the same
image to 84,775 bytes (51%).  G4Z is gem4xe's own design, in the style
of ZX0 (its grammar, not its code): bits interleaved with raw bytes,
numbers in interlaced Elias gamma, and three elements --

    literals        gamma(n), n bytes
    new offset      gamma(hi), a byte lo, gamma(len - 1)
    repeat          gamma(len), at the last offset used

-- the next one chosen by a bit whose meaning depends on the last: after a
match, literals or a new offset; after literals, a repeat or a new offset.
The repeat is what pays on code: a match, a changed byte or two, the same
match again.  `tools/mkxex.py`'s docstring is the specification.

What makes it fit the loader as the old one did: **a chunk still unpacks
on its own.**  Every chunk begins with an empty bit byte and in the
after-a-match state, so the packer ends a chunk at an element boundary --
splitting a run of literals that will not fit, and turning a repeat that
would open a chunk into a new offset (or, for a one-byte repeat, a
literal).  The one thing carried across is the last offset, which the
decoder keeps beside its code in the fast bank; the packer never repeats
an offset a segment has not set, since a segment follows another's last.

## The packer

An optimal parse, forward, one arrival a position: the cheapest way found
to have written each prefix, the last offset on that way, and whether it
ended in literals.  From each position, one more literal, a repeat if
literals came last, and new offsets from a hash of the next two bytes --
the 128 most recent places, each for the lengths no nearer one reached --
all costed in the format's own bits.  1.6 s for the far image.

**Its first version was quadratic on a run.**  A test packing 200,000
zero bytes took 34 seconds: inside a long run, every position compared up
to 4,096 bytes against each candidate.  Comparisons now go 32 bytes at a
time by slices, and a position that finds a match of 256 bytes or more
stops the search at the positions inside it.  The first cut of that
stopped the search 48 bytes short of the match's end, which let those
positions find long matches of their own and push the quiet stretch on
past the real path, which then had only literals -- 97,752 bytes for the
zeros.  The test that measures it checks the size too now.

## The decoder

`src/farload.s`, in the fast bank, native mode.  A bit is `asl` of the
bit byte, which keeps a 1 below its last bit: when shifting leaves
nothing, the next byte is taken with the 1 rolled in below it.  A number
is 1, then while a 0 comes, one more bit below.  Literals and matches are
still one `MVN` a piece, through phase 56's `ff_copy`.  X holds the packed
stream's absolute address in bank $00 rather than an index, which is what
made the decoder fit: `StageCode` is 507 bytes and it is 505.  (Faster
bit reading, inlined, would not fit without shrinking the staging buffer.)

## Checked, three ways

- `tools/mkxex.py` decodes every chunk it writes, through its own
  `decode()`, and refuses to write a `.xex` whose chunks do not give the
  segment back.
- `tests/host/test_mkxex.py` loads each `.xex` the way DOS does, through a
  model of the loader written a second time from the format's description
  rather than from `decode()`, and requires the image back byte for byte;
  and packs every shape of the format -- numbers of every width, offsets
  of every width, repeats, runs, and random data cut into chunks of 16, 40
  and 300 bytes so that literal splits and repeats at a chunk's start
  happen everywhere.
- every emulator gate boots its program through the 65816 decoder.
