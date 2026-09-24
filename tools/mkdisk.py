#!/usr/bin/env python3
"""Build a bootable Atari disk that auto-runs a .xex, for the emulator harness.

Copies a real DOS image (never modifies the original -- retroharness rule: the
fixture must be a COPY) and writes the .xex into it as AUTORUN.SYS, so booting
the disk runs the program with no keystroke driving at all.

That matters more here than it looks: the Rapidus cold-boots as a 6502 and
switching to the 65C816 resets the CPU, so a program cannot switch the CPU and
then keep running.  The machine has to already be a 65C816 when the program
loads -- which means the program must arrive via the boot path, after the
switch, not before it.

  python3 tools/mkdisk.py <source.atr> <program.xex> <out.atr> [NAME]
                          [--enhanced] [--high] [--sweep] [--compact]
                          [--add FILE NAME]...
                          [--remove NAME]...

The default name is HELLO.COM: the fixture DOS is DOS II+/D 6.4, which boots to
a `D1:` command prompt rather than running AUTORUN.SYS, so the harness types the
name to launch it.  That is an advantage here -- it means the program is started
*after* the CPU switch, on the 65C816.

--add puts further files on the disk under the names given -- what the file
layer's gate reads back through CIO (tests/emu/m12_file.py).  --remove
deletes a file the source image carries first: the fixture DOS disk has
the DOS's demonstration programs on it, and the product disk has no room
for them beside GEM.  --sweep deletes every file except the DOS's own
(DOS.SYS and DUP.SYS), which is what the double-density product disk
does: its fixture is somebody's game disk, and all we want off it is the
DOS that boots.  That disk also passes `--remove DUP.SYS`, because the
system outgrew it with the DOS's own shell on board -- seven sectors'
worth -- and a floppy is now a test vehicle rather than how the thing is
run (docs/shipping.md section 2).

--compact, after the sweep, clears the deleted entries behind the last file
so their slots can be used again: a fixture whose directory was full is
otherwise full after the sweep too (atr.Dos2.compact says why).

--enhanced makes the disk DOS 2.5 enhanced density (1040 sectors) before
anything is written: the runner outgrew a single-density disk's 620 free
sectors.  --high then writes the program into the upper half first, the part
a DOS 2.0 cannot reach, so that the boot itself proves the fixture DOS reads
it -- the alternative being a disk that works until a file grows past sector
720 and then fails in a way nothing has tested.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atr import ATRImage, Dos2, enhance  # noqa: E402


# What a DOS 2 disk needs to boot and to have somewhere to come back to:
# the DOS, and the command processor if it is a separate file.  --sweep
# keeps these and deletes the rest; a caller that cannot afford the shell
# removes it by name afterwards, which is not the same decision and is
# made in the Makefile where it is visible.
DOS_FILES = ("DOS.SYS", "DUP.SYS")


def build(src_atr, xex, out_atr, name="HELLO.COM", extra=(), enhanced=False, high=False,
          remove=(), sweep=False, compact=False):
    os.makedirs(os.path.dirname(os.path.abspath(out_atr)), exist_ok=True)
    img = ATRImage.load(src_atr)
    if enhanced:
        img = enhance(img)
    dos = Dos2(img)
    if sweep:
        remove = [f for f in dos.list()
                  if f.upper() not in DOS_FILES] + list(remove)
    for dname in remove:
        dos.delete(dname)
        print(f"{out_atr}: {dname} removed")
    if compact:
        print(f"{out_atr}: {dos.compact()} deleted entries cleared")
    for path, dname in ((xex, name),) + tuple(extra):
        if dos.find(dname):
            raise SystemExit(f"{out_atr}: {dname} already present in the image")
        data = open(path, "rb").read()
        ent = dos.add_file(dname, data, above=Dos2.HIGH if high else 0)
        print(f"{out_atr}: {dname} <- {path} ({len(data)} bytes, {ent.count} "
              f"sectors, start sector {ent.start}, flag ${ent.flag:02X})")
    print(f"{out_atr}: {img!r}, {dos.free_count()} sectors free")
    # Written only once everything is in: a disk without the program on it
    # would look up to date to make and boot to a prompt that cannot find it.
    img.save(out_atr)
    return out_atr


def main(argv):
    args, extra, flags, remove = [], [], set(), []
    i = 0
    while i < len(argv):
        if argv[i] == "--add":
            extra.append((argv[i + 1], argv[i + 2]))
            i += 3
        elif argv[i] == "--remove":
            remove.append(argv[i + 1])
            i += 2
        elif argv[i] in ("--enhanced", "--high", "--sweep", "--compact"):
            flags.add(argv[i])
            i += 1
        else:
            args.append(argv[i])
            i += 1
    if len(args) < 3:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    build(*args[:4], extra=extra, enhanced="--enhanced" in flags, high="--high" in flags,
          remove=remove, sweep="--sweep" in flags, compact="--compact" in flags)


if __name__ == "__main__":
    main(sys.argv[1:])
