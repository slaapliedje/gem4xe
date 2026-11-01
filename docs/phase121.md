# Phase 121 -- the desktop kept, dormant

Step 5 of [memory-plan.md](memory-plan.md).  When the desktop ends to run
a program, its loaded image -- code and variables, unpacked and relocated
-- is kept instead of freed, and when the program ends the desktop runs
again from it: no unpacking, no relocating, no reading.  GS/OS's
`UserShutDown` with its dormant flag, on gem4xe's allocators.

## How

**Keeping** (`app_keep`, `src/sys/app.c`).  Everything the desktop had goes
as `app_free`'s would -- its near region, its resource, its Malloc blocks,
its files, its workstations -- except its image, which is handed to the
system (owner 0) with the desktop's kind in its tag and purge level 1
(`far_adopt`, `far_set_purge`, phases 119 and 120).  Only a packed program
(format 5, as the desktop is) can be kept: its code and its variables
are each a far block of their own, starting where the loader recorded
them.  The shell keeps the desktop only when it ends with `shel_write`'s
SHW_EXEC -- a program it will come back from -- and only the default
desktop; a shutdown, or a desktop that `shel_wdef` renamed, is freed.

**Reviving** (`app_revive`).  The image was relocated for its far blocks,
which do not move, and for its near region, which is taken back at the
same address (`pool_claim`, new in `src/sys/pool.c`).  It gets a new owner;
its blocks are adopted back at purge level 0.  Then it is run, and its
start-up does the rest: `crt_gemapp.s` calls `__initialize_sections`, which
copies every initialised data section from the image and zeroes every
other one, near and far, at every start -- so a second run begins as clean
as a first.

**Its near region is saved, too.**  Reviving at the same address is not
enough by itself: the region is freed while the program runs -- the
program needs the pool -- and a small-data program keeps its constants, its
data initialisers and its init table in it (`src/app/gemapp.scm`,
`AppBits`).  test-m16's stand-in desktop, small-data, came back drawing the
wrong colours and then stopped.  So `app_keep` copies the whole region into
a far block at the top of the heap, with the image's tag and level, and
`app_revive` copies it back after claiming the place.

**When it cannot** -- the image was purged for room, or something else now
has the near region's place, or there is no owner to give -- the image is
given back (`app_forget`) and the desktop is loaded from its cached file
as before, or from the disk if that went too.

The record of what was kept is an `APP` in `zwin`, not a block of far
memory, so no gate's model of the heap has one more block to place.  A
purge of level 1 takes the image's two blocks together, and the purge
hook forgets the record.

## What it saves

On the Rapidus the gates run, a return to the desktop was already short:
phase 120 took away the disk read of DESKTOP.RSC, which was the slow part,
and unpacking and relocating the desktop on a 20 MHz 65C816 is a frame or
so -- test-m18 sees the second desktop reach its `rsrc_load` one frame
sooner.  What step 5 saves grows with a slower CPU, which does the same
unpacking and relocating at a twelfth of the speed.

## Gates

- `test-m18`: the second desktop, after M11.PRG, is run from its kept image
  (`sh_revived`, read by the conformance runner's sys op 3021), and its
  pictures, its G at five probes and the far heap afterwards are all the
  model's, as before.  With keeping switched off the check fails.
- `test-m16`: the stand-in desktop, a small-data program, revived after
  M11.PRG and the rest of its run -- which is what found the near region
  had to be saved.
- `test-m18` catches the second desktop in its `rsrc_load` when it can and
  says so when it cannot: revived, with its resource copied from memory,
  it can begin and end that call inside one frame, and then its stack is
  not painted or measured.
- `test-m32` models a program's `Malloc` from the whole far heap
  (`far_heap(..., everything=True)`): the dormant desktop takes room the
  program's blocks would otherwise have had.  Every other gate's view still
  leaves the cached and dormant blocks out.
- The whole of `make test`: every gate that runs a program from the desktop
  and comes back now comes back to a revived desktop.
