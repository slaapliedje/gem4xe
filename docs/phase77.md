# Phase 77 -- Pexec gave a far resource back in bank $00

A tester building gem4xe reported four warnings from `src/sys/gemdos.c`:

    gemdos.c:2203: incompatible integer to pointer conversion assigning
                   to 'void *' from 'uint32_t'   rsc = p->p_rsc;
    ...and three more like it, for p_rsc2 and the two stores back

They were a real bug.  `gd_pexec` keeps the parent's process fields while
the child runs in the same record, and it kept the resource bases in
`void *rsc, *rsc2`.  In the small data model the system is built in a
pointer is 16 bits.  Pexec was written (`06da211`) when every resource
was in the pool, where 16 bits is the whole address; since far trees
(`6954af9`, phase 42) a resource may be in far memory, `p_rsc` is 24
bits, and Pexec cut the bank off and put back a bank-$00 address.

A GEM program with a far resource that ran anything with `Pexec` came
back with every `rsrc_gaddr` pointing into bank `$00` -- and, it turned
out when the gate ran on the old code, with `rsrc_free` refusing too.
The far heap marks (`p_rscfar`, `p_rscfar2`) were never kept at all.
Nothing had hit it: the desktop runs programs through the shell, and
the Pexec gate's program (m32) has no resource.

## The fix

`rs_hold` / `rs_unclaim` (`src/aes/rsrc.c`), the pair the AUTO and CPX
loaders already use for a program run inside another's record: all six
fields, at their own types, and the per-slot far block caches forgotten
when the child left something behind.

## Two more warnings, and why they are errors now

The same build printed two others:

- `shel.c:679`, `app_run` called with no declaration in scope.  It is
  `SIMPLE_CALL` in `abi.h`.  The listings show the undeclared call puts
  the 32-bit entry in A:X exactly as the declared one in `app.c` does, so
  control panel modules have been starting correctly -- by the luck of
  the default convention, not by design.  `shel.c` includes `abi.h` now.
- `m3_vdi.c:713`, a near pointer passed where `mn_register` takes a
  32-bit address: the right value, widened to bank `$00`; the runner's
  cast now says so.

`tools/ccdep.sh`, which every C compile goes through, now passes
`-Werror=int-conversion -Werror=implicit-function-declaration`.  In this
memory model each has been a way to lose a bank or a register silently.
With the old `gemdos.c` the build stops on exactly the tester's four.

## The gate

`make test-m33`: after its other checks M33.PRG runs `M32KID.PRG` (m32's
child, now on m33's disk too) with `Pexec`, then asks `rsrc_gaddr` for
tree 0 again.  It must get its `exit(5)` and the same far address.  On
the old `gd_pexec`:

    Pexec M32KID.PRG: returned 5, tree 0 after it in bank $00 (MOVED)
    FAIL: after a Pexec child the resource's tree 0 is in bank $00, not $07
    FAIL: rsrc_free returned 0 (step 9), expected 1
