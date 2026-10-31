# Phase 119 -- owners with a kind and sub-pools

Step 3 of [memory-plan.md](memory-plan.md).  Every block in both of
gem4xe's allocators had an 8-bit owner and nothing else.  Now it also
carries a **tag**: the owner's kind in the high four bits and a sub-pool
in the low four.  With the main owner, that is GS/OS's 16-bit user ID:

| | GS/OS | gem4xe |
|---|---|---|
| main | 8 bits | `far_owner`, 1-255, one per loaded program |
| aux | 4 bits; 0 is the main ID itself | the sub-pool, 1-15; 0 is the owner's own memory |
| type | 4 bits | the kind: system, program, accessory, module, desktop, AUTO program (`OWN_*`, `src/sys/farmem.h`) |

## Where the tag lives

Nowhere new in the far heap.  An entry's address had the owner in its top
byte since phase 79, and its length's top byte was always zero, because
no block is 16 MB.  The tag goes there; every reader of a length masks
it, `far_shrink` keeps it, and `far_keep`, which hands a block to the
system, clears it.  The pool gets a fifth array, `pb_tag`, 32 bytes of
`zwin`.  `far_tag`, the tag the next block takes, sits beside
`far_owner` and is in `zwin` too, because LoRAM is at its floor.

A context's owner was already 16 bits, with the high byte unused; it
holds the tag now, so a switch puts back both, and so does `app_exec`
around a program.  The loader stamps the kind: the shell says what it
is loading (`app_kind`) before an accessory, an AUTO program, a module
or the desktop, and anything it does not say is a program.

## What it is for

**Freeing by owner frees every sub-pool.**  `far_free_owner` and
`pool_free_owner` match the main owner and ignore the tag, so a
program's exit takes everything it had, whichever sub-pool it was in.
Nothing outlives a program, by construction.

**A program can free part of itself in one call.**  Two GEMDOS calls,
gem4xe's own:

| call | | |
|---|---|---|
| `Mpool(n)` | `0x1F4` | what the program takes from now on -- `Malloc`, `Mxalloc`, a resource, anything gem4xe takes on its behalf -- goes in its sub-pool `n`, 1 to 15, or back in its own memory with 0.  Answers the sub-pool before. |
| `Mfreepool(n)` | `0x1F5` | every block of sub-pool `n`, 1 to 15, freed at once. |

The program's sub-pool is in its context, so a switch to an accessory
and back keeps it.  This is what GSlayer's Memory Manager needs for a
IIGS program's `DisposeAll` and `PurgeAll` with an aux ID: translation,
not invention.

**A block says what owns it.**  A gate or a memory listing can tell an
accessory's block from the desktop's without knowing which owner number
went to whom.

## Gates

- `tests/host/test_farmem.py`: owner 9 takes a block of its own and two
  in sub-pool 3 (one shrunk, which keeps its tag), owner 10 takes one in
  its own sub-pool 3, and `far_free_sub(9, 3)` frees exactly owner 9's
  two: their hole is the next one's, owner 9's own block and owner 10's
  sub-pool 3 survive, and `far_free_owner(9)` then takes the rest.  A
  `far_free_sub` that ignores the sub-pool fails it.
- `tests/host/test_pool.py`: the same for the pool.
- `test-m32`: the GEMDOS gate's program calls `Mpool(3)`, `Malloc`,
  `Mpool` back, `Malloc`, `Mfreepool(3)`; then the first block cannot be
  freed again and the second can.  With `Mfreepool` doing nothing it
  fails.
- `test-m44`: on the product's disk, the desktop's near region is of the
  desktop's kind and the three accessories' blocks are an accessory's.
- `test_bind`: the two bindings, and the binding simulator's record
  buffer from 260 to 300 entries, which the new calls had filled.
- The whole of `make test`.
