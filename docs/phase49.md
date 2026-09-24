# Phase 49 -- one file, and no DOS at all

The request was small and the answer was not: *a `.car` somebody can put
on an Ultimate Cart or fetch with a FujiNet, so people can easily
download and play around with it.*

**The barrier it removes was never technical.**  `gem4xe-0.6.1.atr`
does not boot on its own -- it carries no DOS by design and wants
SpartaDOS X in the machine -- so the release page pointed at
<https://sdx.atari8.info/> and asked a newcomer to find the right image,
work out what to do with it, and only then see a desktop.  There is a
`gem-boot.atr` in this tree that boots standalone, and it stays home
because **the DOS on it is not gem4xe's to give away**.  A licence, not
a problem.

So the question underneath the request was: *does this need an open
source DOS?*

## No, and read-only is why

`docs/cartridge.md` has the argument; the short form is that **most of
what a DOS is, is the write side** -- the free-sector bitmap, the
allocation, the VTOC, the whole business of changing a disk without
corrupting it.  A demo needs none of it.

What gem4xe actually asks a `D1:` for is three things:

| | |
|---|---|
| open a file by name, read it, close it | every file the system loads |
| a directory | opened as `*.*`, read as DOS 2's 17-character records |
| which drives exist | a bitmap |

That is a **CIO device handler**, not a DOS.  And nothing writes at
boot: the three write sites in the whole system -- *Save desktop*, a
file copy, and a CPX saving its settings -- are all things a person does
on purpose afterwards, and all three already report failure.  So a
read-only disk boots to a **complete** desktop and only disappoints
somebody who tries to save.

`src/cartd.s` is that handler: 1,179 bytes, linked at `$0700` because
that is where a DOS would have been, carried in the cartridge and copied
down.  **gem4xe did not change at all.**  It sees a device in HATABS
answering CIO the way a DOS 2 does and never learns where the bytes came
from.

## Four steps, each gated before the next went on top

Because a wrong `.car` header or a wrong mapper gives a cartridge that
is perfectly valid and does *nothing* -- silence, not an error, which is
indistinguishable from broken code.

**1. It boots.**  `tools/mkcar.py`, `src/cart.s`, an AtariMax 1 Mbit of
128 banks, and the bootstrap in **bank 127**, which is the bank that
mapper maps at reset.  Confirmed by moving it to bank 0 and watching the
gate say so.

Two things settled here.  The Calypsi linker drops an object nothing
references, so every cartridge section is `root` -- without it the link
succeeds and produces an empty ROM.  And **never read `$D5xx`**: real
AtariMax hardware switches bank on a read of that page and this tree's
Altirra deliberately does not, so code that reads it works here and
changes bank under itself on a real cartridge.

**The CPU switch comes free.**  A Rapidus always cold-boots as a 6502;
the cartridge finds the card, switches it, and the reset brings the
machine straight back -- which is *easier* than the disk path, where
`farload.s` has to force a cold start so the DOS runs its start-up file
again.  Here the cartridge is still in the slot and the OS calls it
again by itself.

**2. The payload, staged.**  16,384 of 16,384 bytes into far memory,
with each byte's value depending on its offset **and** its bank, so two
banks arriving swapped or one arriving twice fails as loudly as a byte
going missing.

**The copier cannot live in the cartridge**, and that is the whole shape
of the step: selecting a payload bank replaces `$A000-$BFFF`, which is
where the code doing the selecting would be.  So it is copied to page 6,
written position-independently -- every reference a zero-page one, a
hardware address or a relative branch -- and puts the boot bank back
*before* it returns, so the `rts` lands in a window that exists again.

**3. The read-only `D1:`.**  OPEN by name, GET, CLOSE, and the directory.
PUT and SPECIAL **refuse**, because a write that silently did nothing
would leave a program believing it had saved.

**The proof is a read, not an installation.**  CIO will dispatch into a
table of rubbish just as willingly, so the cartridge opens a file
through the ordinary `CIOV` and the gate checks its length and sum
against the host's copy -- then the directory, and the gate checks the
**records** rather than a checksum of them, because a sum proves the
bytes and not their shape, and the shape is what `dos_dirline` parses.
The expected listing is built in the gate from `src/sys/dos.c`'s
description of the format, not from the handler's output, which is the
only way the two agreeing means anything.

It cost a magic word (without one the bootstrap copied 2 KB of erased
flash to `$0700` and *called* it, surviving by luck) and a precedence
bug (`.byte1 DEV_AT+DEV_HDR` binds as `(.byte1 DEV_AT) + DEV_HDR`).

**4. The whole system.**  `build/gem4xe-sys.car` -- every file the
release's loose `system/` folder carries, taken from `mkdist.SYSTEM`
rather than listed a second time -- and the desk at the end compared
pixel for pixel with `tools/deskref.py`, exactly as `test-boot` compares
the product floppies.

## The one job of a DOS that read-only did not remove

**Loading a program.**  So the bootstrap grew a `.xex` loader: the
`$FFFF`, then `<first> <last> <bytes>` segments read straight to where
they go, CIO handed the destination so the loader holds no pointer of
its own.

What it could not simplify is the vector rule -- **call `INITAD` after
every segment and point it at an RTS once you have** -- because gem4xe's
far image travels as a hundred chunks each followed by a two-byte
segment writing that vector, and a loader that fired it once would
unpack the first chunk and jump into an image nine tenths absent.
`tools/mkxex.py` measured that rule on a real DOS in September, after a
reader on AtariAge corrected an earlier account of it; this is its
second reader.

## DOS 2's variables at `$0700` had no owner

`Drvmap` returns `DRVBYT` at `$070A` **verbatim**, and with the handler
linked from `$0700` that byte was one of its own branch offsets -- so
the desktop would have drawn a drive icon per bit of an instruction.
The handler owns the first sixteen bytes now: a `JMP` to its entry, and
`DRVBYT = 1`, which is the truth.  `MEMLO` goes up past it, and `DOSVEC`
points at the OS's cold start, because on a cartridge "quit" means the
machine comes back up and finds the cartridge still in the slot.

The rest of that page is left zero and **deliberately not modelled**: a
DOS 2's other variables there are its own file manager's, nothing
outside a DOS 2 reads them, and inventing values would be inventing a
DOS.

**Those bytes are at the top of `devcode`, not in a section of their
own.**  A section was the first try, named first in the memory's section
list, and the linker placed it **last**, at `$0BA4`: the order sections
are named in a memory is not the order fragments are laid into it.
`tools/mkcar.py` checks the address rather than trusting either story,
and it is what caught it, immediately, in the packer rather than on the
machine.

## The desk picture cannot be what proves it

A cartridge that served files but listed nothing would give a desk
**identical** to this one: the accessories are in the Desk menu, which
is not open.  So the gate reads `sh_naccs` -- the AES finds `*.ACC` by
opening the directory and reading it a line at a time, which is the one
thing the real system does with this handler that a file read-back never
touches.

Verified rather than asserted, which this project has learned to do:
a cartridge built with the three `.ACC` files left off gives **the same
49 calls and the same picture to the pixel**, and `sh_naccs` 0 instead
of 3.  Nothing else in the gate would have noticed.

## Twenty-six seconds, and it is the CPU

Measured, and printed by the gate every run so a change in it is seen
rather than discovered:

    165 KB of system, off the ROM        1,325 frames -- 26 seconds

**That is not the cartridge being slow.**  A Rapidus comes up with
`MCR = $FF` -- every 16 KB window on the 1.79 MHz motherboard bus -- and
nothing raises that until gem4xe's own `rapidus_speedup()` runs, which
is *after* the load.  So 165 KB goes through CIO's byte-at-a-time GET
and the handler at 1.79 MHz: about 280 cycles a byte, a third of it
CIO's loop in ROM and the rest `src/cartd.s`.

It is no worse than the floppy it replaces, and the bootstrap prints a
dot per segment, because twenty-six seconds of an unchanging screen is
indistinguishable from a machine that has hung.

Two things could be done about it and neither belongs in this phase: a
tighter `cd_get` (about 2x), and Rapidus fast mode in the bootstrap
(about 2.3x for window 0 alone).  **Window 3 is not one of them** --
that is where CIO lives, and priming its SRAM copy means reading and
writing back every byte of `$C000-$FFFF`, with `$D000-$D7FF` in the
middle of it, so the sync would write every hardware register back with
what it read.  `docs/cartridge.md` §9 costs both.

## Also in this release

**A measurement, and a question answered before enthusiasm answered it.**
`docs/multitasking.md`: gem4xe *already* multitasks -- the accessories
are processes with their own contexts and turns -- and holding two real
applications is an **allocator** problem, not a scheduler one.  The pool
is 14,336 bytes at `$4800-$7FFF` and both allocators are bump
allocators.  A swap disk does not help with that; a second pool would.

**MVN, measured on target.**  `src/sys/blkmove.s`: 2,386 KB/s against
368 KB/s for the C byte loop -- 6.5x, and nothing in the tree was using
it.  The first run hung because `##` is a 16-bit immediate in this
assembler and `#` an 8-bit one, so `lda ##0x54` emitted a stray `00`
that executed as `BRK`.

**The Rapidus cache, and a question no gate here can answer.**
`docs/rapidus-cache.md`: the 4 KB cache is **SDRAM-only**, so the far
heap crossing `$080000` is where it starts to matter -- and Altirra
stores the cache bit and models no cache, so every gate runs green
whatever the hardware does.  gem4xe write-then-executes relocated
program code with 45,640 bytes of SRAM headroom.  The gate prints the
number and asserts nothing, because crossing is not a failure; it is the
point at which only the real board knows.

**An SDK somebody else can use.**  `tools/sdk/` grew `KIND=prg|acc|cpx`
and a `DATAMODEL`, so the kit builds all three things it ships rather
than one; `acc.c` and `cpx.c` as worked examples; `install.py` and
`screenshot.py`, so testing a program is a command rather than a person
watching; and `served.md`, which is every opcode the system answers,
read out of the AES's and the VDI's own dispatch tables.

**And the desktop's model knew four file extensions where the target
knew five.**  `tools/deskref.py` now takes its executable list from the
ST's vocabulary -- `.PRG`, `.G4A`, `.APP`, `.TOS`, `.TTP` -- and
`test-m17`'s disk carries one of each.

## Gates

`m1`-`m37`, `test-boot`, `test-install`, `test-sdx816`, 285 host tests,
`check-cc`, `memreport`, `nearcast`, `opcodes`, and `modelsnap`.

`test-m37` is new and has four parts: the `.car` header on the host, the
boot and CPU switch on two machines that must give different answers,
the staging, the read-only `D1:` read back through real `CIOV`, and the
whole system booting into a desk that matches the model.
