# G4DOS as gem4xe's own DOS: one system, two shapes

A plan, started 2026-11-02.  G4DOS (`src/fdos.s`, [fdos.md](fdos.md))
boots the system floppy, loads GEM and writes; since the same day its
disks have folders under GEM, served by gem4xe's own SDFS engine
([sdfs-plan.md](sdfs-plan.md)).  This page is what is left for G4DOS to
be the DOS gem4xe is *made for* -- everywhere SpartaDOS X is today, and
faster -- and the two shapes of system that makes possible.

## Two shapes, one system

**The installed system.**  A fully upgraded Atari with a hard disk
behind an APT interface (Ultimate 1MB, Incognito, a SIDE) or a large
image: it boots to a desktop somebody has set up -- accessories, control
panel modules, applications in their folders -- a small office computer.
Today that is SpartaDOS X on the card image ([media.md](media.md)), and
it stays a way to run gem4xe; the multitasking AES, when it comes
([multitasking.md](multitasking.md)), comes here.

**The appliance.**  One disk -- a floppy, an image, a cartridge -- that
boots straight into one program with the graphical interface: RetroWP,
or GACS ([gacs.md](gacs.md)).  Nothing to install and nothing to
configure.  **This already exists as a convention**: the program is the
disk's `DESKTOP.PRG`, so the shell runs it where it would run the
desktop.  `GACS.ATR` and `RETROWP.ATR` are built exactly that way --

    X32G.DOS  STARTUP.BAT  AUTOEXEC.BAT     SpartaDOS 3.2g, CD >GEM, GEM
    GEM>GEM.COM  LANG.RSC  GEM4XE.CFG  816.COM
        DESKTOP.PRG                         the application itself
    GACS.RSC  CHASSIS.DAT ...               its own files, in the root

-- but on SpartaDOS 3.2g, which nobody runs any more.  On G4DOS the same
disk needs no batch file and no third-party DOS: the boot sectors load
G4DOS, G4DOS finds `GEM.COM` one folder down, gem4xe finds the program
and its files by bare name (root first, then one level down).

Both shapes are the same gem4xe on the same G4DOS; what differs is what
is on the disk.  So the work is G4DOS being a first-class host on every
medium, and the tools that make each shape's disk.

## G4DOS, a DOS of its own

G4DOS is also meant to be a DOS somebody uses without GEM: a kernel that
bootstraps GEM, and the same kernel with a shell beside it.  Atari's DOS
2 had this shape -- DOS.SYS resident, DUP.SYS loaded only when you asked
for DOS -- and a disk with DOS.SYS and one program on it booted into that
program.  G4DOS in three parts:

| part | what it is | when it is in memory |
|---|---|---|
| `G4DOS.SYS`, the kernel | the boot, the `D:` handler, the sector entry gem4xe uses, and the loader, which runs the disk's boot file: `GEM.COM` if there is one, else `AUTORUN.SYS`, else the shell | always (and less of it under GEM: *Room*, below) |
| the shell | a program on the disk, never resident: loaded when a program leaves to DOS, or when there is nothing else to boot | between programs |
| gem4xe | GEM, on top, when the disk boots it | while it runs |

So a disk with `G4DOS.SYS` and one program boots into that program; one
with the shell as well is a DOS to work in; one with `\GEM\` is the
desktop or an appliance.

**The shell** has two faces over one set of operations: a menu in the
manner of DOS 2.5's and SmartDOS's -- a letter an action, for somebody
who wants to be led -- and a command line in SpartaDOS X's place, with
**commands a Linux user already knows**:

    ls [-l]   cd   pwd   cp   mv   rm   mkdir   rmdir   cat   more   df

a program run by typing its name, `/` taken between folders as well as
SpartaDOS's `>` and GEM's `\`, and the old names (`DIR`, `COPY`, `DEL`)
as aliases for anybody's fingers that remember them.  The same command
set serves gem4xe's *File -> DOS command* window and GEMDOS `Psystem`:
one implementation, two hosts.

The shell needs folders, so it uses the same SDFS engine gem4xe does
(`src/sys/sdfs.c`, in C) -- which makes it a 65C816 program to begin
with: every machine gem4xe runs on has one.  **6502 machines are a
target too, later**: the feature set goes in first, on the upgraded
machine, and is squeezed down after.  So what is portable stays plain C
a 6502 build can take -- the engine already builds for the host with
gcc as well as for the 65C816 -- and nothing here is 65C816-only that
does not have to be.

## Room: the ceiling at `$2000`

G4DOS must end below `$2000` because that is where gem4xe's bank `$00`
begins -- its direct page, then its stack and data, its code, the window
and the application pool -- and gem4xe begins there so that one GEM.COM
sits above every DOS it runs on (SpartaDOS X leaves MEMLO at `$1C1D`,
DOS 2.5 at `$1CFC`).  Moving it up would cost every DOS's application
pool, and bank `$00` is gem4xe's scarcest memory.  (exec816 went the
other way: it is an operating system of its own, keeps its kernel and
its file services in far banks, and refuses a resident DOS -- MEMLO must
be at most `$0A00`.)

So G4DOS gets room without moving the line:

- **on the cartridge**, its code runs from the ROM, as the cartridge's
  `D1:` handler already does, and only its buffers want RAM;
- **on a floppy**, it is large while it boots and small under GEM: once
  gem4xe is up the engine does the files, and what has to stay resident
  is the sector entry, a buffer, and what RESET needs.  The rest of
  `$0700`-`$1FFF`, about five kilobytes, becomes bank-`$00` memory for
  gem4xe where the DOS is G4DOS -- room no other DOS can give it.  The
  cost: gem4xe's bank-`$00` allocator takes a second region, and a
  program run outside GEM finds G4DOS's handler gone until the kernel
  is loaded again (which the shell, being on the disk, can do).

## What gem4xe takes from a DOS today

Everything that branches on the DOS (`src/sys/dos.c`, `gemdos.c`,
`clock.c`, `sdcio.c`):

| what | SpartaDOS X gives it by | on G4DOS today | the plan |
|---|---|---|---|
| files and folders: paths, listings with stamps, rename, lock, make and remove folders, free space | CIO, its own SDFS | **done**: gem4xe's engine behind CIO's `D:` | -- |
| loading GEM.COM | `X.COM` / the command line | G4DOS's loader, `D1:GEM.COM` | -- |
| loading programs, resources, fonts | CIO | the engine | -- |
| a command line: GEMDOS `Psystem`, the desktop's *File -> DOS command* | XCOMLI, its command processor (`dos_command`) | **nothing** | the shell's command set, built into gem4xe as well (step 4) |
| the clock | `kd_gettd` / `kd_settd`, through whichever driver is loaded | gem4xe reads the U1MB's and the SIDE's itself | the other clocks read by gem4xe too (step 6) |
| which drives there are | probed by listing each | DRVBYT says D1: and D2: | probe D1:-D8: (step 2) |
| sector sizes | 128, 256, 512 | 128 and 256 | 512, which APT partitions use (step 3) |
| leaving GEM | its prompt | a cold start: the disk boots again | -- (an appliance wants exactly that) |
| memory | MEMLO `$1C1D`, and banks of its own | MEMLO `$2000`, every extended bank gem4xe's | -- (already better) |

The pattern is the folders' one ([sdfs-plan.md](sdfs-plan.md)):
**G4DOS keeps only what must exist before gem4xe or without it** -- the
boot, the loader, sector I/O -- because it is full: 4,769 bytes of code
with 4 to spare, and `$2000` is gem4xe's direct page.  Everything else
is gem4xe's, in far memory, written in C until measuring says otherwise.

## Speed

Measured on the MiSTer core, 2026-11-02, the system floppy from power to
gem4xe's boot screen:

    XL OS (Hias's high-speed SIO), drive at Fast-0     29 s
    Rapidus OS, the same drive setting                 93 s

G4DOS reads through the OS's SIO routine, so it is exactly as fast as the
OS is: the Rapidus OS evidently transfers at standard speed, and so does
a stock OS.  The CPU is not what limits a load -- under the Rapidus OS
the core's 1x hold during disk I/O made no difference to it.

So the first speed step is **G4DOS's own high-speed SIO**: the drive
asked for its speed (the `?` command, as SpartaDOS X and Hias's code do)
and read at it, for drives on the serial bus.  For anything else -- a
drive an Ultimate 1MB or a SIDE serves from its own firmware, hooking
the OS's routine -- G4DOS goes on calling the OS: exec816, another
65C816 loader, brought a serial driver of its own and could not read
those drives at all.  Room for it comes out of bank `$00` that does
not exist, so it is also the step that decides what moves out of G4DOS:
the flat view's search, say, which nothing needs once gem4xe is up.

After that, gem4xe's own time: the engine's hot paths, and anything
`make g4bench` and `make bench-boot` point at, in assembly where the
measurements say so ([perf notes](phase52.md) has how to measure).

## The gates

Gates move off SpartaDOS 3.2g to G4DOS as they are next touched, not all
at once.  `test-m15g` is the template: the conformance runner named
`GEM.COM` on a G4DOS disk (`tools/mkspdisk.py --g4dos`), every answer
held to the disk image, and the emulator's working copy checked with
`atr.Sdfs.check()` afterwards.

## The steps

Each says how it is tested.

1. **The appliance disk.**  **Built 2026-11-02.**
   `tools/mkfloppy.py OUT --app PROGRAM --add FILE 'GEM>NAME'...`: a G4DOS
   disk with the system in `\GEM\` less the desktop's own files, the
   program as `GEM>DESKTOP.PRG`, and its files beside it -- where a bare
   name finds them under G4DOS and under SpartaDOS X alike, the disk's
   `AUTOEXEC.BAT` putting SpartaDOS X in `\GEM\`.  *Gate*: `test-fdosapp`
   boots `build/gem-appliance.atr`, EDIT's, with no SpartaDOS X: EDIT asks
   for a file and no desktop icon is drawn (a check shown to find one on
   the desktop's screen).  Next: GACS's and RetroWP's builds make their
   disks this way, in their own repositories.
2. **Every drive.**  **Built 2026-11-02.**  Nothing probes at start-up:
   `Dsetdrv` answers D1: and D2:, and the desktop's *Options -> Install
   devices* asks every drive with GEMDOS's `Dprobe` -- about a second for
   each one that is not there (336 frames for six, measured), the pointer
   busy meanwhile -- and *Save desktop* keeps the set.  `Dprobe` skipped
   any drive G4DOS's DRVBYT did not name, which is DOS 2's rule; under
   GEM the engine reaches any unit, so `sdc_init` drops the drive map.
   *Gate*: `test-m15g` mounts a disk in D3: with D2: empty, `Dprobe`
   answers D1: and D3: alone, and D3:'s folders list as its image has
   them -- a 256-byte-sector unit beside D1:'s 128 (the check fails, as
   `0x0001`, with the drive map left in).
3. **512-byte sectors**, which an APT partition has.  **Built
   2026-11-02 under GEM.**  The engine takes them (`SD_SECMAX` 512; a
   512-byte volume has one boot sector and its size byte is 1), told the
   drive's sector size before it reads sector 1 -- which is 512 bytes
   there and 128 everywhere else -- by `sd_devsec`: on the Atari the
   drive's PERCOM block, asked once a unit.  G4DOS's 256-byte buffers
   cannot hold one, so gem4xe moves a 512-byte sector itself, through a
   slice of the pool and the OS's SIO (`dsk_read`, `dsk_write`).
   *Gates*: `test-sdfs` reads the card image's two partitions and runs
   the by-hand and random rounds at 512; `test-m15g` mounts a 512-byte
   disk in D4: -- found, listed, read, a file written over six sectors
   into a folder and read back and deleted, `Dfree` agreeing with the
   image (every check fails with the drive's answer ignored).  **Left**:
   G4DOS itself on a 512-byte disk, before GEM is up -- what booting from
   a partition needs (step 8).
4. **The shell**, its command line first: the commands above over the
   engine, printing to the screen when it runs alone and into the far
   buffer XCOMLI's output goes to when gem4xe's *File -> DOS command*
   runs them.  G4DOS's loader runs the boot file (`GEM.COM`, else
   `AUTORUN.SYS`, else the shell) and DOSVEC loads the shell.  *Gates*:
   a G4DOS disk with the shell boots to its prompt and a scripted session
   is checked against the disk afterwards; the desktop's command window
   runs the same commands.  The menu face comes after the command line.
5. **High-speed SIO in G4DOS**, as above.  *Gate*: `make bench-boot`,
   and the floppy on the MiSTer core under both OSes.
6. **More clocks**: FujiNet's `APETIME` and an R-Time 8, read by
   `src/sys/clock.c` the way it reads the U1MB's.  *Gate*: as
   `test-m15u` checks the U1MB's, where an emulator has one.
7. **G4DOS on the cartridge** ([sdfs-plan.md](sdfs-plan.md), step 4):
   the ROM a drive of its own, the floppies served without a DOS booted
   first.
8. **The installed system on G4DOS**: the card image's partition booting
   G4DOS into the desktop, as it boots SpartaDOS X today (needs 3).
   *Gate*: `test-cf` on G4DOS.
9. **Folders in G4DOS's handler**, for programs run outside GEM: a path
   through any depth of folders (`D1:>A>B>NAME`, and `/`) where today it
   finds a name in the root or one folder down.  Making folders stays the
   shell's.  *Gate*: `fdwtest.s` reading and writing two folders down.
10. **G4DOS small under GEM**: what stays resident sized exactly, and the
    rest of `$0700`-`$1FFF` given to gem4xe's bank-`$00` allocator as a
    second region when the DOS is G4DOS.  *Gates*: `make memcheck`
    models it; `test-fdos` and the stack check run on it.
