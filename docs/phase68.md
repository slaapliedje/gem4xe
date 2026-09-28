# Phase 68 -- QED ships

Item 5 of 0.9 (`docs/roadmap-0.9.md`): QED, the Atari ST's GEM text
editor, ported in phases of its own since 2026-09-18 and gated in its
own tree, now goes out with gem4xe.

## Its licence, and the kit's

QED's only terms are its author's, from 1994 (`dist/liesmich.txt` and
`doc/qed-en.stg` in QED): public domain including the sources, anyone may
change it and publish changed versions -- and nobody may distribute it
for a fee of any kind.  That last clause could not sit in one program
with gem4xe's application kit while the kit was GPL, which lets anyone
sell copies and forbids further restrictions.  So the kit became
LGPL-2.1-or-later (`docs/licence.md`), which is what a library a program
links is for.  The program is four parts on four sets of terms --
QED's, the kit's and cflib's LGPL, and the Apache 2.0 of the NuttX code
in Calypsi's C library -- and its NOTICE says so.

## Where it is

The port lives in its own repository (`slaapliedje/qed-gem4xe`, QED's
tree with a `gem4xe/` directory), because it is QED's code on QED's
terms rather than gem4xe's.  This tree takes the built program from
there: `QED` in the Makefile names the port's directory, and
`build/qed/` holds `QED.PRG`, `QED.RSC`, `QED.TXT` (the NOTICE) and the
two licence texts it names.

| | |
|---|---|
| the card (`gem-cf.img`) | in `\APPS\`, when QED has been built -- the card is a gate's disk too, and a tree without the port still builds and tests |
| `gem-qed.atr` | QED and its notices in `\APPS\`, with the applications floppy's `INSTALL.BAT` |
| the release folder | the five files in `system/`, each with its line on the page |

**`gem-qed.atr` is 720 KB, an image and not a floppy.**  QED and its
resource are 361 KB, and a double-sided double-density disk holds 360.
Whatever reads an image reads it -- an SIO emulator, a FujiNet, a
loader, SDX mounting it -- and `-INSTALL D2:` from it puts QED on a
drive beside the rest.  `QED.PRG` is not packed: G4Z (phase 57) packs
`GEM.COM`'s far image, not a program's, and a program packed the same
way would be a 1.0 speed item that also fits a floppy.

`make release` needs QED built and says how when it is not.

## The port's gate, again

The port's `make check` had been red since gem4xe renamed programs to
`.PRG` (`e9213f3`): its disk carried the desktop as `DESKTOP.G4A`, the
shell found no `DESKTOP.PRG`, and GEM went back to the DOS after its boot
screen.  With the names fixed it passes whole -- QED launched from
gem4xe's own desktop, its 33 KB resource in far memory, a document typed
and saved through the file selector.

`tests/host/test_qed_ships.py` holds the three lists to the same five
files, requires the page to say QED may not be sold, and checks the
image has room; without `QED.TXT` in the card's table it fails twice.
