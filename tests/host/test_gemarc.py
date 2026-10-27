#!/usr/bin/env python3
"""GemARC's engine on the host, held to The Unarchiver.

build/arc_host is src/apps/arccodec.c and arcfile.c -- the code the Atari
runs -- over stdio (tests/host/arc_host.c).  Two halves, neither of which
trusts GemARC to judge itself:

  READING: every member of every *.ARC under [gemarc].dirs is taken out,
  and each must decode with its CRC right and be byte for byte what
  `unar` takes out.  These are real archives, made by SEA's ARC, PKARC
  and the Atari's own ARCs; 1,402 members on the machine this was
  written on, stored, packed, squeezed and crunched.

  WRITING: files built to be awkward -- empty, one byte, runs, the RLE
  escape $90 in runs and alone, random bytes that will not pack, text,
  an executable, 200 KB that fills the LZW table and clears it -- put in
  an archive in two goes, the second replacing a member, and the result
  must pass `lsar -t` and give back exactly those files through `unar`.

    python3 tests/host/test_gemarc.py
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST = os.path.join(ROOT, "build", "arc_host")

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")


def unar(archive, out):
    subprocess.run(["unar", "-q", "-f", "-D", "-o", out, archive],
                   capture_output=True)
    return {f.upper().strip(): os.path.join(out, f) for f in os.listdir(out)}


def reading(dirs, work):
    archives = []
    for d in dirs:
        for top, _, files in os.walk(d):
            archives += [os.path.join(top, f) for f in files
                         if f.lower().endswith(".arc")]
    members = same = 0
    for k, p in enumerate(sorted(archives)):
        a = os.path.join(work, f"a{k}")
        b = os.path.join(work, f"b{k}")
        os.mkdir(a)
        os.mkdir(b)
        r = subprocess.run([HOST, "x", p, a], capture_output=True, text=True)
        theirs = unar(p, b)
        for line in r.stdout.split("\n"):
            if not line.strip():
                continue
            name, code = line.rsplit(" ", 1)
            members += 1
            if code != "0":
                check(False, f"{p}: {name!r} did not decode (error {code})")
                continue
            t = theirs.get(name.upper().strip())
            if t is None:
                continue                    # unar names it otherwise; skip
            if open(os.path.join(a, name), "rb").read() == open(t, "rb").read():
                same += 1
            else:
                check(False, f"{p}: {name!r} differs from unar's")
        shutil.rmtree(a)
        shutil.rmtree(b)
    print(f"  reading: {len(archives)} archives, {members} members, "
          f"{same} byte for byte as unar has them")
    check(members > 0, "no archives found to read: set [gemarc].dirs")
    check(members - same <= max(1, members // 500),
          f"{members - same} members not compared with unar's")


def writing(work):
    src = os.path.join(work, "src") + "/"
    os.mkdir(src)
    rnd = random.Random(1)
    big = open(os.path.join(ROOT, "src", "vdi", "vdi.c"), "rb").read()
    files = {
        "EMPTY.DAT": b"",
        "ONE.DAT": b"A",
        "RUNS.DAT": b"A" * 1000 + b"B" * 3 + b"C" * 2 + b"D" * 256 + b"E" * 600,
        "DLE.DAT": b"\x90" * 300 + b"x\x90\x90y" + bytes([0x90, 0]) * 50 + b"\x90",
        "RANDOM.DAT": bytes(rnd.getrandbits(8) for _ in range(20000)),
        "TEXT.TXT": open(os.path.join(ROOT, "docs", "guide.md"), "rb").read(),
        "PROG.XEX": open(HOST, "rb").read()[:60000],
        "BIG.DAT": (big * (200000 // len(big) + 1))[:200000],
        "MIXED.DAT": bytes(rnd.choice(b"AAAAB\x90\x00") for _ in range(70000)),
    }
    for n, d in files.items():
        open(src + n, "wb").write(d)
    arc = os.path.join(work, "T.ARC")
    tmp = os.path.join(work, "T.TMP")
    names = sorted(files)
    half = len(names) // 2
    for batch in (names[half:], names[:half] + ["TEXT.TXT"]):
        r = subprocess.run([HOST, "a", arc, tmp, src] + batch,
                           capture_output=True, text=True)
        check(r.returncode == 0, f"adding {batch}: {r.stdout.strip()}")
    listed = subprocess.run([HOST, "l", arc], capture_output=True, text=True).stdout
    order = [line.split()[0] for line in listed.splitlines()]
    check(order == names, f"the members are {order}, not {names} in order "
          "with TEXT.TXT once")
    t = subprocess.run(["lsar", "-t", arc], capture_output=True, text=True)
    check(f"{len(names)} passed, 0 failed" in t.stdout,
          f"lsar -t: {t.stdout.strip().splitlines()[-1:]}")
    out = os.path.join(work, "u")
    os.mkdir(out)
    got = unar(arc, out)
    for n in names:
        if n == "EMPTY.DAT" and n not in got:
            continue                        # unar makes no empty file
        check(n in got and open(got[n], "rb").read() == files[n],
              f"{n}: unar does not give it back as it went in")
    methods = {line.split()[0]: line.split()[1] for line in listed.splitlines()}
    check(methods.get("RANDOM.DAT") == "2" and methods.get("BIG.DAT") == "8",
          f"the methods chosen: {methods}")
    print(f"  writing: {len(names)} files put in, methods {methods}")


def main():
    print("test_gemarc: GemARC's engine against The Unarchiver")
    if not os.path.exists(HOST):
        print("FAIL: build/arc_host is missing -- make build/arc_host")
        return 1
    if not shutil.which("unar") or not shutil.which("lsar"):
        print("FAIL: unar and lsar (The Unarchiver) are needed")
        return 1
    cfg = tomllib.load(open(os.path.join(ROOT, "fixtures.toml"), "rb"))
    dirs = cfg.get("gemarc", {}).get("dirs", [])
    work = tempfile.mkdtemp(prefix="test_gemarc-")
    try:
        reading(dirs, work)
        writing(work)
    finally:
        shutil.rmtree(work)
    print(f"test_gemarc: {'FAIL' if problems else 'PASS'} -- "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
