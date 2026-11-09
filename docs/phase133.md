# Phase 133 -- the header in front

Step 1 of [cpanel-plan.md](cpanel-plan.md).  A `.CPX` is now the
module's 512-byte header and then the module, as on the ST, so the AES
lists a module by reading its header and loads at boot only the modules
that ask.

| | was | now |
|---|---|---|
| the file | a `.G4A` named `.CPX`, its header a variable inside it | the header, then the `.G4A` (`tools/mkcpx.py`) |
| listing a module | run it, so `cpx_init` fills the header | read 512 bytes off the front of the file |
| at boot | every module run, then freed | only `CPX_BOOTINIT`, `CPX_RESIDENT` and `CPX_SETONLY` modules run |
| how many | 6 (`CPX_MAX`), the rest skipped in silence | 16, the table sized to what the scan found |
| a file with no header | -- | refused, and counted (`sh_cpxbad`) |
| `cpx_init` | `(XCPB *, CPXHEAD *)`, filling the header | `(XCPB *)`; the header is the file's |
| icons | none: no module set one | General, Color and the test module have one |

## The header is text

`tools/mkcpx.py HEADER.cpxh MODULE.g4a OUT.cpx` writes the header from a
small text file beside the module -- `src/apps/general.cpxh`,
`color.cpxh`, `src/m35_cpx.cpxh` -- with the id, the version (`1.00` is
`$0100`, as XControl prints it), the flags, the title, the icon's text
and its colours, and the icon as 24 rows of 32 `#` and `.`.  An icon is
drawn in an editor and reviewed in a diff.  The words are the 65816's,
little-endian, at Atari's offsets.

The colour words are GEM's own: XControl hands `i_color` straight to its
slot's ICONBLK as `ib_char` and `t_color` to its TEDINFO as `te_color`.
`src/app/cpx.h` had read them as bit-fields, backwards, with macros that
took them apart wrongly; nothing ever set or read them, and the macros
are gone.

One module can go out under two headers.  The gate does: the same
`m35_cpx.g4a` is `M35.CPX` with no flags and `M35B.CPX` with
`CPX_BOOTINIT`, which only a header outside the code allows.

## The AES

`sh_cpxscan` reads the directory twice, once to count the `*.CPX` and
once, with the table allocated for exactly that many, to read each one's
header into its slot in eight 64-byte pieces (512 bytes of bank $00's
stack are not there to spend), check the magic, and lay its `.CFG` over
the buffer.  The names are no longer kept on the stack between the two,
which was 78 bytes.  `sh_cpx` then runs the modules whose flags ask, as
it ran all of them before.  A module that asks and declines stays
listed, with no vtable, so opening it tries again and says why.

The owners' bytes moved in front of the slots, since the table now ends
where the scan says.  `sh_xcpb`, 64 bytes of far memory allocated with
the table and never used, is gone, and with it 4 bytes of near memory.

The loader steps over the header when it loads a module (`app_kind`
`OWN_CPX`), checking the magic again rather than trusting the scan.  The
magic stays `$6811`: an ST's CPX begins with 100, and a 68000 module must
be refused, not loaded.

The glue (`src/app/cpxmain.c`) no longer writes a header.  If it did, a
module's defaults would land on top of the settings the scan had just
read back.

## The panel

`CPX_SETONLY` modules act at boot and have nothing to open, so they are
not listed, as XControl drops them; they are boot-initialised with the
`CPX_BOOTINIT` ones.  A row maps to its slot through `cpx_row`.  The
panel still shows six rows until step 2 gives it a window.

## Gates

- `test-host`: `HeaderInFront`, nine tests.  The magic and the size
  agree in `cpx.h`, `shel.c`, `app.h` and the tool; the tool writes the
  map's offsets; a header reads back; the icon is most significant bit
  first; bad headers and foreign files are refused; the shipped headers
  parse, and their flags are what the gates lean on.
- `test-m35`, rewritten: nine files -- one asking to be loaded at boot,
  seven not, and a bare `.G4A` with no header.  Eight listed, one
  refused, the titles read from the headers, one loaded at boot and
  freed, every vtable 0, the desktop where it is with no module.  Fails
  with every module loaded regardless of its flags, and with the magic
  check removed.
- `test-m44`: two modules loaded at boot (General and Color), both
  freed, three listed.  `tools/memreport.py` reads each module's flags
  from its built `.cpx`, so its pool floor follows what the AES does.
- `test-m36`, `test-m40`, `test-m42` unchanged and passing.
- `test_accessories_ship` counts a `.cpx` as a module binary: it looked
  only at `.g4a`, so with the modules gone from its view its own guard
  -- at least one module on the media -- failed, as it is meant to.

## Found on the way

- **`test-m35` did not depend on its base disk.**  It boots
  `build/m14-boot.atr` to measure "nothing stayed", and run on its own
  it booted whatever the last `test-m14` had left -- a system three days
  old here, whose runner never started.  In the suite's order it passed
  by luck.

## For a module's author

`cpx_init` takes one argument now, and the header moves out of the C
into a `.cpxh`.  A `.CPX` from an earlier release has no header in
front, so it is refused and counted, not loaded.
