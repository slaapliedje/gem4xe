#!/usr/bin/env python3
"""G4DOS writes: its write side driven through CIO, and the disk it leaves
read back by a reader that is not G4DOS.

    make test-fdosw

The disk is made here, with tools/atr.py, and holds G4DOS (src/fdos.s) on
its boot sectors and, as GEM.COM, tests/emu/fdwtest.s -- a plain 6502
program G4DOS's loader runs in GEM's place.  It does, through CIO:

  NEW.DAT    created: 1,000 bytes in one PUT CHARACTERS (the burst) and a
             record a byte at a time (PUT RECORD)
  BIG.DAT    39,000 bytes in three PUTs: two map pages and more
  OLD.TXT    there already, emptied and written again
  REN.TXT    renamed RENAMED.TXT (XIO 32)
  KEEP.DAT   deleted (XIO 33) -- out of SUB, where the flat view finds it
  A.X        made, then a second file to write refused ($A1), a wildcard
             refused ($A5), and A.X deleted
  and reads NEW.DAT and BIG.DAT back, comparing BIG.DAT itself.

Each call's status is in memory when it is done, and is checked; then the
emulator's working copy of the disk is read with tools/atr.py -- every
file's bytes, the names that should and should not be there -- and
atr.Sdfs.check() holds the bitmap to every chain and the superblock's free
count to the bitmap.  Twice: on 256-byte sectors (what gem4xe's floppies
are) and on 128-byte ones, with five map pages in BIG.DAT.
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr, mkxex, mkfloppy                     # noqa: E402

BUILD = os.path.join(ROOT, "build")
RES = 0x0600


def pattern(i):
    return ((i >> 8) * 13 + 3 + 7 * (i & 0xFF)) & 0xFF


PAT = bytes(pattern(i) for i in range(16384))
OLD = b"old " * 500
REN = b"rename me\x9b"
KEEP = bytes(range(256)) * 10

# (what, the status it should be) in the program's order, from RES+1
STEPS = [
    ("OPEN NEW.DAT to write", 1), ("PUT 1,000 bytes", 1), ("PUT RECORD", 1),
    ("CLOSE NEW.DAT", 1),
    ("OPEN BIG.DAT to write", 1), ("PUT 13,000", 1), ("PUT 13,000", 1),
    ("PUT 13,000", 1), ("CLOSE BIG.DAT", 1),
    ("OPEN OLD.TXT, which is there", 1), ("PUT 300", 1), ("CLOSE OLD.TXT", 1),
    ("RENAME REN.TXT,RENAMED.TXT", 1), ("DELETE KEEP.DAT, in SUB", 1),
    ("OPEN A.X to write", 1), ("a second file to write: $A1", 0xA1),
    ("CLOSE A.X", 1), ("a wildcard to write: $A5", 0xA5), ("DELETE A.X", 1),
    ("OPEN NEW.DAT to read", 1), ("GET its 1,006 bytes", 1),
    ("GET past its end: $88", 0x88), ("CLOSE NEW.DAT", 1),
    ("OPEN BIG.DAT to read", 1),
    ("GET 13,000", 1), ("...mismatches against the pattern", 0),
    ("GET 13,000", 1), ("...mismatches", 0),
    ("GET 13,000", 1), ("...mismatches", 0),
    ("CLOSE BIG.DAT", 1),
]

problems = []


def check(ok, what):
    print(f"    {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def program():
    segs, syms = mkxex.read_elf(os.path.join(BUILD, "fdwtest.elf"))
    xex = b"\xff\xff"
    for addr, data in segs:
        xex += mkxex.seg(addr, data)
    return xex + mkxex.seg(mkxex.RUNAD, struct.pack("<H", syms["t_start"]))


def make_disk(path, secsize, sectors):
    img = atr.ATRImage(secsize, sectors)
    fs = atr.Sdfs.format(img, "G4TEST")
    fs.mkdir("SUB")
    fs.add_file("GEM.COM", program())
    fs.add_file("OLD.TXT", OLD)
    fs.add_file("REN.TXT", REN)
    fs.add_file("SUB>KEEP.DAT", KEEP)
    b1, b23, dos = mkfloppy.fdos_parts(ROOT)
    fs.boot_gem4xe(b1, b23, dos)
    img.save(path)


def run(label, secsize, sectors):
    print(f"  {label}: {sectors} sectors of {secsize}")
    work = tempfile.mkdtemp(prefix="fdosw-")
    disk = os.path.join(work, "fdosw.atr")
    make_disk(disk, secsize, sectors)
    tag = f"fdosw{secsize}"
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for(tag), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag=tag, memsize="1088K", extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        f = 0
        while f < 6000 and b.peek(RES) != ord("D"):
            b.frames(50)
            f += 50
        done = b.peek(RES) == ord("D")
        got = bytes(b.memdump(RES + 1, len(STEPS)))
        check(done, f"the program finished by frame {f}")
        for (what, want), st in zip(STEPS, got):
            check(st == want, f"{what}: {st:#04x}" + ("" if st == want else f", not {want:#04x}"))
    finally:
        emu.stop()

    if not check(os.path.exists(written), f"the emulator wrote its working copy ({written})"):
        return
    fs = atr.Sdfs(atr.ATRImage.load(written))
    names = set(fs.list(""))
    check(fs.read("NEW.DAT") == PAT[:1000] + b"HELLO\x9b", "NEW.DAT holds the 1,000 bytes and the record")
    check(fs.read("BIG.DAT") == PAT[:13000] * 3, "BIG.DAT holds the pattern three times, 39,000 bytes")
    check(fs.read("OLD.TXT") == PAT[500:800], "OLD.TXT holds the 300 bytes it was written with, nothing of before")
    check("REN.TXT" not in names and "RENAMED.TXT" in names
          and fs.read("RENAMED.TXT") == REN, "REN.TXT is RENAMED.TXT, its bytes the same")
    check("KEEP.DAT" not in fs.list("SUB"), "KEEP.DAT is gone from SUB")
    check("A.X" not in names, "A.X is gone")
    check("GEM.COM" in names and "G4DOS.SYS" in names, "GEM.COM and G4DOS.SYS are still there")
    bad = fs.check()
    check(not bad, "the bitmap, the chains and the free count agree"
          + ("" if not bad else ": " + "; ".join(bad[:6])))
    shutil.rmtree(work, ignore_errors=True)


def main():
    print("gem4xe-fdosw: G4DOS writes, read back by tools/atr.py")
    run("256-byte sectors", 256, 1440)
    run("128-byte sectors", 128, 2560)
    print(f"\ngem4xe-fdosw: {'PASS' if not problems else 'FAIL'} -- G4DOS writes, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
