# EDIT

A small text editor, for a CONFIG.SYS, a batch file, a README.
`EDIT.PRG` and `EDIT.RSC`, in `\APPS\`.  QED stays the big editor; EDIT
is the one that is always there.

The QED patch for Atari 8-bit line ends was turned down upstream
(freemint/qed #16): QED is meant to be a plain-text editor for the ST,
and ATASCII's own characters are beyond it anyway.  An editor written
for this machine can do both.

## Opening a file

- **From the desktop:** double-click a document, choose **Show**, and
  press **Return** in the window that shows it.  The alert stays Show /
  Print / Cancel -- an alert has at most three buttons -- and Show is the
  read-only viewer it always was until Return is pressed.
- The desktop looks for `EDIT.PRG` in `\APPS\` on the document's own
  drive first, then on every other drive the DOS has, so the
  applications floppy can be in any of them.  With no `EDIT.PRG`
  anywhere, Return does nothing and Show is the viewer it was.
- **Options -> Install application** can give a type, such as `TXT`, to
  EDIT, so that a double-click opens it straight away.  A file dropped
  on `EDIT.PRG` opens too, and `EDIT.PRG` run on its own asks for a
  file -- a name that is not there yet is a new file.

## Keys

One window on one file.  The info line says where the cursor is and
which line ends the file has.

| key | does |
|---|---|
| arrows | move.  Shift and up or down moves a window's height; Shift and left or right goes to the line's start or end |
| typing | inserts at the cursor |
| Backspace / Delete (Control and Backspace) | delete before / at the cursor; at a line's end they join two lines |
| Return | splits the line, with the file's own line end |
| Tab | inserts a tab: $7F in an Atari file, $09 in any other |
| ^S | saves |
| ^O | opens another file |
| Esc, ^Q, or the closer | ends EDIT, asking Save / Discard / Cancel if the text has changed |

A click puts the cursor where it lands.  The menu bar has Desk, for the
accessories, and File.  The keys are a GEM program's, not vi's: someone
who opened a file from the desktop expects to type.

## What it keeps

**Every byte it is not asked to change.**  Inverse video, ATASCII
graphics, control characters and stray CRs are written back as they
were read.

**The file's own line ends**, found when it is opened, by the first
$9B, CR or LF in it:

| first one | the file is | a line ends with | the info line says |
|---|---|---|---|
| $9B, or none at all | an Atari one | $9B | Atari ($9B) |
| CR then LF | an ST or PC one | CR LF | CR LF |
| LF alone | a Unix one | LF | LF |
| CR alone | a Mac one | CR | CR |

Only that kind ends a line; any other is a character.  So a $9B in an ST
file is its cent sign, and a CR in an Atari file -- ATASCII's Control-M
graphic -- is shown, not taken for a break.  The FIRST one decides,
rather than "any CR or LF anywhere", because either of those is rare
before a file's first line has ended.  A new file is an Atari one.

## How it looks

An Atari file is drawn in the Atari's own characters: the graphics
($00-$1F, $60, $7B, $7D-$7F) as the machine draws them, and inverse
video white on black.  The system font is the ST's, which has the
ASCII the two share and other pictures for the rest, so EDIT reads the
character set out of the OS at start-up into a one-plane form and
copies each graphic from it with `vrt_cpyfm`; the rest of a line is the
system font, a run at a time.  Atari's ROM font is copyrighted, so it
is read from the machine and never shipped.  It is checked before it is
used -- a space must be blank and an A must not be -- and on a screen
whose characters are not 8 by 8 (the ANTIC driver's are 6 by 6), the
graphics are drawn as the ASCII that shares their code.

An ST or PC file is drawn in the system font, byte for byte, as QED
draws it, with a tab every eight columns.

## Limits

**32 KB.**  The text is a gap buffer in one 40 KB block of far memory --
32 KB of file and 8 KB to type into -- and a block from `Malloc` never
crosses a bank, so no pointer arithmetic does either.  A larger file is
refused with an alert, never opened cut short, so a save can never
truncate one.  (Show itself still shows only the first 16 KB of a
file.)

Not in this version: find and replace, undo, blocks and the clipboard,
more than one file, a vi mode.

## Saving

The text is written beside the file as `EDIT.TMP`, the file deleted,
and `EDIT.TMP` renamed to its name, so a full disk leaves the file as
it was.  A DOS that cannot rename -- the SpartaDOS X 4.49e that Ultimate
1MB firmware 4.0 and 4.20 carry -- has the text written over the file
instead, the copy in `EDIT.TMP` being safe already, and the copy is
deleted once that has worked.  If even that fails, the alert says the
text is in `EDIT.TMP`.

## How it is built

- `src/apps/edbuf.c` is the text: the gap buffer, the line-end rules,
  the cursor's moves and the line count, kept right by counting line
  ends only in the few bytes around each change.  Portable C; nothing in
  it touches a file.
- `src/apps/edit.c` is the GEM program around it, built
  `--data-model=large`: the text and the glyphs come from `Malloc`, the
  resource goes far, and what must be in bank $00 -- the file selector's
  buffers and the MFDBs `vrt_cpyfm` is handed -- is on the stack.
- `tools/editrsc.py` makes `EDIT.RSC`: the menu, the About box and
  every word EDIT says.
- `src/desk/deskcmd.c` keeps the shown file's path beside the viewer's
  text, and `cmd_edit` hands it over on Return; `do_edit` in
  `src/desk/deskwin.c` finds `EDIT.PRG` and runs it.  Writing that path
  found compiler bug B26 (`tools/ccbug/README.md`): a far pointer kept in
  the direct page, indexed by a variable, is dereferenced as a near one.

## Gates

`make test-edit` runs both halves.

- **On the host** (`tests/host/test_edit.py`, through
  `tests/host/ed_host.c`): 19 cases written by hand from the rules above
  -- every kind of line end, CR LF stepped over whole, a lone CR in a CR
  LF file, a $9B in an ST file, graphics and inverse video kept, up and
  down through tabs; files of every kind loaded and written with no key
  pressed, byte for byte; a full buffer and an oversized file; and 239
  runs of random keys on awkward files against a model in Python
  written from the same rules, text, cursor and line count compared
  after each.  Breaking the CR LF rule failed it 73 ways, and masking
  bit 7 in the gap's move 224.
- **On the emulated Atari** (`tests/emu/edit.py`): the product
  SpartaDOS disk with EDIT, four documents, and the desktop driven as a
  person drives it -- double-click, Show, Return.  An Atari file and an
  ST file are typed into and saved; an ATASCII file is shown in the
  machine's own glyphs -- found on the screen by the bytes of its
  character set -- and in inverse video, and saved unchanged; a 40 KB
  file is refused.  Each file is read back off the disk image and
  compared byte for byte, and no `EDIT.TMP` may be left.  EDIT built
  without its glyphs failed the screen check.
- `make test-m41` adds the other side: on a disk with no `EDIT.PRG`,
  Return in the viewer leaves it as it was.
