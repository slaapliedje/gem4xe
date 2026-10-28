# Phase 114 -- a program that runs its stack out of its own memory

Two programs did it in a week, and gem4xe noticed neither.  An
application's stack is in bank $00, in its near region -- the first page
its direct page, the stack in the region above -- and gem4xe's own
variables are below the application pool.  A stack that runs past its
region writes over the direct page and then over the system, and nothing
says so until the system falls over somewhere else.

- **GemARC's first build** (docs/gemarc.md) kept path buffers on a
  1.5 KB stack.  The direct page went first: the compiler's pseudo
  registers are there, so a name pointer read back as 0, and a return
  address read back as $0004A2.
- **QED's File > Last version** ran its 4 KB stack 2.3 KB past its end.
  The compiler had inlined two helpers with 1 KB line buffers into
  `e_icon_edit`, QED's menu dispatcher (2,498 bytes a frame; 376
  without), and Last version runs the dispatcher inside itself.  The VDI's
  device pointer, `vdev`, held QED's return addresses, and the next VDI
  call jumped to $000000.  The QED port builds `edit.c` `--no-inline`
  (qed-gem4xe 4b6fa27); probes in QED found it -- step numbers written to
  page 6 while gem4xe's `vwk_far` was intact, and the address of a local
  in `restore_edit`, $46EC, under QED's stack at $5015.

## The floor

Every context (src/sys/ctx.h) now knows the lowest its program's stack
may go: `floor`, the program's near base plus $40.  The near region
starts with the program's direct page, and the compiler's pseudo
registers are its first $24 bytes in every program built here; the rest
of the page is unused.  The first version put the floor past the whole
page, and stopped the General and Color control panel modules at every
boot (test-m36): General's 384-byte stack runs 39 bytes into the top of
its page, which is untidy and harms nothing.  `app_exec` sets it around a run and puts the old one
back after, because `Pexec` runs a child in its parent's context; an
accessory's is set when its context is made.

The call gate (src/sys/abi.s) records the caller's stack pointer as it
switches to gem4xe's stack, and `gem_entry` (src/sys/abi.c) compares it
with the floor before serving the call.  A stack pointer ON gem4xe's own
stack, at or under `ctx_base`, is not a runaway: a module's start-up
runs on the stack it was called with.  Between the two -- above gem4xe's
stack and under the floor, where QED's $46EC was -- the call is not
served: the program is ended as `Pterm` would end it, with `GEM_STOPPED`
(-9) as its result -- the call that was stopped is a VDI's or an AES's,
with no result word to take one from, so abi.s supplies it.  The shell
says why on the bare desk before whatever runs next (`APP_E_STACK`,
`LANG.RSC`'s APPSTACK, in all five languages), and `gem_stack_stops`
counts; `gem_stop_sp` and `gem_stop_floor` keep the last stop's two
numbers for whoever has to look.

Nothing can stop the writes as they happen; this stops the program at
the first call it makes from down there.  A frame allocated in one
instruction can still reach below the direct page before that call --
QED's would have -- so this is a guard, not a wall: what it changes is
that the machine says what happened, and stops the culprit, instead of
going on until it jumps somewhere.

## The gate

`make test-m47`: src/m47_parent.c, run as the desktop, `Pexec`s
src/m47_child.c, which recurses 200 bytes a level on a 384-byte stack and
calls the AES at every level.  The child must be stopped once, `Pexec`
must give the parent -9, and the parent's twenty calls after it must be
served -- its own floor, not its child's.  The gate finds the parent
through the floor of the context it runs in, and reads its result once
it has written a mark.  With the check taken out the child ran away
and returned 7 to its parent.

## Measuring a program's frames

`cc65816 ... --assembly-source x.s file.c` writes the assembly; a frame is
the `tsc / sec / sbc ##N / tcs` in a function's prologue plus 2 for each
`pei`.  A frame much larger than the function's own locals is a helper's,
inlined.
