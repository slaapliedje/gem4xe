# Phase 117 -- bank $00's pool frees in any order

Step 2 of [memory-plan.md](memory-plan.md).  Bank $00's application
pool was a bump allocator: a cursor, wound back to a mark, so memory
went back only in the reverse order it was taken.  That one fact is why
accessories and Control Panel modules had to load before the first
program, and why a program's exit could free an accessory's memory
silently if the accessory had taken it a moment too late.  The pool is
now a table of blocks with owners, in `src/sys/pool.c`, and frees in any
order.

## Two kinds of request

The pool has nineteen callers.  Thirteen give back in the same call they
took in -- GEMDOS's read slices, the file selector's work, an alert's
tree -- and that is a stack, which the old comment in `app.h` was right
to keep.  Six hold memory for a lifetime: a program's near region, its
resource, an accessory's, its message queue, the process records.  So
there are two requests rather than one:

| | where | given back by |
|---|---|---|
| `pool_alloc(n, align)` | the top, always | `pool_release(mark)`, as before |
| `pool_take(n, align)` | the lowest gap it fits, a hole a freed block left included | `pool_free(block)` or `pool_free_owner(owner)` |

`app_load` takes a program's near region with `pool_take`; the thirteen
stack-like callers did not change at all.

## Owners

Every block is taken as `far_owner`, the far heap's owner (phase 79), so
a program's blocks in both allocators belong to one owner, and
`src/sys/ctx.c` already keeps that right at every context switch.
`app_free` and `Pexec`'s child free the pool by the program's owner, not
by its mark.  `pool_release(mark)` now gives back only the **current
owner's** blocks above the mark, and cuts short one of its blocks that
the mark goes through, which is what `rs_imfar` relies on when it moves a
resource's images far and keeps the rest.  An accessory that takes a
block while a program's file selector is up keeps it when the selector's
work goes; before, it went with it.

## Nothing moved

`pool_mark()` is still an address, the top of the highest block.  The
gates place their models' trees there (`tools/aesref.py`), the DOS
command's `MEMLO` is it (`src/sys/dos.c`), and `pool_brk` and `pool_low`
keep their names and meanings for the gates that read them.  With no
block freed out of order -- every flow before this phase -- every block
lands exactly where the cursor put it, so `tools/memreport.py`'s layout
and every desktop gate's picture are unchanged.

The table is 32 entries of five bytes, in three arrays rather than an
array of a struct (Calypsi B7), in `zwin` and not in the pool, so the
pool's addresses are the ones they were.  `test-boot` measures 2 and 3
blocks held at the desktop on its disks; with every accessory and module
the product ships, `tools/memreport.py`'s layout is 11, and an alert up
adds four more.  LoRAM, at its floor, pays nothing: the table's
count and its "full" counter are in `zwin` too, and `zwin` has 171 bytes
left.  A take refused for a full table is counted in `pool_full`.

## What it does not do yet

The shell still loads accessories and modules before the first program
and marks the floor after them.  Nothing requires that of the pool any
more; loading a Control Panel module when the panel opens it, adding an
accessory, and telling a program that does not fit how much it needs are
the steps the plan lists next.

## Gates

- `tests/host/test_pool.py`: one script through `pool.c` in the
  compiler's simulator and through `tools/poolref.py`, the rules in
  Python; every answer and the top after every step must agree, and the
  table stay sorted and inside the pool.  The script is the product's
  own shape first, then what the cursor could not do: a block freed out
  of order, a program loaded into the hole another left below a module,
  an accessory's block surviving a program's release, a release cut
  through a block, the floor refusing, and the table running out.  Two
  deliberate breaks of `pool.c` -- a release that ignores owners, a take
  that never looks in holes -- each fail it.
- `test-m48`: two programs loaded by the real loader in the conformance
  runner, the LOWER one freed first, a third loaded into its hole, the
  top coming down when the upper one goes, and at the end the pool's
  table, its top and the far heap exactly as they were, with no release
  refused.  With `pool_take` made bump-only, as the old pool was, it
  fails.
- `test-boot` prints the blocks held at the desktop and fails if a take
  was ever refused for a full table (`pool_full`).
- `test-m5p`'s wait for the runner went from 1,850 frames to 4,250.  The
  plain 65C816 loads the runner over SIO at stock speed, and this phase's
  code made it take exactly 1,850; the wait ends as soon as the runner is
  ready, so the longer ceiling costs a passing run nothing.
- The new hook in the conformance runner keeps its program record
  `static`: as a local it made the runner's command function's frame
  bigger, that frame is under every `Pexec` the runner makes, and
  `test-m32`'s `Pexec` was refused for want of the 1 KB of stack it
  checks for.
- `make memcheck` and the whole of `make test`.
