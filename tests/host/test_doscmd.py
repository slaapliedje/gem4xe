#!/usr/bin/env python3
"""The DOS's commands on the host: src/sys/doscmd.c, the code the Atari
runs -- in G4DOS's shell and in gem4xe's File -> DOS command -- through
tests/host/doscmd_host.c, against ATR images that tools/atr.py makes and
then reads back, so the commands never judge themselves.

One session over three drives, a disk of each sector size: D1: 256-byte,
D2: 128, D3: 512 (a hard disk partition's).  What each line must print
is written out below from what the commands are for (docs/g4dos-plan.md,
step 4) -- the listings, the paths, the messages -- and afterwards every
image is read with atr.py: Sdfs.check() (every chain used once and
marked, the free count the bitmap's), and each file the session copied
or moved compared byte for byte with what it was made from.

    python3 tests/host/test_doscmd.py
"""
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr  # noqa: E402

HOST = os.path.join(ROOT, "build", "doscmd_host")

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


README = b"Hello\r\nWorld\r\n"            # an ST's line ends
LINES = b"".join(b"line %02d\x9b" % i for i in range(1, 31))   # the Atari's
BIG = bytes(random.Random(4).randrange(256) for _ in range(40000))
HELLO = b"\xff\xff\x00\x30\x00\x30\x60"


def disks(d):
    """D1: 256-byte, D2: 128, D3: 512, made by atr.py."""
    paths = []
    for name, secsize, sectors in (("SYS", 256, 720), ("DATA", 128, 1040),
                                   ("BIG", 512, 1024)):
        img = atr.ATRImage(secsize, sectors)
        atr.Sdfs.format(img, name)
        paths.append(os.path.join(d, f"{name.lower()}.atr"))
        img.save(paths[-1])
    s = atr.Sdfs(atr.ATRImage.load(paths[0]))
    s.add_file("README.TXT", README)
    s.mkdir("BIN")
    s.add_file("BIN>HELLO.COM", HELLO)
    s.mkdir("DOCS")
    s.add_file("DOCS>A.TXT", b"aaa\x9b")
    s.add_file("DOCS>B.TXT", b"bbbb\x9b")
    s.add_file("DOCS>C.DOC", b"cc\x9b")
    s.add_file("DOCS>LINES.TXT", LINES)
    s.add_file("DOCS>BIG.DAT", BIG)
    s.mkdir("DOCS>OLD")
    s.img.save(paths[0])
    return paths


def run(paths, lines, *opts):
    r = subprocess.run([HOST, *opts, *paths],
                       input=("\n".join(lines) + "\n").encode("latin-1"),
                       capture_output=True)
    check(r.returncode == 0, f"doscmd_host exited {r.returncode}: "
                             f"{r.stderr.decode(errors='replace')}")
    return r.stdout.decode("latin-1")


def answers(out):
    """{line typed: (printed lines, its answer)}, in order, as a list."""
    got, cur = [], None
    for ln in out.split("\n"):
        if cur is None and "$ " in ln:
            cur = [ln.split("$ ", 1)[1], []]
        elif cur is not None and ln.startswith("= "):
            got.append((cur[0], cur[1], int(ln[2:])))
            cur = None
        elif cur is not None:
            cur[1].append(ln)
    return got


# Each line, what it prints and its answer.  "*" for a line's printing
# means "not checked here"; the disks are checked afterwards instead.
SESSION = [
    ("pwd", ["D1:/"], 0),
    ("ls", ["README.TXT    BIN/", "DOCS/"], 0),
    ("ls -l", ["README.TXT        14 2026-09-04 12:00",
               "BIN/              23 2026-09-04 12:00",
               "DOCS/             23 2026-09-04 12:00"], 0),
    ("cat README.TXT", ["Hello", "World"], 0),
    ("cd docs", [], 0),
    ("pwd", ["D1:/DOCS"], 0),
    ("ls ?.txt", ["A.TXT         B.TXT"], 0),
    ("ls *.*", ["A.TXT         B.TXT", "C.DOC         LINES.TXT",
                "BIG.DAT       OLD/"], 0),
    ("cd old", [], 0),
    ("pwd", ["D1:/DOCS/OLD"], 0),
    ("cd ../..", [], 0),
    ("pwd", ["D1:/"], 0),
    ("cd >docs\\old", [], 0),
    ("cd", [], 0),
    ("pwd", ["D1:/"], 0),
    # copies: a wildcard to another drive, one file to a 512-byte disk
    ("cp docs/*.txt D2:", [], 0),
    ("cp README.TXT D3:/new.txt", [], 0),
    ("cp docs/big.dat D2:", [], 0),
    ("cp README.TXT readme.txt", ["cp: README.TXT: same file"], -36),
    ("cp docs/a.txt docs/b.txt nowhere", ["cp: nowhere: not a folder"], -34),
    ("cp docs D2:", ["cp: DOCS: is a folder"], -36),
    # folders and moves
    ("D2:", [], 0),
    ("ls", ["A.TXT         B.TXT", "LINES.TXT     BIG.DAT"], 0),
    ("mv a.txt sub/", ["mv: sub/: no such folder"], -34),
    ("mkdir sub", [], 0),
    ("mkdir sub", ["mkdir: sub: exists"], -36),
    ("mv a.txt sub", [], 0),
    ("mv b.txt sub/b2.txt", [], 0),
    ("ls sub", ["A.TXT         B2.TXT"], 0),
    ("mv sub sub/inner", ["mv: SUB: not into itself"], -36),
    ("rmdir sub", ["rmdir: sub: not empty"], -36),
    ("D1:", [], 0),
    ("mv docs/c.doc D3:", [], 0),
    ("ls docs", ["A.TXT         B.TXT", "LINES.TXT     BIG.DAT",
                 "OLD/"], 0),
    ("rm docs/*.txt", [], 0),
    ("rm docs/old", ["rm: OLD: is a folder"], -36),
    ("rmdir docs", ["rmdir: docs: not empty"], -36),
    ("rmdir docs/old", [], 0),
    ("rm docs/big.dat", [], 0),
    ("rmdir docs", [], 0),
    ("rm nothing.txt", ["rm: nothing.txt: no such file"], -33),
    # programs: as typed, then the root and its folders
    ("hello", ["{exec D1:\\BIN\\HELLO.COM}"], 0),
    ("bin/hello", ["{exec D1:\\BIN\\HELLO.COM}"], 0),
    ("D3:hello", ["D3:hello: command not found"], -33),
    ("readme", ["readme: command not found"], -33),
    # errors
    ("cat none", ["cat: none: no such file"], -33),
    ("cd none", ["cd: none: no such folder"], -34),
    ("cd README.TXT", ["cd: README.TXT: not a folder"], -34),
    ("ls D5:", ["ls: D5:: no disk it can read"], -46),
    ("D5:", ["D5:: D5:: no disk it can read"], -46),
    ("pwd", ["D1:/"], 0),
    ("reboot", ["{reboot}"], 0),
    ("DIR D3:", ["NEW.TXT           14 2026-11-02 12:34",
                 "C.DOC              3 2026-09-04 12:00"], 0),
    ("type D3:new.txt", ["Hello", "World"], 0),
    ("ERASE D3:new.txt", [], 0),
]


def session(d):
    paths = disks(d)
    out = run(paths, [ln for ln, _, _ in SESSION])
    got = answers(out)
    if not check(len(got) == len(SESSION),
                 f"{len(got)} answers to {len(SESSION)} lines"):
        print(out)
        return
    for (line, want, wante), (typed, printed, e) in zip(SESSION, got):
        check(typed == line, f"line {line!r} came back as {typed!r}")
        if want != "*":
            check(printed == want, f"{line!r} printed {printed!r}, "
                                   f"not {want!r}")
        check(e == wante, f"{line!r} answered {e}, not {wante}")

    s1, s2, s3 = (atr.Sdfs(atr.ATRImage.load(p)) for p in paths)
    for s, name in ((s1, "D1:"), (s2, "D2:"), (s3, "D3:")):
        bad = s.check()
        check(not bad, f"{name} after the session: {bad}")
    check(s1.list("") == ["README.TXT", "BIN"], f"D1: root {s1.list('')}")
    check(s1.read("BIN>HELLO.COM") == HELLO, "D1:/BIN/HELLO.COM changed")
    check(s2.list("") == ["LINES.TXT", "BIG.DAT", "SUB"],
          f"D2: root {s2.list('')}")
    check(s2.list("SUB") == ["A.TXT", "B2.TXT"], f"D2:/SUB {s2.list('SUB')}")
    check(s2.read("SUB>A.TXT") == b"aaa\x9b", "D2:/SUB/A.TXT")
    check(s2.read("SUB>B2.TXT") == b"bbbb\x9b", "D2:/SUB/B2.TXT")
    check(s2.read("LINES.TXT") == LINES, "D2:/LINES.TXT")
    check(s2.read("BIG.DAT") == BIG,
          "D2:/BIG.DAT, 40,000 bytes onto 128-byte sectors")
    check(s3.list("") == ["C.DOC"], f"D3: root {s3.list('')}")
    check(s3.read("C.DOC") == b"cc\x9b", "D3:/C.DOC, moved from D1:")
    return paths


def df(paths):
    """df's numbers are atr.py's."""
    out = answers(run(paths, ["df D1: D2: D3:"]))
    want = ["Drive Sectors   Free  Bytes free"]
    for n, p in enumerate(paths, 1):
        s = atr.Sdfs(atr.ATRImage.load(p))
        free = s.free_count()
        want.append(f"D{n}:{s.total:10d}{free:7d}{free * s.secsize:12d}")
    check(out and out[0][1] == want, f"df printed {out and out[0][1]}, "
                                     f"not {want}")


def more(paths):
    """more waits a screen at a time, ten rows here, and q stops it."""
    out = answers(run(paths, ["more D2:lines.txt"], "-r", "10",
                      "-k", " q"))
    printed = out[0][1] if out else []
    want = ([f"line {i:02d}" for i in range(1, 10)]
            + ["-- more --{del}" + "line 10"]
            + [f"line {i:02d}" for i in range(11, 19)]
            + ["-- more --{del}"])
    check(printed == want, f"more printed {printed!r}, not {want!r}")


def main():
    if not os.path.exists(HOST):
        print(f"{HOST} is not built (make build/doscmd_host)")
        return 1
    with tempfile.TemporaryDirectory(prefix="doscmd-") as d:
        print("  one session over a 256-, a 128- and a 512-byte disk")
        paths = session(d)
        if paths:
            df(paths)
            more(paths)
    if problems:
        print(f"test_doscmd: FAIL ({len(problems)})")
        return 1
    print(f"  {len(SESSION)} lines, each one's printing and answer as "
          "written; the disks checked")
    print("test_doscmd: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
