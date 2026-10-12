# Phase 110 -- high RAM that is somebody else's

A tester: with SpartaDOS X's `DEVICE 65816` and `DEVICE SIO816` in
CONFIG.SYS, gem4xe 0.12 never reached the desktop; 0.11 did.  gem4xe
probed the banks above its own image and took every one up to $EF.

## Who else is up there

Rapidus OS hands the high RAM out through its kernel allocator, `COP #$01`
(drac030's specification, "kmem"): kmalloc, kfree, and from 2.42 kmgetblk,
which lists the blocks in address order from LOSEGM's bank.  Read live
under AltirraSDL with Rapidus OS 2.48 and SDX 4.50, and out of the ROMs:

- **The Rapidus BIOS** (1.0-1.2), called by the OS at cold start, takes the
  top bank reset-proof -- $EF0000-$EFFEFF on a 16 MB board -- with its own
  state at $EF:EE00, and the allocator keeps its table at $EF:FF00-$FFFF.
  Altirra's stand-in BIOS returns at once, so no gate ever saw this.
- **65816.SYS** takes the allocator over, same calls, and puts its drivers
  -- the 65816 core, SIO816, EXT816 -- in a block in that top bank;
  CARCACHE and RD816 allocate from the top down below it.

gem4xe 0.12 unpacked squeezed programs at the top of its heap
(`far_alloc_top`, src/sys/app.c): over SIO816 and the 65816 core with the
drivers loaded, and over the BIOS's bank on every real Rapidus.

## What changed

- `abi_probe_os` reads one more byte of `@:SYSDEF`: byte 14 bit 0 is the
  allocator, `km_ok`.
- `km_getblk` (src/sys/sei.s) makes the call: the block number and function
  3 pushed, `COP #$01`, through gem4xe's own COP handler, which passes a
  foreign COP to the OS with the frame untouched (phase 41).
- `farmem_probe` walks the blocks when `km_ok` says there is an allocator,
  and a bank any allocated block touches is not one of gem4xe's.  The heap
  is the longest run of banks that is both RAM and free.  An OS before 2.42
  answers the first kmgetblk with an error: nothing listed, as before.
  Without Rapidus OS there is no allocator and nothing else up there; the
  probe is unchanged.

The boot screen's Memory line shows it as the range: `banks $04-$EE`
where it said `$04-$EF`.

## Not yet

gem4xe does not take its memory FROM the allocator, so something loaded
after it could be given the same banks, and it does not free it on exit.
Nor does it check that nothing sits where its own image loads (banks $01
up, written by farload before any of this).  Both are the next step.
Done in phase 112 (`docs/phase112.md`).

## Proof

- **`make test-sdx816`** (Rapidus OS 2.48, SDX 4.50, 65816.SYS from D1:) now
  reads the heap and the allocator: banks $04-$EE, one bank in use, and
  requires both.  0.12 under the same gate reaches its first wait and is
  then corrupt (a far pointer of $580BDF0).  It is in `make test` now.
- `make test`.
