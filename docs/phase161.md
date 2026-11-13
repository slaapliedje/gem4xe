# Phase 161 -- MyDOS's folders, and DOS 2 says it has none

The DOS dependencies, put ahead of running plain programs.  MyDOS 4.x is
DOS 2's file system with folders, and gem4xe treated it as a flat DOS 2.
A folder made by MyDOS's own DUP was invisible to the desktop, and New
folder was greyed.  DOS 2.0 and 2.5 have no folders at all, and nothing
said so.

## What MyDOS does, measured

Read from MyDOS 4.50's technical notes (TECH.DOC; the user guide's scan
for the menu), then asked of MyDOS 4.50T itself through the runner's raw
CIO.  Where the two disagreed, MyDOS won:

| asked | MyDOS 4.50T |
|---|---|
| make a folder | XIO 42, or its own 34, which the notes say is the same call "for compatibility with programs written for SpartaDOS" |
| a path | `D1:A>B>FILE` -- and `D1:>A>B>FILE`, SpartaDOS's form with a `>` after the colon, works too |
| a listing | ` :NEWDIR      0008`: `:` in column 1 marks a folder, where SpartaDOS X marks one; the count is four digits |
| rename a file or a folder | XIO 32, in its folder only -- "only the last name in a path can change" |
| remove a folder | XIO 33, delete, once it is empty (175 when not); SpartaDOS's XIO 43 is refused (168) |
| on the disk | a folder is an entry flagged `$10`, its start the first of eight sectors holding its 64 entries, as 361-368 hold the root's; a removed one `$80` |

## What changed

MyDOS stays a DOS 2 to gem4xe: its VTOC answers `Dfree`, and it is left
through DOSVEC.  But it gets folders:
- `dos_ident` gives it `DOS_CAP_DIRS` and `>`, so gem4xe's SpartaDOS-form
  paths reach it unchanged;
- two new capabilities, `DOS_CAP_RMDEL` (a folder is removed as a file is
  deleted) and `DOS_CAP_RENDIR` (a folder renamed in place);
- `Dcaps` answers folders and folder rename, never a move.

The listing parser needed nothing: it has read every digit from column
14 since phase 50, and its folder test reads the `:`.

**`Ddelete` must never delete a file.**  On MyDOS, a folder is removed
with the very call that deletes a file of the same name.  So there the
name is first opened as a folder's listing, and refused (EPTHNF) when it
will not open as one.  With that check taken out, the gate's
`Ddelete("A:\TEST.TXT")` deleted TEST.TXT.

**`Dsetpath`** opened a folder as its raw entries, which only the
SpartaDOSes give; on MyDOS it opens the listing instead.

`tools/atr.py` reads MyDOS's folders now (`DirEntry.is_dir`, `Dos2.entries`
and `find` taking `A>B>NAME`), so a gate can check what MyDOS wrote.

## DOS 2 says it has none

The boot screen's DOS line reads **"DOS 2, no folders"** on DOS 2.0 and
2.5, in all five of LANG.RSC's languages, and **"MyDOS"** on MyDOS.  The
guide gains a paragraph, "Which DOS":
- G4DOS (which the system floppy boots), SpartaDOS X and MyDOS 4.x give
  folders;
- DOS 2.0 and 2.5 cannot read the applications floppy and have no
  command line;
- on those, boot the system floppy instead.

DUP.SYS goes back to DOS 2.0S, not 2.5: 2.5 added the 1050's enhanced
density and the RAM disk, on the same file system without folders.  So
"use DOS 2.5" would not have helped.

## Gate

**`test-m66`**: the MyDOS 4.50T fixture with the runner on it
(`build/m15m-boot.atr`), loaded from MyDOS's DUP.  GEMDOS calls:
- `Dcaps` 0x3;
- folders made, nested;
- the root listing one as a folder;
- a file written into one, `Dsetpath` there, a bare name opened and read
  back;
- renames in place, refused to another folder, a folder renamed;
- `Ddelete` refused for a full folder and **for a file's name, the file
  kept**, done for empty ones.

Then the working copy with `atr.py`: KEEP a folder with K.TXT in it as
written, NEWDIR gone, TEST.TXT kept.

| broken on purpose | result |
|---|---|
| `Ddelete` without its folder check | `Ddelete("A:\TEST.TXT")` answers 0 and TEST.TXT is gone |

The gate's first runs failed every rename.  The gate passed `Frename`'s
two names from offset 6, where TOS's binding puts its reserved word
first (`Frename(0, old, new)`), so gem4xe renamed garbage.  test-m15
passes the zero; the gate does now.
