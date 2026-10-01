# Phase 91 -- the documentation, and keeping it true

The release page, the README and the kit's README had each been written
as the work went, and each had fallen behind it in places.  This phase
gives gem4xe a set of guides, and gives each a way of failing a test
when it goes stale.

## The guides

| Page | What | How it stays true |
|---|---|---|
| [`guide.md`](guide.md) | how to try it: the machine, the media, the emulator, what works, where the settings are | it IS the release page: `make guide` renders the same template `make dist` does, from what needs no build; `tests/host/test_dist.py` regenerates it |
| [`api.md`](api.md) | every AES and VDI opcode, the window fields, `appl_getinfo`, `objc_sysvar` and GEMDOS | `make served` reads the dispatchers' `case` labels; `tests/host/test_opcodes.py` regenerates it whole |
| [`developing.md`](developing.md) | the tool chains, building, testing, the tree, bank `$00`, releasing | its numbers by `make readme`; every path, link and `make` target it names by `tests/host/test_docs.py` |
| [`differences.md`](differences.md) | where gem4xe differs from an ST and from EmuTOS, each with where | the same: every file it names must exist |
| [`gates.md`](gates.md) | every gate and what it proves, then the history | the README's old gate table and log, moved; `tests/host/test_readme.py` checks the table against `make test` |

The README is now a front page: what it is, pictures, the guides, why it
is shaped as it is, the licence.  `make docs` regenerates everything that
is generated.

## What writing them found

Five statements that had been true and were not any more:

- **`appl_getinfo(AES_SYSTEM)` said there were no colour icons**, and a
  new-format resource that had to load far would be refused -- true until
  phases 86 and 87.  It now answers 1 on the 16-colour screen, where they
  are drawn (`src/aes/appl.c`); m11 checks it.
- **The ANTIC screen was "320 x 168"** on the release page and in three
  source comments; phase 71 made it 192 lines.
- **The kit's README** said a `G_CICON` draws its mono form, that
  `menu_popup` is not served, and that a resource must fit the pool; a
  large-data program's goes far, and colour icons are drawn.
- **The kit's `rsrc_load` binding** said the AES goes far only when the
  file will not fit; it goes far whenever the program can take it.
- **The release page** said there was no rubber band and no SHIFT-click,
  and that nothing uses the clipboard.

And `api.md`'s new tables show two gaps that are real: `wind_get` answers
neither `WF_KIND` nor `WF_NAME` nor `WF_INFO`, and no window colours are
served.  They are listed as such rather than fixed here.

## The tests

- `test_opcodes.ApiIsCurrent` and `test_dist.GuideIsCurrent`
  regenerate their pages and compare them whole; each was made to fail by
  editing the committed page.
- `test_docs` checks the hand-written guides' paths, links and `make`
  targets, and proves on a fixture that it reports a broken one.
- `test_readme` reads the version from the front page, the host count and
  the gate table from `gates.md`, and the compiler's defect count from
  `developing.md`.
