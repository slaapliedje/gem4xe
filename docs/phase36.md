# Phase 36 -- the desk accessories

    make test-m27   two contexts taking turns on one engine stack
    make test-m28   an accessory loaded before the desktop, in the Desk
                    menu, running while the desktop owns the mouse

Twenty-eight gates in, gem4xe could run one program at a time.  The
desktop was a program, the calculator was a program, and starting one
ended the other: `sh_ldapp` loaded it, called it, and freed it.  A desk
accessory is the first thing that does not fit that shape, because an
accessory is a second program that is *there* -- loaded before the
desktop, outliving every program the desktop starts, and expected to keep
counting seconds while somebody else has the mouse.

GEM's answer is a process: its own stack, its own message queue, its own
pid, blocked inside `evnt_multi` while a round-robin dispatcher runs
somebody else (EmuTOS `aes/gemdisp.c`, `aes/gemasync.c`).  There is no
cheaper answer that still works -- an accessory's `AC_OPEN` handler calls
`form_do`, and `form_do` blocks, so a callback on the desktop's own event
loop would deadlock on its first dialog.

So the question for this phase was never *what* to build.  It was where to
put the stacks.

## The measurement that chose the design

The engine's stack is 2 KB at `$2E38-$3637` and the gates have been
printing its low-water mark for twenty phases: **1,239 of 2,048 bytes
used**.  LoRAM -- the whole of bank $00 that holds the engine's stack and
every one of its globals -- is 5,504 bytes, and it had 47 free.

There is no room in bank $00 for a second engine stack, and nowhere else
to put one.  An application's *own* stack lives in the pool at `$4800`
and that is safe because of an invariant the memory map has relied on
without ever having had to write it down:

> Whenever a DOS may have banked its own RAM over `$4000-$7FFF`, S is in
> `$2000-$3FFF`, because the call gate moved it there on the way in.

An engine stack in the pool would break that the first time an accessory
asked GEMDOS for anything -- SpartaDOS X with `USE BANKED` would switch
its system bank in over the accessory's stack while servicing the call.

**So the contexts share the one stack and take turns on it.**  A context
that is not running has its extent of that stack parked in far memory;
resuming it copies the extent back *to the same addresses*, which is what
makes every pointer into a frame still the address it was.  The cost is
the depth at the moment of the switch, not the 2 KB -- and a switch
happens at one place only, `ev_poll()`, where the engine is a handful of
frames deep.  `test-m27` prints what it measured: **90 bytes** at the
deepest park of a six-frame recursion, 35 for the root.

`src/sys/ctx.h` carries the argument; `src/sys/ctx.c` is all the
bookkeeping, so no offset into `CTX` is ever written down twice; and
`src/sys/ctx.s` is the three things C cannot say -- read S, write S, and
return through a stack that arrived after the routine started.

## What a turn costs, and when one happens

`ev_poll()` is the single spin every wait loop in `event.c` runs on, so it
is the one place in gem4xe where a context switch can happen.  A process
about to spin records what it is waiting for; `ev_poll` hands the
processor to any *other* process whose wait is already satisfied, and to
nobody while the control manager is inside a gesture -- a menu pulled
down, a gadget held, a button still down -- which is GEM's own rule about
the mouse and also a practical one, since `ct_run` is a call nested in
the application's wait and its state is the AES's, not the process's.

**THE INPUT OWNER IS ALWAYS READY TO RUN**, and that rule is not an
optimisation -- without it the round robin deadlocks in a way that only
shows up when traced.  An accessory finishes its dialog and parks on
`MU_MESAG`; the desktop is parked on the button; neither has a message or
a deadline, so neither is ever chosen again and the accessory spins for
ever in its own poll.  The process that can see the mouse must always get
the chance to look.

Nothing pre-empts and nothing is timed, exactly as in the donor: a
program that computes for a minute freezes the accessories for a minute
too.  In `test-m28` a clock-shaped accessory with a 500 ms timer costs
**two switches a second** and the gate counts 47 turns over its run.

## The contract, which is small and exact

  * **Loading.**  Every `*.ACC` in the system's own directory, at AES
    start-up, *before the first program*.  Both halves are load-bearing.
    Before, because both allocators are bump allocators that `app_free`
    winds back to where `app_load` found them -- an accessory taken
    before the desktop is below the desktop's mark, so every return to
    the desktop leaves it standing; one taken after would be freed
    underneath itself the first time a program exited.  The same rule
    reaches into the accessory: everything it will ever want from bank
    $00, its resource included, it must take while it is starting up.
    Never freed, so the `APP` record is not kept -- what the AES keeps is
    a process and a context.

  * **`menu_register`** keeps the caller's POINTER, never a copy, and it
    goes straight into an object's `ob_spec`.  The donor says so in a
    comment -- "save pointer, like Atari TOS" -- and it means an
    accessory's title must live as long as the accessory.  The id
    returned is the SLOT, found by looking for a free one rather than by
    counting registrations, so six ids stay six ids however they were
    handed out.

  * **`menu_fixup`** destroys the Desk box's child chain and rebuilds it
    BY INDEX over the resource's own `dabox+1 .. dabox+8`: the
    application's item, then -- if any name is registered -- a separator
    and one item per name.  Height is recomputed, **width is not**; a
    title too long for the box the resource drew is clipped, and the
    resource is where its width was decided.  `tools/deskrsc.py` has
    carried the eight children since phase 14 for exactly this, and the
    invariant is the donor's: one child short and the sixth accessory's
    `ob_add` walks into the File drop-down.

  * **Dispatch** is four lines in `hctl_rect`: an item at or below
    `gl_dafirst` in the Desk drop-down is an accessory's and gets
    `AC_OPEN`; everything else is the application's `MN_SELECTED`.

  * **The words are asymmetric and two Compendium pages get them wrong.**
    `AC_OPEN` carries the *Desk title's object index* in `msg[3]` -- 3 in
    every tree the RCS builds -- and the menu id in `msg[4]`.  `AC_CLOSE`
    carries the menu id in `msg[3]`.  Both sources agree with each other;
    p.326's skeleton and p.382's description do not.

  * **`AC_CLOSE`** goes to every registered accessory when the program it
    is sitting under terminates, open or not, because the message does
    not mean "the user closed you" -- it means that program's memory is
    about to be reclaimed.  It goes out before `app_free` and before the
    shell loop's `wm_init` destroys the windows, and then `proc_drain()`
    gives the accessory the TURNS to read it in: the donor's
    `wait_for_accs`, with a bound for the same reason, since an accessory
    that has stopped reading must not hang the machine.  The accessory
    must not close its own windows -- the AES does that, destructively,
    and a handle kept across an `AC_CLOSE` is a handle to a window that
    no longer exists.

## The departures, named

  * **The AES's own messages say sender 0.**  In the donor the control
    manager is a process, `SCRENMGR`, and its pid goes in word 1 of every
    `MN_SELECTED` and `AC_OPEN`; here it is a call nested in the
    application's wait (`docs/phase8.md`), so there is no process to name.
    `appl_write` is the one place a real sender exists and fills it in.

  * **No `perform_untop` before `AC_OPEN`.**  That is an EmuTOS addition,
    not in the ROM AES, and it needs window ownership, which is not here
    yet.

  * **Input ownership is a foreground flag, not the donor's rule.**  There,
    ownership is recomputed from the window under the pointer on every
    button-down.  Here an accessory asked to open becomes the input
    owner, and a wait with none of the input events in it is an accessory
    with nothing on the screen, which is where the application gets the
    mouse back.  That is the half an accessory without a window needs;
    the rest waits on windows having owners.

  * **Falcon's DA-suspend path is not reimplemented, deliberately.**  The
    corpus sets `PS_TRYSUSPEND` when a queued message is `AC_CLOSED` --
    an identifier defined nowhere in the corpus, one grep, one line.  The
    ROM's "suspend the accessory on close" arm does not do what its
    comment claims.  EmuTOS's `AP_ACCLOSE` barrier is the tested model
    and is what `proc_drain` is.

## Six bugs, and every one of them came from a gate

**`ctx_base` was taken one frame too deep.**  `ctx_init` recorded the mark
inside itself, below its own caller, so every later park computed
`base - sp` backwards through zero.  `test-m27`'s first run said it in one
line -- *1 park(s) refused for want of room* -- because the guard that
counts refusals was written before the first run rather than after the
first mystery.  The mark is the caller's S now, and it has to be taken in
assembly for that reason.

**The compiler's register file is per context.**  `registers` in the
direct page -- Calypsi's `_Dp` -- is at a fixed address shared by
everybody, and a context parked in the middle of a function has ITS
values in it.  That is precisely the `d0-a6` a 68000 AES process keeps in
its `UDA`, and missing it is the same mistake as forgetting to save
registers in a context switch.  It travels by being *pushed onto the
outgoing stack* before the park, so it rides inside the copied image and
no `CTX` field and no struct offset has to be written down twice.  It has
to be assembly: a C function restores the register file from its own frame
on the way out and would undo the restore as its last act.

**The root context had nowhere to be parked.**  `ctx_start0` left
`save = 0`, so every park of context 0 wrote its stack extent to far
address 0 -- bank $00's zero page.  `test-m27` passed over the top of
that for three runs, because a runner that spins in a loop afterwards
never asks the OS for anything again.  The shell does, and did not
survive it.  Context 0 is a context like any other now, and `ctx_park`
refuses a park with nowhere to put it rather than writing to address 0.

**Nested waits erased the outer wait's condition.**  The control manager
runs as a call inside the application's wait and the menu and the gadgets
wait *again* in there, on the same process; those nested waits set
`p_evwait` and zeroed it on the way out, leaving the outer wait invisible
to the scheduler.  The symptom was exact and unreadable until measured:
an accessory stopped being given turns the moment the Desk menu had been
pulled down once, and `gem_calls` froze at the desktop's first wait.  It
is the same save-and-restore `ct_run` already does around the one
button-wait slot, for the same reason.

**`mn_init` was doing two jobs.**  The donor calls it once, from
`geminit`, so its registry can live inside it; gem4xe calls it again from
the shell loop between every two programs, because the window and menu
state of the program that has just gone has to go with it.  An
accessory's name must not, because the accessory is still there.  The
registry moved into `mn_start()`, the half that happens once.  `test-m9`
said so before the reasoning did: four cases against one live AES, and
the target kept case 0's registration into case 1 while the model, built
fresh per case, did not.

**CIO answers 1 for success, not 0.**  The accessory scan read the
directory and found nothing, because the loop treated a non-zero status
as failure.  The file selector's own test is `st != CIO_OK && st !=
CIO_OK_EOF` and getting it backwards is a directory that reads as empty.

## And one that was the compiler, for once

Bank $00 ran out in the middle of the phase -- `data`, twenty-five bytes,
would not place -- which forced a tidy-up the donor had already pointed
at: three separate eight-word message scratch buffers in three files
where GEM has one `appl_msg`.  `ap_sendmsg` owns the one buffer now; it is
filled and copied into the destination's queue before the call returns,
so it was never state.  That is 32 bytes back.

It was not enough, so the rectangle pool went to far memory -- and later
the resource's icon bitmaps did too, which is 1,536 bytes of the pool
rather than of LoRAM and took the same trap twice more (below).  `gl_olist`
is eighty ten-byte nodes reached only through `o_link`, from nineteen
places, all in one file -- the only one of the window manager's four
tables that could leave, since `W_TREE` and `W_ACTIVE` are OBJECT trees
that `objc_draw` walks through a near pointer and `gl_win` is an array the
whole library indexes.  LoRAM went from 23 bytes free to **783**, and the
engine's stack low-water moved 1,239 to 1,391, because far pointers make
frames bigger.

**All twelve window cases then failed at once**, on

    r_set(&rl->o_gr, x, y, w, h);

where `rl` is far and `r_set` takes a `GRECT *`.  cc65816 5.18 truncates
the 24-bit address to sixteen bits and writes the rectangle into bank
$00 at the node's offset-within-bank -- **silently, with no diagnostic at
any warning level**.  Value reads and struct assignments across the seam
are fine; it is only an address in a parameter that is lost.

That is the fourth "far address in a near slot" bug in this project --
phase 2's MFDB `fd_addr`, phase 6's `farmem_probe` handing out the bank
its own code was in, phase 24's `far_alloc` straddling a bank, and this --
so the lesson is procedural and worth more than the fix: **moving a
structure to far memory is not done when it compiles.  Grep for `&`
applied to its fields first.**

And then it happened twice more in the same phase, moving the resource's
icons.  `vdi.c` cut the form address to sixteen bits on the way into the
device seam -- right only while every memory form was in bank $00 -- and
`dev_vbxe.c`'s row expander kept its source pointer in the direct page as
a NEAR pointer, so assigning the far one truncated it.  Every address on
the way in was correct and the icons drew as noise.

What found it was not reasoning, which had checked the file, the fixup
arithmetic and the model and found all three right.  It was a probe: the
far copy compared with the file at seven offsets, byte for byte.  That
said the bytes were there and the addresses were right, which left only
the reading -- and the reading is where both casts were.

**The general defence is a gate that exercises the far path**, and there
is one now: the desktop's icons come from far memory on every run of
`test-m17`, `test-m19` and `test-boot`.  The reason the trap could be
sprung twice is that nothing had ever drawn a 1bpp form from outside bank
$00 before.

Smaller, same file: casting an integer VARIABLE to a far pointer crashes
the compiler outright -- *internal error:
Translator/Compiler/IL/Evaluate.hs:370: Irrefutable pattern failed* --
where casting a near pointer to a far one is fine and emits `ldx ##0` for
the bank.  It was the first thing tried.

## What an accessory costs

    M28.ACC       2,350 bytes on disk
                  1,280 near (direct page, bss, a 384-byte stack)
                    902 far
    its queue       128 bytes of the pool, eight messages
    its context   2,048 bytes of far memory for the parked extent
    the table       208 bytes of the pool, four process records

*(no longer true since Phase 47 -- `docs/phase47.md`: the table is 364
bytes and seven process records, six of them accessory slots.)*

The binding constraint is not the Desk menu's six slots.  It is the
**application pool**: 14,336 bytes of bank $00, of which the desktop's
near region is 3,712 and `DESKTOP.RSC` is 6,226, leaving 4,190.  *(no
longer true since Phase 47 -- `docs/phase47.md`: the desktop's near
region is 1,280, and its resource loads far and is charged 0 against the
pool.)*  An accessory trimmed to what it measurably uses is about 1,900
of that including its resource, so the slots stay at six and the loader
stops when the pool says no -- which is also what the donor does when its
one allocation for all the accessories fails.

## Knowing where bank $00 has gone

Three times in this phase a change ran into bank $00 rather than being
told it would: `data`, twenty-five bytes, would not place; the pool was
left with 1,838 bytes and nothing said so; and the question "does a
second accessory fit" could only be answered by building one.

    make memcheck

answers it now.  `tools/memreport.py` reads the linker's map for the
regions, each `.g4a`'s header for what a program reserves and each
`.RSC`'s for what a resource costs the pool once its icons are far, and
then **simulates `pool_alloc` in the order the machine runs it** --
process records, each accessory's queue, near region and resource, then
the desktop and its resource, with a program's region page-aligned as
`app.c` aligns it.  Simulating rather than summing is the point: the
report prints `$5200` for the desktop's near region, which is the address
`test-boot` reads off the live machine, and 3,246 bytes free, which is
the number the machine reports too.  *(no longer true since Phase 47 --
`docs/phase47.md`: the report prints `$5B00` and 8,192 bytes free, with
all three accessories resident.)*  `tests/host/test_memory.py` runs it,
so `make test` says so without being asked, and `test-boot` asserts the
LIVE figure against the same floor -- GEMDOS reads files and directories
through a slice of whatever the pool has spare, so falling under 2 KB is
the difference between a desktop that lists a directory briskly and one
that does not, and nothing else would fail if it went.

## What is not done

  * **Windows have no owners**, so `WM_*` messages all go to the
    application and an accessory cannot keep a window open across a
    program change.  That is the next milestone and it is what turns the
    foreground flag above into the donor's real ownership rule.
  * **Virtual workstations and GEMDOS handles are still global**:
    `vdi_close_virtuals` and `gemdos_release` wipe everything on
    `app_free`, not just the exiting program's.
  * **A second accessory does not fit yet.**  With `CLOCK.ACC` resident
    the pool has 3,246 bytes, and the calculator wants about 2,400 of
    them -- which would leave GEMDOS under the 2 KB its read slice wants.
    The next 1,536 bytes are probably the desktop's own: it reserves
    3,840 and the map says it uses 3,235.  *(no longer true since Phase
    47 -- `docs/phase47.md`: three accessories are resident together, and
    the calculator is one of them.)*
  * **An accessory may not call `menu_bar`.**  The donor does not stop it
    either, and the Compendium's "desk accessories should not use a menu
    bar" is not style advice: `gl_mntree` is one global, so an accessory
    that installs a bar destroys the application's with no way back.
