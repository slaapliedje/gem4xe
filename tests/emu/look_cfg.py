#!/usr/bin/env python3
"""GEM4XE.CFG's LOOK= sets the AES's look before the first window
(src/sys/config.c, gl_3d in src/aes/objc.c).

build/gem-shots.atr is the product SpartaDOS disk, with the Control
Panel's General module and no GENERAL.CFG: nobody has saved a look there,
so the module leaves it alone at boot and the file's line decides.  Three
boots of the same disk, the line in \\GEM\\GEM4XE.CFG changed:

  LOOK=3D        the 3D look is on
  LOOK=WOBBLY    a value this gem4xe does not know is ignored, never
                 refused: the flat look, as with no line at all
  (no line)      flat -- the default, and the control without which "on"
                 could mean anything

    python3 tests/emu/look_cfg.py
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
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from shots import boot, SYMS                  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "gem-shots.atr")
OUT = os.path.join(BUILD, "shots", "look")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def disk_with(work, line):
    """A copy of the product disk whose GEM4XE.CFG ends with `line`."""
    out = os.path.join(work, f"look-{len(os.listdir(work))}.atr")
    shutil.copy(DISK, out)
    img = atr.ATRImage.load(out)
    fs = atr.open_fs(img)
    cfg = fs.read("GEM>GEM4XE.CFG")
    if line:
        cfg += line.encode("ascii") + b"\x9b"
    fs.delete("GEM>GEM4XE.CFG")
    fs.add_file("GEM>GEM4XE.CFG", cfg)
    img.save(out)
    return out


def look_after_boot(disk, tag, syms):
    emu = launch(tag=tag, memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        return b.peek16(syms["gl_3d"])
    finally:
        emu.stop()


def main():
    print("gem4xe-look: LOOK= in GEM4XE.CFG")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="look-")
    try:
        on = look_after_boot(disk_with(work, "LOOK=3D"), "look3d", syms)
        check(on == 1, f"LOOK=3D: the 3D look is on (gl_3d {on})")
        odd = look_after_boot(disk_with(work, "LOOK=WOBBLY"), "lookodd", syms)
        check(odd == 0, f"LOOK=WOBBLY is ignored: flat (gl_3d {odd})")
        none = look_after_boot(disk_with(work, None), "looknone", syms)
        check(none == 0, f"no LOOK line: flat (gl_3d {none})")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-look: {'FAIL' if problems else 'PASS'} -- LOOK= in "
          f"GEM4XE.CFG, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
