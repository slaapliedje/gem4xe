# Phase 122 -- a program asks for its stack

Step 6 of [memory-plan.md](memory-plan.md), and the last of the plan but
the one held back for need (handles, step 7).  A IIGS program declares the
size of its direct page and stack in a segment of its own (kind $12), and
the loader gives it that.  A gem4xe program declared its stack only to the
linker (`--stack-size`), and got exactly that, wherever the layout put it.

## Why the plan's version could not be built

The plan said "a field in the .G4A header ... instead of a fixed share of
its near region".  But the kit's near region was laid out **direct page,
stack, data**: the stack at the foot of `AppBss`, growing down into the
direct page.  Room can only be added to a stack below it, and below this
one is the direct page -- so no loader could give a program more stack
than it was linked with, whatever a header said.

## The stack last

So a program that asks for its stack is linked differently: **direct page,
data, stack**, the stack in a memory of its own, `AppStack`, at the top of
the near region (`src/app/gemapp.scm`, `app-layout-ns` and `app-layout-vs`).
Its stack now grows down into its own data, and room added above it is
more stack.  It is opt-in: every program built before, and every one built
without asking, links byte for byte as it did -- all forty-one in this tree
were compared.

| | where | what |
|---|---|---|
| the build | the Makefile's `g4a`, an eleventh argument; the SDK's `STACK_ASK` | the stack-last layout, and `--stack STACK:ASKED` to mkg4a |
| `tools/mkg4a.py --stack L:A` | the format 5 header's spare bytes, 28 and 30 | the stack it was linked with and the stack it asks for -- after checking that the start-up begins `tsc tay ldx ##top` with `top` the near region's last byte, which is what says the stack really is last |
| the loader, `app_load_v5` | | asked for more: the near region grows by the difference, in pages, and the start-up's stack top moves up by as much; and the floor (phase 114) is the bottom of the stack asked for, never below the stack it actually has |

Format 5 never read bytes 28-31, so an older gem4xe loads such a program
with the stack it was linked with, and a newer one loads every older
program with the old rule -- the floor `CTX_FLOOR` into its near region.

**The floor is the bigger change.**  With the stack last, a stack that runs
out of its room runs into the program's own data, not into its direct page
-- so the old floor, $40 into the near region, would only catch it after
every byte of its data had gone.  A program that asks is stopped the moment
its stack goes below what it asked for.  So asking for *less* than it was
linked with is not meaningless: it is a promise the machine holds the
program to.

## Gates

`test-m47`, with two more children: `src/m47_child.c` again, built with
`M47_LEVELS` and the stack last.

- **BIG.PRG**, linked with 384 bytes and asking for 4096, recurses twelve
  levels (about 2.8 KB) and checks that its own data is as the crt laid it
  down: it returns 7.  With the loader's extra room switched off it is
  stopped by its floor, -9; without the floor guard it returned 7 having
  written through its own data, and its parent's next `Pexec` failed.
- **SMALL.PRG**, linked with 1024 and asking for 256, recurses three levels
  (about 700 bytes, which 1024 would have held): it is stopped, -9.
- `test_sdk`: the kit with `STACK_ASK` unset still rebuilds the gate
  application byte for byte.
- The whole of `make test`.
