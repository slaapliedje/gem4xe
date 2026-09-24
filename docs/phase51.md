# Phase 51 -- a cartridge that saves to your floppy

The cartridge of phase 49 is read-only, and says so: *Save desktop* and
copying a file refuse.  The request after it was the SpartaDOS X shape --
a system you could release on a physical cartridge, with settings and
files saved to a floppy.

**Tape is not in this.**  gem4xe works in files and directories, and a
cassette has neither: no names, no random access, no listing.  It could
hold one settings blob, and that is not what was asked for.

## The DOS comes from the floppy

Writing a floppy needs a real DOS -- the write side is exactly the part
the cartridge's handler does not have (`docs/cartridge.md` §3).  The
cheap way to get one is to let the floppy bring it:

- **`$BFFD` bit 0 is set**: "boot a disk too".  With a DOS disk in drive
  1 -- MyDOS, DOS 2, an ATR on a FujiNet -- the OS boots that DOS before
  it starts the cartridge.  With no drive, it tries, gives up, and the
  cartridge behaves exactly as before.  That try costs about **two
  seconds** in Altirra (1,475 frames to the run vector against 1,325);
  what it costs on real hardware with an empty drive or none is for the
  hardware test.
- **The CPU switch moved into `CARTINI`**, which the OS calls before the
  disk boot.  Left in `CARTRUN`, the floppy's DOS would boot once on the
  6502 and again after the switch's reset.  Now it boots once, on the
  65816.  `cart_run` still asks the same question, so a machine with no
  card is still told so on the screen.

## D1: is an overlay: the floppy on top, the ROM underneath

When the handler installs and finds a `D` already in HATABS, a DOS booted
first.  It keeps that DOS's handler table and puts its own in the slot,
and then:

| | |
|---|---|
| OPEN to read on D1: | the DOS first; the ROM if the floppy has no such file -- so what you saved is what you get |
| OPEN to write, append, update | the DOS: the floppy is where writes go |
| the directory of D1: | the ROM's entries the floppy does not also have, **then the floppy's listing verbatim** |
| a raw directory (AUX1 `$14`) | the DOS, untouched |
| XIO -- rename, delete, format -- and STATUS | the DOS |
| D2: and up | the DOS, entirely |

**Nothing in gem4xe changed for it.**  Every write site in the system is
an `Fcreate` -- `DESKTOP.INF` (`src/desk/deskwin.c`), a CPX's `.CFG`
(`src/apps/cpanel.c`), a copy -- and none is an update in place.  So no
write ever has to modify a ROM file, and "reads from either, writes to
the floppy" is the whole rule.

**The listing's order is forced.**  `Dfree` reads the free-sector figure
from the **last** line of a listing (`src/sys/gemdos.c`), so the floppy's
own listing -- free line and all -- has to go out last and unaltered.
And it has to leave out the ROM entries the floppy also has, or a
`CLOCK.ACC` on both would load twice.  Knowing which ones means reading
the floppy's directory before the ROM part goes out, and there is no
room to buffer it: page 6 is the only RAM free under every DOS and under
gem4xe.  So OPEN reads the floppy's directory once through, noting each
name that is also in the ROM -- a bit per entry per IOCB, 24 bytes in
all -- closes it, and opens it again for the listing the caller reads.
That costs a second read of the floppy's directory, and it holds nothing
back.

While it does that reading itself, CIO's length in zero page is set to
zero: a DOS 2 reads straight into the caller's buffer when a GET asks for
a lot at once, and that buffer is not where these bytes are going.

## The handler left $0700

It had been copied to `$0700` -- the room a DOS would have taken on a
machine with none.  On a machine that booted one, that *is* the DOS.  So
the handler now runs from the ROM, in the boot bank, which is what the
window shows whenever CIO calls it.  Its state and one eleven-byte stub
live in page 6:

    $0600-$060C   the bootstrap's flags, and "a DOS was here first"
    $0610         the stub: select a payload bank, read one byte, select
                  the boot bank again, return.  The one thing that cannot
                  run from the window it switches.
    $0620-$0625   the .xex loader's variables
    $0626-$06AA   the handler's per-IOCB state
    $06B0-$06B3   the demo's write, read back

With no DOS it writes the sixteen DOS-2-shaped bytes at `$0700` itself --
`DRVBYT` = 1 and a zero boot flag -- and `MEMLO` goes to `$0710`.  With a
DOS, `$0700` is the DOS's and none of this happens; nor does `DOSVEC`
change, so quitting gem4xe goes to the DOS's menu as it would from a disk.

## Two things MyDOS taught on the way

**Its last byte comes with status 3**, "end of file on the next read",
not 1.  The bootstrap's demo accepted only 1 and read 265 of a 266-byte
file.  It accepts anything under `$80` now, as a CIO caller should.

**Its sizes have four digits** on a double-density disk: `DOS     SYS
0018`.  The overlay's pre-pass wanted a 17-character line and hid
nothing -- and **gem4xe's own `dos_dirline` read three digits of four**,
so every file under MyDOS showed a tenth of its size.  Both read to the
end of the line now.  That one is a gem4xe fix, and it is in `GEM.COM`.

## The gate

`test-m37` has two new cases, and a MyDOS floppy (`build/cart-floppy.atr`,
from the `[dos].mydos` fixture) carrying the DOS and a `HELLO.TXT` whose
contents are **not** the ROM's:

- **the overlay**, on the demonstration image: the read of `HELLO.TXT`
  gets the floppy's 266 bytes, not the ROM's 149; the listing's ROM part
  is `OUT.TXT` alone, then MyDOS's own lines, its free line last; and a
  file created on D1: reads back through D1: -- and is then found **in
  the floppy image itself**, byte for byte, which is the check that means
  "it went to the floppy" rather than "the cartridge says so";
- **the whole system over MyDOS**: `GEM.COM` from the ROM (the floppy has
  none), three accessories found through the overlay's listing, drive map
  `0x03` because MyDOS's `$070A` is not one (`docs/phase50.md`), and the
  desk pixel for pixel against the model.

Three of the new checks were seen red before they were green, each on a
real fault: the read (265 of 266), the listing (the ROM's `HELLO.TXT`
still in it) and a stale address in the gate itself.

`m1` also changed, and the first fix was wrong.  It failed two runs in six
under the full suite and never alone.  The first reading was that it
typed `HELLO` before the DOS was at its prompt, so the gate was made to
wait for the prompt -- and it failed again under the next suite with the
DOS **never** reaching one in 3,000 frames.  The real cause is in
`docs/shipping.md` already: *a write made while the DOS is mid-SIO is
lost and the DOS hangs.*  `m1` flipped the CPU switch at "frame 30",
which is frame 30 after the bridge connects -- 50 to 100 frames into a
boot already running, later on a loaded host -- so it sometimes landed
in the boot's disk I/O.  Now it waits for the 6502 boot's prompt, THEN
switches, then waits for the prompt again, as `test-boot` and `m14` do.
The other gates that switch on a timer wait 300 frames, after a DOS 2
floppy has finished booting, and a slow bridge only makes them later.
Nothing `m1` boots was touched by this work; the gate was racing, which
is the lesson this tree has had before (`docs/phase14.md`).

## What is not known

- **Real hardware**, all of it: what the OS does with bit 0 and an empty
  drive or no drive at all, and the Ultimate Cart with a floppy beside it.
- **RESET.**  A warm start rebuilds HATABS and runs the DOS's `DOSINI`,
  which puts the DOS's own `D:` back; the cartridge's `CARTINI` does not
  re-install the overlay.  After RESET, D1: is the floppy alone.  Untested.
- **SpartaDOS 3.2 underneath** gets files through the overlay but not a
  merged listing -- gem4xe asks a SpartaDOS for raw directories, which go
  to the DOS untouched -- so the ROM's accessories would not be found.
  SpartaDOS X cannot be underneath at all: it is a cartridge itself.
- **A floppy that is not a DOS disk** -- a game, say -- boots as a
  cartridge-plus-disk machine always has, and takes the machine.
