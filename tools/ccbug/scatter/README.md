# `.scatterTo28` on an Atari-shaped map — what it answers, and what will not parse

Measured 2026-09-19 against Calypsi **6502 5.18** — which is the NEWEST
6502 there is: 5.18.1 and 5.18.2 were 65816-only point releases, so the
symlink this tree's 65816 work follows does not apply here.  The closing
"not on the 65816" note is **as65816 5.18.2**.  For issue #89 (banked code
on the Atari 8-bit).  **This is not a bug report**: the operator does
what its documentation says.  It is the evidence behind the answer, kept
because the 6502 build is a decision this tree has not taken yet
(docs, "bank the applications") and this is what it would rest on.

    python3 validate.py                # re-derives every claim below

or by hand:

    as6502 -o bank_a.o bank_a.s        # one bankedcode section each,
    as6502 -o bank_b.o bank_b.s        # each too big to share an instance
    as6502 -o bank_c.o bank_c.s
    as6502 -o table.o  table.s
    ln6502 atari.scm bank_a.o bank_b.o bank_c.o table.o \
           -o scat.elf --list-file scat.map

`atari.scm` is the machine as it really is: ONE 16 KB window at `$4000`,
`scatter-to` a flat store above `$10000`.  The linker makes three
instances and says so:

    (scatter to 10000 in bankedRAM)
    (scatter to 14000 in bankedRAM)
    (scatter to 18000 in bankedRAM)

`table.s` puts `.word sym` beside `.long .scatterTo28 sym`.  Read back out
of the linked image:

| | runtime | `.scatterTo28` | `(storage - $10000) >> 14` |
|---|---|---|---|
| `far_a` | `$4000` | `$014000` | 1 |
| `far_b` | `$4000` | `$018000` | 2 |
| `far_c` | `$4000` | `$010000` | 0 |

All three run at the window base; the storage address names the bank.
That is everything a PORTB trampoline needs.

**Taking a byte of it.**  Two different answers, and the difference
matters — the first version of this file got it wrong and said everything
was a parse error, because the harness that produced it had lost its
INDENTATION, so the assembler was reading `.byte` as a label and
answering "illegal symbol syntax" to every line.

In a DATA DIRECTIVE, only `.long` is accepted:

    OK      .byte .byte2 far_a            (an ordinary symbol: fine)
    OK      .long .scatterTo28 far_a
    reject  .byte .byte2  .scatterTo28 far_a
    reject  .byte .byte2 (.scatterTo28 far_a)
    reject  .word .word2  .scatterTo28 far_a

In an INSTRUCTION OPERAND it assembles — and then the linker dies:

    as6502  lda #.byte2 (.scatterTo28 far_a)    accepted
    ln6502  internal error: relocation pattern size mismatch

for `.byte0`, `.byte1`, `.byte2`, `.byte3` and for a bare
`lda #.scatterTo28 far_a`.  `lda #.byte2 far_a` — the same shape without
the operator — links cleanly against the same objects and the same map,
which is the control.

So the bank can only be reached through a four-byte table the trampoline
indexes, and `lda #<bank of foo>` at a call site cannot be linked.

**Not on the 65816.**  `as65816` rejects `.scatterTo28` and the 65816
guide does not mention it.  gem4xe's own build needs none of this — it
has real 24-bit addressing — so this matters only to a 6502 port.

**Two roots, on purpose.**  `bankedcode` and `code` are declared `root`
here because nothing calls them; without that the linker dead-strips the
lot and the map shows an empty placement, which reads like a broken
script rather than an empty program.  The first run of this test lost
half an hour to it.
