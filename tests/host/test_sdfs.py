#!/usr/bin/env python3
"""GEMDOS's SDFS engine on the host: src/sys/sdfs.c, the code the Atari
runs, through tests/host/sdfs_host.c, against ATR images that tools/atr.py
makes and then reads back -- so the engine never judges itself.

Three kinds of check:

  READING: gem4xe's own disks, made by tools/atr.py, walked folder by
  folder -- every listing and every file's bytes as atr.py has them.

  BY HAND: each change -- files made, written over, written into and past
  their end, folders made and removed, renames in a folder and between
  folders, a locked file, the names SpartaDOS refuses -- with what must
  come out written down here, then the image read with atr.py and
  Sdfs.check()ed: every chain used once and marked used, every other
  sector free, the free count the bitmap's.

  AT RANDOM: rounds of random changes against a model in Python, each
  round a fresh process (so the cache starts cold, as after a reboot),
  then the whole tree compared with the model and checked.

All of it on 256-byte sectors and on 128.

    python3 tests/host/test_sdfs.py
"""
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr  # noqa: E402

HOST = os.path.join(ROOT, "build", "sdfs_host")
BUILD = os.path.join(ROOT, "build")

EACCDN, EFILNF, EPTHNF, ERANGE = -36, -33, -34, -64

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


class Disk:
    """An image in a temporary directory, and the engine run on it."""

    def __init__(self, secsize=256, sectors=None, src=None):
        self.dir = tempfile.mkdtemp(prefix="sdfs-")
        self.path = os.path.join(self.dir, "disk.atr")
        self.n = 0
        if src:
            with open(src, "rb") as f:
                data = f.read()
            with open(self.path, "wb") as f:
                f.write(data)
        else:
            sectors = sectors or (1440 if secsize == 256 else 2560)
            img = atr.ATRImage(secsize, sectors)
            atr.Sdfs.format(img, "SDFSTEST")
            img.save(self.path)

    def file(self, data):
        self.n += 1
        p = os.path.join(self.dir, f"f{self.n}")
        with open(p, "wb") as f:
            f.write(data)
        return p

    def run(self, lines):
        """The commands, one process: the answers, a list of lists of
        lines (an `ls` has more than one)."""
        r = subprocess.run([HOST, self.path], input="\n".join(lines) + "\n",
                           capture_output=True, text=True)
        if r.returncode:
            check(False, f"sdfs_host stopped with {r.returncode}: {r.stderr.strip()}")
        out, got, it = r.stdout.splitlines(), [], 0
        while it < len(out):
            head = out[it].split()
            it += 1
            block = [out[it - 1]]
            if lines and len(got) < len(lines) and lines[len(got)].startswith("ls ") \
                    and head[0] == "ok":
                for _ in range(int(head[1])):
                    block.append(out[it])
                    it += 1
            got.append(block)
        return got

    def fs(self):
        return atr.Sdfs(atr.ATRImage.load(self.path))

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()


def code(answer):
    """0 for ok, else the error number."""
    w = answer[0].split()
    return 0 if w[0] == "ok" else int(w[1])


def apath(p):
    return p.strip("\\").replace("\\", "/")


# ---- reading ----------------------------------------------------------------

def card_partitions():
    """The card image's APT partitions (tools/mkcf.py), 512-byte SDFS
    volumes, each written out as a 512-byte ATR the harness reads: what a
    hard disk holds, where the floppies are 128 and 256."""
    path = os.path.join(BUILD, "gem-cf.img")
    if not os.path.exists(path):
        return []
    import apt
    img = apt.Image.load(path)
    out, tmp = [], tempfile.mkdtemp(prefix="sdfs-cf-")
    for i, part in enumerate(apt.read_table(img), 1):
        a = atr.ATRImage(512, part.sector_count)
        for n in range(1, part.sector_count + 1):
            a.write_sector(n, part.read_sector(n))
        f = os.path.join(tmp, f"part{i}.atr")
        a.save(f)
        out.append((f"gem-cf.img D{i}:", f))
    return out


def walk_atr(fs, path=""):
    out = {}
    for e in fs.entries(path):
        full = (path + "/" if path else "") + e.filename
        out[full] = e
        if e.is_dir:
            out.update(walk_atr(fs, full))
    return out


def reading():
    print("reading: gem4xe's disks, as tools/atr.py has them")
    disks = [p for p in ("gem-sdx.atr", "gem-apps.atr", "gem-shots.atr",
                         "m14-boot.atr", "gem-qed.atr")
             if os.path.exists(os.path.join(BUILD, p))]
    check(len(disks) >= 2, f"disks to read: {disks}")
    srcs = [(n, os.path.join(BUILD, n)) for n in disks]
    srcs += card_partitions()
    for name, src in srcs:
        d = Disk(src=src)
        fs = d.fs()
        tree = walk_atr(fs)
        dirs = [""] + [p for p, e in tree.items() if e.is_dir]
        files = [p for p, e in tree.items() if not e.is_dir]
        cmds, outs = [], {}
        for p in dirs:
            cmds.append("ls \\" + p.replace("/", "\\"))
        for p in files:
            outs[p] = os.path.join(d.dir, "o" + str(len(outs)))
            cmds.append(f"get \\{p.replace('/', chr(92))} {outs[p]}")
        got = d.run(cmds)
        bad = 0
        for p, a in zip(dirs, got[:len(dirs)]):
            want = sorted((e.filename, e.status, e.size) for e in fs.entries(p))
            have = sorted((ln.split()[0], int(ln.split()[1]), int(ln.split()[2]))
                          for ln in a[1:])
            if not check(code(a) == 0 and have == want,
                         f"{name}: \\{p} lists {have[:3]}..., atr.py {want[:3]}..."):
                bad += 1
        for p, a in zip(files, got[len(dirs):]):
            if not check(code(a) == 0 and d.read(outs[p]) == fs.read(p),
                         f"{name}: \\{p} reads back as atr.py has it ({a[0]})"):
                bad += 1
        print(f"  {name}: {len(dirs)} folders, {len(files)} files"
              f"{'' if not bad else f', {bad} wrong'}")


# ---- by hand ----------------------------------------------------------------

def pattern(n, seed):
    r = random.Random(seed)
    return bytes(r.randrange(256) for _ in range(n))


def by_hand(secsize):
    print(f"by hand: {secsize}-byte sectors")
    d = Disk(secsize)
    free0 = d.fs().free_count()
    a, b, big = pattern(700, 1), pattern(300, 2), pattern(40000, 3)
    got = d.run([
        "mkdir \\GEM",                                  # 0
        "mkdir \\GEM\\SUB",                             # 1
        f"put \\GEM\\SUB\\A.TXT {d.file(a)}",           # 2
        f"put \\B.DAT {d.file(b)}",                     # 3
        f"put \\GEM\\BIG.DAT {d.file(big)} 777",        # 4: map pages
        "mkdir \\GEM",                                  # 5: there already
        f"put \\NOPE\\X.TXT {d.file(b)}",               # 6: no such folder
        f"put \\BAD-NAME.TXT {d.file(b)}",              # 7: a name it refuses
        f"put \\TOOLONGNAME.TXT {d.file(b)}",           # 8
        "rmdir \\GEM",                                  # 9: not empty
        "ren \\B.DAT \\B2.DAT",                         # 10: in a folder
        "ren \\B2.DAT \\GEM\\SUB\\B3.DAT",              # 11: between folders
        "ren \\GEM\\SUB\\A.TXT \\GEM\\SUB\\B3.DAT",     # 12: taken
        "attr \\GEM\\SUB\\B3.DAT 1",                    # 13: locked
        "del \\GEM\\SUB\\B3.DAT",                       # 14: refused
        "attr \\GEM\\SUB\\B3.DAT 0",                    # 15
        f"pwrite \\GEM\\SUB\\A.TXT 100 {d.file(b'Y' * 50)}",    # 16: into it
        f"pwrite \\GEM\\SUB\\A.TXT 690 {d.file(b'Z' * 500)}",   # 17: past its end
        f"pwrite \\GEM\\SUB\\A.TXT 5000 {d.file(b'Q')}",        # 18: a seek too far
        "stat \\GEM\\SUB",                              # 19
        "stat \\NOPE",                                  # 20
        "ren \\GEM\\SUB \\MOVED",                       # 21: a folder moved up
        "rmdir \\GEM\\SUB",                             # 22: gone
        f"put \\GEM\\BIG.DAT {d.file(b)}",              # 23: emptied, shorter
        "space",                                        # 24
    ])
    want = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: EACCDN, 6: EPTHNF, 7: EFILNF,
            8: EFILNF, 9: EACCDN, 10: 0, 11: 0, 12: EACCDN, 13: 0, 14: EACCDN,
            15: 0, 16: 0, 17: 0, 18: ERANGE, 19: 0, 20: EFILNF, 21: 0,
            22: EPTHNF, 23: 0, 24: 0}
    for i, w in want.items():
        check(code(got[i]) == w, f"{secsize}: step {i}: {got[i][0]}, want {w}")
    fs = d.fs()
    a2 = bytearray(a)
    a2[100:150] = b"Y" * 50
    a2 = bytes(a2[:690]) + b"Z" * 500
    tree = walk_atr(fs)
    check(set(tree) == {"GEM", "GEM/BIG.DAT", "MOVED", "MOVED/A.TXT", "MOVED/B3.DAT"},
          f"{secsize}: the tree is {sorted(tree)}")
    check(fs.read("MOVED/A.TXT") == a2, f"{secsize}: A.TXT written into and past its end")
    check(fs.read("MOVED/B3.DAT") == b, f"{secsize}: B3.DAT moved twice, its bytes the same")
    check(fs.read("GEM/BIG.DAT") == b, f"{secsize}: BIG.DAT emptied and written shorter")
    check(fs.find("MOVED").map and fs._read_dir(fs.find("MOVED").map)[0].map == fs.root_map,
          f"{secsize}: the moved folder's header names the root as its parent")
    free_said = got[24][0].split()
    check(code(got[24]) == 0 and int(free_said[1]) == fs.free_count(),
          f"{secsize}: Dfree's {free_said[1:]} is the bitmap's {fs.free_count()}")
    bad = fs.check()
    check(not bad, f"{secsize}: consistent: {bad[:4]}")
    # and the big file before it was emptied: written in one round, read in another
    d2 = Disk(secsize)
    d2.run([f"put \\BIG.DAT {d2.file(big)} 300"])
    out = os.path.join(d2.dir, "back")
    g = d2.run([f"get \\BIG.DAT {out}"])
    check(code(g[0]) == 0 and d2.read(out) == big and d2.fs().read("BIG.DAT") == big,
          f"{secsize}: 40,000 bytes over {40000 // (secsize - 4) // ((secsize - 4) // 2) + 1} "
          f"map pages, read back by both")
    check(not d2.fs().check(), f"{secsize}: consistent after the big file")
    check(free0 - d2.fs().free_count() == -(-40000 // secsize) + -(-(-(-40000 // secsize)) // ((secsize - 4) // 2)),
          f"{secsize}: the big file took its data and its map pages, no more")

    # a disk filled: as much as fits is written, the length says so, and
    # what was written is there; then a delete makes the room again
    d3 = Disk(secsize, 200)
    huge = pattern(200 * secsize, 4)
    g = d3.run([f"put \\FULL.DAT {d3.file(huge)} 1000", "space",
                "del \\FULL.DAT", "space"])
    w = g[0][0].split()
    n = int(w[2]) if w[0] == "err" else -1
    check(w[0] == "err" and int(w[1]) == EACCDN and 0 < n < len(huge),
          f"{secsize}: a disk filled says so, after {n} bytes ({g[0][0]})")
    fs3 = d3.fs()
    check(code(g[2]) == 0, f"{secsize}: and the file is deleted ({g[2][0]})")
    check(int(g[1][0].split()[1]) == 0 or int(g[1][0].split()[1]) < 3,
          f"{secsize}: no room left when it stopped: {g[1][0]}")
    check(not fs3.check(), f"{secsize}: consistent after the disk filled and was emptied: "
                           f"{fs3.check()[:3]}")
    d4 = Disk(secsize, 200)
    g = d4.run([f"put \\FULL.DAT {d4.file(huge)} 1000"])
    n = int(g[0][0].split()[2]) if g[0][0].startswith("err") else -1
    fs4 = d4.fs()
    check(n > 0 and fs4.read("FULL.DAT") == huge[:n] and not fs4.check(),
          f"{secsize}: the {n} bytes a full disk took are the file, and consistent: "
          f"{fs4.check()[:3]}")


# ---- at random --------------------------------------------------------------

def at_random(secsize, seed, rounds=6, ops=120):
    print(f"at random: {secsize}-byte sectors, seed {seed}")
    rnd = random.Random(seed)
    d = Disk(secsize)
    cap = d.fs().free_count() * secsize
    files, dirs = {}, {""}              # model: path -> bytes; folders
    names = ["A", "B", "C", "DATA", "X_1", "LONGNAME"]
    exts = ["", "TXT", "DAT", "B"]

    def name():
        n = rnd.choice(names)
        e = rnd.choice(exts)
        return n + ("." + e if e else "")

    def anydir():
        return rnd.choice(sorted(dirs))

    def join(p, n):
        return (p + "\\" if p else "") + n

    for rnd_i in range(rounds):
        cmds, expect = [], []
        for _ in range(ops):
            op = rnd.choice("pppppddmmrrxw")
            if op == "p":
                p = join(anydir(), name())
                if p in dirs:
                    continue
                size = rnd.choice([0, 1, rnd.randrange(1, 600), rnd.randrange(600, 5000),
                                   rnd.randrange(secsize * 60, secsize * 140)])
                # the model knows nothing of a full disk: stay under half
                used = sum(len(v) for k, v in files.items() if k != p)
                if used + size > cap // 2:
                    size = rnd.randrange(0, 300)
                data = bytes(rnd.randrange(256) for _ in range(size))
                cmds.append(f"put \\{p} {d.file(data)} {rnd.choice([1, 100, 256, 4096])}")
                expect.append(0)
                files[p] = data
            elif op == "d" and files:
                p = rnd.choice(sorted(files))
                cmds.append(f"del \\{p}")
                expect.append(0)
                del files[p]
            elif op == "m":
                p = join(anydir(), name())
                if p in files:
                    continue
                cmds.append(f"mkdir \\{p}")
                expect.append(EACCDN if p in dirs else 0)
                dirs.add(p)
            elif op == "r":
                empty = [x for x in sorted(dirs) if x and not any(
                    k.startswith(x + "\\") for k in list(files) + list(dirs))]
                full = [x for x in sorted(dirs) if x and x not in empty]
                if empty and rnd.random() < 0.7:
                    p = rnd.choice(empty)
                    cmds.append(f"rmdir \\{p}")
                    expect.append(0)
                    dirs.discard(p)
                elif full:
                    cmds.append(f"rmdir \\{rnd.choice(full)}")
                    expect.append(EACCDN)
            elif op == "x" and files:
                p = rnd.choice(sorted(files))
                q = join(anydir(), name())
                if q in files or q in dirs:
                    cmds.append(f"ren \\{p} \\{q}")
                    expect.append(EACCDN if q != p else EACCDN)
                    continue
                cmds.append(f"ren \\{p} \\{q}")
                expect.append(0)
                files[q] = files.pop(p)
            elif op == "w" and files:
                p = rnd.choice(sorted(files))
                old = files[p]
                if sum(len(v) for v in files.values()) + 900 > cap // 2:
                    continue
                at = rnd.randrange(0, len(old) + 1)
                data = bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 900)))
                cmds.append(f"pwrite \\{p} {at} {d.file(data)}")
                expect.append(0)
                files[p] = old[:at] + data + old[at + len(data):]
        got = d.run(cmds)
        for c, w, g in zip(cmds, expect, got):
            check(code(g) == w, f"{secsize}/{seed} round {rnd_i}: {c.split()[0]} "
                                f"{c.split()[1]}: {g[0]}, want {w}")
        fs = d.fs()
        tree = walk_atr(fs)
        want_tree = {p.replace("\\", "/") for p in files} | {p.replace("\\", "/") for p in dirs if p}
        check(set(tree) == want_tree,
              f"{secsize}/{seed} round {rnd_i}: tree differs: extra "
              f"{sorted(set(tree) - want_tree)[:4]}, missing {sorted(want_tree - set(tree))[:4]}")
        wrong = [p for p, data in files.items()
                 if p.replace("\\", "/") in tree and fs.read(p.replace("\\", "/")) != data]
        check(not wrong, f"{secsize}/{seed} round {rnd_i}: contents differ: {wrong[:4]}")
        bad = fs.check()
        check(not bad, f"{secsize}/{seed} round {rnd_i}: inconsistent: {bad[:4]}")
    print(f"  {len(files)} files and {len(dirs) - 1} folders at the end")


def main():
    if not os.path.exists(HOST):
        print(f"no {HOST}: make build/sdfs_host")
        return 1
    reading()
    for sz in (256, 128, 512):
        by_hand(sz)
    for sz in (256, 128, 512):
        for seed in (1, 2, 3):
            at_random(sz, seed)
    print(f"\ntest_sdfs: {'PASS' if not problems else 'FAIL'} -- "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
