# Phase 100 -- memreport's missing page

Item 14 of `roadmap-0.12.md`: `tools/memreport.py`'s model of the
application pool was "a page under the live machine (7,168 against
7,424, phase 69): find the page".

## Measured again, it was a page OVER

A scratch build of GEM.COM logged every `pool_alloc` and release into
far memory, on the product's set of accessories and modules: the three
accessories, General and Color.  A launched program now gets **6,912
bytes**, where the model said 7,168.  The model had drifted to the
wrong side, which is the side that matters for a check whose job is to
fail the build when QED would not fit.

The log matched the model allocation for allocation but the first.
**The process records were 630 bytes**, where `memreport.py` charged
`7 * 52 = 364`.  `PROC` had grown to 90 bytes, as per-process state was
added for the accessories (phases 60 to 97).  The first module's region
is page-aligned, so the difference moved it from `$4A00` to `$4B00`, and
every page after it.

The page phase 69 saw on the other side was a different set of modules.
The model now walks General and Color, and that machine had General
alone.

## Read from the image, and held to the machine

- `src/aes/proc.c` exports `proc_store_size`, `NUM_PROCS * sizeof(PROC)`,
  as a word in the image.  `gem.c` and the m3 runner allocate by it, so
  it is linked, and it costs 2 bytes of Near (129 free).
- `memreport.py` reads its value out of `build/gem.elf`.  The comment
  that said "test-boot checks the live number" was wrong: test-boot
  checks only that the pool has 2 KB left, on disks with no accessories.
- **`make test-m44` now compares** the permanent floor a running machine
  reaches -- `pool_low`, on the tour disk with its gate-only `TEST.CPX`
  -- with the one `memreport.main(..., want_floor=True)` predicts for the
  same set.  With 364 put back into the model, it fails: the machine's
  `$6B00` against the model's `$6A00`.

QED asks for 6,144 and a launched program gets 6,912, so it still
starts on the full product.  The check that says so now uses the right
number.
