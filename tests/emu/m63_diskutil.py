#!/usr/bin/env python3
"""Phase 157 gate: DISKUTIL, driven as a person drives it (docs/disk-plan.md,
step 3).

build/diskutil-test.atr is an appliance floppy -- G4DOS starting DISKUTIL
in the desktop's place (tools/mkfloppy.py --app) -- and four more disks:

  D2  a hard disk partition's shape, 4,096 sectors of 512.  DISKUTIL opens
      on it (the first drive that is not its own), says it is not a floppy
      and offers no density: the Format button does nothing.
  D3  a double-density SDFS disk with a file on it.  Formatted at double
      density as G4DOS, labelled TESTDISK.
  D4  a blank double-sided disk.  Formatted at single density as DOS 2.
  D5  an enhanced-density disk.  D3 copied onto it: another shape, so
      formatted to D3's first, then every sector written.

The dialog is read off the screen and its buttons found from where its
labels are: a row's buttons start six columns after its label, three
apart.  Each alert's own button is the one below its message.  What the
disks hold afterwards is read off the emulator's working copies with
tools/atr.py: TESTDISK an empty SDFS that checks, D4 DOS 2.0S with 707
free, D5 the same as D3 sector for sector.

    python3 tests/emu/m63_diskutil.py
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
from shots import Tour, boot, poke16, PTR_NONE, SYMS  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "diskutil-test.atr")
OUT = os.path.join(BUILD, "shots", "diskutil")
TAG = "m63"
CELL = 8                    # a character, in the screenshot's pixels
problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def find_all(shot, text):
    """Every place `text` stands, top to bottom: each hit painted out and
    the search run again."""
    from PIL import Image
    from vbxeref import SHOT_X0, SHOT_Y0
    im = Image.open(shot).convert("RGB")
    hits, tmp = [], shot + ".all.png"
    while len(hits) < 12:
        im.save(tmp)
        at = find_text(tmp, text)
        if at is None:
            break
        hits.append(at)
        for y in range(SHOT_Y0 + at[1], SHOT_Y0 + at[1] + CELL):
            for x in range(SHOT_X0 + at[0], SHOT_X0 + at[0] + CELL * len(text)):
                im.putpixel((x, y), (255, 255, 255))
    os.remove(tmp)
    return hits


def make_disks(work):
    paths = {}
    d1 = os.path.join(work, "d1.atr")
    shutil.copy(DISK, d1)
    paths[1] = d1
    img = atr.ATRImage(512, 4096)
    paths[2] = os.path.join(work, "d2.atr")
    img.save(paths[2])
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "OLD")
    fs.add_file("OLD.TXT", b"the disk before\x9b")
    paths[3] = os.path.join(work, "d3.atr")
    img.save(paths[3])
    paths[4] = os.path.join(work, "d4.atr")
    atr.ATRImage(256, 1440).save(paths[4])
    paths[5] = os.path.join(work, "d5.atr")
    atr.ATRImage(128, 1040).save(paths[5])
    return paths


def main():
    print("gem4xe-m63: DISKUTIL formats and copies disks")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m63-")
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
    n_shot = [0]

    def shot(name):
        n_shot[0] += 1
        p = os.path.join(OUT, f"{n_shot[0]:02d}-{name}.png")
        b.screenshot(p)
        return p

    def wait_for(text, name, most=12000, step=100):
        f = 0
        while f < most:
            b.frames(step)
            f += step
            p = os.path.join(OUT, f"wait-{name}.png")
            b.screenshot(p)
            if find_text(p, text) is not None:
                os.replace(p, os.path.join(OUT, f"{n_shot[0] + 1:02d}-{name}.png"))
                n_shot[0] += 1
                return os.path.join(OUT, f"{n_shot[0]:02d}-{name}.png")
        return None

    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        p = wait_for("Format and copy disks", "dialog")
        if not check(p is not None, "DISKUTIL's dialog came up in the desktop's place"):
            return 1
        lbl = {w: find_text(p, w) for w in ("From", "To", "Density", "Files", "Exit")}
        if not check(all(lbl.values()), f"the dialog's labels: {lbl}"):
            return 1
        x0 = lbl["To"][0]                       # the labels' column

        def drive(row, n):
            """The middle of drive n's button on the From or To row."""
            return (x0 + (6 + 3 * (n - 1)) * CELL + CELL, lbl[row][1] + 4)

        def button_on(row_label, text, after=0):
            """The button reading `text` on the row of `row_label`, the
            first from the left past column `after`."""
            q = shot("find")
            y = lbl[row_label][1] + (CELL if row_label == "Density" else 0)
            hits = [h for h in find_all(q, text) if abs(h[1] - y) <= 4 and h[0] > after]
            return (hits[0][0] + 4, hits[0][1] + 4) if hits else None

        def alert_ok(message, button):
            """The alert saying `message`: its `button`, the one below it."""
            q = shot("alert")
            m = find_text(q, message)
            if not check(m is not None, f"the alert '{message}' ({q})"):
                return False
            below = [h for h in find_all(q, button) if 0 < h[1] - m[1] < 6 * CELL]
            if not check(below, f"the alert's {button} button ({q})"):
                return False
            t.click((below[0][0] + 4, below[0][1] + 4))
            return True

        def status_after(text, name, most=20000):
            return wait_for(text, name, most=most, step=200)

        # -- D2: a partition's shape, the default -----------------------------
        check(find_text(p, "not a floppy") is not None,
              f"opened on D2:, a partition's shape: 'is not a floppy drive' ({p})")

        # -- D3: double density, G4DOS, labelled ------------------------------
        t.click(drive("To", 3))
        q = shot("d3")
        check(find_text(q, "D3: 720 sectors of 256") is not None, f"D3: chosen and asked ({q})")
        for _ in range(8):              # a key a dozen frames apart: at four
            b.key("BACKSPACE")          # one S of TESTDISK was dropped
            b.frames(12)
        for ch in "TESTDISK":
            b.key(ch, shift=True)
            b.frames(12)
        go = find_all(shot("go"), "Format")
        go = [h for h in go if h[1] > lbl["Exit"][1] - 4]
        if check(go, "the Format button beside Exit"):
            t.click((go[0][0] + 4, go[0][1] + 4))
            if alert_ok("erased", "Format"):
                check(status_after("formatted" , "d3-done") is not None,
                      "D3: formatted, the status line says so")
        q = shot("d3-status")
        check(find_text(q, "D3: formatted, 182784 bytes free") is not None,
              f"...with 714 sectors of 256 free: 182784 bytes ({q})")

        # -- D4: single density, DOS 2 ----------------------------------------
        t.click(drive("To", 4))
        single = button_on("Density", "Single")
        dos2 = button_on("Files", "DOS 2")
        if check(single and dos2, f"the Single and DOS 2 buttons ({single}, {dos2})"):
            t.click(single)
            t.click(dos2)
            t.click((go[0][0] + 4, go[0][1] + 4))
            if alert_ok("erased", "Format"):
                status_after("formatted", "d4-done")
        q = shot("d4-status")
        check(find_text(q, "D4: formatted, 88375 bytes free") is not None,
              f"D4: DOS 2 on single density: 707 sectors of 125 bytes free ({q})")

        # -- copy D3 to D5 -----------------------------------------------------
        q = shot("mode")
        hits = [h for h in find_all(q, "Copy") if h[1] < lbl["From"][1]]
        if check(hits, f"the Copy button ({q})"):
            t.click((hits[0][0] + 4, hits[0][1] + 4))
            t.click(drive("From", 3))
            t.click(drive("To", 5))
            q = shot("copy")
            gc = [h for h in find_all(q, "Copy") if h[1] > lbl["Exit"][1] - 4]
            if check(gc, f"the action button reads Copy ({q})"):
                t.click((gc[0][0] + 4, gc[0][1] + 4))
                if alert_ok("replaced", "Copy"):
                    check(status_after("Copied", "copied", most=40000) is not None,
                          "D3: copied to D5:, the status line says so")
        q = shot("copy-status")
        check(find_text(q, "Copied, 720 sectors of 256") is not None, f"Copied, 720 of 256 ({q})")

        # -- Exit ---------------------------------------------------------------
        e = lbl["Exit"]
        t.click((e[0] + 8, e[1] + 4))
        b.frames(200)
    finally:
        emu.stop()

    # -- what the disks hold --------------------------------------------------
    def image(d):
        p = state[d]
        return atr.ATRImage.load(p) if os.path.exists(p) else None

    d3, d4, d5, d2 = image(3), image(4), image(5), image(2)
    if check(d3 is not None, "D3: has a working copy"):
        fs = atr.Sdfs(d3)
        sb = d3.read_sector(1)
        check(sb[22:30] == b"TESTDISK", f"D3:'s volume is {sb[22:30]!r}")
        check(not fs.check(), f"D3:'s SDFS: {fs.check()[:3]}")
        check([e.filename for e in fs.entries("")] == [], "D3: is empty, OLD.TXT gone")
        check(fs.free_count() == 714, f"D3: {fs.free_count()} free, 714 expected")
        print(f"  D3: an SDFS called TESTDISK, empty, {fs.free_count()} free, checks clean")
    if check(d4 is not None, "D4: has a working copy"):
        check((d4.sector_size, d4.sector_count) == (128, 720),
              f"D4: is {d4.sector_count} of {d4.sector_size}, not single density")
        fs = atr.Dos2(d4)
        check(fs.free_count() == 707 and not fs.mydos, f"D4: DOS 2, {fs.free_count()} free")
        print(f"  D4: DOS 2.0S on single density, {fs.free_count()} free")
    if check(d5 is not None and d3 is not None, "D5: has a working copy"):
        same = (d5.sector_size, d5.sector_count) == (256, 720) and all(
            d5.read_sector(s) == d3.read_sector(s) for s in range(1, 721))
        check(same, "D5: is not D3: sector for sector")
        print(f"  D5: formatted from enhanced to double density, and D3: sector for "
              f"sector: {'yes' if same else 'NO'}")
    check(d2 is None or d2.data == atr.ATRImage(512, 4096).data, "D2:, a partition, was written")
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m63: {'PASS' if not problems else 'FAIL'} -- DISKUTIL formats and "
          f"copies disks, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
