# Object trees in far memory

Status: **all three steps built and gated.** Steps 1 and 2 landed
2026-09-18 -- every tree the AES touches is addressed as a FAR pointer,
and a resource loads into far memory for a program that has said it can
take a far address (`test-m33`). Step 3 landed 2026-09-19/20.
Designed from measurements of the tree as it was, so the argument rests
on what the code does rather than on what it is remembered to do.

> **⚠ THIS DOCUMENT IS THE DESIGN, AND THE POLICY IT DESCRIBES HAS SINCE
> CHANGED.** It was written while far memory was the FALLBACK -- taken
> when a resource would not fit the pool. Since 2026-09-19 far memory is
> the **PREFERENCE**: `rs_load` takes it for any caller that opts in,
> whatever the size of the file, and the pool is the exception for
> small-data callers and colour-icon resources. The desktop became a
> `--data-model=large` program to use it. Every "when it does not fit"
> below is therefore the design's wording and not the rule; the rule,
> the fourteen truncated addresses the change cost, and the current
> figures are in **`docs/phase47.md`**.

## Step 1, as it went

The type change was mechanical (124 sites, `OBJECT`/`TEDINFO`/`ICONBLK`/
`BITBLK` pointers in nine files), the seams were the four named below, and
the three whole-struct reads out of a tree -- a `TEDINFO` twice, an
`ICONBLK` once -- became `far_get` so that B11 never got the chance.
`rsrc.c` was left near on purpose except `rs_obfix`: its pool pointers are
step 2's business.

| what the design promised | what was measured |
|---|---|
| pixel-identical on every gate that draws a tree | m4 15/15, m7 10/10, m8 12/12, m9 4/4, m17 -- identical; the full suite and both applications are in `build/fartrees-suite1.log` |
| the desktop's `objc_draw` within +30 % | **320 frames after GO before, 320 after** -- the +26 % on the walk is invisible at frame granularity, because a redraw's time goes to the blitter |
| four globals gain a bank byte, nothing else grows | `zdata` grew by exactly 8 bytes (two per global); LoRAM fell to 248 free against a floor of 256 and `memreport` said so; the LoRAM/Near boundary moved 16 bytes, the one boundary that can, and LoRAM is at 264 |
| stack | low-water 1,389 -> 1,396 bytes: seven bytes of far pointers on the AES's stack |
| `check-cc`, `mscan`, `negyscan` before and after | all clean -- and `check-cc` gained an entry, below |

**What it found: B18.** `expand_string` -- the one place the VDI reads an
object's text -- was given a FAR string, and the natural loop,
`dst[n++] = (uint8_t)*s++;`, **never finishes compiling** at `-O1` or
`-O2` in the small data model. The compiler prints nothing; the host's
memory guard killed `make` twice before the file was bisected. The trigger
is the combination of a post-increment far read and a `(uint8_t)` cast in
one expression inside a loop; reading the byte into a local first is the
fix, and the reproducer, the matrix and a timeout-based `check-cc` entry
are in `tools/ccbug/` (`b18_farloop.c`, rule 17). Any byte copy out of
far memory this design adds later will want that shape. The port that motivates it is QED
(`docs/qed.md` when it exists; the numbers are below), but the change
serves every application whose resource or object trees outgrow bank `$00`
-- RetroWP's included -- and it is the shape a multitasking AES needs.

## Step 2, as it went

**Stage A -- one fixup, on any base.** `rsrc.c` addressed a loaded
resource through a near `RSHDR *` and fixed it up in place: word-swapping
whole tables, adding a 16-bit base to every offset, `strlen` over near
strings. It now addresses a resource through a **32-bit base**, and a
resource in the pool is one whose base has bank zero -- the same rule
step 1 gave trees. The fixup reads each record into a scratch through
`far_get`, swaps and fixes it there, and writes it back with `far_put`; the
header is copied out wherever a function needs its counts; `rsrc_gaddr`
and `rsrc_saddr` compute addresses rather than dereference pointers; the
process record's two resource slots are 32-bit bases with a far mark
beside each pool mark. `rs_imfar` and the colour-icon path are pool-only
by construction and say so.

This was done first, with **no far resource existing**, precisely so the
existing gates could judge the shared path: m4, m7, m9, m12 (the file
layer, which loads and frees resources), m13 (alerts and icons -- the
image-bits-to-far path), m17 (the desktop, 320 frames after GO as
before), m22 and m23 (accessories with resources of their own), and m28
(an accessory beside the desktop: two resource slots live at once). **All
nine identical.** Bank `$00` unchanged: LoRAM 264 free, Near 323.

**Stage B -- the far path and who may take it.** `rs_load` takes the
file into the pool when it fits, as before; when it does not, and the
caller has set bit 0 of `int_in[0]`, it takes one `far_alloc` (so the
whole file is inside one bank and `tree[obj]` is safe to index), streams
the file up through a 128-byte buffer, and fixes it up with the far base
through the same code. Otherwise it returns 0. The opt-in is safe because
`aes_entry` zeroes `int_in[]` and copies only `control[1]` words: the
large-data kit's `rsrc_load` passes one word set to 1 and keeps all 24
bits of `rsrc_gaddr`'s answer; the small-data kit passes none, so it can
neither ask nor be handed a far address. `global[5..8]` carry `ap_ptree`
and the header as 32-bit addresses now, as the ST's do. Colour icons
(`NEW_FORMAT_RSC`) stay a pool-only feature; a far-path request for one
is refused.

**Stage C -- a resource that cannot fit.** `tools/farrsc.py` builds
`FARRSC.RSC`: **42,364 bytes, 702 objects in 28 trees** -- three times the
pool and inside one bank. `src/m33_farrsc.c` is built twice from one
source: `--data-model=large` as `M33.PRG`, which loads it far, draws tree
0 from there, hit-tests it, reads a free string through the address it
was handed and frees it; and `--data-model=small` as `M33S.PRG`, which
must be refused with nothing else happening. `make test-m33` runs both
under the stand-in desktop (keys F and G) and reads every result out of
the program's near variables. On its first run the resource landed at
**`$070000`** -- bank 7, not the pool -- with tree 0 at `$076338` inside
it, `form_center` placed the 40x28 dialog, and `objc_find` inside the OK
button, a walk through 27 far objects, answered 24: the right one. The
dialog's rectangle on the screen held 12,400 dark pixels where an empty
box holds none; free string 0 read as `'F'` through the address
`rsrc_gaddr` handed back; `rsrc_free` answered 1. `M33S.PRG`, from the
same source, got 0 from `rsrc_load` and reached its wait with nothing
else touched. `make test-m33` passes.

The oracle for the whole step, after m33: the full suite -- 41 gates and
205 host tests, every one green, `build/fartrees-suite2.log` -- then
`make sdk`, and GACS and RetroWP rebuilt against the rebuilt kit and run
end to end. Both pass: neither asks for a far resource, and their
resources load into the pool through the one fixup that now serves both.

Two of the first gate's failures were the gate's own, recorded because
they will recur in any gate that reads a program's variables: **a
program's near region is the shell's again the instant the program
exits**, so a result read after exit is the desktop's variable, not the
program's -- both builds now wait at step 9 until they have been read;
and `sh_runs` counts the desktop's return as a run, so the small build
is run 4, not 3.

## Why

The AES addresses every object tree with a bank-`$00` pointer. `OBJECT
*tree` is the parameter in `objc_draw`, `objc_find`, `form_do`, `mn_bar`,
`fm_do` -- 117 sites across nine files -- and the ABI narrows the address an
application passes with `near_of()`, which refuses anything above `$FFFF`.
A resource loads into the application pool, **14 KB of bank `$00`**
(`rsrc.c:288`); only icon bits are sent far.

That fits everything that exists today. The desktop's resource is 6,226
bytes, GACS's is 2,792, and RetroWP avoided the question by building its
menu tree in code inside its 11.5 KB near region. It does not fit QED:

    qed.rsc   34,026 bytes   682 objects   32 trees   118 TEDINFOs   44 strings

The OBJECT array alone is 16,368 bytes -- larger than the pool before a
single string -- and it is one resource, loaded once, reached through 33
`rsrc_gaddr` sites. Bank `$00` has **1,794 bytes free** with the desktop up
and 258 while a resource is loading (`tools/memreport.py`), so the pool
cannot grow and nothing large can be bounced down.

> **Those are the BEFORE figures -- the measurement this design was
> argued from, kept because the argument rests on it.** Today
> `tools/memreport.py` prints **8,192 bytes free** with the desktop and
> *three* accessories resident, and the loading peak is gone: the
> desktop is a large-data program now, so its 6,398-byte resource never
> enters the pool at all. QED's near region also came down from 11,520
> bytes to 6,144, so it launches from the desktop rather than replacing
> it. `docs/phase47.md`.

So a tree has to be usable where it lies, in far memory, by the AES that
draws it, finds in it, edits it and hangs a menu from it.

## What the data already says

The structures were never 16-bit. The `.RSC` format is 68000-native, and
gem4xe kept its layout byte for byte:

- `OBJECT.ob_spec` is `uint32_t` (aes.h:37): a 32-bit GEM address, or a
  packed colour word for the box types.
- `TEDINFO.te_ptext`, `te_ptmplt`, `te_pvalid` are `uint32_t` (aes.h:307).
- `ICONBLK` names its mask and image in 32-bit fields, and `gsx_blt` has
  taken a 32-bit address since phase 2 -- which is why icon bits already go
  far and nothing notices.
- The kit's application-side `OBSPEC` union (`gem.h:116`) is declared so
  that "the whole long reads as a far pointer whose bank is the high word's
  zero -- bank `$00`". It is already a far pointer. Its bank is just always
  zero today.

Only the AES's *reading* of these fields is 16-bit, and that reading is
concentrated:

| where | what narrows |
|---|---|
| `objc.c:58` | `#define SPEC_PTR(spec) ((void *)(uint16_t)(spec))`, and `ob_getspec()` for `INDIRECT` |
| `rsrc.c:96` | `fix_long()` adds `(uint16_t)h`, a 16-bit base, to every file offset |
| `abi.c:256` | one `switch` turns `addr_in[0]` into `OBJECT *` through `near_of()` for opcodes 30-34, 40-47, 50, 54-56, 75, 114 |
| five raw casts | `(TEDINFO *)`, `(ICONBLK *)`, `(char *)tree...` outside the helper |
| four globals | `gl_mntree`, `gl_wtree`, `gl_awind`, `gl_newdesk` are `OBJECT *` |

## The design: one path, and near is bank zero

**Every tree is addressed through a FAR pointer, and a tree in bank `$00`
is a far pointer whose bank byte is zero.** There is no second path and no
branch per access. A `[dp],y` long-indexed load with bank `$00` in the
pointer reads bank `$00` RAM correctly on the 65816, so the pool trees the
desktop, GACS and RetroWP use today are served by the same code that
serves a far one -- unchanged in storage, changed only in how they are
named.

Concretely:

1. `OBJECT *` becomes `OBJECT FAR *` at every one of the 117 sites, the
   four globals included. `TEDINFO FAR *`, `ICONBLK FAR *`, `BITBLK FAR *`
   likewise.
2. `SPEC_PTR(spec)` becomes `(void FAR *)(spec)` -- the whole long, no
   truncation -- and the five raw casts go through it.
3. `fix_long()` adds a **32-bit** base. For a resource in the pool that base
   is still a bank-`$00` address and every fixed-up field is what it is
   today; for a far resource it carries the bank.
4. The ABI's `near_of()` in the tree `switch` becomes `far_of()`: accept the
   24-bit address, refuse nothing. (`near_of` stays for the opcodes that
   take a *string*; see "strings" below for why those are different.)
5. `rsrc_load` gains a far path: read the file whole into far memory
   (`far_read_file` exists), fix it up in place with the far base, hand
   back far addresses. It takes that path **only when the file will not fit
   the pool and the application has said it can take a far answer** --
   see "who may receive a far address".

This is what `wind.c` already did for its one large structure: `ORECT FAR
*gl_olist`, the rectangle pool, walked directly by the AES since phase 8.
The precedent exists and has been green for thirty-six phases.

### The cost, measured

The same object walk -- follow `ob_next`, sum two rectangle fields --
compiled `--data-model=small -O2` both ways:

    near_walk   74 instructions
    far_walk    93 instructions       (+26 %; the far form spills its
                                        pointer to the stack around the
                                        loop: pei/pha/lda 1,s)

That is the price for *every* tree, including the desktop's, because there
is one path. It is paid in the object walkers -- `everyobj`, `objc_find`,
`ob_get_par` -- which are not where a redraw's time goes; a redraw's time
goes to the blitter, which is unchanged. It is a real cost and it will be
**measured, not assumed**: VCOUNT ticks around `objc_draw` of the desktop
before and after, with a budget of +30 % on the walk and 0 on the pixels.

### Strings: the one place the VDI is involved

An object's text is read by `gr_gtext`, and the VDI takes its text as
`intin` words, not as a pointer into the caller's memory. So the far change
is local to `gr_gtext`: read the bytes through a far pointer into `intin`
instead of through a near one. No bounce, no scratch, no cap. (If
`gr_gtext` turns out to hand the pointer further down rather than copying
into `intin`, the loop moves one level; the shape does not change. That is
implementation step 0, to look rather than to remember.)

Editable fields are the other direction: `objc_edit` and `form_do` write
`te_ptext` in place. Those become far writes -- `far_write8`, or a FAR
`char *` -- at the sites that store a character or move the cursor.

The far-title bounce in `wind.c` stays. A window title is a TEDINFO
the *VDI* re-reads at every redraw through `te_ptext`, and the reasoning
there -- copy at draw time because the application may edit it in place --
is unchanged by any of this. It could later be replaced by the same far
read, which would lift its forty-character cap; that is a follow-up, not
part of this.

> **The follow-up happened (2026-09-20).** `w_ptext` no longer copies
> anything -- it assigns the 24-bit address, because `objc_draw` already
> reads a `G_TEXT`'s string through a far pointer and the frame's name
> takes that same path. The two 41-byte buffers were deleted (+82 bytes
> of LoRAM) and **there is no forty-character cap**. It was not an
> optimisation: the desktop's own `w_name` is fifty bytes, so a deep
> path drew short from the moment `G` moved to far memory, and
> `tools/aesref.py` never modelled the cap -- model and target had
> quietly stopped agreeing. `docs/phase47.md`.

### Who may receive a far address

A small-data-model application holds `OBJECT *` as sixteen bits. Hand it a
far resource and `rsrc_gaddr` writes a truncated pointer **silently** --
the exact failure class this project has spent a week hunting in the
compiler. And the AES cannot tell the two models apart: the `APP` record
(`src/sys/app.h:60`) carries near and far regions and sizes, and *both* a
small-data GACS and a large-data RetroWP have a far region, because both
have far code.

So the application says. The kit is already built once per data model
("the same three for an application compiled `--data-model=large`",
Makefile:453), so the large-model kit's `rsrc_load` binding sets a word in
`int_in` that the ST's `rsrc_load` never used -- "I take far addresses" --
and the small-model kit leaves it zero. The AES's `rsrc_load` then decides:

    fits the pool                     -> the pool, as today, for everyone
    does not fit, flag set            -> far memory
    does not fit, flag clear          -> refused, with an error the
                                         application can show

A small-model application therefore **never** receives a far address, and
a large-model one receives them only for a resource that could not have
loaded before. Nothing that loads today loads differently.

### Limits, stated

- **A tree lives in one bank.** Calypsi's far pointer arithmetic is 16-bit
  (`farmem.h:49`), and `far_alloc` never crosses a bank -- it skips to the
  next -- so a resource is bank-contained by construction and indexing
  `tree[obj]` within it is safe. That caps a resource at 64 KB. QED's is
  34 KB; anything larger is refused with the same error as above, which is
  an honest answer for a machine class where a resource that size would be
  unusual.
- **`rsrc_gaddr` answers a far address for a far resource**, and the
  application must be the one that asked for that (above).
- **Colour icons are still not loaded** (`rsrc.c:2`, "less the colour
  icons"). QED's `icons.rsc` is a separate, 6 KB, version-4 file; it is not
  part of this.

## The compiler bugs this walks into

Every one is catalogued, and every one bites *exactly* this shape:

- **B11** -- a near <-> far struct copy over 8 bytes is an internal error.
  An `OBJECT` is 24 bytes. No `OBJECT tmp = tree[i]`, no `*dst = *src`
  between near and far; field by field, or `far_get`/`far_put`.
- **B1 / B13 / B15** -- two elements of one array in one expression, a
  negative index from a pointer into an array's middle, `p->a = p->b OP e`
  through a spilled pointer. The rules in `tools/ccbug/README.md` already
  forbid the shapes; a far array makes them more likely, not less.
- **#82 (negative Y with long addressing)** -- fixed in the 5.18 this tree
  requires, and `make negyscan` now guards the shape; a far tree walk is
  precisely the code that would produce it.
- **B17** -- `make mscan`.

`make check-cc` runs before and after, and both scans are part of the
gate.

## Verification

1. **Nothing existing changes.** Every gate that draws a tree -- m4, m7,
   m8, m9, m17-m19, m26, GACS `g4a-check`, RetroWP `gem4xe-check` -- stays
   **pixel-identical**. Their trees are pool trees addressed as bank-zero
   far pointers; the images must not move by a byte.
2. **A far resource, drawn against the model.** `tools/rsc.py` builds a
   resource from a description and `tools/aesref.py` draws the same
   description on the host. A fixture of ~700 objects across several trees
   -- too big for the pool by construction -- loaded by a large-model gate
   application, drawn with `objc_draw`, hit-tested with `objc_find`, run
   through `form_do` with an editable field, and hung as a menu bar, each
   compared with the model. This is `make test-m4` again, with the tree
   where it could not be before.
3. **The refusals are exercised.** The same fixture loaded by a
   *small-model* application must be refused, with the error code, and
   nothing written; a resource over 64 KB likewise.
4. **Cost.** VCOUNT around the desktop's `objc_draw`, before and after.
5. **Bank `$00`.** `tools/memreport.py` before and after: four globals gain
   a bank byte; nothing else may grow.

## Order of work

1. The type change, `SPEC_PTR`, `gr_gtext`, the four globals, `far_of` in
   the ABI -- **with no far resource yet.** Every tree is still in the pool;
   every gate must pass unchanged. This proves the one-path claim before
   anything depends on it.
2. `rsrc_load`'s far path, the kit's flag, the refusals, the fixture, the
   new gate.
3. QED.

Step 1 is the risky one and it is the one with a complete oracle already
in place: forty gates that draw trees and compare pixels.

## What this is not

It is not a way to make the pool bigger, and it is not a bounce. Both were
considered. A bounce cannot hold a 34 KB resource in 1,794 free bytes; the
pool cannot grow because the LoRAM/Near boundary is the one boundary in
bank `$00` that fails at link time rather than at run time
(`gem4xe-bank00-which-boundary-to-move`). Keeping the OBJECT array near and
only the strings far was also considered and rejected on the same number:
QED's objects alone are 16 KB.
