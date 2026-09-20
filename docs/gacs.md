# The applications this is for — and what a port actually needs

gem4xe was not started to have a GEM.  It was started because two
programs wanted one: **GACS**, the GURPS Autoduel Construction Set, and
**RetroWP**, a word processor — both built the same way, a portable
engine in strict C89 with no I/O beside a shell per platform, both
aimed first at the Atari ST.  An Atari 8-bit with GEM on it is another
shell.

So the honest question was not "does gem4xe work" but "would GACS run on
it".  It does: the engine has compiled and run in the simulator since
this page was first written (`make gacs-check`, which keeps asking), and
since 2026-09-15 the GEM shell has come up on the emulated machine and
drawn a vehicle (`make g4a-check` in the GACS tree).  What follows is
what that took.

    engine, --data-model=small 7/7 files
    engine, --data-model=large 7/7 files
    footprint: 24819 bytes of code, 56253 of data and 18661 of
               constants, all far; 84 bytes in bank $00
    tables: 27 chassis, 13 engines, 10 tires, 20 weapons
    design: subcompact / small / std
    ad_compute -> 0
    GEM4XE -- Subcompact, Std. chassis, Light suspension, Small power
    plant, 4 Standard tires, driver only. Armor: F 0/1, ... Accel. 5,
    Top speed 80, Driving skill modifier

That is GACS's own engine, compiled by Calypsi for the 65C816, running
in Calypsi's simulator, parsing the six tables GACS ships and computing
a vehicle.  Not a mock-up of one: `ad_compute` answers `AD_OK` and
`ad_1e_format_line` writes the line GACS's own CLI writes.

## What it took, and what it says

**Nothing, in the engine.**  All seven files compile clean at
`--data-model=small` and at `--data-model=large`, with no warnings and
no changes to GACS.  Strict C89, no floating point, no OS calls: the
discipline that makes it portable to a 68000 makes it portable to a
65816, which is the whole argument for writing an engine that way.

**The memory model is the decision.**  `ad_tables` is 22 KB and
`ad_sheet` is another 33; gem4xe's application pool is 14,336 bytes of
bank $00 -- `$4800-$7FFF`, shared with the process records (364 bytes
for seven of them, which is the six Desk-menu accessory slots and the
program that is running), with the three accessories that ship, and with
the desktop, of which only the 1,280-byte near region is in the pool at
all, `DESKTOP.RSC` having gone far in phase 47 -- and 14 MB above it,
reached through GEMDOS's `Malloc`.  How much of the pool a program takes
is set when it links: GACS asks for 2 KB and RetroWP for 8.  So an
application compiles `--data-model=large`, where a pointer is 24 bits,
and works out of far memory -- which is exactly the shape GACS already
has, because its first prime directive is that a shell hands the engine
a buffer.  Compiled that way the engine wants **84 bytes of bank $00**.

**A shell was what was missing, and it is not missing now.**  GACS's GEM
shell was built for gem4xe on 2026-09-15 and has run, gated by `make
g4a-check` in the GACS tree: `GACS.PRG`, two code banks and three
far-variable banks, and 137,722 bytes rebuilt against 0.2 as a format 4
image -- the wide-fixup format, which it wants at 7,001 bank fixups.  An
estimate of one linker line stood here until somebody tried it, which is
the honest argument for trying things.  What a `--data-model=large`
program actually needs, found by building one (`src/m29_big.c`, `make
test-m29`):

  * **Six sections, not three.**  `src/app/gemapp.scm` mapped `farcode`,
    `switch`, `cfar`, `libcode` and `code`.  A large-data program also
    has `far` (initialised variables), `zfar` (uninitialised) and `ifar`
    (the initialiser `far` is copied from) -- and, in bank $00, `near`,
    `znear` and `inear`, because a global goes FAR there unless it is
    declared `__near`, and anything BUT a string handed to the AES must
    be near (`src/sys/abi.c`): a tree or a form far is refused, but the
    shim BOUNCES a far string (`near_str`), so `form_alert`, `rsrc_load`,
    `menu_text`, `menu_register` and the `fsel` dialog title take a far
    literal of up to **63 bytes** -- the near scratch bank $00 can spare.
    A longer string, or a second one in the same call (`fsel`'s path and
    selection, `shel_write`, `shel_find`), still wants `__near`.  It also
    needs `_NearBaseAddress` declared, which a small-data program never
    refers to.
  * **Bits and bss cannot share a memory.**  `far`/`zfar` carry no bytes
    and the linker refuses to place them beside `farcode`, so they go in
    a memory of their own -- the bank above the code.
  * **A runtime library of the same model.**  The linker will not mix
    runtime models, so `crt_gemapp`, `gemabi` and `gemlib` are built
    twice and a large-data program links `clib-lc-ld.a`.
  * **And the .G4A header had to learn to count banks.**  `tools/mkg4a.py`
    sized the far region from the image, and a far bss carries no bytes:
    a program whose variables are in the bank above its code would have
    been given one bank and left them in memory the far heap goes on to
    hand somebody else, with nothing failing at the time.  The count
    comes from the linker's map now, and `m29_big.g4a` asks for two banks
    where every other program in the tree asks for one.

  * **And `_NearBaseAddress` is ZERO**, which is the one that cost the
    afternoon.  A large-data program reaches near data as
    `stx .near sym`, which the assembler turns into `sym -
    _NearBaseAddress` with DB naming the bank; the crt sets DB = $00 and
    the loader relocates bank-$00 addresses by pages, so the offsets have
    to BE those addresses.  Naming the program's own data as the base
    instead made every near access an offset from it, so the first store
    in `main` went to $0000 -- the program scribbled the OS's zero page
    and wedged before reaching its own first statement.  The give-away
    was in the .G4A header all along: near page fixups fell from fourteen
    to one, because an offset needs no relocating and an address does.

`make test-m29` runs it: 3,000 words of far bss arriving zeroed, an
initialised far array arriving initialised, the whole array written and
summed, and the .G4A asking for two far banks where every other program
in the tree asks for one.  After it, the port
is: GACS's `shells/gem/main.c` against gem4xe's `COP` ABI instead of the
ST's trap, and `fopen`/`fread`/`fwrite` onto GEMDOS -- which is now a
seam with `Fseek` under it (`docs/phase16.md`).

## What the shell will find waiting for it

Measured against `shells/gem/main.c`, not assumed:

- **Every AES call it makes, gem4xe has.**  `appl_init`/`appl_exit`,
  `evnt_multi`, `menu_bar`/`menu_ienable`/`menu_tnormal`, `objc_draw`,
  `form_do`/`form_dial`/`form_alert`/`form_center`, `graf_handle`,
  `graf_mouse`, `fsel_exinput`, the nine `wind_*`, and
  `rsrc_load`/`rsrc_free`/`rsrc_gaddr`.  The `_grect` and `_str`
  spellings are gemlib's wrappers over those; `menu_sync` and
  `menu_action` are GACS's own functions, not AES calls.
- **Its VDI use in `main.c` is three calls** -- `v_opnvwk`, `v_clsvwk`,
  `vs_clip` -- but the linked shell pulls more through retroplat's
  drawing and metrics backends: `v_bar`, `vro_cpyfm`, `vs_color`,
  `vsf_color`, `vsf_interior`, `vst_color`, `vq_gdos`, `vqt_extent`,
  `vqt_fontinfo`, `vst_effects`, `vst_load_fonts`, `vst_point`.  Forty-one
  distinct AES and VDI calls in all, and gem4xe serves every one of them.
- **From GEMDOS** `main.c` calls `Dgetdrv` and `Dgetpath`, and the file
  seam under it adds `Fopen`, `Fcreate`, `Fclose`, `Fread`, `Fwrite`,
  `Fseek`, `Fdelete` and `Malloc`.
- **`GACS.RSC` is the format we read**: version 0, 2,792 bytes, 73
  objects, two trees, no colour icons.  It fits the application pool
  with room to spare, which is what matters: **whichever model the port
  is built in, this resource loads.**  Where it lands follows from that
  choice rather than from its size -- `rs_load` gives far memory to a
  caller that asks for it (`int_in[0]` bit 0, which the large-data kit
  sets) and the pool to one that cannot hold a 24-bit address -- and the
  engine compiles clean in both (7/7 files each, above), so the decision
  is still open.  At 2,792 bytes neither answer is tight
  (`docs/phase47.md`).
- **And it fits the screen.**  The two trees are 80x25 and 42x12
  CHARACTER CELLS; on gem4xe's 8x8 cell that is 640x200 and 336x96
  inside a 640x240 screen.  A resource laid out in cells travels, which
  is what the format is for -- the ST's own high resolution is 640x400
  with an 8x16 cell and the same 80x25.

## Printing, which is built now

GACS prints a record sheet; RetroWP prints documents.  GACS's GEM shell
writes **PostScript to a file** (`ad_render_ps`), so it never needed a
printer to reach parity with the ST -- and gem4xe has one regardless:
phase 37 put a third device behind the VDI's seam, 640x800 dots in one
far bank, emitted as PCL 5 or PostScript by `v_updwk`, gated by `make
test-m30` against a Ghostscript oracle (`docs/phase37.md`).  The VDI's
device independence is in `v_opnwk`'s device id, not in GDOS, which is
why that cost a second driver rather than a loader.

What is still absent is **GDOS proper** -- loadable drivers and
metafiles -- and the four calls that come with it (`v_opnprn`,
`vq_devinfo`, `vs_document_info`, `vqt_ext_name`).  qed's printer path
asks for those; neither of these two programs does, and both gate their
GDOS path on `vq_gdos`, which answers 0 here.
