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

## What gem4xe takes from a DOS today

Everything that branches on the DOS (`src/sys/dos.c`, `gemdos.c`,
`clock.c`, `sdcio.c`):

| what | SpartaDOS X gives it by | on G4DOS today | the plan |
|---|---|---|---|
| files and folders: paths, listings with stamps, rename, lock, make and remove folders, free space | CIO, its own SDFS | **done**: gem4xe's engine behind CIO's `D:` | -- |
| loading GEM.COM | `X.COM` / the command line | G4DOS's loader, `D1:GEM.COM` | -- |
| loading programs, resources, fonts | CIO | the engine | -- |
| a command line: GEMDOS `Psystem`, the desktop's *File -> DOS command* | XCOMLI, its command processor (`dos_command`) | **nothing** | built-in commands in gem4xe, over GEMDOS (step 4) |
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
2. **Every drive.**  G4DOS's DRVBYT says all eight; gem4xe probes them
   (`gd_dprobe` already does, through the OS's status command) and shows
   the ones that answer.  *Gate*: `test-m15g` with a disk in D3:.
3. **512-byte sectors**, which an APT partition has.  The engine first
   (`SD_SECMAX`, `test-sdfs` on a 512-byte image), then G4DOS -- whose
   five buffers are 256 bytes each and have no room to double.  The
   answer is probably that G4DOS reads 512-byte sectors only into a
   buffer gem4xe lends it once gem4xe is up, and before that only what
   booting needs.  *Gate*: the card image's partition read by the engine.
4. **A command line** on G4DOS: `Psystem` and *File -> DOS command*
   served by built-in commands written in gem4xe over GEMDOS -- `DIR`,
   `COPY`, `DEL`, `REN`, `MD`, `RD`, `TYPE`, `CD` -- printing into the
   same far buffer XCOMLI's output goes to.  *Gate*: the desktop's
   command window on a G4DOS disk.
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
