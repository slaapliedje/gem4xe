#!/usr/bin/env python3
"""The small desktop items of 0.9's item 4 (docs/roadmap-0.9.md), on the
product disk -- each checked by what it did.

    File -> Show info, DISK A selected on the desk (phase 63)
        the dialog's resource loaded (the far heap rises, as test-m40
        watches it), and what the desktop counted -- folders, files and
        their bytes, the delete's own walk -- equal to the same count
        taken on the host out of the disk image itself
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import deskref                                # noqa: E402
import symfile                                # noqa: E402
import shots                                  # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK   # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from deskrsc import FILEMENU, MASKITEM, CLOSITEM   # noqa: E402

FARMEM_BRK = 8
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def peek32(b, addr):
    d = bytes(b.memdump(addr, 4))
    return int.from_bytes(d, "little", signed=True)


def disk_counts(path):
    """Folders, files and bytes under the root, as the walk counts them."""
    fs = atr.open_fs(atr.ATRImage.load(path))
    dirs = files = size = 0

    def walk(p=""):
        nonlocal dirs, files, size
        for e in fs.entries(p):
            if e.is_dir:
                dirs += 1
                walk((p + ">" if p else "") + e.filename)
            else:
                files += 1
                size += e.size
    walk()
    return dirs, files, size


def listing(t):
    """The labels in the window on top (tests/emu/shots.py Tour.item)."""
    b, tree = t.b, t.g_screen()
    for top in reversed(shots.children(b, tree, 0)):
        if top == shots.DROOT or not shots.children(b, tree, top):
            continue
        return sorted(shots.cstring(b, shots.obj(b, tree, i)["spec"] + 34).strip()
                      for i in shots.children(b, tree, top))
    return []


def set_mask(t, keys):
    t.choose(FILEMENU, MASKITEM)
    t.b.frames(10)
    t.settle()
    for k in ("BACKSPACE",) * 12:               # the field's old mask out
        t.b.key(k)
        t.b.frames(2)
    for k in keys:
        t.b.key(k)
        t.b.frames(3)
    t.b.key("RETURN")
    t.settle()


def main():
    print("gem4xe-m41: the small desktop items")
    syms = symfile.load(SYMS)
    out = os.path.join(HERE, "..", "..", "build", "shots", "m41")
    os.makedirs(out, exist_ok=True)
    want = disk_counts(os.path.abspath(DISK))
    emu = launch(tag="m41", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(10)
        far = lambda: b.peek24(syms["farmem"] + FARMEM_BRK)   # noqa: E731

        # -- Show info on a drive ---------------------------------------
        t.click(t.desk_icon("DISK A"))
        far0 = far()
        b.key("I", ctrl=True)
        b.frames(20)
        t.settle()
        check(far() > far0, "Show info on DISK A puts up its dialog")
        g = t.G()
        got = (peek32(b, g + deskref.g_offset("g_ndirs")),
               peek32(b, g + deskref.g_offset("g_nfiles")),
               peek32(b, g + deskref.g_offset("g_opsize")))
        check(got == want, f"it counted {got[0]} folders, {got[1]} files, "
                           f"{got[2]} bytes; the disk image holds {want}")
        b.screenshot(os.path.join(out, "drive-info.png"))
        b.key("RETURN")
        t.settle()
        check(far() == far0, "...and OK puts it away")

        # -- Set file mask -----------------------------------------------
        t.dclick(t.desk_icon("DISK A"))
        t.click(t.gadget(W_FULLER))
        set_mask(t, ["ASTERISK", "PERIOD", "B", "A", "T"])
        got = listing(t)
        check(got == ["APPS", "AUTOEXEC.BAT", "GEM", "STARTUP.BAT"],
              f"*.BAT lists the BATs and the folders: {got}")
        # *.RSC: nothing in the root, and GEM's resources below it
        set_mask(t, ["ASTERISK", "PERIOD", "R", "S", "C"])
        got = listing(t)
        check(got == ["APPS", "GEM"], f"*.RSC leaves the root its folders: {got}")
        t.dclick(t.item("GEM"))
        got = listing(t)
        check("DESKTOP.RSC" in got and "PREFS.RSC" in got and "GEM.COM" not in got
              and all(n.endswith(".RSC") for n in got),
              f"...and the mask goes down into GEM: {got}")
        t.choose(FILEMENU, CLOSITEM)
        got = listing(t)
        check(got == ["APPS", "GEM"], f"...and back up: {got}")
        set_mask(t, [])
        got = listing(t)
        check("X32G.DOS" in got and len(got) == 5,
              f"an empty mask lists everything again: {got}")
    finally:
        emu.stop()
    print(f"gem4xe-m41: {'FAIL' if problems else 'PASS'} -- the small desktop "
          f"items, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
