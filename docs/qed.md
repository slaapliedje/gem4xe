# QED on gem4xe — what it took

`qed` is a GEM text editor for the Atari ST, maintained in the FreeMiNT
tree (<https://github.com/freemint/qed>).  It is the first candidate for
something gem4xe has never had: **a real application somebody else wrote.**
Everything in `\APPS\` so far is ours -- a calculator, a clock, a
hello-world, and since phase 47 the calculator is a Desk accessory as
well as a program, with a control panel accessory beside it -- and a port
of qed would say the platform is a platform.

**This began as a scoping note and has been overtaken: qed IS ported and
it works.**  Menus, editing and saving through the file selector all run
and are gated, and since phase 47 it LAUNCHES FROM THE DESKTOP rather
than being installed in its place -- its near region came down from
11,520 bytes to 6,144, so it fits beside the desktop instead of
replacing it.  Replacing the desktop was never only a size question: it
would make multitasking permanently harder to add, and this tree would
rather keep the shapes a multitasking AES could keep.

The port lives in a checkout of its own (`~/dev/qed`, branch `gem4xe`),
not in this tree, and its remote is upstream's, so it is not pushed
there.  `tools/ci_gem4xe.py` in that checkout drives the whole thing:
the desktop comes up, opens a drive, and runs `QED.G4A`, requiring
`sh_runs` to go 1 to 2 -- the desktop is still process one.

What follows is the scoping as it was written, kept because the
reasoning is what made the port cheap, with the counts corrected where
the engine has since closed a gap.

## The licence is Public Domain, and that took checking

**qed is PUBLIC DOMAIN, not GPL.**  GitHub reports no licence for the
repository at all: there is no `LICENSE` file, no SPDX line and no GPL
header in any source file, and a web search that says "GPL-2.0" is wrong.
The manual says it outright, in all three languages it ships
(`doc/qed-{en,de,nl}.stg`):

> qed ist ab Version 3.09 inklusive aller Quelltexte Public Domain!

-- public domain, *including all sources*, from version 3.09 on.  That is
compatible with gem4xe's GPLv2+, and more permissive than it.

One thing to know rather than discover: `LIESMICH` records that Tom
Quellenberg built qed out of the demo programs of the book *"Vom Anfänger
zum GEM-Profi"*, and that the program's structure came from the book too.
The author's public-domain declaration covers what he distributes.

## The shape of it

**~800 KB of C in about 35 files, and not one line of assembly** -- which
is the thing that makes this tractable at all, because the ST-specific
assembly is what usually has to be rewritten.  It is a full editor:
syntax highlighting (`highlite.c`, 64 KB), the editor core (`edit.c`,
53 KB), projects, search and replace, macros, word wrap, printing, a
clipboard and multiple windows.

It binds through `cflib.h`, gemlib and `mintbind.h`, with its MiNT-only
code behind `#ifdef __MINT__` and the inter-application AV protocol in a
module of its own (`av.c`).  Those two are separable, which matters:
gem4xe is one application under SpartaDOS X, not a multitasking desktop.

**cflib is not separable, and it is the part to plan around.**  qed links
`-lcflib -lgem -liio` (`src/Makefile.objs`), and cflib is where
`init_app`, `exit_app`, `open_vwork`, `do_alert`, `select_file` and
`getcookie` live -- which is why `appl_init`, `appl_exit`, `graf_handle`,
`v_opnvwk`, `form_alert`, `form_do` and `fsel_exinput` **do not appear in
qed's own sources at all**.  They happen inside the library, and its own
symbol table proves it rather than inferring it: `libcflib.a`'s
undefined `mt_*` set is most of the AES.

What is on this machine is the MiNT cross-root's **prebuilt m68k
archives** -- `libcflib.a` and `libgem.a` in
`/home/root-cp/usr/m68k-atari-mint/lib/`, `cflib.h` beside them, all
dated 2017 -- and **no cflib source anywhere**.  m68k object code cannot
link into a 65816 program, so those archives settle what cflib calls
without helping to build it: they are a specification.  The first
question a port has to answer is still where cflib comes from.

## What gem4xe already answers

Counted rather than guessed, by matching every AES/VDI call in `src/*.c`
against `src/app/gem.h`, the count opened at **74 distinct GEM calls in
qed's own sources, 59 of them served**.  That was a count of qed, not of
a running qed -- what cflib calls on its behalf is not in it, as above.

**The AES half of that gap is closed.**  On 2026-09-19 the engine
reached all 79 AES opcodes (`docs/phase46.md`), and `tools/opcodes.py`,
which reads the dispatchers rather than the header, answers `0 AES ...
opcodes are not served`.  So what remains in the table below is not AES
work at all: two of its rows are cflib's and gemlib's own functions
rather than opcodes, one is MultiTOS's AV extensions that a port trims,
and one is the GDOS printing path qed already gates itself out of.  The
single call still genuinely outstanding is a **VDI** one,
`vqt_real_extent` at opcode 240.  The rows are kept because each still
says what KIND of gap it was, which is what a port has to plan around:

| | calls | what it is |
|---|---|---|
| cflib helpers, not AES | `menu_help`, `menu_key`, `v_slider` | comes with the cflib subset |
| GRECT wrappers | `wind_create_grect`, `wind_open_grect` | trivial; the calls under them exist |
| AV / MultiTOS | `appl_search`, `appl_control` | trim, or stub as "no extensions" -- `appl_find` (13) and `appl_getinfo` (130) are **served now** |
| the clipboard | `scrp_read`, `scrp_write` | **served now** — the AES keeps the scrap directory (`src/aes/scrap.c`), gated in `make test-m12` |
| GDOS printing | `v_opnprn`, `vq_devinfo`, `vs_document_info`, `vqt_ext_name` | **already skipped**: qed gates these on `gl_gdos`, and our `vq_gdos()` answers 0 |

The scrap manager is built now (`src/aes/scrap.c`), so with AV and
printing trimmed, **what is left is the one call cflib drags in behind
it.**  The other two have been served since: `menu_popup` (36), which is
what every popup in `find.c`, `options.c`, `makro.c`, `prn_cfg.c` and
`dd.c` reaches through cflib's `handle_popup`, arrived in phase 46, and
`objc_sysvar` (48), which enters twice over -- through `get_objframe`
and through cflib's own `init_userdef` -- arrived in phase 45.  That
leaves `vqt_real_extent`, a real VDI call at **opcode 240**, in the
FSM/GDOS range and so outside our 1-39 and 100-131 entirely -- though it
sits behind the same `gl_gdos` gate as the rest of the printing path.

**That one is qed-as-built, not qed-as-ported.**  It enters qed's
surface only because it links cflib, and a port has to replace cflib
rather than link it, so it becomes the replacement layer's choice.  The
scrap manager is the one that survives either path, because qed calls it
directly -- and cflib reaches `scrp_read` as well, through
`get_scrapdir`, which makes that verdict firmer rather than looser.

The editor-critical surface is already there and gated:
`objc_edit` for editable dialog fields, `form_center`/`form_keybd`,
`menu_icheck`/`tnormal`/`ienable`, `wind_calc`, the scroll messages
(`WM_VSLID`, `WM_ARROWED`), styled text, and the file selector.

**And three things qed asks for that gem4xe answers correctly by having
nothing.**  Its MiNT calls -- `Psignal`, `Pdomain`, `Pgetuid`, `Pgetgid`,
`Fchmod`, `Fchown` -- get `EINVFN` here, which is what plain TOS returns
and what qed already tests for: `uid = Pgetuid(); if (uid == -32) uid = 0;`
(`src/global.c`).  Its cookie lookup defaults when the jar is absent --
`if (!getcookie("_IDT", &_idt)) _idt = 0x0000112E;` -- and gem4xe has no
jar, which is that same answer.  And its only BIOS use is the bell:
28 calls, every one of them `Bconout(2, 7)`, which is one `#define`.

## The prerequisite that is mostly cleared

A text editor holds its buffers in far memory, so qed would be compiled
`--data-model=large` -- and until 2026-09-14 that was a wall rather than a
preference: every string literal in such a program is far, and the COP
shim nulled a far string, so `form_alert` drew nothing and `rsrc_load`
opened no file.  That is fixed (`src/sys/abi.c`, `near_str`), and `fsel`'s
dialog title bounces too, so the file dialog works.  The limit that
remains is written down in `src/app/gem.h`: a far string bounced through
the near scratch is capped at 63 bytes, so a second string in one call
still wants `__near`.  `form_alert` is no longer one of them -- an alert
is copied into the AES's pool instead, up to 511 bytes.

**And the one that looked as though no bounce could clear it.**
`wind_set(WF_NAME)` and `WF_INFO` pass a string the window manager
*keeps*: it reads the title again at every redraw, so there is nothing to
copy into a scratch that would still be alive when the drawing happened.
The answer was to keep the address rather than the characters.  The
WINDOW record holds all 24 bits of it, and since phase 47 `w_ptext`
(`src/aes/wind.c`) simply ASSIGNS that address into the TEDINFO the
frame is drawn from, because a `te_ptext` is a far pointer now like
every other address in a tree (`docs/far-trees.md`).  That keeps the
ST's contract in both directions -- the address is re-read every redraw,
so an application may still edit its title in place -- and it costs bank
$00 nothing: the near buffers `w_bldactive` used to copy a far title
into are deleted, and **there is no cap on a title's length** in either
memory.  It was not always so: the copy cost 114 bytes of bank $00 that
bank $00 did not have, the LoRAM/Near boundary moved 192 bytes to find
them (`src/gem4xe.scm`, which records the two places that were tried
first and the gates that refused them), and a far title was capped at
forty characters for as long as the buffer existed.  `make test-m29`
draws the same eleven characters from a far address and from a near one
and requires the two title bars to be the same pixels.

RetroWP's titles are still blank, but that is now RetroWP's own doing
rather than a limit of the system.

## If it were done, roughly in this order

1. ~~The scrap manager~~ -- **built**: `scrp_read` and `scrp_write` keep
   the scrap directory in far memory and round-trip it, gated in `make
   test-m12` (`src/aes/scrap.c`).  It was useful to gem4xe with or
   without qed, which is why it went first.
2. **cflib** -- replace it, then trim to only the functions qed calls.
   It supplies qed's start-up, its alerts and its file selector, and
   what is on this machine is m68k binary that a 65816 program cannot
   link, so this is a prerequisite rather than a trim.
3. **Trim** `av.c`, the `__MINT__` paths and the GDOS printing, so what is
   left is the editor.
4. **Build it far** -- ~800 KB of C is several far banks; the loader
   already carries multi-bank images (test-m6, test-m31), and RetroWP is
   the standing precedent at 202 KB over four banks.
5. **Then the long tail**: the ST character set, key codes, and whatever
   the editor assumes about a screen that is 640x240 rather than 640x400.

The honest size is "a project, not an evening" -- but it is bounded, it is
mostly mechanical, and the licence and the ABI are both out of the way.
