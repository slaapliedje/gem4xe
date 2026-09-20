#!/usr/bin/env python3
"""The gem4xe CF card: an APT-partitioned image with the system on it.

This is the volume the desktop is for.  A floppy holds the system and
little else (docs/shipping.md, section 1); a card holds the system, the
applications and the documents, and SpartaDOS X mounts its partitions as
D1:, D2:, ... through the APT table tools/apt.py writes.

    D1:  the system      \\GEM\\GEM.COM       the VDI, AES, GEMDOS, shell
                         \\GEM\\DESKTOP.PRG   the desktop
                         \\GEM\\DESKTOP.RSC   its resource
                         \\APPS\\...          applications
                         AUTOEXEC.BAT       cd into \\GEM and run it
    D2:  documents       empty, and the reason the table has two entries

  python3 tools/mkcf.py <out.img> [--mb 16] [--system-mb 8] [--fat MB]
                        [--add FILE PATH]... [--boot "CD >GEM"]

Every path is SpartaDOS's: `>` between the parts, no drive letter.  The
image is a plain file of 512-byte blocks -- what a card reader writes to
a card, and what the emulator's `harddisk` device reads.

`--fat MB` is the SD-card shape: a FAT32 partition of that size first,
then the APT table and the partitions above.  A SubCart or an AVGCART
browses the first FAT partition itself and, in its SIDE 2 emulation,
hands the whole card to the U1MB's PBI BIOS, which finds the table
through the MBR exactly as it does on a CF card.  The FAT volume is
made by mkfs.fat and carries one README.TXT; it is the cart's, not
GEM's.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apt                                       # noqa: E402
from atr import Sdfs                             # noqa: E402

MB = 1 << 20
EOL = 0x9B
# What the system partition carries, and where.  The names are the ones
# src/aes/shel.c looks for: the shell opens DESKTOP.PRG in the current
# directory, so AUTOEXEC.BAT changes into \GEM before it runs GEM.COM.
SYSTEM = [("build/gem.xex", "GEM>GEM.COM"),
          ("build/desktop.g4a", "GEM>DESKTOP.PRG"),
          ("build/desktop.rsc", "GEM>DESKTOP.RSC"),
          # the chooser, loaded only while Set preferences is open
          ("build/prefs.rsc", "GEM>PREFS.RSC"),
          ("build/lang.rsc", "GEM>LANG.RSC"),
          ("build/gem4xe.cfg", "GEM>GEM4XE.CFG"),
          # the escape hatch the page promises "on the disk": switches a
          # Rapidus by hand if the loader somehow did not (tools/mk816.py)
          ("build/816.com", "GEM>816.COM")]
# ...and what is not the system: the desk accessories, in the system's
# directory -- which is where the AES looks for *.ACC, and not in \APPS\
# with the programs -- and the applications.  The card carries both
# tables; the floppies carry one each (tools/mkfloppy.py, docs/media.md).
#
# THREE ACCESSORIES, and the Desk menu has six slots (src/aes/proc.h,
# NUM_PROCS 7).  CONTROL.ACC and CALC.ACC are --data-model=large, so
# rs_load puts their resources in far memory and they cost bank $00
# nothing beyond their near regions (docs/phase47.md).
#
# The calculator ships TWICE, from one source: APPS>CALC.PRG is the
# program and GEM>CALC.ACC the accessory (src/apps/calcapp.c and
# calcacc.c around src/apps/calc.c).  They share one CALC.RSC, which is
# on the disk twice because \GEM\ and \APPS\ are installed separately
# and either may be the only one present.
APPS = [("build/clockacc.g4a", "GEM>CLOCK.ACC"),
        ("build/clock.rsc", "GEM>CLOCK.RSC"),
        ("build/cpanelacc.g4a", "GEM>CONTROL.ACC"),
        ("build/cpanel.rsc", "GEM>CPANEL.RSC"),
        ("build/calcacc.g4a", "GEM>CALC.ACC"),
        ("build/calc.rsc", "GEM>CALC.RSC"),
        ("build/hello_app.g4a", "APPS>HELLO.PRG"),
        ("build/calc.g4a", "APPS>CALC.PRG"),
        ("build/calc.rsc", "APPS>CALC.RSC"),
        ("build/clock.g4a", "APPS>CLOCK.PRG"),
        ("build/clock.rsc", "APPS>CLOCK.RSC")]
DIRS = ["GEM", "APPS"]
BOOT = ["CD >GEM", "GEM"]

# INSTALL.BAT, one to a floppy: what that disk holds, onto a drive the user
# names at the SpartaDOS X prompt -- `-INSTALL D2:`.  One batch a disk and
# not one that asks for the next, because SpartaDOS X warns against
# changing the disk a batch file is running from (User Guide 4.48, PAUSE).
# Every command was run under SDX 4.50 before it was written here, and
# tests/emu/install.py runs these: IF EXISTS +S sees a directory, a batch
# goes on past an error, and `>` at the start of a path is the root of the
# drive the batch was started from.  The system's leaves the drive an
# AUTOEXEC.BAT that starts GEM, but never over one that is already there.
INSTALL_SYSTEM = [
    "; gem4xe: the system onto a drive. -INSTALL D2:",
    'IF "%1"==""',
    "  ECHO Which drive? As in: -INSTALL D2:",
    "  EXIT",
    "FI",
    "IF NOT EXISTS +S %1>GEM",
    "  MD %1>GEM",
    "FI",
    "COPY >GEM>*.* %1>GEM>",
    "IF EXISTS %1>AUTOEXEC.BAT",
    "  ECHO %1AUTOEXEC.BAT is kept. To start",
    "  ECHO GEM it wants: CD \\GEM, then GEM",
    "ELSE",
    "  COPY >AUTOEXEC.BAT %1>",
    "FI",
    "ECHO The system is on %1",
]
INSTALL_APPS = [
    "; gem4xe: the applications onto a drive. -INSTALL D2:",
    'IF "%1"==""',
    "  ECHO Which drive? As in: -INSTALL D2:",
    "  EXIT",
    "FI",
    "IF NOT EXISTS +S %1>APPS",
    "  MD %1>APPS",
    "FI",
    "IF NOT EXISTS +S %1>GEM",
    "  MD %1>GEM",
    "FI",
    "COPY >APPS>*.* %1>APPS>",
    "COPY >GEM>*.* %1>GEM>",
    "ECHO The applications are on %1",
]


def batch(lines):
    """A SpartaDOS batch file as the DOS reads it: ATASCII lines, each
    ending in EOL."""
    return b"".join(line.encode("ascii") + bytes([EOL]) for line in lines)
FAT_LBA = 2048                  # where a PC's tools start the first partition
FAT_README = """gem4xe is on this card's APT partitions, not here.
The U1MB PBI BIOS mounts them as D1: (the system) and D2:
when the cart's SIDE 2 / IDE emulation is on and the U1MB
setup has PBI BIOS and Hard disk enabled.  This FAT volume
is the cart's own; put what its browser should see here.
"""


def fat_volume(blocks, out):
    """A FAT32 file system of `blocks` blocks, made by mkfs.fat beside
    the image, with the README in it."""
    tmp = out + ".fat"
    mkfs = shutil.which("mkfs.fat") or shutil.which("mkfs.vfat")
    if not mkfs:
        raise SystemExit("--fat needs mkfs.fat (dosfstools)")
    if os.path.exists(tmp):
        os.remove(tmp)
    subprocess.run([mkfs, "-F", "32", "-n", "GEM4XE", "-C", tmp, str(blocks // 2)],
                   check=True, stdout=subprocess.DEVNULL)
    if shutil.which("mcopy"):
        subprocess.run(["mcopy", "-i", tmp, "-", "::README.TXT"], check=True,
                       input=FAT_README.replace("\n", "\r\n").encode("ascii"))
    with open(tmp, "rb") as f:
        data = f.read()
    os.remove(tmp)
    if len(data) != blocks * apt.BLOCK:
        raise SystemExit(f"{mkfs} made {len(data)} bytes, not {blocks * apt.BLOCK}")
    return data


def build(out, mb=16, system_mb=8, adds=(), boot=BOOT, root=None, fat_mb=0,
          cfg=None):
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    system = [(cfg if cfg and name == "GEM>GEM4XE.CFG" else path, name)
              for path, name in SYSTEM + APPS]
    if fat_mb:
        fat_blocks = fat_mb * MB // apt.BLOCK
        apt_lba = FAT_LBA + fat_blocks
        img = apt.Image(apt_lba + mb * MB // apt.BLOCK)
        parts = apt.layout(img, [system_mb * MB // apt.BLOCK, 0],
                           at=apt_lba + apt.HEADER_BLOCKS)
        apt.write_table(img, parts, apt_lba=apt_lba, fat=(FAT_LBA, fat_blocks))
        fat = fat_volume(fat_blocks, out)
        img.data[FAT_LBA * apt.BLOCK:apt_lba * apt.BLOCK] = fat
        print(f"{out}: FAT32 {fat_mb} MB at block {FAT_LBA}, APT table at block {apt_lba}")
    else:
        img = apt.Image(mb * MB // apt.BLOCK)
        parts = apt.layout(img, [system_mb * MB // apt.BLOCK, 0])
        apt.write_table(img, parts)
    fs = Sdfs.format(parts[0], "GEM4XE")
    Sdfs.format(parts[1], "DOCS")
    for d in DIRS:
        fs.mkdir(d)
    for path, name in system + list(adds):
        with open(os.path.join(root, path), "rb") as f:
            data = f.read()
        fs.add_file(name, data)
        print(f"{out}: {name} <- {path} ({len(data)} bytes)")
    if boot:
        fs.add_file("AUTOEXEC.BAT", batch(boot))
    img.save(out)
    free = fs.free_count() * apt.BLOCK
    print(f"{out}: {img!r}, {len(parts)} partitions; D1: {fs.volname} "
          f"{free // MB} MB free of {system_mb}, D2: the rest")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--mb", type=int, default=16, help="the APT part: the whole card without --fat")
    ap.add_argument("--system-mb", type=int, default=8, help="the first partition")
    ap.add_argument("--fat", type=int, default=0, metavar="MB",
                    help="a FAT32 partition of MB first: the SD-card shape")
    ap.add_argument("--add", nargs=2, action="append", default=[],
                    metavar=("FILE", "PATH"))
    ap.add_argument("--boot", action="append", metavar="LINE",
                    help="a line of AUTOEXEC.BAT, in order; the default runs "
                         "GEM.  --boot \"CD >GEM\" alone stops at the prompt, "
                         "which is what a GEMDIAG session wants")
    ap.add_argument("--cfg", metavar="FILE",
                    help="the GEM4XE.CFG to carry instead of build/gem4xe.cfg")
    a = ap.parse_args(argv)
    build(a.out, a.mb, a.system_mb, a.add, fat_mb=a.fat,
          boot=a.boot if a.boot is not None else BOOT, cfg=a.cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
