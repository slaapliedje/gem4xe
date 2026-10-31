# Phase 120 -- purgeable memory, and the desktop's files kept in it

Step 4 of [memory-plan.md](memory-plan.md).  Until now a far block was
either held or freed.  Now it can also be **purgeable**: worth keeping
only while nothing else needs the room, given up when a request would
otherwise fail.

## Purge levels

GS/OS's four levels, kept in the two low bits of each far block's
address, which are always zero because every block is 4-aligned:

| level | means |
|---|---|
| 0 | never purged: every block, unless its owner says otherwise |
| 1 | purged last |
| 2 | purged before level 1 |
| 3 | purged first |

When a request does not fit, the allocator purges **every** block of level
3 and tries again, then level 2, then level 1, and only then refuses -- a
level at a time, as GS/OS does it, because which block of a level to give
up first would be a guess.  Every request goes through this: `far_alloc`,
`far_alloc_span`, `far_alloc_page`, `far_alloc_top`, `far_alloc_banks`
and `far_claim`.

There are no handles here to set to nil, so each purged block is named to
`far_purge_hook`, and whoever kept it forgets it: its address may be
given out again a moment later.  A block in use is set to level 0 first
and back after, so a load that needs memory cannot purge its own source.
`far_set_purge(addr, level)` sets a level; `far_purged` counts purges.

## The first users

**The desktop's program file**, which the shell has kept in far memory
since phase 47 so that a return to the desktop costs a copy and not a
disk read, is now level 1.  If it is purged, the next return reads
DESKTOP.PRG from the disk and keeps it again.

**The desktop's resource files.**  Every return to the desktop read
DESKTOP.RSC from the disk again (about 10 KB, which on a floppy is
seconds), and every dialog it puts up read PREFS.RSC.  Now the bytes of a
resource file the desktop loads are kept, at level 2, and the next load of
the same name copies from them.  What is kept is the *file*, not the
loaded resource: `rs_fixit` and the program change a loaded resource, and
`rsrc_load` must hand out a fresh one.  So the copy is read through as the
file would be, by a reader under `rs_load` and `rs_cicons` (`rs_rd`), and
nothing else in the loader changed.

Only the desktop's resources, which means only the system directory: a
program's resource may be on a floppy the person is about to change.  Any
GEMDOS create, open for writing, delete or rename, and any DOS command
with a command line, throws the whole cache away.  A `Psystem` with no
line, which the desktop makes at every start to ask whether there is a
command processor, does not: it did, at first, and the cache was empty
every time the desktop needed it.

The copies are taken at the **top** of the heap, read low and moved up,
as phase 94's unpack span is, so that nothing the gates' models place low
moves.  Their index is 32 bytes of `zwin`, an address and a 32-bit FNV-1a
hash of the CIO name for each of four, rather than a table block, for the
same reason.  The gates' reader of the far heap (`tests/emu/farheap.py`)
leaves level-2 blocks out.

## Two traps on the way

**A span read through a far pointer.**  The copy comes from
`far_read_file`, whose block may cross a bank, and the first `rs_rd` read
it with `far_get` -- whose pointer arithmetic wraps to the foot of its
bank on this compiler.  DESKICON.RSC's colour icons came back as
nonsense, the walk over them never ended, and test-m18's desktop sat in
its `rsrc_load` forever.  `far_copy_span` is the reader.

**Polling zwin.**  `zwin` is in the window a DOS banks its own RAM into
while it works, and the gates read it from the host while the desktop's
clock and disk make DOS calls: a poll can see the DOS's bank.  The
counters a gate needs from there (`rc_hits`, `rc_fills`, `far_purged`) are
read by the conformance runner (sys op 3021) between calls, not peeked.
`src/sys/zwin.h` said so already.

## What it costs a slow machine

Keeping a copy costs the first boot something: each of the desktop's
resource files is read low, moved to the top of the heap a byte at a
time, and read through a byte at a time, and gem4xe's far copies are C
loops through far pointers, about forty cycles a byte.  On test-m37's
machine -- a 65C816 at 1.79 MHz with 960 KB, a cartridge -- from the shell
starting the desktop to its first wait:

| | frames |
|---|---|
| no copies | 1,060 |
| copies | 1,210 |

Three seconds on the first boot of the slowest machine gem4xe runs on; a
Rapidus does the same work several times faster.  What it buys is every
later return to the desktop without the disk read, which on a floppy is
the slow part.

**MVN was tried and taken out again.**  The CPU's own block move,
`blk_move` (`src/sys/blkmove.s`, seven cycles a byte where the loop costs
forty), was put under `far_copy`, `far_put` and `far_get`, and took the
three seconds back.  But SpartaDOS X's boot (test-m46) crashed at the
desktop's seventh call, in emulation mode with the data bank at $20 --
MVN's destination bank -- and the cartridge's 960 KB boot failed and
passed by turns with the same code.  A fault that depends on where an
interrupt lands is not one to ship on a guess, so every far copy is the
loop again, and the question is open: what, under an interrupt or a DOS,
sees MVN's data bank.

## Gates

- `tests/host/test_farmem.py`: the heap filled with whole banks, two marked
  level 3, one level 2, one level 1 and one 0; a request lands where level
  3 was and purges both of them and nothing else; the next needs level 2,
  alone; one nothing can satisfy purges level 1 too and is refused; the
  hook is told every address, in order.  `tools/farref.py` models it.
  Reversing the order fails it.
- `test-m49`: the same on the machine, with 256 KB spans filling a 15 MB
  heap and a 512 KB request.  Reversing the order fails it.
- `test-m18`: the second desktop, after a program, loads DESKTOP.RSC from
  the copy (`rc_hits`).  It said 0 until the `Psystem` fix.
- `test-m37`'s 960 KB boot now waits for the desktop to settle, and for no
  resource to be mid-load, before it measures the heap, instead of a fixed
  600 frames: on that machine the desktop was still loading then -- one
  `rsrc_load` of DESKICON.RSC is a single call long enough to look settled
  -- and a copy being read is unpurgeable for the moment it is read.
- `make memcheck` and the whole of `make test`.
