# Phase 153 -- the kit's control panel module, built and loaded

Found while packing 0.15.  The release notes were to say that a module
built for 0.13 must be built again, which sent me to check that the kit
builds one that loads.  It did not.  Phase 133 had moved a module's
header in front of its `.G4A` (`tools/mkcpx.py`, from a `.cpxh` text
file).  The kit was never told:

| | was | now |
|---|---|---|
| `make KIND=cpx` | a bare `.g4a`, "install as .CPX" -- which the AES refuses, having no header | `cpx.cpx`: `example/cpx.cpxh` in front of the `.g4a` |
| the kit's tools | no `mkcpx.py` | `tools/mkcpx.py`, and `example/cpx.cpxh` beside the example |
| `example/cpx.c`'s `cpx_init` | `(XCPB FAR *pb, CPXHEAD FAR *hdr)`, the header filled in through `hdr` | `(XCPB FAR *pb)`, as `lib/cpxmain.c` calls it |
| the example's settings | read from `pb->buffer` in `cpx_init`, where `pb` is 0 at boot | read at `cpx_call`, from the panel's block |
| the example's form | its own `form_do` | in the panel's window, through `cpx_xform_do` |
| `cpx.h` | the signature in a comment | declared, so another shape does not compile |

The second argument was the worst of it.  `lib/cpxmain.c` passes one
argument, and with no prototype in `cpx.h` a module defining two
compiled and linked.  It then wrote its title and flags through whatever
lay where the second argument would have been.  `tests/host/test_sdk.py`
built the example and checked only that it built.

The kit's README and the example now say where a module's header comes
from, and that a module from 0.13 or before has to be built again with
one.

## Gates

- **`tests/host/test_sdk.py`** builds the example in a copy of the kit
  and checks the `.cpx`: `CPX_MAGIC` first, `cpx.cpxh`'s flags and title
  in the header, and the `.g4a` after its 512 bytes.
- **`test-m61`**, new, builds the module with the kit, from the kit's own
  tarball, as a person would.  It puts it on the G4DOS system floppy with
  the Control Panel, as `\GEM\MINE.CPX`, and then:
  - the panel lists one module;
  - opening it puts the example's form up in the panel's window, and OK
    brings the list back;
  - the disk read back afterwards has `MINE.CFG` beside the module,
    holding the example's mark and its one opening.
- **A module defining `cpx_init` with the old two arguments** no longer
  compiles: "conflicting types for 'cpx_init'".

| broken on purpose | result |
|---|---|
| the bare `.g4a` installed as `MINE.CPX`, as the kit made it | m61: no module listed, no `MINE.CFG` |
| `test_sdk` before the fix | no `cpx.cpx` |

Running it showed one thing more: the example's message, 35 characters,
ran past the window's 32-cell work area.  It says less now.
