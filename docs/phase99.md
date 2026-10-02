# Phase 99 -- SpartaDOS 3.2's root fallback, measured, and Fdelete

Item 13 of `roadmap-0.12.md`: "its 'is it still there?' open can find
the root's file too (phase 65 fixed `Fopen`'s); and MyDOS measured for
the same".

## When the fallback happens

Phase 65 saw it on the product disk: copying into `GEM`, the desktop's
`Fopen` of `>GEM>X32G.DOS` opened the root's file.  Its fix,
`gd_in_dir`, asks the folder's own entries before an open for reading
on SpartaDOS.  But m15, which runs GEMDOS on SpartaDOS 3.2, never saw
the fault, so a first case added there passed with or without the fix.

With the guard taken out, eight raw opens -- `TEST.TXT`, `X32G.DOS`,
`M3.COM` and `OUT.TXT`, in `\SUB` and in `\SUB\DEEP`, none of them
there -- all answered "not found".  The difference is **the DOS's own
current directory**:

- m15's runner is typed at the root;
- the product disks' `STARTUP.BAT` does `CD >GEM` first.

With the runner started after `CD >SUB`, every one of the eight opened
the root's file.  SpartaDOS 3.2 looks in the root for a name it cannot
find, when its own directory is not the root, whatever path the open
names.

## Fdelete

`Fdelete` asks "is it still there?" when the DOS answers a delete with
"not found", because SpartaDOS erases around a protected file and says
not found ($AA): a file still there was refused, `EACCDN`.  It asked by
opening the file.  So with the DOS in a folder, deleting a missing
`A:\SUB\TEST.TXT` answered `EACCDN` -- the root's `TEST.TXT` opened.
The delete itself did not fall back; the root's file survived.

The witness is now the folder's own entries on SpartaDOS (`gd_in_dir`),
as for `Fopen`: missing is `EFILNF`, and a locked file in the folder is
still `EACCDN`.

## The gate

`make test-m15s` (new) is m15 with SpartaDOS 3.2's own directory in
`>SUB`.  The runner is started by `CD >SUB` and `>M3`
(`tests/emu/m14_sparta.py`'s `boot` takes the program to type).  It
checks:

- the root's names are not found through `\SUB` or `\SUB\DEEP`;
- `Fdelete` of one answers `EFILNF`;
- the root's `TEST.TXT` still opens;
- a file made and locked in `\SUB` is refused, and is deleted once
  unlocked.

Before the fix it failed on the delete, with -36.

## MyDOS

Nothing to measure: gem4xe treats MyDOS as a DOS 2 (`src/sys/dos.c`,
`dirsep` 0), so a path on it is its last component and no open is ever
made inside a MyDOS folder.  `docs/differences.md` had listed MyDOS among
the DOSes with folders, and now says gem4xe does not use them.
