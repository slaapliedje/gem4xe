#!/usr/bin/env python3
"""Phase 158 gate: the desktop formats and copies disks through DISKUTIL
(docs/disk-plan.md, step 4).

The desktop on the G4DOS system floppy, the applications floppy in D2:
with \\APPS\\DISKUTIL.PRG on it.

  1. D2: selected on the desk, File -> Format...: DISKUTIL opens on Format
     with D2: as its destination -- its status line says D2:'s shape.
     Exit, and the desktop is back.
  2. D1: dragged onto D2: on the desk: DISKUTIL opens on Copy, D1: to D2:
     -- the action button reads Copy.  Exit, and the desktop is back.
  3. D2: taken out of its drive, File -> Format... again: no DISKUTIL on
     any disk, and the alert says where it is.

Nothing is formatted or copied: DISKUTIL's own gate (test-m63) does that.
This is about the desktop reaching it with the right tail.

    python3 tests/emu/m64_deskdisk.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS  # noqa: E402
from deskrsc import FILEMENU, FORMITEM        # noqa: E402
from m7_form import F, M, B                   # noqa: E402
from demo_aes import path                     # noqa: E402
from m63_diskutil import find_all, CELL       # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "deskdisk")
problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def main():
    print("gem4xe-m64: the desktop formats and copies disks through DISKUTIL")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m64-")
    d1, d2 = os.path.join(work, "d1.atr"), os.path.join(work, "d2.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), d1)
    shutil.copy(os.path.join(BUILD, "gem-apps.atr"), d2)
    emu = launch(tag="m64", memsize="1088K", extra_args=["--disk", d1, "--disk", d2])
    b = emu.bridge
    n = [0]

    def shot(name):
        n[0] += 1
        p = os.path.join(OUT, f"{n[0]:02d}-{name}.png")
        b.screenshot(p)
        return p

    def wait_for(text, name, most=12000):
        f = 0
        while f < most:
            b.frames(200)
            f += 200
            p = os.path.join(OUT, f"wait-{name}.png")
            b.screenshot(p)
            if find_text(p, text) is not None:
                return p
        return None

    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)

        def back_to_desk(p, name):
            """DISKUTIL's Exit, and the desktop drawn again."""
            e = find_text(p, "Exit")
            if not check(e is not None, f"{name}: DISKUTIL's Exit button ({p})"):
                return False
            t.click((e[0] + 8, e[1] + 4))
            q = wait_for("DISK D1:", f"{name}-desk")
            ok = check(q is not None, f"{name}: the desktop came back after Exit")
            t.settle(3000)
            return ok

        # -- 1. File -> Format... on the selected D2: ---------------------------
        t.click(t.desk_icon("DISK D2:"))
        t.choose(FILEMENU, FORMITEM)
        p = wait_for("Format and copy disks", "format")
        if check(p is not None, "File -> Format... ran DISKUTIL"):
            check(find_text(p, "D2: 1440 sectors of 256") is not None,
                  f"...on D2:, the applications floppy, 1440 x 256 ({p})")
            bottom = find_text(p, "Exit")[1] - 4
            check(any(h[1] > bottom for h in find_all(p, "Format")),
                  f"...to Format: the action button says so ({p})")
            print("  File -> Format... with D2: selected: DISKUTIL on Format, D2:")
            back_to_desk(p, "format")

        # -- 2. D1: dragged onto D2: ------------------------------------------------
        src, dst = t.desk_icon("DISK D1:"), t.desk_icon("DISK D2:")
        t.go(src)
        t.run([F(4), B(1), F(30), M(src[0] + 8, src[1] + 2), F(4)]
              + path((src[0] + 8, src[1] + 2), dst, speed=4) + [F(6), B(0), F(10)])
        p = wait_for("Format and copy disks", "copy")
        if check(p is not None, "D1: dropped on D2: ran DISKUTIL"):
            bottom = find_text(p, "Exit")[1] - 4
            check(any(h[1] > bottom for h in find_all(p, "Copy")),
                  f"...to Copy: the action button says so ({p})")
            check(find_text(p, "D2: 1440 sectors of 256") is not None,
                  f"...onto D2: ({p})")
            print("  D1: dragged onto D2:: DISKUTIL on Copy, D1: to D2:")
            back_to_desk(p, "copy")

        # -- 3. no DISKUTIL on any disk ----------------------------------------------
        b.ok("EJECT 1")                     # D2:, counted from 0
        t.click(t.desk_icon("DISK D1:"))
        t.choose(FILEMENU, FORMITEM)
        p = wait_for("DISKUTIL.PRG", "missing", most=6000)
        if check(p is not None, "with no DISKUTIL on any disk, an alert says where it is"):
            m = find_text(p, "DISKUTIL.PRG")
            ok = [h for h in find_all(p, "OK") if 0 < h[1] - m[1] < 6 * CELL]
            if check(ok, f"the alert's OK ({p})"):
                t.click((ok[0][0] + 4, ok[0][1] + 4))
            print("  no DISKUTIL: the alert, and the desktop goes on")
        q = shot("end")
        # D2:'s label: D1:'s is selected, white on black, which find_text
        # does not read
        check(find_text(q, "DISKUTIL.PRG") is None and find_text(q, "DISK D2:") is not None,
              f"the alert gone and the desktop there ({q})")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m64: {'PASS' if not problems else 'FAIL'} -- the desktop formats and "
          f"copies disks through DISKUTIL, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
