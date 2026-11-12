#!/usr/bin/env python3
"""The kit's control panel module, built by the kit and run (0.15).

The kit's example module had stopped being one a gem4xe could load, and
nothing ran it to say so.  Since phase 133 a module is its 512-byte
header and then its .G4A, and the kit went on making a bare .G4A and
saying "install as .CPX", so the panel refused it.  Its cpx_init still
took the header as a second argument and wrote through it, and
lib/cpxmain.c passes one.  tests/host/test_sdk.py builds it; this gate
LOADS it.

The G4DOS system floppy with the Control Panel and the module the kit
built from example/cpx.c and example/cpx.cpxh (build/kitcpx/cpx.cpx), as
\\GEM\\MINE.CPX, on a disk it may write:

  1. The panel lists one module: the header in front was accepted.
  2. Opened, the example puts its form up in the panel's window (the
     panel's Xform_do), and its OK button brings the list back.
  3. The disk afterwards: MINE.CFG beside the module, the 64 bytes the
     example saved with CPX_Save -- its mark $4B and one opening.

    make test-m61
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import symfile, atr                           # noqa: E402
from shots import Tour, boot, poke16, middle, PTR_NONE, SYMS   # noqa: E402
from deskrsc import DESKMENU                  # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m61")
MODULE = os.path.join(BUILD, "kitcpx", "cpx.cpx")
MY_MARK = 0x4B                  # tools/sdk/cpx.c
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def fresh_disk(work):
    disk = os.path.join(work, "m61.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    img = atr.ATRImage.load(disk)
    fs = atr.open_fs(img)
    for src, name in (("cpanelacc.g4a", "GEM>CONTROL.ACC"),
                      ("cpanel.rsc", "GEM>CPANEL.RSC")):
        fs.add_file(name, open(os.path.join(BUILD, src), "rb").read())
    fs.add_file("GEM>MINE.CPX", open(MODULE, "rb").read())
    img.save(disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("m61"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    return disk, os.path.join(state, "disk.atr")


def main():
    print("gem4xe-m61: the kit's control panel module")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m61-")
    disk, written = fresh_disk(work)
    emu = launch(tag="m61", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        t.choose(DESKMENU, t.desk_acc("Control Panel"))
        b.frames(80)
        t.settle()
        p = t.panel()
        t.shot("listed")
        check(p["wh"] > 0 and p["rows"] == 1,
              f"the panel lists the kit's module: window {p['wh']}, "
              f"{p['rows']} module(s), not 1")
        if p["rows"] == 1:
            opens = p["opens"]
            t.dclick(middle(p["slots"][0]))
            b.frames(40)
            t.settle()
            p = t.panel()
            t.shot("opened")
            check(p["opens"] == opens + 1,
                  f"the module opened: the panel's count {opens} -> {p['opens']}")
            # the example's OK: centred, 32 above the work area's foot
            # (tools/sdk/cpx.c, my_build), the root at the work area
            wx, wy, ww, wh = p["work"]
            t.click((wx + ww // 2, wy + wh - 32 + 8))
            b.frames(40)
            t.settle()
            p = t.panel()
            t.shot("closed")
            check(p["wh"] > 0 and p["rows"] == 1,
                  f"OK brought the list back: window {p['wh']}, {p['rows']} module(s)")
    finally:
        emu.stop()
    if check(os.path.exists(written), f"the emulator wrote its working copy at {written}"):
        fs = atr.Sdfs(atr.ATRImage.load(written))
        names = {e.filename.upper() for e in fs.entries("GEM")}
        check("MINE.CFG" in names, f"MINE.CFG beside the module: \\GEM\\ holds {sorted(names)}")
        if "MINE.CFG" in names:
            cfg = fs.read("GEM>MINE.CFG")
            check(len(cfg) >= 2 and cfg[0] == MY_MARK and cfg[1] == 1,
                  f"MINE.CFG holds the example's mark and one opening: {cfg[:4].hex()}")
    print(f"gem4xe-m61: {'PASS' if not problems else 'FAIL'} -- the kit's module "
          f"loads and saves, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
