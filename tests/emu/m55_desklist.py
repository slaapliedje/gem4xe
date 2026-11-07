"""Phase 130 gate: the Desk menu's list of programs (switcher step 4).

The G4DOS system floppy with M53.PRG (src/m53_app.c) as M54A and M54B,
and EDIT.RSC beside them: asked (step 4), each copy puts up EDIT.RSC's
menu bar and names itself "  Gate N" with menu_register.

  - With the desktop alone, its Desk menu is its own: dropping it builds
    nothing (no far block appears).
  - With programs loaded, the Desk drop-down is the AES's list, read out
    of far memory while it is down: the program's About line, the
    accessories, a line, then every program -- the desktop first, then the
    order they were started in -- with the one in front CHECKED, and each
    under the title it gave itself, kept while it is aside.
  - Choosing a program switches to it: from a program (put aside, the
    other resumed with its menu bar) and from the desktop (AP_G4SWITCH).
  - About is still the program's: MN_SELECTED with its own About item.
    An accessory is still opened: AC_OPEN with its own menu id.
  - The list's block is freed when the menu goes up, every time.

    make test-m55
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
from m17_desktop import header                # noqa: E402
from m7_form import CLICK                     # noqa: E402
from demo_aes import path                     # noqa: E402
from editrsc import ABOUITEM                  # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m55")
APP = os.path.join(BUILD, "m53_app.g4a")
ACC = os.path.join(BUILD, "m50_acc.g4a")
ACC_TITLE = "  Shutdown gate"         # src/m50_acc.c
THEDESK = 3
MN_SELECTED, CHECKED, DISABLED = 10, 0x0004, 0x0008
MAX_ACCS = 6
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m55.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    for src, name in ((APP, "M53.PRG"), (APP, "M54A.PRG"), (APP, "M54B.PRG"),
                      (os.path.join(BUILD, "edit.rsc"), "EDIT.RSC"),
                      (ACC, "GEM>M50.ACC")):
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
    asym = symfile.load(os.path.join(BUILD, "m50_acc.sym"))
    alink = header(ACC)[0]
    work = tempfile.mkdtemp(prefix="m55-")
    disk = make_disk(work)
    emu = launch(tag="m55", memsize="1088K", extra_args=["--disk", disk])
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

        def blocks():
            """{address: (length, owner)} of every far block."""
            n = b.peek16(syms["far_blocks"])
            tab = int.from_bytes(bytes(b.memdump(syms["far_table"], 4)), "little")
            raw = bytes(b.memdump(tab, 8 * n)) if n else b""
            out = {}
            for i in range(n):
                at = int.from_bytes(raw[8 * i:8 * i + 4], "little")
                ln = int.from_bytes(raw[8 * i + 4:8 * i + 8], "little")
                out[at & 0xFFFFFC] = (ln & 0xFFFFFF, at >> 24)
            return out

        listlen = []

        def list_gone():
            """No system block of the list's length is left."""
            return not any(n == listlen[0] and o == 0
                           for n, o in blocks().values())

        def runs_past(n, limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if b.peek16(syms["sh_runs"]) > n:
                    return True
            return False

        def settle_on(pred, limit=1500):
            for _ in range(0, limit, 25):
                b.frames(25)
                if pred():
                    break
            t.settle()
            return pred()

        def accs():
            """The accessories' titles, by slot, as the AES keeps them."""
            out = {}
            for i in range(MAX_ACCS):
                a = int.from_bytes(bytes(b.memdump(syms["gl_acctitle"] + 4 * i, 4)),
                                   "little")
                if a:
                    out[i] = cstring(b, a, 32)
            return out

        def drop_desk():
            """The Desk title hovered: the drop-down down.  The list's block
            if one appeared -- the block that is new while it is down."""
            before = blocks()
            t.drop(THEDESK)
            b.frames(10)
            now = blocks()
            new = sorted(a for a in now if a not in before)
            if len(new) == 1 and not listlen:
                listlen.append(now[new[0]][0])
            return new[0] if len(new) == 1 else None, len(new)

        def listed(d):
            """The list's items: (text, state, its screen middle)."""
            rects = placed(b, d)
            out = []
            for i in children(b, d, 0):
                o = obj(b, d, i)
                out.append((cstring(b, o["spec"], 32), o["state"], middle(rects[i])))
            return out

        def choose(xy):
            """Straight down from the title to the item's row, as the tour's
            choose does: a slant from the title can cross the next one in
            the bar, which takes the menu with it."""
            t.run(path(t.here(), (t.here()[0], xy[1]), speed=4))
            b.frames(6)
            t.run(CLICK())
            t.settle()

        def want_list(d, about, progs, what):
            """The list is About, (a line and the accessories), a line, then
            `progs` -- (text, checked) -- in order."""
            items = listed(d)
            texts = [x[0] for x in items]
            a = accs()
            exp = [about] + ([None] + [a[k] for k in sorted(a)] if a else []) \
                + [None] + [p for p, _ in progs]
            got = [None if (st & DISABLED) and i else x
                   for i, (x, st, _) in enumerate(items)]
            check(got == exp, f"{what}: the list is {texts}")
            ticks = [x for x, st, _ in items if st & CHECKED]
            check(ticks == [p for p, c in progs if c],
                  f"{what}: CHECKED is {ticks}")
            return {x: xy for x, _, xy in items}

        def start(name, ident):
            runs = b.peek16(syms["sh_runs"])
            try:
                xy = t.item(f"{name}.PRG")
            except KeyError:
                t.dclick(t.desk_icon("DISK D1:"))
                t.click(t.gadget(W_FULLER))
                xy = t.item(f"{name}.PRG")
            t.dclick(xy)
            if not (check(runs_past(runs), f"{name}.PRG started")
                    and check(settle_on(lambda: not desk() and w("r_ready") == 1),
                              f"...its window opened")):
                raise SystemExit(1)
            poke16(b, P("r_id"), ident)
            poke16(b, P("step"), 4)
            check(settle_on(lambda: w("r_bar") == 1
                            and b.peek24(syms["gl_mntree"]) != 0),
                  f"...its menu bar is up, its title \"  Gate {ident}\"")

        def about_of_bar():
            """The About line of the bar showing: the Desk box's first."""
            tree = b.peek24(syms["gl_mntree"])
            dabox = obj(b, tree, obj(b, tree, 0)["tail"])["head"]
            return cstring(b, obj(b, tree, dabox + 1)["spec"], 32)

        # -- the desktop alone: its own Desk box ------------------------------
        t.settle()
        about = about_of_bar()
        blk, n = drop_desk()
        check(n == 0, f"the desktop alone: its own Desk box, no list built "
                      f"({n} new far block(s))")
        t.cancel_menu()

        # -- A started; its Desk menu lists the desktop and itself -----------
        start("M54A", 1)
        blk, n = drop_desk()
        if not check(blk is not None, "A's Desk menu: the list, in a block of "
                                      "its own while it is down"):
            raise SystemExit(1)
        b.screenshot(os.path.join(OUT, "01-list-in-A.png"))
        xy = want_list(blk, "  About EDIT...",
                       [("  Desktop", False), ("  Gate 1", True)], "in A")
        print("  -- A: Desktop chosen from the list")
        runs = b.peek16(syms["sh_runs"])
        choose(xy["  Desktop"])
        check(runs_past(runs) and settle_on(desk), "...the desktop is back")
        check(list_gone(), "...and the list's block was freed")

        # -- the desktop with A aside: A under its own title -------------------
        blk, n = drop_desk()
        check(blk is not None, "the desktop's Desk menu, A aside: the list")
        b.screenshot(os.path.join(OUT, "02-list-on-desktop.png"))
        xy = want_list(blk, about, [("  Desktop", True), ("  Gate 1", False)],
                       "on the desktop")
        print("  -- desktop: Gate 1 chosen")
        runs = b.peek16(syms["sh_runs"])
        choose(xy["  Gate 1"])
        check(runs_past(runs) and settle_on(lambda: not desk() and w("r_id") == 1),
              f"...A is resumed: id {w('r_id')}")
        check(w("r_bar") == 1 and b.peek24(syms["gl_mntree"]) != 0,
              "...with its menu bar")
        check(list_gone(), "...and the list's block was freed")

        # -- B beside it ------------------------------------------------------
        runs = b.peek16(syms["sh_runs"])
        b.key("TAB", ctrl=True)
        check(runs_past(runs) and settle_on(desk), "A: CONTROL-TAB, the desktop")
        start("M54B", 2)
        blk, n = drop_desk()
        check(blk is not None, "B's Desk menu: the list")
        b.screenshot(os.path.join(OUT, "03-list-in-B.png"))
        xy = want_list(blk, "  About EDIT...",
                       [("  Desktop", False), ("  Gate 1", False),
                        ("  Gate 2", True)], "in B")
        print("  -- B: Gate 1 chosen")
        runs = b.peek16(syms["sh_runs"])
        choose(xy["  Gate 1"])
        check(runs_past(runs) and settle_on(lambda: not desk() and w("r_id") == 1),
              f"...B aside, A resumed: id {w('r_id')}")

        blk, n = drop_desk()
        check(blk is not None, "A's Desk menu again")
        xy = want_list(blk, "  About EDIT...",
                       [("  Desktop", False), ("  Gate 1", True),
                        ("  Gate 2", False)], "in A, B aside")
        # -- About is the program's own -------------------------------------
        print("  -- A: About chosen from the list")
        sels = w("r_mnsels")
        choose(xy["  About EDIT..."])
        settle_on(lambda: w("r_mnsels") == sels + 1)
        check(w("r_mnsels") == sels + 1 and w("r_mnsel", 0) == THEDESK
              and w("r_mnsel", 1) == ABOUITEM,
              f"...A was sent MN_SELECTED for title {w('r_mnsel', 0)}, item "
              f"{w('r_mnsel', 1)}: its own About ({THEDESK}, {ABOUITEM})")
        check(not desk() and w("r_id") == 1, "...and nothing switched")

        # -- an accessory is still opened -----------------------------------
        # M50.ACC, whose AC_OPEN is counted where the gate can see it
        a = accs()
        slots = [k for k in sorted(a) if a[k] == ACC_TITLE]
        if check(bool(slots), f"M50.ACC registered: {a}"):
            slot = slots[0]
            near = (b.peek24(syms["gl_acctitle"] + 4 * slot)
                    - (asym["acc_title"] - alink))

            def A(n):
                return s16(b.peek16(asym[n] - alink + near))
            opens = A("acc_opens")
            blk, n = drop_desk()
            xy = want_list(blk, "  About EDIT...",
                           [("  Desktop", False), ("  Gate 1", True),
                            ("  Gate 2", False)], "in A, for the accessory")
            print(f"  -- A: {a[slot].strip()} chosen from the list")
            choose(xy[a[slot]])
            b.frames(100)
            check(A("acc_opens") == opens + 1 and A("acc_openid") == slot,
                  f"...it was sent AC_OPEN with menu id {A('acc_openid')}, "
                  f"its slot {slot}")
            b.screenshot(os.path.join(OUT, "04-accessory.png"))
            check(list_gone(), "...and the list's block was freed")

        # -- each quits ---------------------------------------------------------
        def quit_running(what):
            runs = b.peek16(syms["sh_runs"])
            poke16(b, P("app_quit"), 1)
            check(runs_past(runs) and settle_on(desk), what)

        quit_running("A quits: the desktop")
        b.key("TAB", ctrl=True)
        check(settle_on(lambda: not desk() and w("r_id") == 2), "CONTROL-TAB: B")
        quit_running("B quits: the desktop")
        blk, n = drop_desk()
        check(n == 0, f"the desktop alone again: its own Desk box ({n} new)")
        t.cancel_menu()
        check(list_gone(), "no list's block anywhere at the end")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m55: {'FAIL' if problems else 'PASS'} -- the Desk menu's list "
          f"of programs, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
