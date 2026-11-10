#!/usr/bin/env python3
"""The control panel's Options (phase 140, docs/cpanel-plan.md step 4).

On G4DOS -- the system floppy with the panel, GENERAL.CPX and the gate's
module as TEST.CPX (build/cpx4.atr) -- on a disk it may write:

  1. The Options button's pop-up offers two items with no module picked,
     About and Setup, and About puts up an alert that Return takes down.
  2. TEST.CPX picked, it offers four, and CPX Info shows what TEST.CPX's
     header says (src/m35_cpx.cpxh): its file, version 01.00 -- four
     BCD digits, as XControl prints them -- id M35T, not
     resident, not loaded at boot; OK goes back to the list.
  3. Setup: the clock's pop-up set to 12 hour and OK -- the strip's time
     ends in a or p; Save writes CONTROL.INF.  General's delay set to
     Instant and OK'd, which saves GENERAL.CFG.
  4. A cold reset brings both back before anybody touches anything: the
     12-hour clock and the Instant delay.  The disk holds CONTROL.INF,
     "CLOCK 12", in the folder GENERAL.CFG is in -- where a bare name
     goes, the root on G4DOS (docs/phase140.md).

Each place clicked is the panel's own (Tour.panel, Tour.panel_bytes).
"""
import hashlib
import os
import shutil
import sys

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
    sha = hashlib.sha256(open(DISK, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("m59"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="m59", memsize="1088K",
                 extra_args=["--bootrw", "--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)

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
            pu = t.panel_bytes("cp_pu", 24)          # the pop-up's root
            return int.from_bytes(pu[4:6], "little"), (wx + 11 * CELL - 1,
                                                       wy + 2 - 1)

        def pick(at, i):
            """Click item i (from 0) of a pop-up whose corner is `at`."""
            t.click((at[0] + 24, at[1] + i * PU_ROW + 2 + 4))
            b.frames(30)
            t.settle()

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
        check(n == 2, f"no module picked: the Options pop-up shows {n} "
                      f"item(s), About and Setup")
        before = centre()
        pick(at, 0)
        during = centre()
        check(word("cp_optpick") == 0 and during != before,
              f"About picked ({word('cp_optpick')}), and an alert is up "
              f"({before} -> {during} dark pixels in the middle)")
        b.screenshot(os.path.join(OUT, "1-about.png"))
        t.run([K("RETURN", RETURN), F(60)])
        t.settle()
        check(abs(centre() - before) < 40, "...Return took it down")

        # ---- 2. TEST.CPX picked: four items, CPX Info -------------------
        p = t.panel()
        t.click(middle(p["slots"][1]))            # TEST, after GENERAL
        b.frames(20)
        t.settle()
        p = t.panel()
        check(p["sel"] == 1, f"TEST.CPX picked (row {p['sel']})")
        n, at = options(p)
        check(n == 4, f"a module picked: {n} item(s), Open CPX and CPX "
                      f"Info added")
        pick(at, 3)
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
        pick(at, 1)                               # Setup
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
        t = Tour(b, syms, OUT)
        check(b.peek16(syms["mn_display"]) == 0,
              f"after a cold reset General's saved delay is back at boot "
              f"({b.peek16(syms['mn_display'])} ms): GENERAL.CFG was read at boot "
              f"again")
        check(word("cp_hour12") == 1,
              f"after a cold reset the panel read CONTROL.INF: cp_hour12 "
              f"{word('cp_hour12')}")
        check(b.peek16(syms["gem_bad"]) == 0,
              f"{b.peek16(syms['gem_bad'])} call(s) refused")
    finally:
        emu.stop()

    if check(os.path.exists(written), f"the emulator wrote its working copy"):
        # BESIDE THE MODULES' SETTINGS, wherever a bare name goes: GEMDOS's
        # path, which on G4DOS is the root and on SpartaDOS X the DOS's
        # own folder (docs/phase140.md; the open Dgetpath question)
        fs = atr.Sdfs(atr.ATRImage.load(written))
        where = [d for d in ("", "GEM") if "GENERAL.CFG" in fs.list(d)]
        folder = where[0] if where else None
        inf = b""
        if folder is not None:
            name = (folder + ">" if folder else "") + "CONTROL.INF"
            if "CONTROL.INF" in fs.list(folder):
                inf = fs.read(name)
        check(inf == b"CLOCK 12\x9b",
              f"CONTROL.INF beside GENERAL.CFG ({folder!r}) says {inf!r}")
        print(f"    the root: {fs.list('')}")
        print(f"    GEM: {fs.list('GEM')}")
        bad = fs.check()
        check(not bad, "the disk's bitmap, chains and free count agree"
              + ("" if not bad else ": " + "; ".join(bad[:4])))
    print(f"gem4xe-m59: {'PASS' if not problems else 'FAIL'} -- the control "
          f"panel's Options, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
