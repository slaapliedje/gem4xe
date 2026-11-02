#!/usr/bin/env python3
"""The SpartaDOS boot disk for the SpartaGEM gates: a fresh SDFS volume
that boots the SpartaDOS 3.2 on the fixture disk (its boot sectors and
DOS file copied over -- the fixture itself is never modified), with the
program, the file-layer fixtures and a small directory tree on it:

    M3.COM  TEST.TXT  TEST.RSC  OUT.TXT       what the DOS 2 disk carries
    SUB>ONE.TXT  SUB>TWO.DAT  SUB>DEEP>THREE.TXT   folders for the selector

Under SpartaDOS X the cartridge boots instead and this is just D1:, which
is why the tree, not the boot code, is the point of the disk.

  python3 tools/mkspdisk.py <sparta32.atr> <m3.xex> <out.atr> [--name M3.COM] [--sectors N]
                            [--add FILE NAME]... [--mkdir NAME]...
                            [--tree] [--boot "CD >GEM|GEM"]
  python3 tools/mkspdisk.py --g4dos - <m3.xex> <out.atr> --name GEM.COM ...

--g4dos boots G4DOS (src/fdos.s, as tools/mkfloppy.py puts it on the
system floppy) instead of SpartaDOS 3.2, and there is no source disk: G4DOS
loads D1:GEM.COM by itself, so the program is named that (test-m15g).

--boot writes the batch files that run a command at boot, which is how the
product disk comes up in the desktop rather than at a prompt (BOOT_FILES
below, docs/shipping.md).  The gates' disks do not use it: they type the
program's name after switching the CPU, and a disk that ran it first would
run it on the 6502.

tests/emu/m14_sparta.py predicts the listing from the image itself
(tools/atr.py), not from TREE below.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atr import ATRImage, Sdfs  # noqa: E402

# The batch files a SpartaDOS boot runs, both carrying the one command
# --boot names.  Which one runs depends on which DOS booted, and a
# product disk cannot know: SpartaDOS 3.2 from this disk looks for
# STARTUP.BAT (the name is in X32G.DOS beside D1:AUTORUN.SYS, and
# CHANGES.32G documents it), while SpartaDOS X boots from the cartridge
# or U1MB flash and reads CONFIG.SYS then AUTOEXEC.BAT off D1:.  So the
# disk carries both, four bytes each, and the program keeps its name.
BOOT_FILES = ("STARTUP.BAT", "AUTOEXEC.BAT")
EOL = bytes([0x9B])

# (path, contents); a path with no contents is a directory
TREE = [
    ("SUB", None),
    ("SUB>ONE.TXT", b"one\x9b"),
    ("SUB>TWO.DAT", b"two\x9b"),
    ("SUB>DEEP", None),
    ("SUB>DEEP>THREE.TXT", b"three\x9b"),
]


def build(src_atr, xex, out_atr, sectors=1040, adds=(), volname="GEM4XE", name="M3.COM",
          boot=None, tree=False, dirs=(), g4dos=False):
    os.makedirs(os.path.dirname(os.path.abspath(out_atr)), exist_ok=True)
    img = ATRImage(128, sectors)
    fs = Sdfs.format(img, volname)
    if g4dos:
        from mkfloppy import fdos_parts
        fs.boot_gem4xe(*fdos_parts(os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "..")))
    else:
        fs.boot_from(Sdfs(ATRImage.load(src_atr)))
    for d in dirs:                      # before anything that goes in one
        fs.mkdir(d)
    with open(xex, "rb") as f:
        fs.add_file(name, f.read())
    for path, name in adds:
        with open(path, "rb") as f:
            fs.add_file(name, f.read())
    if boot:
        for batch in BOOT_FILES:
            fs.add_file(batch, EOL.join(
                ln.encode("ascii") for ln in boot.split("|")) + EOL)
    if tree:
        for path, data in TREE:
            if data is None:
                fs.mkdir(path)
            else:
                fs.add_file(path, data)
    img.save(out_atr)
    print(f"{out_atr}: {sectors} x 128, {len(fs.list())} in MAIN, "
          f"{fs.free_count()} sectors free")
    return out_atr


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src", help="a SpartaDOS 3.2 boot disk (a copy), or - with --g4dos")
    ap.add_argument("xex", help="the program, stored under --name")
    ap.add_argument("out")
    ap.add_argument("--name", default="M3.COM", help="the program's name on the disk")
    ap.add_argument("--sectors", type=int, default=1040)
    ap.add_argument("--add", nargs=2, action="append", default=[], metavar=("FILE", "NAME"))
    ap.add_argument("--mkdir", action="append", default=[], metavar="NAME",
                    help="a directory, made before the files that go in it")
    ap.add_argument("--tree", action="store_true",
                    help="the file selector's fixture directory as well -- "
                         "what a GATE disk wants and a product disk does not")
    ap.add_argument("--boot", metavar="CMD",
                    help="a command line for STARTUP.BAT and AUTOEXEC.BAT")
    ap.add_argument("--g4dos", action="store_true",
                    help="boot G4DOS, which loads GEM.COM, not SpartaDOS 3.2")
    a = ap.parse_args(argv)
    build(a.src, a.xex, a.out, a.sectors, a.add, name=a.name, boot=a.boot,
          tree=a.tree, dirs=a.mkdir, g4dos=a.g4dos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
