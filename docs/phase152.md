# Phase 152 -- the desktop renames folders and moves by name

Asked for 2026-11-11: "We certainly want the gui to be able to rename and
move files."  The desktop could rename a file and could move anything,
but it could not rename a folder on any DOS.  A move was always a copy of
every byte and a delete, even on a G4DOS disk, whose file system moves
things in place.

| | was | now |
|---|---|---|
| a folder renamed in Show info | greyed on every DOS | on G4DOS, editable; greyed under SpartaDOS, which refuses |
| a SHIFT-drag on one G4DOS drive | a copy and a delete, file by file | a rename into place, a folder and all it holds |
| a folder dragged into itself | copied into itself, folder in folder, until the path was too deep | refused with an alert, on every DOS |
| a window open in a folder renamed or moved | left on a path that was gone | follows it |
| GEMDOS's `Frename` into another folder | the new name's last part, renamed where the file stood | a move on G4DOS; EACCDN under SpartaDOS; ENSAME across drives |

## GEMDOS

`Frename` with the new name in the old one's folder is a rename, as it
always was: CIO's XIO 32, whose new name is a name and no path.  In
another folder of the same drive it is a **move**, as TOS's `Frename`
is:

- **On G4DOS** the engine does it in place, through a new entry in its
  handler, `sdc_move`.  The engine's rename already took two paths and
  moved between folders (`src/sys/sdfs.c`, `sd_rename`).  It refuses a
  folder moved into itself, or onto a name already taken, with EACCDN.
- **Under SpartaDOS** the answer is EACCDN.  It used to take the new
  name's last part and rename the file where it stood, which nobody had
  asked for.
- **A name on another drive** is ENSAME (-48), TOS's answer.  Before
  this, it renamed the file on the first drive.

A program can't tell in advance which of these it will get, so there is
a new gem4xe call, `Dcaps`, GEMDOS `0x1F7`, with three bits for a drive:

- `DC_FOLDERS`: its paths carry folders.
- `DC_RENDIR`: `Frename` renames a folder.
- `DC_MOVE`: `Frename` moves to another folder.

G4DOS answers all three, SpartaDOS 3.2 and X the first, DOS 2 none.

## The desktop

- **Show info** asks `Dcaps` before it offers a folder's name for
  editing.  On SpartaDOS the field stays greyed, as before, rather than
  editable and always refused.
- **A SHIFT-drag** within one drive that moves goes by name, item by
  item.  Where the name is taken in the destination, the item falls back
  on the copy, whose questions handle a taken name; so does an item the
  DOS will not rename.  This is EmuTOS's own rule (`deskdir.c`, a move on
  one drive made `OP_RENAME`).  The dialog's counters go down by what
  went: a folder's contents are counted again where they are now.
- **A folder dropped into itself** or into a folder inside it is
  refused.  This is EmuTOS's `source_is_parent`, which gem4xe's desktop
  never had.  A copy used to copy what it had just made until the path
  was too deep.  The alert is a new string of DESKTOP.RSC, `STINSELF`.
- **A window open on a folder that is renamed or moved**, or on one
  inside it, has its path changed to follow (`win_follow`).

The copy-and-delete move still leaves such a window on a path that is
gone, as it always did.

## Three banks again

The desktop's code grew 1,370 bytes this phase, from 49,053 to 50,423,
and a 65C816 with 512 KB -- three banks for the far heap, `test-m37`'s
`m37three` -- could no longer start it.  The desktop's code has to be
page-aligned and end below $D500 in its bank, so at 50,423 bytes it has
to start within the first $1009 bytes of one.  At boot every bank's foot
was taken.  The calculator accessory's 3,501 bytes of code sat at bank
7's, $070000.  The margin had been 611 bytes, and inlining was not the
cause: with it off the desktop is 50,688.

The calculator was there because of phase 139's in-place loading.  A
squeezed program is unpacked into a block placed so that its code
already sits where code can run.  When that block runs into the next
bank, the code lands at that bank's foot -- the one place a big
program's code can go.  So in place is now for a big program only, code
of 16 KB or more (`V6_INPLACE`, `src/sys/app.c`): the desktop, the
control panel, QED.  A smaller one is loaded the way everything was
before phase 139.  Its image is unpacked at the top of the heap and its
code copied to the lowest page that holds it, which is a hole low down.
The calculator's code is in bank 6 now, at $06BA00, and the desktop's
starts at bank 7's foot with 4,105 bytes to spare.  The settled 960K
boot reaches $083430 where it reached $08C4F7.  Before the change, with
every program in place, `m37three` was refused, as the suite found.

`test-edit`'s disk, the product SpartaDOS disk's size, came out two
sectors short for its 40,000-byte BIG.TXT once GEM.COM and the desktop
had grown.  It has 2816 sectors of its own now.

## The DOS 2 floppy's room

The desktop's growth was 769 bytes of the squeezed `DESKTOP.PRG`, four
sectors of the double-density floppy that boots a DOS 2, and `GEM.COM`
took one more.  The floppy had been exactly at its floor, 6 sectors, the
most `DESKTOP.INF` can take, and went to 1 (`test-boot`).

`DESKTOP.RSC` goes on that floppy squeezed now: 28 sectors to 11, as a
squeezed program is, "G4A" 6, the length and one G4Z stream
(`tools/squeeze.py`).  The AES reads the desktop's own resources into a
cache in far memory (phase 120), and unpacks a squeezed one as it fills
it (`src/aes/rsrc.c`, `rc_unsqueeze`).  A resource cannot begin with
those bytes, so a real one is never taken for one.  The floppy has 17
sectors free.  Every other disk keeps the plain file, which an RCS can
open.

A squeezed file read straight from the disk -- a program's, or the
desktop's own when there is no room for the copy -- is refused by
`rs_load` on its first three bytes.  The first version only said so in
its comment.  Taken as a resource, the bytes ran off into a BRK, which
the break run of the unpacking showed: the desktop faulted in its
seventh call.

## The desktop's model

`test-m19` runs the desktop on SpartaDOS 3.2 against `tools/deskref.py`,
and the model makes every call the desktop makes.  Show info on a folder
now asks `Dcaps`, so the model asks too.  `tools/aesref.py` answers 1,
folders and nothing more, as the SpartaDOSes do.  The model also refuses
a folder into itself, and it raises an error rather than guess at a move
by name, which none of its gates' DOSes make.  Without the call, `m19`
went out of step at its first folder Show info.

## Gates

- **`test-m15`** checks `Frename` and `Dcaps` on every DOS it boots:
  - G4DOS renames a folder; moves a file (read back intact) and then a
    folder with what it holds; refuses a folder into itself and a name
    already taken.
  - SpartaDOS 3.2 and X answer -33 for a folder and EACCDN for a move,
    the file left where it was.
  - DOS 2 has no folders.
  - Every DOS answers ENSAME for another drive.
- **`test-m12`** loads a squeezed resource the way a program does,
  straight from the disk: refused, no fault, no pool kept.
- **`test-boot`** boots the DOS 2 floppy with its squeezed `DESKTOP.RSC`
  into the desktop, compared with the model.
- **`test-m60`**, new, is the desktop on the G4DOS system floppy, with a
  tree of the gate's own and two windows:
  1. A file SHIFT-dragged onto a folder.
  2. A folder dragged the same way, with a window open on it.
  3. The destination folder renamed in Show info.
  4. That folder dropped into the window inside it.

  The disk is read back afterwards. Each moved or renamed thing has the
  sector map it had before, which a copy and a delete would not keep.
  The window followed both the move and the rename. The alert's text is
  found in bank $00, so the refusal was the alert, not a drop that missed.

Each check was seen to fail first:

| broken on purpose | result |
|---|---|
| `Frename` across folders never through the engine, `Dcaps` without G4DOS's bits | m15g: `Dcaps` 1, the file not moved, the folder not moved |
| `Frename` without the other-drive test | m15d: EACCDN, not ENSAME |
| the desktop never moving by name | m60: the maps changed (966 to 972, 960 to 974), the window not following |
| `win_follow` doing nothing | m60: the window left on `MVT\SRC` |
| Show info's folder name never editable | m60: nothing renamed |
| the into-itself test never true | m60: no alert, and NEW copied into itself, `MVT>NEW>SRC>NEW>SRC...` |
| the resource cache not unpacking | test-boot: the desktop faulted in call 7 on the DOS 2 floppy |
| `rs_load` not refusing a squeezed file | m12: the runner never finished |

The gate's first drop for step 4 missed the window and landed on the
desk.  Nothing happened, so every check that says "nothing moved" passed.
The alert check failed, which is what it is there for.  The drop point
is now taken from the window's own box.
