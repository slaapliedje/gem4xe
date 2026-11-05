"""Phase 125 gate: AES 4's window messages -- the top changes hands.

The G4DOS system floppy with the gate accessory (M50.ACC) and M52.PRG
(src/m52_app.c): two windows, A under B, and a log of every window
message the program is sent.  It answers WM_TOPPED and WM_BOTTOMED as an
AES 4 program does; everything else is done to it.

  1  appl_getinfo says so: WM_UNTOPPED, WM_ONTOP and WM_BOTTOMED among the
     messages, WF_TOP's words, WF_NEWDESK's get and WF_BOTTOM among the
     window modes, and Shift-click-to-bottom among the behaviours; and
     wind_get(WF_NEWDESK) reads back the tree the program set
  2  the program tops A itself: B is told WM_UNTOPPED -- topped over, by
     whoever -- and nobody WM_ONTOP, which topping never sends
  3  the accessory opens a window over A: A is told WM_UNTOPPED; it closes
     it: A is uncovered, WM_ONTOP
  4  a click on B, behind: WM_TOPPED; the program tops it, and A is told
     WM_UNTOPPED
  5  Shift held -- the real key, in POKEY's matrix -- and the top window's
     mover clicked: WM_BOTTOMED; the program answers with WF_BOTTOM, A is
     uncovered and told WM_ONTOP -- the program did it, and is told anyway
     -- and B, sent to the back, is told nothing
  6  Shift held and the window at the back clicked: WM_BOTTOMED, not
     WM_TOPPED; WF_BOTTOM of a window already behind changes no top

MultiTOS's GEMWMLIB.C is the specification: which message depends on how
the top changed, not on who changed it.

    make test-m52
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
from m7_form import CLICK                     # noqa: E402
from m17_desktop import header                # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m52")
ACC = os.path.join(BUILD, "m50_acc.g4a")
APP = os.path.join(BUILD, "m52_app.g4a")
TITLE = b"  Shutdown gate\x00"
WM_TOPPED, WM_UNTOPPED, WM_ONTOP, WM_BOTTOMED = 21, 30, 31, 33
NAMES = {WM_TOPPED: "TOPPED", WM_UNTOPPED: "UNTOPPED", WM_ONTOP: "ONTOP",
         WM_BOTTOMED: "BOTTOMED"}
ACC_OPEN, ACC_CLOSE = 10, 11
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m52.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"), disk,
            ACC, "GEM>M50.ACC", APP, "M52.PRG"]
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    asym = symfile.load(os.path.join(BUILD, "m50_acc.sym"))
    psym = symfile.load(os.path.join(BUILD, "m52_app.sym"))
    alink, plink = header(ACC)[0], header(APP)[0]
    work = tempfile.mkdtemp(prefix="m52-")
    disk = make_disk(work)
    emu = launch(tag="m52", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        near = None
        for slot in range(6):
            title = b.peek24(syms["gl_acctitle"] + 4 * slot)
            if title and bytes(b.memdump(title, len(TITLE))) == TITLE:
                near = title - (asym["acc_title"] - alink)
        if not check(near is not None, "M50.ACC loaded and registered"):
            return 1

        def A(n):
            return asym[n] - alink + near

        runs = b.peek16(syms["sh_runs"])
        t.dclick(t.desk_icon("DISK D1:"))
        t.click(t.gadget(W_FULLER))
        t.dclick(t.item("M52.PRG"))
        for _ in range(0, 3000, 25):
            b.frames(25)
            if b.peek16(syms["sh_runs"]) != runs:
                break
        base = b.peek16(syms["app_near"])

        def P(n):
            return psym[n] - plink + base

        def w(n, k=0):
            return s16(b.peek16(P(n) + 2 * k))

        for _ in range(0, 3000, 25):
            b.frames(25)
            if w("r_ready") == 1:
                break
        if not check(w("r_ready") == 1, "M52.PRG opened its two windows"):
            return 1
        wa, wb = w("r_wh", 0), w("r_wh", 1)
        rb = [w("r_rect", 4 + k) for k in range(4)]

        def log():
            n = w("r_nlog")
            return [(w("r_log", 2 * k), w("r_log", 2 * k + 1)) for k in range(n)]

        def since(mark, what):
            got = log()[mark:]
            print(f"    {what}: " + (", ".join(f"{NAMES.get(m, m)}({h})" for m, h in got)
                                     or "nothing"))
            return got

        def click(xy, shift=False):
            t.go(xy)
            if shift:
                b.key_raw("Z", True, shift=True)
                b.frames(4)
            t.run(CLICK())
            b.frames(10)
            if shift:
                b.key_raw("Z", False, shift=True)
            b.frames(80)

        # 1
        mesg, win = w("r_mesg", 1), [w("r_win", k) for k in range(5)]
        check(mesg & 0x46 == 0x46, f"AES_MESSAGE: WM_UNTOPPED, WM_ONTOP, WM_BOTTOMED "
                                   f"(${mesg & 0xFFFF:04X})")
        check(win[1] & 0x43 == 0x43 and win[3] & 4,
              f"AES_WINDOW: WF_TOP's words, WF_NEWDESK get, WF_BOTTOM; "
              f"Shift-click to the back ({win})")
        nd = [w("r_newdesk", k) & 0xFFFF for k in range(3)]
        want = P("r_desk")
        check(nd == [0, want, 0], f"wind_get(WF_NEWDESK) reads back the tree set, "
                                  f"${want:04X}, root 0 ({[hex(v) for v in nd]})")

        # 2
        mark = w("r_nlog")
        poke16(b, P("step"), 1)
        b.frames(60)
        got = since(mark, "A topped by the program")
        check(got == [(WM_UNTOPPED, wb)],
              "B is told WM_UNTOPPED, and nobody WM_ONTOP: topping never sends it")

        # 3
        mark = w("r_nlog")
        poke16(b, A("acc_req"), ACC_OPEN)
        b.frames(80)
        got = since(mark, "the accessory's window over it")
        check(got == [(WM_UNTOPPED, wa)], "A is told WM_UNTOPPED")
        mark = w("r_nlog")
        poke16(b, A("acc_req"), ACC_CLOSE)
        b.frames(80)
        got = since(mark, "...and closed again")
        check(got == [(WM_ONTOP, wa)], "A is uncovered: WM_ONTOP")

        # 4  B's title, where A does not cover it
        bxy = (rb[0] + rb[2] - 30, rb[1] + 4)
        mark = w("r_nlog")
        click(bxy)
        got = since(mark, "B clicked, behind")
        check(got == [(WM_TOPPED, wb), (WM_UNTOPPED, wa)],
              "WM_TOPPED for B; topped, and A told WM_UNTOPPED")
        check(b.peek16(syms["gl_wtop"]) == wb, "...and B is the top")

        # 5
        mark = w("r_nlog")
        click(bxy, shift=True)
        got = since(mark, "Shift and B's mover, B on top")
        check(got == [(WM_BOTTOMED, wb), (WM_ONTOP, wa)],
              "WM_BOTTOMED for the top window; answered with WF_BOTTOM, A is "
              "uncovered and told WM_ONTOP, B told nothing")
        top = b.peek16(syms["gl_wtop"])
        check(top == wa, f"...and A is the top ({top})")

        # 6
        mark = w("r_nlog")
        click(bxy, shift=True)
        got = since(mark, "Shift and B, at the back")
        check(got == [(WM_BOTTOMED, wb)],
              "WM_BOTTOMED for a window behind, not WM_TOPPED, and no top changed")
        b.screenshot(os.path.join(OUT, "m52.png"))

        poke16(b, P("app_quit"), 1)
        b.frames(200)
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m52: {'FAIL' if problems else 'PASS'} -- AES 4's window messages, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
