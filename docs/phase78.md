# Phase 78 -- the cartridge's white screen: say why, and wait

An AtariAge user reported that `gem4xe-0.9.1.car` gave a white screen in
Altirra.  On the machine gem4xe is built for (a Rapidus and a VBXE) it
does not: the cartridge stages the system in 21 seconds, the boot screen
comes up, then about ten seconds of white while GEM loads, then the desk
at 39 seconds -- on this tree's patched emulator and on a stock build
from June alike.  On Altirra's default 6502 it prints "this machine has
no 65C816; gem4xe needs one" and stops, as `test-m37` requires.

The white screen is **Altirra's own 65C816** (System → CPU → 65C816), the
setting a person reaches for, with its **960K** of high memory:

    0-50 s    the cartridge stages gem4xe, at 1.79 MHz rather than 20
    54 s      the boot screen: 65C816, 0.8 MB, banks $04-$0F
    60-93 s   white
    96 s      the cartridge's loading screen again -- and round, for ever

It is a loop, not a hang.  Stopped at the exit (DOSVEC pointed at an
`STP`, since a bridge breakpoint pauses the machine and the next command
then waits for ever), the shell's `sh_lastrc` was -4, `APP_E_FAR`, and
`sh_runs` 0: the desktop never ran.  The far heap's cursor stood at
$10:0000, one past its last bank.  The AUTO programs, the two control
panel modules and the accessories had taken all twelve banks, `sh_main`
returned the error **without a word**, gem4xe left -- and on the
cartridge, whose DOSVEC is the OS's cold start (`src/cart.s`), leaving is
a reboot into the cartridge.

## What changes now

`src/gem.c` `exit_desk`: when the desktop never ran, the reason goes on
the way out -- "the desktop needs more memory" with the kilobytes found,
"DESKTOP.PRG is not on the disk", or "the desktop could not be loaded" --
and when DOSVEC is still the cold start, which is to say there is no DOS
to go back to, "Press a key to start again" and `src/crt_atari.s` waits
for one.  The three lines share `exit_line`: two more buffers of
`LANG_MAXLEN` took LoRAM to 19 bytes free against `test_memory`'s floor
of 256.  The three pointers sit side by side so the assembly prints them
in one loop, and the VBXE refusal's text moved from a C constant into
LANG.RSC -- together that keeps Near at 153 free against a floor of 128.
`test_lang` now counts the number printed in front of `EXIT_FARKB`.

`make test-m37` boots the whole-system cartridge on Altirra's 65C816 with
960K and no accelerator, reads the OS's screen for the three lines,
checks the machine is still waiting ten seconds on, and that a key starts
it again.

## Why the memory ran out

Measured with 4 MB, where the desktop does come up: the heap settles at
$16:4EC4, **nineteen banks, 1.2 MB**, against twelve on 960K.

    CONTROL.ACC  5,638 bytes of code    2 banks
    CALC.ACC     3,194                  2
    GENERAL.CPX  3,991                  2
    COLOR.CPX    5,705                  2
    DESKTOP.PRG  44,986                 2

A program's code goes in whole banks at offset 0 -- the loader relocates
far addresses by the bank byte only -- and a large-data program's far
variables take a bank of their own above it (`src/app/gemapp.scm`).  Then
anything small allocated between two programs, a resource, starts a new
bank, and the next program rounds up past it.  So a 4 KB accessory costs
128 KB, and its resource another 64.

That is the memory manager's to fix, and the next phases do: an allocator
whose blocks have owners and can be freed in any order, and a loader that
can place a small program's code and variables at page granularity.
