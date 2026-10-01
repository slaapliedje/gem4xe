# Phase 90 -- DESKTOP.INF beside GEM4XE.CFG

The desktop kept its layout where TOS keeps it, in the root of the boot
drive: `A:\DESKTOP.INF`.  On gem4xe's own media everything else of the
system is in `\GEM\`, and the root is the user's.  Now DESKTOP.INF is
written beside GEM4XE.CFG -- `\GEM\` on the card and the SpartaDOS X
floppy -- and GEM4XE.CFG can put it anywhere else:

    DESKINF=D1:\GEM\DESKTOP.INF     ; or A:\..., \DIR\NAME, or NAME

`D1:` to `D9:` are the desktop's names for `A:` to `I:`.  A bare name is
beside GEM4XE.CFG; `\DIR\NAME` is from the root.  The system skips the
key, as it skips any it does not know (src/sys/config.h), and the
desktop reads it.

**An older layout is not lost.**  When there is no DESKTOP.INF beside
GEM4XE.CFG and GEM4XE.CFG names none, the desktop reads the root's, once.
The next Save desktop puts it in the new place.  The old file is left
alone.

## By a name with no path

The desktop opens `GEM4XE.CFG` and `DESKTOP.INF` with no drive and no
directory.  That is where the system found GEM4XE.CFG at boot -- it looks
for "D:GEM4XE.CFG", the DOS's current directory -- and so it is the
folder GEM.COM was started from, whatever the medium calls it.

That needed one change in GEMDOS (src/sys/gemdos.c, gd_name).  GEMDOS
made every name absolute from its own current directory, which is the
root until a program sets one, so a bare name meant the root.  The AES
already handed a bare name to the DOS as it is, which is how a program's
resource is found beside it (gd_cioname).  GEMDOS now does the same: a
name with no drive and no backslash, on a drive whose directory no
program has set, goes to the DOS's current directory.  A program the
desktop starts has its directory set first (run_prog), so for it nothing
changes.  Dgetpath still answers "" in that state, all GEMDOS can say of a
directory it was never told.

The desktop sets a directory only in run_prog, on its way out to a
program; when that fails, nothing was set.  So the layout cannot follow a
refused program into its folder, which `A:\` + Dgetdrv() could, the
drive having been changed first.

GEM4XE.CFG is read in 128-byte pieces until the key is found, only when
the layout file is: the first desktop after a boot, Save desktop, and
Read .INF file.  A desktop coming back from a program reads neither.

## Gates

- `test-m19` puts a hidden GEM4XE.CFG on its disk whose DESKINF line is
  past the first 128 bytes, with spaces round its `=`, `D1:` for `A:` and
  a comment after it.  Save desktop must write LAYOUT.INF, and Read .INF
  file read it back.  Hidden, because the gate's clicks and rubber band
  are laid out on the root window's listing: a first try with the file
  showing moved every item after it, and the band deleted GEM4XE.CFG with
  the rest before Save desktop ran.  tools/atr.py's add_file can set
  SpartaDOS's hidden bit now.
- `test-boot`: the SpartaDOS X floppy's first desktop reads GEM4XE.CFG
  from `\GEM\`, finds no key, and looks for DESKTOP.INF there and then in
  the root.  tools/aesref.py resolves a bare name as GEMDOS now does, in
  the folder of the listing's DESKTOP.PRG, and knows a file's bytes only
  where a gate gives them (dos_text).
- `test-boot`'s floor for the DOS 2 floppy is now the longest layout
  `inf_write` can write (1,070 bytes: six sectors with the directory
  entry), computed from the C's sizes, instead of the 4,192-byte shell
  buffer (twenty).  This phase and the two before it took the floppy to
  16 sectors free; DUP.SYS, which would have freed twenty, stays, because
  it is what Quit returns to (docs/shipping.md section 1).
