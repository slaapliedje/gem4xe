# tools/ccbug — the cc65816 bugs gem4xe works around

Eighteen defects in Calypsi cc65816, seventeen found against **5.18**
here and one (B17) reported from another project — twelve in
code generation, two crashes, one compile that never finishes (B18), one
in the front end's arithmetic and one in the run-time library's division
— each reproduced from a shape
lifted out of gem4xe or out of the vendor's own C library, each with the
shape the sources use instead.

**Four are fixed upstream and the tree now builds with 5.18.2**, which is
what `~/dev/toolchains/calypsi-65816` points at: both **B5** shapes,
**B13**, **B14** and **B15** are gone (B15 and B5 in 5.18.1, B13 and B14
in 5.18.2, after upstream issue #88).  **B1 is NOT fixed** -- it read as
fixed for a day because the reproducer hid it; see its entry.  `check-cc` reports them as
`FIXED upstream` and keeps running their workaround shapes, because the
README promises "Calypsi 5.18+" and anyone still on 5.18 must get right
answers.  The workarounds stay in the sources for the same reason. `make check-cc` builds `bugs.c` with the
vendor's minimal linker script and C library, runs it under `db65816`, and
reads the results back; `b6.c` and `b11.c`, which the compiler cannot get
through, are compiled on their own and the outcome read from the compiler,
and `b16.c`, whose output cannot be run, is compiled on its own and its
listing read:

    make check-cc
      B1 stack array element + operand           want   476 got   376   still present
      B1 through a scalar                        want   476 got   476   ok
      ...
      B6 indexed direct-page array                       compiles   still present
      B11 near <-> far struct copy over 8 bytes          compiles   still present
      B16 byte spin loop, rep before its back edge         compiles   still present
    check-cc: PASSED -- every workaround shape is right; 16 of 20 bug shapes still present

The run **fails only if a workaround shape stops compiling right**, because
that is what would break gem4xe. A bug that has gone away is reported as
`FIXED upstream`, which is the cue to remove its workaround. `make test`
includes it.

A second project's ledger is summarised at the end — **MicroPython on the
SNES**, 23 findings against 5.17, filed upstream as Calypsi #86. It is their
evidence, kept separate from the numbered entries for that reason. **Nearly
all of it was fixed in 5.18**, so for this tree it is history rather than a
hazard list; it is kept for the shapes, and for what it says about how
quickly the vendor answers a well-made report.

Every one of these was first seen as a wrong pixel or a wrong returned value
in the conformance suites, then proved by reading the emitted assembly and
finally by the simulator. Phase 6's lesson still applies: a bug that moves
with the code layout is self-corruption until proven otherwise, and every
bug below was proved.

## Which `-O` levels each one needs

Measured on 5.18.2 by running the whole file at each level
(`python3 tools/ccbug/check.py -O 0|1|2`).  A bug that reproduces at every
level is a plain code-generation fault; one that needs `-O1` or `-O2` is
an optimiser fault, and saying which saves a vendor a bisect.

| | -O0 | -O1 | -O2 | note |
|---|---|---|---|---|
| B1 | yes | yes | yes | at every level once the shape is not inlined away |
| B2 | no | no | yes | the entry used to say "-O1 and above"; not on 5.18.2 |
| B3 | no | yes | yes | it is a defect OF inlining |
| B4 | yes | yes | yes | |
| B6 | yes | yes | yes | internal error, every data model too |
| B7 | yes | yes | yes | front end, not the code generator |
| B8 | no | no | yes | |
| B9 | yes | yes | yes | not an inliner fault: -O0 has a real `jsl` |
| B10 | no | yes | yes | a defect OF inlining |
| B11 | yes | yes | yes | internal error |
| B12 | yes | yes | yes | |
| B16 | no | no | yes | |
| B18 | no | yes | yes | the compiler never finishes; `--data-model=large` is clean at every level |
| B19 | yes | yes | yes | the same instruction in both data models; a defect only where the symbol is far |

`--no-inline` is a useful second axis: it clears B3 and B10, which is
expected, and it must NOT clear anything else.  It was `--no-inline` that
exposed B1's reproducer as lying.

## The rules

What the sources do, in one line each. The reasons follow.

1. **Never `stackarray[var] + operand` in one expression.** Read the element
   into a scalar first.
2. **Never trust the flags after `/` or `%`.** The build links
   `src/sys/div16.s` with `--override _Div16 --override _Mod16`; without it,
   `if (a / b)` and `a % b == 0` are wrong.
3. **Never `*out = c ? a : b` in a `static` function.** Return the value.
4. **Never `(int8_t)` an expression derived from a 32-bit value.** Go through
   a `WORD` (or `int8_t`) local.
5. **Never shift, double, increment or decrement a 16-bit load through a
   local pointer in the same expression.** `wd = p->field; stride = wd * 2;`,
   not `stride = p->field * 2;`; `len = p->len; n = len - 1;`, not
   `n = p->len - 1;`.
6. **Never index an array that lives in the direct page.** Direct-page
   scalars and direct-page *pointers* are fine (`__attribute__((tiny))`,
   not the `__tiny` keyword, on a pointer declarator); tables stay
   ordinary statics and are indexed by a direct-page scalar.
7. **Never `sizeof` a struct where an integer constant expression is
   required** — an enum, an array bound, `_Static_assert`. It is padded
   there and not in the code. Write the byte count out (`BCB_SIZE`).
8. **Never narrow arithmetic into a `char` local on one path of a
   conditional and store the local after the join.** Hold the character
   in a `WORD` and narrow it once, at the store.
9. **Never `got = c ? a : b` on a local whose address another path passes
   to a call.** Test the condition, `break` or return on it, then assign
   plainly.
10. **Never clamp a parameter back into itself in a `static` function.**
    `WORD cx = gx > n ? n : gx;` into a fresh local, then use `cx`.
11. **Never assign a struct of more than 8 bytes between a near object and
    a far one.** Copy it byte by byte (`fn_copy`, src/desk/deskwin.c), or
    keep both sides far — far-to-far copies of any size compile.
12. **Never right-shift a signed 16-bit value.** Shift an unsigned copy
    (`(UWORD)v >> n`) when it cannot be negative, and use `asr()`
    (src/vdi/vdi.c) when it can. A shift by one emits a plain `lsr`, which
    is right only for a non-negative value; by more than one the value is
    mangled outright, positive or negative.
13. **Never combine two elements of the same array in one expression**
    when either index is computed. `q = pt[j]; dx = pt[0] - q;`, not
    `dx = pt[0] - pt[i * inc * 2];` — B1 again, and it reaches pointer
    parameters, not only stack arrays.
14. **Never index an array from a pointer into its middle with a
    negative index.** Pass the base and an index, so that every subscript
    is non-negative: `draw_arrow(pt, n, (n-1)*2, -1)`, not
    `draw_arrow(&pt[(n-1)*2], n, -1)` with `pt[-2]` inside.
15. **Never write `P->a = P->b OP e` (or `P[i] = P[j] OP e`) through a
    near pointer.** `s = P->b; P->a = (WORD)(s OP e);` -- the member on
    the left of the operator goes through a scalar. Rules 1 and 13 are
    this rule's two earlier sightings; this is the exact trigger, and it
    is what breaks `fdopen` in the vendor's own C library.
16. **Never spin on a byte.** A poll such as `while (VCOUNT < line) ;`
    reads the byte into a word first -- `while (vcount() < line) ;` with
    `static uint16_t vcount(void) { return VCOUNT; }` -- so that the
    compare is a 16-bit one. At -O2 the byte compare's width switch can
    land before the loop's back edge, and the second pass runs 8-bit code
    as 16-bit.
17. **Never `dst[n++] = (uint8_t)*s++` through a FAR pointer in a loop.**
    Read the byte into a local first (`char c = *s++; ... (uint8_t)c`),
    or index (`s[n]`), or drop the cast. With the cast, the increment and
    the far read in one expression the compiler never finishes -- it is
    not a wrong answer but no answer, and `make` is what gets killed.

## B1 — stack-array element plus operand compiles to a load

    x[d] = x[d-1] + tree[t].ob_x;       /* everyobj(), src/aes/objc.c */

emits `ldy ob_x; lda (&x[d-1]),y`: the operand becomes an *index* and the
element's address is *dereferenced* — a load from `&x[d-1] + ob_x`, not an
add. All `-O` levels. Only stack arrays; a global array or a scalar temporary
is fine.

    prev = x[d-1];  x[d] = prev + tree[t].ob_x;

Found by `make test-m4`: every child object was drawn at its parent's x plus
garbage.

**THIS ENTRY READ AS "FIXED UPSTREAM" FOR A DAY, AND THE REPRODUCER WAS AT
FAULT.**  `b1_bug` was `static` and called with literal arguments, so from
-O1 up it is inlined, `depth` constant-folds, the indexed shape never
arises and the row reports the right answer.  5.18.1's real fixes (B5,
B15) were in the same release, so B1 went into an upstream comment as
fixed alongside them.  It is not fixed: give the function external
linkage, or compile with `--no-inline`, and it fails at every `-O` level
on 5.18.2.  `bugs.c` now declares both shapes `extern` for that reason.

The discriminator, which has no uninitialised memory and carries its own
control, is the version to send upstream:

    WORD x[12], i;  for (i = 0; i < 12; i++) x[i] = 1000 + i;
    x[depth] = x[depth - 1] + t[this].ob_x;     /* ob_x = 4, depth = 1 */

`x[0] + 4` is 1004; the stack array answers **1002**, which is `x[2]` --
`ob_x` used as a byte index.  The same function with a *global* array
answers 1004, and the two sit in one `-O2` listing as `ldy 16,x / lda
(.tiny _Dp),y` against `lda 16,x / clc / adc g,x`.

## B2 — `_Div16` / `_Mod16` return with the wrong flags

Not the compiler alone: a mismatch between it and its library. At `-O2`
`if (a / b)` compiles to `jsl _Div16; beq`, relying on the callee to
leave N and Z from the result. The library's `_DivModSign16`
(`src/lib/lowlevel/integer.s`) ends `plx; bpl; rtl` on the non-negative path,
so the flags describe the **sign word** (dividend ^ divisor), not the
quotient. Hence `8 / 8` tests as zero and `7 / 8` as non-zero; `_Mod16` tests
the dividend, so `a % b == 0` is false for every **positive** non-zero `a`
(a negative dividend takes the library's `inc a` path and the flags come
out right).

**THE COMPILER DISAGREES WITH ITSELF, and that is the way to report it.**
At `-O0` and `-O1` the same call is followed by `inc a; dec a`, which
regenerates N and Z from the returned value — the compiler assuming the
helper's flags mean nothing. At `-O2` that pair is deleted and the branch
takes the callee's flags. One of the two is wrong whatever the intended
contract, and neither `assembly-interface.html` nor `efficient-coding.html`
documents a condition-code contract for the runtime helpers.

**-O2 only.** An earlier version of this entry, the comment in
`src/sys/div16.s`, and the comment on the reproducer in `bugs.c` all said
"-O1 and above". They were wrong. The sweep fixed the first; the other two
were found later, by asking what a stale background job from that day had
been measuring — a reminder that correcting the catalogue is not the same
as correcting every place the claim was written down.

**An earlier version also claimed "over 365 test pairs the library's flags
are right 236 times".  No such sweep has ever existed in this repository**
— `check-cc` tests three rows, and no version of `check.py` in the history
sweeps anything. The number was unsupported from the day it was written and
is removed rather than reconstructed. If a figure is wanted, measure one.

`src/sys/div16.s` is a replacement that computes the result and then loads it
(`tay; tya`) so the flags are its own. It is linked with
`ln65816 --override _Div16 --override _Mod16`, which treats the archive's
symbols as weak. `check-cc` links `bugs.c` both ways and requires the
override to make all three B2 rows right.

Found by `make test-m4`: `gsx_tcalc` decided no line of text fitted a field
exactly one line high, so no G_TEXT / G_FTEXT / G_BOXTEXT ever drew.

## B3 — `*out = c ? a : b` in an inlined static function stores nowhere

    static void callee(..., WORD *pn) { *pn = (n < m) ? n : m; }

once inlined at `-O1`+, stores the conditional into a dead stack slot; the
caller's variable is never written and reads whatever it held. If/else with
two plain stores is fine, an `extern` callee is fine, returning the value is
fine.

    static WORD callee(...) { return (n < m) ? n : m; }

Found by `make test-m4`, in the same `gsx_tcalc` as B2: the character count
came back as uninitialised stack.

**Send the sentinel version upstream, not this one.**  `num` here is an
uninitialised local whose address is taken, and although the callee writes
it unconditionally — so there is no undefined behaviour — a vendor reading
it will reach for "uninitialised variable" first.  Give it a value the
correct answer cannot be:

    WORD num = 23117;                     /* 0x5A4D */
    b3_bug_callee(s, pw, &num);
    return num;                           /* must be 7 */

It returns **0** at -O1 and -O2: neither the right answer nor the
sentinel, so a definite, unconditional store was dropped and there is
nothing indeterminate left to blame.

## B4 — a narrowed operand loses its `(int8_t)` sign extension

    th = (WORD)(int8_t)((spec >> 16) & 0xFF);     /* ob_sst(), spec is uint32_t */

The cast is dropped and the byte is zero-extended, at all `-O` levels.

**THE TRIGGER IS NOT "A 32-BIT VALUE", though this entry said so for
months.**  It is an operand the compiler has already narrowed, and 16 bits
are enough:

    short narrow(unsigned short x)  { return (short)(signed char)(x & 0xFF); }

compiles to `and ##255 / rtl` — the sign extension simply absent, with no
32-bit value anywhere in the function.  Swept: `& 0xFF`, `% 256u` and a
32-bit `>> 16` all lose it; a plain value, an `| 0x00`, a *signed* operand,
a `(uint8_t)` cast and an intermediate 16-bit local all keep it.  A vendor
given the "32-bit" recipe would try a 16-bit control, see it fail too, and
stop trusting the description.

**And the 32-bit form drops the TRUNCATION as well**, which no conversion
rule permits and which is the case to lead with, because it needs no
argument about implementation-defined conversions:

    short narrow32(unsigned long x) { return (short)(signed char)(x >> 16); }

`narrow32(0x12341100)` must be `(int8_t)0x34` = 52.  It returns **4660**
(`0x1234`) — a value outside `int8_t`'s range entirely, so the conversion
was not performed at all rather than performed differently.  Prefer that
to the 254 case, where a vendor can retreat to C17 6.3.1.3p3 and call an
out-of-range conversion implementation-defined.

A `WORD` local in between restores it:

    WORD hi = (WORD)(spec >> 16);  int8_t sth = (int8_t)hi;  th = sth;

Found by `make test-m4`: the outward-border case, where a thickness of -2
became 254 and painted a black band the height of the object.

## B5 — a shifted load through a spilled pointer drops the load

    stride = (uint16_t)((uint16_t)src->fd_wdwidth * 2u);   /* vrt_cpyfm() */

with `src` a local that has been spilled to the stack (a call preceded it) and
is **dead after this line**: the compiler gives `stride` the pointer's own
slot and emits

    tsc ; clc ; adc ##slot ; tax ; asl 0,x

— the slot shifted in place. `stride` becomes `src << 1` and `fd_wdwidth` is
never read. Every shift-shaped operator does it (`* 2`, `<< 1`, `x + x`,
`* 4`, `/ 2u`, `>> 1`); `* 3` does not, a byte field does not, a global or
parameter pointer does not, and a pointer that is still live afterwards does
not. All `-O` levels.

    wd = src->fd_wdwidth;  stride = (uint16_t)((uint16_t)wd * 2u);

This is the Phase 2b "unexplained codegen difference": with `sy1 == 0` row 0
of the source read correctly (`0 * garbage`) and every later row read
unrelated memory. Switching to an incrementing pointer happened to change the
slot allocation so `stride` no longer landed on `src`. It is root-caused now
— `docs/phase2b.md` is updated — and `check-cc` pins it.

**A decrement does it too, and the same rule covers it.** Phase 14's
`inf_numset` wrote `WORD i = (WORD)(ted->te_txtlen - 1);` and got `dec 0,x`
on the pointer's slot: `i` became the TEDINFO's *address* less one, and the
loop that filled the field with spaces filled 25 KB of bank $00 instead —
through `$D0xx`, where any write soft-resets VBXE, and through POKEY's
`IRQEN`, which left an interrupt nothing could acknowledge. A whole machine
frozen by one dropped load. `len = ted->te_txtlen; i = (WORD)(len - 1);`
compiles right; `docs/phase14.md` has the account.

`- 1` does it too, as `dec 0,x` on the slot: `n = ted->te_txtlen - 1` in
`inf_sset()` (src/aes/fsel.c), with `ted` a call's return dead after the
line, made `n` the TEDINFO's address less one — negative in bank 0 above
`$8000` — so the loop copied nothing and every field of the file selector
came up empty.  `-O2`.  Found by `make test-m12`: the target's selector
showed templates with no text where the model showed the path and the
names; `check-cc` pins this shape as well (`B5 spilled pointer, field - 1`).

## B6 — an indexed direct-page array is an internal compiler error

    static __attribute__((tiny)) uint8_t tbl[4];
    static __attribute__((tiny)) int i;
    uint8_t f(void) { return tbl[i]; }

    internal error: Translator/Target/WDC65816/Compiler/CGHelpers.hs:
    (661,1)-(662,59): Non-exhaustive patterns in function mem8Reg

(The span was `(662,1)-(663,59)` on 5.18; check it against the compiler in
use before quoting it upstream.)

**The array is incidental.** The trigger is any variable-address load or
store in the tiny address space, and the smallest form has no array in it
at all:

    __tiny char x;  char f(int i) { return *(&x + i); }      /* same ICE */

so the one-line reproducer to send is `__tiny char a[1]; char f(int i) {
return a[i]; }`.  Element width is irrelevant, which makes the name
`mem8Reg` a red herring: a 32-bit element hits the same pattern match.
Index type and index source are irrelevant, loads and stores both crash,
and it is every `-O` level and every data model.  What does NOT crash
localises it usefully for the vendor: `&tbl[i]` with no dereference
compiles, and `a[i];` with the value discarded compiles, so the failure is
in selecting the load or store rather than in the address arithmetic.  A
constant index compiles. Direct-page scalars and
direct-page pointers (`lda (.tiny p)`, `sta (.tiny p)`, `inc dp:.tiny p`)
are what the fast loops want anyway, and an ordinary array indexed by a
direct-page scalar is one instruction (`ldx dp:.tiny i; lda tbl,x`), so the
sources keep every table out of the direct page.

Two things next to it that are not bugs: the `__tiny` *keyword* on a
pointer declarator (`uint8_t * __tiny p;`) is rejected with
"expected identifier or '('", and the guide says to use
`__attribute__((tiny))` where the keyword form is refused; and
`--assembly-source` is the only way to see what a loop compiled to,
since there is no per-function optimisation pragma.

Found in Phase 8c while moving the line stepper's state into the direct
page (`docs/phase8c.md`).

## B7 — `sizeof` a struct is padded where a constant expression is required

    typedef struct { uint16_t a; uint8_t b; uint16_t c; } S;   /* laid out in 5 bytes */
    enum { STRIDE = sizeof(S) };                                /* 6 */

The code generator lays a struct out with no padding — a 16-bit member
sits at an odd offset if that is where it falls, the 65816 having no
alignment rule — and `sizeof(S)` in an ordinary expression is 5, `S x[2]`
is 10 bytes and `x[1].c` is read at offset 8. But where the language
requires an integer constant expression — an enum, an array bound,
`_Static_assert` — `sizeof(S)` is evaluated with 16-bit members aligned to
2 and is 6. `char buf[sizeof(S)]` merely over-allocates; a stride or an
offset taken from such a constant reads the wrong bytes, and
`_Static_assert(sizeof(S) == 5)` fails on a struct that *is* 5 bytes,
which is how this was found: the BCB overlay in `src/vbxe/vbxe.c` was
given exactly that assertion as a guard. All `-O` levels.

The sources write the byte count out where a constant is needed
(`BCB_SIZE`).  It is checked two independent ways, because one way is
what let this bug bite the project a second time: `check-cc` reads
element 1 of a three-element array through both strides -- a RUN, in the
simulator -- and compiles `b7_bound.c`, which asks for the true size in
an array bound and must be REFUSED.  The day that file compiles, the bug
is gone.

**It bit this project again on 2026-09-16, with rule 7 already written
above.**  `ICONBLK` is 34 bytes (three LONGs and eleven WORDs) and the
array-bound idiom answers 36, so the resource loader's table strides were
read as a live defect, a commit said so, and a peer was told the fix
mattered to their port.  It did not: the loader was correct, and every
gate passed either way for that reason.  What settled it was the target
-- MControl's own resource, 22 colour icons, loaded on the machine with
every record matching the file at a stride of 50, which is 34 + 12 + 4.
Note HOW the idiom fails, because that is what made it convincing: **it
refuses the TRUE value**, so it reads as a failed assertion about the
code rather than a broken instrument.

**Rule 7, in the form that would have prevented both:** measure a struct
by asking the GENERATED CODE -- a function that returns `sizeof(X)`, read
out of `--assembly-source` -- and never an array bound, an enum or a
static assertion.  (`&arr[1] - &arr[0]` is the other obvious way and is
not available: this compiler answers a pointer difference between struct
members with `internal error: ScaleIndex.hs`.)  `tests/host/test_sdk.py`
measures that way, and the tree carries no array-bound use of `sizeof` at
all -- the four floors that briefly guarded the resource loader were
removed, because a floor can only give a false pass and a rule-breaking
construct in the sources is one the next reader copies.

## B8 — a byte local narrowed on one path is stored from 8-bit mode

    char c = *name;
    if (c >= 'a' && c <= 'z')
        c = (char)(c - 0x20);       /* sh_cioname(), src/aes/shel.c */
    out[k] = c;

The taken path does the subtraction in 16 bits, drops to an 8-bit
accumulator to store the byte local, and falls through into the join with
the mode still 8-bit; the untaken path arrives in 16-bit mode. The join
loads the destination *pointer* for `out[k] = c` with `lda`, `tay` — an
8-bit load now, so Y gets half an address and the byte goes to page zero
while `out[k]` keeps whatever it held. `-O2` only; an `unsigned char`
local is the same shape and the same bug, and so is a `static char
to_upper(char)` once it is inlined into the store. Found by
`tests/emu/m12_file.py`: `sh_cioname("test.rsc")` gave `\xEEEST.RSC` —
the first lowercase letter of a name vanished, uppercase names were fine —
and the simulator reproduced it from the function alone.

The sources hold the character in a `WORD` and narrow it once, at the
store; `check-cc` folds `"test"` both ways and reads the first byte.

## The simulator recipe

Everything here is built and run the way `check.py` does it:

    cc65816 -g --code-model=large --data-model=small -O2 -o x.o x.c
    ln65816 -g $CALYPSI/example/minimal/linker.scm x.o -o x.elf clib-lc-sd.a \
            --rtattr exit=simplified [div16.o --override _Div16 --override _Mod16]
    db65816 --nh --nx --exit-breakpoint x.elf      # then, over STDIN:
        run
        ... wait for the line containing SIGSTP ...
        print r_b1_bug
        quit

Two things cost an afternoon each:

- **`db65816 -e run -e print x` races the program.** Batch commands are
  executed before `run` has finished, so `print` shows the pre-run value —
  zeros — and it gets worse with longer programs. Drive the debugger over
  stdin and read lines until `SIGSTP` before printing anything.
- **`cc65816 --assembly-source FILE` writes the assembly and then does not
  write the `.o`.** Compile twice when both are wanted.

Array variables print as `[i] = v` lines; scalars as `$n = v`. Merge stderr
into stdout before parsing, the two interleave.

## Reporting upstream

Each bug has a self-contained reproducer in `bugs.c`, and the characterisation
matrices above say what does and does not trigger it. They have not been sent
to Calypsi; that is the user's call. When a release fixes one, `check-cc`
says so, and the workaround — and for B2 `src/sys/div16.s` plus the two
`--override` flags in the Makefile — can go.

## B9 — a conditional assignment to an address-taken local is dropped

    if (write) { st = cio_write(iocb, p, m); got = ok ? m : 0; }
    else       { st = cio_read(iocb, p, m, &got); }     /* gd_xfer(), src/sys/gemdos.c */

The read path hands `&got` to a callee, so `got` has a stack slot.  The
write path's conditional is evaluated into a scratch slot (`sta 1,s`) and
never copied to that slot; instead the join loads `got` from an unrelated
slot (`lda 15,s; sta 26,s`), and the bytes-moved total that Fwrite returns
is whatever was there — 770 on the target, 259 in the simulator for a
20-byte write.  Sibling of B3 (the conditional store into a dead slot), on
a local rather than through a pointer.  -O2.  `gd_xfer` tests the status,
breaks on failure, and assigns `got = m` on the line after.

## B10 — parameters clamped in place are read from an unwritten slot

    static void snap_icon(WORD gx, WORD gy, WORD *px, WORD *py)
    {
        ...
        if (gx > columns - 1) gx = columns - 1;
        if (gy > rows - 1)    gy = rows - 1;
        *px = gx * icw + spare / columns;                /* src/desk/desktop.c */
        *py = gy * ich + spare / rows + desk.y;
    }

Inlined into its caller at `-O2`, the two parameters are parked at `1,s`
and `3,s` and the clamps store there — the second one to `1,s`, which is
the wrong parameter, though that is the smaller error — and then every
product that follows loads *both* parameters from `5,s`, a slot nothing in
the function ever wrote (`lda 5,s; ldx icw; jsl _Mul16`).  The result is
whatever the last call left on the stack: the first desk icon landed at
(0, 11) because that slot was zero, the second at (31744, 3595) and the
trash at (21844, -8027), off the screen.  Sibling of B3 and B9: a value
assigned on one path of a conditional, then fetched from the wrong slot at
the join.  Clamping into fresh locals (`cx`, `cy`) and leaving the
parameters alone compiles right.

Found by hand-running the desktop (milestone 4, `docs/phase14.md`) and
dumping its screen tree: two of three icons at impossible coordinates, the
first one right.

**A REPRODUCER FOR THIS MUST HAVE EXACTLY ONE CALL SITE.**  Add a second
or third caller as a probe and the `static` function stops being inlined,
the bug vanishes, and a vendor reading that file will correctly report
that it does not reproduce.  Reduced to its condition: a `static` function
that assigns to one of its own parameters under an `if`, inlined into its
single caller, reads that parameter from a stack slot the function never
writes.  One clamped parameter is enough; deleting the clamps removes it;
and the read is unconditional, so it is wrong even when the clamp is not
taken.

## B11 — a near ↔ far struct copy over 8 bytes is an internal compiler error

    FNODE __far *pf;  FNODE fn;          /* pn_active(), src/desk/deskwin.c */
    *pf = fn;

    internal error: labeling failed

**Any two DIFFERENT address spaces**, not only near and far: tiny to far,
tiny to near and near to far24 all fail the same way, in either direction,
at every `-O` level.  Near-to-near and far-to-far compile at any size.
The 8/9 boundary is exact: a struct of up to 8 bytes is copied through the
registers and compiles, and from 9 bytes up it is a block move the back
end cannot label.  A `union` of the same size fails identically.

**The data model claim needs care, and it is a trap for anyone
reproducing it.**  Written as above, with an unqualified pointer on the
near side, the file only fails under `--data-model=small`: in medium and
large the default pointer is already 24 bits, so the copy has degenerated
into far-to-far and compiles.  With an explicit `__near` on one side it
fails in all three.  A vendor who tries the reproducer under a non-default
data model will otherwise report that it does not reproduce.

The error text carries **no internal source location** — no file, no line,
no function — unlike B6's, which is worth saying when reporting it: it is
the one thing that would make this cheap to fix. Near-to-near and far-to-far copies of any size compile, so
the listing's insertion sort slides FNODEs with `*pf = *(pf - 1)` (far to
far) and puts the new one in through a byte loop.

Found in Phase 14, milestone 5, as the first compile of the folder windows
failed at once; bisected to the one statement with a delta-minimiser (the
three-function "minimal failing set" it first reported was an artefact of
unused statics being dropped: the function alone, `static` and unreferenced,
compiles because it is never translated).


## B12 — a signed 16-bit `>>` is not an arithmetic shift

    UWORD i = angle >> 3;               /* Isin(), src/vdi/vdi.c */

emits three logical shifts and then a sign extension **from the wrong bit** --
`eor ##4 / and ##7 / sec / sbc ##4`, which keeps three bits and discards the
rest. So `900 >> 3` is 0 rather than 112, and `900 >> 4` is **-8** rather
than 56, which is the fact to lead with: a non-negative operand cannot
yield a negative result under any conforming implementation, so there is no
implementation-defined escape hatch to argue about.

**The mask is computed from the wrong number.** The idiom is
`eor ##(1<<(n-1)) / and ##((1<<n)-1) / sec / sbc ##(1<<(n-1))`, which
sign-extends an *n*-bit field.  For a 16-bit `a >> n` the field is
`16-n` bits wide, so the constants must come from `16-n`.  They coincide
only at **n == 8**, which is exactly where the compiler is right.

So the rule is narrower than "a signed 16-bit shift": it is a **constant**
shift count of **3 or more, other than 8**, on a **16-bit signed** value.
Correct, and checked on 5.18.2: `>>1` and `>>2` (`cmp ##-32768 / ror a`,
a real arithmetic shift), `>>8` (`xba / eor ##128 / and ##255 ...`),
variable shift counts, unsigned shifts and 32-bit shifts.

**An earlier version of this entry said a shift by one emits a plain `lsr`.
It does not, and reporting that would have had the vendor test `>>1`, see
it pass and close the ticket.**  Keep `-900 >> 3` out of the report too:
right-shifting a negative value is implementation-defined, and the bug does
not need it.

    static WORD asr(WORD v, WORD n)     /* src/vdi/vdi.c */
    {
        if (v >= 0)
            return (WORD)((UWORD)v >> n);
        return (WORD)(-(WORD)(((UWORD)(-v) + (UWORD)((1u << n) - 1u)) >> n));
    }

Found by `make test-m3`: every GDP curve -- circle, ellipse, arc, pie --
drew nothing at all, because `Isin` returned `sin_tbl[0]` for every angle
and each point of the curve landed on its centre.  A sweep of the whole
tree's generated assembly for the broken idiom found no other site.


## B13 and B14 — an arrowhead's two ends

    dx = pt[0] - pt[i * inc * 2];       /* draw_arrow(), src/vdi/vdi.c */

reads the second element as **zero**. It is B1's shape reaching further
than B1 says: through a pointer parameter rather than a stack array, and
with a product of two variables as the index. Neither the index
arithmetic on its own nor the subtraction on its own is wrong -- lifted
into a small test program with the same types, the same expression
compiles correctly -- so this, like B12, is checked by running it rather
than by reading a listing.

    WORD j = (WORD)(i * inc * 2), q = pt[j];
    dx = (WORD)(pt[0] - q);

The head at the OTHER end of the line was wrong for a second reason.  The
donor reaches it with a pointer into the middle of the array and walks
backwards:

    draw_arrow(vwk, point+count-1, count, -1);      /* pt[-2] inside */

and compiled here `pt[-2]` reads neither point -- it came back as -8417
for a coordinate that is 48.  The sources pass the base and the tip's
INDEX, so every subscript inside is non-negative.

Neither shape reproduces on its own: lifted into a small function with
the same types, both compile correctly, and `bugs.c` therefore carries
the whole calculation -- the square root, the rounding and the loop -- to
get the same register pressure.  That is also why neither could have been
found by reading a listing.

Found by `make test-m3`: every arrowhead `vsl_ends` drew pointed at the
origin (B13), and the one at the far end of the line pointed off the
screen (B14).


## B15 — `p->a = p->b OP e` through a spilled pointer is `p->a OP= e`

    stream->fs_bufend = &stream->fs_bufstart[BUFSIZ];   /* __fs_fdopen(), clib */

with `stream` a near pointer that lives on the stack (a call preceded it)
compiles to

    ldy ##fs_bufend ; lda ##64 ; clc ; adc (slot,s),y ; sta (slot,s),y

— the load is done at the **destination's** offset. `fs_bufend` becomes
whatever it was plus 64 and `fs_bufstart` is never read, so any `fwrite`
or `fread` longer than 64 bytes runs off the end of the buffer and into
the heap. Found in the Calypsi-65816-Atari board support package, whose
`readwrite` test wrote 256 bytes and smashed the heap; it links
its own `fdopen.c` ahead of `clib-*.a` and `docs/cc65816-bug.md` there
carries the account.

The trigger is exact, from four characterisation matrices: the right-hand
side, after any casts and parentheses, is **one binary operation whose
left operand is another member or element of the same pointer**.

- Operators: `+ - & | ^ <<` and a signed `>>` (`ror n,x`); `+ 1` and
  `- 1` become `inc n,x` / `dec n,x` on the destination, `* 2` an
  `asl n,x`.
- Any element width — `char`, `WORD`, `long` (`adc ##64; sta 8,x; adc
  ##0; sta 10,x`).
- A variable index on either side is ignored: `p[n] = p[1] + 64` and
  `p[2] = p[n] + 64` are both wrong.
- The right operand can be a constant, a global, a parameter, another
  member or a `_Mul16` product; a `(WORD)` cast round the whole
  right-hand side changes nothing; two such statements in a row are both
  wrong.
- Not triggered: the member on the **right** of a non-commutative
  operator (`k - p->y`, `-p[1]`); more than one operator at the top level
  (`(p->y + k) + m`, `p->y * 2 + k`, `(p->y + k) >> 1`); a call or a
  `_Div16` between the load and the store (`p[1] - g()`, `p[1] / 2`,
  `p[1] * 3`); a cast on the left operand (`(UWORD)p->y >> 1`); a
  compound assignment (`p[2] += p[1]`, which is what the compiler thinks
  it was given); a global pointer, a `__far` pointer, a pointer that is
  still in X because no call spilled it, or an alias (`q = p; q->x =
  p->y + k`).

B1 (a stack array, `x[d] = x[d-1] + ...`), B13 (a pointer parameter with
a computed index) and B5 (the shift or decrement done in place on a dead
pointer's slot) are earlier faces of the same defect. A scan of gem4xe's
tree for the shape — every `P->a = P->b OP e` and `P[i] = P[j] OP e` whose
left operand's root differs from the destination's member — found no
instance left; the one candidate, a global struct in `src/desk/desktop.c`,
compiles right, and its listing was read to be sure.

`bugs.c` gets the spill with a callee that loops — a one-line callee is
inlined at -O2, the pointer never leaves X, and the statement compiles
correctly, which is also why a minimal reproducer so easily misses it.

## B16 — a byte spin loop's width switch lands before its back edge

    if (p) return 0;
    while (VCOUNT >= 19) ;      /* the frame's wrap */
    while (VCOUNT < 19) ;       /* the top of the logo */

with `VCOUNT` a volatile byte, at -O2, compiles the second loop to

    ?L11: lda VCOUNT ; cmp #19 ; rep #32 ; bcc ?L11

The first pass is right. The second runs `lda` as a word and `cmp #19` as
a three-byte instruction, which swallows the `rep`'s opcode `c2`, so the
next thing executed is the branch's own operand — `90 f7` and whatever
follows it. In `src/sys/bootinfo.c` what followed was `20 90 f7`, a `jsr`
into the middle of `farmem_probe`, whose `rtl` then landed in the OS ROM
and BRKed out of the boot screen's rainbow.

**-O0 and -O1 emit the SAME trailing `rep #32`.** What saves them is a
`sep #32` at the top of the loop body, which keeps the loop
width-balanced; -O2 deletes that `sep` as redundant -- true on the
fall-through path, false on the back edge -- and leaves the `rep`.  An
earlier version of this entry said -O0 and -O1 put the `rep` after the
loop, which is wrong and would have had the vendor diff two listings, see
the same `rep` in both and conclude the report misread the output.

The first loop is untouched because its label sits before the `sep`; and
without the `if (p) return 0` both loops compile right, which is why a
minimal reproducer misses it. `do { vc++; } while (vc <
19);` is the same shape.

The shape CAN be run, and stepping it is much better evidence than the
listing: single-stepping `b16_bug` in `db65816` shows the back edge
re-entering the loop with M clear, the `cmp` then assembling as three
bytes, the program counter landing in the middle of the `rep`, and
`20 90 f7` executing as `jsr $f790` -- the entry's prediction,
instruction for instruction.  `check.py` still reads the listing, because
that needs no harness: a conditional branch backwards, immediately preceded
by `rep #32`, with no `sep #32` between the label and the branch. The
same reading over every gem4xe source with its own flags found only the
eight polls in `bootinfo.c`. The sources now read the byte into a word
through a helper and compare the word — `while (vcount() < line) ;`, with
`vcount()` a real call (`jsl`) that costs nothing at 20 MHz — and that
shape runs in `bugs.c` as `r_b16_fix`. Rule 16.

## B17 — a call entered with an 8-bit accumulator

    st = plat_measure_text(f, bytes, len, width_out);   /* linebreak.c, RetroWP */

At -O2 the caller reaches the `jsl` with M set.  The callee is compiled
for a 16-bit accumulator, so its first `##` immediate decodes short --
the operand's high byte is executed as an opcode -- and the program dies
inside a function that is not at fault.  RetroWP met it as a BRK with
`P=$21` at `plat_measure_text +0x33`, and keeps `-O1` on that one file;
at -O2 the image is 636 bytes smaller and does not survive measuring a
word.

The contract is not in doubt.  The vendor's own `assembly-interface.html`
says: *"The 65816 is used in native mode with 16 bit registers.  In some
situations the runtime needs to switch to 8 bit register mode ... This is
done automatically and the compiler will then switch back to 16 bits
mode."*  So a `jsl` reached narrow is a violation whatever the callee
does about it.

**NOT REPRODUCED IN THIS TREE, and this entry says so rather than
implying otherwise.**  Every other entry here was met in gem4xe and
minimised; this one was met in another project, measured there twice --
on the target and in the listing, under 5.18 and again under 5.18.2 --
and is recorded on that evidence.  `tools/ccbug/mscan.py --tree` scans
every source gem4xe builds and finds **zero**, so nothing here is waiting
to die of it.  A minimal reproducer has defeated both projects: the
obvious shape, 8-bit work in front of a call to an `extern`, compiles
correctly, and RetroWP's own small case compiled clean at -O2 -- which,
after B1, is exactly what a shape folded away by the inliner looks like.
Whoever tries next should try with `--no-inline` before believing a
negative.

**5.18.2 does NOT fix it**, measured by RetroWP against the 0.4 kit:
the BRK is in the same place and the listing reaches the `jsl` narrow
under both compilers.  Five shapes went in that release; this is not one
of them, and it must not be marked fixed on their account.

`mscan.py` is the scan.  It is a forward dataflow over the listing, and
the part that matters is the JOIN: a label's state is the meet of its
predecessors, so a branch target whose every path agrees is KNOWN.  That
is not a refinement, it is the whole thing -- RetroWP's failing call sits
behind exactly such a join (the fall-through arrives narrow, and the
other path widens for an immediate and narrows again at once), and a scan
that gives up at every label misses it and reports a clean tree.  Which
this one did, twice: first because it had no join at all, and then
because it spelled a label `` `?L340` `` and a branch target `?L340`, so
no edge was ever recorded and the join it had just grown never ran.  Both
times the answer was zero and both times zero meant nothing.
`tools/ccbug/mscan_b17.s` is that shape, and `check-cc` requires it to
report exactly one call -- because a scan that reports nothing is
worthless until something proves it CAN report.

**A zero from it is not a clean bill.**  It still declines to guess when
a join's paths disagree or when any predecessor is unknown, so gem4xe's
zero means "nothing found by a scan that admits what it cannot follow",
not "nothing there".

It is otherwise deliberately hard to make lie.  A
`##` immediate proves the accumulator is wide, so seeing one clears the
state; any call makes the state unknown, because the callee's exit width
is its own business; any label that is not a function entry makes it
unknown, because control can arrive there from a branch this scan does
not follow; and a call to a `?Lnnnn` fragment is never reported, because
that is the compiler talking to itself.  The first version of it had none
of that and reported 61 calls, every one of them safe -- the compiler
calls an outlined fragment while narrow and the fragment widens before it
returns.  Rule 17: do not spin a scan's output into a bug without reading
one hit all the way through.

## B18 — a far byte loop the compiler never finishes compiling

    while (*s && n < 127)
        dst[n++] = (WORD)(uint8_t)*s++;      /* s is const char __far * */

does not compile at `-O1` or `-O2` under `--data-model=small`. Nothing is
reported: the compiler runs until something kills it, and what killed it
here, twice, was the host's memory guard stopping `make` -- the first sign
was a build that died with no error in its log, on a file that had
compiled a minute earlier.

**The trigger is the combination**, measured one axis at a time
(`b18_farloop.c`, each compile under a 15-second timeout):

| shape | |
|---|---|
| `dst[n++] = (uint8_t)*s++` | **hangs** |
| the same without the `(uint8_t)` | compiles |
| `dst[n] = (uint8_t)s[n]; n++` -- index, not increment | compiles |
| `char c = *s++; dst[n++] = (uint8_t)c` -- the read into a local | compiles |
| `*(const uint8_t __far *)(a + n)` -- the address recomputed | compiles |
| unbounded `while (*s)` with the cast and increment | hangs |
| `-O0` | compiles |
| `--data-model=large`, any level | compiles |
| `-O2 --speed`, `-O2 --no-cross-call` | hang |

So it needs a post-increment read through a far pointer, narrowed in the
same expression, in a loop, with the optimiser on, in the small data model.
Found 2026-09-18 the day `expand_string()` (`src/aes/graf.c`) was given a
FAR string for `docs/far-trees.md`; the fix there is the local (rule 17).

**How `check-cc` sees it:** a bug that never returns cannot be reported by
the compiler, so `HANGS` in `check.py` compiles the file under a timeout and
"still present" means the timeout fired. At `-O0` it compiles at once and
reads `FIXED upstream`, which the matrix above records deliberately.

Reported as [Calypsi #90](https://github.com/hth313/Calypsi-tool-chains/issues/90)
on 2026-09-18, with the reproducer inline and the matrix above.

## B19 — a pointer difference against a far array cannot be linked

`tools/ccbug/b19_ptrdiff.c`. The shape is the most ordinary way in C to
turn a pointer back into a subscript:

    extern char arr[4096];
    short b19_index(const char *p) { return (short)(p - arr); }

Under `--data-model=large` `arr` is in far memory, and a far pointer's
arithmetic is 16-bit within its bank, so the difference only needs the
array's LOW WORD. What comes out asks for the whole address in sixteen
bits:

    sec
    lda     dp:.tiny _Dp        ; p, low word
    sbc     ##arr               ; the WHOLE address in a 16-bit field

and the linker refuses, correctly and at the very end of the build:

    symbol 'arr' referenced from section 'farcode' at offset 00006a in
    block.o: value 542819 is out of range, allowed range is -32768 to 65535

`##.word0 arr` is the instruction that was wanted, and the compiler
already emits exactly that everywhere it loads a far address as a VALUE
(`lda ##.word0 sym` / `ldx ##.word2 sym`, which is how `arr + i` comes
out). **Only the difference gets it wrong.**

**A cast does not help**, which is worth knowing before anyone tries one:
`(unsigned long)p - (unsigned long)arr` folds back to the same 16-bit
subtraction with the same immediate — verified in the reproducer, whose
second function is exactly that and whose listing is identical.

The instruction is the same in both data models and at every `-O` level;
it is a *defect* only where the symbol is far, because in the small model
the address genuinely fits. So `check.py` compiles this one
`--data-model=large`, and `far_ptrdiff_bug()` reads the listing for a
`sbc`/`adc` whose immediate is a bare symbol rather than a `.word0`. The
detector was made to speak both ways before it was believed: it answers
False on a listing containing `arr + i` and a difference between two
runtime pointers, neither of which needs a symbol immediate.

**Found by porting qed.** Three of its globals tripped it — two 11-byte
`char` arrays and a 12 KB struct array — and the workarounds show the
shape of the problem: a small array can go in bank `$00` (`__near`), which
the 12 KB one cannot afford, so its index had to be recovered by comparing
pointers instead of subtracting them. The failure arrives at link time,
in a message that names a symbol rather than a line, which is a long way
from the `p - arr` that caused it.

Reported as [Calypsi #91](https://github.com/hth313/Calypsi-tool-chains/issues/91)
on 2026-09-18; the standalone reproducer the report links is in `b19/`.

## Another project's ledger: MicroPython on the SNES

Fabian Kuebler ported **MicroPython v1.28.0 to the SNES** -- 65816, HiROM,
large memory model, Calypsi **5.17** -- and it passes 91.9% of MicroPython's
own `tests/basics` on the console. Probably the largest C codebase this
toolchain has carried. Along the way he root-caused **23 codegen findings**,
filed as [Calypsi #86](https://github.com/hth313/Calypsi-tool-chains/issues/86)
with the five broadest as their own issues.

    repo      github.com/FabianKuebler/micropython-snes
    ledger    DECISIONS.md          -- all 23, dated, with listings
    repros    bugs/                 -- three ready-to-compile cases
    scanner   tools/check_neg_index.py

**THIS SECTION IS THEIR EVIDENCE, NOT OURS**, the same standing B17 has.
Nothing below was met in gem4xe unless it says so.

**READ THE STATUS COLUMN FIRST. They were found on 5.17 and hth313 fixed
them for 5.18**, which is the floor this project already requires — so for
anyone on 5.18.2 this table is history, not a hazard list. It is kept
because the *shapes* are worth knowing and because the ledger is a good
account of what a large C program meets on this toolchain.

| upstream | finding | status |
|---|---|---|
| #81 | `__attribute__((aligned))` silently ignored on struct members and types | fixed for 5.18 |
| #82 | negative constant index on a **far** pointer compiles to unsigned Y-indexing; the access lands one bank away | fixed for 5.18 |
| #83 | the **third** pointer parameter loses its bank byte in call marshalling | CLOSED; he fixed the varargs case and could not reproduce the rest |
| #84 | assign-and-test in a loop condition stores an OR-mangled value (accumulator clobber) | fixed for 5.18 |
| #85 | `volatile` stores to stack locals dropped inside functions containing `setjmp` | fixed for 5.18 |

And from the ledger, not separately filed: a variadic function whose **last
named parameter is 16-bit** has it destroyed by `tsc` in the frame setup
before it is saved (pointer and 32-bit last parameters go in pseudo
registers and are safe — **fixed**); flexible-array-member initializers
silently dropped (**fixed for 5.18**); `--cross-call` corrupting
indirect-call arguments; `!(k >= k) || f()` folding to constant TRUE; and an
ICE, "unable to label". The last three were not filed individually and their
status is unknown.

That response is worth recording on its own: twenty-three findings from one
outside project, five filed individually, and all five answered and fixed in
a single release.

### What it costs gem4xe

Checked, rather than assumed:

- **#85 is not reachable here.** gem4xe uses no `setjmp`/`longjmp` at all.
- **#81 is not reachable here.** No `aligned` attribute in the tree.
- **The varargs bug is not reachable here.** gem4xe has no `va_start` of its
  own, and the vendor `printf` the kit stubs takes `const char *fmt` as its
  last named parameter -- the shape their note explicitly calls safe.
- **#82 is the family B13/B14 belong to**, which is the interesting one.
  Ours was a NEAR `WORD *pt` in `draw_arrow`, where `pt[-2]` "came back as
  neither point"; theirs is the FAR `[dp],y` form, where Y is added to a
  24-bit base as unsigned 16 bits so the access lands in the next bank.
  B13/B14 are fixed in 5.18.2. Theirs was found on 5.17.

**#82 does not reproduce on 5.18.2, and hth313 says he fixed it for 5.18.**
Measured here at `-O2`, `--code-model=large --data-model=large`: `sp[-2]`
through a `__far` pointer compiles to the safe form -- adjust the base with
`sbc ##4`, then a non-indexed `[_Dp]` -- and a scan of 50 of gem4xe's 71
sources finds zero `ldy ##<negative>` followed by long-indexed addressing.

Those two facts corroborate each other, which is the only reason either is
worth much. On its own the measurement would not have been: **their note
says which form the compiler picks is register-pressure roulette, per
compilation**, so a four-function file and a clean tree are exactly the
evidence B1 taught us to distrust. A clean scan still cannot prove absence
in code nobody has compiled yet -- it says this tree, at these flags, today.

### The scan, and the lesson it repeated within the hour

Their `check_neg_index.py` scans generated listings for the bad pattern and
fails the build -- independently the same idea as `mscan.py`, arrived at for
the same reason: a defect the compiler chooses at random cannot be caught by
testing, only by looking at what came out.

Ours is **`tools/ccbug/negyscan.py`**, `make negyscan`. It reports a
negative `ldy ##` followed by a LONG indexed access (`[dp],y` or
`addr.l,y`) -- and only those, because a negative Y with 16-bit addressing
wraps exactly as C's pointer arithmetic already does and is not a bug. It
finds **zero** across 68 of gem4xe's 71 sources.

Writing it reproduced [[make-a-silent-check-fail-first]] immediately. The
first version reported zero over the whole tree and **one** of the two sites
in a deliberately bad fixture -- because Calypsi puts the first instruction
of a function on the same line as its label (`below2:     sec`), and the
pattern required leading whitespace. Every negative-Y at a function's first
instruction was invisible. The tree's zero was meaningless until the fixture
said two.

`negyscan_82.s` is that fixture: two sites, the first on a label's own line,
and four controls beside them that must stay silent (the safe adjust-base
form, a negative Y with short addressing, a Y reloaded before its use, and
an ordinary positive Y). `check-cc` asserts it reports exactly two.

**And the fixtures found a hole in `check-cc` itself.** A fixture's result
was carried in the same dictionary as the bug shapes, where `False` prints
`FIXED upstream` -- so a scan that had gone blind would have reported good
news and PASSED. Fixtures are now their own group, a wrong count is a
failure in its own right (`BLIND -- must report 2`), and they no longer
inflate the "N of 20 bug shapes" tally, which they had: it read 16 and the
honest number was 15.

### Do not mine the patch; mine the ledger

`patches/0001-compiler-workarounds.patch` is 2,351 lines over 56 files and
is **not** a list of compiler bugs. Much of it is 16-bit-`int` portability --
`((size_t)x + (size_t)y * (size_t)fb->stride)` -- which is correct C that
MicroPython's own code had assumed a 32-bit `int` for. Taking entries from
the patch would put "bugs" in this catalogue that are the language working
as specified. `DECISIONS.md` is where he separates the two, and it is the
file to read.

## Reading the map — not a bug, and it gave the wrong answer twice

`clock()` turned up in a program that never calls it, 275 bytes together
with `Tgettimeofday`, and `ln65816 --list-file` showed both as sections
with no referrer. That was read, twice on the same day, as a dead-section
bug in the linker: an unreachable cycle (`clock` calls `Tgettimeofday`;
`Tgettimeofday`'s section branches into `clock`'s) that the mark had
failed to drop. It was neither unreachable nor a bug.

**The map lists a section's referrers by symbol, and a local label is not
a symbol it prints.** At -O2 cc65816 shares an identical tail across the
functions of one translation unit — the `dl()`/`dos()` epilogue of the
GEMDOS bindings in `src/app/gemlib.c` — and parks it inside one
function's section, so every other function reaches it through a
`?Lnnnn` label. In the map every one of those references is invisible,
and `clock` and `Frename` both read as referrer-less while live. The
chain, from the object file:

    Fread, Fwrite, Fseek   ->  Frename's section        via ?L1473
    Frename, Fdatime       ->  Tgettimeofday's section  via ?L1466
    Tgettimeofday, Fforce, Pexec, Ptermres, Mshrink
                           ->  clock's section          via ?L1462

so any GEMDOS file binding brings `clock` in; twelve bindings reach it
within three hops.

**It happens only under `--data-model=large`.** The same `gemlib.c`
compiled `--data-model=small` — the kit's default, and every program in
this tree — shares no tails at all, and only `Tgettimeofday` reaches
`clock`. A large-model program pays the 275 bytes the moment it touches a
file; a small-model one never does.

The tool is `objchain.py`. It walks an object's relocations backwards
from a symbol's section — `readelf -SW` for the sections and, for each
`.relocations` section, its file offset and the section it applies to;
`-rW` for the entries, matched to their target by that offset; `-sW` for
every symbol's section, local labels included — and names every global
function that transitively keeps the symbol alive:

    python3 tools/ccbug/objchain.py build/appld/gemlib.o clock --hops 3
    12 global function(s) bring clock in within 3 hop(s):
      Fattrib Fdatime Fforce Fread Frename Fseek Fwrite Mshrink Mxalloc Pexec Ptermres Tgettimeofday

    python3 tools/ccbug/objchain.py build/app/gemlib.o clock --hops 3
    1 global function(s) bring clock in within 3 hop(s):
      Tgettimeofday

Three things to keep from it. The map is a summary of the relocations,
not the relocations: when the question is "what references this", read
the object. A `\b` in a regex cannot match a symbol that begins with `?`,
which is how the first scan for `?L1466` found nothing and confirmed the
wrong theory. And the tail-sharing is sound code — the observation is
only that parking a shared tail inside one function's section makes
dead-section elimination all-or-nothing for everything that branches in,
a size cost and not a correctness one. The evidence — both sessions'
maps, objects, readelf dumps, and the scripts that produced the wrong
answer and then the right one — is kept outside the tree at
`build/ccbug-clock-cycle/`, not committed.

**The cluster grows, and there is a switch.** The day `Psystem` went
into `gemlib.c` the GACS session measured it joining the cluster
unasked — 352 bytes now, `clock` 215 + `Tgettimeofday` 60 + `Psystem`
77, for any large-model program that touches a file binding, and one
member more each time a binding is added in that neighbourhood.
`cc65816 --no-interprocedural-cross-jump` is the sharing by name.
Compiling `gemlib.c` with it, in the large model, leaves the library 594
bytes bigger as a whole and every binding its own section, so a program
pays 3–13 bytes more for each binding it *calls* (Fread 39→52, Frename
43→46, Malloc 13→14) and nothing for the ones it does not; `objchain.py`
then finds no function that brings `clock` in. The tree's
`build/appld/gemlib.o` rule carries the flag, and the kit's README tells
a program that builds the bindings itself to do the same. Re-run
`objchain.py` after adding a binding rather than assuming a chain is
stable — that is what it is for.

Measured on GACS the same day, the flag shed **1,028 bytes** of a
138,190-byte image (far 114,210→113,470; bank fixups 7,025→6,929), not
the 352 the cluster accounts for: placed sections went 1,662→1,639, so
twenty-three passengers left, not three — the same mechanism had been
dragging others in. RetroWP, which calls more of the bindings, shed
1,075 bytes of 204,252 with `gemlib.c` byte-identical on both sides.
Neither saving exists under `--data-model=small`, whose bindings share
no tail to begin with. Two details a consumer will meet. The flag belongs
on `gemlib.c` **only**: `clib.c` compiled with it gave the same section
count and 15 bytes more, because a program uses nearly all of `clib.c`
and there is nothing for cross-jumping to waste — this is an
optimisation for a library a program uses a fraction of. And `make`
tracks a rule's sources, not its recipe: adding the flag to an existing
rule rebuilds nothing, the gate re-runs the old image and reports the
old number — delete the object or make the Makefile a prerequisite.
