# Memory: what GS/OS teaches gem4xe

A plan, being built: steps 1 to 4 are done ([phase116.md](phase116.md),
[phase117.md](phase117.md), [phase118.md](phase118.md),
[phase119.md](phase119.md), [phase120.md](phase120.md)).  The Apple IIGS runs the same CPU on the same kind
of memory -- one scarce bank $00, many plentiful banks above -- and its
Memory Manager (*Apple IIGS Toolbox Reference*, volume 1 chapter 12, volume
3 chapter 36; *GS/OS Reference*, chapters 2 and 8) solved the problems
gem4xe has met one at a time.  This takes its design, never its code.

## Where gem4xe hurts today

**Bank $00's application pool is a bump allocator.**  14,336 bytes at
`$4800-$7FFF`, a cursor and a mark, no headers, released only in reverse
order of loading (`src/sys/app.c`).  Everything else follows from that:

- desk accessories and Control Panel modules must load **before** the first
  program and are charged to the pool **for life** -- a module cannot load
  when the panel opens it, and an accessory cannot be added or removed;
- QED fits by 768 bytes; one more module would stop it starting;
- only one application can be resident: `docs/multitasking.md` calls it "an
  allocator problem";
- with everything loaded, 5,632 bytes are free and a program gets 6,912.

**Bank $00's own map is fixed at link time** (`src/gem4xe.scm`): LoRAM has
257 bytes free against a 256 floor and has been short six times; the
engine stack has about 40 bytes of margin under Pexec.

**The far heap is better** -- phase 79 made it a block table with owner
tags, first fit, any order -- but:

- nothing in it can be reclaimed under pressure: a resource, a font, the
  desktop's own code are either held or freed, never "keep if there is
  room";
- every return to the desktop rebuilds it: its program file is kept in
  far memory (`src/aes/shel.c`, `sh_desk_blob`), but it is unpacked and
  relocated again, and `DESKTOP.RSC` is read from the disk again;
- owners are a flat byte, 1-255; a program cannot give part of its memory
  an owner of its own and free that part in one call;
- the Atari's bank probe (Rapidus OS, kmalloc, `HIGHRAM=`, about 250 lines)
  was in the same file as the allocator, and several comments still
  described the old bump heap (both put right by step 1).

## What GS/OS does

| | GS/OS | gem4xe today |
|---|---|---|
| bank $00 | blocks, each page-aligned and locked, owned and freed by ID, in any order | a bump cursor, freed in reverse |
| a program's direct page and stack | one locked block in bank $00, sized from the program's header (kind $12), default 4 KB | part of its near region in the pool |
| owners | 16-bit user ID: type, 4-bit aux, 8-bit main; aux 0 is a wildcard for DisposeAll / PurgeAll | an 8-bit owner |
| reclaiming | purge levels 0-3 on blocks; when NewHandle fails: OOM routines, compact, purge 3, 2, 1, OOM again, then memErr | refuse |
| program exit | UserShutDown can leave a program **dormant**: its segments purgeable, restartable without the disk | freed; the desktop's file is kept, but it is unpacked again and its resource read from disk |
| placement | attributes: locked, fixed, no-cross-bank, page-aligned, fixed bank, fixed address, not-special-memory | four kinds of call, plus `far_claim` |
| moving blocks | handles; blocks move only during synchronous calls, never from interrupts | nothing moves |
| asking | FreeMem, RealFreeMem (free plus purgeable), MaxBlock | Malloc(-1): the largest block |

## The plan

In order: the cheapest first, the one everything else needs second, and
the riskiest -- moving blocks -- last and only if a need shows up.  Each
step is a phase with a gate of its own, and `make test` green before the
next starts.  This is restructuring, not speed or fixes, so it is 0.15
work; 0.14 stays the stable release.

### 1. The bank probe out of the allocator

`farmem.c`'s Rapidus OS, kmalloc and `HIGHRAM=` code to a file of its own
(`src/sys/hiprobe.c`), the allocator left machine-independent, and the
stale bump-heap comments corrected.  Nothing changes behaviour.
**Done** in [phase116.md](phase116.md).

*Gate:* `test_farmem`, `test-kmem`, `test-sdx816` and the suite, unchanged.

### 2. Bank $00 as blocks, freed in any order

The pool becomes a small block allocator of its own, on GS/OS's bank $00
rules: every block owned, freed by owner in any order.

**Done** in [phase117.md](phase117.md), with two changes from this plan,
both from reading the pool's nineteen callers.  Thirteen give back in the
call they took in, which is a stack, so those keep a top-of-pool request
and a mark (`pool_alloc`, `pool_release`), and only the lifetimes take
from holes (`pool_take`).  And blocks are not page-granular: most are
small, and a page each would cost about 128 bytes a block in a 14 KB
pool; a program's near region is page-aligned, as it was.  Nor are a
program's blocks placed from the top: the DOS command is lent the
memory from the pool's top to MEMTOP (`src/sys/dos.c`), and a desktop at
the top would leave it none.  A program goes in the lowest gap it fits,
so a freed program's hole is the next one's.

What it makes possible, each a step of its own after:

- **a Control Panel module loaded when the panel opens it** and freed when
  it closes -- **done** in [phase118.md](phase118.md);
- **an accessory added or removed** without a reboot;
- **room measured honestly**: a program that does not fit is told how much
  it needs.

*Gate:* a host model held to the C, as `farref.py` holds the far heap; the
pool walk in `memreport` from the new table; a new emulator gate that
loads and frees programs and modules out of order and checks every byte is
given back; the suite.

### 3. Owner IDs with a type and an aux

The owner becomes GS/OS's shape: a type (system, application, accessory,
module, the desktop), a 4-bit aux, an 8-bit main.  A program's private
sub-pools are its main ID with an aux; freeing by the main frees them all.
`app_free` does that, so nothing outlives a program, by construction.

*Gate:* `test_farmem` extended -- an owner's aux blocks freed by its main,
another program's untouched -- and the suite.

**Done** in [phase119.md](phase119.md): the kind and the sub-pool are a
tag beside the owner, in a far block's spare length byte and a pool
array; `Mpool` and `Mfreepool` give a program its sub-pools.

### 4. Purgeable blocks, and a reclaim order

Purge levels on far blocks, and GS/OS's order when an allocation fails:
purge level 3, then 2, then 1, retrying after each, then refuse.  The first
users are caches: a resource file kept after it is freed, in case it is
loaded again, and the fonts.

*Gate:* a model test of the order; an emulator gate that fills the far heap
with purgeable blocks and shows a fixed allocation still succeeding.

**Done** in [phase120.md](phase120.md).  The first users are the
desktop's program file (level 1) and the bytes of the desktop's resource
files (level 2), which also does much of step 5's work: a return to the
desktop no longer reads DESKTOP.RSC from the disk.  The fonts were not a
user after all -- the VDI loads its one extra face once and keeps it.

### 5. The desktop kept, dormant

When a program starts, the desktop's loaded image and its resource are made
purgeable instead of freed (GS/OS's UserShutDown with a quit flag), and
when the program ends the desktop restarts from them -- unless step 4 had
to purge them for room.  Today the shell keeps only the desktop's FILE
(`sh_desk_blob`): every return unpacks and relocates it again and reads
`DESKTOP.RSC` from the disk again, which on a floppy is the slow part.
The most visible change in the plan.

*Gate:* `test-boot`'s desk compared as now; a timed return to the desktop
from a program, before and after, in `bench-desk`.

### 6. A program's direct page and stack sized by the program

A field in the `.G4A` header for the size of the program's direct page and
stack, as GS/OS's kind $12 segment does, instead of a fixed share of its
near region.  QED's 2.5 KB frame (phase 114) would have been asked for
rather than found.

*Gate:* the stack check (test-m47) with a program that asks for more and
one that asks for less.

### 7. Handles -- only if fragmentation shows

Movable blocks through master pointers, moved only during a GEM call, never
from an interrupt.  Opt-in, for large data a program asks for that way;
every existing pointer stays a pointer.  Not before a real program is
refused for fragmentation.

## What this gives GSlayer

GSlayer's Memory Manager answers a IIGS program's NewHandle and DisposeAll
calls.  Steps 2-4 make gem4xe's allocators work the way those calls
assume: bank $00 blocks for a program's direct page and its tools'
direct pages, owners with an aux, purge levels.  The layer then translates
rather than invents.
