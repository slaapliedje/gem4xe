# Phase 80 -- small programs share banks (.G4A format 5)

Phase 79 gave the far heap an allocator, and the 960K machine booted.
What it could not change was the loader's unit: a program's code went at
offset 0 of whole banks, because the fixups relocated only the bank byte
of a far address, and a large-data program's far variables took a bank
of their own above it.  `CONTROL.ACC` is 5,638 bytes of code and 372 of
variables, and it took 128 KB.

## Packed

A program is now linked six times, not three (the Makefile's `g4a`, and
the kit's Makefile): in place; the near region up a page; the whole far
region up a bank; and -- new -- **the code down a bank, the code up a
page, the far variables up a page**, each with the other region left
where it was.  `tools/mkg4a.py` takes the bytes that moved in each as a
fixup list, now ten of them: for the near part and for the code image,
references to the near region (by page), to the code (by bank, by page)
and to the variables (by bank, by page).  The variables' bank list is the
whole-region bank list less the code's.  The code moves DOWN a bank for
its list rather than up, because up it would overlap the variables'
bank in that link; the diff is taken the other way round.

**The lists, kept small.**  The first format 5 wrote ten lists of u16
offsets, and the desktop came out 6.8 KB BIGGER than as format 3 -- most
of a program's references are whole 24-bit addresses, and each was in a
page list and a bank list -- which took the DOS 2 floppy two sectors past
full (its room is tight, docs/phase57.md).  So: seven lists a part, a
**long** list for the 24-bit ones (the middle byte at the offset, the
bank byte after it) beside page-only and bank-only lists, for the code
and for the variables; and each list is **delta-coded**, a byte from the
last offset, or 0 and the offset itself.  The desktop is 50,124 bytes as
format 5 against 52,136 as format 3, and the floppy has 32 sectors free.
`mkg4a` reads every file it writes back (`read_v5`, `apply_v5`) and
patches it for where it was linked: any difference, and nothing is
written.  `test_g4a` holds every shipped program to no bigger than its
format 3.

A program **packs** when its code is one extent under the $D5 page and
its variables fit one bank.  Then it is written as **format 5**, and the
loader (`src/sys/app.c`, `app_load_v5`) places the code with
`far_alloc_page(size, $D500)` and the variables with
`far_alloc_page(size, $10000)` -- each at any page of any bank, each
wherever the allocator finds room -- and applies each list with its own
delta.  A page fixup adds to an address's middle byte and cannot carry,
since the code ends under $D500 and the variables inside their bank
wherever they go.

What does not pack is written as format 3 or 4 exactly as before: QED
(266 KB of code), GACS's shell, m31's image bigger than a bank.  Format 3
still loads and is still tested: `test_g4a` makes one from `m29_big`'s
links without `--pack` and relocates it against the shifted link.  `mkg4a` says why ("not packed -- ...").

Everything that ships but QED packs: the desktop (44,986 of code, 2,852
of variables), the three accessories, both control panel modules, CALC,
CLOCK, G4BENCH and the gate programs.

## What a boot takes now

Altirra's 65C816 with 960K, the whole-system cartridge, the desktop up:

    before phase 79     19 banks
    after phase 79      12 banks
    now                  3 banks, $04-$06 -- 184 KB in 38 blocks

and `CONTROL.ACC` sits at $05:7800, a page past `GENERAL.CPX`'s
variables.  `make test-m37` holds the boot to three banks.

## Checked three ways

- **Against the linker, at an arbitrary place** (`tests/host/test_pack.py`):
  the program is linked once more with its near region at $1300, its
  code at $05:0300 and its variables at $0A:0600 (`build/<name>-at.elf`,
  which only the test builds), and the file's bytes, with format 5's
  fixups applied for exactly those places as `app_load_v5` applies them,
  must be that link's bytes.  Run on `CONTROL.ACC` (far variables, the
  case that splits) and the desktop (2,434 code-page fixups).  With the
  variables' page delta dropped, 154 bytes of the accessory differ.
- **Running**: every gate that loads a program loads packed ones now --
  the desktop models (m17 and the rest, whose `desk_places` places a
  packed desktop as the loader does and finds its `G` among its
  variables through `app_vars`), accessories (m28), control panel
  modules (m35), the ABI (m11).
- **Leaving**: m17's heap check -- the heap after a desktop run must be
  the heap before plus the cached file -- caught the first version: the
  format 5 path returned before `APP.owner` was set, so `app_free` freed
  owner 0, which it refuses, and every packed program's blocks outlived
  it.

## The kit

The kit's Makefile links six times too, so a program built with it is
packed.  **Format 5 needs gem4xe 0.9.2 or later**: an older loader
refuses it (`APP_E_MAGIC`).  The Makefile says how to build a format 3
file instead.
