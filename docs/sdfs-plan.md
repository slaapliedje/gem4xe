# GEMDOS's own SDFS: folders where G4DOS is the DOS

Agreed 2026-11-02, and steps 1 to 3 BUILT the same day: G4DOS's disks
have folders under GEM, held by `test-sdfs`, `test-m15g` and `test-fdos`.
The steps say what each one is and how it is tested; step 4 is what is
left.

## Why

G4DOS (`src/fdos.s`, [fdos.md](fdos.md)) reads and writes SDFS, but as a
DOS 2 does: one flat view, the root and one folder down, new files in the
root.  Real folders -- paths, `Dcreate`, `Ddelete`, a current directory
per drive -- do not fit where it lives.  It was 4,715 bytes of code and
five sector buffers in bank $00, from `$0700` to `$1FFF`, and `$2000` is
gem4xe's direct page: there is nothing left to grow into.

gem4xe has room where G4DOS has none: far memory, megabytes of it, and a
65C816 to run C in.  So the folders go **there**.  When the DOS is G4DOS,
gem4xe stops handing its disks to G4DOS's handler and reads and writes
the SDFS on them itself, through G4DOS's sector routine; when it is
anything else --
SpartaDOS X, a SpartaDOS 3, a DOS 2, MyDOS -- nothing changes.

This is the DOS/TOS hybrid: GEMDOS is the API every program sees, as on
the ST; the file system under it is gem4xe's own C; G4DOS is what boots
the machine and what a program run outside GEM uses.  It is also the
shape a multitasking gem4xe would keep ([multitasking](multitasking.md)):
one engine, one lock at its entry, every open file owned by a process.

## What stays as it is

- **G4DOS**: the flat view, writes to the root, one file being written at
  a time.  It is still the DOS for a program run without GEM, and it
  loads GEM.
- **Every other DOS**: GEMDOS over CIO, exactly as today.
- **The disk format**: SDFS as `tools/atr.py` writes it, which is what
  SpartaDOS X reads and writes.  A disk written by either side is a disk
  the other, and SpartaDOS X, read.

## The steps

### 1. The engine, on the host first

`src/sys/sdfs.c`: SDFS in portable C, knowing nothing of GEMDOS or CIO.
Below it a sector device -- read or write sector *n* of unit *u* -- and a
small cache of sectors; above it:

| | |
|---|---|
| mount | a unit's superblock: sector size, root, bitmap, sector count |
| paths | `\DIR\SUB\NAME.EXT` to a directory and an entry, folders to any depth |
| directories | each entry in turn: name, attributes, length, date and time |
| files | open, read, write, seek, close; create and truncate |
| changes | delete, rename, a folder made and removed, attributes, a stamp |
| space | free and total sectors |

The rules are G4DOS's, which are `tools/atr.py`'s: the first free sector
at or after a hint, map pages linked both ways, a directory grown a
zeroed sector at a time, and the same order on the disk -- a file's first
map page and its entry at create, its data until the map that names it
goes down at close -- so a RESET part way through leaves a disk SpartaDOS
reads.

**Tested on the host**, as EDIT's text engine and GemARC's codec are
(`tests/host/ed_host.c`, `arc_host.c`): the same `sdfs.c`, built by gcc,
run against an ATR file by `tests/host/sdfs_host.c`, and
`tests/host/test_sdfs.py` checking every result with `tools/atr.py` --
each file's bytes, each listing, and `Sdfs.check()`, the consistency check
G4DOS's gate uses -- including long random sequences of operations
compared against the model.  Both sector sizes.

### 2. The sector path on the Atari

G4DOS gives gem4xe its sector routine, `fd_xsec`, behind a header at a
fixed place (`src/fdos.s`):

| | |
|---|---|
| `$0706` | `G4`: G4DOS is there, and `src/sys/dos.c` says `DOS_G4DOS` |
| `$0708` | the unit |
| `$0709` | bit 0 write, bit 7 a 128-byte sector; bit 6 alone asks where G4DOS's data buffer is, answered in A and X |
| `$070B` | `JMP fd_xsec` |
| `$070E` | the sector |

It reads or writes the sector with the OS's SIO through G4DOS's own data
buffer, and keeps G4DOS's caches true: the buffer is tagged with what it
now holds, and a sector written is no longer what the map buffer or the
bitmap buffer say they hold.  Carry set is a failure, and DSTATS says
which.  gem4xe calls it the way it calls into SpartaDOS X
(`sdx_call`, `src/sys/cio.s`: emulation mode, the OS's interrupts) and
copies the sector to and from the engine's cache in far memory
(`sd_dev`, `src/sys/sdcio.c`).  Nothing new in bank $00 on gem4xe's side
but one far pointer; G4DOS's header grew by nine bytes.

### 3. GEMDOS on the engine

Not where this plan first put it.  GEMDOS is not the only thing in gem4xe
that opens files: the file selector, the shell's scans for AUTO
programs, control panel modules and accessories, the program loader and
the resource loader all call `src/sys/cio.c` themselves.  Routing GEMDOS
alone would have given the desktop folders and left the selector flat.
So the engine is behind **CIO's D:** instead (`src/sys/sdcio.h`):

- from `gemdos_init` on, a D: name that `cio.c` is given goes to the
  engine, and an IOCB the engine has is marked with an ICHID of its own,
  so every later call on it comes back to the engine too; nothing above
  `cio.c` changed;
- the DOS is described as SpartaDOS is -- directories, the raw 23-byte
  listing, stamps, `>` between folders -- and the engine answers in
  SpartaDOS's terms: its listings in SpartaDOS X's line form or as raw
  entries, its errors as the statuses `gd_err` turns back into GEMDOS's;
- a **bare name** -- no `>` in it -- keeps G4DOS's meaning: the root,
  then each folder of the root.  That is how gem4xe finds its own files
  (`gd_cioname`), and the boot's reads before `gemdos_init` go to G4DOS
  itself, which finds them the same way;
- the engine reads sector 1 again once an operation (`sd_recheck`), not
  once a call, so a lookup through five folders costs one read of it.

Tested where it is used: `test-m15g` runs GEMDOS's whole gate on a G4DOS
disk -- listings down the tree against the image, files read and written,
`Fseek`, `Fdatime`, rename, lock, delete, folders made, renamed and
removed, `Dfree` -- and checks the emulator's working copy with
`Sdfs.check()` afterwards; `test-fdos` opens the system's folder and the
applications' from the desktop and runs EDIT out of one.

Not done yet: `Fdatime` cannot set a stamp (the engine can, `sd_fstamp`;
GEMDOS answers EINVFN on every DOS), and a backwards `Fseek` still
reopens and reads forward, as on every DOS, where the engine could seek.

### 4. After

- G4DOS on the cartridge, with the ROM on its own drive (D5:, or the
  first free one after it) and the floppies served without a DOS booted
  first -- which also takes away the OS's wait for a disk at a cold start
  ([cartridge.md](cartridge.md), section 9).
- The engine's cache tuned by `make bench-boot` and G4BENCH.
- A lock at the engine's entry and handles owned by processes, when
  multitasking comes.

## What it costs

Far code and far data only, on gem4xe's side: the engine, its cache
(eight sectors to start with, more if the benchmarks say so), and a
record per open file and per IOCB -- about 2.9 KB of far memory, taken
only where the DOS is G4DOS.  Bank $00 gives four bytes, the pointer to
it all, in the window (`src/sys/zwin.h`), because LoRAM is at its floor.
G4DOS gave nine bytes of header and its sector entry.

And stack: a GEMDOS call through the engine goes 613 bytes deep where the
same call on SpartaDOS 3.2 goes 412 (`test-m15g`, `test-m15`) -- about ten
levels of C under CIO's, each with its return address and saved
registers.  Every buffer a call needs -- paths, a directory entry, the
lookups -- is in the far blocks rather than on the stack, which is what
took it down from 789; through `test-fdos`'s whole tour GEM.COM's engine
stack still has 522 bytes spare.
