"""Phase 127 gate: a program put aside and resumed (switcher step 2).

The G4DOS system floppy with M53.PRG (src/m53_app.c): one window, its own
file kept open, a count in its near data that goes up every turn.  Three
times over:

  1  the gate asks it to call shel_write(SWM_G4SUSPEND); the desktop comes
     back -- the shell ran the next thing, and the program did not end
  2  M53.PRG is started again from the desktop: it is RESUMED, not loaded
     -- the call answers 1, its count went on from where it was (a load
     starts it at 0 and forgets how many resumes there were), its file
     still reads, its window is the top one again, and it was sent a
     WM_REDRAW for it and a WM_ONTOP

then it quits like any program, and the desktop comes back for good.

    make test-m53
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
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from m17_desktop import header                # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m53")
APP = os.path.join(BUILD, "m53_app.g4a")
WM_REDRAW, WM_ONTOP = 20, 31
ROUNDS = 3
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m53.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"), disk,
            APP, "M53.PRG"]
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    psym = symfile.load(os.path.join(BUILD, "m53_app.sym"))
    plink = header(APP)[0]
    head = open(APP, "rb").read(2)
    work = tempfile.mkdtemp(prefix="m53-")
    disk = make_disk(work)
    emu = launch(tag="m53", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)

        def start():
            """M53.PRG double-clicked in the desktop's D1: window, opened
            first if the desktop came back without it."""
            try:
                xy = t.item("M53.PRG")
            except KeyError:
                t.dclick(t.desk_icon("DISK D1:"))
                t.click(t.gadget(W_FULLER))
                xy = t.item("M53.PRG")
            t.dclick(xy)

        def runs_past(n, limit=3000):
            for _ in range(0, limit, 25):
                b.frames(25)
                if b.peek16(syms["sh_runs"]) > n:
                    return True
            return False

        runs = b.peek16(syms["sh_runs"])
        start()
        if not check(runs_past(runs), "M53.PRG started"):
            return 1
        base = b.peek16(syms["app_near"])

        def P(n):
            return psym[n] - plink + base

        def w(n, k=0):
            return s16(b.peek16(P(n) + 2 * k))

        for _ in range(0, 3000, 25):
            b.frames(25)
            if w("r_ready") == 1:
                break
        if not check(w("r_ready") == 1, f"its window opened (near base ${base:04X})"):
            return 1
        wh = w("r_wh")
        check(w("r_fh") > 0, f"its own file is open: handle {w('r_fh')}")

        for k in range(ROUNDS):
            print(f"  -- round {k + 1}")
            b.frames(60)
            count = b.peek16(P("r_count"))
            mark = w("r_nlog")
            runs = b.peek16(syms["sh_runs"])
            poke16(b, P("step"), 1)
            if not check(runs_past(runs), "put aside: the desktop came back "
                                          f"(sh_runs {runs} -> {b.peek16(syms['sh_runs'])})"):
                return 1
            check(b.peek16(syms["sh_lastret"]) == 0 and b.peek(syms["sh_parked"]) == 0,
                  "...and nothing ended")
            t.settle()
            b.screenshot(os.path.join(OUT, f"desk-{k + 1}.png"))
            runs = b.peek16(syms["sh_runs"])
            start()
            if not check(runs_past(runs), "M53.PRG started again"):
                return 1
            for _ in range(0, 1500, 25):
                b.frames(25)
                if w("r_resumes") == k + 1:
                    break
            check(b.peek16(syms["app_near"]) == base,
                  f"its near region where it was, ${base:04X}")
            check(w("r_resumes") == k + 1 and w("r_ret", k) == 1,
                  f"RESUMED, not loaded: the call answered {w('r_ret', k)}, "
                  f"{w('r_resumes')} resume(s)")
            now = b.peek16(P("r_count"))
            check(now >= count, f"its count went on: {count} before, {now} now")
            got = bytes(b.memdump(P("r_head") + 2 * k, 2))
            check(w("r_read", k) == 2 and got == head,
                  f"its file still reads: {w('r_read', k)} bytes, {got.hex()}")
            log = [(w("r_log", 2 * i), w("r_log", 2 * i + 1))
                   for i in range(mark, w("r_nlog"))]
            print(f"    told: {log}")
            check((WM_REDRAW, wh) in log, "a WM_REDRAW for its window")
            check((WM_ONTOP, wh) in log, "...and WM_ONTOP")
            check(b.peek16(syms["gl_wtop"]) == wh, "its window is the top one")
            b.screenshot(os.path.join(OUT, f"resumed-{k + 1}.png"))

        runs = b.peek16(syms["sh_runs"])
        poke16(b, P("app_quit"), 1)
        check(runs_past(runs), "it quit, and the desktop came back")
        check(b.peek16(syms["sh_lastret"]) == 0, "main() returned 0")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m53: {'FAIL' if problems else 'PASS'} -- a program put aside "
          f"and resumed, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
