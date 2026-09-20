# The licence position, and what is still open

gem4xe is **GPLv2 or later**.  The lineage is EmuTOS, which *is* the
Caldera-GPL'd Digital Research GEM source carried forward in C, so the
licence is inherited rather than chosen.  What follows is the part that
is not obvious, written down because it was got wrong once in this
tree's own README and because it decides what may be linked.

## The donor's two wordings, and GPLv2 section 9

EmuTOS does not say the same thing in both halves:

    vdi/*.c   "This file is distributed under the GPL, version 2 or at
               your option any later version."
    aes/*.c   "This software is licenced under the GNU Public License.
               Please see LICENSE.TXT for further information."

The AES files name **no version**, and `doc/license.txt` -- what they
point at -- is the plain GPLv2 text.  The question that matters is
whether that is a v2-only grant.  It is not, and the answer is in GPLv2
itself, section 9:

> If the Program specifies a version number of this License which applies
> to it and "any later version", you have the option of following the
> terms and conditions either of that version or of any later version
> published by the Free Software Foundation.  **If the Program does not
> specify a version number of this License, you may choose any version
> ever published by the Free Software Foundation.**

So silence is not v2-only; silence is the *recipient's* choice of any
version, v3 included.  The only arguable point left is whether pointing
at a file that happens to contain the v2 text amounts to "specifying a
version number" -- and the wording is "for further information", which
reads as naming where the licence text is rather than electing a version.
EmuTOS's own practice treats the tree as v2-or-later throughout.

**This matters less than it looks, now, and that is deliberate.**  The
only reason the project ever needed v3 was to link an Apache-2.0 C
library, and it no longer links one (below).  The tree is v2-or-later and
nothing in it requires a reader to accept the paragraph above.

## What was removed, and why

Calypsi's C library carries the string and memory functions as
`libs/libc/string/lib_*.c` and `libs/libc/...`, taken from **Apache
NuttX** and licensed **Apache 2.0**.  Apache 2.0 is incompatible with
GPLv2 -- it is compatible with v3 and not with v2 -- so linking them put
Apache-2.0 object code inside a GPLv2 binary.

`src/sys/clib.c` replaces all eight with our own, written to the ISO C
standard's wording: `memcpy memset strlen strcpy strcat strcmp strncmp
strchr`.  They are cold -- six `strlen`, five `strcpy`, two `memset`, one
each of the rest across the whole engine, none in a drawing path -- so a
byte at a time is the right shape, and they compile into `farcode` with
the rest of the C and cost bank $00 nothing.  GEM.COM got 34 bytes
smaller.

The applications -- the desktop, the calculator, the clock, and the
three accessories (`CLOCK.ACC`, `CONTROL.ACC`, `CALC.ACC`) -- never
linked any of it.  Which runtime archive they take makes no difference
to that claim: the desktop, the control panel accessory and the
calculator accessory are `--data-model=large` and so link
`clib-lc-ld.a`, where the calculator, the clock and the clock accessory
link `clib-lc-sd.a`, and `tests/host/test_licence.py` reads every map in
`build/` against both spellings rather than one.

## The compiler's runtime, and why it is not a problem

The **compiler's own runtime** is still the vendor's, in the engine and
in every application:

    pseudoRegisters.o   _Dp (738 references), _Vfp
    integer.o           _Mul16, _Mul32, _Div32, _UDivMod16, _UDivMod32
    controlFlow.o       _JmpIndLong
    vswitch16.o         _ValueSwitch16
    memory.o            _MoveLongNear
    memcpy_far.o        __memcpy_far
    memset_far.o        __memset_far
    spill.o             _FillDP2
    initialize.o        __initialize_sections
    cstartup.o          __program_start, __low_level_init
    simplified_exit.o   exit
    defaultExit.o       _Stub_exit

Eight of the twelve carry the vendor's own header, which reads, in full:

> Copyright Håkan Thörngren.  This file is part of the Calypsi C library.
> Permission to use with the Calypsi tool chain is hereby granted.

That is a grant to **use**, and it does not mention redistribution either
way.  The other four are not the vendor's wording at all.
`memcpy_far.o` and `memset_far.o` are NuttX's `lib_memcpy.c` and
`lib_memset.c`, "Copyright (C) 2007, 2011 Gregory Nutt", under the
three-clause BSD licence -- GPL-compatible, and its second clause asks
that the notice travel with binary distributions, which is why
`tools/dist/README.md` reproduces it.  `vswitch16.o` and `initialize.o`
come from `vswitch.c` and `initialize.c`, which have no header of any
kind; they fall under the tool chain's licence alone.

Read carefully, the position is narrower than it first looks, and worth
stating in both directions.

**The tool chain's licence almost certainly permits this.**  Its clause 2
expressly grants "personal non-commercial use, including personal hobby
and education, **producing application software for vintage and retro
computing systems**", and the restriction that follows -- "you may not
... distribute Software" -- is about *Calypsi*, which clause 1 defines as
"The Software and its documentation".  Not its output.  A licence whose
stated purpose is producing retro software, read as forbidding anyone
from being given the retro software, would defeat its own grant.

**And the GPL's side closes too, by the licence's own text.**  An
earlier draft of this page said the opposite -- that the whole work had
to be GPL-licensable, that 815 bytes of it was not, and that no choice
of GPL version fixed it.  That was a misreading.  GPLv3 section 1:

> The "System Libraries" of an executable work include anything, other
> than the work as a whole, that (a) is included in the normal form of
> packaging a Major Component, but which is not part of that Major
> Component, and (b) serves only to enable use of the work with that
> Major Component [...]  A "Major Component", in this context, means a
> major essential component (kernel, window system, and so on) of the
> specific operating system (if any) on which the executable work runs,
> **or a compiler used to produce the work**, or an object code
> interpreter used to run it.
>
> The "Corresponding Source" for a work in object code form means all
> the source code needed to generate, install, and (for an executable
> work) run the object code and to modify the work [...]  However, it
> does not include the work's System Libraries [...]

A compiler's runtime library -- shipped with the compiler, not part of
the compiler, linked into every program it produces and good for nothing
else -- is the case those words were written for.  The FSF's own FAQ
says so twice: a GPL program built with Visual C++ may be linked with
its runtime and distributed, "the runtime libraries are 'System
Libraries' as GPLv3 defines them"; and for any library meeting the
criteria, "the requirement to distribute source code for the whole
program does not include those libraries, **even if you distribute a
linked executable containing them**".  GPLv2 section 3 has the older,
looser form of the same carve-out ("the major components (compiler,
kernel, and so on) of the operating system on which the executable
runs"); gem4xe is v2-or-later, so every recipient may take v3 and the
explicit words.  Nor does either version ask that the compiler be free
software: the licence wants the source of the *work* to travel with the
binary, and it does.

The one condition attached, in both versions, is that a System Library
stops being one if it "accompanies the executable" -- the release must
not bundle Calypsi itself.  It does not.

So this is closed.  Two things would still make it tidier, and neither
is something a release waits for:

1. **A runtime exception from the author**, in writing.  It would settle
   the position for every program anyone builds with the tool chain
   rather than resting it on a reading of section 1.
2. **Replacing the runtime.**  About a day, not the research project an
   earlier draft made it sound.  The contracts are not in the guide, but
   one `--list-file` compile of five functions gives all of them:
   `_Mul16` takes A and X and returns A; `_UDivMod16` takes the dividend
   in A and the divisor in X and returns the quotient in X and the
   remainder in A; `_Mul32` and `_Div32` take their operands in
   `_Dp..+6`; `_ValueSwitch16` takes the value in A and the table's long
   address in `_Dp`, and the table is `.word n-1`, `.word default-1`,
   then ascending `(value, target-1)` pairs, because it returns by RTS.
   `initialize.o` need not be reimplemented at all: the linker's
   `--no-data-init-table-section` and the documented `.sectionStart` /
   `.sectionEnd` symbols let the startup clear and copy its own
   sections.  `src/sys/div16.s` is the precedent -- `--override`, and a
   reproducer in `tools/ccbug/` run under `make check-cc`.  What it buys
   is that every byte of the binary has GPL source, which the licence
   does not require and the project may want anyway.

## Keeping it true

`tests/host/test_licence.py` reads the linker maps and fails if an
Apache-2.0 unit comes back, or if the vendor-runtime set grows beyond
what is listed above.  It is the same discipline as
`tests/host/test_memory.py`: a number the machine checks rather than a
paragraph somebody remembers.

    python3 -m unittest tests.host.test_licence

## The rest of the provenance, which is unchanged

  * **The Atari Corp VDI/AES corpus is a specification only.**  It settles
    what a real ROM does; no line of it appears here.
  * **Nothing that is not ours to give is in the tree.**  No ROM images,
    no disk images, no firmware: the disk images are the user's own
    (`fixtures.toml`), and the Altirra patches in `tools/altirra/` are
    diffs against a GPLv2 project that are also filed upstream.
  * What *is* here from elsewhere is GPL'd and says so in its own header:
    the GEM 8x8 font and the standard fill patterns, extracted from
    EmuTOS by `tools/fontconv.py` and `tools/patconv.py`.
  * **The DOS on each disk image is not gem4xe's.**  It is there so the
    disk boots; whoever owns it owns it.
