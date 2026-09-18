# SpartaDOS X relocatable 65C816 binaries — can gem4xe ship as one?

Asked 2026-09-18.  **Answer: not with the toolchain this tree uses.**  The
three blockers below are all properties of *Calypsi*, not of the 65C816
and not of SDX — which is a materially different statement from the one
this note first made, and the amendment at the end says why it matters.
What gem4xe *should* take from SDX 4.5x's 65C816 support is a different
thing entirely, and it is small — the section before that.

Everything below is read out of the **SpartaDOS X Programming Guide
v4.50** (`~/Documents/Atari/SDX/SDX450_Programming_Guide.pdf`, §2 and
§19), not from memory, and checked against what gem4xe and Calypsi
actually emit.

## What gem4xe emits today

| | format | who relocates it |
|---|---|---|
| `GEM.COM` | AtariDOS binary, `$FFFF` magic, `<start><end><data>` (`tools/mkxex.py`) | nobody; far banks travel as packed chunks and an `INITAD` copier puts them up |
| an application | gem4xe's own `.G4A`, magic `G4A` v3/v4 (`tools/mkg4a.py`) | gem4xe's loader, `src/sys/app.c`: near region by pages into the bank-`$00` pool, far region by banks |

`.G4A`'s fixups are **derived**, not declared: `mkg4a.py` links the
program three times — once at the placeholder addresses, once with the
near region a page up, once with the far region a bank up — and takes the
bytes that moved.  That exists because **Calypsi's linker emits no
relocations at all**.  Nothing in `src/` or `tools/` reads an SDX
relocatable block; the only `$FFFE`/`$FFF9` matches in the tree are 6502
CPU vectors, icon bitmap data and an Altirra patch.

## The format, as specified

SDX knows seven block types.  Beside the AtariDOS `$FFFF` segment and the
fixed-address `$FFFA` one:

    $FFFE  BSS allocation (control byte $80+index) or, with bit 7 clear,
           a position-independent block with data behind the header
    $FFFD  fix-ups for a position-independent block
    $FFFB  symbols required (XREF)      $FFFC  symbols defined (XDEF)
    $FFF9  extended relocatable block (65C816, §19.1.3.3): like $FFFE but
           the bytes to LOAD and the bytes to ALLOCATE are separate
           fields, so BSS can be declared in high RAM

A `$FFFD` fix-up stream is delta-encoded: each byte means *advance this
many bytes and fix up*, with `$FF` = advance 250, `$FE` = change target
block, `$FD` = jump to an absolute 16-bit position.  Fixing up **adds the
base block's load address to a two-byte word** at that position.

§19.1.3.2 adds the 65C816 rules.  The ones that matter here:

1. a block may not exceed **65535 bytes**, and a program at most 128
   blocks (so ~8 MB);
2. a block is guaranteed to load **entirely inside one 64 KB segment** —
   it never spans a bank;
3. **references inside a block must use SHORT (16-bit) addressing.**  A
   long absolute reference made within its own high-RAM block "would not
   be resolved properly";
4. references *into segment 0* from outside use 16-bit fix-ups;
5. references **between two blocks, neither in segment 0**, use 24-bit
   (three-byte) fix-ups and must use long addressing;
6. `runad` is 16-bit, so a program with high-RAM blocks must also load a
   segment-0 block, which gets control and `JSL`s upward.  (EXT816.SYS's
   `H_LOAD` lifts this one.)

And the caveat that governs all of it, §2.4:

> A fix-up byte always points to a two-byte word.  Therefore a position
> independent binary **may not contain a value of its internal address
> split into lower and higher order byte stored separately.**

## Why gem4xe cannot be built this way

Three blockers, in descending order of how fatal they are.  Rule 6 is
*not* among them: gem4xe already has exactly that shape, a bank-`$00`
entry that reaches far code, so it would cost nothing.

**1. Calypsi materialises addresses split, which §2.4 forbids outright.**
Under `--code-model=large` an address that becomes a *value* — taking
`&array`, building a far pointer, passing a callback — is loaded as two
separate immediates.  Observed in this tree's own generated code
(`options.c`, while chasing the far-pointer-difference bug):

        lda     ##.word0 (local_options+0x263)
        lda     ##.word2 (local_options+0x263)

That is precisely the `lda #<addr / ldx #>addr` construction the guide
rules out, and it is not rare or avoidable — it is how the compiler
represents a pointer constant.  A `$FFFD` fix-up cannot patch a split
pair; it only knows how to add to one contiguous word.

**2. Rule 3 inverts Calypsi's calling convention.**  SDX wants
intra-block references SHORT and inter-block references LONG.  Calypsi's
large code model compiles *every* call as `jsl long:target`, including
calls between functions in the same object and the same bank — that is
what the model means.  gem4xe's `farcode` is one contiguous region spread
over several banks (3–4 for the system, 6 for QED), with long references
criss-crossing it freely.  To satisfy SDX the compiler would have to know
which functions share a block and emit short references for those — a
code-generation feature Calypsi does not have and cannot be talked into
from the outside.

**3. Rule 1 conflicts with how the image is laid out.**  Blocks are
≤64 KB and bank-contained.  `ln65816` places sections across banks by the
`.scm` map; it does not partition an image into ≤64 KB units with the
internal/external discipline rules 3 and 5 require.  Re-cutting the image
into SDX blocks means re-cutting it in the linker, and then rule 2 still
has to hold for every one of them.

**The asymmetry worth naming.** `mkxex.py` and `mkg4a.py` work *because*
gem4xe owns both ends: it derives whatever fixups it likes and its own
loader applies them in whatever form it likes, including the split
three-byte bank fixups `.G4A` v4 carries.  SDX's loader has a fixed
vocabulary, and Calypsi's output is not in it.  Supporting `$FFF9` is
therefore not a packaging job like `mkxex.py` was — it is a compiler
requirement, and it lands outside this project.

## What is worth taking from SDX 4.5x instead

The genuinely useful part of §19 is not the file format but **memory
management**, and gem4xe has a real gap there.

Today `farmem_probe()` (`src/sys/farmem.c`) sizes high RAM by writing
each bank's number and reading it back, then `far_alloc()` hands banks out
of its own bump allocator.  gem4xe **claims** high RAM; it never asks who
else wants it.  It already reads `MEMLO` for bank `$00` (`src/sys/dos.c`),
so the low side is well behaved — the high side is not.

That has bitten once already.  `65816.SYS` loads at the *top* of high RAM
— `$EF0000` on a 16 MB Rapidus — and the probe's `$EF` write at `$EF0100`
landed in the driver's code; the SDX file calls it served then failed and
the desktop reported `DESKTOP.RSC` missing on a disk where every file was
present (`docs/phase41.md`).  The fix was to save and restore every byte
the probe writes, which it now does.  **That prevents corruption while
probing.  It does not prevent double-allocation afterwards**: if
`65816.SYS` ≥ 3.0 is loaded and anything has taken high RAM through
`MALLOC`, gem4xe will hand the same banks out again.

Two steps, either useful alone:

- **Bound the probe from `COMTAB2`** — `_816FLG` (+`$00`), `_SEGCNT`
  (−`$04`, count of extra 64 KB segments) and `_SEGBEG` (−`$05`, the first
  such segment).  Cheap, no driver required, and it replaces guessing the
  top of RAM with asking.  gem4xe reads none of these today.
- **Allocate through `MALLOC` memory index `$03`** when `65816.SYS` ≥ 3.0
  is present: `Y=0`, `X=$03` (or `$23` for 64 KB-aligned, which is what
  `far_alloc`'s bank-contained rule wants), size in `bytbuf`/`A`,
  attributes in `scan/attr`, answer in `addpos`.  A legacy call, so
  emulation mode.  Fall back to the probe when the driver is absent — which
  is the common case and must stay working.

Sizing: the `COMTAB2` read is an afternoon; the `MALLOC` path is a day or
two including a gate that boots with `65816.SYS` loaded and asserts
gem4xe does not overlap it.  Both are additive and neither changes the
file format.

## Amendment, the same day: the blockers are Calypsi's, not the machine's

Written first as "no, structurally", which was too strong.  Read the three
blockers again and every one of them is a sentence about **Calypsi**:

- it emits **no relocations at all** — which is precisely why
  `tools/mkg4a.py` has to link the program three times and diff the bytes
  that moved, and why `.G4A` carries fixup lists gem4xe derived itself;
- it materialises an address as **two immediates** (`##.word0` /
  `##.word2`), the construction §2.4 forbids;
- it lays sections across banks by the `.scm` map rather than cutting an
  image into ≤64 KB, bank-contained blocks with SDX's internal-short /
  external-long discipline.

None of that is true of the 65C816, and none of it is true of SDX.  It is
true of one compiler.

**And there is a 65C816 toolchain that does emit relocations: ORCA.**
ORCA/C (Byte Works; maintained now by Stephen Heumann, 2.2.0 covering
nearly all of C17) with the ORCA linker produces **OMF**, the Apple IIGS
object module format — a genuinely relocatable format with real
relocation records, for both 16-bit and 24-bit references, because the
IIGS loader places segments anywhere and fixes them up.  That is
structurally the same problem SDX's `$FFFD` fix-ups solve, and the same
information Calypsi denies us.  **Golden Gate** (Kelvin Sherlock) runs
ORCA/C and the linker as a cross-compiler on Linux, so this is reachable
from this machine rather than only from a IIGS.

What that does NOT mean is that OMF is SDX-compatible: SDX has its own
block types and its own rules (§19.1.3.2 still wants internal references
short and external ones long, and blocks bank-contained).  What it means
is that an **OMF -> `$FFFE`/`$FFFD`/`$FFF9` converter is a conceivable
tool**, the way `mkxex.py` converts ELF to `.xex`, because the relocation
information would exist to convert.  With Calypsi there is nothing to
convert from.

So the honest verdict is scoped, not absolute.

## Verdict

**Not with Calypsi**, and that is the whole of it: the benefit — letting
SDX place the image — is small for a system that switches to native mode
and takes the machine anyway, and the cost against this toolchain is a
compiler requirement rather than a packaging one.  Not recommended *now*.

It is worth keeping on the list of **things gem4xe wants from a 65C816 C
compiler**, beside the far-pointer defects this port has been paying for
all along (`tools/ccbug`, B1-B18, and the pointer-difference bug that made
QED need a source patch).  Relocatable output is a feature request with a
working precedent, not a wish.

The coexistence work in the section above — bounding the far-RAM probe
from `COMTAB2`, and allocating through `MALLOC` index `$03` when
`65816.SYS` is loaded — is the part of SDX 4.5x's 65C816 support gem4xe
actually wants, and it is worth doing on its own whatever the compiler.
