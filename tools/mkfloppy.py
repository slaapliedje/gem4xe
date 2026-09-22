#!/usr/bin/env python3
"""The gem4xe floppies: SDFS disks with no DOS on them.

The two floppies `make dist` builds each boot a DOS that is not gem4xe's
to give away (fixtures.toml.example), so the public release had none of
its own until these.  Each is a double-sided double-density disk (1440
sectors of 256 bytes, 360 KB) formatted SDFS, with NO boot code beyond
the stub every blank SDFS disk has.

  gem-sdx.atr   THE SYSTEM: \\GEM\\ as the card holds it -- GEM.COM, the
                desktop and its resources, LANG.RSC, GEM4XE.CFG, 816.COM
                -- the card's AUTOEXEC.BAT, and INSTALL.BAT.  It boots
                under SpartaDOS X, which lives in the machine rather than
                on the disk: from a cartridge or from Ultimate 1MB flash,
                SDX comes up, changes to the disk in D1: and runs its
                AUTOEXEC.BAT, and that is GEM.
  gem-apps.atr  THE APPLICATIONS: \\APPS\\, the desk accessories and the
                control panel extension in \\GEM\\, and an INSTALL.BAT
                of its own.  Not a boot disk: it goes
                in another drive beside the system, and the desktop opens
                it there.

A floppy is where gem4xe starts, not where it lives (docs/media.md).
Each disk's INSTALL.BAT copies what that disk holds onto a drive the
user names -- `-INSTALL D2:` at the SpartaDOS X prompt -- and the
system's leaves the drive an AUTOEXEC.BAT when it has none.  One batch a
disk, because SpartaDOS X warns against changing the disk a batch file is
running from.  The accessory is on the applications disk rather than the
system's because the rest of GEMDOS took the DOS 2 floppy under its floor
of free sectors (docs/phase42.md), and every floppy is the system and
nothing else since.

Both stay double-sided, which the system alone no longer needs, so that
the pair is one geometry: the XF551, every SIO emulator and every FAT
loader read it, and SDX mounts it.

  python3 tools/mkfloppy.py <out.atr> [--apps] [--add FILE PATH]...
  python3 tools/mkfloppy.py --batch system|apps <out.bat>

The file tables and the batch files are tools/mkcf.py's own, so the pair
IS the card's system partition in two halves rather than lists that
could drift from it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkcf                                      # noqa: E402
from atr import ATRImage, Sdfs                   # noqa: E402

SECTOR = 256
SECTORS = 1440                                   # DSDD, as an XF551 writes


def build(out, adds=(), boot=mkcf.BOOT, root=None, table=None, install=None,
          dirs=("GEM",), volname="GEM4XE"):
    """The system floppy by default; build_apps() for the other."""
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    table = mkcf.SYSTEM if table is None else table
    install = mkcf.INSTALL_SYSTEM if install is None else install
    img = ATRImage(SECTOR, SECTORS)
    fs = Sdfs.format(img, volname)
    for d in dirs:
        fs.mkdir(d)
    for path, name in list(table) + list(adds):
        with open(os.path.join(root, path), "rb") as f:
            data = f.read()
        fs.add_file(name, data)
        print(f"{out}: {name} <- {path} ({len(data)} bytes)")
    if boot:
        fs.add_file("AUTOEXEC.BAT", mkcf.batch(boot))
    if install:
        fs.add_file("INSTALL.BAT", mkcf.batch(install))
    img.save(out)
    free = fs.free_count()
    print(f"{out}: {img!r}, {fs.volname}, no DOS; {free} sectors free, "
          f"{free * (SECTOR - 2) // 1024} KB")
    return out


def build_apps(out, root=None):
    return build(out, (), None, root, mkcf.APPS, mkcf.INSTALL_APPS,
                 mkcf.DIRS, "GEMAPPS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--apps", action="store_true",
                    help="the applications floppy rather than the system's")
    ap.add_argument("--batch", choices=("system", "apps"),
                    help="write that disk's INSTALL.BAT to OUT, and nothing else")
    ap.add_argument("--add", nargs=2, action="append", default=[],
                    metavar=("FILE", "PATH"))
    a = ap.parse_args(argv)
    if a.batch:
        with open(a.out, "wb") as f:
            f.write(mkcf.batch(mkcf.INSTALL_SYSTEM if a.batch == "system"
                               else mkcf.INSTALL_APPS))
        return 0
    if a.apps:
        build_apps(a.out)
    else:
        build(a.out, a.add)
    return 0


if __name__ == "__main__":
    sys.exit(main())
