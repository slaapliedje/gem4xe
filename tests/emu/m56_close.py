"""Phase 131 gate: closing a program from the Desk menu's list, and the
desktop's Quit with programs aside (switcher step 4's last part).

The G4DOS system floppy with M53.PRG (src/m53_app.c) as M54A, M54B and
M54C, and EDIT.RSC: each puts up EDIT.RSC's menu bar and a title of its
own (step 4); A and B say they understand AP_TERM (step 5), C does not.
SHIFT is the real key, held in POKEY's matrix with F4, which types
nothing.

  1  In C, Gate 1 (A, aside) chosen with SHIFT: A is resumed with AP_TERM
     waiting, and quits; the desktop comes back.
  2  On the desktop, Gate 3 (C, which cannot be asked) with SHIFT: the
     alert, inside it no switch, and afterwards nothing changed.
  3  Quit with C aside: refused -- the alert on the bare desk, then the
     desktop again, GEM still running, the programs still loaded.
  4  C says it understands now; B is to refuse.  Quit: each program aside
     is asked in turn, and B's AP_TFAIL stops it -- B is in front.
  5  In B, its own line chosen with SHIFT: AP_TERM to itself, and it quits.
  6  Quit with C aside: C is asked, quits, and GEM ends -- G4DOS's shell.

    make test-m56
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import (Tour, boot, poke16, PTR_NONE, SYMS, obj, children,  # noqa: E402
                   placed, middle, cstring)
from aesref import W_FULLER                   # noqa: E402
from m14_sparta import screen                 # noqa: E402
from m17_desktop import header                # noqa: E402
from m7_form import CLICK                     # noqa: E402
from demo_aes import path                     # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m56")
APP = os.path.join(BUILD, "m53_app.g4a")
THEDESK = 3
SH_CDIRLEN, SU_NAME, SH_DESKREC = 114, 8, 1   # src/aes/shel.c
NAMES = {1: "M54A", 2: "M54B", 3: "M54C"}
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m56.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    for src, name in ((APP, "M53.PRG"), (APP, "M54A.PRG"), (APP, "M54B.PRG"),
                      (APP, "M54C.PRG"),
                      (os.path.join(BUILD, "edit.rsc"), "EDIT.RSC")):
        args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"),
                disk, src, name]
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    psym = symfile.load(os.path.join(BUILD, "m53_app.sym"))
    plink = header(APP)[0]
    work = tempfile.mkdtemp(prefix="m56-")
    disk = make_disk(work)
    emu = launch(tag="m56", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)

        def P(n):
            return psym[n] - plink + b.peek16(syms["app_near"])

        def w(n, k=0):
            return s16(b.peek16(P(n) + 2 * k))

        def desk():
            return b.peek16(syms["sh_deskrun"]) != 0

        def runs():
            return b.peek16(syms["sh_runs"])

        def ring():
            at = b.peek24(syms["sh_cdir_far"]) + SH_CDIRLEN
            out = []
            for i in range(b.peek16(at)):
                e = int.from_bytes(bytes(b.memdump(at + 2 + 4 * i, 4)), "little")
                out.append("DESK" if e == SH_DESKREC else
                           bytes(b.memdump(e + SU_NAME, 8)).decode().strip())
            return out

        def until(pred, limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if pred():
                    return True
            return False

        def settle_on(pred, limit=1500):
            until(pred, limit)
            t.settle()
            return pred()

        def running(ident):
            return lambda: not desk() and w("r_ready") == 1 and w("r_id") == ident

        def start(name, ident, register):
            n = runs()
            try:
                xy = t.item(f"{name}.PRG")
            except KeyError:
                t.dclick(t.desk_icon("DISK D1:"))
                t.click(t.gadget(W_FULLER))
                xy = t.item(f"{name}.PRG")
            t.dclick(xy)
            if not (check(until(lambda: runs() > n), f"{name}.PRG started")
                    and check(settle_on(lambda: not desk() and w("r_ready") == 1),
                              "...its window opened")):
                raise SystemExit(1)
            poke16(b, P("r_id"), ident)
            poke16(b, P("step"), 4)
            check(settle_on(lambda: w("r_bar") == 1), "...its menu bar is up")
            if register:
                poke16(b, P("step"), 5)
                b.frames(50)

        def to_desktop(what):
            n = runs()
            b.key("TAB", ctrl=True)
            check(until(lambda: runs() > n) and settle_on(desk), what)

        def desktop_from_list(what):
            n = runs()
            choose(rows()["  Desktop"])
            check(until(lambda: runs() > n) and settle_on(desk), what)

        def rows():
            """The Desk drop-down hovered; its list's rows, by text."""
            before = set(blocks())
            t.drop(THEDESK)
            b.frames(10)
            new = [a for a in blocks() if a not in before]
            if not check(len(new) == 1, "the Desk menu's list is down"):
                raise SystemExit(1)
            rects = placed(b, new[0])
            return {cstring(b, obj(b, new[0], i)["spec"], 32): middle(rects[i])
                    for i in children(b, new[0], 0)}

        def blocks():
            n = b.peek16(syms["far_blocks"])
            tab = int.from_bytes(bytes(b.memdump(syms["far_table"], 4)), "little")
            raw = bytes(b.memdump(tab, 8 * n)) if n else b""
            return [int.from_bytes(raw[8 * i:8 * i + 4], "little") & 0xFFFFFC
                    for i in range(n)]

        def choose(xy, shift=False):
            """Straight down from the Desk title to the row, and a click --
            with SHIFT held, the real key (and F4, which types nothing)."""
            t.run(path(t.here(), (t.here()[0], xy[1]), speed=4))
            b.frames(6)
            if shift:
                b.key_raw("F4", True, shift=True)
                b.frames(4)
            t.run(CLICK())
            b.frames(10)
            if shift:
                b.key_raw("F4", False, shift=True)
            b.frames(20)

        def in_alert():
            """Process 0 in sh_close's alert: ev_appwait is put down for
            it, and is up whenever it waits in an evnt_ call of its own."""
            return b.peek(syms["ev_appwait"]) == 0

        # -- three programs; A and B can be asked to end, C cannot ----------
        start("M54A", 1, True)
        to_desktop("A: CONTROL-TAB, the desktop")
        start("M54B", 2, True)
        to_desktop("B: CONTROL-TAB, the desktop")
        start("M54C", 3, False)
        check(ring() == ["DESK", "M54A", "M54B"], f"C running: the ring is {ring()}")

        # 1 -- A, aside, chosen with SHIFT from C's menu ---------------------
        print("  -- 1: in C, Gate 1 chosen with SHIFT")
        n = runs()
        choose(rows()["  Gate 1"], shift=True)
        check(until(lambda: runs() >= n + 2) and settle_on(desk),
              "A was resumed and quit; the desktop is back")
        check(ring() == ["M54B", "M54C"], f"...A is gone: the ring is {ring()}")
        check(b.peek16(syms["sh_lastret"]) == 0, "...A's main() returned 0")

        # 2 -- C, which cannot be asked, chosen with SHIFT -------------------
        print("  -- 2: on the desktop, Gate 3 chosen with SHIFT")
        n = runs()
        choose(rows()["  Gate 3"], shift=True)
        b.frames(60)
        check(in_alert() and desk() and runs() == n, "the alert is up, and "
                                                     "nothing switched")
        b.screenshot(os.path.join(OUT, "2-noterm.png"))
        b.key("RETURN")
        b.frames(150)
        check(not in_alert() and desk() and runs() == n
              and ring() == ["M54B", "M54C"],
              f"...answered: still the desktop, the ring {ring()}")

        # 3 -- Quit, with C aside: refused -------------------------------------
        print("  -- 3: Quit, C aside and not able to be asked")
        n = runs()
        b.key("Q", ctrl=True)
        check(until(lambda: not desk(), 1500), "the desktop ended")
        b.frames(100)
        check(not desk() and runs() == n, "...and the alert is up on the bare "
                                          "desk, GEM still running")
        b.screenshot(os.path.join(OUT, "3-quitloaded.png"))
        b.key("RETURN")
        check(until(lambda: runs() > n) and settle_on(desk),
              "...answered: the desktop again")
        check(ring() == ["M54B", "M54C"], f"...both still loaded: {ring()}")

        # 4 -- C can be asked now; B will refuse ----------------------------
        print("  -- 4: C registers, B will refuse; Quit")
        n = runs()
        choose(rows()["  Gate 3"])
        check(until(lambda: runs() > n) and settle_on(running(3)), "C is in front")
        poke16(b, P("step"), 5)
        b.frames(50)
        desktop_from_list("C: Desktop chosen, the desktop")
        n = runs()
        choose(rows()["  Gate 2"])
        check(until(lambda: runs() > n) and settle_on(running(2)), "B is in front")
        poke16(b, P("r_refuse"), 1)
        terms = w("r_apterms")
        desktop_from_list("B: Desktop chosen, the desktop")
        order = ring()
        print(f"    the ring before Quit: {order}")
        b.key("Q", ctrl=True)
        check(until(running(2), 3000) and settle_on(running(2)),
              "Quit asked each program aside in turn; B refused and is in front")
        check(w("r_apterms") == terms + 1, f"...B was sent AP_TERM "
                                           f"({w('r_apterms')} now)")
        want = [x for x in ["DESK", "M54C"] if x == "DESK"
                or order.index(x) > order.index("M54B")]
        check(sorted(ring()) == sorted(want),
              f"...whatever came before B was asked first and went: {ring()}")
        check(b.peek(syms["sh_closing"]) == 0, "...and the Quit's round is over")

        # 5 -- B closes itself with SHIFT on its own line ---------------------
        print("  -- 5: in B, its own line chosen with SHIFT")
        poke16(b, P("r_refuse"), 0)
        n = runs()
        terms = w("r_apterms")
        choose(rows()["  Gate 2"], shift=True)
        check(until(lambda: runs() > n) and settle_on(desk),
              "B was sent AP_TERM by its own choice, and quit")

        # 6 -- Quit: C asked and gone, and GEM ends ---------------------------
        if "M54C" in ring():
            print("  -- 6: Quit, C aside")
            b.key("Q", ctrl=True)
            until(lambda: False, 2000)
        else:
            print("  -- 6: Quit, nothing aside")
            b.key("Q", ctrl=True)
            until(lambda: False, 800)
        ls = [ln.strip() for ln in screen(b) if ln.strip()]
        check(bool(ls) and ls[-1].endswith("$"),
              f"GEM ended, and G4DOS's shell is back "
              f"({ls[-1] if ls else 'nothing on the screen'})")
        b.screenshot(os.path.join(OUT, "6-shell.png"))
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m56: {'FAIL' if problems else 'PASS'} -- closing from the list, "
          f"and Quit with programs aside, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
