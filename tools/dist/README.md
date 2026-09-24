# gem4xe — how to try it

**Version {version}** — build {stamp}

GEM on an Atari XL/XE: the VDI, the AES and a desktop, at 640 x 240 in
16 colours on VBXE's HR overlay, running native on a 65C816.  It is a
port of the Caldera-GPL Digital Research sources by way of EmuTOS, and
it is early — this page says what works and what does not, and both
halves are generated from the program itself.

## The quickest way in

**`gem4xe.car`.**  One file, on an Ultimate Cart, a MaxFlash or any
other cartridge that takes an AtariMax 1 Mbit image — or handed to an
emulator with `--cart`.  Turn the machine on and the desktop comes up:
no DOS to find, no disk to write, nothing to type.

It carries its own read-only `D1:`, so everything in `system/` below is
on it and the system reads its files the ordinary way.  Two things to
know: it takes about **twenty-six seconds** to read itself out of the
ROM and prints a dot per segment while it does, so it has not hung; and
it is **read-only**, so *Options → Save desktop* and copying a file will
say they cannot.  Nothing else writes, so nothing else is affected.

Everything below this line is the same gem4xe on media you can write to.

## The machine

| | |
|---|---|
| **VBXE** | wanted, not required; an **FX core, version 1.26**.  gem4xe detects the core by the low nibble of `CORE_REVISION` and writes an overlay priority of `$FF`, because bits 6/7 changed meaning at 1.26 and a priority of `$00` makes the overlay vanish there.  **Without a VBXE you get 320 x 168 on ANTIC mode F instead** — one `GEM.COM` carries both drivers and picks at start-up, and `VIDEO=ANTIC` in `GEM4XE.CFG` forces the small screen on a machine that has a VBXE its monitor will not show |
| **a 65C816 with linear RAM** | required. **Rapidus** is the one this is tested on; Antonia should qualify and is not emulated, so it is untested |
| **Ultimate 1MB** | optional. Its DS1305 is where file timestamps come from, and its flash can hold SpartaDOS X and the PBI BIOS that mounts a CF card |

gem4xe **refuses a plain 6502** rather than corrupting it: writing the
bank its code lives in needs a 65C816, and on an NMOS 6502 the long
store is an unstable undocumented opcode.  A machine that *has* an
accelerator sitting in 6502 mode is a different case, and the loader
switches that one itself — see *Booting*.

## In the emulator

[AltirraSDL](https://github.com/ilmenit/AltirraSDL), or Altirra with the
same devices.  This is the command line the test suite itself uses:

    AltirraSDL --pal --hardware 800xl --kernel xl --nobasic \
        --memsize 1088K --cleardevices \
        --adddevice "vbxe,version=126,alt_page=false,shared_mem=false" \
        --adddevice rapidus \
        {emu_disk}

{emu_note}
In desktop Altirra the two devices go in **System > Configure System >
Devices**; the machine is an 800XL, PAL, BASIC off.

**One warning about emulation, and it is not gem4xe's bug.**  Altirra's
65C816 core has two faults in native mode, which is the only mode gem4xe
runs in: a taken branch does the 6502's page-crossing dummy read (so code
in a high bank can put `$D5xx` on the bus and switch a cartridge's bank),
and `SEI` with an interrupt pending leaves a shadow flag the native-mode
vectors never clear, which re-enters the handler at every opcode fetch
until the stack has walked through all of bank `$00`.  Both are fixed
upstream — [pull request #88](https://github.com/ilmenit/AltirraSDL/pull/88),
merged 2026-09-06, so an AltirraSDL built from `main` at 46567a14
(2026-09-09) or later has the fixes; for an older build, the patch is in
the source tree's `tools/altirra/`.  On an emulator without them, a
stall with the screen frozen, or a machine that reboots itself, is more
likely to be one of those than anything here — **on real hardware neither
exists**.

## Booting

**Put the disk in and wait.**  You should see the machine start, stop
and start again, and then the desktop.  (With the cartridge there is no
disk, but the same restart happens and for the same reason.)

The restart is not a fault.  A Rapidus **always cold-boots as a 6502** —
Altirra's own device does it in `ColdReset()` ("reset FPGA, force boot
on 6502"), and the card does the same — so gem4xe begins loading on a
CPU it cannot run on.  Rather than refuse, the loader looks for the card
behind that 6502, and when it finds one it sets `COLDST` (so that the
restart is a *cold* one: a DOS does not run its start-up file after a
warm start) and switches the CPU.  That reset is the stop you see.  The
DOS then starts GEM again, this time on a 65C816, and it stays.

On a machine with an **Ultimate 1MB** the question does not arise: its
Rapidus plugin sets the CPU over the M1 signal before the OS runs, so
there is only one boot.

If you have put the files on a disk of your own and start GEM **by
typing its name**, the same thing happens — but the DOS has no start-up
file to run afterwards, so you come back to a prompt on a machine that
is now a 65C816.  Type it once more and it stays.  Giving the disk an
`AUTORUN.SYS` (DOS 2) or a `STARTUP.BAT`/`AUTOEXEC.BAT` holding `GEM`
(SpartaDOS) is what makes that second one unnecessary.

If the machine does **not** switch itself, you will see this instead —
and nothing will have been written:

    gem4xe needs a 65C816: this is a 6502.
    Nothing was changed.  Press a key.

That means no accelerator answered.  On a machine that has one, the
escape hatch is on the disk: press a key to get the DOS back and run
**816** — type `816` at the SpartaDOS prompt, or give `816.COM` to the
DOS 2 disk's binary-load option.  It makes the same three writes by
hand.  **If you have to do that, it is worth reporting**, because the
loader should have.

## On real storage

The card image is for an **APT** interface -- Ultimate 1MB or Incognito,
SIDE/SIDE2/SIDE3, IDE Plus 2.0, MyIDE-II.  They all read the same table,
because the driver that reads it lives in your machine's flash or
cartridge rather than on the card, so there is no per-interface build
and no driver file to copy.

`gem-cf.img` is a whole-card image: writing it **replaces everything on
the card**, and only its first 16 MB are in the partition table.  Give
it a card of its own.

    dd if=disks/gem-cf.img of=/dev/sdX bs=1M conv=fsync    # sdX, not sdX1

{install}

## What is in the download

{disks}

And loose, for putting on a disk of your own — any DOS gem4xe supports
(SpartaDOS 3.2, SpartaDOS X, DOS 2) will do, and the program keeps
whatever name it is given:

{system}

## What works

The desktop:

{works}

and, with the mouse: an item dragged into another window or onto a
folder is **copied** there, the same drag with **SHIFT** held **moves**
it, and a drag onto the trash deletes it.  Show info is also the
rename — what you leave in its name field is what a file is called
afterwards.  Under all of it: windows that open, scroll, size, full and
close, menus, dialogs, alerts, the file selector, and a program run
from its icon that comes back to the desk where it left it.

Translations are read from `LANG.RSC` and an alphabet from a `.FNT`
beside it, so what the system says is on the disk rather than in the
program.

## What is not there yet

These are in the menu and **disabled** — the desktop puts them up
greyed rather than pretending:

{notyet}

Besides those:

- **one item at a time.**  There is no rubber band and no shift-click,
  so every operation works on the single selected item.
- **the desktop remembers its layout only when you ask it to.**
  *Options -> Save desktop* writes a `DESKTOP.INF` and the desktop reads
  it at start-up; nothing is saved automatically, so a power cycle loses
  whatever was not saved.
- **a folder cannot be renamed.**  `XIO 32` renames a file, and both
  SpartaDOS 3.2 and SpartaDOS X answer "file not found" for a
  directory, so Show info shows a folder's name greyed rather than
  offering something the DOS will refuse.
- **a document prints, but the printer DRIVER has nothing clicking it.**
  Double-click a file that is not a program and the desktop offers
  *Show*, *Print* or *Cancel*, as the ST's does; Print sends the file to
  `PRN:` byte for byte, which is what you want for text and what any DOS
  would do.  That is the plain-character path and it needs no driver.

  Separately, the VDI has a *graphics* printer device — 640 x 800 dots,
  which `v_updwk` writes out as PCL 5 or PostScript to wherever
  `PRINTTO=` names, turned on by `PRINTER=` in `GEM4XE.CFG`.  Nothing in
  the desktop opens that workstation yet, so a printed page of GEM
  graphics is still something an application you write yourself does.
- **a clipboard with nothing using it yet.**  `scrp_read` and
  `scrp_write` are served, so two programs can agree on a scrap
  directory and pass files through it, which is what the GEM clipboard
  is; nothing in `\APPS\` cuts or pastes yet.

## Writing a program for it

`sdk/gem4xe-sdk.tar.gz` is everything needed to build one, and nothing
of gem4xe itself — an application links against none of it.  Unpack it,
read its `README.md`, and `make` turns its commented example into a
program you can put on the disk beside the others and double-click.
Install it as `.PRG`, which is what the Atari world reads as "run me";
`.APP`, `.TOS` and `.TTP` work too, and so does the container's own
`.G4A`, which is what 0.5 installed.

## If something is wrong

Worth saying, with the report: **the line in `VERSION`** (it is also this
page's subtitle and the name of the folder this came in), which disk,
what the machine is (real or emulated, and with what), what was on the
screen, and what you did.  A screenshot settles most of it.  The refusal
in step 1 is not a fault; anything after step 3 probably is.

`VERSION` holds two numbers and they answer different questions: the
release, which is what **Desk -> About gem4xe** shows and what to say out
loud, and the date and commit, which identify the build exactly.  The
About box's *other* number, the AES version, is 1.40 for every build --
it is the AES gem4xe claims to be, not gem4xe's own.

## Licence

gem4xe is **GPLv2 or later** — `COPYING`, and the source carries the
lineage: EmuTOS, which is the Caldera-GPL'd Digital Research GEM.
`src/gem4xe-src.tar.gz` is the tree these binaries were built from,
exactly as committed, because that is what the licence asks for; the
tree itself lives at <https://github.com/slaapliedje/gem4xe>, and the
build stamp at the top of this page names the commit.

One footnote, for completeness rather than because it affects you: about
**815 bytes** of `GEM.COM` is the C compiler's own runtime, which is the
compiler author's rather than ours.  The GPL carves exactly that out --
a "System Library" of "a compiler used to produce the work" (GPLv3 §1;
GPLv2 §3 says the same more loosely) is not part of the Corresponding
Source -- and Calypsi's own licence expressly allows "producing
application software for vintage and retro computing systems".
`docs/licence.md` in the source has it in full.  Pass these files on
freely.

Two of those runtime routines, the far `memcpy` and `memset`, began life
in NuttX and carry a notice the BSD licence asks to be reproduced here:

> Copyright (C) 2007, 2011 Gregory Nutt.  All rights reserved.
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions
> are met: 1. Redistributions of source code must retain the above
> copyright notice, this list of conditions and the following
> disclaimer.  2. Redistributions in binary form must reproduce the
> above copyright notice, this list of conditions and the following
> disclaimer in the documentation and/or other materials provided with
> the distribution.  3. Neither the name NuttX nor the names of its
> contributors may be used to endorse or promote products derived from
> this software without specific prior written permission.
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
> "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
> LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
> A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT
> OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
> SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
> LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
> DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
> THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
> (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
> OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

{dosnote}
