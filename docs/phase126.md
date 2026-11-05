# Phase 126 -- a program runs in a context of its own

Step 1 of [switcher-plan.md](switcher-plan.md).  Nothing switches yet:
every program still runs and returns as before.  What changed is where.

## Before

The shell ran a program by calling it.  `sh_main` -> `sh_ldapp` ->
`app_exec` -> `app_run`, and the program's calls into the AES were served
below all of those frames on the one engine stack, for as long as it ran.
A second program could not be started without unwinding the first, which
is the one thing a switcher has to do.

## Now

`sh_ldapp` calls `sh_run` (`src/aes/shel.c`), which runs the program in a
context of its own, as an accessory has always run (`src/sys/ctx.c`).

The obstacle was `rlr`.  It is `ctx_cur` (`src/aes/proc.h`): the context
running IS the process running, so the shell -- which calls the AES too,
drawing the desk and draining the accessories -- has to be process 0
whenever it runs, and so does the program.  They take turns in process 0's
context.  While a program runs, the shell's bookkeeping is kept in
`proc_shell`, a spare CTX after the process records, and is `ctx_root`,
where a finished context returns:

1. the shell's CTX is copied to `proc_shell`, which becomes `ctx_cur` and
   `ctx_root`;
2. process 0's CTX is made new (`ctx_reset`, split from `ctx_make`) in the
   park buffer `proc_shell` was keeping, with the program's owner and stack
   floor -- what `app_exec` set around `app_run`, which the switch now
   applies;
3. the switch parks the shell's frames and starts the program at the top
   of the stack (`ctx_boot`);
4. when it returns, `ctx_boot` leaves `main()`'s value in the finished
   context's `entry` and switches to `ctx_root`; the shell is copied back
   and the buffers are swapped back.

AUTO programs, the control-panel modules and a Pexec's child still use
`app_exec`: they run in whatever context runs them.

## The cost and the gain

- 30 bytes of pool for `proc_shell`, inside the process records' pages
  (`proc_store_size`, so `tools/memreport.py` sees it), and a second
  2 KB park buffer in far memory at boot.  A launched program still gets
  6,912 bytes.
- One more park and unpark per program: the shell's few frames.
- **420 bytes of engine stack**, at the deepest: test-m16 measured 1,671
  of 2,080 before and 1,251 after.  A program's calls are no longer served
  under the shell's frames.  `sh_ldapp`'s one-buffer-used-twice, and
  `GD_PEXEC_STACK`'s refusals when that frame grew, were the price of the
  nesting.

## Gates

The suite, unchanged: every program still starts, runs and returns, and
the accessories still hand turns to it and back (test-m50) and are
drained after it (`proc_drain` runs in the shell, which is process 0
again by then).

## Also: only `Malloc(-1)` asks how much is free

Found tracing RetroWP's startup hang for its session (2026-11-05).
`gd_malloc` took **any** negative size as the question "how much is
free" and answered the largest block less its header -- 65,532 with a
bank free.  RetroWP's allocator, handed a garbage size of more than 2 GB
by a caller of its own, took that answer for the address of a new arena:
bank $00, offset $FFFC.  The arena's end landed at `$00:D32C`, the PIA's
mirrors, and its zero went into PORTB, which turned an extended bank into
`$4000-$7FFF` under the program's stack and direct page.  Every word saved
before that read back as the extended bank's bytes -- a different
garbage every run -- and the next `RTL` ran into bank $65.

TOS asks only `amount == -1L` (EmuTOS `bdos/umem.c`); any other negative
size is a size, too big to give, and the answer is 0 -- which RetroWP
would have heard as "no memory".  gem4xe answers that way now.
`test-m15` (and every variant that runs `m15_gdos.py`) asks
`Malloc(-2)`, `Malloc(-0x7F00DE)` and `Malloc(-0x80000000)` for 0; with the
old rule all three answer `$FFFC` and fail.
