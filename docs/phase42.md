# Phase 42 -- the rest of GEMDOS: a console, the standard handles, Pexec and Pterm

GEMDOS arrived in phase 14 with the calls the desktop asks for -- files,
directories, searches, Malloc, the clock -- and grew to twenty-six.  That
is what a GEM program needs.  It is not what a *ported* program needs: a
command-line tool prints with `Cconws` and reads with `Cconin`, a C
runtime ends with `Pterm`, a shell runs other programs with `Pexec` and
sends their output somewhere with `Fforce`.  Every one of those answered
EINVFN.  Now every call TOS 1.04's GEMDOS has is served, and what each can
mean on this machine is written at its function in `src/sys/gemdos.c`.

## The console

On the ST, handles 0 and 1 end at the console: a VT-52 terminal the BIOS
draws in the system font over whatever is on the screen (The Atari
Compendium, 3.13).  Here the screen is GEM's, so `src/sys/con.c` draws
through the AES's own waist (`src/aes/graf.c`) in cells of the system
font -- 80 x 30 on the VBXE, 40 x 24 on ANTIC.  A cell's background is a
solid fill in the paper colour, the characters on it a transparent text
run in the ink, a scroll one screen-to-screen blit; printable characters
are gathered into runs, so a line is two VDI calls, not two per character.

Every escape in the Compendium's table is there -- the cursor moves, E J
K L M d l o, Y, b and c, e and f, j and k, p and q, v and w -- and CR, LF,
BS and TAB.  Where gem4xe is not the ST it says so in `src/sys/con.h`:
the colour numbers are VDI indices (0 white, 1 black on either screen)
rather than hardware pens; the cursor is a solid block drawn only while a
program waits for a key, and it starts enabled, which is what the ST's
desktop does for a TOS program; wrap starts off, as TOS's console does
(EmuTOS `bios/vt52.c`); a TAB is the spaces GEMDOS's own output makes.

The keyboard is read through the AES's own wait, `ev_keybd`, so while a
program sits in `Cconin` the pointer moves and the accessories have their
turns.  `Cconis` and `Crawio` look without waiting (`ev_keyq`, new beside
it), and a key `Cconis` finds is held for the next read rather than
taken.  `^C` at `Cconin`, `Cnecin` or `Cconrs` ends the program with -32,
as GEMDOS does; `Crawcin` hands it over as a key.  `Cconrs` is EmuTOS's
`cgets`: BACKSPACE and DELETE, `^X`, `^U` and `^R` after a `#`, RETURN
ending the line with a carriage return.

## The standard handles

The ST gives every process six.  They are a row of bytes per process in
far memory, each naming what the handle reaches -- the console, `aux:`,
`prn:`, nothing, or an IOCB when it has been forced onto a file -- with a
row of the four `Fdup` hands out beside it.  A file one of them names
counts them and stays open while anything does: `Fforce(1, h)` then
`Fclose(h)` is how a program sends its output into a file and lets go of
the handle, and the file stays open for handle 1.  `Fclose` of a standard
handle puts it back to its device and answers E_OK, as EmuTOS's `xclose`
does.  Every character call goes through the handle it is the ST's for,
so a program's `Cconws` lands in the file once handle 1 has been forced.

The devices have their own handles, the ST's -1, -2 and -3, which `Fopen`
answers for "CON:", "AUX:" and "PRN:".  `prn:` is `GEM4XE.CFG`'s `PRINTTO`,
opened on the first byte and closed when the program ends, and it is
*nowhere* while `PRINTER=NONE` -- the default, because a machine that has
said it has no printer must not wait for one.  `aux:` has no device
behind it yet: it takes nothing, gives 0xFF1A -- MiNT's end of file,
where the ST would hang -- and is never ready.

## Memory, the clock, Super

The far heap is still a bump allocator.  What changed is that every
Malloc'd block now carries a LONG in front of it, its size and a mark, so
the *last* block can be given back by `Mfree` and cut down in place by
`Mshrink` -- which is what a program that allocates, uses and frees in
turn needs -- and an address Malloc never gave out is refused, EIMBA.
`Mshrink` bigger is EGSBF, as on the ST.  `Mxalloc` is Malloc: there is
one kind of memory.  And `Malloc` that cannot now answers 0, the ST's NULL;
it answered ENSMEM, which a program testing for NULL would have used as an
address.

`Tsetdate` and `Tsettime` set the clock `clock_read` reads.  On the
DS1305 (U1MB, SIDE) the seven registers are written with the chip's write
protect lifted for the moment and put back; through SpartaDOS X it is
kernel call 101, `kd_settd` (the number from cc65's `asminc/atari.inc`).
A bad date, or no clock, is non-zero.  Altirra's model answers every read
with the host's time, so a write cannot be read back in the emulator:
nothing here has set a real card's clock yet.

`Super(1L)` says supervisor, -1, as TOS tells a supervisor (EmuTOS
`bdos/rwa.S`); anything else changes nothing.  A 65C816 program already
has the whole machine.

## Pterm

A program ends itself with `Pterm`, `Pterm0`, `Ptermres`, or `^C`.  GEMDOS
sets `gem_term`, and the COP handler, after the call, does not return to
the program (`src/sys/abi.s`, `gem_cop_term`): it goes where main() would
have returned to -- `app_run`, whose S `gem_api_sp` has held since the jsl
into the program -- with the code in A where main's value would be.
Everything the program pushed lies under that and is left behind; D and
DB are gem4xe's already; `app_run` now keeps the caller's P around the
call so the interrupt state comes back too.  The loader cannot tell a
Pterm from a return, which is the point.  Nothing stays resident after
`Ptermres`: there is nothing on this machine for a TSR to hook.

## Pexec

Mode 0, load and go.  The child is loaded above its parent -- the pool
and the far heap are bump allocators, and the child's end winds both back
-- and entered as its parent was; the call waits inside it, on the engine
stack under the parent's COP, until its main() returns or it ends with
Pterm, and the code is the answer.

It runs as the same process, because the ST's AES does not know about
Pexec either, so what GEMDOS keeps per process is kept for it: the child
starts with its parent's standard handles and none of its files, a DTA of
its own, and `shel_read` answering with its own name and the tail it was
given (`sh_push`/`sh_pop` in `src/aes/shel.c`).  At its end its files
close, its searches go, a virtual workstation it left open is closed
(`vdi_close_virtuals_but`, which leaves the parent's), its resource slots
are put back, and the handles, the DTA and the call gate's words are the
parent's again.  What it did to the screen, the windows or the menu bar
is its own business, as on the ST.

Modes 3, 4, 5 and 6 are about a basepage -- memory laid out the 68000's way
for a loader to fill in -- which a .G4A is not loaded into; they say
EINVFN.  A child's calls are served under its parent's on the one engine
stack, so a Pexec with less than a kilobyte of it left is refused, ENSMEM
(`ctx_stack_lo`, from the linker through `src/sys/ctx.s`).

## Bank $00

It had one byte above its floor.  GEMDOS's five far pointers became one
far block with fixed offsets (sixteen bytes back), which paid for
`gem_term` and left the rest; the console, the handle rows and the
printer's IOCB are all in that far block.  LoRAM went from 257 bytes free
to 272; Near gave two bytes to `ctx_stack_lo`.

## The gate

`make test-m32` runs `M32.PRG` (`src/m32_con.c`) from the stand-in
desktop, and the program never calls the AES.  It writes a page of VT-52
that uses every escape, and the screen is held against `tools/conref.py`
-- the console's model, written from the Compendium's table and drawn
through `aesref`'s waist -- with the cursor waiting after it.  It reads
`K`, then a line with a backspace in it, `Z`, `^C` and a key `Cconis`
found; the screen is held again with the echoes on it.  It forces handle
1 onto a file, writes with `Cconws`, `Cconout` and `Fwrite`, puts it back
through `Fdup`'s handle, reads the file back, then forces handle 0 onto it
and reads it with `Cconin`, `Cconrs` and `Crawcin` to 0xFF1A.  It runs
`M32KID.PRG` (`src/m32_kid.c`) with handle 1 forced onto a file: the child
reads its tail, writes it, leaves a file open, a handle duplicated and 4 KB
allocated, and ends with `Pterm(5)` -- and the parent's own file is still
open after it, the heap is where it was, a missing program is EFILNF and
mode 3 EINVFN.  It checks Super, Mxalloc/Mshrink/Mfree to the byte,
`aux:` and `prn:` with nothing behind them, and ends with `Pterm(42)` from
inside a function, the program itself left holding a forced file and a
duplicate.  The shell's record says 42, not the 7 main() returns after the
call; the desktop comes back and reads a key; no IOCB is left open, and
the pool and the far heap are where they were.

## What went wrong on the way

- **Every answer was 3.**  The first run drew the page perfectly and then
  stopped at the `Q`.  Sampling the PC showed a key wait, and the frozen
  call count said `Cconis` had not been called again -- so it looked as if
  `Cconis` itself was blocking.  It was not: reading the running call's
  function number out of the block (`gem_pb`) said 8, `Cnecin`.  The loop
  had never run.  `Cconis` had answered 3, and so had every key call
  before it.  The calls that wait are served by `gd_nopath`, which
  returned a flag and stored the result through a pointer into
  `gemdos_call`'s `r`; it is a static called once, Calypsi 5.18 inlined it,
  and the store went nowhere -- B3's family (`tools/ccbug/README.md`), the
  same shape `gsx_tcalc` was rewritten for.  It returns the result now,
  with a sentinel for "not one of these".  Four more shapes of the same
  family in the new code were rewritten before they could bite: parameters
  clamped on one path of a conditional (B10) in `con.c`'s cursor, `gd_rw`
  and the clock's `weekday`, and a `?:` at a switch's join (B9).  Why the
  first run never went on past its `Q` when three diagnostic runs with the
  same timing did is not known; the stale answers were the defect, and
  the gate has passed on every run since.
- **The desktop gates moved by four bytes.**  test-m17, m18 and m23
  compare the desktop's globals with the model's, and the desktop's
  `Malloc` arena now starts after its header.  `aesref`'s Malloc took the
  header too.
- **test-m15 expected refusals** for calls that exist now: `Tsetdate` as
  EINVFN (it is -1 for a day 0, on every machine), and `Fclose(3)` as
  EIHNDL (it is E_OK).  The refusal counter's check moved to `Maddalt`,
  which stays refused.
- **The gate program did not fit.**  A small-data program's string
  literals are near constants, and the page is 397 bytes of them; the
  default 256 bytes of near constants would not hold it.
- **`clock.c` used `FAR` without `portab.h`,** which `test_portab` says.

## The floppies

All of this is 10,316 bytes of code -- `gemdos.o` 6,373 more, the console
2,952, the clock's write path 611 -- and 7,602 more bytes of `GEM.COM` on
a disk, and `make test-boot` said so: the DOS 2 floppy went to 65 free
sectors, under the floor of 80 kept for a program of the user's own.  The
floor stayed.  Every floppy is now the system and nothing else; the
applications and the desk accessory are on a floppy of their own,
`gem-apps.atr`; and each SpartaDOS floppy carries an `INSTALL.BAT` that
copies what it holds onto a drive the user names, `-INSTALL D2:`
(`tools/mkcf.py`).  The DOS 2 floppy is back at 87 free.

The batch files were written from the SpartaDOS X 4.50 manual and run in
the emulator before they were kept: `IF EXISTS +S` sees a directory, `%1`
is the drive, `>` at the start of a path is the root of the drive the
batch started on, and a batch goes on past an error.  One batch a disk
rather than one that asks for the next, because the manual warns against
changing the disk a batch is running from.  `make test-install` boots the
SDX cartridge with a blank disk in D1: and both floppies beside it, runs
both installs and the system's again over the first, lists the drive,
and cold-starts it into the desktop with the clock accessory loaded.
`docs/media.md` has the layout and who each disk is for.

## Not here

`Maddalt` (there is no memory the probe missed), `Flock`, and MiNT's
calls say EINVFN.  `aux:` wants a serial device -- an 850's `R:` -- to put
behind it.  The ST's desktop clears the screen for a TOS program ("TOS
takes over"); gem4xe has no TOS program type yet, so a console program
from the desktop writes over the desk.  The BIOS and XBIOS (`COP #$42`
and `#$58` are kept free for them) and a C `stdio` over these calls in
the kit are the next things a port will ask for.
