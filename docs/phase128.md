# Phase 128 -- MVN for the far copies, and why it failed before

The third item of the order agreed after phase 122: find why MVN broke
SpartaDOS X in phase 120, then use it.  It is in `far_put`, `far_get` and
`far_copy` now (`src/sys/farmem.c`, `src/sys/blkmove.s`), for every copy
of eight bytes or more but one kind.

## The cause: the emulator's MVN reads bank $00

Altirra's 65C816 runs MVN as states: read the source byte, write the
destination byte, then two "false reads of destination"
(`src/Altirra/source/cpu65c816.cpp`, `Decode65C816`, opcodes `$54` and
`$44`).  Those reads use the address register, the destination's
**offset**, with the address bank still the **source's**, set by cycle 3.
The W65C816S data sheet has no memory access in those two cycles: they
are internal operations (`IO`, VDA and VPA low).

So a copy **from bank $00**, which is what `far_put` is, reads bank $00 at
every destination offset, twice per byte.  If the destination's offsets
fall in `$D000-$D7FF`, those reads hit the hardware registers.  SpartaDOS
X comes on a MaxFlash cartridge, where any access to `$D500-$D50F`
selects a bank, so the DOS's next call into its cartridge runs garbage.
Whether a far block lands at such an offset depends on what was allocated
before it, which is why phase 120 found it "layout- and timing-dependent",
in emulation mode with a far data bank and no obvious leak.

It is the second bug of this family: `src/gem4xe.scm` already keeps far
code out of the `$D5` page because Altirra folds a taken branch's
page-crossing read into bank $00.

### How it was found

The bridge could not break on the accelerated CPU and returned at most
4,096 instructions of history.  A local build adds `HISTORY count skip`
to page through the CPU's whole 131,072-entry ring buffer.  With it, a run
was stopped where SpartaDOS X's own RAM handler called into its cartridge
and ran garbage: the cartridge was in another bank, and no instruction
in the history had touched `$D5xx`.  The emulator's MVN source showed
which accesses the history does not record.

### Proof both ways

| | stock Altirra | MVN's two cycles made `kStateWait` |
|---|---|---|
| MVN everywhere, `test-m46` (SpartaDOS X) | fails, 3 of 3 | **passes, 3 of 3** |
| MVN except the window, `test-m46` | **passes, 3 of 3** | |
| MVN except the window, `test-m37` (the cartridge boot) | **passes, 2 of 2** | |

The patch to Altirra makes cycles 6 and 7 `kStateWait` in both 65C816
decoders (`Altirra/source/cpu65c816.cpp`, `ATCPU/source/decode65816.cpp`).
It is drafted for upstream and not yet sent.

## The rule gem4xe keeps until every emulator has the fix

`mvn_safe` gives MVN every copy except one **from bank $00** whose
destination offsets touch `$D000-$D7FF`. Those keep the byte loop.  A
far source's false reads land in far RAM and do no harm.  On real
hardware the rule costs a few copies a little speed and nothing else.

## The gate

`test-m15x` (the GEMDOS gate under the SpartaDOS X cartridge) takes a
whole bank's block with `Malloc` and reads the 149-byte fixture into it
at offset `$D4C0`, across `$D500-$D50F`.  The bytes must arrive and the
cartridge's bank must not move (the bridge's `CART_INFO`).  Without the
rule, the next call into SpartaDOS X never returns and the gate fails.
The same lines run on every other DOS, where they check only the bytes.

## What it saves

`make bench-boot`, phase C (from GEM.COM loaded to the desktop, where the
far copies are), on the Rapidus:

| | before | MVN |
|---|---|---|
| DOS 2.0S | 240 frames | 220 |
| G4DOS | 345 | 315 |
| SpartaDOS X | 520 | 485 |
| the cartridge | 380 | 335 |

The switcher's copies are the reason for it: a 6 KB near region is about
42,000 cycles each way with MVN and 240,000 with the loop, 2 ms against
12 ms on a Rapidus, 23 ms against 134 ms at 1.79 MHz.
