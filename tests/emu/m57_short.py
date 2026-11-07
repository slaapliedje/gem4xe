"""Phase 132 gate: what was short (switcher step 5) -- each case forced,
and each refused with an alert that says what, never a half-switched
machine.

ON THE RAPIDUS, with M53.PRG (src/m53_app.c) as M54A to M54G and M50.ACC
with a resource of its own (M50.RSC, a copy of EDIT.RSC):

  1  six programs started and put aside; a seventh is refused: the
     TOOMANY alert on the bare desk, then the desktop, the six still there
  2  M50.ACC loads its resource at run time, into the pool where the
     programs aside keep their near regions: resuming one is refused, the
     NORESUME alert, the desktop; the resource freed, it resumes

ON A PLAIN 65C816 WITH A MEGABYTE (cpu816=15), with M54A:

  3  the program takes every FREE byte of far memory (step 6), leaving
     the dormant desktop: CONTROL-TAB is refused with the NOASIDE alert --
     the record is not made at the dormant desktop's cost (far_keep1) --
     the program is still in front and the desktop still kept
  4  it makes the heap purge the desktop and takes that too (step 8), then
     gives back 12 KB (step 7) -- room to put it aside, none to load the
     desktop again: put aside, the desktop cannot be loaded, and the
     program is resumed in its place with the NODESK alert; GEM goes on
  5  it quits; its memory freed, the desktop loads

    make test-m57
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
from langrsc import STRINGS                   # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m57")
APP = os.path.join(BUILD, "m53_app.g4a")
ACC = os.path.join(BUILD, "m50_acc.g4a")
ACC_TITLE = b"  Shutdown gate"            # src/m50_acc.c
ACC_RSRC, ACC_UNRSRC = 12, 13
SH_CDIRLEN, SU_NAME, SH_DESKREC = 114, 8, 1   # src/aes/shel.c
SEVEN = ["M54A", "M54B", "M54C", "M54D", "M54E", "M54F", "M54G"]
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work, name, files):
    disk = os.path.join(work, name)
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    for src, dest in files:
        args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"),
                disk, src, dest]
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


class Machine:
    """One emulator, the desktop up, and the helpers every case uses."""

    def __init__(self, b, syms, psym, plink):
        self.b, self.syms, self.psym, self.plink = b, syms, psym, plink
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        self.t = Tour(b, syms, OUT)
        b.frames(10)

    def P(self, n):
        return self.psym[n] - self.plink + self.b.peek16(self.syms["app_near"])

    def w(self, n, k=0):
        return s16(self.b.peek16(self.P(n) + 2 * k))

    def poke(self, n, v):
        poke16(self.b, self.P(n), v)

    def desk(self):
        return self.b.peek16(self.syms["sh_deskrun"]) != 0

    def runs(self):
        return self.b.peek16(self.syms["sh_runs"])

    def ring(self):
        b = self.b
        at = b.peek24(self.syms["sh_cdir_far"]) + SH_CDIRLEN
        out = []
        for i in range(b.peek16(at)):
            e = int.from_bytes(bytes(b.memdump(at + 2 + 4 * i, 4)), "little")
            out.append("DESK" if e == SH_DESKREC else
                       bytes(b.memdump(e + SU_NAME, 8)).decode().strip())
        return out

    def until(self, pred, limit=3000):
        for _ in range(0, limit, 25):
            self.b.frames(25)
            if pred():
                return True
        return False

    def settle_on(self, pred, limit=1500):
        self.until(pred, limit)
        self.t.settle()
        return pred()

    def double_click(self, name):
        """NAME.PRG double-clicked in D1:'s window, which is opened first if
        it is not up.  On the plain 65C816 the drive is read at 1.79 MHz,
        and settle() -- no call for thirty frames -- returns while the
        desktop is still in the DOS: so the window and its item are waited
        for, not assumed."""
        t, b, syms = self.t, self.b, self.syms

        def found():
            try:
                return t.item(f"{name}.PRG")
            except KeyError:
                return None
        def drive():
            try:
                return t.desk_icon("DISK D1:")
            except KeyError:
                return None
        def window():                   # signed: no window is -1
            return s16(b.peek16(syms["gl_wtop"])) > 0
        xy = found()
        if xy is None:
            self.until(lambda: drive() is not None, 3000)
            # A double-click the slow machine is too busy to see as one is
            # tried again, not taken as a failure of the system's.
            for _ in range(3):
                t.settle()
                t.dclick(drive())
                if self.until(window, 1500):
                    break
            b.frames(400)               # the directory read, not yet drawn
            t.settle()
            t.click(t.gadget(W_FULLER))
            b.frames(600)               # fulled and drawn again, items moved
            t.settle()
            self.until(lambda: found() is not None, 3000)
            xy = found()
        t.dclick(xy)

    def start(self, name, ident):
        n = self.runs()
        self.double_click(name)
        if not (check(self.until(lambda: self.runs() > n), f"{name}.PRG started")
                and check(self.settle_on(lambda: not self.desk()
                                         and self.w("r_ready") == 1),
                          "...its window opened")):
            raise SystemExit(1)
        self.poke("r_id", ident)

    def key_switch(self):
        self.b.key("TAB", ctrl=True)

    def alert_says(self, name):
        """The alert up is LANG.RSC's `name`: lang_str's one buffer holds
        what fm_alert was given (src/aes/lang.c), and nothing else asks for
        a string while an alert is up."""
        got = bytes(self.b.memdump(self.syms["lang_buf"], 132)).split(b"\0")[0]
        want = dict(STRINGS)[name].encode("latin-1")
        return check(got == want, f"...and it is {name}: {got[:40]!r}...")

    def in_poll_alert(self):
        """sh_tell's alert: ev_appwait is put down for its length."""
        return self.b.peek(self.syms["ev_appwait"]) == 0


def rapidus(work, syms, psym, plink, asym, alink):
    disk = make_disk(work, "m57r.atr",
                     [(APP, "M53.PRG")] + [(APP, f"{n}.PRG") for n in SEVEN]
                     + [(ACC, "GEM>M50.ACC"),
                        (os.path.join(BUILD, "edit.rsc"), "GEM>M50.RSC")])
    emu = launch(tag="m57r", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        m = Machine(b, syms, psym, plink)
        near = None
        for slot in range(6):
            title = b.peek24(syms["gl_acctitle"] + 4 * slot)
            if title and bytes(b.memdump(title, len(ACC_TITLE))) == ACC_TITLE:
                near = title - (asym["acc_title"] - alink)
        if not check(near is not None, "M50.ACC loaded and registered"):
            return

        def A(n):
            return s16(b.peek16(asym[n] - alink + near))

        # 1 -- six aside, a seventh refused ------------------------------------
        print("  -- 1: six programs aside, then a seventh")
        for i, name in enumerate(SEVEN[:6]):
            m.start(name, i + 1)
            n = m.runs()
            m.key_switch()
            check(m.until(lambda: m.runs() > n) and m.settle_on(m.desk),
                  f"...{name} put aside")
        check(sorted(m.ring()) == sorted(SEVEN[:6]), f"six aside: {m.ring()}")
        n = m.runs()
        m.double_click(SEVEN[6])
        check(m.until(lambda: not m.desk(), 1500), "the desktop ended to start "
                                                    "the seventh")
        b.frames(150)
        check(not m.desk() and m.runs() == n, "...which was not loaded: the "
                                              "alert is up on the bare desk")
        m.alert_says("TOOMANY")
        b.screenshot(os.path.join(OUT, "1-toomany.png"))
        b.key("RETURN")
        check(m.until(lambda: m.runs() > n) and m.settle_on(m.desk),
              "...answered: the desktop again")
        check(sorted(m.ring()) == sorted(SEVEN[:6]),
              f"...the six still loaded, not the seventh: {m.ring()}")

        # 2 -- a pool place taken -------------------------------------------
        print("  -- 2: M50.ACC's resource in the pool, then a resume")
        poke16(b, asym["acc_req"] - alink + near, ACC_RSRC)
        check(m.until(lambda: A("acc_rsc") != 0, 600),
              f"M50.ACC loaded its resource at run time ({A('acc_rsc')})")
        first = m.ring()[0]
        n = m.runs()
        m.key_switch()
        check(m.until(lambda: not m.desk(), 1500), "CONTROL-TAB: the desktop ended")
        b.frames(150)
        check(not m.desk() and m.runs() == n,
              f"...{first} was not resumed: the alert is up")
        m.alert_says("NORESUME")
        b.screenshot(os.path.join(OUT, "2-noresume.png"))
        b.key("RETURN")
        check(m.until(lambda: m.runs() > n) and m.settle_on(m.desk),
              "...answered: the desktop again")
        check(first in m.ring(), f"...{first} still aside: {m.ring()}")
        poke16(b, asym["acc_req"] - alink + near, ACC_UNRSRC)
        check(m.until(lambda: A("acc_rsc") == 0, 600), "M50.ACC freed it")
        n = m.runs()
        m.key_switch()
        check(m.until(lambda: m.runs() > n)
              and m.settle_on(lambda: not m.desk() and m.w("r_ready") == 1),
              f"CONTROL-TAB: {first} is resumed now (id {m.w('r_id')})")
    finally:
        emu.stop()


def small(work, syms, psym, plink):
    disk = make_disk(work, "m57s.atr", [(APP, "M53.PRG"), (APP, "M54A.PRG")])
    emu = launch(tag="m57s", memsize="1088K", rapidus=False, cpu816=15,
                 extra_args=["--disk", disk])
    b = emu.bridge
    try:
        m = Machine(b, syms, psym, plink)
        m.start("M54A", 1)

        # 3 -- no room to put it aside -----------------------------------------
        print("  -- 3: every free byte of far memory taken, then CONTROL-TAB")
        m.poke("step", 6)
        check(m.until(lambda: m.w("step") == 0 and m.w("r_filled") > 0, 3000),
              f"the program took far memory: {m.w('r_filled')} block(s)")
        check(b.peek(syms["sh_dorm"]) == 1, "...the dormant desktop still kept")
        b.frames(50)
        n = m.runs()
        m.key_switch()
        b.frames(100)
        check(m.in_poll_alert() and not m.desk() and m.runs() == n,
              "CONTROL-TAB refused: the alert is up, the program in front")
        m.alert_says("NOASIDE")
        b.screenshot(os.path.join(OUT, "3-noaside.png"))
        b.key("RETURN")
        b.frames(150)
        check(not m.in_poll_alert() and not m.desk() and m.runs() == n
              and m.w("r_id") == 1 and m.ring() == ["DESK"],
              f"...answered: still the program, the ring {m.ring()}")
        check(b.peek(syms["sh_dorm"]) == 1,
              "...and the dormant desktop was not purged to make room")

        # 4 -- room to put it aside, none for the desktop -----------------------
        print("  -- 4: the desktop purged too, 12 KB given back, CONTROL-TAB")
        m.poke("step", 8)
        check(m.until(lambda: m.w("step") == 0, 3000) and b.peek(syms["sh_dorm"]) == 0,
              f"the heap purged the dormant desktop ({m.w('r_filled')} blocks)")
        m.poke("step", 7)
        check(m.until(lambda: m.w("step") == 0, 600), "the program gave 12 KB back")
        count = b.peek16(m.P("r_count"))
        n = m.runs()
        m.key_switch()
        b.frames(300)
        check(not m.desk() and m.runs() == n,
              "put aside, the desktop could not be loaded: the alert is up")
        m.alert_says("NODESK")
        b.screenshot(os.path.join(OUT, "4-nodesk.png"))
        b.key("RETURN")
        check(m.until(lambda: m.runs() > n)
              and m.settle_on(lambda: not m.desk() and m.w("r_ready") == 1),
              "...answered: the program was resumed in the desktop's place")
        check(m.w("r_id") == 1 and b.peek16(m.P("r_count")) >= count,
              f"...the same program, its count going on "
              f"({count} -> {b.peek16(m.P('r_count'))})")
        check(m.ring() == ["DESK"], f"...the desktop in the ring: {m.ring()}")

        # 5 -- it quits; the desktop loads -----------------------------------
        print("  -- 5: the program quits")
        n = m.runs()
        m.poke("app_quit", 1)
        check(m.until(lambda: m.runs() > n, 3000) and m.settle_on(m.desk),
              "its memory freed, the desktop loads")
    finally:
        emu.stop()


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    psym = symfile.load(os.path.join(BUILD, "m53_app.sym"))
    plink = header(APP)[0]
    asym = symfile.load(os.path.join(BUILD, "m50_acc.sym"))
    alink = header(ACC)[0]
    work = tempfile.mkdtemp(prefix="m57-")
    try:
        rapidus(work, syms, psym, plink, asym, alink)
        small(work, syms, psym, plink)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m57: {'FAIL' if problems else 'PASS'} -- what was short, each "
          f"case forced, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
