#!/usr/bin/env python3
"""Phase 155 gate: the drive itself -- Dgeom, Dformat and Drwsec.

docs/disk-plan.md, step 1.  The runner on G4DOS (build/m15g-boot.atr) in
D1:, scratch disks in D2: and D3:, and the calls made through the runner's
sys op as test-m15 makes GEMDOS's.  The emulator's drives are switched
between three kinds while the machine runs (the bridge's CONFIG diskemu):

  generic  takes a PERCOM block, so every density, each read back by Dgeom
  810      takes none: single density, refusing enhanced and double
  1050     takes none: single and enhanced, refusing double

Then the edges -- drive 0 and 9, an empty drive, a hard disk's shape (one
track of thousands of 512-byte sectors) which must never be formatted, a
sector past the end, a density that does not exist -- and sectors written
and read back across the 128-byte boot sectors of a 256-byte disk.

And first, G4DOS's folders forgetting a disk formatted under them: D2:
starts as an SDFS disk with a file on it, listed through GEMDOS, so the
engine has its sectors; it is formatted, a new SDFS is laid on it through
Drwsec (tools/atr.py's, sector by sector), and GEMDOS must list it empty
and write a file onto it -- which the image says it did, afterwards.

    python3 tests/emu/m62_drive.py
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import symfile, atr                         # noqa: E402
from m7_form import STATUS, SYMS            # noqa: E402
from m12_file import Runner                 # noqa: E402
import m15_gdos as m15                      # noqa: E402
from m15_gdos import Gdos, W, L, BUF, BUF_ROOM, FA_SUBDIR, HANDLE_BASE  # noqa: E402

# src/sys/gemdos.h
m15.FN.update(Dgeom=0x1F8, Dformat=0x1F9, Drwsec=0x1FA)
DG_FLOPPY, DG_PERCOM, DG_WPROT = 0x01, 0x02, 0x04
DF_ASIS, DF_SD, DF_ED, DF_DD, DF_DSDD = 0, 1, 2, 3, 4
EDRVNR, EUNCMD, EBADRQ, ESECNF, EUNDEV, EDRIVE = -2, -3, -5, -8, -15, -46
ALL = (1 << DF_SD) | (1 << DF_ED) | (1 << DF_DD) | (1 << DF_DSDD)
GEOM = {DF_SD: (128, 720), DF_ED: (128, 1040), DF_DD: (256, 720), DF_DSDD: (256, 1440)}
NAME = {DF_SD: "single", DF_ED: "enhanced", DF_DD: "double", DF_DSDD: "double-sided"}

G4DISK = os.path.abspath(os.path.join(ROOT, "build", "m15g-boot.atr"))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test.txt")
TAG = "m62"


def boot(b):
    """G4DOS from a cold reset, the runner loaded and switched to the
    65C816, as test-m15 --g4dos boots it."""
    b.ok("COLD_RESET")
    b.frames(2)
    b.poke(0xD1FF, 0x01)
    b.poke(0xD191, 0x00)
    for _ in range(0, 8000, 50):
        b.frames(50)
        s = bytes(b.memdump(STATUS, 14))
        if s[:2] == b"VD" and s[2] == 1:
            return s
    return None


class Drive:
    """The three calls, and Dgeom's twenty bytes taken apart."""

    def __init__(self, g, r, check):
        self.g, self.r, self.check = g, r, check

    def geom(self, drv):
        ret, _ = self.g.call("Dgeom", W(drv), L(self.r.sc + BUF))
        if ret < 0:
            return ret, None
        raw = self.r.read(BUF, 20)
        secsize, sectors, flags, formats = struct.unpack("<HHHH", raw[:8])
        return ret, dict(secsize=secsize, sectors=sectors, flags=flags,
                         formats=formats, percom=raw[8:20])

    def format(self, drv, dens):
        ret, _ = self.g.call("Dformat", W(drv), W(dens), L(self.r.sc + BUF))
        return ret, self.g.frames

    def rwsec(self, drv, rw, sector, count, secsize):
        ret, _ = self.g.call("Drwsec", W(drv), W(rw), W(sector), W(count),
                             W(secsize), L(self.r.sc + BUF))
        return ret

    def formats_to(self, what, drv, dens):
        """Dformat at `dens`, then Dgeom: the geometry it was meant to make."""
        ret, _ = self.format(drv, dens)
        self.check(ret == 0, f"{what}: Dformat {NAME[dens]} answered {ret}")
        if ret != 0:
            return
        bad = self.r.read(BUF, 2)
        self.check(bad == b"\xff\xff", f"{what}: the bad list starts {bad.hex()}, not $FFFF")
        ret, d = self.geom(drv)
        want = GEOM[dens]
        got = (d["secsize"], d["sectors"]) if d else ret
        self.check(got == want, f"{what}: {NAME[dens]} made {got}, wanted {want}")
        print(f"  {what}: {NAME[dens]} density, {want[1]} sectors of {want[0]}")


def refuses(check, what, ret, want):
    check(ret == want, f"{what}: answered {ret}, wanted {want}")


def lay(drv, r, d, img, check):
    """The image's sectors that are not zeros, written through Drwsec four
    at a time: a fresh format is all zeros, so that is the whole of it."""
    ss = img.sector_size
    last = max(n for n in range(1, img.sector_count + 1) if any(img.read_sector(n)))
    per = BUF_ROOM // ss
    for first in range(1, last + 1, per):
        n = min(per, last + 1 - first)
        blob = b"".join(img.read_sector(k).ljust(ss, b"\0") for k in range(first, first + n))
        r.stage(BUF, blob)
        ret = d.rwsec(drv, 1, first, n, ss)
        check(ret == 0, f"Drwsec writing sectors {first}-{first + n - 1}: {ret}")
    return last


def forgets(g, r, d, check):
    """D2: a file left open on it across a format.  A path is checked
    again at every open -- the engine reads the disk's first sector, and
    forgets a disk that is not the one it had -- but a handle already open
    is not: its next write and its close go where the OLD disk had room,
    which is the new disk's root and bitmap.  Dformat makes the engine
    forget the disk, the handle with it."""
    g.call("Fsetdta", L(r.sc + m15.DTA))
    got, _ = g.listing("B:\\*.*", FA_SUBDIR)
    check("OLD.TXT" in got, f"D2: before: {sorted(got)}, no OLD.TXT")
    data = open(FIXTURE, "rb").read()
    h, _ = g.call("Fcreate", L(g.string("B:\\OPEN.TXT")), W(0))
    check(h >= HANDLE_BASE, f"Fcreate B:\\OPEN.TXT before the format: {h}")
    r.stage(BUF, data)
    g.call("Fwrite", W(h), L(len(data)), L(r.sc + BUF))
    ret, _ = d.format(2, DF_DD)
    check(ret == 0, f"Dformat D2: with a file open on it: {ret}")
    img = atr.ATRImage(256, 720)
    atr.Sdfs.format(img, "NEWDISK")
    last = lay(2, r, d, img, check)
    r.stage(BUF, data)
    stale_w, _ = g.call("Fwrite", W(h), L(len(data)), L(r.sc + BUF))
    stale_c, _ = g.call("Fclose", W(h))
    check(stale_w < 0, f"Fwrite to a handle opened on the disk before it was formatted: "
                       f"{stale_w}, not an error")
    got, _ = g.listing("B:\\*.*", FA_SUBDIR)
    check(got == {}, f"D2: a new SDFS laid by Drwsec lists {sorted(got)}, not nothing"
                     + (": the old handle wrote to the new disk" if "OPEN.TXT" in got else ""))
    h, _ = g.call("Fcreate", L(g.string("B:\\NEW.TXT")), W(0))
    check(h >= HANDLE_BASE, f"Fcreate B:\\NEW.TXT on the new disk: {h}")
    if h >= HANDLE_BASE:
        r.stage(BUF, data)
        n, _ = g.call("Fwrite", W(h), L(len(data)), L(r.sc + BUF))
        check(n == len(data), f"Fwrite to the new disk: {n}")
        g.call("Fclose", W(h))
    h, _ = g.call("Fopen", L(g.string("B:\\NEW.TXT")), W(0))
    n, _ = g.call("Fread", W(h), L(BUF_ROOM), L(r.sc + BUF))
    check(n == len(data) and r.read(BUF, n) == data,
          f"B:\\NEW.TXT read back {n} bytes, the fixture is {len(data)}")
    g.call("Fclose", W(h))
    print(f"  D2: formatted with a file open on it, {last} sectors of a new SDFS laid "
          f"by Drwsec; the old handle refused (Fwrite {stale_w}, Fclose {stale_c}), the disk listed "
          f"empty, NEW.TXT written and read back")


def sectors(r, d, check):
    """A 256-byte disk: sectors 1-3 are 128 bytes in 256-byte places."""
    pat = bytes((i * 13 + 5) & 0xFF for i in range(4 * 256))
    r.stage(BUF, pat)
    check(d.rwsec(2, 1, 1, 4, 256) == 0, "Drwsec writing sectors 1-4")
    r.stage(BUF, bytes(4 * 256))
    check(d.rwsec(2, 0, 1, 4, 256) == 0, "Drwsec reading sectors 1-4")
    back = r.read(BUF, 4 * 256)
    for k in range(3):
        place = back[k * 256:(k + 1) * 256]
        check(place[:128] == pat[k * 256:k * 256 + 128] and place[128:] == bytes(128),
              f"sector {k + 1}: not its 128 bytes and an untouched half")
    check(back[768:] == pat[768:], "sector 4: not the 256 bytes written")
    r.stage(BUF, pat[:256])
    check(d.rwsec(2, 1, 720, 1, 256) == 0, "Drwsec writing the last sector, 720")
    refuses(check, "Drwsec reading sector 721 of 720", d.rwsec(2, 0, 721, 1, 256), ESECNF)
    refuses(check, "Drwsec at sector 0", d.rwsec(2, 0, 0, 1, 256), EBADRQ)
    refuses(check, "Drwsec with 300-byte sectors", d.rwsec(2, 0, 1, 1, 300), EBADRQ)
    check(d.rwsec(2, 0, 5, 0, 256) == 0, "Drwsec of no sectors")
    print("  Drwsec: sectors 1-4 written and read back, the boot sectors' halves kept, "
          "the last sector written, the edges refused")


def main():
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    work = tempfile.mkdtemp(prefix="m62-")
    d1 = os.path.join(work, "d1.atr")
    shutil.copy(G4DISK, d1)
    d2 = os.path.join(work, "d2.atr")
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "OLDDISK")
    fs.add_file("OLD.TXT", b"the disk before\x9b")
    img.save(d2)
    d3 = os.path.join(work, "d3.atr")
    atr.ATRImage(512, 4096).save(d3)            # a partition's shape
    d3_before = open(d3, "rb").read()
    states = {}
    for p in (d1, d2, d3):
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
        states[p] = os.path.join(config_dir_for(TAG), "disk_state", sha)
        shutil.rmtree(states[p], ignore_errors=True)

    emu = launch(tag=TAG, memsize="1088K",
                 extra_args=["--bootrw", "--disk", d1, "--disk", d2, "--disk", d3])
    b = emu.bridge
    try:
        if boot(b) is None:
            print("FAIL: the runner did not come up")
            return 1
        r = Runner(b, syms)
        g = Gdos(r, check)
        d = Drive(g, r, check)

        print("generic (a drive that takes a geometry):")
        b.ok("CONFIG diskemu generic")
        ret, geo = d.geom(2)
        check(ret == 0 and geo, f"Dgeom D2: {ret}")
        if geo:
            check((geo["secsize"], geo["sectors"]) == (256, 720),
                  f"Dgeom D2: {geo['sectors']} sectors of {geo['secsize']}, the image is 720 of 256")
            check(geo["flags"] == DG_FLOPPY | DG_PERCOM, f"Dgeom D2: flags {geo['flags']:#x}")
            check(geo["formats"] == ALL, f"Dgeom D2: formats {geo['formats']:#x}, wanted {ALL:#x}")
            check(geo["percom"][6:8] == b"\x01\x00", f"Dgeom D2: PERCOM {geo['percom'].hex()}")
            print(f"  Dgeom D2: 720 of 256, a floppy that takes a geometry, PERCOM "
                  f"{geo['percom'].hex()}")
        forgets(g, r, d, check)
        for dens in (DF_SD, DF_ED, DF_DSDD, DF_DD):
            d.formats_to("generic", 2, dens)
        sectors(r, d, check)

        print("the edges:")
        refuses(check, "Dgeom of drive 0", d.geom(0)[0], EDRIVE)
        refuses(check, "Dgeom of drive 9", d.geom(9)[0], EDRIVE)
        refuses(check, "Dformat of drive 0", d.format(0, DF_SD)[0], EDRIVE)
        refuses(check, "Dgeom of the empty D4:", d.geom(4)[0], EDRVNR)
        refuses(check, "Dformat at density 7", d.format(2, 7)[0], EBADRQ)
        ret, geo = d.geom(3)
        check(ret == 0 and geo and not geo["flags"] & DG_FLOPPY,
              f"Dgeom D3:, a partition's shape: {ret}, {geo}")
        if geo:
            print(f"  D3: {geo['sectors']} sectors of {geo['secsize']}, PERCOM "
                  f"{geo['percom'].hex()}: not a floppy")
        refuses(check, "Dformat of D3:, a partition's shape", d.format(3, DF_DD)[0], EUNDEV)
        print("  drive 0 and 9, the empty D4:, density 7 and D3: refused")

        print("810 (no geometry):")
        b.ok("CONFIG diskemu 810")
        ret, geo = d.geom(2)
        check(ret == 0 and geo and geo["flags"] == DG_FLOPPY
              and geo["formats"] == (1 << DF_SD) | (1 << DF_ED),
              f"Dgeom D2: on an 810: {ret}, {geo}")
        d.formats_to("810", 2, DF_SD)
        refuses(check, "an 810 asked for enhanced density", d.format(2, DF_ED)[0], EUNCMD)
        refuses(check, "an 810 asked for double density", d.format(2, DF_DD)[0], EUNCMD)

        print("1050 (no geometry, enhanced density):")
        b.ok("CONFIG diskemu 1050")
        d.formats_to("1050", 2, DF_ED)
        d.formats_to("1050", 2, DF_SD)
        refuses(check, "a 1050 asked for double density", d.format(2, DF_DD)[0], EUNCMD)
        b.ok("CONFIG diskemu generic")
        d.formats_to("generic again", 2, DF_DD)
        lay(2, r, d, atr.Sdfs.format(atr.ATRImage(256, 720), "FINAL").img, check)
    finally:
        emu.stop()

    written = os.path.join(states[d2], "disk.atr")
    if os.path.exists(written):
        out = atr.ATRImage.load(written)
        check((out.sector_size, out.sector_count) == (256, 720),
              f"D2's image ends {out.sector_count} sectors of {out.sector_size}")
        bad = atr.Sdfs(out).check()
        check(not bad, "D2's last SDFS: " + "; ".join(bad[:4]))
        print(f"  D2's image: {out.sector_count} sectors of {out.sector_size}, an SDFS "
              f"{'that checks' if not bad else 'with problems'}")
    else:
        check(False, f"the emulator wrote no working copy of D2: ({written})")
    d3_written = os.path.join(states[d3], "disk.atr")
    check(not os.path.exists(d3_written) or open(d3_written, "rb").read() == d3_before,
          "D3:, a partition's shape, was written to")
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m62: {'PASS' if not fails else 'FAIL'} -- the drive itself, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
