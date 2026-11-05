# A task switcher: XM/GEM's shape, on gem4xe

Status: **steps 1-3 built, and step 4's key** (phases 126, 127, 129); the
Desk menu's list is next.  The order agreed: AES 4's calls first (phases
123-125: `AP_TERM`, AES 4.0, the window messages), then this, then MVN as
a speed-up for it (`docs/multitasking.md`; phase 128).

## What it is

Several programs loaded at once, **one running**: the others are frozen
where they stopped, and the user switches between them -- XM/GEM's design
(1987; its swapper is `ref/gemworld/xmgem/GDOS/SW.C`, GPL-2), not
MultiTOS's.  Nothing runs in the background but the accessories, which
already do.  It is the answer `docs/multitasking.md` reached: the problem
on this machine is room, not scheduling.

## What is already here

| | where | what it gives |
|---|---|---|
| processes | `src/aes/proc.h` | records with queues and waits; process 0 the application, the rest accessories |
| contexts | `src/sys/ctx.c` | a process's extent of the one engine stack parked in far memory and put back at the same addresses -- how three accessories coexist today |
| a dormant program | phase 121, `app_keep` / `app_revive` | the desktop kept while a program runs: its image, and its near region copied to far memory and claimed back at the same address -- a one-slot switcher that RESTARTS what it keeps |
| bank $00 as blocks | memory plan steps 2-4 | pool blocks freed in any order, owned and tagged, purgeable far memory |
| asking a program to end | phase 123 | `AP_TERM`, refusal, `SHUT_COMPLETED` -- the switcher's "close this one" |
| names to list | phase 124 | `menu_register`'s title for an application (`mn_apptitle`), `appl_search` |
| telling a program its window is back | phase 125 | `WM_ONTOP` / `WM_UNTOPPED` |

## The question at the centre

The dormant desktop is restarted.  A switched-away program must
**resume where it stopped** -- and it always stops inside the AES, waiting
in an `evnt_` call, which is the only place a switch can happen (as for an
accessory: `ev_poll`).  Its state then is:

- its **near region** (direct page, stack, data) in the pool, bank $00;
- its **frames on the engine stack**: `sh_ldapp`, `app_exec`, the program
  and the AES's own frames below them;
- its **far memory** -- code, far data, Malloc blocks -- which stays where
  it is, owned and tagged;
- its **windows and menu bar**, its **workstations**, its **open files**
  and its **DTA** (per process already), and the **DOS's current
  directory**, which is the DOS's and global.

The engine stack is the hard part.  Today the application runs nested in
the shell loop's call to `sh_ldapp`, so a second program cannot be started
without unwinding the first.  **The proposal: every application is a
process with a context of its own, as an accessory is** -- started from
the shell loop, parked and resumed by `ctx.c` -- and the shell loop
becomes what starts them, not what they run inside.  Process 0 stays "the
application that is running", as the AES's single-application rules
assume; the others are parked records.

The near region: only one program's fits the pool beside the desktop's
(6,912 bytes for a launched program), so a switched-away program's region
is **copied to far memory and claimed back at the same address** --
`app_keep` / `app_revive`'s method, now for a running program.  At the
measured byte-loop speed a 6 KB region is about 16 ms each way; MVN would
make it 2.5 ms (the third item of the order).

## The steps

Each says how it is tested; a check is believed only once it has failed.

1. **Applications as processes** -- BUILT, phase 126
   ([phase126.md](phase126.md)): the shell and the program take turns in
   process 0's context, the parked one kept in `proc_shell`; 420 bytes of
   engine stack back at the deepest.  The shell starts a program in a
   context of its own; nothing switches yet.  *Gate*: the suite unchanged
   -- every program still runs and returns as now -- and the engine stack's
   depth at the deepest no worse (test-fdos measures it).

   What the code says this takes (read 2026-11-04):
   - **Process 0's context is the shell's today** (`ctx_start0` makes
     `proc_tab[0].p_ctx` the root), which is why the program is nested:
     `sh_main` -> `sh_ldapp` -> `app_exec` -> `app_run`, all context 0.  The
     shell needs a CTX of its own (30 bytes of bank $00: from the pool
     before the keep mark, as the process records are -- LoRAM and the
     window are at their floors) and `ctx_root` becomes it.
   - **Whoever switches to process 0 must reach the shell when no
     application is live**: the accessories loaded at boot park into
     process 0 (`sh_ldacc` "runs until it parks"), and `proc_drain` after a
     program has ended hands turns out from the shell and expects them
     back.  One function that answers "process 0's context" -- the
     application's while it lives, the shell's otherwise -- used by
     `proc_pass` and `proc_drain`.
   - **`ctx_boot` drops `app_run`'s return value**; `sh_lastret` needs it.
     And `app_exec`'s owner and floor become the context's, set before
     the first switch as `sh_ldacc` sets an accessory's.
   - **A gain on the way**: `sh_ldapp`'s frame stops being under the
     program.  Its comment explains why it has one buffer used twice --
     the frame is on the engine stack for as long as the program runs,
     and `GD_PEXEC_STACK` refused every Pexec when it grew 114 bytes.  In
     its own context the program starts at the top of the stack, with the
     shell's frames parked.
2. **Suspend and resume one program** -- BUILT, phase 127
   ([phase127.md](phase127.md)): `shel_write(SWM_G4SUSPEND)` puts it aside;
   started again from the desktop under the same name, it is resumed.
   From inside: a private request
   (a `shel_write` mode in gem4xe's own range) parks the running program
   -- context, near region, windows and menu bar hidden, the DOS's
   directory kept -- and revives the desktop; a second request resumes it.
   *Gate*: a program counting in its near data and drawing in a window,
   suspended and resumed three times: the count goes on, the window comes
   back with a `WM_REDRAW` and `WM_ONTOP`, its files are still open.

   The design, after step 1 (2026-11-04):
   - **The desktop is never suspended.**  It ends, kept dormant, as it
     does today to run a program (phase 121), and is revived.  Only the
     programs it starts are resumed where they stopped: XM's shape, and
     half the work.
   - **Suspending** happens inside the program's own `shel_write`: it
     switches to `ctx_root` without finishing, so `sh_run` gets the
     processor back with process 0's context still `CTX_LIVE`.  The shell
     then keeps, in one far record: the context (its parked stack stays in
     its own park buffer, and process 0 is given a new one), the process
     record, process 0's message queue, every pool block the program owns
     (near region, a near resource, its pool Mallocs -- address, length,
     owner, tag and bytes; then freed, which is what lets the desktop take
     its own region back), its windows and its menu bar, and the DOS's
     current directory.  Its far blocks stay where they are, owned.
   - **Resuming** is the desktop ending with a request to resume, and the
     shell doing the reverse: the pool blocks claimed back at their
     addresses (`pool_claim`, as `app_revive` does) and refilled, the
     windows put back at their own handles -- the shell loop's `wm_init`
     has emptied the table, so they are free -- the menu bar, the queue,
     the record, the directory; then the switch, which unparks the program
     inside its `shel_write`, and a `WM_REDRAW` for every window and
     `WM_ONTOP` for the top one.
   - **One suspended program** in step 2; a list in step 3.
3. **Several at once** -- BUILT, phase 129 ([phase129.md](phase129.md)):
   up to six programs besides the desktop, each put aside in a record, in
   a ring that keeps the order they were started in with the desktop
   after the last.  *Gate* (test-m54): three programs started, switched
   among in an order, each resumed with its state, the ring read out of
   far memory after every switch, and the far heap's blocks the same by
   length and kind once all have quit.
4. **The user's way to switch**: the Desk menu lists the loaded programs
   by their `menu_register` titles, as MultiTOS's does, and a key goes to
   the next -- **the key is BUILT, phase 129**: CONTROL-TAB, and
   SHIFT-CONTROL-TAB back, MultiTOS's Control-Alternate-Tab on a keyboard
   with no Alternate; `shel_write(SWM_G4SWITCH)` for a program.  Still to
   do: the list, and closing one from it with `AP_TERM`.  *Gate*: driven
   with the pointer and the key, and a program that refuses `AP_TERM`
   stays.
5. **When there is no room**: no far memory for a parked region, no
   record, a pool place taken -- refused with an alert that says what was
   short, never a half-switched machine.  *Gate*: each case forced.
6. **MVN for the copies**, behind the stress gate the MVN work needs
   (`mvn-far-copy-crash`), measured against the byte loops.

## Decisions for the project

1. **How many programs** may be loaded: six for now (`SH_PROGS`, phase
   129), as the Desk menu's slots -- one constant, still the project's to
   decide.  Not process records, as this first thought: a program put
   aside is a far record, not a process.
2. **The switch key**: Alt-Tab, the user said (2026-11-05) -- built as
   CONTROL-TAB, since this keyboard has no Alternate key (phase 129).
3. **What the desktop is** while programs are suspended: the shell, always
   reachable, as XM's desktop was; quitting it with programs loaded asks
   each to end first (phase 123's shutdown).
4. **Accessories** keep running throughout, as now.

## What it will not do

Run two programs at once; protect one program's memory from another;
swap to disk.  A program that never reaches an `evnt_` call cannot be
switched away from -- it never gives the AES the chance, on XM/GEM too.
