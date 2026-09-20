#!/usr/bin/env python3
"""Phase 14, milestone 7 gate: the desktop's first writes to a disk.

The desktop from milestones 4 to 6, driven at the mouse and the
keyboard through two operations that change what is on the disk:

  File -> New folder puts up ADMKDBOX, the name typed into its editable
  field ("NEWDIR"), OK -> Dcreate, and the window lists the folder that
  was not there before;

  the window fulled, the SUB folder selected and File -> Show info
  counting what is inside it (three files, one folder, their bytes)
  and showing it -- with the name and the attributes not editable,
  because a folder is neither the DOS's to rename nor its to lock;
  then the same on a FILE, whose extension is edited in place and
  whose OK renames it (Frename) -- the desktop's rename;

  Options -> Save desktop writes the window that is open, its place and
  its path, to DESKTOP.INF, and Options -> Read .INF file reads it
  straight back -- the windows closed and opened again from the file,
  which is the half of remembering that a power cycle uses.  The gate
  reads the file off the image as well;

  and File -> Delete counts what it is about to do
  (the donor's OP_COUNT pass: the folders inside folders walked, a DTA
  per level), says so in ADDELDIA -- three files, two folders -- and on
  OK deletes them, the counts ticking down as they go, and the window
  lists what is left.

Everything milestone 5's gate checks is checked here (the screens
against the model, G byte for byte at every stop, the call count, the
pool and the far heap, the stack), and one thing more: the disk image
itself, read back with tools/atr.py when the run is over.  The gate
runs on a COPY of the milestone-5 disk, made afresh for every run,
because this is the first gate whose target rewrites the directory it
booted from.
"""
import hashlib
import os
import shutil
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import aesref, vdiref, vbxeref, symfile, atr    # noqa: E402
import deskref                              # noqa: E402
from deskref import Desktop, DROOT, GLOBES_SIZE, LEN_ZPATH  # noqa: E402
from deskref import DESK_SPEC, WINDOW_SPEC                    # noqa: E402
from deskrsc import (FILEMENU, OPTNMENU, SHOWITEM, NFOLITEM,  # noqa: E402
                     DELTITEM, QUITITEM, SAVEITEM, READITEM,
                     MKOK, CDOK, FIOK, FICNCL)
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE,  # noqa: E402
                     F, B, K, M, RETURN, BACKSPACE, DCLICK, drive, compare, storm_check)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC                 # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL                 # noqa: E402
from m17_desktop import (DISK as SRC_DISK, DESKTOP, DESK_RSC,  # noqa: E402
                         desk_places,
                         rsc_imlen, DESK_SYM, SYMS,
                         SHOT, PROBE, DRVBYT, GCLICK, header, listing, menu)
from aesref import W_FULLER                 # noqa: E402
from demo_aes import path                   # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m19-run.atr"))
# Where the emulator keeps what a run writes.  Mounted --bootrw,
# AltirraSDL does not write the file it was given: it copies it to
# `<config>/disk_state/<the image's SHA-256>/pristine.atr` and mounts a
# working copy, `disk.atr`, beside it (its src/AltirraSDL/source/app/
# disk_state.cpp, ATResolveDiskMount) -- and reuses that copy on every
# later mount of the same bytes.  So the gate drops the pair before it
# starts, and reads the working copy afterwards; the emulator's log says
# which configuration directory it chose, and the gate checks it against
# this one rather than trusting it.
# ...and that directory is this RUN's own, not the user's: the emulator
# writes its machine settings back on exit, so a shared one lets each gate
# inherit the last one's CPU and RAM (tools/a8test/launcher.py,
# private_config).  The gate still checks the emulator's log against it
# rather than trusting the arrangement.
CONFIG_DIR = config_dir_for("m19")
INF_NAME = "DESKTOP.INF"                    # what Save desktop writes
NEWDIR = "NEWDIR"                           # the folder the gate makes
KILLDIR = "SUB"                             # ...and the tree it deletes
# What Show info renames, and to what.  A FILE: renaming a folder is
# not the DOS's to do -- XIO 32 answers "file not found" for a
# directory on both SpartaDOS 3.2 and SpartaDOS X (tests/emu/
# m15_gdos.py measures it), so the desktop shows a folder's name and
# does not let it be edited.
RENAME_FROM, RENAME_TO = "OUT.TXT", "OUT.DAT"
# ...and the second thing the rubber band catches, deleted with the
# folder to prove the selection really is more than one item
ALSO_KILL = "TEST.RSC"
# What it drags into NEWDIR: the SUB tree, so the walk copies a folder,
# the files in it and the folder inside that.  It has to be an item on
# the window's FIRST row -- the second row's cells hang below the work
# area, where a press belongs to the control manager and never reaches
# the desktop at all.
# One per SHOT, in order, named for what the screen shows at it.
STOPS = ["desktop", "window-a", "new-folder", "made", "exists",
         "picked", "copy-dialog", "copied", "fulled",
         "folder-info", "file-info", "renamed", "selected",
         "delete", "deleted", "saved", "reread"]



def cell(d, pw, name):
    """The rectangle of the cell a window shows `name` in."""
    for pf in pw.path.fnodes[:pw.path.count]:
        if pf.name == name and pf.obid:
            x, y = d.centre(d.g_screen_addr, pf.obid)
            o = d.screen[pf.obid]
            return (x - o.ob_width // 2, y - o.ob_height // 2,
                    o.ob_width, o.ob_height)
    raise KeyError(f"{name} is not shown in {pw.path.spec.s}")


def inputs(memo):
    """The step producers, one per wait the desktop blocks in, as
    milestone 5's gate has them: `memo` collects G at each."""
    def probe(d):
        memo.setdefault("globes", []).append(d.globes())
        return PROBE

    def desktop(d):
        # the desk is up: two clicks on drive A's icon opens its window
        icon = d.centre(d.g_screen_addr, d.screen[DROOT].ob_head)
        return [F(3), probe(d), SHOT, *path(d.pointer(), icon), F(4),
                *DCLICK(icon)]

    def window_a(d):
        # the window on A:\*.*: File -> New folder
        memo["wh"] = d.win_ontop().id
        return [F(3), probe(d), SHOT, *menu(d, FILEMENU, NFOLITEM, False)[1:]]

    def new_folder(d):
        # form_do on ADMKDBOX, entered with the button still down from
        # the item: the name typed, then OK
        ok = d.centre(d.a_mkdir, MKOK)
        return [F(3), B(0), F(2),
                *[K(c, ord(c.lower())) for c in NEWDIR], F(2), SHOT,
                *path(d.pointer(), ok), F(4), B(1), F(14), B(0)]

    def made(d):
        # the folder is in the listing: New folder again, with the name
        # it already has, to see what the desktop says about it
        return [F(3), probe(d), SHOT, *menu(d, FILEMENU, NFOLITEM, False)[1:]]

    def again(d):
        # the same dialog, the same name: Dcreate refuses it
        ok = d.centre(d.a_mkdir, MKOK)
        return [F(3), B(0), F(2), *[K(c, ord(c.lower())) for c in NEWDIR],
                F(2), *path(d.pointer(), ok), F(4), B(1), F(14), B(0)]

    def exists(d):
        # the alert, whose text is a free string of DESKTOP.RSC
        # (STFOFAIL): RETURN takes its default button.  The call is
        # counted as form_alert is ENTERED, and the alert -- parsed,
        # built, its background saved, drawn -- takes it four frames to
        # reach its wait; a key sent before that is typeahead, which
        # fm_do flushes, and the target then waits for a RETURN that
        # never comes.  Ten frames, as m17 gives its about box.
        return [F(10), SHOT, K("RETURN", RETURN)]

    def picked(d):
        # SUB pressed and HELD: the AES waits out the double-click
        # delay before it delivers the event, by which time a hand
        # dragging is still on the button -- which is what makes it a
        # drag rather than a click
        pw = d.win_ontop()
        src = d.item(pw, KILLDIR)
        return [F(3), probe(d), SHOT, *path(d.pointer(), src), F(4),
                B(1), F(2), M(src[0] + 8, src[1] + 4)]

    def dragged(d):
        # the outline dragged onto NEWDIR and let go there: a copy
        pw = d.win_ontop()
        dst = d.item(pw, NEWDIR)
        return [F(2), *path(d.pointer(), dst), F(2), B(0)]

    def copy_dialog(d):
        # the same dialog a delete uses, wearing the copy's title
        ok = d.centre(d.a_delete, CDOK)
        return [F(3), B(0), F(2), SHOT, *path(d.pointer(), ok), F(4),
                B(1), F(14), B(0)]

    def copied(d):
        # the window has been read again after the copy -- that is the
        # shot.  The fuller then: at the window's opening size only two
        # cells are in the work area and both hold folders, and Show
        # info wants a FILE to rename
        g = d.gadget(memo["wh"], W_FULLER)
        return [F(3), probe(d), SHOT, *path(d.pointer(), g), F(2), *GCLICK(g)]

    def fulled(d):
        # the window is the desk now, every entry in it: one click
        # selects SUB, for Show info and then the delete
        pw = d.win_ontop()
        sub = d.item(pw, KILLDIR)
        return [F(3), B(0), F(2), probe(d), SHOT, *path(d.pointer(), sub),
                F(4), B(1), F(2), B(0), F(14)]

    def folder_menu(d):
        # SUB is selected: File -> Show info.  The count pass runs
        # before the dialog, as a delete's does -- a folder is as big
        # as what it holds
        return [F(3), *menu(d, FILEMENU, SHOWITEM, False)[1:]]

    def folder_info(d):
        # ADFINFO on a folder: the title says FOLDER, the counts are
        # the walk's, and the name and the attributes are both shown
        # and not editable.  Cancel.
        cncl = d.centre(d.a_finfo, FICNCL)
        return [F(3), B(0), F(2), SHOT, *path(d.pointer(), cncl), F(4),
                B(1), F(14), B(0)]

    def file_pick(d):
        # ...and one click on a file, for the rename
        pw = d.win_ontop()
        it = d.item(pw, RENAME_FROM)
        return [F(3), *path(d.pointer(), it), F(4), B(1), F(2), B(0), F(14)]

    def file_menu(d):
        return [F(3), *menu(d, FILEMENU, SHOWITEM, False)[1:]]

    def file_info(d):
        # ADFINFO on a file: the title says FILE, the size and stamp
        # are the listing's, the attribute buttons live and the name
        # editable -- the cursor at the end of the places, where three
        # BACKSPACEs take the extension out and three letters put
        # another in.  That is the desktop's rename.
        ok = d.centre(d.a_finfo, FIOK)
        ext = RENAME_TO[RENAME_TO.index(".") + 1:]
        return [F(3), B(0), F(2), SHOT,
                *[K("BACKSPACE", BACKSPACE) for _ in ext],
                *[K(c, ord(c.lower())) for c in ext], F(2),
                *path(d.pointer(), ok), F(4), B(1), F(14), B(0)]

    def renamed(d):
        # the window listed again, the file under its new name.  Then a
        # RUBBER BAND over two cells -- the folder and a file, one above
        # the other -- because that is how several things are selected
        # at once here: SHIFT does it too, and no harness on this
        # machine can hold SHIFT down through a click (docs/phase26.md).
        #
        # The band grows right and down from where it is pressed
        # (src/aes/grlib.c gr_rubwind), so it is anchored in the four
        # pixels of gap to the LEFT of the cells it is to catch, inside
        # the work area rather than above it -- a press on the frame
        # belongs to the control manager and never reaches the desktop.
        pw = d.win_ontop()
        d.item(pw, RENAME_TO)                   # it is there, or KeyError
        x0, y0, _w0, _h0 = cell(d, pw, KILLDIR)
        x1, y1, w1, h1 = cell(d, pw, ALSO_KILL)
        # The press is held through the double-click delay and a nudge
        # of more than two pixels is what flushes the wait -- and the
        # AES reports the pointer where it is THEN, so the nudge travels
        # DOWN the gap rather than across it, or the band would be
        # anchored on the cell it is meant to catch.
        start = (x0 - 3, y0 + 9)
        memo["band"] = (start, (x1 + w1 + 1, y1 + h1 + 1))
        return [F(3), probe(d), SHOT, *path(d.pointer(), (x0 - 3, y0 + 1)),
                F(4), B(1), F(2), M(*start)]

    def banded(d):
        # the box drawn out to past the second cell, and let go
        start, end = memo["band"]
        return [F(2), *path(start, end), F(2), B(0)]

    def chosen(d):
        # File -> Delete: the count pass runs before the dialog
        return [F(3), SHOT, *menu(d, FILEMENU, DELTITEM, False)[1:]]

    def delete(d):
        # form_do on ADDELDIA: what it counted, then OK
        ok = d.centre(d.a_delete, CDOK)
        return [F(3), B(0), F(2), SHOT, *path(d.pointer(), ok), F(4),
                B(1), F(14), B(0)]

    def deleted(d):
        # the tree is gone.  Options -> Save desktop: the window that is
        # open, its place and its path, onto the disk as DESKTOP.INF --
        # which is what makes a desktop remember across a power cycle
        # rather than only across a program (deskwin.c inf_save)
        return [F(3), probe(d), SHOT, *menu(d, OPTNMENU, SAVEITEM, False)[1:]]

    def saved(d):
        # the button is still down from the Save item, as it is after
        # every menu choice: let go before anything else.  Then Options
        # -> Read .INF file, which reads back what was just written,
        # closes what is open and opens what the file says -- the other
        # half of remembering, and the half a power cycle uses
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, OPTNMENU, READITEM, False)[1:]]

    def reread(d):
        # the window is back, in the place and on the path the file
        # carried
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, FILEMENU, QUITITEM, False)[1:]]

    return [desktop, window_a, new_folder, made, again, exists,
            picked, dragged, copy_dialog,
            copied, fulled, folder_menu, folder_info,
            file_pick, file_menu, file_info, renamed, banded, chosen,
            delete, deleted, saved, reread]


def model(mark, brk, pointer, drvmap):
    """The prelude and the desktop against the model, as milestone 5's
    gate builds it (m17_desktop.model), with this gate's inputs."""
    v, a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
    v.close_virtuals()
    a.wm_init()
    a.mn_init()
    a.ratinit()
    a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
    a.tree = a.W_TREE
    a.draw(0, 0, (0, 0, a.gl_width, a.gl_height))
    pl = desk_places(brk)
    a.dos_brk = pl.pop("dos_brk")
    a.dos_dirs = listing(DISK)
    # A folder SpartaDOS X has just made measures 0 in its parent's
    # entry -- measured here, against the 23 (one entry) the host's own
    # mkdir writes -- and the window's information line counts it, so
    # the model's fresh directory measures 0 as well.
    a.dos_newdir = 0
    g_link = symfile.load(DESK_SYM)["G"]
    memo = {}
    d = Desktop(v, a, mark, pl.pop("link_near"), pl.pop("near_size"),
                g_link, drvmap, inputs(memo), **pl)
    d.main()
    return v, a, want, d, memo


def fresh_disk():
    """A copy of milestone 5's disk, and the emulator's own working copy
    of it dropped, so the run starts from the fixture as built.  Returns
    where the run's writes will land."""
    shutil.copyfile(SRC_DISK, DISK)
    with open(DISK, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    state = os.path.join(CONFIG_DIR, "disk_state", sha)
    if os.path.isdir(state):
        shutil.rmtree(state)                # this image's, by its own hash
    return os.path.join(state, "disk.atr")


def check_disk(check, written):
    """What the run left on the disk, read back from the image."""
    if not os.path.exists(written):
        check(False, f"the emulator wrote no working copy at {written}")
        return
    fs = atr.Sdfs(atr.ATRImage.load(written))
    names = {e.filename.upper(): e for e in fs.entries("")}
    check(NEWDIR in names, f"{NEWDIR} is not in the image's root")
    if NEWDIR in names:
        e = names[NEWDIR]
        check(e.is_dir, f"{NEWDIR} is on the disk but is not a folder")
        if e.is_dir:
            # what the drag copied into it: the SUB tree, whole
            got = {x.filename.upper(): x for x in fs.entries(NEWDIR)}
            check(list(got) == [KILLDIR],
                  f"{NEWDIR} holds {sorted(got)}, not just {KILLDIR}")
            if KILLDIR in got:
                inner = {x.filename.upper(): x
                         for x in fs.entries(NEWDIR + ">" + KILLDIR)}
                check(sorted(inner) == ["DEEP", "ONE.TXT", "TWO.DAT"],
                      f"the copy of {KILLDIR} holds {sorted(inner)}")
                for name, size in (("ONE.TXT", 4), ("TWO.DAT", 4)):
                    if name in inner:
                        check(inner[name].size == size,
                              f"the copied {name} is {inner[name].size} "
                              f"bytes, not {size}")
                deep = [x.filename.upper() for x in
                        fs.entries(NEWDIR + ">" + KILLDIR + ">DEEP")]
                check(deep == ["THREE.TXT"],
                      f"the copy of DEEP holds {deep}")
    check(KILLDIR not in names,
          f"{KILLDIR} is still in the image's root after the delete")
    check(ALSO_KILL not in names,
          f"{ALSO_KILL} is still there: the rubber band selected one "
          f"thing, not two")
    check(RENAME_TO in names and RENAME_FROM not in names,
          f"Show info did not rename {RENAME_FROM} to {RENAME_TO}: "
          f"the root has {sorted(names)}")
    # Options -> Save desktop wrote the layout as a FILE, so the next
    # boot of this disk comes up with the window that was open here.
    check(INF_NAME in names, f"{INF_NAME} is not on the disk: the desktop "
                             f"was not saved")
    if INF_NAME in names:
        text = fs.read(INF_NAME).decode("latin-1")
        print(f"  {INF_NAME}: {len(text)} bytes, "
              f"{text.count(chr(13))} lines")
        check(text.startswith("#R 02"),
              f"{INF_NAME} starts {text[:8]!r}, not with its revision")
        check(text.count("#W") == 4,
              f"{INF_NAME} has {text.count('#W')} window lines, not 4")
        check("A:\\*.*@" in text,
              f"{INF_NAME} does not name the window that was open: {text!r}")
        # The backgrounds.  Set preferences... used to change the desk
        # and write nothing down, so the choice was gone at the next
        # boot; the "#Q" line is what carries it, a desk byte and a
        # window byte per screen with the colour screen's first.  These
        # are the DEFAULTS -- this gate never opens the dialog -- and
        # they are written here from desk.h's two specs rather than read
        # out of either implementation.
        want = " %02X %02X %02X %02X" % (DESK_SPEC & 0xFF, WINDOW_SPEC & 0xFF,
                                         DESK_SPEC & 0xFF, WINDOW_SPEC & 0xFF)
        check("#Q" + want + "\r\n" in text,
              f"{INF_NAME} has no '#Q{want}' line -- the desk's pattern and "
              f"colour are not being saved: {text!r}")
    print(f"  the image afterwards: {sorted(names)}")


def main(argv):
    keep = "--shot" in argv
    written = fresh_disk()
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    calls, ptr = syms["app_calls"], syms["ptr_state"]
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3
    os.makedirs(SHOTDIR, exist_ok=True)
    shots = []

    def shot(b, name):
        p = os.path.join(SHOTDIR, f"m19-{name}.png")
        b.screenshot(p)
        shots.append(p)
        return p

    def map_range(path_, name):
        ln = [ln for ln in open(os.path.join(ROOT, "build", path_))
              if ln.startswith(name + " ")][0].split()
        return tuple(int(x, 16) for x in ln[1].split("-"))

    stk_lo, stk_hi = map_range("m3desk.map", "stack")
    dstk = map_range("desktop.map", "stack")         # at the link's near base
    dlink = map_range("desktop.map", "AppDP")[0]
    PAINT, MARGIN, DESK_MARGIN = 0xA5, 256, 64

    def paint(b):
        b.memload(stk_lo, bytes([PAINT]) * (stk_hi - stk_lo + 1))

    def low_water(b):
        dmp = b.memdump(stk_lo, stk_hi - stk_lo + 1)
        for i, x in enumerate(dmp):
            if x != PAINT:
                return stk_lo + i
        return stk_hi + 1

    # --bootrw: the writes go to the image.  Altirra's default for a
    # mounted disk is virtual read/write -- the guest sees its writes and
    # the file never changes -- which is right for every other gate and
    # wrong for this one, whose point is what ends up on the disk.
    emu = launch(tag="m19", memsize="1088K",
                 extra_args=["--bootrw", "--disk", DISK])
    b = emu.bridge
    try:
        t, st = boot(b, prepare=paint)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  M3.COM loaded and running {t} frames after RETURN")
        kind = st[8]
        drvmap = 0x03 if kind else (b.peek(DRVBYT) or 1)
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room, brk = rec[6] & 0xFFFF, rec[7], (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}; "
              f"DOS kind {kind}, drive map {drvmap:#04x}")

        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want, d, memo = model(mark, brk, pointer, drvmap)
        script = d.script
        print(f"  the model's desktop: {len(script)} calls, waits at {d.waits}, "
              f"near ${d.near:04X}, G ${d.G:04X}, arena ${d.dta:06X}; "
              f"{len(ref_a.shots)} screens")
        check(len(ref_a.shots) == len(STOPS),
              f"the model took {len(ref_a.shots)} shots, not {len(STOPS)}")

        stage = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(stage, 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        poke16(b, calls, 0)
        b.poke(STATUS + ST_GO, 1)

        def read():
            return (b.peek16(calls) - 1) & 0xFFFF

        first = d.waits[0]
        for t in range(0, 4000, 5):
            n = read()
            if n != NOT_STARTED and n >= first:
                break
            b.frames(5)
        else:
            check(False, f"the desktop did not reach its first wait (call {read()})")
            return 1
        check(n == first, f"the desktop is in call {n}, not its first wait {first}")
        print(f"  the desktop up {t} frames after GO, in call {n}")

        # its stack, painted below where it stands at this wait
        app_s = b.peek16(b.peek16(syms["gem_api_sp"]) - 1)
        dstk_lo, dstk_hi = (x + d.near - dlink for x in dstk)
        check(dstk_lo <= app_s <= dstk_hi,
              f"the desktop's S ${app_s:04X} is off its stack "
              f"${dstk_lo:04X}-${dstk_hi:04X}")
        b.memload(dstk_lo, bytes([PAINT]) * (app_s + 1 - dstk_lo))

        def desk_low_water(bb):
            dmp = bb.memdump(dstk_lo, dstk_hi - dstk_lo + 1)
            for i, x in enumerate(dmp):
                if x != PAINT:
                    return dstk_lo + i
            return dstk_hi + 1

        probes = iter(enumerate(memo["globes"]))

        def probe(bb):
            k, want_g = next(probes)
            got = bb.memdump(d.G, GLOBES_SIZE)
            if got == want_g:
                print(f"  G at ${d.G:04X}, probe {k} (call {read()}): "
                      f"{GLOBES_SIZE} bytes as the model has them")
                return
            bad = [i for i in range(GLOBES_SIZE) if got[i] != want_g[i]]
            field = [f for f, _ in deskref.GLOBES
                     if deskref.g_offset(f) <= bad[0]][-1]
            check(False, f"G at probe {k} (call {read()}) differs at {len(bad)} "
                         f"byte(s), first at +{bad[0]} ({field} +"
                         f"{bad[0] - deskref.g_offset(field)}): target "
                         f"{got[bad[0]:bad[0] + 8].hex()} model "
                         f"{want_g[bad[0]:bad[0] + 8].hex()}")

        stops = iter(STOPS)

        def take(bb):
            shot(bb, next(stops))

        plan = {k: [("shot", take) if s == SHOT else
                    ("probe", probe) if s == PROBE else s for s in v]
                for k, v in d.plan.items()}
        err = drive(b, None, ptr, plan, read=read)
        check(not err, f"driving the desktop: {err}")
        if err:
            storm = storm_check(b)
            if storm:
                print(f"  {storm}")
            # where it stuck: the screen, what the delete had counted,
            # which call the target is inside, the path the operation
            # was working on, and the last few frames of history (the
            # patched bridge; --shot keeps the picture)
            print(f"  screen at the stall: {shot(b, 'stall')}")
            fault = b.peek(syms["irq_fault"])
            lw = desk_low_water(b)
            print(f"  irq_fault {fault}; the desktop's stack "
                  f"${dstk_lo:04X}-${dstk_hi:04X}, low water ${lw:04X}"
                  f"{' -- OVERFLOWED' if lw == dstk_lo else ''}")
            got = b.memdump(d.G + deskref.g_offset("g_nfiles"), 8)
            print(f"  the target counted {int.from_bytes(got[0:4], 'little')} "
                  f"file(s) and {int.from_bytes(got[4:8], 'little')} folder(s)")
            # the ABI keeps the caller's parameter block, whose control
            # array starts with the opcode (src/sys/abi.c gem_pb,
            # gem_which; a .g4a's block is in bank $00 with its data)
            which = b.peek(syms["gem_which"])
            pb = b.peek16(syms["gem_pb"]) | (b.peek16(syms["gem_pb"] + 2) << 16)
            kind = {0x44: "GEMDOS", 0x56: "VDI", 0x41: "AES"}.get(which, hex(which))
            if pb < 0x10000:
                ctl = b.peek16(pb) | (b.peek16(pb + 2) << 16)
                op = b.peek16(ctl & 0xFFFF) if ctl < 0x10000 else -1
                print(f"  it is inside a {kind} call, opcode {op}")
            addr = symfile.load(DESK_SYM)["op_path"] + d.near - dlink
            raw = bytes(b.memdump(addr, LEN_ZPATH))
            end = raw.find(0)
            print(f"  its op_path ${addr:04X}: "
                  f"{raw[:end if end >= 0 else None].decode('latin-1')!r}")
            try:
                print(f"  REGS: {b.ok('REGS')}")
                b.ok("CONFIG history true")
                b.frames(2)
                for h in b.ok("HISTORY 32").get("entries", []):
                    print(f"    {h.get('k', '')}:{h['pc']} "
                          f"{h.get('bytes', h['op'])} a={h['a']} x={h['x']} "
                          f"y={h['y']} s={h.get('sh', '')}{h['s']} p={h['p']} "
                          f"e={h.get('e', '')}")
            except Exception as exc:            # an unpatched build
                print(f"  no post-mortem: {exc}")
        poke16(b, ptr + 4, 0)               # the button, held since Quit
        check(next(probes, None) is None, "not every probe was taken")
        for name, rgb in zip(STOPS, ref_a.shots):
            p = os.path.join(SHOTDIR, f"m19-{name}.png")
            if not os.path.exists(p):
                check(False, f"no screenshot at {name}")
                continue
            bad, shown = vbxeref.compare_to_shot(rgb, p)
            check(not bad, f"{name}: {bad} px differ from the model; first {shown[:3]}")
            if bad:                         # the model's own, to look at beside it
                print("    model: " + vbxeref.save_rgb(
                    rgb, os.path.join(SHOTDIR, f"m19-{name}-model.png")))
            print(f"  {name:<58s} {'ok' if not bad else 'FAIL'}")

        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            check(False, f"after Quit: the runner did not finish (call {read()})")
            return 1
        b.frames(4)
        n = b.peek16(r.count)
        check(n == len(stage), f"{n} records, not {len(stage)}")
        recs = vdiref.decode(b.memdump(r.results, n * vdiref.RESULT_WORDS * 2), n)
        err = compare(b, r.results, len(PRELUDE), PRELUDE, want)
        check(not err, f"the prelude: {err}")
        rec = recs[-1][2:]
        ret, nruns, lret, lrc, ncalls, bad = rec[6:12]
        print(f"  sh_main returned {ret}: {nruns} run, last returned {lret}, "
              f"last load {lrc}; {ncalls} ABI calls, {bad} refused")
        check(ret == 1, f"sh_main returned {ret}, not the 1 program run")
        check(nruns == 1, f"sh_runs {nruns}, not 1")
        check(lret == 0, f"the desktop's main() returned {lret}, not 0")
        check(ncalls == len(script),
              f"the desktop made {ncalls} ABI calls; the model made {len(script)}")
        check(bad == 0, f"{bad} ABI calls refused")

        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        brk2 = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"after:  pool ${mark2:04X}, {room2} free; far brk ${brk2:06X}")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; "
              f"was ${mark:04X}, {room}")
        check(brk2 == brk + desk_len,
              f"far brk moved {brk2 - brk} bytes; the desktop's file is {desk_len}")
        lw = low_water(b)
        used, size = stk_hi + 1 - lw, stk_hi - stk_lo + 1
        print(f"stack:  {used} of {size} bytes used at the low-water mark (${lw:04X})")
        check(lw - stk_lo >= MARGIN,
              f"the stack came within {lw - stk_lo} bytes of its bottom ${stk_lo:04X}")
        lw = desk_low_water(b)
        used, size = dstk_hi + 1 - lw, dstk_hi - dstk_lo + 1
        print(f"  the desktop's: {used} of {size} bytes used at the low-water "
              f"mark (${lw:04X})")
        check(lw - dstk_lo >= DESK_MARGIN,
              f"the desktop's stack came within {lw - dstk_lo} bytes of its "
              f"bottom ${dstk_lo:04X}")
    finally:
        emu.stop()

    # the emulator's own account of where it kept its state, against
    # the directory the working copy was looked for in
    said = [ln.split("=", 1)[1].strip() for ln in open(emu.log, errors="ignore")
            if ln.startswith("Altirra: config dir =")]
    check(said and os.path.realpath(said[0]) == os.path.realpath(CONFIG_DIR),
          f"the emulator's configuration directory is {said}, not {CONFIG_DIR}")
    check_disk(check, written)              # the disk the run wrote
    if not fails and not keep:
        for p in shots:
            os.remove(p)
    print(f"gem4xe-m19: {'PASS' if not fails else 'FAIL'} -- New folder, "
          f"Delete, Show info, the desktop saved and read back, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--model" in sys.argv:
        fresh_disk()
        v, a, want, d, memo = model(0x4800, 0x020000, (0, 0), 0x03)
        deskref.describe(d)
        print(len(d.script), "calls; waits at", d.waits, "; shots", len(a.shots),
              "; probes", len(memo["globes"]))
        for pw in d.wlist:
            print(f"  wnode root {pw.root} id {pw.id} spec {pw.path.spec.s!r} "
                  f"count {pw.path.count} size {pw.path.size}")
        print("  root now:", [e[0] for e in a.dos_dirs["A:\\"]])
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
