# Phase 82 -- no SEI in native mode: Windows Altirra's IRQ shadow

The AtariAge user whose black screen phase 81 went after sent their
setup: a PAL 130XE with 1088K, a VBXE, a Rapidus and Atari's XL OS rev.
2, in Windows Altirra, loading the 0.9.2 `.car`.  So not AltirraOS, and
not a plain 65C816: the machine every gate here runs, but in the other
emulator.  Their debugger history, 200 instructions of it:

    00:FB0A: 94 46     STY $46,X
    00:FB0C: 00        BRK
    00:FAFF: 4D FA 4C  EOR $4CFA
    00:FB02: 1E F2 00  ASL CIX,X
    ...                            (S four bytes lower each time round)

`$FAFF` is what Atari's XL ROM holds at `$FFE6`, the native-mode BRK
vector.  The CPU was running the ROM's data as code, a `BRK` every fifth
instruction, each taking the stack down four bytes; gem4xe's own vectors
were long gone by then.

## Windows Altirra's 65C816

In native mode Altirra's 65C816 lets the one IRQ through that arrives
as an SEI, SEP #$04 or PLP sets I -- as a 6502 does -- and never clears
the flag that let it: `kState816_NatIRQVecToPC` and `NatNMIVecToPC` do
not do what the emulation-mode vector states do.  So the IRQ is taken
again at the handler's first opcode fetch, and every fetch after, for as
long as the source is asserted, and the handler never runs an
instruction to acknowledge it.  Four bytes pushed per fetch until the
stack has wrapped through bank $00, the hardware registers included
(PORTB among them: the ROM comes back in, and with it `$FFE6`).

gem4xe found it in phase 14, and AltirraSDL has had the fix since PR
#88 (tools/altirra/README.md) -- which is what the gates run.  The
fork's source still marks it "not yet in Windows Altirra" after its
4.50-test21 sync.  gem4xe's timer 1 at 4 kHz, and an SEI after every
VDI and AES call, make the moment it needs a matter of seconds to
minutes: the reporter's crash came at about half a minute.

**Reproduced.**  `tools/altirra/altirra-sdl-windows-irq-bug.patch` takes
the fix back out of an AltirraSDL.  On the reporter's machine the 0.9.2
cartridge crashes there (a screen of one colour, the storm's signature)
and reaches the desktop on the fixed build.  The phase 81 build crashes
the same way.

## The fix: I is set by an interrupt

An interrupt sets I without the shadow, in Altirra's core as on the
chip.  `irq_sei` (src/sys/sei.s) makes a COP from one address,
`irq_sei_ret`; `irq_cop`, where the COP vector goes now, knows it by the
return address the CPU pushed, all 24 bits, before it saves or writes
anything, and returns with I set in the P its RTI pulls; any other COP
goes on to `gem_cop` (src/sys/abi.s) as it came.  A file of its own,
because the programs that run with interrupts link different halves of
the rest: m27 has abi.s and no irq.s, m30 irq.s and cio.s but a stub
for abi.s -- the first version, in those two, failed both.  Every register, both widths and the
flags come back as they went in.  With I already set it makes no COP at
all -- which is also what keeps it safe before `irq_install`, when
`$FFE4` is not yet gem4xe's.  About 60 cycles against an SEI's two.

The native-mode SEIs it replaces: the one after `gem_entry` in the COP
handler (every VDI, AES and GEMDOS call from an application), the one at
the top of the CIO trampoline (every OS call), and `cpu_sei()`, which is
`irq_sei` now instead of the compiler's `__disable_interrupts()`
(`irq_remove`, the boot logo's raster loop).  The SEIs left are in
emulation mode or run with I already set, and `tests/host/test_sei.py`
lists each with its reason: a new one fails it until it is looked at,
and C cannot write one.  (Calypsi's library has one SEI, in the Foenix
float coprocessor's path, which gem4xe does not link.)

## The gate

`make test-winbug` boots the whole-system cartridge on the reporter's
machine in an AltirraSDL built with that patch, and asks for the
desktop and two minutes more of it with the vertical blank and the
sampler counting and no fault.  It is not part of `make test`: it needs
that build (`WINBUG=`), and fails without one rather than skipping.

    this build     PASS  VBI 6,000 of 6,000 frames, sampler 474,011, fault 0
    0.9.2's .car   FAIL  VBI 0, sampler 0 -- the storm

m12 (which failed deterministically on the unfixed emulator when it was
written), m17, m37 and m38 pass on it too.

What to tell a Windows Altirra user until Altirra has the fix: gem4xe
from this build on; or AltirraSDL, which has it.  The report for
Altirra's author is the user's to send.
