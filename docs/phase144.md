# Phase 144 -- the VDI's far buffers are the system's

Found while preparing step 2 of [vdi-plan.md](vdi-plan.md).  Step 2's
first change needs a far buffer of its own, and looking at how the VDI
takes the ones it already has turned up five defects.  They come before
any speed work, by the plan's own rule: a faster wrong answer is still
wrong.

| | was | now |
|---|---|---|
| contour fill's bitmap and seed stack | the property of the program that made the first fill: freed when it ended, the pointers kept | the system's |
| ANTIC's menu save area | the property of the program whose drop-down came first | the system's |
| a loaded face's strip | the property of the program whose `vst_load_fonts` loaded the first face | the system's |
| the printer's page | never given back, and the pointer kept after the program that printed ended | the system's, freed when the last printer workstation closes |
| contour fill on a printer workstation | a 64,000-byte map computed as -1,536: never worked | works |

## Whose a block is

A VDI call runs as the program that made it.  `src/sys/ctx.c` sets
`far_owner` at every switch, so a block the VDI takes during a call
belongs to the caller, and a program's end frees everything it owns.
The VDI took four of its buffers lazily, on first use, and kept the
pointers for good.  When the program that happened to be first ended,
the VDI went on using memory the heap could give to someone else:

- **The contour fill's bitmap and seed stack**: the first
  `v_contourfill`, in any program.
- **ANTIC's menu save area**: the first drop-down or alert, which is
  usually the desktop's.  With the desktop's blocks freed, the next
  program's menus saved the screen into them.  The VBXE keeps its save
  area in VRAM and was never affected.
- **A loaded face's strip**: the first `vst_load_fonts` when the boot
  loaded no `SYSTEM.FNT`.  The face is the whole system's and outlives
  any program.

Each now calls `far_keep` after it is taken, which makes the block the
system's.  `vwk_far`, the workstation table, does too, although only
`v_opnwk` at boot ever takes it.

## The printer's page

`pr_page_close` was called by nothing.  Its comment still described
the bump allocator that 0.9.2 replaced, which wound back with the
program.  The page went with the program that printed, and the pointer
stayed set, so the next program to open a printer workstation was told
the page was there and drew into freed memory.

The page is the system's now, so a second program printing at the same
time keeps it when the first ends.  `print_closed` frees it when no
printer workstation is left open.  It runs after `v_clsvwk` and after
`vdi_close_virtuals_but`, which closes a program's workstations at its
end.

## Contour fill on the page

`CF_BYTES` was `SCR_W / 8 * SCR_H` in 16-bit signed arithmetic.  On the
page that is 80 x 800 = 64,000, which as a WORD is -1,536.  Two things
followed:

- the allocation asked for four gigabytes and failed;
- with a screen's map already taken, the loop that clears the map
  compared a 32-bit offset against four gigabytes and went far past the
  map.

It is computed in 32 bits now.  And the map is a device's size, so one
too small for the workstation being filled is given back and taken
again at the right size.

## Gate

- **`test-m3`**, three system ops' worth (357 cases):
  - op 24, before any case: a contour fill made as a fresh owner, that
    owner's blocks freed, and the bitmap still a block;
  - op 25, after the cases have left a screen-sized bitmap: a printer
    workstation opened as a fresh owner, that owner freed, the page
    still a block; a fill low on the page, where a screen's bitmap does
    not reach, leaving a 64,000-byte bitmap; and the workstation closed,
    the page forgotten and its block freed.

  `cf_map` lost its `static` for these, and the runner reads
  `pr_page`, which was already public.
- **`test-m25`** takes ANTIC's save area as a fresh owner, frees that
  owner, and finds the area still a block.

The strip a loaded face goes into has no check of its own: it is the
same one line, `far_keep` after the take, that the others' checks prove.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| `far_keep` of the bitmap removed | the bitmap went with its first filler |
| `far_keep` of the page removed | page kept 0 |
| the page not freed at the close | pointer forgotten 0, block freed 0 |
| `CF_BYTES` back to 16 bits | the bitmap is 0 bytes |
| the resize removed | the bitmap is 19,200 bytes, the page needs 64,000 |
| `far_keep` of ANTIC's save area removed | m25: the save area went with its owner |

## A gate that passed by luck

The suite stopped at `test-m15g`: the runner, booted as GEM.COM on a
G4DOS disk, never came up.  Phase 143's build failed the same way, two
boots in four, so the cause was older than this phase.  The gate set
the Rapidus registers "two frames in" from launch.  The emulator has
run some frames of its own by the time the bridge answers, so that was
a different moment in the OS's start-up on every run, and about one
boot in two never reached the runner.  The gate now starts from a cold
reset, as the product's gates boot: six boots in six, and the gate
three times in three.

## The ANTIC floppy's room

Phases 142 to 144 grew the DOS 2 build of GEM.COM by about four
sectors, and the gate-only `gem-antic.atr`, the shipped floppy plus a
`GEM4XE.CFG` that says `VIDEO=ANTIC`, ran out by one.  That file was the
whole 4,378-byte template with the line uncommented: eighteen sectors,
on a floppy with seventeen free.  A user writes that file at the DOS
prompt when the monitor will not show the VBXE's picture, and what
`docs/guide.md` tells them to write is the one line.  The floppy does
not carry the template, and DOS 2 has no editor to edit one with.  So
the gate's file is the one line now, which is what a user would have.
The rule still checks that the template names the key.  The shipped
floppy has seventeen sectors free, against a floor of six.

m3's runner calls `vdi_init` again at each screen width.  That forgets
the system's bitmap without freeing it, about 50 KB a width.  The
product calls `vdi_init` once, at boot.
