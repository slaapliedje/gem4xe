#!/usr/bin/env python3
"""Phase 14, milestone 5 gate: the GEM Desktop and its folder windows.

DESKTOP.G4A (src/desk) under sh_main on the SpartaDOS disk, with the
harness at the mouse: the desk comes up with its drive icons and the
trash under the menu bar; a click selects an icon; Desk -> About opens
the dialog, OK closes it; a double-click on drive A opens a window on
A:\\*.*, sorted folders first; a double-click on the SUB folder walks
the window into it, File -> Close walks it back out; the fuller grows
the window to the desk and back; the down arrow scrolls the listing a
row; the closer, at the root, closes the window; File -> Quit ends the
session.  Four
things are checked --

  the screen, against the model, at every stop: the desk up, the Desk
  menu dropped, the About item under the pointer, the dialog with OK
  under the pointer, the window on A:, on A:\\SUB, on A: again, full,
  back, scrolled, closed, the File menu dropped, Quit under the pointer;

  the desktop's globals G, read out of the target at every stop where
  they changed and compared byte for byte with the model's: the screen
  tree as deskobj.c and deskwin.c build and free it, the WNODEs and
  their in-place strings, the icons' ICONBLKs and labels, the geometry
  the AES answered;

  the calls: the ABI's counter says which call the desktop is inside,
  the harness feeds each wait its input while the target is in that
  call (m7_form.drive), and the sys op's record at the end says how
  many calls the desktop made in all, which must be the model's count
  and none refused -- the GEMDOS calls that read the directory among
  them, answered on the model from the listing this gate reads off the
  disk image (tools/atr.py);

  the pool and the far heap afterwards: back where they were, and the
  stack's low-water mark under the desktop.

The model is not a script but the desktop itself, transcribed against
the AES model (tools/deskref.py): it asks the model what the target asks
the AES, and the answers steer it the way the AES's steer the target.
Every address the desktop uses -- its near region, G, the resource, the
far arena its Malloc gets -- is derived as the loader derives it;
nothing is read off a probe.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vdiref, vbxeref, symfile, atr    # noqa: E402
import deskref                              # noqa: E402
from deskref import Desktop, DROOT, GLOBES_SIZE  # noqa: E402
from aesref import (W_CLOSER, W_FULLER, W_DNARROW, W_RTARROW,  # noqa: E402
                    FA_RDONLY, FA_HIDDEN, FA_SUBDIR, FA_ARCHIVE)
from deskrsc import (DESKMENU, FILEMENU, VIEWMENU, ABOUITEM, CLOSITEM, FITITEM,  # noqa: E402
                     QUITITEM, ICONITEM, TEXTITEM, SIZEITEM, NAMEITEM, DEOK)
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE,  # noqa: E402
                     F, B, M, DCLICK, drive, compare, storm_check)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC                 # noqa: E402
from m14_sparta import DISK as M14_DISK, boot, screen   # noqa: E402
from m16_shell import SHELL                 # noqa: E402
from demo_aes import path                   # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m17-boot.atr"))
# The desktop gates' runner: the conformance runner with its staging cut
# down, so the pool it loads the desktop and DESKTOP.RSC into is the size
# GEM.COM gives them (the Makefile, M3DESK_SIZES).
SYMS = os.path.join(ROOT, "build", "m3desk.sym")
DESKTOP = os.path.join(ROOT, "build", "desktop.g4a")
DESK_RSC = os.path.join(ROOT, "build", "desktop.rsc")
DESK_SYM = os.path.join(ROOT, "build", "desktop.sym")
SHOT = ("shot", None)
PROBE = ("probe", None)                     # G, read out of the target
DRVBYT = 0x070A                             # DOS 2's drive map (gemdos.c)
DATE0 = 0x0021                              # gemdos.c GD_DATE0
# the stops, in the order the plans take them
STOPS = ["desktop", "desk-menu", "about-item", "about", "window-a", "sub",
         "closed-folder", "full", "text-view", "by-size", "with-fit",
         "no-fit", "scrolled-right", "unfull",
         "scrolled", "closed", "file-menu", "quit-item"]


def GCLICK(xy):
    """A click on a window gadget.  The desktop asks for two clicks, so
    the AES holds every press for the double-click time before it acts
    on it; then the control manager watches the gadget while the button
    is down and sends its message at the release, which ends the wait."""
    return [M(*xy), B(1), F(14), B(0)]


def rsc_imlen(path):
    """The bytes of image data at the END of a .RSC -- what rs_load moves
    to far memory, or 0 when it keeps them (a resource with BITBLKs or
    free images, whose bytes a near address has to be able to name)."""
    d = open(path, "rb").read(36)
    h = struct.unpack(">18H", d)
    imdata, nbb, nimages, rssize = h[7], h[14], h[16], h[17]
    if nbb or nimages:
        return 0
    return rssize - imdata


def header(path):
    """The G4A header's link addresses and far banks (src/sys/app.c
    app_load).  Either format, 3 or 4: they differ only in how wide a far
    fixup offset is, which is past everything read here."""
    with open(path, "rb") as f:
        d = f.read(20)
    assert d[:3] == b"G4A" and d[3] in (3, 4), d[:4]
    link_near, near_size = struct.unpack("<HH", d[4:8])
    return link_near, near_size, d[15]


def link_bank(path):
    """The bank the far image was LINKED at (byte 14): a far link address L
    relocates to ((base >> 16) + (L >> 16) - link_bank) << 16 | (L & 0xFFFF).
    Only a large-data program needs it -- that is where its globals are."""
    with open(path, "rb") as f:
        return f.read(16)[14]


def desk_large():
    """Is the desktop a --data-model=large program?  Read out of its map's
    own command line -- clib-lc-ld.a against clib-lc-sd.a, the same test
    tools/memreport.py makes -- so it follows the build rather than being
    restated here.  It decides where G and the resource live."""
    try:
        with open(os.path.join(ROOT, "build", "desktop.map"),
                  "r", errors="replace") as f:
            return "clib-lc-ld.a" in f.read(4096)
    except OSError:
        return False


def rsc_rssize(path):
    """rsh_rssize: what rs_load allocates, near or far (src/aes/rsrc.c)."""
    return struct.unpack(">18H", open(path, "rb").read(36))[17]


def desk_g(b, syms):
    """Where the desktop's G is in the RUNNING machine.

    A small-data build keeps it in the near region the pool gave it
    (app_near); a large-data one keeps it in far bss, placed with the rest
    of the far image (app_far).  src/sys/app.c exports both addresses for
    exactly this, because a gate cannot otherwise find a large-data
    program's globals -- its .sym gives a LINK address in bank $02 or $03,
    not where the loader put it.
    """
    dsyms = symfile.load(DESK_SYM)
    g_link = dsyms["G"]
    link_near, _, _ = header(DESKTOP)
    if not desk_large():
        return b.peek16(syms["app_near"]) + g_link - link_near
    d = b.memdump(syms["app_far"], 3)
    base = d[0] | (d[1] << 8) | (d[2] << 16)
    return (base + (((g_link >> 16) - link_bank(DESKTOP)) << 16)
            + (g_link & 0xFFFF))


def desk_places(brk):
    """Where app_load and rs_load put the desktop, as the model must see it.

    The .g4a blob sits at `brk` (shel.c far_read_file), the code's banks
    start at the next bank boundary (app.c app_load, farmem.c
    far_alloc_banks), and what follows them is the resource: the WHOLE file
    when the desktop is a large-data program, because rs_load puts it far
    rather than in the pool, or just the icon bitmaps rs_fixit moved up
    when it is not (src/aes/rsrc.c).

    Returns the keywords Desktop() wants, so the five gates that build the
    model share one copy of this arithmetic instead of five.
    """
    link_near, near_size, far_banks = header(DESKTOP)
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3
    far_base = (brk + desk_len + 0xFFFF) & ~0xFFFF
    after = far_base + (far_banks << 16)
    large = desk_large()
    rlen = rsc_rssize(DESK_RSC) if large else rsc_imlen(DESK_RSC)
    return dict(link_near=link_near, near_size=near_size,
                far_base=far_base if large else None,
                link_bank=link_bank(DESKTOP),
                rsc_far=after if large else None,
                imbase=after if (not large and rlen) else None,
                dos_brk=after + ((rlen + 3) & ~3))


def listing(disk):
    """The image's directories as the target's Fsfirst/Fsnext report
    them (src/sys/gemdos.c gd_next over SDX's raw entries): {path: [(name,
    attr, time, date, size)]} keyed the way the desktop's specs name them.

    `disk` is the path to an image, or a file system already open on one
    -- a partition of the CF card, in tests/emu/cf_boot.py."""
    fs = atr.Sdfs(atr.ATRImage.load(disk)) if isinstance(disk, str) else disk
    dirs = {}

    def stamp(e):
        y = 2000 + e.year if e.year < 80 else 1900 + e.year
        date = DATE0
        if 1 <= e.month <= 12 and 1 <= e.day <= 31:
            date = ((y - 1980) << 9) | (e.month << 5) | e.day
        time = 0
        if e.hour <= 23 and e.minute <= 59 and e.second <= 59:
            time = (e.hour << 11) | (e.minute << 5) | (e.second >> 1)
        return time, date

    def walk(where, spec):
        ents = []
        for e in fs.entries(where):
            s = e.status
            attr = ((FA_RDONLY if s & 0x01 else 0) | (FA_HIDDEN if s & 0x02 else 0)
                    | (FA_ARCHIVE if s & 0x04 else 0) | (FA_SUBDIR if s & 0x20 else 0))
            time, date = stamp(e)
            ents.append((e.filename.upper(), attr, time, date, e.size))
            if e.is_dir:
                walk(where + "/" + e.filename, spec + e.filename.upper() + "\\")
        dirs[spec] = ents

    walk("", "A:\\")
    return dirs


def menu(d, title, item, shots):
    """The steps that choose `item` from the `title` menu of the desktop
    `d` at a wait: a screenshot with the menu dropped and another with
    the item under the pointer when `shots`."""
    t = d.centre(d.a_menu, title)
    # straight down from the title into its drop-down: a slant would
    # cross into the next title first and drop that menu instead
    i = (t[0], d.centre(d.a_menu, item)[1])
    # the wait asks for two clicks, so the press is held through the
    # double-click delay before the menu sees it (m7_form.CLICK)
    return [F(3), *path(d.pointer(), t), F(8), *([SHOT] if shots else []),
            *path(t, i, speed=4), F(8), *([SHOT] if shots else []), B(1), F(14)]


def inputs(memo):
    """The step producers, one per wait the desktop blocks in.  `memo`
    collects what the gate reads back from the model at each: G as it
    stands when the wait begins, one snapshot per PROBE step."""
    def probe(d):
        memo.setdefault("globes", []).append(d.globes())
        return PROBE

    def icon_click(d):
        # the first evnt_multi: the desk is up, G is complete
        memo["icon"] = d.screen[DROOT].ob_head
        icon = d.centre(d.g_screen_addr, memo["icon"])
        return [F(3), probe(d), SHOT, *path(d.pointer(), icon), F(6),
                B(1), F(2), B(0), F(14)]

    def desk_about(d):
        return menu(d, DESKMENU, ABOUITEM, True)

    def about_ok(d):
        # form_do, entered with the button still down from the item
        ok = d.centre(d.a_info, DEOK)
        return [F(3), B(0), F(2), *path(d.pointer(), ok), F(10), SHOT,
                B(1), F(14), B(0)]

    def open_a(d):
        # two clicks on drive A's icon (still selected from the first
        # click): do_dopen -- a window on A:\*.*
        icon = d.centre(d.g_screen_addr, memo["icon"])
        return [F(3), probe(d), *path(d.pointer(), icon), F(4), *DCLICK(icon)]

    def window_a(d):
        # the window is up and drawn; two clicks on the SUB folder walk
        # the window into it (do_fopen)
        pw = d.win_ontop()
        memo["wh"] = pw.id
        sub = d.item(pw, "SUB")
        return [F(3), probe(d), SHOT, *path(d.pointer(), sub), F(4), *DCLICK(sub)]

    def sub(d):
        # File -> Close: back out to A:\*.* (win_close without closing)
        return [F(3), probe(d), SHOT, *menu(d, FILEMENU, CLOSITEM, False)[1:]]

    def closed_folder(d):
        # the fuller: WM_FULLED, the window grows to the desk.  The button
        # is still down from the Close item.
        g = d.gadget(memo["wh"], W_FULLER)
        return [F(3), B(0), F(2), probe(d), SHOT, *path(d.pointer(), g), F(2),
                *GCLICK(g)]

    def full(d):
        # the fuller again: back to where it was
        g = d.gadget(memo["wh"], W_FULLER)
        return [F(3), probe(d), SHOT, *path(d.pointer(), g), F(2), *GCLICK(g)]

    def as_text(d):
        # View -> Show as text.  The item is checked, every open window
        # is built again and then drawn, and the listing that was a grid
        # of icons is a column of lines.
        return [F(3), *menu(d, VIEWMENU, TEXTITEM, False)[1:]]

    def text_view(d):
        # what the lines say: the mark, the name and extension in their
        # columns, the size right-aligned, the stamp -- all of it placed
        # by the resource's template (tools/deskrsc.py STFLINE).  Then
        # View -> Sort by size, which is the order that shows in a text
        # view whether it worked.
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, VIEWMENU, SIZEITEM, False)[1:]]

    def by_size(d):
        # biggest first -- and the folder still at the top, because
        # folders come first in every order but No sort (deskwin.c
        # pn_comp).  Then back to by name, and to icons.
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, VIEWMENU, NAMEITEM, False)[1:]]

    def sorted_back(d):
        return [F(3), B(0), F(2), *menu(d, VIEWMENU, ICONITEM, False)[1:]]

    def with_fit(d):
        # the icons back, and the window is NOT full -- which is the only
        # state in which size to fit shows, because it is what makes the
        # window narrower than the screen's own grid.  View -> Size to
        # fit turns it OFF.
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, VIEWMENU, FITITEM, False)[1:]]

    def no_fit(d):
        # the same listing laid out for the WIDEST window this screen
        # could show (G.g_icols) instead of for this one, so it runs off
        # the right-hand edge and the horizontal slider has somewhere to
        # go for the first time.  The right arrow: WA_RTLINE.
        # ...held, not clicked: an arrow gadget sends its WM_ARROWED at
        # the PRESS once the double-click time has passed, so the wait
        # ends with the button still down and the next step releases it
        # (as unfull does below).
        g = d.gadget(memo["wh"], W_RTARROW)
        return [F(3), B(0), F(2), probe(d), SHOT, *path(d.pointer(), g), F(2),
                B(1), F(14)]

    def scrolled_right(d):
        # a column further along, and then size to fit back on -- which
        # puts the columns back under the window and w_cvcol back to 0
        return [F(3), B(0), F(2), probe(d), SHOT,
                *menu(d, VIEWMENU, FITITEM, False)[1:]]

    def unfull(d):
        # the down arrow: WM_ARROWED WA_DNLINE at the press (once the
        # double-click time has passed), the listing scrolls a row
        # the button is still down from the Show as icons item
        g = d.gadget(memo["wh"], W_DNARROW)
        return [F(3), B(0), F(2), probe(d), SHOT, *path(d.pointer(), g), F(2),
                B(1), F(14)]

    def scrolled(d):
        # The arrow is released first thing: the control manager sends
        # WM_ARROWED again once it has been held for the double-click
        # time, and the target's clock ran while the desktop scrolled.
        # Then the closer: WM_CLOSED is File -> Close, and at the root
        # the window goes.
        g = d.gadget(memo["wh"], W_CLOSER)
        return [F(1), B(0), F(2), probe(d), SHOT, *path(d.pointer(), g), F(2),
                *GCLICK(g)]

    def closed(d):
        return [F(3), probe(d), SHOT, *menu(d, FILEMENU, QUITITEM, True)[1:]]

    return [icon_click, desk_about, about_ok, open_a, window_a, sub,
            closed_folder, full, as_text, text_view, by_size, sorted_back,
            with_fit, no_fit, scrolled_right,
            unfull, scrolled, closed]


def model(mark, brk, pointer, drvmap):
    """The prelude and the desktop against the model: (v, a, want, d, memo).
    `brk` is the far heap's cursor before the shell reads the desktop's
    file to it."""
    v, a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
    # sh_main before the desktop: the previous program's workstations
    # closed, the window manager, the menu and the pointer started, the
    # desk drawn (m16_shell.model_desk)
    v.close_virtuals()
    a.wm_init()
    a.mn_init()
    a.ratinit()
    a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
    a.tree = a.W_TREE
    a.draw(0, 0, (0, 0, a.gl_width, a.gl_height))
    # Where the loader and rs_load put the desktop: desk_places() above,
    # shared with the other four gates that build this model.
    pl = desk_places(brk)
    a.dos_brk = pl.pop("dos_brk")
    a.dos_dirs = listing(DISK)
    g_link = symfile.load(DESK_SYM)["G"]
    memo = {}
    d = Desktop(v, a, mark, pl.pop("link_near"), pl.pop("near_size"),
                g_link, drvmap, inputs(memo), **pl)
    d.main()
    return v, a, want, d, memo


def main(argv):
    keep = "--shot" in argv
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    calls, ptr = syms["app_calls"], syms["ptr_state"]
    for addr in (calls, ptr, syms["sh_runs"]):
        assert not 0x4000 <= addr < 0x8000, hex(addr)
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3   # far_alloc's rounding
    os.makedirs(SHOTDIR, exist_ok=True)
    shots = []

    def shot(b, name):
        p = os.path.join(SHOTDIR, f"m17-{name}.png")
        b.screenshot(p)
        shots.append(p)
        return p

    def map_range(path, name):
        ln = [ln for ln in open(os.path.join(ROOT, "build", path))
              if ln.startswith(name + " ")][0].split()
        return tuple(int(x, 16) for x in ln[1].split("-"))

    # m3desk's own map: the runner this gate boots.  m3's shares its
    # layout only until one of them relinks -- a stale m3.map once put
    # the painted range eleven bytes into live variables and read the
    # stack as touching bottom (2026-09-16)
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

    assert DISK != M14_DISK
    emu = launch(tag="m17", memsize="1088K", extra_args=["--disk", DISK])
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
        # GEMDOS's drive map from the DOS seam (src/sys/gemdos.c gd_drvmap)
        drvmap = 0x03 if kind else (b.peek(DRVBYT) or 1)
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room, brk = rec[6] & 0xFFFF, rec[7], (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}; "
              f"DOS kind {kind}, drive map {drvmap:#04x}")

        # The model, all the way through: the desktop's script, its plans
        # and its screens come out of it.
        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want, d, memo = model(mark, brk, pointer, drvmap)
        script = d.script
        print(f"  the model's desktop: {len(script)} calls, waits at {d.waits}, "
              f"near ${d.near:04X}, G ${d.G:04X}, resource ${d.rsc_base:04X}, "
              f"arena ${d.dta:06X}")
        check(len(ref_a.shots) == len(STOPS),
              f"the model took {len(ref_a.shots)} shots, not {len(STOPS)}")

        # The target: the prelude and the shell, staged by hand; the
        # ABI's call counter, zeroed by the sys op, says which of the
        # desktop's calls the target is inside.
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

        # the load from disk is slower than drive() waits for a start
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

        # The desktop's own stack, painted below where it stands at this
        # wait -- the loader zeroed it, and the ABI keeps the caller's S
        # under gem4xe's (src/sys/abi.s: pushed at gem_api_sp).  Its
        # extent is the map's, moved where the loader put the near region.
        app_s = b.peek16(b.peek16(syms["gem_api_sp"]) - 1)
        dstk_lo, dstk_hi = (x + d.near - dlink for x in dstk)
        check(dstk_lo <= app_s <= dstk_hi,
              f"the desktop's S ${app_s:04X} is off its stack ${dstk_lo:04X}-${dstk_hi:04X}")
        b.memload(dstk_lo, bytes([PAINT]) * (app_s + 1 - dstk_lo))

        def desk_low_water(bb):
            dmp = bb.memdump(dstk_lo, dstk_hi - dstk_lo + 1)
            for i, x in enumerate(dmp):
                if x != PAINT:
                    return dstk_lo + i
            return dstk_hi + 1

        # G, read out of the target at each probe while the desktop waits,
        # against the model's snapshot at the same wait
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

        # the plans, and a screenshot at each stop
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
            # where it stuck: the screen, the CPU, and the last few frames
            # of history (the patched bridge; --shot keeps the picture)
            print(f"  screen at the stall: {shot(b, 'stall')}")
            fault = b.peek(syms["irq_fault"])          # src/sys/irq.s
            lw = desk_low_water(b)
            print(f"  irq_fault {fault} ({'none' if fault == 0 else 'BRK' if fault == 2 else 'ABORT' if fault == 3 else 'IRQ'}); "
                  f"the desktop's stack ${dstk_lo:04X}-${dstk_hi:04X}, low water ${lw:04X}"
                  f"{' -- OVERFLOWED' if lw == dstk_lo else ''}")
            try:
                print(f"  REGS: {b.ok('REGS')}")
                b.ok("CONFIG history true")
                b.frames(2)
                for h in b.ok("HISTORY 32").get("entries", []):
                    print(f"    {h.get('k', '')}:{h['pc']} {h.get('bytes', h['op'])} "
                          f"a={h['a']} x={h['x']} y={h['y']} s={h.get('sh', '')}{h['s']} "
                          f"p={h['p']} e={h.get('e', '')}")
            except Exception as e:          # an unpatched build
                print(f"  no post-mortem: {e}")
        poke16(b, ptr + 4, 0)               # the button, held since Quit
        check(next(probes, None) is None, "not every probe was taken")
        for name, rgb in zip(STOPS, ref_a.shots):
            p = os.path.join(SHOTDIR, f"m17-{name}.png")
            if not os.path.exists(p):
                check(False, f"no screenshot at {name}")
                continue
            bad, shown = vbxeref.compare_to_shot(rgb, p)
            check(not bad, f"{name}: {bad} px differ from the model; first {shown[:3]}")
            print(f"  {name:<58s} {'ok' if not bad else 'FAIL'}")

        # the sys op's return
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
        check(lrc == 0, f"the last load's status {lrc}, not 0")
        check(ncalls == len(script),
              f"the desktop made {ncalls} ABI calls; the model made {len(script)}")
        # ...and WHICH call, not just how many: near_of() refuses a far
        # address from several opcodes and the default arm refuses one
        # that does not exist (src/sys/abi.c, gem_badop).
        badop = b.peek16(syms["gem_badop"]) if "gem_badop" in syms else -1
        check(bad == 0, f"{bad} ABI calls refused, the last in AES "
                        f"opcode {badop}")

        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        brk2 = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"after:  pool ${mark2:04X}, {room2} free; far brk ${brk2:06X}")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; was ${mark:04X}, {room}")
        check(brk2 == brk + desk_len,
              f"far brk moved {brk2 - brk} bytes; the desktop's file is {desk_len}")
        lw = low_water(b)
        used, size = stk_hi + 1 - lw, stk_hi - stk_lo + 1
        print(f"stack:  {used} of {size} bytes used at the low-water mark (${lw:04X})")
        check(lw - stk_lo >= MARGIN,
              f"the stack came within {lw - stk_lo} bytes of its bottom ${stk_lo:04X}")
        lw = desk_low_water(b)
        used, size = dstk_hi + 1 - lw, dstk_hi - dstk_lo + 1
        print(f"  the desktop's: {used} of {size} bytes used at the low-water mark (${lw:04X})")
        check(lw - dstk_lo >= DESK_MARGIN,
              f"the desktop's stack came within {lw - dstk_lo} bytes of its bottom ${dstk_lo:04X}")
    finally:
        emu.stop()

    if not fails and not keep:
        for p in shots:
            os.remove(p)
    print(f"gem4xe-m17: {'PASS' if not fails else 'FAIL'} -- the desktop, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--model" in sys.argv:
        # a dry run on the host: the model alone, its script listed
        v, a, want, d, memo = model(0x4800, 0x020000, (0, 0), 0x03)
        deskref.describe(d)
        print(len(d.script), "calls; waits at", d.waits, "; shots", len(a.shots),
              "; probes", len(memo["globes"]))
        for pw in d.wlist:
            print(f"  wnode root {pw.root} id {pw.id} cv {pw.cvrow} "
                  f"col {pw.pncol} row {pw.pnrow} vn {pw.vnrow} "
                  f"spec {pw.path.spec.s!r} count {pw.path.count} size {pw.path.size}")
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
