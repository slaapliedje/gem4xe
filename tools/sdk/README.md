# The gem4xe application kit

Everything needed to build a program that runs on gem4xe, and nothing
of gem4xe itself: an application links against **no** part of the
system.  It reaches the VDI, the AES and GEMDOS through three call
gates and is loaded, relocated and called at run time.

    make                        example/hello.c  ->  hello.g4a
    make APP=mine.c             mine.c           ->  mine.g4a
    make APP=src/mine.c NAME=ed                  ->  ed.g4a
    make APP=mine.c ASM="fast.s io.s"            ->  mine.g4a, your assembly linked in

You need **Calypsi for the 65816** (`cc65816`, `as65816`, `ln65816`),
**5.18.2 or later**, from <https://www.calypsi.cc/>.  Its licence covers
personal, non-commercial use and names "producing application software
for vintage and retro computing systems" expressly; read it before you
sell anything.  Point `CALYPSI` at the toolchain if it is not in
`~/dev/toolchains/calypsi-65816`, and you need Python 3 for the packer.

**Read `doc/ccbug.md` before you debug anything.**  That compiler has
defects this project has catalogued, and several of them -- a narrowed
operand losing its sign extension, a conditional assignment dropped, a
signed `>>` that is not arithmetic -- produce a **silently wrong answer**
in ordinary C with nothing to say the compiler is at fault.  Every one
was first seen here as a wrong pixel or a wrong return value and blamed
on the program for a while first.

## What kind of thing are you building

Three, and `KIND` says which:

    make KIND=prg APP=example/hello.c     a program          install as .PRG
    make KIND=acc APP=example/acc.c       a desk accessory   install as .ACC
    make KIND=cpx APP=example/cpx.c       a panel extension  install as .CPX

All three come out as a `.g4a`.  **That is the container and it is the
same for all of them; the extension you install it under is the role**,
and the role is what the system reads.  The desktop launches a `.PRG`
(and `.APP`, `.TOS`, `.TTP`, `.G4A`); the AES loads `*.ACC` and `*.CPX`
out of its own directory at start-up and never out of `\APPS\`.

There is a fourth thing you can build with `KIND=prg`: a program that
ends with `Ptermres` and stays -- see "Starting at boot" below.

## What is here

    include/gem.h       every call the system serves, declared
    include/portab.h    the compiler's dialect -- FAR, SIMPLE_CALL and
                        the rest -- in one place, for a second compiler
    lib/gemlib.c        the bindings: they fill a parameter block and
                        make the call
    lib/gemstub.c       the routines the C library asks the BOARD for --
                        open, read, write and the rest -- over GEMDOS,
                        which is what makes printf work
    lib/gemstat.c       stat(), one Fsfirst with the caller's DTA put back
    lib/gemabi.s        the three call gates -- COP #$56 (VDI),
                        COP #$41 (AES), COP #$44 (GEMDOS); a program
                        built with an older kit's ($73, $C8, $01) is
                        refused by the loader and must be rebuilt
    lib/crt_gemapp.s    the start-up: a stack, a direct page, the data
                        sections, main
    lib/gemapp.scm      the linker's rules and your memory budget
    include/cpx.h       the control panel extension contract
    lib/cpxmain.c       a module's main(), which you do not write
    lib/gemtime.c       time(), gmtime(), strftime(), clock()
    lib/gemcompat.c     stricmp(), opendir() and the rest an ST source
                        reaches for
    include/osbind.h    ...and the headers an ST source includes by
    include/tos.h       reflex.  Most are one door pointing at gem.h;
    include/mintbind.h  support.h and dirent.h carry real code in
    include/gemx.h      lib/gemcompat.c.  They are here because the qed
    include/macros.h    port wrote every one of them in its own shim
    include/strings.h   before they were
    include/support.h
    include/dirent.h
    include/time.h      a 32-bit time_t (doc/ccbug.md, B20)
    include/sys/stat.h  no <sys/> in Calypsi's own libc
    tools/mkg4a.py      ELF x3 -> .g4a, deriving the loader's fixups
    tools/install.py    put what you built on a gem4xe disk image
    tools/atr.py        the disk file systems install.py uses
    doc/ccbug.md        the compiler's defects, and the rules the
                        sources follow to avoid them.  READ THIS
    example/hello.c     a whole program, commented
    example/acc.c       a whole desk accessory, commented
    example/cpx.c       a whole control panel extension, commented

The library is source, not an object, so that it is built by *your*
compiler with *your* flags -- and so that you can read what a call
actually does.  One flag to keep: `lib/gemlib.c` is compiled with
`--no-interprocedural-cross-jump`, as this kit's Makefile does.  Without
it, at `-O2`, the compiler shares one tail across the GEMDOS bindings
and parks it inside one function's section, so a `--data-model=large`
program that calls `Fread` links `clock`, `Tgettimeofday` and `Psystem`
it never calls -- 352 bytes, and more with every binding added.  With it
each binding is its own section and costs you 3-13 bytes per binding
you call, and nothing for the rest; two programs that build their own
bindings measured 1,028 and 1,075 bytes shed, the cluster's passengers
included.  It pays only under `--data-model=large`: the small model's
bindings share no tail, so a `--data-model=small` image is the same
size either way, and the flag is kept there for one rule, not for a
saving.

## The shape of a program

    #include "gem.h"

    int main(void)
    {
        appl_init();
        ...
        appl_exit();
        return 0;
    }

`main`'s return value is the program's exit status; gem4xe's shell
takes it and puts the desktop back.  There is no `argc`/`argv`: a
command tail arrives through `shel_read`, as it does on an ST.

`example/hello.c` opens a workstation, draws, waits and leaves.  An
interactive program puts an `evnt_multi` loop where the wait is and
answers the `WM_*` messages the window manager sends it.

## What you can call

Everything in `include/gem.h`, which is the whole surface the system
serves:

- **VDI** -- the drawing, in the names it has had since 1984:
  `v_pline`, `v_gtext`, `vr_recfl`, the ten GDPs (`v_bar`, `v_arc`,
  `v_circle`, `v_rbox`, `v_justified`, …), `v_fillarea`,
  `v_contourfill`, the markers, the raster calls (`vro_cpyfm`,
  `vrt_cpyfm`) with a real `MFDB`, the attribute setters, every `vq*`
  inquiry, `vs_clip`, the mouse form and the vector exchanges.
- **AES** -- `appl_*`, `evnt_*`, `menu_*`, `objc_*`, `form_*`,
  `graf_*`, `wind_*`, `rsrc_*`, `shel_*`, and the file selector
  (`fsel_input`, `fsel_exinput`).
- **GEMDOS** -- `Fopen`/`Fread`/`Fwrite`/`Fclose`, `Fsfirst`/`Fsnext`,
  `Dcreate`/`Ddelete`/`Dsetpath`/`Dgetpath`, `Frename`, `Fattrib`,
  `Fdatime`, `Malloc`/`Mxalloc`/`Mshrink`/`Mfree`, the clock -- and the
  rest of TOS 1.04's: `Cconws`, `Cconin`, `Cconrs` and the other character
  calls reach a VT-52 console drawn on GEM's screen, through standard
  handles `Fdup` and `Fforce` can point at a file; `Pexec` (mode 0) runs
  another program and has it back; `Pterm` ends yours from anywhere.

Four VDI opcodes have no binding on purpose -- cell array (10 and 27),
the valuator (29) and 34 -- because the driver answers them with
nothing, and a call that silently does nothing is worse than a name
that is not there.

Two names are gem4xe's rather than the ST's, and say so where they are
declared: `v_string` answers **one** GEM key code per call rather than
a line, and a `vex_*` vector is a `LONG` rather than a function
pointer, because a handler is 24 bits under the large code model.

## Porting from the ST

What a program written against the ST's C libraries meets here, found by
compiling cflib against this kit (94 of its 141 files build with no
edit) and written down so the next port does not find it one error at a
time:

- **The published names are here.**  Object types, flags and states,
  `ED_*`, `K_*`, `WM_*` and `WF_*` (AES 4's `WM_ONTOP`, `WM_UNTOPPED`
  and `WF_BOTTOM` among them, declared and not served), `MD_*`, the line
  types and ends, and the structs an ST resource or binding names --
  `CICONBLK`, `MENU`, `PARMBLK`, `USERBLK` -- each with a line in `gem.h`
  saying what this AES does with it, which is not always what the ST's
  does (`G_CICON` draws its mono form; `G_USERDEF` draws nothing yet;
  `menu_popup` is not served).
- **`evnt_multi` has the ST's shape**: twenty-three arguments, the two
  mouse rectangles flat.  `evnt_multi_moblk` is the same call with the
  rectangles as `MOBLK`s, for a program written here; the AES sees no
  difference.  **One argument still differs from mintlib's binding**, and
  it is the timer: the AES takes it as two words, low then high, which is
  what this kit declares, where mintlib takes one `unsigned long`.  So a
  ported ST event loop is one argument away from identical rather than a
  different shape -- which is close enough that an `#ifdef` around the
  call wants a comment saying so.
- **`<sys/stat.h>` and `<mint/cookie.h>` are the kit's**, Calypsi's C
  library having neither: `stat()` is one `Fsfirst` (kind, size, one
  stamp for all three times, `ENOENT` for a path that names nothing),
  and `Getcookie()` answers `C_NOTFOUND` for every cookie, there being
  no jar -- the answer a well-written program defaults on.
- **`printf` works, and a file descriptor is a GEMDOS handle.**  The C
  library reaches the platform through nine routines it expects the board
  to provide, and `lib/gemstub.c` is all nine, over GEMDOS.  Descriptors
  pass straight through with no table: stdout is handle 1 and reaches the
  VT-52 console on GEM's screen, `Fforce` redirects it into a file as it
  does on an ST, and `open` hands back the GEMDOS handle itself.  Without
  that file a program that prints does not link, and what the linker says
  -- *missing stub routine '_Stub_write' needs to be provided for your
  hardware/board-support* -- names the board rather than the program, so
  it is worth recognising.  Two things are not a Unix system call and
  cannot be: `O_APPEND` seeks to the end once, at open, GEMDOS having no
  append mode; and the errors are GEMDOS's, mapped to the nearest
  `errno`, so a missing file and a missing path both arrive as `ENOENT`.
- **Stdout is unbuffered, so a line costs a call per character.**  Ten
  bytes are ten trips through the call gate and into GEMDOS, which is
  fine for a diagnostic and slow for a report.  `setvbuf` with a buffer
  of your own is the fix; there is no heap, so give it the array rather
  than asking stdio to allocate one.
- **The compiler says `__CALYPSI__`, not `__GNUC__`.**  A header that
  branches on `__GNUC__` takes its other path here; and a symbol such a
  header defines only under `__GNUC__` or `__PUREC__` (cflib's `_WORD`)
  must come as `-D`, Calypsi having no `-include`.
- **A stub should answer TRUTHFULLY, not merely link.**  This is the one
  that has cost ported code the most here, and every instance looks
  harmless in isolation.  A `Getcookie` that answered "found" with an
  empty jar would have sent a program off to read the ST's cookie-jar
  pointer at `$5A0`, which on this machine is whatever happens to live
  there; answering `C_NOTFOUND` kept it away.  An `appl_xgetinfo` that
  returns 0 sends a library down a fallback that picks a font height of
  13 on a machine whose cell is 8.  A `Dpathconf` that claims a case
  distinction this filesystem cannot honour has the caller comparing
  filenames on a promise nothing keeps.  A `vq_vgdos` answering anything
  but -2 loads fonts that are not there.  Four shapes, one mistake: the
  temptation when porting is to stub the smallest thing that links, and
  that is exactly what turns a missing answer into a plausible wrong one.
  Prefer the answer that is true about this machine, even when it is
  "no".
- **Files with bytes above 127** -- Atari sources often are -- defeat a
  `grep` without `-a`, including a grep for exactly those bytes.

## Writing a desk accessory

`example/acc.c` is a whole one.  It is built exactly like a program --
same crt, same gates, same budget -- and four rules make it an accessory.
Each is a rule rather than a style, and three of them fail silently:

**It never returns.**  A program's `main()` ends and the AES frees it;
an accessory parks in `evnt_mesag()` forever.  Returning hands your
memory back while the Desk menu still carries your name.

**It registers a name, and keeps the string.**  `menu_register(id, title)`
answers your slot, which `AC_OPEN` arrives in as `msg[4]`.  The AES
stores the **address** of your title, not a copy, so it must be `static`
or global.  A title in a local works until the stack is reused, and then
the Desk menu draws rubbish.

**It takes what it needs at start-up and never gives it back.**  An
accessory loads before the first program, and both of gem4xe's
allocators are bump allocators that wind back to a mark when a program
exits.  Anything you allocate *after* a program has loaded is freed
underneath you the first time that program ends.  So `rsrc_load` in
`main`, before the loop -- **not** on first `AC_OPEN`, which is the
obvious thing and is wrong -- and never `rsrc_free`.  Same for a
workstation: one `v_opnvwk` kept for the life of the machine.

**`AC_CLOSE` is about somebody else.**  It means the program you were
open over is going away, so anything of *its* that you were holding is
gone.  Do not close your own window on it -- the AES has.

Six slots, TOS's number, and the loader stops sooner if the pool runs
out.  It goes in `\GEM\`, never `\APPS\`: the AES scans its own
directory for `*.ACC` and nowhere else.

## Writing a control panel extension

`example/cpx.c` is a whole one, and `include/cpx.h` is the contract.
This is XCONTROL's shape: the **host** owns the window and the event
loop, the **module** owns the dialog, and they meet at a vtable the
module publishes when it loads.

**You do not write `main()`.**  `lib/cpxmain.c` is linked in for you: it
reads the slot address the AES left in the command tail, calls your
`cpx_init()`, publishes what you return, and ends with `Ptermres` so the
module stays.  You write `cpx_init()` and the entries it hands back.

**Every entry takes one `uint32_t`, and the compiler decided that.**  A
cross-module entry must be `SAVEDS` so it establishes its own direct page
and data bank; this compiler emits that switch *before* the body reads an
argument the caller left in the **caller's** direct page.  Measured
across five signatures: one `short` is safe, one `unsigned long` is safe,
and a second argument of any kind -- or a first one that is a pointer --
arrives as garbage, with nothing refused and nothing warned.  So: one
`uint32_t`, cast inside.  That is GEM's own ABI shape anyway.

**Two kinds**, and `cpx_call` says which by what it leaves in `pb->ret`:
`0` is a form CPX (you ran your own `form_do` and are finished), `1` is
an event CPX (you drew yourself, and the panel now feeds you events until
you set `pb->quit`).

**Your sixty-four bytes.**  The AES keeps a buffer per module at
`xcpb->buffer`.  Write it and call `CPX_Save`, and it goes to
`<YOURNAME>.CFG` beside the module -- you never learn your own name,
which is what stops two modules arguing over one file.  Set
`CPX_BOOTINIT` in your flags and the panel opens you once at start-up
with `xcpb->booting` true, so you can put settings back before anybody
sees the desk; draw nothing on that pass.

**Canned alerts.**  `XGen_Alert` puts up one of the panel's own -- by
number, so every module says "that file was not found" in the same words
and a translator translates it once.  Check the callback for 0 before
calling it: `cpx.h` says every callback may be 0, and a host that hands
out fewer than this one does is allowed.

A port from an ST changes one thing in its source besides the above:
COPS's by-value struct arguments become ordinary argument lists.

## Starting at boot

A program in `\GEM\AUTO\` is run once at start-up, in name order,
before the extensions and the accessories and before the AES fixes the
permanent floor.  End with `Ptermres` and you stay; return normally and
you are freed like anything else.

**`Ptermres` here is all or nothing.**  The ST's takes a byte count and
frees the rest; both of gem4xe's allocators are bump allocators, so
giving back the tail of a region would leave a hole neither can ever
hand out again.  The `keep` argument is accepted and the region is kept
whole, so size your program rather than the argument.

An AUTO program gets **no process record and no turn in the event
loop**.  It runs, installs whatever it installs -- a vector, a service
another program will look for -- and the machine goes on without it.
`.PRG`, `.G4A`, `.APP` and `.TOS` run from there; `.TTP` deliberately
does not, because there is nobody to type its command line.

## Your resource

**Making one.**  The file format is the **ST's**, unchanged -- gem4xe's
loader is the donor's -- so anything that writes a GEM `.RSC` writes one
this reads.  In practice that means a Resource Construction Set: Atari's
own RCS or ORCS under an ST emulator, or `Interface` on a modern host.
There is no gem4xe-specific step and no conversion; copy the `.RSC` onto
the disk beside your program.

gem4xe builds its own resources a third way, from Python descriptions
(`tools/rsc.py` in the source tree), which is convenient when the layout
wants to be generated rather than drawn.  That is not in this kit: it
depends on the project's host model of the AES, which is larger than the
kit itself.  If you want it, it is in the source tarball on the release
page.

**One authoring rule that is not obvious**, because it decides what your
resource costs at run time: put the image block **last**, after the
tables, which is how RCS lays one out.  `rsrc_load` moves icon bitmaps
to far memory and hands the pool back what they took -- but only when
`rsh_imdata` is the last thing in the file.  A file with tables above it
keeps its bits in bank `$00` and costs its whole `rsh_rssize`.


`rsrc_load` reads the whole `.RSC` into the application pool in one
piece -- `rsh_rssize` bytes -- fixes it up in place, then moves any icon
bitmaps to far memory and hands the pool back what they took -- when the
image block is the last thing in the file, which is how RCS lays one out
and not how every tool does; a file with tables above `rsh_imdata` keeps
its bits in the pool and costs its whole `rsh_rssize`.  So a
resource has to fit the pool beside everything else resident, and the
`OBJECT` trees in it cannot go far: the AES reads them in place.  That is
the limit a large ST program meets first; measure a resource's
`rsh_rssize` against the pool before anything else.

**New-format resources -- the ones with colour icons -- load.**  The
extension past `rsh_rssize` is streamed to far memory and never sits in
the pool; what comes back near is one 50-byte record per icon, the mono
`ICONBLK` every `CICONBLK` begins with.  A `G_CICON` draws that mono
form for now.  Its colour planes are kept far beside it, for the day the
object library draws them: on this 16-colour surface that is the natural
thing to do, and it is not done yet.

## Your memory

The three numbers at the top of the `Makefile` are the budget, and the
link enforces every one:

| | |
|---|---|
| `BSS` (2048) | near memory with no initial value: your stack and your uninitialised data |
| `BITS` (256) | near memory with one: constants, and the initial values of data |
| `STACK` (256) | how much of `BSS` is stack |
| code | a far bank of its own -- 64 KB, and not part of the above |

The near part comes out of **the application pool**, which is
**14,336 bytes** in bank `$00` (`$4800-$7FFF`) for the whole machine --
your program, the desktop, every desk accessory and every control panel
extension, together.  With the desktop and the three accessories gem4xe
ships resident, about **8 KB of it is free**, and that is what your
program's near region is taken from.  So the 2048 above is your budget
inside a shared 14 KB, and bank `$00` is the scarce thing on a machine
with 14.9 MB.  Keep large data in far memory:
`Malloc` answers with a far address, and `__far` pointers reach all
15 MB.  A `char buf[1024]` on the stack is how a first program runs
out.

**There is a real clock.**  `Tgettimeofday` -- MiNT's call, GEMDOS
`0x155` -- answers seconds and microseconds from a ~4 kHz timer the
system keeps, monotonic and exact to a quarter of a millisecond, and
`clock()` in this kit is built on it in `CLOCKS_PER_SEC` units, so a
program written against mintlib's `clock()` runs unchanged.  Pace by
that, not by counting `vex_timv` ticks; and sleep with `evnt_timer`,
which yields to the accessories, rather than spinning on the clock --
a spin that never calls the AES starves everything else on the machine.
The ST's 200 Hz system variable is not reachable here (no supervisor
mode, no address an application may read), so a port that reads
`_hz_200` directly changes that line to `Tgettimeofday`.

**There is a DOS prompt to hand a line to.**  `Psystem(line, out, max)`
-- gem4xe's own, GEMDOS `0x1F0` -- runs `line` through SpartaDOS X's
command processor (`XCOMLI`) with GEM's screen left as it is, and every
byte the command prints lands in `out`, `max` bytes of a buffer you
`Malloc`'d, the DOS's `$9B` ending each line; it answers the bytes
caught.  `DIR`, `COPY`, `DEL`, `MKDIR`, `CHKDSK` and the rest of the CAR:
set run in the ten KB of bank `$00` the system is not using; a program
that stays resident from there does not survive the call, and a command
that asks a question has nobody to answer it -- the DOS's console is
under the overlay.  `Psystem(0, 0, 0)` asks only whether there is a
command processor: `EINVFN` on a DOS 2, a SpartaDOS 3, a SpartaDOS X
before 4.4 or one that started GEM with `X.COM`, and a program should
grey its item on that answer, as the desktop's **File -> DOS command...**
does.

**There is no C heap.** Your heap block is zero bytes, because memory
above bank `$00` is `Malloc`'s to give out. `malloc` and `free` are
refused at link time -- a call to either fails with an undefined symbol
named `gem4xe_has_no_heap__use_GEMDOS_Malloc` -- so use `Malloc`.  If you
build this kit's library from its sources yourself, `lib/clib.c` is what
carries that refusal.

Leave room in `STACK`: the AES calls back **into** your program --
a redraw while a dialog is up, for instance -- so the deepest stack is
not the one your own code makes.

## Getting it onto a disk

A `.g4a` is a file like any other, and `tools/install.py` puts it on
one of the disk images the release ships -- the one you were going to
boot anyway:

    python3 tools/install.py gem4xe-0.6.1-apps.atr mine.g4a "APPS>MINE.PRG"
    python3 tools/install.py gem4xe-0.6.1.atr acc.g4a "GEM>MINE.ACC" mine.rsc "GEM>MINE.RSC"
    python3 tools/install.py gem4xe-0.6.1-apps.atr --ls

It edits the image in place unless you give `--out`, and replaces a name
that is already there, so keep the original.  `>` is SpartaDOS's path
separator, which is what these images use.

**Where a thing goes is not filing** -- it decides whether the system
looks at it at all:

| | |
|---|---|
| `GEM>NAME.PRG`, `APPS>NAME.PRG` | a program, launched from its icon |
| `GEM>NAME.ACC` | a desk accessory. `\GEM\` **only** |
| `GEM>NAME.CPX` | a panel extension. `\GEM\` **only** |
| `GEM>AUTO>NAME.PRG` | run once at start-up |
| `GEM>NAME.RSC` | a resource: `rsrc_load` takes a bare name and resolves it against the system's directory |

The extension is the role; the loader checks the file's **magic** and
refuses anything that is not gem4xe's, so a 68000 `.PRG` off a real
Atari is turned away with a message rather than run.

## Trying it

    AltirraSDL --pal --hardware 800xl --kernel xl --nobasic \
        --memsize 1088K --cleardevices \
        --adddevice "vbxe,version=126,alt_page=false,shared_mem=false" \
        --adddevice rapidus \
        --diskemu generic --nofastboot \
        --disk gem4xe-0.6.1.atr

Two of those switches are load-bearing and were each found the hard way.
**`--diskemu generic`**: with `fastest`, the SpartaDOS disk does not boot
at all.  **`--nofastboot`** for the same class of reason.  The release
page has the rest -- the two Altirra 65C816 native-mode bugs and which
build fixes them, and why the machine cold-boots as a 6502 and restarts
itself.

A second drive is the easy way to carry your own work: put the apps
floppy in `--disk` twice over, or build your program onto a copy of it
and boot the system disk beside it.

If your program has a resource, `rsrc_load("MINE.RSC")` reads it from
the same disk, and it must be a real GEM `.RSC`: gem4xe's resource
loader is the donor's, and the file's format is the ST's.

## Licence

GPLv2 or later, like the rest of gem4xe -- see `COPYING`.  The library
here is part of gem4xe, so a program that links it inherits that;
`gem.h` and the bindings are the interface a GEM program has always
had, and the terms are the ones EmuTOS's are under.
