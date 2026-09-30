# Phase 79 -- the far heap gets an allocator

**The result first: Altirra's 65C816 with 960K now boots the cartridge to
the desktop**, with every accessory and both control panel modules
loaded -- the machine a 0.9.1 tester's white screen came from
(docs/phase78.md).  The desktop came up there with 30 far blocks in
twelve banks; before this phase it needed nineteen.

Until now the far heap was a bump pointer with marks (`src/sys/farmem.c`):
a program's exit wound it back to where the program's load had found it,
a resource freed itself only if nothing had been taken above it, and
GEMDOS's `Mfree` and `Mshrink` worked only on the last block.  Anything
permanent sat under a floor, `far_keep_mark`, so that no release could
reach it.  It was simple and it could not fragment, and on a 65C816 with
960K it could not start the desktop (docs/phase78.md).

## What it is now

**A table of blocks**, sorted by address, in the first bank of the heap
-- the table is block 0, 256 entries, 2 KB.  Free space is what lies
between two blocks, so there is no second list to keep in step with the
first.  Each entry is the address with its **owner** in the top byte,
and the length.

**Owners.**  0 is the system: the shell's buffers, the desktop's cached
file, the table, every context's save area.  `app_load` gives each
program a new one (`far_new_owner`), and `far_owner` says whose the next
block is.  The owner is kept in the context (`CTX.owner`,
`src/sys/ctx.h`), and `ctx_switch` makes it `far_owner`, so a resource an
accessory loads while it runs is the accessory's and not whoever ran
last.  `app_exec` sets it around a program's run in record 0: the
desktop, a program, a `Pexec` child, an AUTO program, a control panel
module.  `app_free` frees a program's owner, every block at once.  An
accessory's owner is never freed, and that is all "permanent" means now:
the keep mark is gone.

**Four kinds of request**, each the lowest place that fits:

| | |
|---|---|
| `far_alloc` | 4-aligned, never across a bank: a far pointer's arithmetic is sixteen bits |
| `far_alloc_span` | 4-aligned, may cross: a file read whole |
| `far_alloc_page` | page-aligned, ending at or below a limit in its bank: phase 80's packed code, which must stay under the $D5 page |
| `far_alloc_banks` | whole banks, the lowest free run |

Whole banks come from the lowest free run and not from the top of the
heap, which would have kept them out of the small blocks' way: on a
Rapidus the top of the heap is SDRAM, behind a cache that no gate here
can say is coherent for code the loader writes and then runs
(docs/rapidus-cache.md), and the first megabyte is SRAM.

Freed singly (`far_free`), by owner (`far_free_owner`), cut down in place
(`far_shrink`), and asked for the biggest request that would fit
(`far_largest`).

## What moved onto it

- **`far_read_file`** can no longer take a file a slice at a time from
  the cursor, since there is none: it takes the largest free span, reads
  into it, and shrinks it to the file.
- **`app_load_file` frees the file once the program is in place.**  The
  loader copies the image and applies the fixups and never reads the
  file again, so an accessory's 5 KB file stops costing 5 KB the moment
  it has loaded -- which the bump heap could not do.
- **GEMDOS**: `Mfree` gives a block back wherever it is, `Mshrink` cuts
  it down in place, and `Malloc(-1)` is the largest free block, as on the
  ST.  `Pexec` frees the child by its owner and its own save block by
  address.
- **`rsrc.c`**: a far resource, its moved icon bitmaps and its colour
  icon extension are each a block, freed directly.

## The model, and the gates

`tools/farref.py` is the same rules in Python.  `test_farmem.py` writes
a script of 31 requests -- a bank's edge, exactly the rest of one and a
byte more, a page block against the $D5 page, spans, frees out of order
and by owner, a shrink, the largest gap, a heap run out -- and runs it
through `farmem.c` in the compiler's simulator and through the model;
every answer must agree, and the simulator checks the table's order and
that no `far_alloc` block crosses a bank after every step.  It was made to
fail first: rounding to 8 instead of 4 in `farmem.c` gave eleven
disagreements.

The desktop gates placed the desktop by arithmetic on one cursor.  They
now read the target's table (`tests/emu/farheap.py`) and run the shell's
requests through the model (`desk_places`, m17): the file, the code's
banks, the resource.  The model's GEMDOS `Malloc` is the model heap too.
After a desktop run the heap must be what it was plus the cached file.

m32's memory checks measured Malloc(-1) differences, which a largest-free-
block answer does not give.  It now predicts every answer from the heap
as it stood, and asks two questions that show a shrink and a free did
what they say: 900 bytes after `Mshrink(p, 100)` land at `p + 104`, and
100 bytes after `Mfree(p)` land at `p` -- which the bump heap would have
failed, `p` not being its last block.

`CTX` grew a word (m27's size), `APP.far_mark` became `APP.owner`, and
`far_refused` and `FARMEM.brk` are gone.

## m37: three small machines

`small_machines()` in `tests/emu/m37_cart.py` boots the whole-system
cartridge on Altirra's own 65C816 three ways:

    960K                      the desktop: the shell has run it
    192K                      the loader refuses ("no linear RAM in bank
                              $04 ... Press a key") and waits
    960K, heap cut to three   gem4xe's own words (docs/phase78.md) with
      banks by the bridge     "192 KB", and waits; a key starts it again

Altirra has no size between 192K and 960K, so the third machine is made:
the gate waits for `farmem_probe` to have run -- `farmem.banks` non-zero
-- and before the shell has, pokes `last_bank`, `banks` and `bytes`
down to three banks.  `still_waiting` checks the cartridge's step has
not moved ten seconds on, which a cold start would have reset.
