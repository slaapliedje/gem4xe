# Phase 14 — GEMDOS, and the road to the Desktop

Status: **in progress, in Altirra.**  Milestone 1, the GEMDOS layer:
`make test-m15` PASS on SpartaDOS 3.2g -- 0 problems across the
directory walk, the file calls, memory, the write path, attributes,
Dcreate/Ddelete and Dfree, every answer compared with the image on the
host; DOS 2 and SpartaDOS X are recorded below as they are measured.
Milestone 3, the shell loop: `make test-m16` PASS, and GEM.COM itself
boots, runs the desktop, runs a program from it, and returns to the DOS
prompt on both product disks.  Milestones 4 and 5, the desktop and its
folder windows: `make test-m17` PASS (the sections at the end).
Nothing here has run on a Rapidus, a VBXE or a real SpartaDOS machine.

The GEM Desktop is a GEM application: it draws through the VDI, runs
under the AES, and asks **GEMDOS** for everything else -- which files
are in a folder, their sizes and dates, a file's bytes, a folder made,
a program's memory.  gem4xe had the first two managers and no third.
This phase builds it, as the ST's trap #1 on CIO, so that the donor's
desktop code can read unchanged above it.

## The third face of the ABI (`src/sys/gemdos.h`, `src/sys/gemdos.c`)

    COP #$73   VDI     X:C = a VDIPB
    COP #$C8   AES     X:C = an AESPB
    COP #$01   GEMDOS  X:C = a call block:  +0 LONG result  +4 WORD fn  +6.. args

The block is the ST's trap #1 stack frame with the result put in front
of it: the function number, then the arguments in the ST's order and
sizes.  An ST binding's stack picture is the block's picture four bytes
along, which is why the layout is that and not something tidier.  The
handler (`src/sys/abi.s`) treats it exactly as the other two: the block's
address noted, gem4xe's stack and direct page, `gem_entry()` dispatches
on the signature byte.  On the application's side `src/app/gemabi.s`
gained `dos_call` and `src/app/gemlib.c` the ST's osbind names --
`Fsfirst`, `Fopen`, `Fread`, `Dsetpath`, `Malloc` and the rest --
pointers far, so a buffer Malloc gave out can be read into directly.

**What it answers.**  Handles, paths, the DTA, the attribute bits and
the error numbers are the ST's.  A drive is a `D:` unit (`A` = `D1:`);
a path is `A:\DIR\NAME.EXT` or relative to the per-drive current
directory GEMDOS keeps, composed and then given to the DOS seam
(`src/sys/dos.c`) to turn into what CIO opens.  What CIO cannot do says
so: `Fseek`, `Fdatime`, `Tgetdate` and `Tgettime` are `EINVFN` today and
are counted in `gemdos_bad`, rather than answering something plausible.
On a flat DOS a path with a directory in it is `EPTHNF` and `Dcreate` is
`EACCDN`.

**Searches.**  `Fsfirst` opens the directory once and reads as much of it
ahead as the pool allows -- 1 KB -- into a slot in far memory keyed by
the DTA's address; `Fsnext` walks the slot and never touches the DOS
until the cache is dry.  Seven slots, the least recently used taken for
an eighth.  The pattern is matched here (`dos_wildcmp`), the DOS asked
for `*.*`, so the ST's `*.T*` shapes work on a DOS that has no idea of
them.  Measured on 3.2, the six-entry root: `Fsfirst` 3 CIO round trips
and 15 frames, every `Fsnext` 0 trips.

**Raw or lines.**  Where the DOS can hand out the directory itself --
`DOS_CAP_RAWDIR`, SpartaDOS 3.2's `OPEN` with aux1 `$14`, 23-byte SDFS
entries -- the slot holds entries: status byte, size in bytes, name,
date and time, so the DTA carries the true length and a real stamp.
Where it cannot (DOS 2), the slot holds the 17-character lines, the
size is sectors x 125, and the stamp is `DATE0` -- 1 January 1980 --
which is what a desktop shows for a file the DOS knows nothing about.

**Memory.**  `Malloc` is the far heap's bump allocator, wound back when
the application exits (`app_free`), so `Mfree` is a no-op and a leak
lasts one run.  `Malloc(-1)` says how much is left: 15.5 MB on the
1088K emulated Rapidus.  `Fread` into a far buffer is one CIO call --
7 frames for the fixture -- because CIO reads into a bank-$00 bounce
buffer from the pool and the bytes are copied up.

## Two bugs that were not where they looked

**The runner died at `Dsetpath("deep")`, reporting 10798 records.**
10798 is `0x2A2E`, `".*"` in little-endian ASCII.  The stack was then 1 KB
at `$3201-$3600` (2 KB since milestone 3) and `vdi_result_count` sat at
`$31FD`, directly beneath it; the first thing a stack overflow overwrites is the word the harness
polls.  The GEMDOS calls held two 128-byte paths and a 64-byte CIO name
in locals, `gd_full` under `gd_fsfirst` under `gemdos_call` under the
runner's op, and a COP from an application is served on gem4xe's stack
*under* the launcher's frames as well.  The path work is now a
`gd_work_t` taken from the pool per call (`pool_alloc`, released on
return, `ENSMEM` if there is no room), and GEMDOS's own frames are a few
dozen bytes.  Lesson recorded: a result count that reads as text is a
stack that reached it.

**`Fwrite` returned 770, then 7586, for a 149-byte write.**  The write
loop was `got = ok ? m : 0` beside a `cio_read(..., &got)` on another
path; cc65816 5.18 at -O2 loads `got` from an unrelated stack slot for
that shape.  Reproduced in six lines as B9 in `tools/ccbug` (`make
check-cc` shows the bug present and the workaround sound), the rule
written down: test the condition, break, then assign plainly.  The
compiler's ninth defect in this port; all of them are in that directory
with a reproduction each.

## What a SpartaDOS actually says (measured, 3.2g)

The GEMDOS error mapping is from CIO statuses, and the statuses had to
be measured rather than read, because the manual's are not always the
DOS's:

    XIO 35/36 (lock/unlock)              1
    XIO 33 on a protected file           $AA "not found" -- ERASE skips it
    rename of a protected file           1, allowed
    open for write of a protected file   1, allowed
    delete of a missing file             $AA
    MKDIR of an existing name            $97
    RMDIR of a non-empty directory       $A7
    RMDIR of a missing directory         $AA

So `Fdelete` of a locked file would have answered `EFILNF`, which a
desktop would show as "file not found" for a file it is looking at.
`gd_xio` re-opens the name for read on `$AA` and answers `EACCDN` if
it is there.  The raw directory open takes a pattern on 3.2
(`D1:>SUB>*.*`); the bare directory name (`D1:>SUB>`) is `$A5`.  The
`FREE SECTORS` trailer of the line listing has no leading spaces and
ends in an EOL, which is why `Dfree` keeps the last *complete* line.

## Two emulator bugs, and what they cost

Everything above runs in Altirra, and this phase found two places where
Altirra's 65C816 is not a 65C816.  Both are in native mode only, both
are in the CPU core (`src/Altirra/h/cpumachine.inl`), and both were
first seen as gem4xe crashes that no amount of reading gem4xe explained.
The fix for both is `tools/altirra/altirra-65c816-native-mode.patch`,
ten lines against upstream `b3061c7` (2026-09-01); the gates run
against a build carrying it with

    ALTIRRASDL=/path/to/patched/AltirraSDL make test

(`tools/a8test/launcher.py` takes the binary from that variable).
The installed `altirrasdl-git` package (r535, built 2026-06-24) has
both bugs, and so did upstream HEAD when they were found.  Both fixes,
with the U1MB switches below, are a pull request against
ilmenit/AltirraSDL (`tools/altirra/README.md` has the link); the CPU
core is shared with Windows Altirra, which is not on GitHub, so the
hunks carry AltirraSDL's fork marker to survive a mainline re-sync.

### 1. A taken branch reads the wrong page -- in bank $00

The SpartaDOS X gate died in the DOS: after gem4xe's first CIO call
into the cartridge, the cartridge answered garbage.  `CART_INFO` over
the bridge showed the MaxFlash bank had changed from 1 to 4 during
gem4xe's *initialisation*, before any CIO call, and nothing in gem4xe
writes to `$D5xx`.  Reading back through Altirra's own bus trace found
the write's twin: a **read** of `$D504`, and the instruction on the bus
at that moment was a `bne` at `$01D59A`, taken, to `$01D604`.

The 6502 spends an extra cycle when a taken branch crosses a page, and
in that cycle it reads the wrong-page address (`$D504` here: the old
page with the new low byte).  Altirra models that cycle as
`kStateJccFalseRead`, and emits it for the 65C816 in native mode too --
where the W65C816S data sheet (instruction table, note 7) says the
penalty exists in emulation mode only.  Worse, the read is
`AT_CPU_READ_BYTE(mAddr)`, a bank-$00 read, not a read in bank K: code
in bank $01 put `$D504` on the *motherboard* bus, and on a MaxFlash
cartridge any access to `$D500-$D50F` selects that bank.  A 21-byte
program -- a native-mode `bne` placed at `$01D5FE`, nothing else --
reproduces it: `CART_INFO` before and after differ.

Until the emulator is fixed the linker map leaves the `$D5` page of
every far bank empty (`src/gem4xe.scm`, THE HOLE): 256 bytes a bank,
and the failure becomes impossible instead of layout-dependent.  With
the patch applied the hole can go; it is kept for now because the
installed emulator is the unpatched one.

### 2. `SEI` with an IRQ pending, in native mode, never stops interrupting

With the first bug patched, `make test-m12` -- the file layer on DOS
II+/D, which had passed for three phases -- began failing on the same
hole build, at the sixth directory operation, every time.  The crash
shape was a stack that had wrapped through all of bank $00, a BRK storm
on top of the wreckage, and `REGS` sampled from the bridge showing the
program counter inside the IRQ stubs.  The false-read fix had not
caused it; it had shifted the timing by a few cycles, so that POKEY's
timer-1 IRQ (the 4 kHz pointer sampler) now arrived on the same cycle
as the `sei` at the top of `cio_call` (`src/sys/cio.s`).

The 6502 lets one interrupt through after `SEI`: an IRQ asserted during
the instruction is taken before the next one, I flag or no.  Altirra
models the shadow with `kIntFlag_IRQSetPending`, set by `kStateSEI`
when I goes 0 -> 1 and consulted by `ProcessInterrupts()` (`cpu.cpp`),
which takes the interrupt if the flag is set even though I is set.  The
emulation-mode vector states (`kStateIRQVecToPC`, `kStateNMIVecToPC`
and their `NMIOrIRQ` variants) clear the flag when the vector is
fetched.  The native-mode states `kState816_NatIRQVecToPC` and
`kState816_NatNMIVecToPC` set PC and K and nothing else.  So in native
mode the flag survives the interrupt, the handler's first opcode fetch
finds the IRQ still asserted (the handler has not run, so nothing has
acknowledged it) and the flag still set, and takes it again; and again
at every fetch, four bytes pushed each time, until S has wrapped
through bank $00 and something in the wreckage clears the flag by
accident.  On silicon `SEI` is atomic and the handler runs.

The proof is a per-state trace from an instrumented build of the
emulator (the instrumentation is not in the patch): after the `sei` at
`$388A` the IRQ sequence starts at `$388B`, then at `$3E40`, the IRQ
stub, then at `$3E40` again, and again, with S dropping by four each
time and the stub's first instruction never executed.  With the two
lines added -- clear the flag in both native vector states, as the
emulation states already do -- the same build passes; with *only* that
change and the false read left as upstream has it, it passes too,
which is how the two were told apart.

gem4xe could hide this (write `IRQEN = 0` before every `sei` that
follows a `cli`, and re-arm after), and does not: it is an emulator
defect that affects every native-mode program that uses interrupts, the
patch is ten lines, and a workaround in `cio.s` would have to be
explained to every reader who wonders why real hardware would need it.
It would not.

### What finding them taught about the rig

- **Instrument the emulator, not the program.**  Two days of poking the
  guest from the bridge -- watches, breakpoints, frame stepping, REGS
  sampled on the wall clock -- produced a dozen different crash
  shapes and no cause.  Twenty lines of `fprintf` in `cpumachine.inl`
  produced the cause in one run.  The AltirraSDL clone builds in about
  a minute incrementally (`./build.sh --release --system-sdl3`, with
  the two `-DALTIRRA_*FFMPEG*=OFF` options).
- **The bridge's watches are chip-bus layers and shift timing.**  A
  `WATCH_SET` on `$D504` made the crash move; it did not make it
  visible.  `BP_SET` does nothing in the accelerated (Rapidus) CPU
  path.  `HISTORY 4096` hangs the bridge.  Frame stepping cannot
  perturb sub-frame phase: every poke through the bridge is
  frame-aligned, so a crash that depends on which cycle an IRQ lands
  on is exactly reproducible whatever the harness does between frames.
- **A bug that moves with a fix elsewhere is usually timing.**  The
  false-read patch "caused" the m12 failure only in the sense that it
  changed which cycle a `sei` executed on.  The memory note from Phase
  6 (a bug that moves with the layout is layout-dependent) has a
  sibling now: a bug that moves with a cycle-count change is
  cycle-dependent, and the thing to trace is the interrupt.

### Status

Under the patched emulator the whole suite passes; under the installed
one `make test-m12` fails, deterministically, by the second bug, and
every other gate passes because none of their `sei`s happen to meet an
IRQ.  That "happen to" is the reason to fix the emulator rather than
the program: which gate fails next is a function of code size.

## The Ultimate 1MB, switched on at last

Phase 0 recorded that U1MB "cannot be enabled in AltirraSDL at all" and
parked it: on a Rapidus machine the U1MB is flash, SDX, PBI and a clock,
not memory, so nothing depended on it.  Phase 14 wanted the clock (for
`Tgetdate`/`Tgettime`) and, more than that, the machine as it is
actually built: SpartaDOS X booting from the U1MB flash, not from a
cartridge image the vendor made for emulators.  So the question was
asked properly.

**The core has emulated it all along.**  `ATUltimate1MBEmulator` is in
Altirra proper and AltirraSDL links it; what the SDL front end lacked was
any way to reach it from a command line or the bridge -- an ImGui
checkbox and `System.ToggleUltimate1MB` were the only paths -- and it
embeds no U1MB recovery BIOS (Windows Altirra builds one from
`src/Kernel/source/Ultimate/main.s`; the SDL resource table has no such
entry), so even switched on, an emulated U1MB had a blank flash and
nothing to boot.  Our clone of upstream (b3061c7, 2026-09-01, newer than
the installed `altirrasdl-git r535`) now carries `--ultimate1mb`,
`--u1mbrom <file>`, the bridge's `CONFIG u1mb`/`u1mbrom`, and `KEYRAW`
-- `tools/altirra/altirra-sdl-u1mb-keyraw.patch`, `tools/altirra/README.md`.

### Driving the BIOS without a keyboard interrupt

The U1MB BIOS 1.25 in the user's own flash image boots into its setup
screen on a fresh NVRAM, and it reads the keyboard the way firmware does:
polling `SKSTAT` bit 2 and `KBCODE` at `$C430`, with the I flag set and
no IRQ.  The bridge's `KEY` verb is the OS's cooked path -- it queues a
keystroke until the keyboard interrupt is enabled and acknowledged -- so
the BIOS never saw one.  `KEYRAW` holds the key in POKEY's matrix
instead (`PushRawKey`/`ReleaseRawKey`; the cursor keys are CONTROL plus
the arrow keys, and the verb splits the modifier bits into the real
SHIFT/CONTROL keys).  Per-frame readouts of `SKSTAT`, `SKCTL`, `IRQEN`
and the BIOS's own variables at `$D7xx` showed the key landing.

The first key tried, ESC, "seemed ignored": the screen was unchanged
after it.  It had been accepted.  ESC is *Abandon changes and exit*, and
with the fresh profile unsaved the BIOS exits, finds nothing saved, and
restarts straight back into setup -- `SKCTL=0`, `IRQEN=0`, loader code
at `$556B`, the same screen.  The way out is page 7, *Save and Exit*:
`RIGHT` x7 (the pages wrap), then `B` for *Save changes and boot*.
From then on the NVRAM lives in `~/.config/altirra/settings.ini`
(`"Ultimate1MB clock"`, with the firmware registration
`Firmware\Available\...` and `Firmware\Default\u1mb`), and the next
launch boots SDX directly: prompt after 100 frames, no setup screen.

### SpartaDOS X 4.49b, from the flash

    SpartaDOS X 4.49b, "Ultimate clock installed"
    PORTB $FF   MEMLO $1D99   MEMTOP $9C1F   RAMTOP $A0
    VBXE at $D640, core $10 (the BIOS shows "VBXE base: 0xD640")
    memory 1088K, cartridge slot empty (CART_INFO present: false)

The same shape as SDX 4.50 from the cartridge (docs/spike-spartados.md
§4): the DOS at `$A000-$BFFF` from the flash instead of a cartridge,
everything the Phase 13 layout assumed still true.

### `$D190-$D193` read `$FF` -- and that is correct

The Rapidus registers read `$00 $40 ..` while the BIOS ran and `$FF`
under SDX, which looked like the U1MB's `$D1xx` handling hiding them.
It is the PBI select register.  `rapidus.cpp` creates the register
layer at `kATMemoryPri_PBI` over page `$D1` and enables it only from
`SelectPBIDevice(true)` -- the OS writing the Rapidus's ID (bit 0) to
`$D1FF`.  The BIOS had it selected; SDX left `$D1FF` clear.  Every gate
in this suite already writes `$D1FF = $01` before `$D191`, from the day
the switch was first made to work, and it works under SDX-from-flash
for the same reason:

    $D1FF as SDX left it   D190-3: ff ff ff ff
    $D1FF = $01            D190-3: 00 40 ff ff      bit 6: a 6502
    $D191 = $00            reset; SDX boots again, mode 65C816
    D1:M3                  the runner up after 4250 frames (91 KB at SIO speed)

One thing to know for a real machine: the U1MB's own PBI ID is
`1 << (2 * n)` for its BIOS setting n = 0..3, so setting 0 is bit 0 --
the Rapidus's.  Altirra's PBI manager resolves the collision by whichever
device registered last; hardware would not.  Pick 1, 2 or 3.

### The rest of the flash: the PBI BIOS and the loader

The same image carries two more programs, and both matter to shipping
(docs/shipping.md, section 3).  The **PBI BIOS** is the hard-disk
driver: it reads an APT table off a SIDE cartridge's CF card and mounts
the mapping-slot partitions as `D1:`, `D2:`, ... before any DOS runs, so
SpartaDOS X needs no `SIDE.SYS` and the card needs nothing on it.  The
**SIDE Loader** is the flash's own file browser -- FAT16/FAT32 volumes,
`.ATR` images it can mount, and the APT partitions past the fifteen
mapping slots.

Driving the BIOS setup, now that a gate does it every run: LEFT and
RIGHT step the pages along the icon row, UP and DOWN move the field
cursor, RETURN changes the field under it, and the last page offers
*Save changes and boot* (`B`), *Save changes* (`S`) and *SIDE Loader*
(`L`).  On a configured machine, HELP with RESET reopens setup.  A gate
that wants the setup screen wants a fresh NVRAM, and the emulator keeps
the NVRAM in its profile, so `tests/emu/cf_boot.py` runs with
`XDG_CONFIG_HOME` pointed at `build/altirra-cf` -- its own profile,
thrown away and rebuilt each run, which also keeps the U1MB gates from
leaving state in the user's own `~/.config/altirra`.

One thing the PBI BIOS will not do is touch the disk while the
cartridge port is claimed; the wait is at `$D803` in its ROM and
shipping.md section 3 has it.

`make test-m14u` and `make test-m15u` run the two SpartaDOS gates on
this configuration (`[u1mb].flash` in `fixtures.toml`, the patched
emulator via `ALTIRRASDL=`).  They are outside `make test` because they
need both.

One trap the U1MB gates set for every other gate: the emulator saves its
profile to `~/.config/altirra/settings.ini` on exit, U1MB state included,
so the first `--u1mbrom` run left U1MB switched on for every plain run
after it -- `make test-m15x` (SDX 4.50 from the cartridge) then booted a
U1MB machine with the flash's SDX and the cartridge together, and the
runner never came up.  The launcher now pins `--noultimate1mb` in its
base arguments (the installed emulator logs the unknown switch and goes
on); `--u1mbrom` later on the line switches it back on for the run that
wants it.  A harness must state every machine option it depends on,
because the emulator remembers the last one.

And a DOS finding: the SDX in this flash is 4.49b (December 2016), and
it answers XIO 35 (protect, GEMDOS `Fattrib` read-only) with OK and does
nothing -- `whatsnew-450.txt`, 4.49f: "XIO 35 worked by accident,
fixed".  `Fdelete` then removes the file it should have refused.  The
gate reports that as a note and skips the locked-file checks on such a
DOS; the port's side of it is the same code that passes on 4.50.

## Milestone 3: the shell loop, and GEM.COM

`make test-m16` PASS.  The GEM Desktop is a program the AES runs, and
the AES's shell loop -- `sh_main` in the donor's gemshlib.c -- is what
runs it: the desktop, then whatever the desktop asks for through
`shel_write`, then the desktop again, until it asks to shut down.  This
milestone builds that loop, a desktop just large enough to drive it,
and **GEM.COM**, the product: the same bring-up as the conformance runner
with no host in it, which hands the screen to the loop and gives the
machine back to DOS when the loop ends.

`src/aes/shel.c`'s `sh_main` is the donor's: reset the windows and the
menu, draw the desk edge to edge, report the last failure, load and run
the next thing.  One departure, because the donor's desktop is in ROM
and cannot fail to load while ours is a file: a desktop that will not
load ends the loop with the reason (a negative `APP_*`), and a desktop
that returns without asking for anything is a shutdown, not the desktop
again forever.  `DESKTOP.PRG` is read once (`far_read_file`, in slices
the size of the pool's spare room) and kept below every program's far
memory, so a return to the desktop is a copy and a relocation, not a
disk read.  `src/desk/desktop.c` is the v0 desktop: a line of help and
three keys -- R runs `M11.PRG`, the ABI gate's program; X asks for a
program that is not there; Q shuts down.

The gate plays the user: R, X, RETURN on the shell's alert, Q; the desk
and the help line against the model at each stop, the shell's counters
polled while it is inside the loop, and afterwards the pool back where
it was and the far heap higher by exactly the desktop's file.  GEM.COM
was then driven the same way by hand on both product disks
(`build/gem-sp.atr`, SpartaDOS 3.2; `build/gem-boot.atr`, DOS II+/D):
GEM, R, Q, the `D1:` prompt back and a DIR working after it.  Neither
is driven by hand any more: `make test-boot` boots both with nothing
typed and requires the desk, and the DOS 2 one is double density now
(`docs/shipping.md`, sections 1 and 2).  The
disks are built by `make` now -- so is `m6split-boot.atr`, after a
gate run by hand against it compared a stale disk with a fresh linker
map and reported two bytes wrong in bank `$01`.  A gate's disk must be
as fresh as its map, and the default target is where that is enforced.

### A fault that was a stack overflow

The first run of M11 under the shell died with `graf_dragbox` "running
during `wind_open`" -- an AES call nobody had made.  Nobody had: the
VDI's fill had written `pe_ptr`, its pattern-expansion cache, and
`pe_ptr` lived at `$320E`, four bytes below the bottom of the 1 KB
stack, exactly where `gr_rect`'s return address had just been pushed.
The `rtl` went to `$01:3CD7`, the cached pattern's address plus one,
which in that build was three bytes into `crysbind`'s AES dispatch:
`dey; lda ($8e,s),y; jsl gr_dragbox`.  A drag box waits for the button,
the wait ran with the cursor vector clobbered, and the BRK it ended in
was at `$0032`.  Nothing in that chain was the bug; the chain was
`main`, the runner's op, `sh_main`, `app_exec`, the COP handler,
`gem_entry`, `crysbind`, `wm_open`, `draw_change`, `ob_draw`, `gr_rect`,
`bb_fill`, the VDI and its fill -- a kilobyte of frames, which is what a
program running under the shell under the runner costs.  Measured, the
low-water mark on the R path is 1191 bytes -- and the gate now measures
it every run: the stack section is painted at the DOS prompt before `M3`
is typed (the `.xex` writes nothing between `$2100` and `$357F`, and the
startup zeroes `zdata`, not the stack), read back after `sh_main`
returns, and the run fails if the first touched byte is within 256 of
the bottom.  1199 bytes of the 2048 at the last run.

So the stack is 2 KB, and bank `$00` had no 1 KB to give it: LoRAM was
at 98.7% and Near at 97.9%.  What moved out is bss no interrupt handler
touches and nothing polls from the host while a DOS call is in flight
-- the window trees, the message queue, the formatting strings, the
blit list, 1480 bytes -- into a new section `zwin` at `$4000-$47FF`,
the first 2 KB of the banked window (`ZWIN` on the definition,
`src/sys/zwin.h`).  The pool starts at `$4800`, 8 KB under the runner
and the whole window under GEM.COM (`src/gem4xe.scm`'s `layout`
function takes the far start and where the pool ends; the runner
links `(layout #x010000 #x67ff)`, GEM.COM `#x7fff`).  Why the data
moved and not the stack: on a Rapidus only window 0 runs at full speed
both ways -- the others read from SRAM and write through to the bus --
and a stack is written as often as it is read, while what moved is
read far more than written.

The fault handler learned from this too: `irq_brk`/`irq_abort` park in
a `wai` loop with POKEY's IRQs off rather than a tight branch, because
a branch spinning at 20 MHz overwrites the emulator's instruction
history within a frame, and the last few hundred instructions are what
a post-mortem needs (the patched emulator's `REGS` and `HISTORY`
verbs, `tools/altirra/README.md`).

### Virtual workstations

Two of the gate's screen checks failed in mirror image.  After M11 the
target's desk was right and the model's was solid; after the alert the
model's was right and the target's was solid.  Both had the same cause:
one workstation.  The AES caches the attributes it last set --
`gl_mode`, `gl_fis`, `gl_patt` and the rest, the donor's `gsx_attr` --
and skips the VDI call when nothing changed, which is only correct if
nothing else touches its workstation.  M11 opens a workstation and sets
its own fill, so when the desktop came back the AES believed pattern 4
was still set and drew the desk with M11's solid fill; the model's
V_OPNVWK reset the same shared state under its own caches the other
way round.  Invalidating the caches would have fixed the gate and
broken every GEM program, which relies on its own attributes surviving
an AES call.

The VDI now has what the specification says it has: a physical
workstation and virtual ones (`NUM_VWK` 4, `src/vdi/vdi.c`).  The
small data model addresses globals absolutely, so there is no pointer
to swap: `vwk` stays the one workstation every routine reads, and the
dispatcher copies the right one in and the previous one out when
`contrl[6]` names another -- the donor's `screen()` looks the handle up
before every call but open, and does nothing for an unknown one.
`v_opnvwk` hands out the first free handle above the physical one, from
its own `intin` (no device reset), and `v_clsvwk` never closes the
physical one.  The AES draws on the physical workstation
(`VDI_PHYS_HANDLE`, as EmuTOS's `gsx_start` opens the device itself);
a program gets the handle from `graf_handle` and opens a virtual one on
it; `app_free` closes what the program left open.  The user line style
(`vsl_udsty`) and the user fill pattern are per workstation, and the
pattern-expansion cache is invalidated when a user-pattern workstation
is swapped in, since its `patptr` is the same global either way.  The
model (`tools/vdiref.py`) keeps one attribute set per handle and
`aesref.py`'s AES calls name the physical one; the gates that draw
from a program -- m11, m16 -- now do it on handle 2 on both sides.

### The far heap moved by 224 bytes it should not have

The last failure: the far heap ended 7028 bytes above where it started,
and the desktop's file is 6804.  The 224 were the pointer's three
remembered forms (3 x 37 words, rounded to the allocator's 4), which
`graf_mouse` took lazily the first time a form was set -- during the
shell's alert, with no program loaded, so it stayed.  Had the first
form been set while a program was loaded, `app_free`'s wind-back of
the heap would have taken the forms with the program and the next
load would have written over them.  The AES's far memory is taken at
start-up, before any program's; that was the rule for `sh_init` and
`fs_start` already and it is `gsx_start`'s now.

### Sizes that changed on the way

The application ABI's `intin` is 128 words, because `v_opnvwk`'s
`work_in` is 11 and `vsc_form`'s form is 37 and `v_gtext`'s string is
whatever it is; a program's near budget (`APP_BSS`, `src/app/gemapp.scm`)
is 2 KB.  The SpartaDOS product and gate disks are 2048 sectors
(`SP_SECTORS`): M3.COM and GEM.COM are 95 KB each, and the DOS 2 disk's
1040 sectors hold one of them, the fixtures and the two `.G4A` files
with 81 to spare, which is why the shell gate runs on the SpartaDOS
disk and the products get a disk each.

The bank-`$00` map, as it stands (the one in `src/gem4xe.scm` is the
authority):

    $2000-$20FF  direct page
    $2100-$357F  zdata, the 2 KB stack, data          95%
    $3580-$3FFD  near code and constants              90%
    $4000-$47FF  zwin: bss the handlers never touch   86%
    $4800-$67FF  the application pool (to $7FFF under GEM.COM)
    $6800-$7FFF  the runner's host-poked buffers
    $8000-$9BFF  MEMAC A; farload's staging at load time

## Milestone 4: the desktop

`make test-m17` PASS.  `DESKTOP.PRG` is the GEM Desktop now, or the
first of it: `src/desk/desktop.c` and `deskobj.c` are the donor's
deskmain.c and deskobj.c cut down to what this milestone shows -- the
menu bar, a drive icon for each drive GEMDOS reports and the trash, an
icon that selects when clicked, Desk -> About and its dialog, File ->
Quit -- and `src/m16_desk.c` is the milestone-3 stand-in, kept as what
`test-m16` drives the shell loop with.  The desktop is an application
like any other: what it knows of the machine it asks the AES and
GEMDOS for, and the ninety lines of `src/app/gemlib.c` it needed --
`rsrc_load` and `rsrc_gaddr`, `menu_bar` and `menu_ienable`,
`graf_mouse`, `form_center`, `shel_write`, `Dgetdrv` and `Dsetdrv`
through the ABI's GEMDOS face -- are the bindings a program would use.
Its resource, `DESKTOP.RSC`, is built by `tools/deskrsc.py` (48 objects
of menu, 14 of the About dialog, two strings, three ICONBLKs; 3278
bytes) and loaded through `rsrc_load` into the pool behind the
program's near region, where `rsrc_gaddr` hands the trees back; the
icons are EmuTOS's, extracted from desk/icons.c by `tools/iconconv.py`
into `tools/deskicons.py` and checked in the way the font and the fill
patterns are, with `tests/host/test_deskicons.py` re-parsing the donor
so the copy cannot drift.

The screen tree is the donor's: one OBJECT array of twenty-two, the
desk under ROOT, four window boxes after it, and sixteen items on a
free chain through `ob_next`, each with a SCREENINFO beside it holding
the ICONBLK copied from the resource with its own label ("DISK A",
"TRASH") and the drive letter written into the icon.  The drives come
from GEMDOS's map -- SpartaDOS answers D1: and D2: and DOS 2 whatever
DRVBYT says -- and the icons snap to a grid the desk's size and the
icon's cell decide between them, floppies down the left, the trash in
the bottom corner.  All of it is bank-`$00` data, 1330 bytes of it in
one structure `G`, which is what the gate reads back.

### What was wrong on the way

The first run put the second icon at (31744, 3595) and the trash at
(21844, -8027).  The first icon was right, which is what made it look
like arithmetic rather than the compiler: it was the compiler.
`snap_icon` clamps its two grid parameters in place and cc65816 5.18,
inlining it at `-O2`, then loads both from a stack slot the function
never wrote -- zero for the first call, the previous call's leavings
after that.  Bug B10 in `tools/ccbug/`, a sibling of B3 and B9 (a value
assigned on one path and fetched from the wrong slot at the join), with
the workaround the others have: clamp into fresh locals and leave the
parameters alone.  Found by dumping the screen tree, not the screen.

The pointer never appeared.  The VDI opens with it hidden and the AES's
hide count at zero, and nothing before the first program's first
`graf_mouse` showed it; `graf_mouse(ARROW)` sets a shape, not the
visibility.  The donor's `sh_main` calls `ratinit()` before every
program -- the pointer on, the count zero, so that a program that
returned with it hidden does not hide it for the next -- and ours does
now (`src/aes/graf.c`).

`form_error`'s five alert texts are half a kilobyte, and the near
region was 98% full: they live in far memory now and the one wanted is
copied into the pool for the length of the call, and the LoRAM/Near
boundary moved down a page all the same (`$357F`/`$3580`), the stack
and `zdata` having the room the near code did not.

### The gate is the desktop, transcribed

The earlier gates walk a script through the runner, one record at a
time, and compare each record's result.  The desktop is not a script:
which calls it makes and with what depends on what the AES answered --
`graf_handle`'s cell size decides the icon grid, `wind_get`'s desk
rectangle the tree, `form_center`'s position where the dialog goes and
where the pointer has to click.  So `tools/deskref.py` is the desktop
itself, transcribed against the AES model: `Desktop.main()` makes the
same calls in the same order, taking its answers from `aesref`, and
what comes out is the script the target must have made (69 calls) with
a plan for each of the four waits it blocks in -- the model consumed
the plan too, so a plan that leaves an input unused or asks for one the
model does not need fails on the host before the emulator starts.  The
harness has no count of records to sync to, since the desktop is a
program, so `m7_form.drive` learned to take its position from the ABI's
own call counter, which the sys op zeroes before `sh_main` and
`gem_entry` bumps on every VDI, AES and GEMDOS call: inside the
desktop's k-th call the counter reads k+1, and the plan for a wait is
fed while the target is in that call.

Checked, in order: the screen at six stops (the desk with DISK A
selected, the Desk menu down, About under the pointer, the dialog with
OK under the pointer, the File menu, Quit under the pointer) against
the model's; `G`, all 1330 bytes, read out of the target while it waits
for the first click and compared byte for byte with the model's
`Desktop.globes()` -- the tree as deskobj.c and desktop.c built it, the
ICONBLK copies, the labels, the geometry the AES answered; the shell's
record afterwards (one run, returned 0, 69 calls, none refused); the
pool back at `$4800` with 8192 free and the far heap higher by the
desktop's file exactly (9220 bytes: near 3328, far 5086); and the stack's
low-water mark, 1190 of 2048.  Every address the gate uses -- the
program's near region, `G`, the resource -- is derived the way
`app_load` derives it, from the `.G4A` header and the desktop's own
symbol file, and the pointer's start from the target.  One thing the
model settled before the emulator did: the desktop waits for two
clicks, so a press on a menu item is held through the double-click
delay before the menu sees it, and the plans end with the frames that
cover it.

The desktop comes up 430 frames after GO on the SpartaDOS disk (the
stand-in took 240): the file, the resource, and the icons drawn through
`objc_draw`.  GEM.COM does the same from the DOS prompt, driven by hand
in Altirra with the joystick's trigger for the button.  Not in this
milestone: the View and Options items and File's window items are in
the menu, disabled (`NOT_YET`), until milestone 5 opens a folder window
and 6 runs a program from an icon and brings the desktop back.

## Milestone 5: the folder windows

`make test-m17` PASS, extended.  A double-click on a drive icon opens a
window on the drive's root, sorted folders first; a double-click on a
folder in it walks the window into the folder, File -> Close and the
closer walk it back out (at the root they close the window); the
fuller grows the window to the desk and back; the arrows scroll the
listing; File -> Close Window closes it wherever it is.
`src/desk/deskwin.c` is the donor's deskwin.c and deskfpd.c with the
window half of its desksupp.c and deskact.c, for the one view this
desktop has (icons) and the one order (name, folders first).  A window
is a WNODE: the AES window, its box in the screen tree (the four boxes
under ROOT that deskobj.c has always built, one per window, in stacking
order -- `objc_order` moves the topped one last), the rows of the item
grid in view, and a PNODE, the directory it lists -- the search spec
and an FNODE per entry read through `Fsfirst`/`Fsnext`.  The FNODEs
are in far memory: a window's worth (64) is 1.7 KB, four windows' more
than the near data allows, so the desktop `Malloc`s one arena at start
(the listing's DTA, then the FNODEs; 7212 bytes) and the AES never
reads there.  What it does read -- the window's name and information
lines, the labels behind `ib_ptext` -- stays in bank `$00`, in the
WNODE.

Opening lists the directory into the FNODEs by insertion as they are
read (the donor sorts its list afterwards; here there are 64 at most),
names the window after the spec (" A:\SUB\*.* "), puts the total on
the information line (" 145320 bytes used in 9 items."), and builds
the items -- a G_ICON per entry in the rows shown, the folder, program
or document icon by its attribute and name -- under the window's box
for the AES to draw when it asks.  Every redraw is a `WM_REDRAW`
answered with `objc_draw` under the window's rectangle list, so a
window under another draws only what shows; the open grows out of the
icon and the fuller between the two rectangles (`graf_growbox`,
`graf_shrinkbox`), as the donor animates them, and a close is not
animated.  Scrolling rebuilds the items a row on.  The bindings the
desktop needed (`src/app/gemlib.c`): `objc_order`, `graf_growbox` and
`graf_shrinkbox`, the slider modes of `wind_get`/`wind_set`, and
`Fsfirst`, `Fsnext`, `Fsetdta`, `Fgetdta`, `Malloc` and `Mfree`
through the GEMDOS face.  The resource gained the three item icons
(folder, program, document: 4150 bytes, from 3278), and the desktop's
globals are 1960 bytes now, the WNODEs in them.

### What was wrong on the way

An eleventh compiler defect, B11 in `tools/ccbug/`: a struct
assignment between a near object and a far one is an internal error
("labeling failed") when the struct is longer than 8 bytes, at every
`-O` level and in both data models -- up to 8 bytes the copy goes
through registers, from 9 it is a block move the back end cannot
label.  Near to near and far to far copy at any size.  `fn_copy`
moves the FNODE byte by byte; the shuffle within the far list is a
far-to-far assignment and compiles as it is written.

The first window never opened.  The gate stalled with the CPU parked
in the fault handler, and the post-mortem it gained for the purpose --
the screen, REGS, HISTORY, `irq_fault`, the application's S read off
the ABI's saved stack pointer -- showed S at `$5109`, below the
desktop's stack, whose bottom was `$5126`: the open (the button,
`do_open`, `do_dopen`, `do_wopen`, `graf_growbox` and the COP's frame
on top) had run the 256 bytes out into the globals below it.  A
`.G4A`'s stack is part of its near bss and had been the
linker script's `(block stack (size #x0100))` for every application;
the size is now the link's `--stack-size`, which the Makefile's `g4a`
macro takes as an argument and the map shows, and the desktop's is
640.  The measured low-water mark is 347, so 256 was ninety bytes
short.  Not 3 KB of bss, which is what the first attempt was: the
runner's pool is 8192 bytes, and the desktop's near region (3584, a
page multiple), `DESKTOP.RSC` (4150) and the 320-byte work area every
GEMDOS call takes from what is left (`gd_work_t`: two 128-byte paths
and a CIO name) leave 138 bytes for the directory read-ahead; another
page of near region would have left 202, and every GEMDOS call
`ENSMEM`.  The gate paints the desktop's stack when the desktop first
waits and reports its low-water mark with the runner's, and fails if
the margin is under 64 bytes.

The hourglass stayed over the folder the desktop had finished opening,
until the mouse moved -- in the target and in the model, so the gate
was green with it in both screens, the phase-8 lesson again.
`graf_mouse(ARROW)` is `vsc_form`, and `vsc_form` only defines the
form: a pointer that is on the screen and not moving keeps its old
picture until something draws it again, in the donor's VDI as in ours.
What the donor's AES does about it is in `gsx_mfset`, which hides the
pointer before the change and shows it after; both `src/aes/graf.c`
and `tools/aesref.py` do now, and every path to it -- `graf_mouse`,
`form_alert`'s arrow -- was re-run (`test-m13`, `test-m16`).  Not
done: the donor's control manager also swaps the arrow in while it
owns the mouse for a menu and puts the application's form back; no
program yet reaches a menu with anything but the arrow set
(`src/aes/ctrl.c`).

One thing the model settled before the emulator did, again: the
desktop asks `evnt_multi` for two clicks, so a press on a window gadget
is held for the double-click time before the AES acts on it, and only
then does the control manager watch the gadget while the button is down
and send its message at the release.  The gate's gadget click is a
press, fourteen frames, and the release (`GCLICK`).  The arrow is the
exception: its message comes at the delayed press and again for as
long as it is held, so its plan ends with the press and the next
wait's begins with the release.

### The gate, and the product disk

The transcription (`tools/deskref.py`) grew with the desktop: 250
calls, eleven waits, and the GEMDOS calls among them answered on the
model from the listing the gate reads off the disk image with
`tools/atr.py` -- the same entries, attributes and stamps `gemdos.c`
derives from SpartaDOS's raw directory -- and `Malloc` from a brk the
gate derives from the shell's.  Checked: thirteen screens (the desk,
the Desk menu, About, the dialog, the window on A:, on A:\SUB, on A:
again, full, back, scrolled, closed, the File menu, Quit); `G`, all
1960 bytes, at the nine waits where it changed, against the model's;
250 calls on both sides and none refused; the pool back at `$4800`
with 8192 free and the far heap higher by the desktop's file exactly
(16812 bytes: near 3584, far 11858, and 669 fixups); the runner's
stack low-water mark, 1223 of 2048, and the desktop's, 347 of 640.
The desktop comes up 690 frames after GO on the SpartaDOS disk (430 in
milestone 4; the file is nearly twice the size).  The model's screens
are what the target matched pixel for pixel; `--shot` keeps the
target's in `build/shots/`.

The DOS II+/D product disk holds GEM.COM, DESKTOP.PRG and DESKTOP.RSC
and nothing else now, 18 sectors free: `tools/atr.py` knows no double
density, and the three fill a single-density disk.  The gate fixtures
and M11.PRG are on the SpartaDOS disk only, which is where milestone 6
-- a program run from an icon, and the desktop back -- will find a
program to run; what the DOS 2 disk runs is a question for then.

## Milestone 6: a program from the desktop

`make test-m18` PASS.  A double-click on a program's icon runs it, and
the desktop comes back afterwards with its windows where they were.
The mechanism is the donor's, in `src/desk/deskwin.c`: `do_aopen`
makes the window's directory the default (`Dsetdrv`, `Dsetpath` --
GEMDOS verifies the directory by opening `X:\DIR\*.*` through CIO, and
a failure is the donor's alert), hands the program's name to
`shel_write(SHW_EXEC)`, and answers TRUE; `do_open` passes that answer
up through `hndl_button` and the menu's Open, and the desktop's loop
ends on it.  Before it returns, the desktop records every open window
(`cnx_put`: the current rectangle from `wind_get(WF_CXYWH)` snapped as
`do_xyfix` snaps it, the row shown first, the search spec) in a table
of slots (the donor's WSAVE, one per WNODE) and writes them to the
shell buffer as the text of DESKTOP.INF (`app_save`): `#R 02`, then a
`#W` line per slot with the sliders and the place in character cells
as two hex digits each and the path ending in `@`, after the 128 bytes
the donor reserves at the front for copy and paste data.  It does not
close its windows: the donor leaves them to the AES, and the shell's
reinitialisation takes the screen back.  The shell runs the program,
and when that returns, the desktop again, which reads the buffer back
(`app_start`, from `shel_get`, or a default of one slot per window at
`WIN_XCELL`/`WIN_YCELL` when no `#` is there, the donor's
`app_blddesk`), parses the lines (`scan_2`, two hex digits after the
spaces, and `-1` at the end), and opens each slot's window on its
path (`cnx_get`: a place off the desk is pulled back to it, the drive's
icon found for the path by its letter, `do_diropen` with the saved
rectangle and row).  The round trip is in cells, as on the ST: a
window filling the desk at (0, 11, 640, 229) comes back at (0, 11,
640, 224).

The slots and the desktop's copy of the shell buffer are in its far
arena, which grows from 7212 bytes to 11644 (the DTA, the FNODEs, the
CSAVE, 4192 for the buffer); `G` gains the two far pointers and is
1968 bytes.  `shel_get` and `shel_put` therefore take a full 24-bit
address in `addr_in[0]`, as the ST's take a 32-bit one -- the AES
only moves bytes -- and the shell's buffer, which is far already, is
cleared at `sh_init` (the donor's is zeroed BSS, and the desktop tests
its first byte for `#`) and copied far to far (`far_copy`, `far_fill`
in `src/sys/farmem.c`), clamped to its 4192 bytes.  The bindings
(`src/app/gemlib.c`) take `void __far *`.  `src/desk/deskwin.c` is
1058 lines now (757), `DESKTOP.PRG` 19844 bytes (near 3584, far
14510, and 859 fixups).

### What was wrong on the way

`do_open`'s answer.  Once the loop ended on it, `do_dopen`'s TRUE --
a drive's window opened -- ended the desktop after the first window.
The model said so before the emulator did: `test-m17`'s dry run
stopped at 110 calls where it had made 252, at the wait after the
window came up.  The donor's `do_open` (desksupp.c) calls `do_dopen`
and `do_fopen` for their effect and answers FALSE for a disk and a
folder; only `do_aopen`'s answer comes back.  Both the desktop and
the transcription had it wrong the same way, and the transcription
was the one that showed it, because its script is what the gate
already knew to be right.

The gate's stack measurement.  `test-m17` paints the desktop's stack
when the desktop first waits and reads the low-water mark at the end;
here the loader zeroes the near region for the program and again for
the second desktop, so the end shows a stack that reads as used to
its last byte -- "640 of 640" -- which is the zeroing, not an
overflow.  `test-m18` paints each run's stack while the desktop sits
in its `rsrc_load`, whose read from disk keeps it inside the ABI for
frames, so the S the ABI saved is exact and everything the run does
after the resource is measured -- including, for the second run, the
window opened from the slot before the first wait -- and reads each
run's mark at its `appl_exit`, the last call the counter sees before
the shell loads the next program over the region.

The compiler's inlining.  The first run's mark came back 511 of 640,
164 deeper than milestone 5 had measured, and `test-m17` -- which
runs no program -- now said 511 too.  The linker map had no
`do_aopen`: Calypsi inlines a static function with a single call
site, so `do_aopen`'s path and tail (48 + 128 bytes) had become part
of `do_open`'s frame and sat under every window the desktop opens,
which is where its deepest stack is (`do_dopen`, `do_diropen`,
`do_wopen`, `graf_growbox`).  `__attribute__((noinline))` is not an
attribute cc65816 knows ("unknown attribute 'noinline' ignored"), and
its inlining switches are per compilation, so `do_aopen` is external
instead: with a caller elsewhere possible the compiler leaves it a
function, and the 176 bytes are paid only on the way out to a
program.  It costs 61 bytes of code.  The first run's mark is then
425 of 640, in `do_aopen` (the buffers, the GEMDOS frames,
`shel_write`); the second's 268, and `test-m17`'s window path 292.
The margin is 215 bytes; the milestones that bring
dialogs over file operations will want it, and the near budget is
the tight one (milestone 5).

### The gate

`tests/emu/m18_launch.py` is the desktop transcribed twice against one
AES model: the first desktop's `shel_put` leaves the record in the
model's shell buffer and the second's `shel_get` finds it there, as
the target's does in the AES's.  M11.PRG between them is counted, not
replayed: the shell's restart resets everything of the AES it touches
(`m16_shell`'s model of it), so its 18 AES and VDI calls and 7 + n
GEMDOS calls -- n the root entries its `Fsfirst`/`Fsnext` walk finds,
made on the model's listing as M11.PRG makes it -- are what the ABI's
counter counts between the two desktops, and the second desktop's
plans key on the first's 148 calls plus M11.PRG's 34.  The far heap
is the same address on both runs because the shell winds it back to
the desktop's blob after every program, so the second run's `Malloc`
lands where the first's did; the model's brk is reset to the same
derivation.  Checked: six screens (the desk, the window on A:, full,
the window back on A: after M11.PRG, the File menu, Quit); `G` at the
four waits; M11.PRG's return of 18 through `sh_lastret` while the
second desktop loads; 275 calls on both sides (148 + 34 + 93), none
refused, three programs run and `sh_main` returning 3; the pool back
at `$4800` with 8192 free and the far heap higher by the desktop's
file exactly; the runner's stack low-water mark, 1223 of 2048, and the
desktop's per run.  The first desktop is in its `rsrc_load` 638 frames
after GO and up 150 later; M11.PRG loads, runs and returns and the
second desktop is loading 210 frames after the double-click, in its
`rsrc_load` the next frame, and up 185 frames later.

The DOS II+/D product disk lost the fixture DOS's demonstration
programs (XMST, MEMTEST) to make the room: `tools/mkdisk.py --remove`,
through `tools/atr.py`'s `delete`, frees the file's sectors in the
VTOC and flags the entry deleted as the DOS does.  It holds GEM.COM,
DESKTOP.PRG and DESKTOP.RSC with 41 sectors free; M11.PRG and the gate
fixtures are on the SpartaDOS disk only, and what the DOS 2 disk runs
is still the open question.

## Milestone 7: New folder, and Delete

The first two things the desktop does *to* a disk.  **File -> New
folder** puts up the donor's `ADMKDBOX` -- a title, an editable field
with the template `Name: ________.___` and the AES's `F` validation,
OK and Cancel -- takes the name the user typed, `Dcreate`s it in the
top window's directory and lists the window again, so the folder
appears where it will be found.  **File -> Delete** works on what is
selected there: it counts first, walking folders inside folders (the
donor's `OP_COUNT` pass), says what it is about to do in `ADDELDIA`
-- "DELETE FILE(S)", the number of files and the number of folders --
and on OK deletes them, a folder after its contents, with the two
counts ticking down in the dialog as they go.

The mechanism is `src/desk/deskfun.c`, in the shape of the donor's
`deskfun.c` (`fun_mkdir`, `fun_del`) and `deskdir.c` (`d_doop`): one
near path buffer mutated in place as the walk goes down and back up
(`add_path`, `sub_path`, `add_fname`, `set_all_files`), and a DTA per
level of the walk.  The DTAs matter.  Our GEMDOS keeps a directory
search in a slot owned by the DTA that started it (`SL_OWNER`,
`src/sys/gemdos.c`), exactly as the ST keeps the search's state in the
DTA itself, so a folder inside a folder is a nested `Fsfirst`/`Fsnext`
and the outer search survives it -- provided each level sets its own
DTA, which is what the donor allocates one for.  `MAX_DELLEVEL` of
them (four) sit at the end of the far arena; deeper than that is an
alert, as the donor's eighth level is.  The dialogs' fields are read
and written through the donor's `deskinf.c` shape (`inf_sset`,
`inf_sget`, `inf_numset`, `inf_what`), for which `src/app/gem.h` grew
a `TEDINFO`.

### The room it took

Two dialogs and two operations do not fit where milestone 6 left
things.  `DESKTOP.RSC` went from 4150 bytes to 4652, and the
desktop's near region from 14 pages to 16 (2944 bytes of bss, 768 of
constants) -- and the two share the application pool, which in the
conformance runner is 8192 bytes, the half of the banked window its
host-poked staging buffers leave.  Together they wanted 8748.

The room came from the gate rig rather than the product.  `GEM.COM`
already gives the pool the whole window (14336 bytes); the runner's
staging is 6 KB of conformance scaffolding that the desktop gates do
not use -- they stage a prelude, a shell op and the pool probes, a few
hundred bytes.  So `src/m3_vdi.c`'s three buffer sizes became
overridable and the Makefile builds `build/m3desk.xex`: the same
runner with `SCRIPT_WORDS 128`, `SCRATCH_BYTES 512`, `MAX_RESULTS 24`,
linked `(layout #x010000 #x78ff)`, which leaves the pool 12544 bytes.
The desktop gates (m17, m18, m19) boot that one and read their
symbols from its map; the conformance gates keep the runner they had,
buffers and all.  The desktop is now measured in a pool close to the
size the real system gives it, which is worth more than the bytes.

### What was wrong on the way

`do_filemenu`'s answer, again.  The item handlers return the
desktop's *done* flag, and `fun_mkdir` returned TRUE the way the
donor's does (where it means "handled") -- so the first New folder
made its folder and then quit the desktop.  The model's dry run found
it before the emulator ran, exactly as milestone 6's `do_open` was
found; both operations return nothing now, because only a program run
from an icon ends the loop.

A rule of the compiler's, broken.  `WORD i = (WORD)(ted->te_txtlen -
1);` is precisely the shape `tools/ccbug` rule 5 forbids -- a 16-bit
load through a local pointer with the arithmetic in the same
expression -- and cc65816 5.18 dropped the load: `i` became the
TEDINFO's *address* less one.  `inf_numset` then filled some 25 KB
with spaces, upward from the dialog's text buffer: through the
resource, through `$D0xx` -- where any write soft-resets VBXE, so the
screen went black -- and through `$D20E`, which left POKEY asserting
an interrupt that `POKMSK` did not cover, so `irq_irq` could not
acknowledge it and the machine froze in an interrupt storm.  The gate
saw a desktop that stopped making calls; its post-mortem said which
call it was inside (the ABI keeps the caller's parameter block, and
its control array starts with the opcode), what the delete had
counted, what `op_path` held, and then the CPU history, which was the
same eight instructions of the IRQ handler over and over.  The fix is
the rule's: the field into its own local, then the subtraction.  The
minimal shape is in the compiler's own defect list already; what was
new was the blast radius, and that a write to GTIA space is how a
runaway loop shows up as a black screen.

A folder SpartaDOS X has just made measures **0** in its parent's
directory entry, where the host's own `mkdir` writes 23 (one entry).
The window's information line counts the bytes it lists, so the model
has to agree: `aesref`'s `Dcreate` takes the size from the gate, which
sets it to what the target's DOS was measured to report.

And the disk itself.  AltirraSDL mounted `--bootrw` does not write the
file it was given: it copies it to `<config>/disk_state/<the image's
SHA-256>/pristine.atr` and mounts a working copy, `disk.atr`, beside
it (`ATResolveDiskMount`), reusing that copy on every later mount of
the same bytes.  So the gate drops the pair before it starts -- the
directory is named by the hash of the image the gate itself just
built -- and reads the working copy afterwards, checking the
emulator's own account of its configuration directory against the one
it looked in.

### The strings, and where they live now

Eleven `form_alert` calls in the desktop carried their text as C
literals, which is the one thing that cannot be translated.  They are
free strings of `DESKTOP.RSC` now, asked for by index through
`fun_alert(defbut, stnum)` -- the donor's shape, and its names where it
has the same alert -- with `rsrc_gaddr(R_STRING, n)` answering the
bank-$00 address `form_alert` wants.  Eleven call sites, nine strings:
two of the texts are used twice, and the resource holds each once.  The
resource grew 430 bytes; the desktop's near constants shrank by 450,
which put `DESK_BITS` back to 512 and the near region back to fifteen
pages.  One alert stays a literal, necessarily: the one that says
`DESKTOP.RSC` is not on the disk.

`docs/shipping.md` is the plan this belongs to -- `LANG.RSC` for what
the system says, a per-language resource per application, because a GEM
dialog's geometry travels with its text.

### The gate

`tests/emu/m19_files.py` boots a fresh copy of milestone 5's disk and
drives the desktop through eight stops: the desk, the window on
`A:\*.*`, the New folder dialog with `NEWDIR` typed into it, the
listing with the folder in it, the alert when the same name is typed
again -- "You cannot create a folder with that name", out of the
resource -- `SUB` selected, the delete dialog saying three files and
two folders, and the listing with `SUB` gone.  The screens are compared
with the model's at every stop, `G` at five of them, and the call
counts agree: 289 on both sides, none refused.
Then the disk image is read back: `NEWDIR` is there and empty, `SUB`
and everything under it -- `ONE.TXT`, `TWO.DAT`, `DEEP\THREE.TXT` --
is gone.  The pool and the far heap come back where they were; the
runner's stack low-water mark is 1199 of 2048 and the desktop's 291
of 640, which is the walk, its dialogs and the two nested searches
together.
