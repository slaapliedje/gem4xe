#!/usr/bin/env python3
"""Phase 152 gate: the desktop renames a folder and moves by name, on G4DOS.

The G4DOS system floppy with a tree of the gate's own in MVT:

    MVT\\F.TXT   MVT\\SRC\\A.TXT   MVT\\SRC\\DEEP\\B.TXT   MVT\\DST\\

Two windows: one on MVT, one on MVT\\SRC.  Then, in the window on MVT:

  1  F.TXT dragged onto DST with SHIFT held: a move, and on this drive a
     move BY NAME (GEMDOS's Dcaps says G4DOS's file system moves) -- the
     copy dialog, OK, and on the disk F.TXT in DST with the sector map it
     had before.  A copy and a delete would have written a new one.
  2  SRC dragged onto DST with SHIFT: the folder moved by name, its map
     the same, A.TXT and DEEP\\B.TXT inside it still; and the window that
     was open on MVT\\SRC is open on MVT\\DST\\SRC now.
  3  DST renamed NEW in Show info, whose name field is editable on this
     drive: NEW on the disk with DST's map, and the second window on
     MVT\\NEW\\SRC.
  4  NEW dragged into the second window, which is inside it: the alert
     STINSELF, and nothing moved.

SHIFT is the real key, held in POKEY's matrix with F4, which types
nothing (m56).  The disk is mounted --bootrw and read back afterwards
with tools/atr.py, as test-m19 reads its own.

    make test-m60
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
from shots import Tour, boot, poke16, placed, PTR_NONE, SYMS  # noqa: E402
from aesref import W_NAME                     # noqa: E402
from deskrsc import (FILEMENU, SHOWITEM, VIEWMENU, TEXTITEM,   # noqa: E402
                     FIOK, CDOK, MOVE_ALERT)
from deskref import g_offset, WNODE_SIZE, WN_SPEC, LEN_ZPATH   # noqa: E402
from m7_form import F, M, B, K, RETURN, BACKSPACE   # noqa: E402
from demo_aes import path                     # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m60")
TAG = "m60"
FTXT = b"moved by name\x9b"
ATXT = b"in SRC\x9b"
BTXT = b"in DEEP\x9b"
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def fresh_disk(work):
    """The system floppy with MVT added, and where the run's writes land:
    the emulator's working copy, by the image's own hash (m19)."""
    disk = os.path.join(work, "m60.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    img = atr.ATRImage.load(disk)
    fs = atr.open_fs(img)
    for d in ("MVT", "MVT>SRC", "MVT>SRC>DEEP", "MVT>DST"):
        fs.mkdir(d)
    fs.add_file("MVT>F.TXT", FTXT)
    fs.add_file("MVT>SRC>A.TXT", ATXT)
    fs.add_file("MVT>SRC>DEEP>B.TXT", BTXT)
    img.save(disk)
    with open(disk, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    state = os.path.join(config_dir_for(TAG), "disk_state", sha)
    if os.path.isdir(state):
        shutil.rmtree(state)
    return disk, os.path.join(state, "disk.atr")


def maps(disk):
    """{path: (map, is_dir)} of everything under MVT, read off an image."""
    fs = atr.Sdfs(atr.ATRImage.load(disk))
    out = {}

    def walk(p):
        for e in fs.entries(p):
            q = f"{p}>{e.filename.upper()}"
            out[q] = (e.map, e.is_dir)
            if e.is_dir:
                walk(q)
    walk("MVT")
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m60-")
    disk, written = fresh_disk(work)
    before = maps(disk)
    emu = launch(tag=TAG, memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)

        def wnodes():
            """The open windows' paths, from the desktop's G."""
            out = []
            base = t.G() + g_offset("g_wlist")
            for i in range(4):
                w = base + i * WNODE_SIZE
                if b.peek16(w) not in (0, 0xFFFF):
                    out.append(bytes(b.memdump(w + WN_SPEC, LEN_ZPATH)).split(b"\0")[0].decode())
            return out

        def shift_drag(src, dst):
            """Pressed on src and held, dragged to dst and let go there, SHIFT
            down from before the press until after the release: graf_dragbox
            returns and the desktop asks graf_mkstate then (desktop.c)."""
            t.go(src)
            b.key_raw("F4", True, shift=True)
            t.run([F(4), B(1), F(30), M(src[0] + 8, src[1] + 2), F(4)]
                  + path((src[0] + 8, src[1] + 2), dst, speed=4) + [F(6), B(0), F(10)])
            b.key_raw("F4", False, shift=True)
            t.settle()

        def at(name):
            """An entry of the window on top, as the text view lines it up:
            a folder after its mark, a file's name padded to its extension
            (deskrsc.py's template)."""
            base, _, ext = name.partition(".")
            return t.item(base.ljust(9) + ext if ext else "\x07" + base)

        def listed(name):
            try:
                at(name)
                return True
            except KeyError:
                return False

        def ok_dialog(field, which):
            t.click(t.dialog(field, which))
            t.settle()

        # -- the two windows, side by side, as text ---------------------------
        t.dclick(t.desk_icon("DISK D1:"))
        t.dclick(t.item("MVT"))
        t.dclick(t.item("SRC"))                 # the first: MVT\SRC
        t.dclick(t.desk_icon("DISK D1:"))
        t.dclick(t.item("MVT"))                 # the second, on top: MVT
        nm = t.gadget(W_NAME)                   # moved to the right by its bar
        t.go(nm)
        t.run([B(1), F(4)] + path(nm, (nm[0] + 312, nm[1]), speed=8) + [F(6), B(0)])
        t.settle()
        t.choose(VIEWMENU, TEXTITEM)            # every entry on a line of its own
        t.shot("two")
        check(wnodes() == ["A:\\MVT\\SRC\\*.*", "A:\\MVT\\*.*"],
              f"two windows, on MVT\\SRC and MVT: {wnodes()}")

        # -- 1: a file moved by name -------------------------------------------
        shift_drag(at("F.TXT"), at("DST"))
        t.shot("move-dialog")
        ok_dialog("a_delete", CDOK)
        t.shot("file-moved")
        check(not listed("F.TXT"), "F.TXT is no longer listed in MVT")

        # -- 2: a folder moved by name, and the window on it follows -----------
        shift_drag(at("SRC"), at("DST"))
        ok_dialog("a_delete", CDOK)
        t.shot("folder-moved")
        check(wnodes() == ["A:\\MVT\\DST\\SRC\\*.*", "A:\\MVT\\*.*"],
              f"the window on SRC followed it into DST: {wnodes()}")

        # -- 3: the folder renamed in Show info --------------------------------
        t.click(at("DST"))
        t.choose(FILEMENU, SHOWITEM)
        t.shot("folder-info")
        t.run([F(4)] + [K("BACKSPACE", BACKSPACE) for _ in "DST"]
              + [K(c, ord(c.lower())) for c in "NEW"] + [F(4)])
        ok_dialog("a_finfo", FIOK)
        t.shot("renamed")
        check(wnodes() == ["A:\\MVT\\NEW\\SRC\\*.*", "A:\\MVT\\*.*"],
              f"...and followed it to NEW: {wnodes()}")

        # -- 4: a folder into a window inside it ---------------------------------
        if check(listed("NEW"), "NEW is listed in MVT, to be dragged"):
            # The alert's text is never in bank $00 until it is put up: the
            # desktop's string is in its far resource, and form_alert parses it
            # into the pool.  So finding it there, with the alert up, is the
            # alert -- and not a drop that missed and moved nothing.
            said = MOVE_ALERT[0][2].split("][")[1].split("|")[-1].encode()
            check(said not in bytes(b.memdump(0, 0x10000)),
                  f"{said!r} is not in bank $00 before the drop")
            # the first window's ground, under its two lines: its box in the
            # desktop's screen tree (WNODE's w_root, deskwin.c), low down
            root = b.peek16(t.G() + g_offset("g_wlist") + 2)
            x, y, w, h = placed(b, t.g_screen())[root]
            inside = (x + w // 2, y + h * 3 // 4)
            shift_drag(at("NEW"), inside)
            t.shot("inside-itself")
            check(said in bytes(b.memdump(0, 0x10000)),
                  f"the alert STINSELF is up: {said!r} in bank $00")
            t.run([K("RETURN", RETURN), F(10)])
            t.settle()
            check(wnodes() == ["A:\\MVT\\NEW\\SRC\\*.*", "A:\\MVT\\*.*"],
                  f"nothing moved into itself: {wnodes()}")
    finally:
        emu.stop()
    after = maps(written) if os.path.exists(written) else {}
    if not check(bool(after), f"the emulator wrote its working copy at {written}"):
        return 1
    # BY NAME: the same map sector, which a copy and a delete would not keep
    for old, new in (("MVT>F.TXT", "MVT>NEW>F.TXT"), ("MVT>SRC", "MVT>NEW>SRC"),
                     ("MVT>DST", "MVT>NEW")):
        check(new in after and after[new][0] == before[old][0],
              f"{old} is {new} on the disk, map {before[old][0]} kept: "
              f"{after.get(new)}")
    check("MVT>NEW>SRC>A.TXT" in after and "MVT>NEW>SRC>DEEP>B.TXT" in after,
          f"what SRC held went with it: {sorted(k for k in after if 'SRC' in k)}")
    check(not any(k in after for k in ("MVT>F.TXT", "MVT>SRC", "MVT>DST")),
          f"nothing left behind: {sorted(after)}")
    check(not any(k.startswith("MVT>NEW>SRC>NEW") for k in after),
          "and NEW was not copied into itself")
    print(f"gem4xe-m60: {'PASS' if not problems else 'FAIL'} -- the desktop "
          f"moves by name, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
