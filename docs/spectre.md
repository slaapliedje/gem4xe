# Spectre GS -- Apple IIGS Toolbox programs on gem4xe

Spectre GS runs unmodified Apple IIGS desktop programs on gem4xe.  A IIGS
program is 65816 machine code, as gem4xe is, so on a Rapidus or an Antonia
it runs as it is: what it needs from the machine is the IIGS's **Toolbox**
and **GS/OS**, and Spectre GS answers both.  The name is a nod to David
Small's Spectre, which ran Macintosh software on the Atari ST -- the user
means to ask him for his blessing on it.  Unlike Spectre, no Apple ROM is
involved: every call is written here from Apple's published references
(the *Apple IIGS Toolbox Reference*, volumes 1-3, and the *GS/OS
Reference*), never from Apple's code.

What can run: programs that reach the machine only through the Toolbox and
GS/OS.  What cannot: programs that write the Super Hi-Res screen at
$E1:2000 themselves and expect to see it, use the IIGS's `$C0xx` soft
switches, or play the Ensoniq sound chip -- most games and demos.

`gem4gs` is the other direction, gem4xe ported to the IIGS; not started.

## How it runs

`SPECTRE.PRG` is an ordinary gem4xe program (`src/spectre`).

- It takes **bank $E1** from gem4xe with `Mclaim` (GEMDOS `$1F2`, new for
  it: memory at a fixed address, `far_claim` in `src/sys/farmem.c`).  A IIGS
  program calls the Toolbox at `$E1:0000` and draws at `$E1:2000` by
  address, so those must be real and Spectre's.
- At `$E1:0000`, `$E1:0004` and `$E1:00A8` it puts `jml`s into its own
  dispatchers (`src/spectre/sgabi.s`): the Tool Locator's two entries and
  GS/OS's.
- It **loads the program** (`sgomf.c`): a GS/OS load file, Object Module
  Format version 2 (GS/OS Reference, appendix F) -- static segments into
  memory Malloc'd from gem4xe, two passes, then the data and relocation
  records (LCONST, DS, CONST; RELOC, INTERSEG, cRELOC, cINTERSEG, SUPER).
  Every segment is a Memory Manager handle, as GS/OS's loader makes it.
- The program's **bank $00** -- its 4 KB direct page and stack (GS/OS's
  default for a program with no stack segment), QuickDraw II's three
  pages, and anything else asked for in bank $00 -- is an arena in
  Spectre's own near memory.  So gem4xe sees one program whose stack is its
  own, and its stack floor (phase 114) holds.
- It runs the program as GS/OS starts one: A = its user ID, D = the bottom
  of its direct page/stack, S = the top.

A Toolbox call is served in C, on the caller's stack, with Spectre's own
direct page and DB = $00 put back first.  The convention is volume 1's
table 2-3: inputs off the stack, output space left, D and DB the
caller's, the error in A and the carry.  **A call not written yet stops the
program and says which** (`sg_why`, `sg_what`): nothing is guessed.

## Milestone 1 -- done

`tests/iigs/sghello.c`, built with ORCA/C, starts the Tool Locator, the
Memory Manager, Misc Tools and QuickDraw II, clears the screen, paints a
rectangle, frames another, and draws two lines of text.  `make test-sg1`
runs it on MAME's apple2gs against Apple's own Toolbox and on gem4xe
under Spectre GS, and compares the Super Hi-Res area byte for byte:
every pixel outside the text, all 256 SCB bytes and palette 0 are equal.

What ORCA/C's run-time start-up asked for on the way, in order, each
served as the reference says (the program only draws):

| call | | Spectre's answer |
|---|---|---|
| `$1A02` FindHandle | its own code's handle | the segment's handle: segments are handles |
| `$060A` SANEStatus, `$020A` SANEStartUp | floating point | housekeeping only; arithmetic is not served |
| GS/OS `$2037` GetStdRefNum | stdin/out/err already open? | `$60` dataUnavail: nothing is open |
| GS/OS `$200A` GetPrefix | prefixes 8-12 | 8 and 9 `:D1:`, the rest null |
| GS/OS `$2038` GetRefNum | is it open? | `$60` |
| GS/OS `$2010` Open | the null prefix 10 | `$40` badPathSyntax for an empty path; any other path is not served yet |
| `$1002` DisposeHandle | | freed |
| GS/OS `$2039` GetRefInfo | | `$43` invalidRefNum |

### Text

Spectre draws text in gem4xe's 8x8 font (EmuTOS's, GPL).  The IIGS's is
Shaston 8, Apple's, in Apple's ROM: a program on MAME asked QuickDraw for
it with `GetFont`, and System 6's font handle does not hold the font record
volume 2's figure 16-25 documents (no `offseToMF` = 6, no family $FFFE).
Working out what it does hold would be reading Apple's code, which this
project does not do.  So the gate compares the text by where its ink is --
the same rows on both, 53-60 and 73-80 -- and everything else exactly.
A Shaston-compatible font of our own, or a IIGS font file the user
supplies, is for later.

### The compiler

cc65816 -O2 compiled `super()`'s subrecord loop wrong: with `c` a byte,
it tested `c & 0x80` in the HIGH half of a stack word and then took
`c + 1` from the LOW half -- a stray byte -- so every count of patches
was wrong, most relocations were skipped and the rest went astray; the
first program run wrote over bank $00 and the machine ran away in a BRK
loop.  It is B23's family (a byte tested in a chain, read back from the
wrong place), in a new spot.  Every byte local in Spectre that is tested
or compared is a word now.

## Next

- Show the screen: the Super Hi-Res buffer at $E1:2000 onto the VBXE's
  640-pixel mode.
- The Event Manager, so a program can wait for the mouse and keys.
- GS/OS files, through gem4xe's GEMDOS.
- The loader into gem4xe's own program loader, so a `.S16` runs from the
  desktop.
- Strings: Spectre's two alerts are in the C; they go to LANG.RSC before
  it ships.
