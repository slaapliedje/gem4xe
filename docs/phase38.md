# Phase 38 -- the boot screen, and the packed loader

A TOS machine shows its boot screen for three seconds -- the version, the
processor, the memory, the drives -- and the reason it is worth three
seconds is that it is the one place a person sees what the system found
before the desktop hides it.  On this machine there is more to find and
more to get wrong: whether the accelerator is there, how much of its
memory the probe accepted, which DOS the disk booted, whether
`GEM4XE.CFG` and `LANG.RSC` were read at all, which VBXE, which clock,
what `MOUSE=` was taken as.  Phase 29 and phase 30 were both a person
reporting a symptom ("the mouse is slow as snot", "I can't click on
anything") that a screen like this would have narrowed in one look.

So gem4xe has one now (`src/sys/bootinfo.c`), and the story of the phase
is what it cost: 3,088 bytes, which the DOS 2 floppy did not have.  The
second half of the phase is the far image travelling **packed**, which
gave the floppy back about 170 sectors and let it carry what it had been
shedding for three phases.

    make test-boot

    gem-boot.atr: ATRImage(256b x 720), a double-density DOS 2, AUTORUN.SYS
      816.COM, AUTORUN.SYS, CLOCK.ACC, CLOCK.RSC, DESKTOP.PRG, DESKTOP.RSC,
      DOS.SYS, DUP.SYS, GEM4XE.CFG, LANG.RSC
      122 sectors free, 30 KB -- DUP.SYS is on it, so GEM has a DOS to return to
      the boot screen, 560 frames after the switch:
       |  ____________________________________
       |  Version   0.1.1
       |  Processor 65C816, Rapidus
       |  Memory    14.8 MB, banks $04-$EF
       |  DOS       DOS 2
       |  Settings  GEM4XE.CFG
       |  Language  LANG.RSC
       |  Screen    VBXE 1.26 ($D640)
       |  Clock     none
       |  Pointer   ST mouse
       |  Printer   none
       |  ____________________________________
       |    Hold SHIFT to pause this screen
      the far image: 1241 bytes probed, all as the linker wrote them

## The screen

It is drawn on **E:**, the OS's own 40 x 24 text screen, through CIO --
the screen that exists before either GEM device is brought up, and the
one the OS keeps drawing to under the accelerator, because its memory is
in the 16 KB window `src/sys/rapidus.c` leaves slow.  Each line lands
right after the probe it reports, so a hang shows where it hung: the
logo, the version, the CPU and the memory come up before the VDI exists;
the video line when the device is chosen; the clock line after the RTC
probe; the pointer line as `ptr_init` gets its kind; the printer line
from the configuration.  Then a rule, a hint, and EmuTOS's hold: three
seconds, any key ends it, SHIFT held pauses it -- counted in frames,
each of which the hold spends following the beam down the logo (below).

The GTIA colour registers are written for GEM's colours, white paper and
black ink, and **not the OS shadows**, so the way out -- the OS's VBI
back -- restores DOS's blue without anyone having to remember to.
Except the ink, and the picture said so: the first `00-boot.png` had
grey text on the white, `$CA`, DOS's `COLOR1`, when the code had written
`$00`.  A frame-by-frame read of GTIA showed the register going black
with the other two and grey again inside the same frame, and the ROM
has three stores to `COLPF1`: one in the keyboard IRQ, one in the
stage-2 colour loop that `CRITIC` keeps out of every CIO call -- and one
in the VBI's **first** stage, `$C0FC`-`$C107`, before the `CRITIC` test
at `$C114`, where the XL OS refreshes the text luminance every blank
whatever else is going on.  Every row of the screen is a CIO call in
emulation mode with the OS's vectors live, so any blank that landed in
one put the grey back, and one always did.  The ink now goes through
`COLOR1`, saved first and put back after the hold.
`tests/emu/product_boot.py` reads `COLPF1` and `COLPF2` off `HWSTATE`
while the screen is held, so the gate asks the question the picture
answered -- and its first version asked it after the desktop had come
up, when `boot_end` had put DOS's grey back, which failed all three
disks at once and said nothing about the screen.

The screen is inset two columns, and E: has a left margin of its own,
`LMARGN`, two as the OS sets it and counted towards the inset -- the
first gate run parsed every label as `None`, because the rows had been
built two columns in and E: had added two more, and the parser, like
the code, had assumed a fixed column.  Both now derive it: the code
from `LMARGN`, the gate from where the rule starts.

Two rules the project already had, applied:

- **No string a person reads belongs in the C.**  The labels and the few
  values that are words (`defaults`, `built in`, `none`, the bank word)
  are `BOOT_*` strings in `LANG.RSC` (`tools/langrsc.py`); the rest --
  names of hardware and of DOSes, numbers, file names -- are the
  machine's own.  A label is at most `LANG_BOOT_LABEL` (nine) characters,
  asserted by the generator and by `tests/host/test_lang.py`, whose
  German translator now knows that a label is cut at nine and a value is
  not, because the column the values start in is what makes the screen
  readable.
- **Nothing shown once has a claim on bank `$00`.**  The logo, the names,
  the digits are all `FAR`; the row is built on the stack and written in
  one CIO call, because forty `PUTCHR`s a row through the OS is forty
  trips to the slow bus.

`tests/emu/product_boot.py` reads the E: screen back on every product
disk, parses it into label and value, and checks each against the
machine that wrote it: the version against `VERSION`, the memory line
against `farmem`'s own record, the DOS line against `dos.kind`, and
that the clock, pointer and printer lines exist at all.  It also
photographs it, `build/shots/boot-<disk>.png`; the tour (`make shots`)
takes the same picture on its way to the desk, and that one is
`docs/shots/00-boot.png`.

## The rainbow

The one thing this screen does that a TOS machine's cannot: the logo
is coloured the Atari way, a rainbow of raster bands rolling down the
letters for as long as the screen is held.  The text screen cannot do
it as it stands.  In ANTIC mode 2 the ink takes `COLPF2`'s hue and only
`COLPF1`'s luminance -- which is why GEM's black on white is the one
pair of colours the boot screen could have -- so for the hold the
logo's five rows are switched to **mode 4**, where a character is four
two-bit cells and cell value 3 is `COLPF2` for a plain character and
`COLPF3` for an inverse one.  A character set of one glyph, all eight
bytes `$FF`, makes a space paper and an inverse space the raster's
colour, and the rows as E: wrote them need not change at all.  The set
lives at `$8000`: the loader's staging buffer, spent before `main()`,
in the 16 KB the speed-up leaves on the motherboard bus, which is where
ANTIC reads.

Each frame, `boot_end` waits for `VCOUNT` to reach the first logo row,
writes `CHBASE` and the first band's colour in the horizontal blank a
`VCOUNT` step opens with, then a colour every step down the logo --
twenty bands of two lines, the hues 1 to 15 twice each so a band is
four lines and the wheel is sixty, walking down a step a frame -- and
the OS's `CHBASE` back as the rule's row begins.  Interrupts are held
off for those forty lines and no longer, so a mouse sample cannot push
a write into the picture.  No display list interrupt and no `WSYNC`:
`VCOUNT` is polled, which needs nothing installed and nothing in bank
`$00`, and what the accelerator does with a halted bus is not a thing
this screen wants to find out.  The display list is walked, not
assumed: blank lines, then a mode-2 instruction a row with the first
carrying the address, and anything else leaves the logo black, which
is a boot screen too.  The switch happens with the beam below the
logo, so no frame shows a mode-4 row with the OS's set, whose space is
empty in both colours; the way back likewise, and the desktop starts
with the OS's list and set as they were.

**The compiler took the first version down**, and it took a day to
see how.  The polls were written against byte variables, `while (vc <
LOGO_TOP) ;`, so that each was `lda`, `cmp`, branch and the store
landed inside the blank.  `make test-boot` then said the desktop never
set its device, and the picture showed the logo black and the machine
in the BRK handler.  Watchpoints on the variables never fired -- the
bridge's `WATCH_SET` does not see writes into the accelerator's fast
RAM -- but a breakpoint on the BRK vector's stub in bank `$00` does
halt, and with `CONFIG history true` the `HISTORY` before it is the
whole story: the second `VCOUNT` wait in `frame()` compiled to

    ?L300: lda $D40B ; cmp #19 ; rep #32 ; bcc ?L300

The width switch is *before* the back edge.  The first pass is right;
the second loads a word, `cmp #19` takes three bytes and swallows the
`rep`'s opcode, and the next instruction is the branch's own operand
followed by whatever comes after -- `20 90 f7`, a `jsr` into the
middle of `farmem_probe`, whose `rtl` landed in the OS ROM and BRKed.
It needs -O2, a conditional return before the loop and 16-bit code
after it; the minimal shape is six lines and it is **B16** in
`tools/ccbug` (`b16.c`, compiled alone and its listing read, since the
code cannot be run; the shape the sources use runs in `bugs.c`).  The
polls now read `VCOUNT` into a word through a helper, `while (vcount()
< line) ;`, and compare the word: a `jsl` per poll, which at 20 MHz
is nothing against a scan line.  A listing reader written for the
occasion went over every source in the tree with its own flags and
found the shape in nothing but the eight polls.

## What it cost

The screen is far code and far constants, so bank `$00` did not notice.
`gem.xex` did: 133,536 bytes became 136,624, and `build/gem-boot.atr`,
the double-density DOS 2 floppy, had **twelve sectors** left
(`shipping.md`).  Twelve sectors is 3,036 bytes.  The build broke on the
floppy, not on the machine.

The floppy had been losing things for three phases -- its `DUP.SYS` in
phase 37, its accessory in phase 36, the full `GEM4XE.CFG` replaced by a
generated short form -- and the honest reading of the arithmetic was
that the next kilobyte would take the desktop's resource.  The system is
131 KB of far image, and a 65816 program is compressible: it is jump
tables, parameter blocks, `jsl` sequences that differ in one operand.
The loader was already reading the image in chunks through a staging
buffer and copying them up (`phase6.md`); the copy is where a decoder
goes.

## The format

`tools/mkxex.py` packs each far ELF segment independently into tokens,
and its docstring is the specification.  A token is one byte, `LLLL
MMMM`: `L` literals follow (15 means read extension bytes until one is
not 255), then a 16-bit offset, then the match of `M + 4` bytes is
copied from the output so far, `offset` bytes back (15 again means
extension bytes).  Overlap is allowed, so a run is offset 1.  Minimum
match four, offset up to 65,535, hash on four bytes: LZ4's shape with
the constants chosen for a decoder that has to fit in 507 bytes of
emulation-mode 65816 and run with the OS's interrupts on.

    130,759 far bytes -> 87,400 packed (66%) in 17 chunks of up to 6,656
    gem.xex 136,624 -> 90,468 bytes; the floppy: 12 sectors free -> 122

**One detail the first draft got wrong, on paper rather than on the
machine.**  A run of incompressible data has to be flushed as literals
in pieces (1,024 at a time, the buffer's worth), and a token that is
"literals, then nothing" is indistinguishable from "literals, then a
four-byte match" once the next token begins.  The reference decoder in
the host test would have read a match where there was none, and the
65816 with it.  So a token is *always* followed by its offset word, and
**offset 0 means no match**: the token was its literals, `M` must be 0,
nothing follows.  A chunk's last token may drop the word -- the header's
output count says when to stop -- and `join()` strips it, which is what
makes the packed stream and the unpacker agree on where a chunk ends.
`tests/host/test_mkxex.py` has that case (`incompressible flush with no
match word`, `no dangling no-match word at chunk 1100`) and every chunk
is unpacked by the reference decoder at build time before it is written,
so a packer bug fails the build and not the boot.

Each chunk is one `.xex` segment: a five-byte header -- 24-bit
destination, 16-bit output count -- immediately before the payload, then
an `INITAD` segment pointing at `_fl_copy`, exactly as before.  A chunk
is cut at a token boundary, packed size within the buffer, output within
a word.

## The decoder

`src/farload.s`, in a section of its own.  It runs in emulation mode,
`D = 0`, with the OS's VBI and SIO alive under it, because it is called
by DOS's binary loader between two reads of the file.  Its working
registers are the OS's floating-point page, `$D4-$E5` -- free while no
BASIC is running, and nothing in a DOS's loader uses them (measured:
DOS 2, DOS II+/D, SpartaDOS 3.2, SpartaDOS X all load the product
through it).  Source, destination and match pointers are 24-bit and are
dereferenced with `[dp],y`, which is why it is 65816 code and why the
CPU check that already guarded the copier still comes first.

The inner loop is a page-run copier: the length of a run is the least of
the bytes left, the bytes to the end of the source's page and the bytes
to the end of the destination's, so the 24-bit pointers advance once a
run and the `[dp],y` addressing never crosses a page inside one.  The
match pointer is the destination minus the offset, in 24 bits, so a match
may reach back across a bank boundary into the previous chunk's output
-- the packer's window is the whole segment, and the test
`matches across chunk seams` is there to say so.

**Where it lives is the one map change.**  `farstage` was the staging
buffer alone, `$8000-$9F13`; now `Stage` is `$8000-$9A04` (header and
6,656-byte buffer) and **`StageCode` is `$9A05-$9BFF`**, 507 bytes of
decoder, both under SpartaDOS X's screen at `$9C00` and both inside the
MEMAC A window, which is plain RAM until `vbxe_init()` opens it -- the
same free lunch as before.  They are two memories rather than one
because a `bss` section cannot share a memory with one that carries
bits: the linker packs sections with contents and then places the
empties, and the buffer landed on top of the code.

Two things the assembler and the linker said before the emulator got a
turn: `duplicate symbol: fl_next` (the PBI slot scan of phase 23 already
had one; it is `fl_nextslot` now), and `symbol 'fl_noram' referenced
from section 'stagecode' ... out of range` -- a conditional branch from
the decoder to the refusal in `code`, which is a `jmp` through a local
stub now.  On the machine `make test-m6` read 1,960 probed bytes of the
m3 image and 1,866 of the split one back out of banks `$01`-`$03`, all
as the linker wrote them, first time.

`make test-m1` failed once, on its first run after the change, with the
signature unwritten and DOS II+/D back at its prompt, and passed on the
next three runs and every one since.  The screen of the failing run was
not kept.  It is recorded here because a one-in-five that does not
reproduce is the kind of thing this notebook exists for; it is not
understood.

## The About box that said 0.1

The desktop gates found something else once the screen was done, and
it is older than the screen.  `test-m17`, `m18`, `m19`, `m23` and
`m26` failed together with the same shape: every object tree the model
predicted sat two bytes below where the target had it, and the About
box differed by 225 pixels.  Two bytes is the difference between
"version 0.1" and "version 0.1.1", and the About box is where
`tools/deskrsc.py` puts the contents of `VERSION`.

`build/desktop.rsc` is made from `deskrsc.py`, and the Makefile listed
the tools it reads but not the file it reads.  So when `VERSION`
became `0.1.1`, the resource was not remade; the model, which is
Python and reads `VERSION` every run, moved; the target kept the
resource it had.  The gates said "G at probe differs" rather than
"the About box is stale", which is fair -- they compare the trees, and
the trees differed -- but it means the first thing to check when
every desktop gate moves at once is whether the resource on the disk
is the resource the model thinks it is.

The rule lists `VERSION` now.  The consequence that matters is not the
gates: **the 0.1.1 release's `system/DESKTOP.RSC` says "version 0.1"**
in its About box, because `make release` built from that same stale
file.  The tarball, the zip and the `.atr` on GitHub all have it.
Nothing else in them is wrong -- `VERSION` reaches the C through
`build/version.h`, which did depend on it, so the boot screen says
0.1.1 -- and the fix to the published assets is a decision
for the release, not for this notebook.

## What the room bought

The DOS 2 floppy carries, again, the things it had been shedding:

- **`DUP.SYS`.**  GEM returns to DOS when it quits, and on a DOS 2 that
  return is a jump to a shell that has to be on the disk (`shipping.md`,
  section 2, has DOS 2.5 taking an illegal instruction inside itself
  when it is not).  `product_boot.py` used to assert its *absence*, so
  that it could not come back by accident; it asserts its presence now,
  for the same reason.
- **The full `GEM4XE.CFG`**, all 1,922 documented bytes of it.
  `tools/mincfg.py`, which generated the short form, is gone.
- **`CLOCK.ACC` and `CLOCK.RSC`**, so the accessory is on every product
  disk and not only the SpartaDOS ones.  `test-m26` noticed before
  anyone did: it still judged "is the desktop at its first wait" by
  `gem_calls`, which counts every process's calls, and the accessory's
  seven put the desktop at "call 50" -- the mistake `test-boot` made
  the day the accessory arrived (`src/sys/abi.c`, `gem_entry`), on the
  one gate whose disk had no accessory to make it then.  It reads
  `app_calls` now.

And a floor: the gate requires **80 sectors free** on the DOS 2 disk,
which is `DESKTOP.INF` and a program or two, and prints the figure so
the next phase that eats into it sees it go.

The BSP (`~/dev/Calypsi-65816-Atari`) keeps the plain four-byte-header
loader; nothing there is short of a sector.  `tools/mkxex.py` is what the
application kit ships too, but a `.G4A` is not a `.xex` and `mkg4a` uses
only its ELF reader, so the kit is unaffected.
