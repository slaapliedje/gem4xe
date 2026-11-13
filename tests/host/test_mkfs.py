#!/usr/bin/env python3
"""DISKUTIL's file systems (src/apps/mkfs.c, docs/disk-plan.md step 2),
built with gcc and held against three witnesses -- because a writer and a
model of it can agree and both be wrong:

  tools/atr.py's own formatters, byte for byte, wherever it has one: SDFS
      on every geometry, DOS 2.0S on single density, DOS 2.5 on enhanced
      (atr.enhance), MyDOS on 720 sectors of 256;
  a disk real MyDOS 4.50 formatted, double-sided: its VTOC's code and
      count, and which sectors it keeps for itself;
  this file's own reading of Altirra's InitNew, for the MyDOS volumes
      atr.py cannot write -- the VTOC growing down from 360.

And the order: the sector that makes a disk a disk -- SDFS's sector 1, DOS
2's VTOC -- comes last, so a format cut short is not taken for one.  And
the refusals: a bad sector, a geometry with no such file system.

    python3 tests/host/test_mkfs.py      (needs build/mkfs_host)
"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr                                  # noqa: E402
import tomllib                              # noqa: E402

HOST = os.path.join(ROOT, "build", "mkfs_host")
MKFS_EGEOM, MKFS_EBAD = -64, -65
STAMP = 0xA500          # atr.py's blank superblock: serial 0, random $A5
problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def run(kind, ss, n, label="TEST", stamp=STAMP, bad=None):
    """The engine's writes, in order, laid on a blank image: (image, the
    sectors in the order written, its answer)."""
    args = [HOST, kind, str(ss), str(n), label, hex(stamp)] + ([str(bad)] if bad else [])
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    img = atr.ATRImage(ss, n)
    order, ret = [], None
    for ln in out.splitlines():
        if ln.startswith("S "):
            _, sec, length, data = ln.split(" ")
            sec, length = int(sec), int(length)
            check(length == img.sector_len(sec),
                  f"{kind} {n}x{ss}: sector {sec} written {length} bytes, it has {img.sector_len(sec)}")
            img.write_sector(sec, bytes.fromhex(data))
            order.append(sec)
        elif ln.startswith("R "):
            ret = int(ln[2:])
    return img, order, ret


def differ(a, b, skip=()):
    """The sectors where two images differ, but those in `skip`."""
    return [s for s in range(1, a.sector_count + 1)
            if s not in skip and a.read_sector(s) != b.read_sector(s)]


# ---- SDFS --------------------------------------------------------------------

def sdfs():
    print("SDFS against atr.py's Sdfs.format:")
    for ss, n in ((128, 720), (128, 1040), (256, 720), (256, 1440), (512, 2048),
                  (256, 16384), (128, 65535)):
        img, order, ret = run("sdfs", ss, n)
        ref = atr.ATRImage(ss, n)
        atr.Sdfs.format(ref, "TEST")
        d = differ(img, ref)
        check(not d, f"SDFS {n}x{ss}: sectors {d[:6]} differ from atr.py's")
        same = "the same bytes" if not d else f"{len(d)} sector(s) DIFFERENT"
        fs = atr.Sdfs(img)
        bad = fs.check()
        check(not bad, f"SDFS {n}x{ss}: {bad[:3]}")
        check(ret == fs.free_count(), f"SDFS {n}x{ss}: answered {ret}, {fs.free_count()} free")
        check(order and order[-1] == 1, f"SDFS {n}x{ss}: sector 1 written at {order.index(1) + 1} "
                                        f"of {len(order)}, not last")
        print(f"  {n} x {ss}: {same}, {len(order)} sectors written, {ret} free, "
              f"sector 1 last")
    img, _, _ = run("sdfs", 256, 720, label="my disk.atr", stamp=0x1234)
    sb = img.read_sector(1)
    check(sb[22:30] == b"MYDISK  ", f"the label 'my disk.atr' is {sb[22:30]!r}")
    check(sb[38:40] == b"\x34\x12", f"the stamp is {sb[38:40].hex()}, not 3412")
    img, _, _ = run("sdfs", 256, 720, label="")
    check(img.read_sector(1)[22:30] == b"NEWDISK ", "no label is not NEWDISK")
    print("  the label as Altirra makes it, NEWDISK for none, the stamp in 38-39")


# ---- DOS 2 -------------------------------------------------------------------

BOOT = bytes([0x00, 0x01, 0x00, 0x07, 0x07, 0x07, 0x38, 0x60]).ljust(128, b"\0")


def dos2_against_atr():
    print("DOS 2 against atr.py's Dos2.format and enhance:")
    cases = (("DOS 2.0S", 128, 720, lambda r: atr.Dos2.format(r)),
             ("MyDOS", 256, 720, lambda r: atr.Dos2.format(r, mydos=True)),
             ("DOS 2.5", 128, 1040, None))
    for name, ss, n, make in cases:
        img, order, ret = run("dos2", ss, n)
        if make:
            ref = atr.ATRImage(ss, n)
            make(ref)
        else:
            sd = atr.ATRImage(128, 720)
            atr.Dos2.format(sd)
            ref = atr.enhance(sd)
        d = differ(img, ref, skip=(1, 2, 3))
        check(not d, f"{name} {n}x{ss}: sectors {d[:6]} differ from atr.py's")
        check(img.read_sector(1) == BOOT and img.read_sector(2) == bytes(128),
              f"{name}: the boot sectors are not the BOOT ERROR stub")
        fs = atr.Dos2(img)
        check(ret == fs.free_count(), f"{name}: answered {ret}, {fs.free_count()} free")
        check(order[-1] == 360, f"{name}: the VTOC written at {order.index(360) + 1} of "
                                f"{len(order)}, not last")
        what = (f"the same VTOC{' and VTOC2' if n == 1040 else ''} and directory" if not d
                else f"{len(d)} sector(s) DIFFERENT")
        print(f"  {name}, {n} x {ss}: {what}, {ret} free, the VTOC last")


def vtoc_model(ss, n):
    """Altirra's InitNew, read again here (diskfsdos2.cpp): how many VTOC
    sectors a MyDOS volume has, its code, the sectors kept."""
    count, code = 1, 2
    if ss == 128 and n > 943:
        count = ((n + 1 + 80 + 2047) >> 11) << 1
        code = (count >> 1) + 2
    elif ss == 256 and n >= 1024:
        count = (n + 1 + 80 + 2047) >> 11
        code = count + 2
    kept = {0, 1, 2, 3} | set(range(361, 369)) | set(range(361 - count, 361))
    return count, code, kept


def dos2_mydos():
    print("MyDOS volumes atr.py cannot write:")
    fixture = tomllib.load(open(os.path.join(ROOT, "fixtures.toml"), "rb"))["dos"].get("mydos")
    for ss, n in ((256, 1440), (128, 943), (128, 944), (128, 2000), (256, 4000), (128, 8192)):
        img, order, ret = run("dos2", ss, n)
        count, code, kept = vtoc_model(ss, n)
        raw = b"".join(img.read_sector(360 - i) for i in range(count))
        bits = raw[10:]
        free = {s for s in range(n + 1) if bits[s >> 3] & (0x80 >> (s & 7))}
        want = set(range(1, n + 1)) - kept
        check(raw[0] == code, f"MyDOS {n}x{ss}: VTOC code {raw[0]}, wanted {code}")
        check(free == want, f"MyDOS {n}x{ss}: {len(free ^ want)} sectors' bits wrong, "
                            f"e.g. {sorted(free ^ want)[:6]}")
        total = raw[1] | (raw[2] << 8)
        count_free = raw[3] | (raw[4] << 8)
        check(total == n - count - 11 == count_free == ret,
              f"MyDOS {n}x{ss}: VTOC says {total} to use, {count_free} free, answered {ret}; "
              f"wanted {n - count - 11}")
        check(not any(bits[(n + 1 + 7) >> 3:]), f"MyDOS {n}x{ss}: bits set past the disk")
        check(order[-1] == 361 - count, f"MyDOS {n}x{ss}: the VTOC's first sector not last")
        print(f"  {n} x {ss}: code {code}, {count} VTOC sector(s) from {361 - count}, "
              f"{ret} free")
    if fixture and os.path.exists(fixture):
        real = atr.ATRImage.load(fixture)
        img, _, _ = run("dos2", 256, 1440)
        v, w = real.read_sector(360), img.read_sector(360)
        check(v[0] == w[0] and v[1:3] == w[1:3],
              f"against MyDOS 4.50's own 1440 x 256 disk: code {v[0]}/{w[0]}, "
              f"to use {v[1] | v[2] << 8}/{w[1] | w[2] << 8}")
        kept_real = {s for s in range(1441) if not v[10 + (s >> 3)] & (0x80 >> (s & 7))}
        _, _, kept = vtoc_model(256, 1440)
        check(kept <= kept_real, f"MyDOS 4.50's disk keeps {sorted(kept - kept_real)} free "
                                 "that this keeps")
        print(f"  MyDOS 4.50's own double-sided disk: code {v[0]}, {v[1] | v[2] << 8} to use, "
              f"and every sector kept here kept there too")
    else:
        print("  (no MyDOS fixture: [dos].mydos in fixtures.toml)")


def refusals():
    print("refused:")
    for kind, ss, n, bad, want, what in (
            ("sdfs", 256, 720, 400, MKFS_EBAD, "an SDFS on a disk with a bad sector"),
            ("dos2", 128, 720, 5, MKFS_EBAD, "a DOS 2 on a disk with a bad sector"),
            ("dos2", 512, 2048, None, MKFS_EGEOM, "DOS 2 on 512-byte sectors"),
            ("dos2", 128, 700, None, MKFS_EGEOM, "DOS 2 on 700 sectors"),
            ("sdfs", 128, 5, None, MKFS_EGEOM, "SDFS on 5 sectors"),
            ("sdfs", 300, 720, None, MKFS_EGEOM, "SDFS on 300-byte sectors")):
        args = [HOST, kind, str(ss), str(n), "TEST", "0"] + ([str(bad)] if bad else [])
        out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
        writes = [ln for ln in out.splitlines() if ln.startswith("S ")]
        ret = int(out.split("R ")[-1])
        check(ret == want and not writes, f"{what}: answered {ret} after {len(writes)} "
                                          f"sector(s), wanted {want} and none")
    print("  bad sectors, 512-byte DOS 2, short disks and odd sizes refused before a write")


def main():
    if not os.path.exists(HOST):
        print(f"no {HOST}: make build/mkfs_host")
        return 1
    sdfs()
    dos2_against_atr()
    dos2_mydos()
    refusals()
    print(f"\ntest_mkfs: {'PASS' if not problems else 'FAIL'} -- {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
