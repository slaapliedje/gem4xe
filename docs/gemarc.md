# GemARC

ARC archives on gem4xe: an archive listed in a window, its files taken
out, and new archives made.  `GEMARC.PRG` and `GEMARC.RSC`, in `\APPS\`.

## Using it

- **File -> Open archive... (^O)** chooses an `.ARC`.  The window lists
  its members -- name, size, packed size, how it was packed, and the
  date -- and the info line says how many there are and how well they
  packed.  Dropping an `.ARC` on `GEMARC.PRG` on the desktop opens it
  the same way; so does double-clicking one, once *Options -> Install
  application* has given `ARC` documents to GemARC.
- **Click** a member to select it, again to let it go.  **Archive ->
  Select all (^A)** selects them all, or none if they all were.
- **Archive -> Extract... (^E)** takes the selected members out;
  **Extract all...** takes every one.  The file selector asks for the
  folder: go into it and click OK.  If some of the files are there
  already GemARC asks once, for all of them: Replace, Skip them, or
  Cancel.  Every member's CRC is checked as it comes out; one that is
  damaged, or packed a way GemARC does not know, is not left behind
  half made, and the alert at the end says how many there were.
- **File -> New archive... (^N)** names a new, empty archive.
- **Archive -> Add files... (^I)** puts files in.  Choose one file, or
  type a pattern such as `*.TXT` in the selector's Selection field for
  every file that matches -- up to 64 at a time.  A member of the same
  name is replaced; the members stay in name order, as ARC keeps them.
  The archive is written beside itself as `GEMARC.TMP` and only then
  put in the old one's place, so a full disk leaves it as it was.
- **File -> Close archive (^U)**, or the window's closer, closes it;
  closing the empty window, or **Quit (^Q)**, ends GemARC.

A member's name is made a name the DOS takes before it is written:
upper case, letters, digits, `_` and the dot.  An archive made on a PC
can carry names an Atari DOS will not.

## What it reads and writes

| method | what it is | reads | writes |
|---|---|---|---|
| 1, 2 | stored | yes | yes |
| 3 | packed: repeated bytes counted (RLE) | yes | yes |
| 4 | squeezed: RLE, then Huffman | yes | no |
| 5-7 | ARC 4's crunching | no | no |
| 8 | crunched: RLE, then LZW to 12 bits -- ARC 5's, and the Atari's | yes | yes |
| 9 | squashed: LZW to 13 bits -- PKARC's | yes | no |

Each file put in is packed all three ways it can write, counted without
writing anything, and written the way that came out smallest -- as ARC
does.  Random bytes and files already packed come out stored.

On the 1,402 members of the Atari archives on hand when this was
written, 1,331 were crunched and the rest stored, packed or squeezed:
nothing used 5 to 7.

## How it is built

- `src/apps/arccodec.c`: the methods, written from the format rather
  than from anybody's ARC.  Crunching is Unix compress's LZW, down to
  its quirks -- codes in groups of eight, the rest of a group thrown
  away when the code size grows, the reader and writer growing it one
  code apart -- because that is what every ARC reads.
- `src/apps/arcfile.c`: archives -- listing, taking out, adding.
- Both are portable C over a handful of file functions: GEMDOS in
  `src/apps/gemarc.c`, stdio in `tests/host/arc_host.c`.  So the code
  the Atari runs is the code the host tests.
- `src/apps/gemarc.c`: the GEM program, compiled `--data-model=large`.
  Its 55 KB of tables and the member list come from `Malloc`, its
  resource goes to far memory, and the only things in bank $00 are the
  file selector's buffers, which must be.

## The gates

`make test-gemarc` runs both:

- `tests/host/test_gemarc.py`: every member of every `.ARC` under
  `[gemarc].dirs` in `fixtures.toml`, taken out by GemARC's engine and
  compared byte for byte with The Unarchiver's (`unar`); and archives
  GemARC makes of files built to be awkward -- empty, runs, the RLE
  escape byte, random bytes, 200 KB that fills the LZW table -- which
  `lsar -t` must pass and `unar` must give back exactly.
- `tests/emu/gemarc.py`: GemARC on the emulated Atari, driven by its
  shortcuts: `[gemarc].archive` opened and listed, every member taken
  out and compared with `unar`'s, a new archive made of the text files,
  and that checked by `lsar -t` and `unar`.

Breaking RLE90 by one repeat failed the emulator gate nine ways; the
CRC check is what catches it.

## Found on the way

The first build ran its stack through its direct page: 1,536 bytes were
too few for path buffers on the stack, and the compiler's pseudo
registers on the direct page were what went first -- a name pointer read
back as 0, then a return to $0004A2.  The paths are far statics now and
the stack is 2 KB; only `shel_read`'s and the file selector's buffers
are on it, because they must be in bank $00.
