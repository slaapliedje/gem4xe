"""Phase 129 gate: several programs put aside, and the switch key
(switcher steps 3 and 4's key, docs/switcher-plan.md).

The G4DOS system floppy with three copies of M53.PRG (src/m53_app.c) as
M54A, M54B and M54C.PRG.  Each is started from the desktop and put aside
with CONTROL-TAB; then the key goes round them -- from the desktop, which
the AES asks to end (AP_G4SWITCH), from one program straight to the next,
with SHIFT back, and once by the program itself (shel_write(SWM_G4SWITCH)).
After every switch:

  - the one running is the one expected: the id the gate gave that copy,
    its count gone on, its window the top one, and a WM_REDRAW and a
    WM_ONTOP for it
  - THE RING, read out of far memory (src/aes/shel.c), holds the rest in
    the order the circle says: started order, then the desktop

CONTROL-TAB with nothing aside does nothing, and inside a dialog it is
dropped, not kept for later: the desktop's About box, which the screen
lock covers, and an alert a program puts up without taking the lock,
which only the AES's "waiting in an evnt_ call of its own" covers.  Then
each quits; the ring is empty and the far heap is the blocks it was at
the start.

    make test-m54
"""
import os
import re
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
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from m17_desktop import header                # noqa: E402
from deskrsc import DESKMENU, ABOUITEM, DEOK  # noqa: E402
from farheap import far_heap, heap_text       # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m54")
APP = os.path.join(BUILD, "m53_app.g4a")
WM_REDRAW, WM_ONTOP = 20, 31
NAMES = {1: "M54A", 2: "M54B", 3: "M54C"}
problems = []


def shel_define(name):
    """A #define of src/aes/shel.c, so the ring is read as the code lays
    it out rather than as this file remembers it."""
    src = open(os.path.join(ROOT, "src", "aes", "shel.c")).read()
    m = re.search(rf"^#define {name}\s+(\d+)", src, re.M)
    if not m:
        raise SystemExit(f"{name} is not a number in src/aes/shel.c")
    return int(m.group(1))


SH_CDIRLEN = shel_define("SH_CDIRLEN")
SU_NAME = shel_define("SU_NAME")
SH_DESKREC = 1


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m54.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    # M53.PRG too: every copy opens it as its own file (src/m53_app.c)
    for name in ("M53", "M54A", "M54B", "M54C"):
        args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"),
                disk, APP, f"{name}.PRG"]
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    psym = symfile.load(os.path.join(BUILD, "m53_app.sym"))
    plink = header(APP)[0]
    work = tempfile.mkdtemp(prefix="m54-")
    disk = make_disk(work)
    emu = launch(tag="m54", memsize="1088K", extra_args=["--disk", disk])
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

        def ring():
            """The ring's entries: a program put aside by its name, the
            desktop as DESK (src/aes/shel.c, SH_DESKREC)."""
            at = b.peek24(syms["sh_cdir_far"]) + SH_CDIRLEN
            out = []
            for i in range(b.peek16(at)):
                e = int.from_bytes(bytes(b.memdump(at + 2 + 4 * i, 4)), "little")
                out.append("DESK" if e == SH_DESKREC else
                           bytes(b.memdump(e + SU_NAME, 8)).decode().strip())
            return out

        def runs_past(n, limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if b.peek16(syms["sh_runs"]) > n:
                    return True
            return False

        def ready(limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if not desk() and w("r_ready") == 1:
                    return True
            return False

        def start(name, ident):
            """NAME.PRG double-clicked in the desktop's D1: window."""
            runs = b.peek16(syms["sh_runs"])
            try:
                xy = t.item(f"{name}.PRG")
            except KeyError:
                t.dclick(t.desk_icon("DISK D1:"))
                t.click(t.gadget(W_FULLER))
                xy = t.item(f"{name}.PRG")
            t.dclick(xy)
            if not (check(runs_past(runs), f"{name}.PRG started")
                    and check(ready(), f"...its window opened (near base "
                                       f"${b.peek16(syms['app_near']):04X})")):
                raise SystemExit(1)
            poke16(b, P("r_id"), ident)
            check(w("r_fh") > 0, f"...its own file is open: handle {w('r_fh')}")

        state = {}                      # id -> (count, the log's length)
        shots = []

        def leave():
            """What the running program has done so far, kept for its resume."""
            if not desk():
                state[w("r_id")] = (b.peek16(P("r_count")), w("r_nlog"))

        def press(shift=False):
            runs = b.peek16(syms["sh_runs"])
            leave()
            b.key("TAB", ctrl=True, shift=shift)
            return runs

        def arrived(runs, want, ring_want, what):
            """The switch `what` has run `want` (an id, or "DESK") and left
            the ring as `ring_want`."""
            print(f"  -- {what}")
            if not check(runs_past(runs), "the shell ran the next thing "
                                          f"(sh_runs {runs} -> "
                                          f"{b.peek16(syms['sh_runs'])})"):
                raise SystemExit(1)
            if want == "DESK":
                for _ in range(0, 1500, 25):
                    b.frames(25)
                    if desk():
                        break
                t.settle()
                check(desk(), "the desktop is running")
            else:
                for _ in range(0, 1500, 25):
                    b.frames(25)
                    if not desk() and w("r_ready") == 1:
                        break
                t.settle()
                got = w("r_id")
                check(got == want, f"{NAMES[want]} is running: id {got}")
                count, mark = state.get(want, (0, 0))
                now = b.peek16(P("r_count"))
                check(now >= count, f"...RESUMED, its count went on: {count} "
                                    f"before, {now} now")
                log = [(w("r_log", 2 * i), w("r_log", 2 * i + 1))
                       for i in range(mark, w("r_nlog"))]
                wh = w("r_wh")
                check((WM_REDRAW, wh) in log and (WM_ONTOP, wh) in log,
                      f"...told WM_REDRAW and WM_ONTOP for its window: {log}")
                check(b.peek16(syms["gl_wtop"]) == wh, "...its window is the top one")
            r = ring()
            check(r == ring_want, f"the ring is {r}, as the circle says {ring_want}")
            shots.append(what)
            b.screenshot(os.path.join(OUT, f"{len(shots):02d}.png"))

        t.settle()
        before = far_heap(b, syms)
        print(f"  the far heap at the desktop: {heap_text(before)}")
        check(ring() == [], f"nothing loaded: the ring is {ring()}")

        # -- nothing aside: the key does nothing ------------------------------
        runs = b.peek16(syms["sh_runs"])
        b.key("TAB", ctrl=True)
        b.frames(150)
        check(b.peek16(syms["sh_runs"]) == runs and desk(),
              "CONTROL-TAB with nothing aside: the desktop stays")

        # -- three started, each put aside by the key ------------------------
        start("M54A", 1)
        check(ring() == ["DESK"], f"A running: the ring is {ring()}")
        arrived(press(), "DESK", ["M54A"], "A: CONTROL-TAB, the desktop")
        start("M54B", 2)
        check(ring() == ["DESK", "M54A"],
              f"B started just before the desktop: the ring is {ring()}")
        arrived(press(), "DESK", ["M54A", "M54B"], "B: CONTROL-TAB, the desktop")
        start("M54C", 3)
        arrived(press(), "DESK", ["M54A", "M54B", "M54C"],
                "C: CONTROL-TAB, the desktop")

        # -- in a dialog the key is dropped ---------------------------------
        print("  -- the About box: CONTROL-TAB inside it")
        runs = b.peek16(syms["sh_runs"])
        t.choose(DESKMENU, ABOUITEM)
        b.key("TAB", ctrl=True)
        b.frames(100)
        t.click(t.dialog("a_info", DEOK))
        b.frames(200)
        check(b.peek16(syms["sh_runs"]) == runs and desk(),
              "dropped: still the desktop after the box closed")
        check(ring() == ["M54A", "M54B", "M54C"], f"...the ring as it was: {ring()}")

        # -- round the circle ------------------------------------------------
        arrived(press(), 1, ["M54B", "M54C", "DESK"],
                "desktop: CONTROL-TAB, A (AP_G4SWITCH)")
        # -- in a program's own alert, the screen not locked ---------------
        # The About box above is dropped by the screen lock the desktop
        # holds round its menu handling; an alert a program puts up without
        # wind_update holds nothing, and only ev_appwait stops the key there.
        print("  -- A: an alert up, no wind_update, CONTROL-TAB inside it")
        runs = b.peek16(syms["sh_runs"])
        alerts = w("r_alerts")
        poke16(b, P("step"), 3)
        for _ in range(0, 1500, 25):
            b.frames(25)
            if w("r_inalert") == 1:
                break
        b.frames(60)
        check(w("r_inalert") == 1, "its alert is up")
        b.key("TAB", ctrl=True)
        b.frames(150)
        check(b.peek16(syms["sh_runs"]) == runs and not desk(),
              "...CONTROL-TAB inside it switched nothing")
        b.key("RETURN")
        for _ in range(0, 1500, 25):
            b.frames(25)
            if w("r_alerts") == alerts + 1:
                break
        b.frames(200)
        check(w("r_alerts") == alerts + 1 and w("r_inalert") == 0,
              "...RETURN answered the alert")
        check(b.peek16(syms["sh_runs"]) == runs and not desk() and w("r_id") == 1,
              "dropped: A is still running after the alert closed")
        check(ring() == ["M54B", "M54C", "DESK"], f"...the ring as it was: {ring()}")
        arrived(press(), 2, ["M54C", "DESK", "M54A"], "A: CONTROL-TAB, B")
        arrived(press(shift=True), 1, ["M54B", "M54C", "DESK"],
                "B: SHIFT-CONTROL-TAB, back to A")
        print("  -- A: shel_write(SWM_G4SWITCH, 1)")
        runs = b.peek16(syms["sh_runs"])
        leave()
        switched = w("r_switches")
        poke16(b, P("step"), 2)
        arrived(runs, 2, ["M54C", "DESK", "M54A"], "A: SWM_G4SWITCH, B")
        arrived(press(), 3, ["DESK", "M54A", "M54B"], "B: CONTROL-TAB, C")
        arrived(press(shift=True), 2, ["M54C", "DESK", "M54A"],
                "C: SHIFT-CONTROL-TAB, back to B")
        arrived(press(shift=True), 1, ["M54B", "M54C", "DESK"],
                "B: SHIFT-CONTROL-TAB, back to A")
        check(w("r_switches") == switched + 1 and w("r_swret") == 1,
              f"A's shel_write(SWM_G4SWITCH) answered {w('r_swret')} when it "
              f"was resumed")

        # -- each quits ------------------------------------------------------
        def quit_running(want_ring, what):
            runs = b.peek16(syms["sh_runs"])
            poke16(b, P("app_quit"), 1)
            arrived(runs, "DESK", want_ring, what)
            check(b.peek16(syms["sh_lastret"]) == 0, "...main() returned 0")

        quit_running(["M54B", "M54C"], "A quits: the desktop")
        arrived(press(), 2, ["M54C", "DESK"], "desktop: CONTROL-TAB, B")
        quit_running(["M54C"], "B quits: the desktop")
        arrived(press(shift=True), 3, ["DESK"], "desktop: SHIFT-CONTROL-TAB, C")
        quit_running([], "C quits: the desktop")

        after = far_heap(b, syms)
        print(f"  the far heap at the desktop again: {heap_text(after)}")
        # THE SAME BLOCKS, BY LENGTH AND KIND -- not by address.  The shell
        # takes a new park buffer for every program it puts aside and gives
        # one back at every resume (src/aes/shel.c, sh_suspend, sh_run), and
        # the desktop's blocks go wherever there is room while programs
        # hold theirs: so after a round the same blocks can sit elsewhere.
        # A record or a buffer not given back is one block too many.
        def kinds(h):
            # length; the system's or not (the owners are renumbered at
            # every run); the kind and the purge level (src/sys/farmem.h)
            return sorted((n, (o & 0xFF) == 0, (o >> 12) & 0x0F, (o >> 16) & 3)
                          for _, n, o in h.blocks)
        moved = [f"${a:06X}+{n}" for a, n, _ in after.blocks
                 if (a, n) not in [(x, y) for x, y, _ in before.blocks]]
        if moved:
            print(f"    (placed elsewhere this time: {moved})")
        ka, kb = kinds(before), kinds(after)
        check(ka == kb, "nothing left behind: the far heap is the blocks it "
              "was, by length and kind"
              + ("" if ka == kb else
                 f" -- new {[k for k in kb if k not in ka]}, "
                 f"missing {[k for k in ka if k not in kb]}"))
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m54: {'FAIL' if problems else 'PASS'} -- three programs put "
          f"aside and switched among, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
