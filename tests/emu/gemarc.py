#!/usr/bin/env python3
"""GemARC on the Atari: a real archive opened, taken out, and a new one
made -- each result checked by The Unarchiver, not by GemARC.

build/gemarc-test.atr is SpartaDOS 3.2 on a 1 MB image with GemARC as
the desktop, so the shell runs it straight after the boot, and TEST.ARC
on it: [gemarc].archive, made by somebody else's ARC.  Driven by its
keyboard shortcuts, as a person could:

  1. ^O, TEST.ARC: the window lists every member (read off the screen).
  2. ^A, ^E, OK: every member taken out into the root.  The files on the
     image afterwards must be byte for byte what `unar` takes out of the
     same archive on the host.
  3. ^N, NEW.ARC: a new archive.  ^I, *.TXT: the text files just taken
     out put in.  `lsar -t` must pass NEW.ARC, and `unar` must take out
     of it exactly the files that went in.
  4. ^Q.

    python3 tests/emu/gemarc.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from a8test.launcher import launch, config_dir_for   # noqa: E402
import symfile                                # noqa: E402
import atr                                    # noqa: E402
from sdx816 import find_text                  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "gemarc-test.atr")
SHOTS = os.path.join(BUILD, "shots", "gemarc")
KEYNAME = {".": "PERIOD", "*": "ASTERISK"}

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def unar_files(archive):
    """name -> bytes, as The Unarchiver takes them out."""
    out = tempfile.mkdtemp(prefix="gemarc-unar-")
    try:
        subprocess.run(["unar", "-q", "-f", "-D", "-o", out, archive], check=True)
        return {f.upper(): open(os.path.join(out, f), "rb").read()
                for f in os.listdir(out)}
    finally:
        shutil.rmtree(out)


def main():
    print("gemarc: GemARC on the Atari")
    os.makedirs(SHOTS, exist_ok=True)
    work = tempfile.mkdtemp(prefix="gemarc-")
    disk = os.path.join(work, "gemarc.atr")
    shutil.copy(DISK, disk)
    src = atr.Sdfs(atr.ATRImage.load(disk))
    test_arc = os.path.join(work, "TEST.ARC")
    open(test_arc, "wb").write(src.read("TEST.ARC"))
    want = unar_files(test_arc)
    gsym = symfile.load(os.path.join(BUILD, "gem.sym"))

    # The emulator writes to a working copy of the image, kept by its hash
    # in the run's config directory (tests/emu/m19_files.py fresh_disk);
    # a stale one from an earlier run is dropped first.
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("gemarc"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="gemarc", memsize="1088K", extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge

    def settle(most=3000):
        n, still, f = b.peek16(gsym["app_calls"]), 0, 0
        while f < most and still < 4:
            b.frames(30)
            f += 30
            now = b.peek16(gsym["app_calls"])
            still = still + 1 if now == n else 0
            n = now

    def shot(name):
        p = os.path.join(SHOTS, name + ".png")
        b.screenshot(p)
        return p

    def ctrl(k, wait=120):
        b.key(k, ctrl=True)
        b.frames(wait)
        settle()

    def type_in(text):
        for ch in text:
            b.key(KEYNAME.get(ch, ch))
            b.frames(6)

    def enter(wait=300):
        b.key("RETURN")
        b.frames(wait)
        settle()

    try:
        f = 0
        while f < 20000 and b.peek16(gsym["sh_runs"]) < 1:
            b.frames(100)
            f += 100
        check(b.peek16(gsym["sh_runs"]) >= 1, "the shell ran GemARC")
        b.frames(300)
        settle()
        p = shot("01-up")
        check(find_text(p, "GemARC") is not None, f"GemARC's window is up ({p})")

        ctrl("O")
        type_in("TEST.ARC")
        enter(600)
        p = shot("02-open")
        seen = [n for n in want if find_text(p, n) is not None]
        check(len(seen) == len(want), f"the list shows {len(seen)} of the "
              f"{len(want)} members: {sorted(set(want) - set(seen))} missing ({p})")

        ctrl("A")
        ctrl("E")
        shot("03-folder")
        enter(1500)                         # OK: the folder the archive is in
        settle(20000)
        p = shot("04-taken-out")
        check(find_text(p, f"{len(want)} files taken out.") is not None,
              f"the alert says {len(want)} files taken out ({p})")
        enter()

        ctrl("N")
        type_in("NEW.ARC")
        enter(600)
        ctrl("I")
        type_in("*.TXT")
        shot("05-add")
        enter(1500)
        settle(20000)
        p = shot("06-put-in")
        txt = sorted(n for n in want if n.endswith(".TXT"))
        check(find_text(p, f"{len(txt)} files put in.") is not None,
              f"the alert says {len(txt)} files put in ({p})")
        enter()
        p = shot("07-new")
        seen = [n for n in txt if find_text(p, n) is not None]
        check(seen == txt, f"NEW.ARC's list shows {seen}, expected {txt} ({p})")
        ctrl("Q", 300)
    finally:
        emu.stop()

    if not os.path.exists(written):
        check(False, f"the emulator wrote no working copy at {written}")
        return 1
    fs = atr.Sdfs(atr.ATRImage.load(written))
    on_disk = {e.filename.upper(): e for e in fs.entries("")}
    for name, data in sorted(want.items()):
        got = fs.read(name) if name in on_disk else None
        check(got == data, f"{name}: taken out "
              + ("byte for byte as unar has it" if got == data else
                 "missing" if got is None else f"{len(got)} bytes, unar {len(data)}"))
    if "NEW.ARC" not in on_disk:
        check(False, "NEW.ARC is not on the disk")
    else:
        new = os.path.join(work, "NEW.ARC")
        open(new, "wb").write(fs.read("NEW.ARC"))
        t = subprocess.run(["lsar", "-t", new], capture_output=True, text=True)
        check(t.returncode == 0 and f"{len(txt)} passed, 0 failed" in t.stdout,
              f"lsar -t passes NEW.ARC: {t.stdout.strip().splitlines()[-1:]}")
        got = unar_files(new)
        check(got == {n: want[n] for n in txt},
              f"unar takes out of NEW.ARC exactly the {len(txt)} files put in")
    shutil.rmtree(work)
    print(f"gemarc: {'FAIL' if problems else 'PASS'} -- GemARC lists, takes out "
          f"and makes archives The Unarchiver agrees with, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
