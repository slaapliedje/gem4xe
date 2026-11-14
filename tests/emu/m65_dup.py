#!/usr/bin/env python3
"""Phase 160 gate: DUP, DOS 2's disk menu in a GEM window, driven by its
keys (docs/disk-plan.md, part two).

build/dup-test.atr is an appliance floppy -- G4DOS starting DUP in the
desktop's place, SHELL.SYS on it so that H has G4DOS to write -- and four
more disks:

  D2  an SDFS with README.TXT and A.TXT.
  D3  blank, double density: I formats it, H writes DOS to it.
  D4  blank, single density: P formats it.
  D5  blank, double-sided: J duplicates D3 onto it.

What DUP prints is read off the screen after each answer:
  A  D2:'s directory, in DUP's columns, and its free sectors
  C  A.TXT copied to C.TXT, saying COPYING---D2:A.TXT
  E  C.TXT renamed E.TXT;  F  E.TXT locked, A showing its star;
  G  unlocked;  D  deleted, asked DELETE FILE D2:E.TXT? and Y
  I, P  D3 and D4 formatted, each asked TYPE "Y" first
  H  DOS written to D3;  J  D3 duplicated onto D5
  K  NOT UNDER GEM (L and B run things: test-m71)
Then the disks with tools/atr.py: D2 as it began, D3 an SDFS with
G4DOS.SYS and SHELL.SYS that boots alone to G4DOS's prompt, D4 single
density, D5 the same as D3 sector for sector.

    python3 tests/emu/m65_dup.py
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import boot, poke16, PTR_NONE, SYMS  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "dup-test.atr")
OUT = os.path.join(BUILD, "shots", "dup")
TAG = "m65"
KEYS = {":": ("SEMICOLON", True), ",": ("COMMA", False), ".": ("PERIOD", False),
        "*": ("ASTERISK", False), ">": ("GREATER", False), " ": ("SPACE", False)}
problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def make_disks(work):
    paths = {1: os.path.join(work, "d1.atr")}
    shutil.copy(DISK, paths[1])
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "DUPTEST")
    fs.add_file("README.TXT", b"read me\x9b")
    fs.add_file("A.TXT", b"the file A\x9b")
    paths[2] = os.path.join(work, "d2.atr")
    img.save(paths[2])
    for d, (ss, n) in ((3, (256, 720)), (4, (128, 720)), (5, (256, 1440))):
        paths[d] = os.path.join(work, f"d{d}.atr")
        atr.ATRImage(ss, n).save(paths[d])
    return paths


def main():
    print("gem4xe-m65: DUP, DOS 2's disk menu in a GEM window")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m65-")
    disks = make_disks(work)
    state = {}
    for d, p in disks.items():
        sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
        state[d] = os.path.join(config_dir_for(TAG), "disk_state", sha, "disk.atr")
        shutil.rmtree(os.path.dirname(state[d]), ignore_errors=True)
    args = ["--bootrw"]
    for d in sorted(disks):
        args += ["--disk", disks[d]]
    emu = launch(tag=TAG, memsize="1088K", extra_args=args)
    b = emu.bridge
    n = [0]

    def typ(s, wait=12):
        for c in s:
            if c.isalnum():
                b.key(c.upper())
            elif c == "\n":
                b.key("RETURN")
            else:
                k, sh = KEYS[c]
                b.key(k, shift=sh)
            b.frames(wait)

    def wait_for(text, name, most=20000, step=100):
        """Until `text` is on the screen: the picture, or None."""
        f = 0
        while f < most:
            b.frames(step)
            f += step
            p = os.path.join(OUT, f"wait-{name}.png")
            b.screenshot(p)
            if find_text(p, text) is not None:
                n[0] += 1
                q = os.path.join(OUT, f"{n[0]:02d}-{name}.png")
                os.replace(p, q)
                return q
        return None

    def ask(letter, answer, want, name, most=20000):
        """A letter, its answer, and what it must print."""
        typ(letter)
        b.frames(30)
        typ(answer + "\n")
        p = wait_for(want, name, most=most)
        return check(p is not None, f"{letter} {answer!r}: '{want}' never printed "
                                    f"(build/shots/dup/wait-{name}.png)")

    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)  # no pointer over the text
        if not check(wait_for("SELECT ITEM", "menu") is not None,
                     "DUP came up with its menu"):
            return 1
        ask("A", "D2:", "README  TXT 001", "dir")
        p = os.path.join(OUT, f"{n[0]:02d}-dir.png")
        check(find_text(p, "A       TXT 001") is not None, f"A.TXT in the listing ({p})")
        check(find_text(p, "FREE SECTORS") is not None, f"the free sectors under it ({p})")
        print("  A: D2:'s directory in DUP's columns, and its free sectors")
        ask("C", "D2:A.TXT,D2:C.TXT", "COPYING---D2:A.TXT", "copy")
        ask("E", "D2:C.TXT,E.TXT", "SELECT ITEM", "rename")
        ask("F", "D2:E.TXT", "SELECT ITEM", "lock")
        ask("A", "D2:", "*E       TXT 001", "locked")
        print("  C, E, F: copied, renamed and locked -- A shows the star")
        ask("G", "D2:E.TXT", "SELECT ITEM", "unlock")
        ask("A", "D2:", " E       TXT 001", "unlocked")
        typ("D")
        b.frames(30)
        typ("D2:E.TXT\n")
        if check(wait_for("DELETE FILE D2:E.TXT?", "delask") is not None, "D asks for E.TXT"):
            typ("Y")
            wait_for("SELECT ITEM", "deleted")
        print("  G, D: unlocked, then deleted after its question")
        for letter, d in (("I", 3), ("P", 4)):
            ask(letter, str(d), f'TYPE "Y" TO FORMAT DISK {d}', f"fmt{d}-ask")
            typ("Y\n")
            check(wait_for("FREE SECTORS", f"fmt{d}") is not None,
                  f"{letter} {d}: the formatted disk's free sectors")
        print("  I, P: D3: and D4: formatted, each asked first")
        ask("H", "3", 'TYPE "Y" TO WRITE DOS TO DRIVE 3.', "dos-ask")
        typ("Y\n")
        wait_for("SELECT ITEM", "dos")
        ask("J", "3,5", "INSERT BOTH DISKS, TYPE RETURN", "dup-ask")
        typ("\n")
        wait_for("SELECT ITEM", "dup", most=40000)
        typ("K")
        check(wait_for("NOT UNDER GEM", "save") is not None, "K says it is not done under GEM")
        print("  H, J, K: DOS written to D3:, D3: duplicated onto D5:, K refused")
    finally:
        emu.stop()

    def image(d):
        return atr.ATRImage.load(state[d]) if os.path.exists(state[d]) else None

    d2, d3, d4, d5 = image(2), image(3), image(4), image(5)
    if check(d2 is not None, "D2: has a working copy"):
        fs = atr.Sdfs(d2)
        names = sorted(e.filename for e in fs.entries(""))
        check(names == ["A.TXT", "README.TXT"], f"D2: holds {names}: C and E are gone")
        check(not fs.check(), f"D2:'s SDFS: {fs.check()[:3]}")
    if check(d3 is not None, "D3: has a working copy"):
        fs = atr.Sdfs(d3)
        names = sorted(e.filename for e in fs.entries(""))
        check(names == ["G4DOS.SYS", "SHELL.SYS"], f"D3: holds {names}")
        check(not fs.check(), f"D3:'s SDFS: {fs.check()[:3]}")
        print(f"  D3: an SDFS with G4DOS on it, {fs.free_count()} free")
    if check(d4 is not None, "D4: has a working copy"):
        check((d4.sector_size, d4.sector_count) == (128, 720), "D4: is single density")
        check(not atr.Sdfs(d4).check(), "D4:'s SDFS does not check")
    if check(d5 is not None and d3 is not None, "D5: has a working copy"):
        same = (d5.sector_size, d5.sector_count) == (256, 720) and all(
            d5.read_sector(s) == d3.read_sector(s) for s in range(1, 721))
        check(same, "D5: is not D3: sector for sector")
        print(f"  D5: D3: duplicated, sector for sector: {'yes' if same else 'NO'}")

    from fdos_shell import wait_for as wait_screen, fresh, lines
    if d3 is not None:
        alone = os.path.join(work, "boot3.atr")
        shutil.copy(state[3], alone)
        emu = launch(tag="m65boot", memsize="1088K", extra_args=["--disk", alone])
        try:
            emu.bridge.ok("COLD_RESET")
            t = wait_screen(emu.bridge, fresh, 20000)
            check(t >= 0, f"D3: booted alone did not come to G4DOS's prompt: "
                          f"{lines(emu.bridge)[-3:]}")
            if t >= 0:
                print(f"  D3: booted alone: G4DOS's prompt, {t} frames")
        finally:
            emu.stop()
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m65: {'PASS' if not problems else 'FAIL'} -- DUP, DOS 2's disk menu "
          f"in a GEM window, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
