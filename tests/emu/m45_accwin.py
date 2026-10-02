#!/usr/bin/env python3
"""0.12's gate for items 11 and 12: the six accessory slots, and an
accessory's own window.

THE DISK (build/m45-boot.atr) is the product system with seven copies of
the window gate accessory in \\GEM\\, A1.ACC to A7.ACC (src/m45_acc.c),
and no other accessory.

  11. THE SLOTS.  The Desk box has six (src/aes/proc.h, MAX_ACCS), as TOS
      has.  Six copies must load and register -- every slot in use, the
      Desk drop-down eight items long -- and the seventh must be turned
      away.  Turned away AND TOLD: before the desktop starts, the shell
      puts up LANG.RSC's ACCFULL alert, and waits for it.  So the gate
      requires the desktop NOT to have started while the alert is up,
      photographs the alert against tools/aesref.py's, pixel for pixel,
      answers it, and requires the desktop then to start.

  12. THE MESSAGES.  Desk -> the first "Window gate" opens a window of
      that accessory's own.  Every WM_ message the AES sends about a
      window must go to the process that created it (WF_OWNER), and
      until phase 103 they all went to the application -- the desktop --
      whoever owned the window.  The accessory counts what it gets
      (src/m45_acc.c), and a message about any window not its own as a
      misdelivery.  In order:
        - opening it: a WM_REDRAW, which it answers by painting;
        - the desktop's own window opened over it, then a click on what
          shows of the accessory's title bar: WM_TOPPED, which it answers
          with WF_TOP, and the WM_REDRAW of what was covered;
        - its title bar dragged: WM_MOVED, and the window where it was
          dragged to;
        - its close box: WM_CLOSED, which it answers by closing and
          deleting the window.
      And the desktop's window, which owns nothing of the accessory's,
      must stay open and be on top at the end.

Where to click is read off the window tree the AES keeps (gl_wtree): a
window's object there is its whole frame, on the screen.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import aesref, symfile, vbxeref, langrsc      # noqa: E402
from shots import (Tour, poke16, PTR_NONE, SYMS, BUILD, obj, children,  # noqa: E402
                   cstring, STEP, BOOT_WAIT, boot_screen)
from deskrsc import DESKMENU                  # noqa: E402
from m7_form import K, F, M, B                # noqa: E402
from m14_sparta import screen                 # noqa: E402
from m17_desktop import header                # noqa: E402
from m4_aes import PRELUDE                    # noqa: E402
from aesref import RETURN                     # noqa: E402

DISK = os.path.join(BUILD, "m45-boot.atr")
ACC = os.path.join(BUILD, "m45_acc.g4a")
ACC_SYM = os.path.join(BUILD, "m45_acc.sym")
OUT = os.path.join(BUILD, "shots", "m45")
TITLE = "Window gate"
D1_ICON = (40, 38)              # drive D1's icon on the desk
SLOTS = 6                       # src/aes/proc.h MAX_ACCS
COPIES = 7                      # on the disk
WM_KEYS = ("acc_id", "acc_menu", "acc_opens", "acc_closes", "acc_wh",
           "acc_redraws", "acc_topped", "acc_moved", "acc_closed",
           "acc_foreign")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def signed(w):
    return w - 0x10000 if w & 0x8000 else w


def main():
    print("gem4xe-m45: six accessory slots, and an accessory's own window")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    asym = symfile.load(ACC_SYM)
    link_near, _, _ = header(ACC)
    emu = launch(tag="m45", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge

    def shot(name):
        p = os.path.abspath(os.path.join(OUT, f"{name}.png"))
        b.frames(2)
        b.screenshot(p)
        return p

    try:
        # ---- to the boot screen, as shots.boot goes -----------------------
        b.ok("COLD_RESET")
        for t in range(0, 20000, STEP):
            b.frames(STEP)
            if b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502":
                break
        else:
            raise SystemExit("the loader never switched the CPU")
        for t in range(0, BOOT_WAIT, STEP):
            b.frames(STEP)
            if boot_screen(b):
                break
        else:
            raise SystemExit("the boot screen never showed its hint")

        # ---- 11. the slots ------------------------------------------------
        # The accessories are loaded once the boot screen has gone; then
        # the shell either starts the desktop or, a seventh having been
        # turned away, says so first and waits.
        for t in range(0, 6000, 50):
            b.frames(50)
            if b.peek16(syms["gl_accreg"]) >= SLOTS or b.peek16(syms["sh_runs"]):
                break
        b.frames(600)
        naccs = b.peek16(syms["sh_naccs"])
        full = b.peek16(syms["sh_accfull"])
        reg = b.peek16(syms["gl_accreg"])
        nproc = b.peek16(syms["proc_n"])
        print(f"  {naccs} accessories started, {full} turned away, "
              f"{reg} registered, {nproc} processes")
        check(naccs == SLOTS, f"{naccs} accessories started, of {SLOTS} "
                              f"slots")
        check(reg == SLOTS, f"{reg} names registered, of {SLOTS}")
        check(nproc == SLOTS + 1, f"{nproc} processes, of {SLOTS + 1}")
        check(full == COPIES - SLOTS,
              f"{full} accessory(ies) turned away: the "
              f"{COPIES - SLOTS} the disk has past the slots")

        # ...and the person is told: the desktop has not started, and the
        # screen is the alert, as the model draws it on the bare desk.
        runs = b.peek16(syms["sh_runs"])
        check(runs == 0, f"the desktop waits ({runs} runs) while the "
                         f"shell says an accessory was turned away")
        alert = shot("alert")
        mark = b.peek16(syms["app_pool_lo"])
        ptr = syms["ptr_state"]
        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        v, a, _ = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
        v.close_virtuals()
        a.wm_init()
        a.mn_init()
        a.ratinit()
        a.gr_mouse(aesref.ARROW)
        a.tree = a.W_TREE
        a.draw(0, 0, (0, 0, a.gl_width, a.gl_height))
        a.plan = [("frames", 2), ("shot",), ("key", "RETURN", RETURN),
                  ("frames", 2)]
        a.shots = []
        text = dict(langrsc.STRINGS).get("ACCFULL")
        if check(text is not None, "LANG.RSC has an ACCFULL alert to say it with"):
            a.fm_alert(1, text)
            bad, where = vbxeref.compare_to_shot(a.shots[0], alert)
            check(not bad, f"the alert against the model's: {bad} px "
                           f"differ, first {where[:3]} ({alert})")

        t = Tour(b, syms, OUT)
        t.run([K("RETURN", RETURN), F(20)])
        for _ in range(0, 6000, 50):
            b.frames(50)
            if b.peek16(syms["sh_runs"]):
                break
        check(b.peek16(syms["sh_runs"]) == 1,
              "the desktop starts once the alert is answered")
        t.settle()
        b.frames(300)
        t.settle()

        # The Desk drop-down: About, the line, and six accessories.
        tree = b.peek24(syms["gl_mntree"])
        themenus = obj(b, tree, 0)["tail"]
        dabox = obj(b, tree, themenus)["head"]
        items = [cstring(b, obj(b, tree, i)["spec"], 32).strip()
                 for i in children(b, tree, dabox)]
        check(len(items) == 2 + SLOTS and items[2:] == [TITLE] * SLOTS,
              f"the Desk drop-down is {items}")

        # ---- 12. the window ----------------------------------------------
        # Slot 0's accessory, by the title pointer the AES holds: its near
        # region is where acc_title is, less acc_title's link offset.
        title0 = b.peek24(syms["gl_acctitle"])
        near = title0 - (asym["acc_title"] - link_near)
        acc = {n: asym[n] + near - link_near for n in WM_KEYS}

        def got():
            return {n: signed(b.peek16(acc[n])) for n in WM_KEYS}

        wtree = b.peek24(syms["gl_wtree"])

        def frame(wh):
            o = obj(b, wtree, wh)
            return o["x"], o["y"], o["w"], o["h"]

        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t.choose(DESKMENU, t.desk_acc(TITLE))
        b.frames(60)
        t.settle()
        s = got()
        wh = s["acc_wh"]
        print(f"  opened: {s}")
        check(s["acc_opens"] == 1 and wh > 0,
              f"Desk -> {TITLE}: {s['acc_opens']} AC_OPEN, window {wh}")
        check(s["acc_redraws"] >= 1,
              f"its window opened and it was sent "
                                      f"{s['acc_redraws']} WM_REDRAW")
        shot("1-open")
        if wh <= 0:
            return 1
        acc_frame = frame(wh)

        # The desktop's window, over it.
        t.dclick(D1_ICON)
        b.frames(200)
        t.settle()
        dwh = b.peek16(syms["gl_wtop"])
        check(dwh not in (0, wh), f"the desktop's window is on top of it "
                                  f"(gl_wtop {dwh})")
        d = frame(dwh)
        shot("2-under")
        # what shows of the accessory's title bar: its left end when the
        # desktop's window starts to the right of it, else its right end
        ax, ay, aw, ah = acc_frame
        bar_y = ay + 4
        if d[0] > ax + 24 or not (d[1] <= bar_y < d[1] + d[3]):
            bar = (ax + 20 if not (d[0] <= ax + 20 < d[0] + d[2]) or
                   not (d[1] <= bar_y < d[1] + d[3]) else ax + aw - 8, bar_y)
        else:
            bar = (ax + aw - 8, bar_y)
        r0 = got()["acc_redraws"]
        t.click(bar)
        b.frames(60)
        t.settle()
        s = got()
        print(f"  clicked from behind at {bar}: {s}")
        check(s["acc_topped"] == 1, f"a click on it from behind sent it "
                                    f"{s['acc_topped']} WM_TOPPED")
        check(b.peek16(syms["gl_wtop"]) == wh,
              f"its WF_TOP put it on top (gl_wtop "
              f"{b.peek16(syms['gl_wtop'])})")
        check(s["acc_redraws"] > r0, f"uncovered, it was sent a WM_REDRAW "
                                     f"({r0} -> {s['acc_redraws']})")
        shot("3-topped")

        # Dragged by its title bar.
        grab = (ax + aw // 2, ay + 4)
        to = (grab[0] - 64, grab[1] + 24)
        t.go(grab)
        t.run([B(1), F(6)] + [M(grab[0] - 16 * k, grab[1] + 6 * k)
                              for k in range(1, 5)]
              + [F(6), B(0), F(10)])
        b.frames(60)
        t.settle()
        s = got()
        moved = frame(wh)
        print(f"  dragged {grab} -> {to}: {s}, now {moved}")
        check(s["acc_moved"] == 1, f"a drag of its bar sent it "
                                   f"{s['acc_moved']} WM_MOVED")
        check(moved[:2] != acc_frame[:2],
              f"the window moved ({acc_frame} -> {moved})")
        shot("4-moved")

        # Closed by its close box, at the frame's top left.
        mx, my = moved[0], moved[1]
        t.click((mx + 4, my + 4))
        b.frames(60)
        t.settle()
        s = got()
        print(f"  close box: {s}")
        check(s["acc_closed"] == 1, f"its close box sent it "
                                    f"{s['acc_closed']} WM_CLOSED")
        check(s["acc_wh"] == -1, "it has no window left")
        check(s["acc_foreign"] == 0,
              f"{s['acc_foreign']} message(s) about a window not "
              f"its own reached it")
        check(b.peek16(syms["gl_wtop"]) == dwh,
              f"the desktop's window {dwh} is on top at the end "
              f"(gl_wtop {b.peek16(syms['gl_wtop'])})")
        shot("5-closed")
        check(b.peek16(syms["gem_bad"]) == 0,
              f"{b.peek16(syms['gem_bad'])} call(s) refused")
    finally:
        emu.stop()
    print(f"gem4xe-m45: {'PASS' if not problems else 'FAIL'} -- the "
          f"accessory slots and windows, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
