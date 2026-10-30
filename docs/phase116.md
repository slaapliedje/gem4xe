# Phase 116 -- the bank probe out of the allocator

Step 1 of [memory-plan.md](memory-plan.md): `src/sys/farmem.c` held two
things that have nothing to do with each other, and now holds one.

| | before | after |
|---|---|---|
| finding the banks: the write-and-read-back probe, the Rapidus OS's kernel allocator (`kmgetblk`, `kmalloc`, `kfree`), LOSEGM/HISEGM, `HIGHRAM=` | `farmem.c`, about 250 lines | `src/sys/hiprobe.c` and `hiprobe.h` |
| `FARMEM`, the far-memory helpers, the block allocator | `farmem.c` | `farmem.c`, which no longer knows the machine |

The probe clears the heap through a new `far_heap_clear()` rather than
writing the allocator's variables itself, and fills `FARMEM` and calls
`far_heap_init()` as before.  Every program image that linked `farmem.o`
links `hiprobe.o` beside it.  Nothing changes behaviour.

`tests/host/farmem_sim.c` compiled the probe along with the allocator
only because they were one file, and stubbed the loader's `_fl_top` and
the six kmalloc entries to do it; it compiles the allocator alone now and
the stubs are gone.

## Comments put right

Four comments still described the far heap as a bump allocator, which it
stopped being in phase 79: `src/sys/app.h`, `src/aes/shel.c` (twice) and
`src/aes/rsrc.c`.  Two of them are only half wrong -- bank $00's
application pool still IS a bump allocator, which is why accessories and
Control Panel modules load before the first program -- and they say that
now, and that step 2 of the plan changes it.  `farmem.c` and `farmem.h`
said `far_alloc_banks` takes from the top of the heap; it takes the lowest
free run, for the reason at the function (the top of a Rapidus's heap is
cached SDRAM).

## Gates

`test_farmem` (the allocator against `tools/farref.py`), `test_memory`
(bank $00's budgets) and the whole of `make test`, unchanged -- which is
what a move with no change of behaviour has to show.
