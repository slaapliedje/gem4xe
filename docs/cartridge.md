# A gem4xe cartridge

One file you download, put on a flash cartridge, and look at.
**Read-only**, which is the detail that decides everything below: it
means there is no DOS to write, and most of what a DOS is does not have
to exist.

---

## 1. The barrier it would remove is real

The public release ships `gem4xe-0.6.1.atr`, and **it does not boot on
its own**.  It carries no DOS by design: it boots under SpartaDOS X,
which lives in the machine rather than on the disk.  Run it without one
and you get a blue screen of `BOOT ERROR`, which is what I got the first
time I pointed the kit's own screenshot tool at it.

The release page says so honestly and points at
<https://sdx.atari8.info/> -- but "download SpartaDOS X separately, work
out which image, put it in your cartridge slot" is three steps before
anything happens.  There is a `gem-boot.atr` in this tree that boots
standalone into the desktop with nothing typed, and the public release
leaves it out because **the DOS on it is not gem4xe's to give away**.

So: the thing standing between a newcomer and the desktop is a DOS
licence, not a technical problem.

## 2. The memory map is already clear

`src/gem4xe.scm` has said this since the map was written:

    $A000-$BFFF  NOT OURS: SpartaDOS X is a cartridge and this is it.
                 Under a disk DOS it is RAM and gem4xe leaves it alone.

gem4xe runs with a cartridge in that window every time it boots under
SDX, and it never touches it.  `$8000-$9BFF` is the MEMAC window and is
borrowed only at LOAD time, by `farload.s`'s staging buffer.

**So a cartridge costs gem4xe nothing and needs no change to the map.**
That was the thing most likely to sink this, and it does not.

## 3. It does not need a DOS

The request is for a **demo**: something to put on a flash cartridge and
look at.  Read-only is fine.  That is not a small relaxation, it is most
of the problem.

**What a DOS mostly is, is the write side** -- a free-sector bitmap,
allocation, a VTOC, directory maintenance, the whole business of
changing a disk without corrupting it.  A read-only device needs none of
it.

What gem4xe actually asks a `D1:` for, and this is the complete list:

| | |
|---|---|
| open a file by name, read it, close it | `DESKTOP.PRG`, `DESKTOP.RSC`, `LANG.RSC`, the accessories, the extensions, and anything you double-click |
| a directory | opened as `D1:*.*` and read as text -- **17-character records**, `src/sys/dos.c`'s `DIRLINE`, which is DOS 2's own format |
| which drives exist | a bitmap |

That is a **CIO device handler**, not a DOS: a `D` entry in HATABS and a
handful of vectors over a directory laid out in ROM.  Hundreds of lines
of 6502, not thousands, and the directory-as-text format is the easiest
thing in the world to generate from a table.

**And nothing writes at boot.**  There are exactly three write sites in
the whole system -- `CPX_Save` (`src/apps/cpanel.c`), *Options -> Save
desktop* (`src/desk/deskwin.c`) and a file copy (`src/desk/deskfun.c`)
-- and all three are things a person does on purpose, after the desktop
is up.  `CPX_Save` already reports failure through `xcpb->ok`, and the
other two already put up an alert.  So a read-only disk **boots to a
complete desktop** and only disappoints somebody who tries to save.

That is the answer to "do we need an open source DOS": **no.**

## 4. What it still has to carry

A cartridge containing *only* gem4xe still boots a machine with **no
D1: at all**, and the shell's first act is to load `DESKTOP.PRG` from a
disk that is not there.  So it brings its files with it.  Three pieces:

1. **A bootstrap.**  The cart's init runs on the 6502 -- a Rapidus
   cold-boots as one -- finds the accelerator, switches it, and stages
   the image bank by bank from the cart window into far memory.  This is
   `src/farload.s`'s job with a different source, and that code already
   exists, already identifies the CPU before its first store, and
   already refuses a machine it cannot run on.
2. **The read-only CIO handler** of section 3.  This is the piece that
   does not exist, and it is what lets **gem4xe itself stay completely
   unchanged**: it sees a DOS-2-shaped device and never knows.
3. **A packer**, `tools/mkcar.py`, laying the banks out and writing the
   16-byte `.car` header.

## 5. The type, and the sizes

**AtariMax 1 Mbit (`MaxFlash_1024K`)**: 128 banks of 8 KB at
`$A000-$BFFF`.  That is the type SpartaDOS X's own cartridge image uses,
so it is proven on this rig, in Altirra, and on an Ultimate Cart.
MegaCart 512K/1M/2M are the alternatives if a 16 KB window turns out to
be easier to stage from.

    GEM.COM                    112,831
    DESKTOP.PRG                 41,745
    resources, accessories      ~30,000
    the system, near enough    ~190 KB   against 1 MB

Comfortable, with room for `\APPS\` and a few documents so there is
something to double-click.

**And it is testable**: Altirra takes `--cart`, so a gate can boot the
`.car` and compare the desk against the model exactly as `test-boot`
does today.  That matters -- this would otherwise be a feature only
hardware could check.

## 6. The disk route, which this replaces rather than needs

The earlier draft of this document recommended finding a freely
redistributable DOS first, and putting it on `gem-boot.atr` -- which
already boots standalone into the desktop and is left out of the public
release only because its DOS is not gem4xe's to give away.

**That is no longer the prerequisite.**  It was the recommendation while
"the cartridge needs a file system, therefore it needs a DOS" was the
reading; section 3 is why it does not.  The cartridge is now the
*shorter* path to a thing somebody can download and run, because a
read-only handler over a ROM directory is smaller than finding, testing
and shipping somebody else's DOS.

It keeps an independent value, and a real one: a bootable `.atr` serves
everybody with a FujiNet, an SDrive, an SD cartridge or a real drive,
and a `.car` serves only people with a cartridge that takes one.  So it
is worth doing **after**, not before.  When it is:

- **MyDOS is the obvious candidate, and it works now** (`docs/phase50.md`):
  it never mangled the load, it saved CIO's zero-page IOCB with a 6502
  wrap that a 65816 carries into bank `$01`.  `make test-mydos` boots the
  desktop from it.  What is left is whether it may be redistributed.
- **BW-DOS** is the other candidate and has never been tried.

## 7. FujiNet

FujiNet is an SIO device -- disks, printer, network -- with no cartridge
port, so it cannot present a `.car` to the machine.  What it can do is
**fetch one**, which is what "downloaded from FujiNet" means: the file
arrives over the network and goes onto the flash cartridge.  Nothing
here depends on that, and nothing here has to serve it.

## 8. The order to build it

1. **The packer and the bootstrap.**  DONE, 2026-09-23 --
   `tools/mkcar.py`, `src/cart.s`, `src/cart.scm`, gated as `test-m37`.
   A 1 MB AtariMax image whose bank 127 the machine comes up on, boots,
   prints and can be read back.  The gate checks the header on the host
   *and* the boot on the machine, because a wrong type or a wrong bank
   gives a cartridge that is perfectly valid and does nothing -- silence,
   not an error, which is indistinguishable from broken code.  Confirmed
   by moving the bootstrap to bank 0 and watching it say so.

   Two things it settled.  The Calypsi linker drops an object nothing
   references, so every cartridge section is `root` -- without it the
   link succeeds and produces an empty ROM.  And **never read `$D5xx`**:
   real AtariMax hardware switches bank on a read of that page and this
   tree's Altirra deliberately does not, so code that reads it works
   here and changes bank under itself on a real cartridge.

   **The CPU switch too.**  A Rapidus always cold-boots as a 6502, and
   the cartridge finds the card, switches it, and the reset brings the
   machine straight back to the cartridge -- which is *easier* than the
   disk path, where `farload.s` has to force a cold start so the DOS
   runs its start-up file again.  Here the cartridge is still in the
   slot and the OS calls it again by itself.

   It cannot loop, and that is proven rather than reasoned about:
   switching resets the CPU and nothing else, the card keeping its mode
   across it, so the second pass finds a 65816 and stops.  `test-m37`
   boots the same image on a machine with no Rapidus, where it must say
   so and stop -- two machines, two answers, and they have to differ or
   the pair proves nothing.
2. **The staging.**  DONE, 2026-09-23 -- payload banks out of the
   cartridge and into far memory, 16,384 of 16,384 bytes, gated in
   `test-m37`.  The pattern each byte carries depends on its offset AND
   its bank, so two banks arriving swapped or one arriving twice fails
   the check as loudly as a byte going missing; proven by making bank 1
   a copy of bank 0 and watching it report `0/8192`.

   **The copier cannot live in the cartridge**, and that is the whole
   shape of this step: selecting a payload bank replaces `$A000-$BFFF`,
   which is where the code doing the selecting would be.  A loop that
   switched banks from the cartridge would delete itself between one
   instruction and the next.  So it is copied down to page 6 and called
   there, is written position-independently -- every reference a
   zero-page one, a hardware address or a relative branch, and no `jsr`
   or `jmp` of its own -- and puts the bootstrap's bank back **before**
   it returns, so the `rts` lands in a window that exists again.

   The destination is probed before a byte goes near it, with
   `farload.s`'s two values: a 65816 with nothing where the payload is
   going is as fatal as a 6502 and much less obvious.

3. **The read-only `D1:`.**  DONE, 2026-09-23 -- `src/cartd.s`, 1,179
   bytes linked at `$0700` where a DOS would have been, carried in the
   cartridge and copied down.  OPEN by name, GET a byte at a time, CLOSE,
   and the directory as DOS 2's 17-character records; PUT and SPECIAL
   refuse, because a write that silently did nothing would leave a
   program believing it had saved.

   **The proof is a read, not an installation.**  CIO will dispatch into
   a table of rubbish just as willingly, so the cartridge opens a file
   through the ordinary `CIOV` and reads it, and the gate checks the
   length and the sum against the file on the host.  Then the directory,
   and the gate checks the RECORDS rather than a checksum of them --
   a sum proves the bytes and not their shape, and the shape is what
   `dos_dirline` parses:

       '  HELLO   TXT 002\x9b'
       '  OUT     TXT 003\x9b'

   The expected listing is built in the gate from `src/sys/dos.c`'s
   description of the format, not from the handler's output, which is
   the only way the two agreeing means anything.

   Three things it cost.  A **magic word** in front of the handler,
   because without one the bootstrap copied 2 KB of erased flash to
   `$0700` and CALLED it on an image that carries no handler -- which
   survived by luck.  A **precedence bug**: `.byte1 DEV_AT+DEV_HDR` binds
   as `(.byte1 DEV_AT) + DEV_HDR`, so the copy read from `$B404`, found
   `$FF` and called that too.  And the per-IOCB state is **data rather
   than bss**, since the handler travels as one run of bytes and a bss
   section would have been a hole in the middle of it.
4. **The whole system on it.**  DONE, 2026-09-23 -- `build/gem4xe-sys.car`
   boots into the desktop from one file, with nothing typed and nothing
   else to find, and `test-m37` compares that desk pixel for pixel with
   `tools/deskref.py` exactly as `test-boot` compares the product
   floppies.

   **The one job of a DOS that read-only did not make go away is loading
   a program**, so the bootstrap grew a `.xex` loader: the `$FFFF`, then
   `<first> <last> <bytes>` segments read straight to where they go, CIO
   given the destination so the loader holds no pointer of its own.  What
   it could not simplify is the vector rule -- **call `INITAD` after
   EVERY segment and point it at an RTS once you have** -- because
   gem4xe's far image travels as a hundred chunks each followed by a
   two-byte segment that writes that vector, and a loader that fired it
   once would unpack the first chunk and jump into an image nine tenths
   absent.  `tools/mkxex.py` measured that rule in September and this is
   the second reader of it.

   **What the machine has no owner for is DOS 2's variables at `$0700`.**
   `Drvmap` returns `DRVBYT` at `$070A` verbatim, and with the handler
   linked from `$0700` that byte was one of its branch offsets -- so the
   desktop would have drawn a drive icon per bit of an instruction.  The
   handler owns the first sixteen bytes now: a `JMP` to its entry, and
   `DRVBYT = 1`, which is the truth.  `MEMLO` goes up past it, and
   `DOSVEC` is pointed at the OS's cold start, because on a cartridge
   "quit" means the machine comes back up and finds the cartridge still
   in the slot.  Those bytes are **at the top of `devcode`, not in a
   section of their own**: a section was the first try and the linker
   placed it last, at `$0BA4` -- the order sections are named in a memory
   is not the order fragments are laid into it -- and `tools/mkcar.py`
   checks the address rather than trusting either story.

   **The desk picture cannot be what proves it.**  A cartridge that
   served files but listed nothing would give a desk identical to this
   one: the accessories are in the Desk menu, which is not open.  So the
   gate reads `sh_naccs` -- the AES finds `*.ACC` by opening the
   directory and reading it a line at a time, which is the one thing the
   real system does with this handler that a file read-back does not.
   Verified by building a cartridge with the three `.ACC` files left off:
   **the same 49 calls and the same picture to the pixel, and `sh_naccs`
   0 instead of 3.**  Nothing else here would have noticed.

   **It also cost a confusing afternoon two calls from its cause.**  A
   refused OPEN leaves this machine's CIO with the IOCB still claimed, so
   the next OPEN answers 129, "already open".  The step-three image
   stopped reading `HELLO.TXT` the moment a `GEM.COM` it does not carry
   was looked for first.  The loader closes after a refusal now, which is
   what a DOS does anyway.

## 9. What it costs, which is twenty-six seconds

Measured, and printed by the gate every run so that a change in it is
seen rather than discovered:

    165 KB of system, off the ROM        1,325 frames -- 26 seconds

**That is not the cartridge being slow, it is the CPU being slow.**  A
Rapidus comes up with `MCR = $FF` -- every 16 KB window on the 1.79 MHz
motherboard bus -- and nothing raises that until gem4xe's own
`rapidus_speedup()` runs, which is after the load.  So 165 KB goes
through CIO's byte-at-a-time GET and the handler at 1.79 MHz: about 280
cycles a byte, of which roughly a third is CIO's loop in ROM and the rest
is `src/cartd.s`.

It is not worse than what it replaces -- a floppy reading the same 165 KB
through SIO is the same order -- and the bootstrap now prints a dot per
segment, because twenty-six seconds of an unchanging screen is
indistinguishable from a machine that has hung.

Two things could be done about it, neither of them step four's:

- **A tighter `cd_get`.**  About 180 of the 280 cycles are the handler's,
  and a good deal of that is a `jsr`/`rts` pair per byte and a 24-bit
  decrement.  Perhaps 2x, so twenty-six seconds becomes fifteen.
- **Rapidus fast mode in the bootstrap**, which is the 11x.  Window 0
  (`$0000-$3FFF`) is safe and is what `rapidus.c` already does; window 2
  must stay slow because the cartridge is in it; **window 3 is where CIO
  lives and must not be made fast** -- priming its SRAM copy means
  reading and writing back every byte of `$C000-$FFFF`, and `$D000-$D7FF`
  in the middle of that is hardware, so the sync would write every
  register back with what it read.  Window 0 alone is about 2.3x.
  It would also make the boot screen report the cartridge's `MCR` rather
  than the firmware's, which `test-boot` reads, so it is a change with a
  gate of its own.

## 10. Saving, when there is a floppy

BUILT, 2026-09-24 (`docs/phase51.md`).  With a DOS disk in drive 1 the
OS boots it first (`$BFFD` bit 0) and the cartridge's D1: becomes an
**overlay**: reads try the floppy and fall back to the ROM, writes go to
the floppy, and the listing is the ROM's entries the floppy lacks
followed by the floppy's own.  Other units are the DOS's.  So *Save
desktop* and a control panel extension's settings land on the floppy
and win over the ROM at the next boot -- with no change to gem4xe, whose
every write is an `Fcreate`.  With no drive it is the read-only
cartridge above, about two seconds slower to start.  Tape is out: a
cassette has no names and no directory.

The demo it produces is a machine that comes up in the desktop with a
drive icon, the trash, three accessories in the Desk menu and programs to
double-click -- from one file, with nothing typed and nothing else to
find.
