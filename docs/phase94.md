# Phase 94 -- squeezed programs

Item 6 of `roadmap-0.12.md`, asked for as "read a smaller file off disk,
decompress into ram and run the desktop, like many games back in the day
did".  GEM.COM has been packed this way since phase 57.  The programs
never were: the desktop was 211 of the DOS 2 floppy's sectors, stored as
it was linked.

## Format 6

A `.G4A` of format 6 is a whole format 3, 4 or 5 file, packed as one G4Z
stream:

    0  'G4A' 6
    4  u32  the length it unpacks to
    8  the stream

G4Z is GEM.COM's own packer (`tools/mkxex.py`, phase 57).  Here it is
one stream for the whole file, not chunks.  `tools/mkg4a.py` writes
format 6 when it is smaller, which is always for a program, and
`--no-squeeze` writes the plain file.  It reads the result back before
keeping it.

The loader (`src/sys/app.c`, `app_load_v6`) unpacks into a block of its
own, loads the file inside it as any other, and gives the block back.
What stays in memory is what an unsqueezed file would have left.  The
unpacker is `src/sys/g4z.s`, resident in GEM.COM.  The boot loader's
(`src/farload.s`) exists only while DOS is loading, and reads only
bank $00.  This one reads a packed file of any size from wherever
`far_read_file` put it, through 24-bit pointers that carry into the
next bank.  If the stream asks to write past the length the header
gave, it stops and the load fails, so a damaged file overwrites
nothing but its own block.

The program files' readers -- the gates, `tools/memreport.py`, the host
tests -- read them through `mkg4a.read_file`, which unsqueezes.

## Room

| | before | after |
|---|---|---|
| DESKTOP.PRG | 53,290 bytes, 211 sectors | 27,495 bytes, 109 sectors |
| the small programs | | 32-52% of their size |
| the DOS 2 floppy, sectors free | 14 | **114** |
| the gate's ANTIC floppy, sectors free | 2 | 102 |

## Time

`make bench-boot` with a scratch profile of stretch C -- the boot
screen to the desktop -- shows `g4z_unpack` taking 730,000 machine
cycles for the desktop.  That is about 20 frames, 0.4 s.  Then:

- **on the gates' DOS 2 drive**, whose SIO is patched to read almost
  at once, the unpack costs more than the reading it saves: stretch C is
  240 frames, against 230 unsqueezed;
- **on SpartaDOS X**, which uses its own SIO, it is 505 against 570:
  1.3 s sooner;
- **on a real drive at standard speed** -- about 1.4 KB a second -- 26 KB
  less to read should be on the order of fifteen to twenty seconds.  That
  is not measured here: no gate drives a real 1050.

The unpacker is about 150 cycles a byte and could be made faster.

## The vendor's simulator has no MVN

`src/farload.s` copies with MVN, 7 cycles a byte, and so did the first
`g4z.s`.  `tests/host/test_g4z.py` hung.  The vendor's simulator does not
implement MVN.  An MVN between any two banks, bank $00 to itself
included, moves nothing (`lda long` after it reads the old byte).  It
also shows no memory where the ELF has no segment, and its `print` of
a cast to a far pointer reads 0.  Each of these looked like a bug in
the unpacker for a while.  The copy is now a `[dp],y` loop, about 20
cycles a byte, which carries into the next bank by itself.  The test
links a scratch section over the two bank-straddling ranges it uses.

## Proof

- `tests/host/test_g4z.py`, in the vendor's simulator: the desktop as
  built, and 80 KB made with long runs and matches reaching back past
  60 KB, are packed by `tools/mkxex.py` and unpacked by `g4z.s` from an
  address that straddles a bank to another that straddles one.  The
  result's checksum must match the original's.  A count cut short must
  answer 1 and leave the next byte alone.  Without the destination
  bank's carry it fails.
- `tests/host/test_g4a.py`: every shipped program is format 6, under 60%
  of its format 5, and unpacks to exactly it; a parse with a literal
  run over 65,535 bytes is left unsqueezed.
- Every gate boots disks whose programs are squeezed, so every program
  any gate starts goes through `app_load_v6` on the target.

## Where the unpack span goes

The first version took the span with `far_alloc_span`, low, like the
file.  Three gates went red, one after another, and each was right:

- **m17**: its model of the far heap put the desktop where an unsqueezed
  load would.  It read text where `G` should be, because the span had
  pushed the program's blocks up.
- **m18**: after a program, the colour icons the AES keeps from the first
  desktop sat in the hole the span left.  The second span, and the second
  desktop, then went somewhere else.
- **m37**: every boot-time program was placed above its span, and the
  boot reached `$07BB34`, past the three banks from `$04` it is held to.

So the span now comes from the **top** of the heap: `far_alloc_top`,
new in `src/sys/farmem.c`, the top of the highest gap it fits, which may
cross banks.  A program loads exactly where it did unsqueezed, and the
gates' heap models need only take the span and free it.  It holds data
only, never code, so the SDRAM cache question that keeps whole-bank
code low (`far_alloc_banks`) does not reach it.  The unpack takes the
same 730,000 cycles up there.  `tools/farref.py` models the new
function, and `tests/host/test_farmem.py` holds the two to each other.
That covers the top hole, a fall back to a lower one, a refusal, the
rounding down to four (which it catches when broken), and a span across
a bank.

m18's model also stopped assuming that the desktop reloaded after a
program lands where the first one did: it places the second one on the
heap as it then stands (`desk_places(read=False)`), and each probe reads
its own desktop's `G`.

## Not yet

- **Resources.** `DESKTOP.RSC` packs from 27 sectors to 10, but
  `rsrc_load` reads it, not the program loader.
- **QED** links through its own Makefile with the kit's `mkg4a.py`, so
  its next build is squeezed: 1,303 sectors to about 651.
- **The kit** squeezes by default.  A program built with it needs
  gem4xe 0.12; `make SQUEEZE=0` for an older one.
