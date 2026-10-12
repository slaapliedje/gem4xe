# Phase 112 -- the high RAM, asked for and given back

Phase 110 stopped gem4xe taking banks the Rapidus OS had already given
out.  It still took everything else it could write to, held none of it
in the OS's books, and gave nothing back.  A tester's Antonia II (the
Rapidus OS runs there too, since 2.48) has its banked RAM and its flash
inside the same 16 MB, so "it reads back what I wrote" is not "it is
mine" there; and a driver or program loaded while gem4xe runs could be
given the banks it was using.

## Where the high RAM is

The OS is told by the board's BIOS where its high RAM lies, LOSEGM to
HISEGM ($024D, $024E; $01 and $EF on a 16 MB Rapidus, HISEGM the last
bank, inclusive).  When the allocator is there (`km_ok`), the probe
keeps inside that range: a bank outside it is not RAM the OS hands out,
whatever a write to it reads back.

For a board whose OS says nothing, `HIGHRAM=` in `GEM4XE.CFG` fences the
heap by hand: `HIGHRAM=$04-$3F`, or in decimal.  Parsed straight into
two direct-page bytes of farmem.c's, as `MOUSEPORT` goes into the
pointer's; anything malformed is ignored.  What gem4xe holds of the
allocator is on the direct page too (`km_heap`, `km_image`, `km_clash`,
`km_held`): LoRAM, where `farmem` is, was 5 bytes short of its reserve
with them in the struct.

## Asked for

Two blocks are taken from the allocator (`kmalloc`, `COP #$01`
function 1, src/sys/sei.s `km_malloc`), mode 0 -- the OS's `kfree`
will not free a resident block:

- **the image**, the banks from $01 that src/farload.s filled before
  any of this ran, from the first page the OS has not taken (it keeps
  $010000-$0100FF where the zero page is mirrored there);
- **the heap**, 64K-aligned, whole banks.

One bank of the free run is left for somebody else when the OS is
sharing the RAM out: SpartaDOS X's drivers and commands ask it for high
RAM, and a DOS command runs while gem4xe holds what it took.

`kmalloc` takes no address; it places a block at the first free place
that fits.  A block that lands below the chosen place (a heap fenced by
`HIGHRAM=`) is handed back, the gap under the place filled with a spacer
block, and the request made again; the spacers are freed once it lands.
A block that lands anywhere else is handed back and the heap runs
unclaimed, as before.

If the OS had already given out some of the image's banks -- gem4xe has
loaded over them by the time it can ask -- the boot screen says so under
the Memory line: `in use before GEM: $01-$03`.

## Given back

`farmem_release()` frees both blocks before every way back to DOS
(src/gem.c), while the OS's calls still go out through the vectors they
came in by.  After a DOS command, `farmem_held()` asks the OS whether
both are still allocated: SpartaDOS X runs the command as a program of
its own, and frees a finished program's blocks.

## The check that could not tell

`test-sdx816` quits to the SpartaDOS X prompt and runs the OS's own
`KMSCAN.COM`: one free block from $010000, 65816.SYS's system block at
$EF0000, nothing else.  It passed with `farmem_release()` taken out --
SpartaDOS X frees gem4xe's blocks when gem4xe ends.  So it shows the OS
is left clean, not that gem4xe cleaned it.

DOS 2 frees nothing.  `test-kmem` boots the DOS 2 floppy under Rapidus
OS, quits to DUP and loads `AUTORUN.SYS` again: the second run must find
what the first did.  Without the release it found one bank,
`Memory 0.1 MB, banks $EF-$EF`, said `in use before GEM: $01-$03`, and
could not start.

## Proof

- `test-kmem` (Rapidus OS, DOS 2): image block $0100, heap block $0400,
  banks $04-$EE (HISEGM $EF less the bank left), both allocated; the
  second run the same, one Memory line; a cold boot with
  `HIGHRAM=$10-$1F` has banks $10-$1E and its block at $1000.
- `test-sdx816` (Rapidus OS, SpartaDOS X, 65816.SYS): banks $04-$ED
  ($EF is 65816.SYS's, $EE left), both blocks held after the DOS command
  runs VER, and KMSCAN after Quit shows only free space and the system.
- `make test`.

## Not yet

- **Banked RAM that is also linear RAM.**  An OS that does not keep it
  out of LOSEGM-HISEGM leaves it to `HIGHRAM=`.  Finding it -- a mark
  written through each PORTB and Axlon bank, looked for in the linear
  banks -- needs a board that does it, and none is emulated.
- **A second run with one bank** crashed rather than refusing.  It only
  happens when somebody else holds nearly all the high RAM.
