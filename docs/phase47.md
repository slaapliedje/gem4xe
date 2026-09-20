# Phase 47 -- resources go far, six accessory slots, and fourteen truncated addresses

This phase began as a UI and turned into a structural change, because
the UI would not fit.

The control panel the audit asked for is a small thing: two settings, a
dialog, an accessory shell around it.  It was written, it built, and
then the pool overflowed by **254 bytes** at the moment a second
accessory was loading.  Bank `$00` had run out, with a 15 MB machine
underneath it.

There were two ways out.  One was to make the dialog smaller and keep
going -- which buys one accessory and produces the same conversation at
the third.  The other was to ask why a **resource** was in bank `$00` at
all.  The second is what happened, and it is the whole of this phase.

## Why bank $00 is the scarce thing, and nothing else is

Worth restating, because the number looks absurd next to the hardware.

The 65816 confines two things to bank zero and the WDC manual is
explicit about both: *"This direct page is ... limited to bank zero"*,
and *"the stack pointer has been unbound from page one to float anywhere
in bank zero"*.  It adds that *"direct page and stack-based values are
always accessed in bank zero"*, and that *"the interrupt vectors ... are
located in bank zero, and they point to interrupt handling routines
which also must be located in bank zero"*.

So a program on this machine has 14.9 MB for code and data, and one
64 KB bank for its stack, its direct page and anything the OS must reach
without a bank register.  Of that bank, `$0000-$1FFF` is the OS and DOS,
`$8000-$9BFF` is the MEMAC window, `$9C00-$9FFF` is SDX's screen,
`$A000-$BFFF` is on the 1.79 MHz bus and `$C000-$FFFF` is ROM.  What is
left for applications is `$4800-$7FFF`: **14,336 bytes**, which is the
figure the memory report prints and the reason a control panel could
overflow it.

One thing in that manual is *not* a constraint, and it is worth saying
because this tree had assumed it was: *"bank boundaries do not confine
indexing, which crosses them into the next bank"*.  Far-pointer
arithmetic failing to carry into the bank byte is a **Calypsi**
property, not a silicon one.

## The change: rs_load prefers far, rather than falling back to it

Since the far-trees work (`docs/far-trees.md`), `rs_load` could put a
resource in far memory -- but only when the file *would not fit* in the
pool.  Far memory was the fallback.  That is backwards: the pool is the
scarce resource and far memory is the plentiful one, so far should be
the preference and the pool the exception.

`src/aes/rsrc.c` now reads:

```c
mark  = pool_mark();
gofar = wants_far && !(hdr.rsh_vrsn & NEW_FORMAT_RSC);
mem   = gofar ? NULL : pool_alloc(size, 2);
if (mem) { ... } else if (gofar) { /* the far path */ }
```

Two conditions, and both matter.

**`wants_far` is opt-in, not inferred.**  It is `int_in[0]` bit 0, set
by the large-data kit.  A `--data-model=small` program holds 16-bit
pointers; hand it a far resource and every `ob_spec` it reads is a
number it cannot follow.  So the caller states that it can take one, and
the AES believes it.  This is visible in the memory report: the clock
accessory links `G4A_LIB` and its 268-byte resource is charged against
the pool, while the control panel and the calculator link `G4A_LIB_LD`
and theirs are not.  Same AES, same call, different answer, because they
asked different questions.

**Colour icons stay in the pool.**  `NEW_FORMAT_RSC` resources carry
`CICONBLK` chains whose internal pointers this loader fixes up as 16-bit
quantities.  Rather than ship a half-converted path, those are refused
the far route and keep the behaviour they had.

The desktop itself became a `--data-model=large` program to take
advantage of it, which is where most of the win came from: its 6,398-byte
resource left bank `$00` entirely.

## What it cost: fourteen addresses truncated to sixteen bits

The change is four lines.  Making the tree survive it was the work.

`ob_spec`, `te_ptext`, `te_ptmplt`, `te_pvalid`, `ib_ptext`, `ib_pdata`,
`mn_tree`, `fd_addr` -- these are LONGs that hold ADDRESSES.  While
every resource lived in bank `$00`, taking the low sixteen bits of one
was correct, and a great deal of code did exactly that, in the plainest
way.  Fourteen places in this tree, in two flavours:

**An explicit `(uint16_t)` cast** -- code that stated an assumption which
had just stopped being true.  Nine in `src/desk/`, four in
`src/apps/clock.c`, one in the calculator.  These were findable: the
clang warnings from `tools/ccdep.sh` name them.

**A silent one.**  `wind_set(WF_NAME)` and `WF_INFO` in
`src/desk/deskwin.c` passed a title's low word and a hardcoded `0` for
the high word; `WF_NEWDESK` did the same in both the `gem.h` macro and
`wind.c`.  Nothing warns about that -- the call takes two words and it
was given two words, one of them wrong.

Two others were their own shape.  `menu_register` had been bouncing its
string through `abi.c`'s 64-byte `str_scratch`, which is fine for a call
that reads its argument and returns -- but the AES keeps a registered
name for the life of the machine, and `str_used` winds back to zero on
the next call.  It now stores the full 24 bits.  And `w_ptext` used to
*copy* a window title into a 41-byte near buffer; it now just assigns
the address, which deleted `gl_nbuf` and `gl_ibuf` (+82 bytes of LoRAM)
and removed the 40-character cap on a far title as a side effect.

## The one that did not announce itself

Thirteen of the fourteen were found by reading.  The fourteenth was
found by bisecting disk images, and it is the reason this phase has a
tool in it.

`CALC.ACC` hung the desktop.  Not a crash: the hourglass came up over an
empty desk and stayed.  No `BRK`, no `irq_fault`, no refused AES call.
`gl_mntree` read 0, `gem_which` said `$44` -- inside GEMDOS -- and
`gem_calls` was frozen at 47.

Three disk images settled where it was: two accessories were fine, and
two-including-the-calculator were not, so it was the calculator and not
the count.  The cause was six lines into `calc.c`:

```c
TEDINFO *ted = (TEDINFO *)(uint32_t)tree[CDISP].ob_spec.index;
return (char *)(uint32_t)ted->te_ptext;
```

with `(uint16_t)` where both `(uint32_t)` now are.  The calculator had
been writing its display over bank `$00` -- on top of the engine -- at
the same offset the text would have had if the resource were near.

**`tools/nearcast.py` exists so that is not found that way twice.**  It
scans the trees that are compiled as programs -- `src/apps`, `src/desk`,
`src/app` -- for a 16-bit cast on a line naming one of those fields.  It
does not scan the engine, which is small-data and owns genuinely near
trees whose casts are correct.  A deliberate cast says so on the line
with `nearcast-ok:` and a reason, so the reason travels with the code
instead of rotting in an allowlist.

`tests/host/test_nearcast.py` **puts the fault back** into a copy of
`calc.c` and requires the tool to report it.  A check that passes by
saying nothing is not a check yet, and this tree has been caught by that
twice before.

One more diagnostic came out of the same afternoon.  `gem_badop` records
which opcode the last refused call was in, set in `aes_entry` by
comparing `gem_bad` before and after `crysbind`.  It earned itself
immediately: `shel_write` was refusing `""` and `"\0"` from
`SHW_SHUTDOWN` -- far string literals in a large-data program -- and
`gem_badop` named opcode 121 rather than leaving it to be searched for.

## Six accessory slots, because that is what TOS has

`NUM_PROCS` went 4 to 7 in `src/aes/proc.h`, with
`#define MAX_ACCS (NUM_PROCS - 1)`.  Six is TOS's number and the Desk
box has exactly eight children -- two desktop items plus six -- which
Atari's own AES enforces by destroying and rebuilding that child chain
(`cnt = 2 + accessories`, bounded by `NUM_ACCS`).  The process store
grew to 364 bytes, which the memory report charges.

Three accessories ship and coexist: `CLOCK.ACC`, `CONTROL.ACC` and
`CALC.ACC`.  The sixth slot registering and the seventh being refused by
`proc_new` is **not yet proven** -- three is what has been run.

The calculator is now two programs from one source.  `calc.c` was split
into `calc_start()`, `calc_ws()` and `calc_panel()` with no `main()`;
`calcapp.c` supplies the program's `main()` in the original call order,
so `test-m22` still measures what it measured, and `calcacc.c` supplies
the accessory's.  `make shots` photographs all three accessories by
name, and `docs/shots/11-calc-acc.png` is the calculator open over a
window on `A:\APPS\*.*` -- which is the point of the shape.

## QED launches from the desktop

Its near region went 11,520 to 6,144 bytes -- `BSS` 8192 to 5632 and
`BITS` 3072 to 256, plus `menu_popup` and `appl_xgetinfo` deleted from
its shim, both of which this AES serves directly.

That it now fits *beside* the desktop rather than replacing it was not a
size decision.  Replacing the desktop makes multitasking permanently
harder to add, and this tree would rather keep shapes a multitasking AES
could keep (`gem4xe-multitasking-request`).  `tools/ci_gem4xe.py` drives
desktop -> DISK A -> `QED.PRG` and requires `sh_runs` to go 1 to 2 --
the desktop is still process one.

## The numbers

Pool free, with the desktop and **three** accessories resident:

    before   3,074 bytes
    after    8,192 bytes  (model, desktop + three accessories)
            11,928 bytes  (measured live by test-m17, desktop alone)

and 6,398 bytes of desktop resource that are no longer in bank `$00` at
all.

## Gates

`m7`-`m33`, `test-boot`, `test-sdx816`, the host suite (242), plus
`tools/memreport.py`, `tools/nearcast.py` and `tools/modelsnap.py` --
whose digest `69e954213736b66d` did not move, which is the point of it.

Four gates failed during the work and every one was the gate being
wrong, not the target: `m18` had its import updated but not its two
`Desktop(...)` constructions; `m28` read `gl_mntree` -- an
`OBJECT FAR *` -- with `peek16`; `test-sdx816` reported six problems
that were one bad read of `a_menu` against `app_near` instead of
`app_far`; and `m16` failed at link because `DESK_BITS` had been serving
two programs with opposite needs, now split into `M16_BITS`.

`tools/a8test/bridge.py` gained `peek24`, which reads a Calypsi far
pointer -- offset first, bank in byte 2 -- and is what three of those
four needed.
