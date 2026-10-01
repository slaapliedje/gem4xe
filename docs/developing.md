# Developing gem4xe

How to build it, test it, and change it.  For using it, see
[`guide.md`](guide.md); for writing a program that runs on it, the
application kit's [`tools/sdk/README.md`](../tools/sdk/README.md), what
the system serves, [`api.md`](api.md), and where it differs from an ST,
[`differences.md`](differences.md).

## The tool chains

| What | Version | Where it is looked for | What for |
|---|---|---|---|
| [Calypsi](https://github.com/hth313/Calypsi-tool-chains/releases) for the 65816 | **5.18.2** | `CALYPSI=`, default `~/dev/toolchains/calypsi-65816` (the directory holding `bin/cc65816`) | everything that runs on the Atari |
| Python | **3.11** or later (`tomllib`), with **Pillow** | `python3` | the build's tools, the reference models, every test |
| An [EmuTOS](https://github.com/emutos/emutos) checkout | any recent | `EMUTOS=`, default `~/dev/emutos` | the opcode names in `make served`, and regenerating the font and patterns |
| [AltirraSDL](https://github.com/ilmenit/AltirraSDL), built from source | current `main`, plus one patch | `ALTIRRASDL=`, default `AltirraSDL` on the `PATH` | the emulated gates |
| Atari disk images of your own | -- | `fixtures.toml` | the emulated gates |
| `mkfs.fat` (dosfstools) | -- | the `PATH` | `make sd` only |

**Calypsi** is Håkan Thörngren's C compiler; it is free for hobby use and
its licence permits "producing application software for vintage and retro
computing systems".  Unpack the 65816 tool chain anywhere and point
`CALYPSI=` at it.  It has no Atari target: this tree carries its own
board support (`src/crt_atari.s`, `src/gem4xe.scm`, `tools/mkxex.py`).
**5.18.2 exactly** is what the workarounds are written against; a newer
release is welcome, and `make check-cc` says which of its defects it has
fixed (below).

**AltirraSDL** needs one patch that is not upstream yet, for the `H:`
device on Linux; the CPU core and debugger patches gem4xe needed were
merged in September 2026.  [`tools/altirra/README.md`](../tools/altirra/README.md)
has each patch and its state.  Build it, apply
`tools/altirra/altirra-sdl-hostfs-posix-paths.patch`, and run the gates
with `ALTIRRASDL=/path/to/AltirraSDL`.

**The disk images are yours.**  None is distributed here: the DOSes are
not gem4xe's to give away.  Copy `fixtures.toml.example` to
`fixtures.toml` (it is ignored by git) and fill in what you have:

| Key | What | Needed by |
|---|---|---|
| `[dos] sd_dos2`, `dd_dos2` | a single- and a double-density DOS 2 disk | the DOS 2 product floppy, the early gates |
| `[dos] mydos` | a MyDOS 4.50 disk | `test-mydos` |
| `[spartados] disk_32` | a SpartaDOS 3.2 disk | most desktop gates, the pictures' disk |
| `[spartados] sdx_cart` | a SpartaDOS X cartridge image | `test-boot`, `test-install`, QED's gate |
| `[u1mb] flash` | an Ultimate 1MB flash image | `test-cf`, `test-cf-dosclock` |

A gate copies an image into `build/` before it touches it, and one whose
fixture is missing says so and stops.

The **QED** port is its own repository,
[slaapliedje/qed-gem4xe](https://github.com/slaapliedje/qed-gem4xe),
checked out beside this one (`QED=`, default `~/dev/qed/gem4xe`); the
release carries what it builds.  Its first clean build wants
`make build/kit/include/gem.h` before `make`.

## Building

    make            # GEM.COM, the desktop, the accessories, the disks
    make sdk        # the application kit
    make dist       # what a tester is handed: the disks, the kit, the page
    make release    # the same for the public, named by VERSION
    make docs       # rewrite every generated page (api, guide, readme)

`VERSION` at the top of the tree is the version.  `make release` refuses a
dirty tree, because the source tarball it ships must be the source of the
binaries beside it.

The C is compiler-neutral: every word Calypsi adds to the language --
`__far`, `__attribute__((tiny))`, `__simple_call`, the interrupt
intrinsics -- is mapped once in `src/portab.h` (`FAR`, `TINY`,
`SIMPLE_CALL`, `cpu_sei()`...) and appears nowhere else, which
`tests/host/test_portab.py` enforces.  A second 65816 compiler would need
a second block in that header and its own assembly sources, not a sweep
through the tree.

The GEM system font and the fill patterns are extracted from EmuTOS by
`tools/fontconv.py` and `tools/patconv.py` and checked in, so the target
and the host reference read the same bytes; EmuTOS is needed only to
regenerate them.

## Where things are

| Path | What |
|---|---|
| `src/vdi/` | the VDI: the dispatcher, the attribute and drawing calls, and the device drivers -- `dev_vbxe.c` (the blitter), `dev_antic.c` (ANTIC mode F), `dev_print.c` |
| `src/aes/` | the AES, from EmuTOS's: objects, forms, events, windows (`wind.c`), menus, resources (`rsrc.c`), the shell (`shel.c`) and the control manager |
| `src/desk/` | the desktop, `DESKTOP.PRG` -- an application like any other |
| `src/sys/` | under both: the application loader, GEMDOS, the far heap, the call gate (`abi.c`), CIO and the DOS seam |
| `src/apps/` | the accessories and the programs in `\APPS\` |
| `src/app/` | the application kit: `gem.h` and the bindings every program links |
| `tools/` | the build's tools, and the reference models: `vdiref.py`, `aesref.py`, `deskref.py`, `devref.py`, `farref.py` |
| `tools/ccbug/` | every compiler defect this tree has met, reproduced |
| `tests/host/` | tests that need no emulator |
| `tests/emu/` | the gates, which boot the system in AltirraSDL |
| `docs/` | the guides, and a note per phase of the work ([`README.md`](README.md) indexes them) |

## Testing

    make test-host  # the host tests: no emulator, no fixtures
    make test       # the host tests, then every emulated gate (about forty minutes)
    make test-m19   # one gate

Run the emulated gates with `ALTIRRASDL=` set as above.  They are
listed, each with what it proves, in [`gates.md`](gates.md).

## Verification

Every gate compares the target against a **host reference model** —
`tools/vbxeref.py`, `tools/vdiref.py`, `tools/aesref.py`, `tools/deskref.py`
— which is treated as the specification. Both pixels and returned values
are compared, byte for byte, running on emulated hardware with all three
boards fitted.

Nothing here is asserted by eye. Two of the bugs found so far were
invisible on screen and only a pixel diff caught them — and one went the
other way: the file selector listed a file the reference did not, every
returned value agreed, and only the screenshots disagreed
(`docs/phase11.md`).

A model and the target can also agree and both be wrong, because one
person wrote both.  So a new check is made to fail first -- the code it
guards is broken on purpose and the check must say so -- and where it
can, a third view decides: the file on the disk image, the call the
target actually made, the number the C's own sizes give.

Calypsi cc65816 5.18.2 has **26 defects** this tree has met — mostly in code
generation, plus two crashes in the compiler itself, a compile that never
finishes, a refusal and a bad link — each reproduced in the vendor's own
simulator and worked around at the source (or, for the divide flags, with
a linker override). `tools/ccbug/README.md` lists them one by one with the
rules the sources follow; `make check-cc` runs every workaround shape and
reports which defects are still present, so one fixed upstream shows up as
a workaround that can go.  `make mscan` scans the build's own assembly for
the accumulator-width miscompiles (B17, B21, B23), which no gate can see
until they crash.

## Bank $00

Everything a 65C816 must find in bank `$00` -- the direct page, the
stack, the AES's near data, the application pool -- shares 64 KB with the
Atari's own OS, hardware and screen.  `make memcheck`
(`tools/memreport.py`) prints the budget from the linker's map, and the
host tests fail when LoRAM drops below its 256-byte reserve
(`tests/host/test_memory.py`); new state goes in far memory or on the
direct page (`TINY`), not there.

## The pages that are generated

Some documentation is written by the tree about itself, and a host test
fails when the committed copy is out of date:

| Page | Written by | Checked by |
|---|---|---|
| [`api.md`](api.md) | `make served` (`tools/opcodes.py`), from the dispatchers | `tests/host/test_opcodes.py` |
| [`guide.md`](guide.md) | `make guide` (`tools/mkdist.py`), from the release page's template | `tests/host/test_dist.py` |
| the numbers in `README.md`, [`gates.md`](gates.md) and this page | `make readme` (`tools/readme.py`) | `tests/host/test_readme.py` |

`make docs` runs all three.  The hand-written guides -- this one,
[`differences.md`](differences.md), the README -- are checked too
(`tests/host/test_docs.py`): every file, folder and `make` target they
name must exist, so a rename that leaves one behind fails.

## Releasing

1. Set `VERSION`.  The About box reads it (`tools/deskrsc.py`), and
   `make release` checks that the built resource says it.
2. `make docs`, and commit what it changed.
3. `make test`: everything green, with the fixtures in place.
4. `make release`, and publish what it writes with notes that say what
   changed, link the guides **at the release's tag**, and say what a
   person upgrading has to know.
5. Even releases are for speed and fixes only; odd ones bring features.
