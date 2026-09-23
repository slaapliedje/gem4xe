# Multitasking: XM/GEM, FreeMiNT, or neither

A question that keeps coming up, written down so it can be asked properly
rather than answered by whoever is enthusiastic that week.

**Short version: the question as usually posed has the wrong shape.**
gem4xe already multitasks.  What it cannot do is hold two APPLICATIONS
in memory at once, and that is an allocator problem, not a scheduler
problem.  Both candidate answers should be judged on what they do about
14,336 bytes.

---

## 1. What is already here, measured

`src/aes/proc.h` and `src/sys/ctx.h`, both built and gated:

| | |
|---|---|
| processes | `NUM_PROCS 7` -- the desktop and six accessory slots, TOS's number |
| each has | a message queue, event blocks saying what it waits for, a context |
| the switch | `ev_poll()`, and nowhere else |
| the rule | cooperative.  Nothing pre-empts, nothing is timed |
| the stack | ONE engine stack, 2 KB, shared by turns -- there is no room in bank `$00` for a second |
| parking | a context's extent of that stack is copied to far memory and back **to the same addresses**, so every pointer into a frame stays valid |

That last row matters more than it looks.  **gem4xe already swaps state
out to the 15 MB and back** -- it is how three accessories coexist today
(`test-m22`, `test-m23`, `test-m28`).  The mechanism a switcher needs is
not missing.  It is in the tree, gated, and running on real hardware.

What is missing is that only one of those processes may be an
application.  The desktop launches a program, the program runs, the
program exits, the desktop comes back (`test-m18`).

## 2. Why: the fourteen kilobytes

The 65816 confines the direct page, the stack and the interrupt vectors
to bank zero.  After the OS, DOS, the MEMAC window, SpartaDOS X's screen
and the OS ROM, what is left for applications is `$4800-$7FFF`:

    application pool                       14,336 bytes
    ...with the desktop and three accessories resident, free    8,192
    engine stack, used at the low-water mark        1,660 of 2,048 (test-m17)
    LoRAM free                                                      295
    Near free                                                       143
    Window free                                                      12

A second *application* resident means a second near region, a second
direct page, a second application stack -- in that 14 KB, beside the
desktop and the accessories that are already there.  Two medium
applications do not fit.  This is the constraint every phase of this
project has paid something to, and it is the one a multitasking design
has to answer first.

Everything else is plentiful: 14.9 MB of fast linear RAM, of which the
far heap uses a fraction.

## 3. XM/GEM

**What it is.** Digital Research's own multitasking GEM, 1987 -- "GEM XM
Desktop", advertised as *"load up to ten applications simultaneously,
switch between them at any time in any order"*.  Sources at
`retroarchive.org` (GEM World): **66 C files**, complete GEMVDI, GEM and
DESKTOP, **GPLv2** in the Caldera release.  Unpacked to `ref/gemworld/`
here, which is gitignored.

**What it actually does.**  Not a scheduler.  Reading the sources beside
the single-tasking GEM/3 tree:

- Both AESes already contain `savestat()` and `switchto()`, and both
  have a process descriptor.  **GEM's AES was built to multitask from
  the start** -- that is what a desk accessory is, and it is the same
  design gem4xe implements.
- The new work is `GDOS/SW.C`, **773 lines of C**: swapping whole DOS
  applications out to expanded memory so several can be loaded at once.
- The AES files differ by 20-150 lines each (dispatcher, control
  manager, `appl_*`).  That number is an **upper bound and not a
  measurement of multitasking**: the two trees' version headers
  disagree with each other (one says 3.0/1986, the other 2.3/1987), so
  ordinary version drift is mixed into it.

**Why it maps onto this machine almost exactly.**  XM/GEM's problem was
that the PC's 640 KB could not hold several applications while expanded
memory could hold anything.  gem4xe's problem is that bank `$00`'s 14 KB
cannot hold several applications while 14.9 MB of linear RAM can hold
anything.  Same shape, and the swap is *cheaper here*: bank `$00` is on
the accelerator's SRAM (`docs/phase7.md`), so parking a 14 KB near
region is a fast-RAM copy rather than a disk write to a ramdisk.

**What it does not give.**  Concurrency.  One application runs; the
others are frozen, not slow.  A download does not continue in the
background because there is no background.

### What the swap costs, measured 2026-09-22

The whole tier turns on one number, so it was measured rather than
argued (`docs/bench.md`, `make bench "block move"`):

| moving 256 bytes | | |
|---|---|---|
| a C loop through a far pointer (`src/sys/farmem.c`) | 0.679 ms | 368 KB/s |
| **MVN, the CPU's own block move** (`src/sys/blkmove.s`) | **0.105 ms** | **2,386 KB/s** |

**6.3x**, and 7.4 cycles a byte at the 65816's clock against the
datasheet's 7 -- which is how you tell you measured the instruction and
not the harness.  Every bank pair is the same to three digits, `$00` to
`$00` and bank `$04` to bank `$EF` alike, so the 14.9 MB is uniformly
fast and parking something at the top of it costs nothing extra.

What that buys:

    a 6 KB near region parked                     2.5 ms
    a switch -- park one, restore another         5.0 ms
    ...as a share of a 50 ms slice                 10%
    ...of a 100 ms slice                            5%

    the same switch through the C loop            32 ms
    ...as a share of a 50 ms slice                 63%

So the swap tier is affordable, and it was not before.  **Nothing in the
tree used MVN until this was written** -- `far_get`, `far_put` and
`far_copy` are byte loops, which is what C offers.  Those are now worth
revisiting on their own account, quite apart from multitasking.

Two things the measurement turned up, both worth keeping:

- **`MVN src,dst` assembles to `$54, DST, SRC`** -- the operand order is
  backwards from the syntax, and a swapped pair moves real bytes to a
  real place with nothing to say so.  The bench runs a correctness pass
  (out to far memory and back, compared) before it will print a rate.
- **The banks are in the instruction, not in a register**, so a routine
  that moves between banks chosen at run time writes its own MVN into
  four bytes of RAM and calls it.  That is what `blkmove.s` does; whether
  the Rapidus's 4 KB cache has anything to say about code patched that
  often is **not yet known** and should be asked before this is used at
  a timer tick rather than in a benchmark.

## 4. FreeMiNT

**What it is.**  A preemptive multitasking kernel for TOS with Unix-like
processes, signals, pipes and a virtual filesystem, plus **XaAES**, a
multitasking AES that replaces the ROM's.

**What it would cost here, honestly.**

- **Preemption fights the shared stack.**  gem4xe switches at `ev_poll()`
  and nowhere else, and the copy costs *the depth at that moment* -- a
  handful of frames.  Pre-empting at an arbitrary instruction means
  copying whatever depth the victim happened to be at, every tick.  The
  alternative is a stack per process, and `src/sys/ctx.h` records why
  there is no room in bank `$00` for a second one.
- **No MMU.**  There is no memory protection to be had on this machine,
  so one of MiNT's real arguments does not apply.
- **The AES contract changes.**  XaAES is a different AES, not an
  addition to one.  Everything gem4xe has gated -- 79 opcodes against a
  host model -- is written against the single-client AES.
- **It is a much larger thing to carry.**  gem4xe's whole system is
  145 KB of files.

**What it would give.**  Real concurrency, a process model people
already know, and a path to software written for FreeMiNT.

## 5. The middle answer nobody has named yet

Worth putting on the table because it may dominate both: **do nothing to
the scheduler, and make the ALLOCATOR able to hold two near regions.**

The reason only one application fits is partly the 14 KB and partly that
both allocators are bump allocators with a single keep mark
(`docs/phase48.md`).  A second resident application does not need
preemption, a kernel, or a new AES -- it needs somewhere to put a near
region and a way to give it back out of order.  That is a contained
piece of work in `src/sys/` and it is the prerequisite for *either*
candidate above.

XM/GEM is then a small addition on top; FreeMiNT is still a rewrite.

## 6. The questions actually worth asking others

1. **Would you rather have ten applications loaded and frozen, or two
   applications genuinely running?**  On this hardware those are
   different projects, not different settings.
2. **Is FreeMiNT compatibility a goal in itself** -- i.e. do you want to
   run software written for FreeMiNT -- or is "multitasking" the goal
   and FreeMiNT just the familiar name for it?
3. **What do you actually want to do with it?**  A clock that keeps
   ticking and a terminal that keeps receiving are served by a timer and
   an accessory, both of which exist.  Two word processors open at once
   is a different requirement.
4. **Who would maintain it?**  XM/GEM is 66 C files of 1987 8086-era C
   that nobody has compiled in thirty years.  FreeMiNT is alive but is a
   68000 kernel.

## 7. Licence footing

XM/GEM and the GEM/3 sources both ship **GPLv2 verbatim** (Caldera's
1999 release).  gem4xe is GPLv2, so this code may be **used**, not only
read -- which is the opposite of `~/Documents/Atari/gem-source-corpus/`,
Atari Corp's "All Rights Reserved" tree, which is specification only and
must never be transcribed into this project.

One exception found in the same archive: `GEMSPEC.TXT`, DRI's internal
GEMDOS 1.0 specification of May 1985, is a **document** stamped "DRI
CONFIDENTIAL; INTERNAL USE ONLY" rather than source, so the GPL release
does not obviously cover it.  Treat it the way the Atari corpus is
treated: read it, cite it, transcribe nothing.

(It has already earned itself.  §9.28 defines `p_termres(nbytes, rc)`
and then warns: *"Use of this function may make an application difficult
to port to a future operating systems."*  gem4xe keeps the whole region
or none of it, and DRI flagging their own byte count as portability-
hostile is as good a corroboration as that decision is going to get.)
