# Shipping gem4xe: how it boots, what it lives on, what language it speaks

Everything before this document is about making GEM *work*.  This one is
about making it something a person installs and uses: a disk that comes
up in the desktop, a volume big enough to hold more than the system
itself, and a text file a translator can replace.  None of it is built
yet; it is written down now because the decisions shape what the next
milestones do -- particularly localization, which is cheap to design for
and expensive to retrofit.

## 1. The system fills a floppy, and that is the point

Measured, today:

    GEM.COM        92,230 bytes   the VDI, the AES, GEMDOS and the shell
    DESKTOP.G4A    23,737         the desktop
    DESKTOP.RSC     5,082         its resource
                  --------
                  121,049

against what the formats hold, in bytes a file system can actually use:

    single density    707 x 125 =  88,375   less than GEM.COM alone
    enhanced          1009 x 125 = 126,125  the system, and 5 KB over
    double density     707 x 253 = 178,871  the system, and 15 KB over
    SDFS, our gates   2048 x 128 = 262,144  the system, and 96 KB over

(The system is **168 KB** now, not 121 -- 681 sectors of 253 on the disk,
which is the figure the arithmetic below uses.  GEM.COM carries BOTH
display drivers since `phase34.md`, which cost it 10 KB, and the printer
device and its emitters since `phase37.md`; the desktop has grown
besides.  The DOS takes 3.5 KB of the 15 the double-density disk has left
-- and its `DUP.SYS` would have taken 5 KB more than there are, which is
why that disk no longer carries one.  See below.)

Enhanced density is where the DOS 2 product disk used to live, and it
was too tight to be a product: the system left **three sectors free**,
which is no room for the applications a desktop exists to launch -- and
none for the DOS's own shell either, which is worse (section 2).
**Double density is where it lives now**: the system and the DOS, with
**12 sectors -- 3,036 bytes -- still free**, and no `DUP.SYS`.  The
shell went because the system wanted seven sectors more than the disk had
left beside it, and because a floppy is a test vehicle now rather than how
anybody runs this: a real machine runs gem4xe off the APT/CF card, which
has 96 KB spare.  `tests/emu/product_boot.py` asserted its absence, so
that putting it back would be a deliberate act and not an accident -- and
it was one, a phase later; see below.

That was 42 KB when this section was written, and it is 6 now.  One
binary that carries both display drivers took 10 KB of it and the
desktop took the rest, and the conclusion the paragraph was already
drawing has simply arrived: **the DOS 2 floppy is the system and
nothing else.**  What 6 KB is still enough for is the thing a user
writes on the first day -- `DESKTOP.INF`, from Options -> Save desktop
-- and that is what `tests/emu/product_boot.py` now checks for instead
of room for a program.

**Since phase 38 the far image travels packed** (`phase38.md`), and
the arithmetic above is a record rather than the state of the disk:
`GEM.COM` is 90,468 bytes and 358 double-density sectors, not 122 KB
and 486, so the DOS 2 floppy has **`DUP.SYS` back, the full
`GEM4XE.CFG`, `CLOCK.ACC` and its resource, and 122 sectors (30 KB)
free** with all of it aboard.  `tests/emu/product_boot.py` now requires
the shell -- it is what GEM returns to -- and a floor of 80 free
sectors, and prints the figure so the next phase that eats into it sees
it go.  The paragraphs that follow were true when written and are what
the packing was measured against.

**Phase 42 was that phase.**  The rest of GEMDOS -- the console, the
standard handles, Pexec -- is 10 KB of code and 7.6 KB more `GEM.COM` on
the disk, and the DOS 2 floppy went to 65 sectors free, under the floor.
The floor stayed and the desk accessory went: from that floppy and from
every other, which are the system and nothing else now.  The applications
and the accessory are on a floppy of their own, `gem-apps.atr`, and each
SpartaDOS floppy carries an `INSTALL.BAT` that puts what it holds on a
drive (`docs/media.md`).  The DOS 2 floppy has `DUP.SYS`, the full
`GEM4XE.CFG` and 87 sectors free.

**Phase 43 was the next.**  File -> DOS command is 3.4 KB more
`DESKTOP.G4A` and 0.7 KB more `GEM.COM`, and the DOS 2 floppy went to 65
sectors free again.  This time the file went and the floor moved:
`GEM4XE.CFG` is off the DOS 2 floppy -- every value in it is the
default, so a machine without the file runs exactly as the file says,
and the boot screen says *defaults* where it said the file's name -- and
the floor is 72 sectors, 18 KB, still two programs of `HELLO.G4A`'s
size.  The SpartaDOS X floppy and the card carry the file as before.
Behind the decision is a plainer one: nobody runs DOS 2 now -- people
run MyDOS or SpartaDOS X -- so the DOS 2 floppy is the third-party-DOS
tester it was built as, and its sectors are not worth a feature.  A
MyDOS tester disk could be double-sided and the question would not
arise, but MyDOS is the DOS section 2 caught mangling the staged image,
so that swap is work of its own.

**Phase 45 was the third, and the argument was already made.**
`wind_get(WF_OWNER)` was handing back the top and bottom of the window
list where the Compendium asks for the window directly above and the one
directly below, and `WF_BOTTOM` was a name `gem.h` promised that the AES
did not keep.  Putting both right is 186 bytes of `GEM.COM` and two of
the DOS 2 floppy's sectors, which took it to 70 against a floor of 72.
Nothing went off the disk this time: **the floor moved to 64**, because
the paragraph above had already settled what this disk is.  A DOS 2
cannot read `gem-apps.atr`, so it is not where anybody puts a program of
their own -- the SpartaDOS X floppy and the card are, and both have room
to spare.  Eight sectors of margin rather than two, so that the next two
hundred bytes are not another conversation.

**Phase 46 was the fourth, and it changed the QUESTION rather than the
number.**  The last ten AES opcodes -- `scrp_clear`, `appl_read`, the
four menu calls, the two shell calls and the two tape calls, which took
the AES to all 79 -- put the floppy at 52 against a floor of 64.  Three
paragraphs above argue that nobody puts a program on this disk, the
Makefile calls it "a gate's more than anybody's way in", and the way in
is the INSTALLER: both floppies carry `INSTALL.BAT`, SpartaDOS X copies
them onto a drive and the machine boots from that (`test-install`,
`docs/media.md`).  So the floor was guarding a use this file had already
written off, which is why it produced a conversation every two hundred
bytes.

It guards one real thing now: `DESKTOP.INF`, which is what a person can
write to this disk, when they arrange the desktop and choose Options ->
Save desktop.  Its size is BOUNDED rather than guessed -- `inf_write`
builds the text in the shell buffer (`src/desk/deskwin.c`) and
`SIZE_SHELBUF` is 4,192 bytes, 17 double-density sectors of 253, plus
one for the directory entry.  **The floor is 20**, and the rest of the
margin is given back.  Splitting the system across two floppies was the
other option on the table and is not needed here: the *product* already
is split that way, and the desktop draws one icon per drive in GEMDOS's
map, D1: to D8: (`src/desk/desktop.c`, `MAX_DRIVES` 8), so a machine
with four drives already shows four.

That is the honest shape of the thing rather than a regression to be
fixed: a 640x240 GUI with a resident AES belongs on a volume measured in
megabytes, and the machine this project targets (Rapidus, VBXE, U1MB) is
a machine that has one.  The floppy is a *bootstrap* -- enough to start
the system, and to carry it to the real volume.  **An application goes
on the applications floppy, `gem-apps.atr`, or on the card**, and each
floppy's `INSTALL.BAT` carries what it holds to the real volume, laid out
as the card is (section 4, and `docs/media.md`).

## 2. Booting straight into the desktop

**Since phase 23 the machine also switches its own CPU** (`phase23.md`):
a Rapidus cold-boots as a 6502, and rather than refuse a machine that
could run it, the loader probes the PBI slots for the card, sets
`COLDST` and switches. What follows is about the other half -- which
file each DOS runs at boot -- and is unchanged by that.

Every DOS on this platform runs something at boot, and no two of them
agree on its name.  What follows was read out of the DOSes themselves
and then booted, because the received wisdom was wrong twice.

**SpartaDOS 3.2g** -- the fixture, and what the product disk boots --
looks for `D1:AUTORUN.SYS` and for `STARTUP.BAT`: both names are in
`X32G.DOS`, and `CHANGES.32G` on the same disk documents the batch file.
It does *not* look for `AUTOEXEC.BAT`.  **SpartaDOS X** boots from the
cartridge or from U1MB flash and reads `CONFIG.SYS` then `AUTOEXEC.BAT`
off `D1:`.  A product disk cannot know which one booted it, so the
SpartaDOS 3.2 product disk carried **both batch files**, four bytes each
(`GEM` and an EOL), and the program kept the name a person would type
(`tools/mkspdisk.py --boot GEM`); `test-boot` booted it with nothing typed
and compared the desk against the model.  That disk was retired after
phase 42 -- the installer is SpartaDOS X's (`docs/media.md`) -- and the
screenshot disk is what still carries the pair.

**DOS II+/D 6.4** -- the DOS 2 fixture -- **has no `AUTORUN.SYS` at
all**: the string is nowhere in its `DOS.SYS`, and a disk built with the
program under that name boots to its `D1:` prompt and waits (measured).
Its command processor is *inside* `DOS.SYS`, which is the only reason it
fits on a disk beside GEM.

**DOS 2.5 does run `AUTORUN.SYS`**, and its `DOS.SYS` is 37 sectors --
one *less* than DOS II+/D's.  But its command processor is a separate
`DUP.SYS` of 42 more, and an enhanced-density disk holds 1,009:
`GEM.COM` (738), `DESKTOP.G4A` (190), `DESKTOP.RSC` (41) and `DOS.SYS`
(37) leave three, so `DUP.SYS` is 39 sectors short of fitting.  Built
without `DUP.SYS` the disk does boot GEM -- and then dies the moment GEM
hands the machine back, because DOS 2.5 goes looking for `DUP.SYS` and
it is not there (an illegal instruction inside DOS at `$144C`, measured;
with `DUP.SYS` present the same disk returns to its menu).  **So on an
enhanced-density floppy you can have a DOS shell or an auto-start, and
not both** -- which is the argument for the density above it.

**That argument has since come due on the double-density disk as well.**
The system is 681 sectors and the disk has 674 free beside `DOS.SYS` and
`DUP.SYS`, so as of `phase37.md` the shell had to go there too -- the
same trade one density up, seven sectors instead of thirty-nine.

What it costs, stated exactly, because the enhanced-density measurement
above must not be read as covering this: **what this DOS does when GEM
quits is not measured.**  The `$144C` illegal instruction above is DOS
2.5's, and this disk carries the German "DISK OPERATING SYSTEM II" of
1990 instead.  What IS measured is that the disk boots into the desktop
with nothing typed (`test-boot`), which is what the floppy is for.
Quitting is not: the SpartaDOS install disk and the card both keep their
DOS and both return to it, and that is where a machine anybody uses for
anything runs from.  Driving File -> Quit on the PRODUCT is harder than
it looks and is why the figure is absent rather than wrong -- the
product's pointer comes from the emulated mouse and not from the
host-driven `ptr_state` the accessory and desktop gates poke, so the
click the gates use does not reach it.

### Double density, which is where the DOS 2 disk belongs

A double-density disk is the same DOS 2 file system with 253 data bytes
to a sector instead of 125: 707 sectors, 174 KB, room for the system and
the DOS and a few kilobytes besides.  `tools/atr.py` writes it now.  The format is
Altirra's `ATDiskFSDOS2` (`diskfsdos2.cpp`), read rather than
remembered, and the one thing that is genuinely different is the byte
count in the sector link: **a whole byte in double density**, because
253 does not fit in the seven bits a single-density disk leaves it.  The
directory stays eight entries to a sector and uses half of one.
`tests/host/test_atr.py` checks both densities against those rules, and
`test-boot` boots the result.

The disk is built by sweeping a fixture down to its DOS (`mkdisk.py
--sweep`) and writing GEM onto it as `AUTORUN.SYS`, so what ships is
the DOS's boot sectors, `DOS.SYS`, `DUP.SYS` (removed in phase 37 for
want of seven sectors, back since the image is packed) and ours.  The DOS is the
German Atari **"DISK OPERATING SYSTEM II"** of 1990 (H. Barth and
F. Bruchhäuser), which does double density and does run `AUTORUN.SYS`.

**MyDOS does not work, and the reason is not known.**  It is the obvious
choice -- double density, hard disks, subdirectories, `AUTORUN.SYS` --
and GEM crashes under it every time, at the same place: twelve bytes of
the far image are missing at bank `$01` offset `$20`, the first
`gemdos_call` runs into the zeros and takes a BRK.  What is established:
the file on the disk is byte-for-byte `build/gem.xex`; the near part of
the program loads correctly; the staging buffer holds the right bytes
when the load is over, so they *were* read; and it happens under MyDOS
4.50T and 4.53/4 alike, from `AUTORUN.SYS` and from the DUP menu, while
the same file under this DOS and under SpartaDOS arrives perfect.  So it
is something about MyDOS's binary loader and our chunk staging
(`tools/mkxex.py`, `src/farload.s`), and it wants an hour with a
watchpoint that the bridge does not have yet.  It matters for the hard
media of section 3 only if the hard-disk DOS is MyDOS; SpartaDOS X, which
is what APT wants, is unaffected.

**Ultimate 1MB flash / a cartridge**: the deployment story
flashjazzcat's GUI uses, and the one that makes gem4xe feel like part
of the machine rather than a program.  It is a later phase: the system
would live in flash and the disk would hold only documents.

What makes all of this worth writing down is the ordering rule the
Rapidus imposes and that every gate here obeys -- **the program must
arrive after the CPU switch, through the boot path** (`docs/phase0.md`).
A start-up file satisfies it only if the machine is *already* the 65C816
when the DOS boots, and that is not free: the switch resets the CPU, the
OS treats that reset as a **warm** start, and a warm start is exactly
when a DOS does not run its start-up file.  On a real machine that is
what U1MB's Rapidus plugin is for -- it sets the CPU over the M1 signal
before the OS runs.  The gate arranges the same thing by hand: it lets
the 6502 pass finish (the batch runs GEM, GEM refuses through CIO, the
prompt comes back), sets `COLDST` (`$0244`) so the OS comes up cold, and
only then switches -- with the machine idle, because a write made while
the DOS is mid-SIO is lost and the DOS hangs.  Two boots of a 92 KB
program is also why that gate takes a few minutes.

## 3. Bigger volumes: partitions, APT, and hard media

**The card is built.**  `make` writes `build/gem-cf.img`: a 16 MB image
of 512-byte blocks, an **APT** table (Konrad Kokoszkiewicz's Advanced
Partition Table, which is what SpartaDOS X mounts), and two 8 MB SDFS
partitions -- the system in `\GEM\`, a demonstration application in
`\APPS\`, an `AUTOEXEC.BAT` that changes into `\GEM` and runs `GEM`,
and 7 MB free.  `tools/apt.py` lays out the table and
`tools/mkcf.py` fills it, the way `mkspdisk.py` fills a floppy, and it
needs no fixture: a card carries no DOS of its own, because SDX boots
from a cartridge or from U1MB flash.

The layout was read rather than remembered, out of Altirra's own
`ATDecodePartitionTable` (`src/ATIO/source/partitiontable.cpp`), which
reads real APT disks, and its APT writer in `blockdevdiskadapter.cpp`:

    LBA 0    a protective MBR -- one entry, type $7F, pointing at the
             table, so a PC does not offer to format the card
    LBA 1    the table: sixteen-byte entries, the first the header
             ('APT' in bytes 1-3), the rest partitions.  Entries 1-15
             are the mapping slots, and a DOS mounts them as D1:..D15:
    LBA 8+   the partitions

A partition entry says where it starts and how long it is in blocks,
and how the DOS's sectors sit inside those blocks.  These are **512-byte
sectors, one to a block**, which is also what SDFS wants on anything
bigger than a floppy: `Sdfs.format` grew that case (one boot sector
instead of three, a size byte of 1, a boot header that loads at $0440 --
`ATDiskFSSDX2::InitNew`, and CLX 1.9 checks it).
`tests/host/test_apt.py` holds it to those rules, field by field.

**The SD-card shape, for a SubCart or an AVGCART.**  Those carts hand
the whole card to the U1MB PBI BIOS through their SIDE 2 / IDE
emulation, but their own browser wants a FAT32 partition first and only
ever sees that one.  `make sd` writes `build/gem-sd.img`: a 64 MB FAT32
partition from LBA 2048 (a `README.TXT` on it says what the rest is),
the MBR's first entry type `$0C` pointing at it and the `$7F` entry
second, the APT table right after the FAT, and the same two SDFS
partitions after that.  `tools/apt.py`'s `write_table(fat=...)` and
`read_fat` know the shape; `make test-sd` boots it the way `test-cf`
does.  Needs `mkfs.fat` and `mcopy`, so it is not in `make`.

**A card that stops at the prompt** is what a diagnosis wants:
`tools/mkcf.py out.img --boot "CD >GEM" --add build/gemdiag.com
"GEM>GEMDIAG.COM"` gives one where `GEM` and `GEMDIAG` are typed
(`docs/phase39.md`, "What to do on the hardware").

**`make test-cf` boots it, and nothing on the card is a driver.**  The
machine this project is for has an Ultimate 1MB, and the U1MB's flash
carries three things that matter here: SpartaDOS X, the **PBI BIOS**,
and the SIDE Loader.  The PBI BIOS is the disk driver.  It reads the APT
table itself, mounts the mapping-slot partitions as `D1:`, `D2:`, ...
before any DOS runs, and SDX then finds `AUTOEXEC.BAT` on `D1:` exactly
as it would on a floppy.  So the card needs no `SIDE.SYS`, no
`CONFIG.SYS` line and no driver file of its own -- which is just as
well, because neither SDX we have carries an IDE driver at all.  Listing
the ROM file systems by hand: the 4.49b in the U1MB flash holds ARCLOCK,
ATARIDOS, COMEXE, CON64, CONFIG, DOSKEY, ENV, INDUS, JIFFY, QUICKED,
RAMDISK, RTIME8, RUNEXT, SIO, SPARTA, ULTIME and XEP80, and the 4.50
cartridge the same less ARCLOCK, CON64 and ULTIME.  The driver was never
going to come from the DOS.

Three facts about that machine had to be measured, and each is a step of
`tests/emu/cf_boot.py`:

- **The BIOS setup has to be walked, and the gate walks it.**  A fresh
  U1MB profile boots into *Ultimate Setup*, and what the card needs is
  off by default: page 3, *PBI BIOS: Enabled* and *Hard disk: Enabled*.
  The pages step along the icon row with LEFT and RIGHT, the field
  cursor moves with UP and DOWN, RETURN changes the field under it, and
  page 8 offers *Save changes and boot* (`B`) and *SIDE Loader* (`L`).
  On a machine already configured, HELP with RESET reopens it.  The gate
  drives all of that through `KEYRAW`, from a config directory of its
  own (`build/altirra-cf`), so every run starts from the same fresh
  NVRAM and the user's emulator profile is left alone.  It reads the
  screen after every key rather than counting keys, because the setup
  changes between firmware releases.  2.0 added a *PBI logo* row
  between the device ID and *Hard disk*, 4.0 made the device ID a
  field you open with RETURN and renamed the save item *Save changes
  and cold boot*, and 1.25-3.10 store their menu as ASCII codes while
  4.x use the OS's internal codes.  The menu is character rows the
  display list points at, so the gate finds each field by name and
  watches its value; `--flash ROM` runs it against any U1MB image.
- **The PBI device ID must not be 0.**  Setting 0 is PBI bit 0, the
  Rapidus's (docs/phase14.md).
- **The SIDE must let go of the cartridge window.**  The PBI BIOS's
  first act is a wait, at `$D803` in its ROM:

        LDA #$80 / STA $D5E4 / BIT $D384 / BVS $D803

  `$D384` bit 6 is the U1MB's *external cart active* sense, and the SIDE
  asserts it while its own SDX module is mapped -- the state of a SIDE 2
  whose SDX switch is on.  A machine that runs SpartaDOS X from the U1MB
  has that switch off.  AltirraSDL has the switch as a device button
  with no command-line or bridge verb, so the gate unmaps the SDX bank
  the way the switch does, by writing `$80` to the SIDE's bank register
  at `$D5E1`; a reset puts the bank back, so it writes it again through
  the run.  Left alone, the machine sits in that loop forever after
  printing `Ultimate PBI v.1.85` -- which is what "the card does not
  work" looked like before it was read out of the ROM.

With those three, the boot is the floppy's boot: the card starts GEM on
the 6502, the loader refuses the machine, COLDST goes in and the CPU is
switched, and the desktop comes up on the restart with `DISK A` and
`DISK B` on it -- the card's two partitions -- pixel for pixel against
`tools/deskref.py`.

**And on the real machine, two settings in the Rapidus's own menu**
(HELP at power-on with the card's BIOS installed; docs/phase40.md):

- ***Preference* must be *Rapidus*.**  It is the first option and it
  is a preset for the rest of the menu -- *Classic*, *Sweet16*, *Warp
  XE*, *Warp II*, *Rapidus*, *Custom*.  On *Sweet16* the first real
  board froze before the boot screen: attract-mode colours, then
  nothing.  On *Rapidus* it booted.
- ***SDRAM 4k cache: Off*** on a 6S9054E core, per the card's own
  known-issues list.

The board's `Vectors` line then reads `OS copied ($74/$81/W)`: the
card takes the native vectors the way its own firmware writes them,
write-through on, not the way the emulator does.

The table itself was never the problem, and there is direct evidence:
the firmware's own parser state, read out of the machine while its list
was on screen, showed the signature accepted, three entries counted and
both partitions intact.  The SIDE Loader's `APT` page saying *No
Entries* is correct as well -- that list is of partitions **beyond** the
fifteen mapping slots, and ours are in slots 1 and 2, which is what
makes them `D1:` and `D2:`.

Two findings from the same afternoon, so nobody repeats them:

- **SIDE 2 and a cartridge cannot both be in the machine.**  SDX 4.50
  from a MaxFlash `.car` plus `--adddevice side2` boots to a black
  screen: they are both cartridges.  The pairing that works is SDX in
  U1MB flash with SIDE 2 in the slot -- the machine this project targets
  -- or SDX in a cartridge with a PBI interface beside it.
- **A FAT16 card works too, and is the quickest way to prove the
  plumbing.**  The SIDE Loader browses FAT volumes off the same card and
  will mount an `.ATR` from one as `D1:`; a card with `GEM.XEX` in a
  FAT16 partition shows up in its file list.  That was the control that
  said the emulated SIDE 2 and its IDE bus were fine long before the
  APT path ran.

~~One thing on the target has to move with it: `Dfree` cannot answer
more than 999.~~ **Fixed** (`docs/phase16.md`): `Dfree` reads the file
system's own count now -- the VTOC on a DOS 2 disk, the superblock on a
SpartaDOS one, one sector through the OS's SIO, which is the path a PBI
hard disk answers on as well as a floppy -- instead of the three
characters CIO's directory trailer gives it.  `make test-m15` reports
1489 free against an image's 1489, where the old ceiling would have said
999, and the card's 16116 is no longer a problem waiting to be found.
The listing is still the fallback for a drive that will not answer SIO.

## 4. An install layout

With a volume that has room, the system stops being one lump:

    \GEM\GEM.COM         the system: VDI, AES, GEMDOS, the shell
    \GEM\GEM4XE.CFG      the screen and the mouse -- see section 4a
    \GEM\DESKTOP.G4A     the desktop
    \GEM\DESKTOP.RSC     its resource (its own strings, its own layout)
    \GEM\LANG.RSC        the system's strings -- see below
    \GEM\*.ACC           desk accessories, with their resources
    \GEM\*.FNT           fonts, when they are loadable
    \APPS\...            applications, one directory each
    \...                 the user's documents

**The accessories are in `\GEM\`, not `\APPS\`, and the distinction is
not filing.**  An application is something the desktop launches: the AES
loads it, runs it, frees it, and the desktop comes back.  An accessory is
loaded once, by the AES itself, before the first program -- and it stays,
through every program that runs afterwards, which is why it appears in
the Desk menu rather than as an icon.  So the AES looks for `*.ACC`
in its OWN directory, the one `GEM.COM` was started from, and never in
`\APPS\`.  `docs/phase36.md` has the reason it must be loaded first: both
allocators are bump allocators, and anything taken after a program has
loaded is freed underneath it when that program exits.

Every SpartaDOS X medium carries the same `GEM4XE.CFG`, with every
setting in it commented out, so that finding the file is finding its
documentation; the DOS 2 floppy has carried none since phase 43
(section 1), and runs on the same defaults.
How much documentation has gone up and down with the DOS 2 floppy's
room: for two phases it was a generated short form, the keys without the
prose, because the disk had 3 KB free; the packed image gave the room
back and the file grew to 3,280 bytes of essay; and on 2026-09-16
colour-icon support took seven sectors of the image and put the floppy
under its 80-sector floor, so the essay went and the file is the keys
again -- every key `src/sys/config.c` reads, each with its values and
one line of why, about 1.3 KB.  The long form of the reasoning is
section 4a below and `docs/printing.md`; the file now also names
`PRINTER` and `PRINTTO`, which the parser had accepted all along and the
shipped file had never mentioned.

`CLOCK.ACC` is the first one shipped.  It is the same `src/apps/clock.c`
as `\APPS\CLOCK.G4A`, with a different `main`: the program opens its
panel once and exits, the accessory registers "Clock" in the Desk menu
and waits to be asked.  It is on the card and on the applications
floppy, and on no system floppy: it was on every product disk from phase
38, when the packed image made room for it on the DOS 2 floppy, until the
rest of GEMDOS took that disk under its floor of free sectors in phase 42
and every floppy became the system and nothing else (section 1).  The
applications floppy's `INSTALL.BAT` puts it in the installed `\GEM\`,
where the AES finds it.

`build/gem-cf.img` is that layout, less the two files that do not exist
yet (section 5's `LANG.RSC` and a font).  The desktop opens a folder in
a window and runs a `.G4A` from its icon, and `make test-cf` boots the
card into that desktop, so the layout is not a plan.  Two things follow for the loader: an
application is found by path, not by being on `D1:`, and the shell's
command tail (`SH_TAILLEN`, 128 bytes) is what carries arguments -- both
already true.

## 4a. `GEM4XE.CFG`: the settings that cannot live in a dialog

Everything a user can change about gem4xe is in `DESKTOP.INF`, which the
desktop writes and reads with a GEM already on the screen.  Two things
cannot be, and they are in a plain text file beside `GEM.COM`:

    # VIDEO=AUTO       AUTO, VBXE, ANTIC (= SAFE)
    # MOUSE=AUTO       AUTO, ST, AMIGA, TRAKBALL, TABLET, XEM1, NONE

**The screen**, because a monitor that will not lock to the VBXE's
640x240 leaves the user with nothing to put a dialog on.  `VIDEO=ANTIC`
brings the machine up on stock ANTIC -- 320x168 in two colours, on
Atari's condensed 6x6 face -- even where a VBXE is fitted and working.
That is the safe mode, and it has to beat a working VBXE or it is not a
way out.

**The mouse**, because a user whose pointer does not move cannot reach a
dialog either.

`VIDEO` names a **screen**, not a resolution, because there is one VBXE
mode today: 640x240 in sixteen colours.  VBXE HR can also be 512 or 672
pixels wide, but those change how much of the line is drawn, not the
timing a monitor has to lock to, so they are not the answer to "my
monitor will not show this" -- ANTIC is.  If more modes are ever added
they get names in this key and old files keep working, because a value
gem4xe does not know is ignored.

The file ships with every setting commented out, so finding it is finding
its documentation.  A missing file means the same thing.  An unknown key
or value is skipped, never refused: a typo in this file must not be able
to stop the machine starting, and a file written for a later gem4xe has
to keep booting this one.

**The recovery path is a DOS prompt.**  Boot to DOS, edit the file, run
GEM again.  On media that starts GEM by itself -- the SpartaDOS batch
file of section 2, DOS 2's `AUTORUN.SYS` -- GEM comes straight back, so
there the answer is to boot another disk and edit the file from that.
That is worth saying in the manual next to the file, because it is the
one case where the product's best feature (it comes up in the desktop
with nothing typed) is in the way.

`tests/emu/m26_fallback.py` boots the shipped disk three ways -- with a
VBXE, without one, and with `VIDEO=ANTIC` against a working VBXE -- and
checks which device the VDI ended on, what the AES laid out for, what the
file parsed to, and that the two routes to ANTIC give the same picture to
the pixel.  `docs/phase34.md` has the rest.

## 5. Localization: `LANG.RSC`

**The rule: no string a person reads is in the C.**  Eleven were, when
this was written -- the desktop's alerts, written as literals while the
milestones were about mechanism -- and they are not any more.  The
donor's shape is the one they moved into: EmuTOS's desktop keeps them
as *free strings* in its resource and asks for them by index
(`fun_alert(1, STDELDIR)`), our builder already made free strings
(`tools/rsc.py`'s `free_string`) and the AES already resolved them
(`rsrc_gaddr(R_STRING, n)` answers a bank-$00 address, which is what
`form_alert` wants).  Eleven call sites became **nine strings** -- two
of the texts were used twice -- with the donor's names where the donor
has the same alert (`STNOWIND`, `STDEFDIR`, `STDELFIL`, `STDELDIR`,
`STFOFAIL`, `STFO8DEE`, `STDEEPPA`), and `test-m19` puts one on the
screen (New folder, the name it already has) and compares it against
the model.  The resource grew 430 bytes and the desktop's near
constants shrank by 450, which gave a page of the pool back.

**One string cannot come from the resource**: the alert that says
`DESKTOP.RSC` is not on the disk.  It stays a literal in `desktop.c`,
with a comment saying why -- and it is the one line a translator will
have to accept in English.

The split, once they are out of the C:

- **`LANG.RSC` -- what the *system* says.**  The AES's and the shell's
  own text: `form_alert`'s default button labels, the file selector's
  strings, the error texts GEMDOS returns as words, month names, the
  "no such program" alert.  `GEM.COM` loads it once at start and keeps
  it; a translator ships one file.
- **An application's own resource -- what the *application* says.**
  `DESKTOP.RSC` is one of these.  Translations are longer than English
  by a third or more, and a GEM dialog's geometry is *in* the resource,
  so a translated application ships a translated resource with its
  boxes widened -- which is how DRI and Atari did it, one `.RSC` per
  language, and why the split above puts the layout with the text
  rather than the text on its own.

**`LANG.RSC` exists, and `make test-m20` proves a translation is a
file.**  `tools/langrsc.py` describes what the system says -- eight
strings today: `form_error`'s five alerts, the one carrying a DOS error
number, and the shell's two failures -- and builds three things from
that one description, because the three must not disagree: the file
itself, the same bytes as a `__far` array in the image, and the indices
the C uses.  `src/aes/lang.c` reads the file at start-up into far memory,
and `lang_str()` copies the string being used into one near buffer, which
is what `form_alert` wants.  The built-in copy is what a disk without the
file falls back on, because a system that cannot say "this application
cannot be found" *because its language file is missing* is worse than one
that says it in English.  **The file overrides; it is not required.**

The gate runs `form_error` -- the call that takes a number and no string,
so every character that reaches the screen came from the system -- on
three disks: the product's `LANG.RSC`, a German one whose every string
differs and is longer, and no file at all.  Each is compared pixel for
pixel with `tools/aesref.py` given the strings that disk carries.  The
first and the third draw the same screen; the second draws the
translation, which is what says the file is being read rather than
ignored.

Two rules a translation must keep, and the gate holds one to both:
`form_alert`'s grammar (`[icon][text|lines][buttons]`), and one `#` with
two characters after it in the string that carries an error number --
the number is written over them, found by searching for the `#` rather
than by counting, so the phrase may move.

What is not in `LANG.RSC`, and why:

1. ~~Strings must be reachable without spending bank $00~~ -- done, as
   above.  But the file selector's **tree** is still in the far image
   (`tools/fselrsc.py`) rather than in `LANG.RSC`, because the selector
   copies its whole resource into the application pool each time it
   opens: a kilobyte of alert text there would be a kilobyte less for
   the application's own resource, every time (`docs/phase11.md` has
   that budget).  So a translation cannot widen the selector's boxes
   yet.  The desktop's "`DESKTOP.RSC` is not on the disk" alert stays a
   literal for the reason above it; `LANG.RSC` could serve it once the
   application ABI has a call for a system string, which it has not.
2. ~~**The character set has to survive the round trip.**~~ Done, and
   `make test-m21` boots it.  The 8x8 face gem4xe links is EmuTOS's
   Atari ST set, whose high half is the accented Latin letters of
   Western Europe; Polish, Czech, Greek and Cyrillic need a different
   set, so **the strip is loadable**.  `SYSTEM.FNT` beside `GEM.COM` is
   read at start-up (`src/vdi/font.c`, from `lang_init`, so a
   translation's two files are read together), and 2 KB of glyphs
   replace the linked ones in far memory and in the VRAM masks.

   EmuTOS ships exactly the sets that are wanted, all GPL: `make fonts`
   writes `l2.fnt` (Latin-2), `ru.fnt` (Cyrillic), `gr.fnt` (Greek) and
   `tr.fnt` (Turkish) out of a checkout in DRI's own `.FNT` format
   (`tools/mkfnt.py`).  The gate uses none of them -- a gate should not
   need a checkout -- but the *system font inverted*, built from the
   strip that is committed, so every glyph differs and "the file is what
   is being drawn from" is a screenshot rather than a matter of trust.

   **The cell stays 8x8, and that is a decision.**  The AES asks for the
   character cell once, at start-up, and lays the desktop out with the
   answer; the blitter has no shifter, so every glyph is also a
   pre-shifted second copy in VRAM; and the host reference draws the
   same cells.  A face of another SIZE is all of that again and earns
   its place only when there is something to do with it.  A face of
   another ALPHABET is 2 KB and a file.  So the loader refuses -- and
   keeps the face it had -- a form that is not 256x8, a character range
   that is not 0..255, a `top` that is not the linked font's, and the
   colour or word-swapped variants of the format.

   **GDOS's own calls do this**, since they are the ones an application
   would use: `vst_load_fonts` (119) reads `SYSTEM.FNT` and answers how
   many faces that added (0 or 1, there being one place to look),
   `vst_unload_fonts` (120) goes back to the linked face, `vst_font`
   (21) chooses between them and `vqt_name` (130) names them.  That is
   the font half of GDOS and not the rest of it: no `ASSIGN.SYS`, no
   NDC, no Bezier, no metafile.  With 14 MB of RAM the memory was never
   the constraint -- the geometry is.

Two more things a translator will ask for, recorded so they are not
forgotten: **the keyboard** (gem4xe reads POKEY scan codes directly,
`src/vdi/pointer.c` and `src/sys/irq.s`, through a table that is the US
layout -- a localized layout is another table, not new code), and
**date and time formats** in the window's information line and the file
selector (`DD/MM/YY` against `MM/DD/YY` is a one-line difference and a
real one).

## 6. What this means for the milestones

Nothing above blocks the desktop's remaining features, but two pieces
are cheapest now and dear later:

1. ~~The eleven strings out of the C and into `DESKTOP.RSC`'s free
   strings~~ -- done, above.
2. ~~`AUTOEXEC.BAT` on the SpartaDOS product disk and `AUTORUN.SYS` on
   the DOS 2 one~~ -- done.  Both product disks boot into the desktop
   with nothing typed and `make test-boot` requires it.  The SpartaDOS
   one runs `STARTUP.BAT` (3.2) or `AUTOEXEC.BAT` (X); the DOS 2 one had
   to become **double density** first, which `tools/atr.py` writes now.
   Section 2 has the measurements, the names each DOS actually looks
   for, and the one DOS that still will not do it.

3. ~~The APT/CF image writer in `tools/`, and a gate that boots one~~ --
   done: `make` writes `build/gem-cf.img`, an APT card with the install
   layout on it; `tests/host/test_apt.py` holds the table and the
   512-byte SDFS to the rules a reader applies; and `make test-cf` boots
   it into the desktop on the machine this project is for -- U1MB flash
   for SpartaDOS X *and* the PBI BIOS that mounts the partitions, a
   SIDE 2 with the card on its bus.  No driver file on the card, and no
   SDX distribution disk needed after all.  Section 3 says why, and what
   three things about that machine had to be measured first.

4. ~~`LANG.RSC` and the far-string helper; a loadable font~~ -- done,
   both, in section 5: `make test-m20` proves a translation of what the
   system says is a file, and `make test-m21` proves the character set
   it says it in is another.  What a translator still cannot change is
   the file selector's dialog (its tree is in the image, for the pool
   reason in section 5), the keyboard layout, and the date format.

## The version number

`VERSION` at the top of the tree holds it, and **that file is the only
place it lives**: `tools/deskrsc.py` reads it into the About dialog, so
`tools/deskref.py`'s model of that dialog reads the same string and the
three gates that compare it pixel for pixel cannot disagree with the
product -- provided the resource was remade.  It was not, once: the
Makefile's rule for `build/desktop.rsc` did not list `VERSION`, so
0.1.1 went out with an About box that says 0.1 (`phase38.md`).  The
rule lists it now, and `make release` refuses a resource whose About
box does not say what `VERSION` says.  `make dist` writes both numbers
into the distribution's own `VERSION`:

    0.1 (2026-09-11-bd01a07)

They answer different questions.  The release is what a human says out
loud and what *Desk -> About gem4xe* shows; the date and commit identify
the build exactly, and `make dist` refuses a dirty tree so that the
second one is true.  A **build stamp in the About box was the other
candidate and is the wrong thing**: it would change every day, and every
gate that compares that dialog would have to be told the date.  A version
changes when somebody decides it does.

`make release` is `make dist` for the public, and the version is its
name: `build/gem4xe-0.1.1.tar.gz`, the same tree again as
`gem4xe-0.1.1.zip` for Windows, the floppies on their own as
`gem4xe-0.1.1.atr` and (since phase 42) `gem4xe-0.1.1-apps.atr`, and one
`gem4xe-0.1.1.sha256` covering them for the release page; the inner
`VERSION` still carries the date and commit.  What it leaves out is
`gem-boot.atr`, because it boots a DOS that is not gem4xe's to give away
(`fixtures.toml.example`); the card image, `gem-sdx.atr` and
`gem-apps.atr` are built from this tree alone and carry no DOS, so they
travel (`docs/media.md`, *The floppies the release can carry*).  The
page says which file is missing and how to make one from `system/`
rather than pretending the download is the same one a tester gets.

The About box's other number is the **AES version**, 1.40, filled in at
run time from `global[0]`.  That is the AES gem4xe claims to be -- TOS
1.04's, which is what EmuTOS reports -- and not gem4xe's own.
