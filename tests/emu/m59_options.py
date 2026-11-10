#!/usr/bin/env python3
"""The control panel's Options (phases 140-141, docs/cpanel-plan.md step 4).

On G4DOS -- the system floppy with the panel, GENERAL.CPX and the gate's
module as TEST.CPX (build/cpx4.atr) -- on a disk it may write:

  1. The Options button's pop-up offers three items with no module
     picked -- About, Setup, and Activate, EXTRA.CPZ being on the disk --
     and About puts up an alert that Return takes down.
  2. TEST.CPX picked, it offers seven, so it scrolls, and CPX Info shows what TEST.CPX's
     header says (src/m35_cpx.cpxh): its file, version 01.00 -- four
     BCD digits, as XControl prints them -- id M35T, not
     resident, not loaded at boot; OK goes back to the list.
  3. Setup: the clock's pop-up set to 12 hour and OK -- the strip's time
     ends in a or p; Save writes CONTROL.INF.  General's delay set to
     Instant and OK'd, which saves GENERAL.CFG.
  4. A cold reset brings both back before anybody touches anything: the
     12-hour clock and the Instant delay.
  5. Managing them (phase 141): with EXTRA.CPZ on the disk the pop-up
     offers Activate, which renames it EXTRA.CPX and reads the folder
     again -- three listed; EXTRA picked, Deactivate renames it back --
     two; TEST picked, Unload takes it out of the list -- one; Setup's
     Reload reads the folder again -- two.
  6. The disk afterwards: CONTROL.INF ("CLOCK 12") and GENERAL.CFG
     BESIDE THE MODULES, in GEM, where the AES reads them at boot, and
     EXTRA.CPZ deactivated again.

Each place clicked is the panel's own (Tour.panel, Tour.panel_bytes).
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
import cpanelrsc as cr                        # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, obj, middle, cstring  # noqa: E402
from deskrsc import DESKMENU                  # noqa: E402
from m7_form import K, F, M, B                # noqa: E402
from aesref import RETURN                     # noqa: E402

OUT = os.path.join(ROOT, "build", "shots", "m59")
DISK = os.path.join(ROOT, "build", "cpx4.atr")
CELL = 8
PU_ROW = CELL + 4               # a pop-up slot (cpanel.c, cp_popup)
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def main():
    print("gem4xe-m59: the control panel's Options")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    # THE DISK, with what an older gem4xe left: General's settings saved in
    # the ROOT -- a bare name made goes there on G4DOS -- saying Slow.  The
    # boot must read them (the fixture is live), and the first save beside
    # the modules must take them away, or the root's copy, read first,
    # would win at every boot after (src/aes/shel.c, sh_cpxfile).
    work = tempfile.mkdtemp(prefix="m59-")
    disk = os.path.join(work, "cpx4.atr")
    img = atr.ATRImage.load(DISK)
    atr.Sdfs(img).add_file("GENERAL.CFG", b"G\x02\x03\x00" + bytes(60))
    img.save(disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("m59"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="m59", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        check(b.peek16(syms["mn_display"]) == 400,
              f"the old GENERAL.CFG in the root was read at boot: the delay "
              f"is Slow ({b.peek16(syms['mn_display'])} ms)")

        def opened():
            t.choose(DESKMENU, t.desk_acc("Control Panel"))
            b.frames(80)
            t.settle()
            return t.panel()

        def word(name):
            v = int.from_bytes(t.panel_bytes(name, 2), "little")
            return v - 0x10000 if v & 0x8000 else v

        def options(p):
            """Press Options and let go: the menu comes up over the button,
            and a slow click on it picks nothing (src/app/cpx.h, Popup) --
            then the number of items it shows, from the panel's own tree."""
            wx, wy = p["work"][:2]
            btn = (wx + 11 * CELL + 4 * CELL, wy + 2 + CELL // 2)
            t.go(btn)
            t.run([B(1), F(40), B(0), F(20)])
            # how many the panel offered (cp_optn): the pop-up's own tree
            # has five slots at most, scrolling past that
            return word("cp_optn"), (wx + 11 * CELL - 1, wy + 2 - 1)

        def pick(at, i):
            """Click item i (from 0) of a pop-up whose corner is `at`."""
            t.click((at[0] + 24, at[1] + i * PU_ROW + 2 + 4))
            b.frames(30)
            t.settle()

        def pick_in(at, n, i):
            """Item i of a pop-up of n items: past five it scrolls -- an up
            arrow, three items, a down arrow -- so the down arrow is held
            to the end first when i is beyond the first three."""
            if n <= 5:
                return pick(at, i)
            off = 0
            if i > 2:
                t.go((at[0] + 24, at[1] + 4 * PU_ROW + 2 + 4))   # down arrow
                t.run([B(1), F(90), B(0), F(10)])
                off = n - 3
            pick(at, i - off + 1)

        def rows():
            return t.panel()["rows"]

        def centre():
            raw = os.path.join(OUT, "c.png")
            b.screenshot(raw)
            from PIL import Image
            im = Image.open(raw).convert("L")
            w, h = im.size
            return sum(1 for y in range(h // 3, 2 * h // 3, 2)
                       for x in range(w // 3, 2 * w // 3, 2)
                       if im.getpixel((x, y)) < 64)

        # ---- 1. nothing picked: About, Setup -----------------------------
        p = opened()
        check(p["wh"] > 0, f"the panel opened (window {p['wh']})")
        n, at = options(p)
        check(n == 3, f"no module picked: the Options pop-up shows {n} "
                      f"item(s), About, Setup and -- EXTRA.CPZ on the disk "
                      f"-- Activate")
        before = centre()
        pick(at, 0)
        during = centre()
        check(word("cp_optpick") == cr.CPOPABOUT and during != before,
              f"About picked ({word('cp_optpick')}), and an alert is up "
              f"({before} -> {during} dark pixels in the middle)")
        b.screenshot(os.path.join(OUT, "1-about.png"))
        t.run([K("RETURN", RETURN), F(60)])
        t.settle()
        after = centre()
        b.screenshot(os.path.join(OUT, "1-after-about.png"))
        check(during - after > 300 and after <= before + 40,
              f"...Return took it down ({during} -> {after}, {before} before)")

        # ---- 2. TEST.CPX picked: four items, CPX Info -------------------
        p = t.panel()
        t.click(middle(p["slots"][1]))            # TEST, after GENERAL
        b.frames(20)
        t.settle()
        p = t.panel()
        check(p["sel"] == 1, f"TEST.CPX picked (row {p['sel']})")
        n, at = options(p)
        check(n == 7, f"a module picked: {n} item(s), Open CPX, CPX Info, "
                      f"Unload CPX and Deactivate added")
        pick_in(at, n, 4)                         # CPX Info, scrolled to
        b.screenshot(os.path.join(OUT, "2-info.png"))
        form = t.panel()["form"]
        got = {k: cstring(b, obj(b, form, ob)["spec"] & 0xFFFFFF, 14)
               for k, ob in (("file", cr.CIFILE), ("ver", cr.CIVER),
                             ("id", cr.CIID), ("res", cr.CIRES),
                             ("boot", cr.CIBOOT))}
        print(f"  CPX Info shows {got}")
        check(got == {"file": "TEST.CPX", "ver": "01.00", "id": "M35T",
                      "res": "No", "boot": "No"},
              "CPX Info shows TEST.CPX's header: file, version, id, not "
              "resident, not loaded at boot")
        t.run([K("RETURN", RETURN), F(60)])      # OK, the default
        t.settle()
        check(t.panel()["wh"] > 0 and word("cp_opens") == 0,
              "...OK went back to the list, nothing opened")

        # ---- 3. Setup: 12 hour, OK; Save --------------------------------
        p = t.panel()
        n, at = options(p)
        pick_in(at, n, 1)                         # Setup
        wx, wy = t.panel()["work"][:2]
        clock = (wx + (cr.VALUE_X + 5) * CELL, wy + cr.ROW0 * CELL + CELL // 2)
        t.go(clock)
        t.run([B(1), F(40), B(0), F(20)])         # the clock's pop-up
        cat = (wx + cr.VALUE_X * CELL - 1, wy + cr.ROW0 * CELL - 1)
        pick(cat, 1)                              # 12 hour
        b.screenshot(os.path.join(OUT, "3-setup.png"))
        t.click((wx + (cr.VALUE_X + 5) * CELL,
                 wy + (cr.ROW0 + 3) * CELL + CELL // 2))     # Save
        b.frames(60)
        t.settle()
        t.click((wx + 10 * CELL, wy + cr.BTN_Y * CELL + CELL // 2))   # OK
        b.frames(60)
        t.settle()
        tm = t.panel_bytes("cp_time", 7).split(b"\0")[0].decode("latin-1")
        check(word("cp_hour12") == 1 and tm[-1:] in ("a", "p"),
              f"Setup's clock set to 12 hour: cp_hour12 "
              f"{word('cp_hour12')}, the strip shows {tm!r}")
        b.screenshot(os.path.join(OUT, "3-twelve.png"))

        # ---- 3a. a module's setting saved: General's delay, Instant -----
        import generalrsc as gr
        p = t.panel()
        t.dclick(middle(p["slots"][0]))           # General
        b.frames(60)
        t.settle()
        wx, wy = t.panel()["work"][:2]
        btn = (wx + (gr.GROUP_X + gr.MN_W // 2) * CELL, wy + 7 * CELL + CELL // 2)
        t.go(btn)
        t.run([B(1), F(40), B(0), F(20)])         # the delay's pop-up
        pick((wx + gr.GROUP_X * CELL - 1, wy + 7 * CELL - 1), 0)   # Instant
        t.click((wx + 10 * CELL, wy + gr.BTN_Y * CELL + CELL // 2))  # OK
        b.frames(60)
        t.settle()
        check(b.peek16(syms["mn_display"]) == 0,
              f"General's delay set to Instant and OK'd "
              f"({b.peek16(syms['mn_display'])} ms)")

        # ---- 4. a cold reset: the 12-hour clock is back ------------------
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)   # the reset undid it
        t = Tour(b, syms, OUT)
        check(b.peek16(syms["mn_display"]) == 0,
              f"after a cold reset General's saved delay is back at boot "
              f"({b.peek16(syms['mn_display'])} ms): GENERAL.CFG was read at boot "
              f"again")
        check(word("cp_hour12") == 1,
              f"after a cold reset the panel read CONTROL.INF: cp_hour12 "
              f"{word('cp_hour12')}")

        # ---- 5. managing them: Activate, Deactivate, Unload, Reload -----
        p = opened()
        b.screenshot(os.path.join(OUT, "5-opened.png"))
        check(rows() == 2, f"{rows()} module(s) listed: GENERAL and TEST")
        n, at = options(p)
        check(n == 3, f"EXTRA.CPZ on the disk: {n} item(s), Activate added")
        pick(at, 2)                               # Activate...
        b.frames(20)
        pick(at, 0)                               # EXTRA.CPZ, the only one
        b.frames(60)
        t.settle()
        check(rows() == 3 and word("cp_reloads") == 1,
              f"Activate: EXTRA.CPZ renamed and the folder read again, "
              f"{rows()} listed ({word('cp_reloads')} reload)")
        t.click(middle(t.panel()["slots"][2]))    # EXTRA, the third
        b.frames(20)
        t.settle()
        n, at = options(t.panel())
        check(n == 6, f"EXTRA picked, nothing deactivated: {n} items")
        pick_in(at, n, 5)                         # Deactivate
        b.frames(60)
        t.settle()
        check(rows() == 2, f"Deactivate: EXTRA renamed back, {rows()} listed")
        t.click(middle(t.panel()["slots"][1]))    # TEST
        b.frames(20)
        t.settle()
        n, at = options(t.panel())
        check(n == 7, f"TEST picked, EXTRA.CPZ back: {n} items")
        pick_in(at, n, 5)                         # Unload CPX
        b.frames(60)
        t.settle()
        check(rows() == 1 and b.peek16(syms["sh_ncpx"]) == 1,
              f"Unload: TEST out of the list until a reload, {rows()} listed")
        n, at = options(t.panel())
        pick_in(at, n, 1)                         # Setup
        wx, wy = t.panel()["work"][:2]
        t.click((wx + (cr.VALUE_X + 5) * CELL,
                 wy + (cr.ROW0 + 5) * CELL + CELL // 2))     # Reload
        b.frames(60)
        t.settle()
        t.click((wx + 10 * CELL, wy + cr.BTN_Y * CELL + CELL // 2))   # OK
        b.frames(60)
        t.settle()
        check(rows() == 2 and word("cp_reloads") == 3,
              f"Setup's Reload: TEST back, {rows()} listed "
              f"({word('cp_reloads')} reloads)")
        b.screenshot(os.path.join(OUT, "5-managed.png"))
        check(b.peek16(syms["gem_bad"]) == 0,
              f"{b.peek16(syms['gem_bad'])} call(s) refused")
    finally:
        emu.stop()

    if check(os.path.exists(written), f"the emulator wrote its working copy"):
        # BESIDE THE MODULES, where the AES reads them at boot: written
        # through Cpxfile since phase 141, not by GEMDOS's path (the root)
        fs = atr.Sdfs(atr.ATRImage.load(written))
        gem = fs.list("GEM")
        inf = fs.read("GEM>CONTROL.INF") if "CONTROL.INF" in gem else b""
        check(inf == b"CLOCK 12\x9b" and "GENERAL.CFG" in gem,
              f"CONTROL.INF ({inf!r}) and GENERAL.CFG beside the modules, "
              f"in GEM")
        check("CONTROL.INF" not in fs.list("") and "GENERAL.CFG" not in fs.list(""),
              "...and nothing left in the root")
        check("EXTRA.CPZ" in gem and "EXTRA.CPX" not in gem
              and "TEST.CPX" in gem,
              "EXTRA.CPZ deactivated again, TEST.CPX still there")
        print(f"    the root: {fs.list('')}")
        print(f"    GEM: {fs.list('GEM')}")
        bad = fs.check()
        check(not bad, "the disk's bitmap, chains and free count agree"
              + ("" if not bad else ": " + "; ".join(bad[:4])))
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m59: {'PASS' if not problems else 'FAIL'} -- the control "
          f"panel's Options, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
