"""Phase 123 gate: AES 4's shutdown, asked for and answered.

The G4DOS system floppy, build/gem-sys.atr, with the gate's pair added by
the SDK's own install.py: M50.ACC in the system's folder, and one program
(src/m50_app.c) four times in the root, its name saying how it answers
AP_TERM.  The accessory is the one that asks -- shel_write(SWM_SHUTDOWN)
-- when the gate writes its acc_req; everything checked is read out of the
two programs and the AES by symbol.

  1  appl_getinfo says so: shell modes up to 10, AP_TERM and the shutdown
     messages (bits 3 and 4)
  2  M50U never registered: the shutdown is REFUSED, 0, and nothing is
     sent to it -- a program that did not say it understands AP_TERM may
     be holding work it would lose
  3  M50F refuses: AP_TERM arrives with msg[5] = AP_TERM, its AP_TFAIL is
     taken, and the accessory is told SHUT_COMPLETED 0, who (process 0)
     and the code (77); the shutdown is over, so an abort now answers 0.
     Asked again, it ends, and SHUT_COMPLETED says 1
  4  M50S never answers: asking again while it is pending answers 1 (the
     same caller), the caller may abort it (1), and only once (then 0);
     when the program ends later, nothing is sent
  5  M50T ends on AP_TERM, and SHUT_COMPLETED says 1
  6  the desktop registers too, and AP_TERM is Quit: a shutdown asked for
     with the desktop up ends GEM, and G4DOS's shell is back

    make test-m50
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
from m14_sparta import screen                 # noqa: E402
from m17_desktop import header                # noqa: E402

BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shots", "m50")
ACC, APP = (os.path.join(BUILD, f"m50_{n}.g4a") for n in ("acc", "app"))
TITLE = b"  Shutdown gate\x00"
AP_TERM, AP_TFAIL, SHUT_COMPLETED = 50, 51, 60
SD_PARTIAL, ACC_ABORT = 1, 3
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m50.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"), disk,
            ACC, "GEM>M50.ACC"]
    for k in "UFTS":
        args += [APP, f"M50{k}.PRG"]
    # tools/sdk/install.py imports atr from beside it, as it is in the
    # SDK; in this tree atr.py is in tools/ (tests/host/test_kit_install.py)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    asym = symfile.load(os.path.join(BUILD, "m50_acc.sym"))
    psym = symfile.load(os.path.join(BUILD, "m50_app.sym"))
    alink = header(ACC)[0]
    plink = header(APP)[0]
    work = tempfile.mkdtemp(prefix="m50-")
    disk = make_disk(work)
    emu = launch(tag="m50", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)

        # the accessory, found by the title the AES holds for it
        near = None
        for slot in range(6):
            title = b.peek24(syms["gl_acctitle"] + 4 * slot)
            if title and bytes(b.memdump(title, len(TITLE))) == TITLE:
                near = title - (asym["acc_title"] - alink)
                break
        if not check(near is not None, "M50.ACC loaded and registered its title"):
            return 1

        def A(n):
            return asym[n] - alink + near

        def acc(n, k=0):
            return s16(b.peek16(A(n) + 2 * k))

        def ask(how, frames=60):
            asked = acc("acc_asked")
            poke16(b, A("acc_req"), how)
            for _ in range(0, 1200, 10):
                b.frames(10)
                if acc("acc_asked") != asked:
                    break
            b.frames(frames)
            return acc("acc_ret")

        def run(name):
            """Double-click the program in D1:'s window; its variables once
            it is ticking, or None."""
            runs = b.peek16(syms["sh_runs"])
            try:
                at = t.item(name)
            except KeyError:
                t.dclick(t.desk_icon("DISK D1:"))
                t.click(t.gadget(W_FULLER))
                at = t.item(name)
            t.dclick(at)
            for _ in range(0, 3000, 25):
                b.frames(25)
                if b.peek16(syms["sh_runs"]) != runs:
                    break
            base = b.peek16(syms["app_near"])

            def P(n):
                return psym[n] - plink + base
            for _ in range(0, 3000, 25):
                b.frames(25)
                if b.peek16(P("app_ticks")) >= 2:
                    return P
            return None

        def app(P, n, k=0):
            return s16(b.peek16(P(n) + 2 * k))

        def back(what, runs=None):
            """The program ends, the desktop runs again -- counted from
            `runs`, taken BEFORE whatever ended it: a program that ends on
            AP_TERM is gone, and the desktop back, before ask() returns."""
            if runs is None:
                runs = b.peek16(syms["sh_runs"])
            for _ in range(0, 4000, 25):
                b.frames(25)
                if b.peek16(syms["sh_runs"]) != runs:
                    b.frames(200)
                    t.settle()
                    return True
            return check(False, f"{what}: the desktop came back")

        # 1-2: M50U, never registered
        P = run("M50U.PRG")
        if not check(P is not None, "M50U.PRG runs"):
            return 1
        sh = [app(P, "app_shell", k) for k in range(4)]
        check(sh[:3] == [10, 1, 1], f"appl_getinfo(AES_SHELL): modes to 10, "
                                    f"0 cancels, 1 at exit ({sh})")
        mesg = app(P, "app_mesg")
        check(mesg & 0x18 == 0x18, f"appl_getinfo(AES_MESSAGE): AP_TERM and the "
                                   f"shutdown messages, bits 3 and 4 (${mesg:04X})")
        check(app(P, "app_reg") == -1 and chr(app(P, "app_mode")) == "U",
              "M50U chose its way by its name, and did not register")
        r = ask(SD_PARTIAL)
        check(r == 0, f"a shutdown with an unregistered program running is "
                      f"refused, 0 ({r})")
        ticks = app(P, "app_ticks")
        b.frames(120)
        check(app(P, "app_terms") == 0 and app(P, "app_ticks") > ticks,
              "...nothing is sent to it, and it runs on")
        check(acc("acc_shut") == 0, "...and no SHUT_COMPLETED")
        poke16(b, P("app_quit"), 1)
        back("M50U")

        # 3: M50F refuses once, then ends
        P = run("M50F.PRG")
        if not check(P is not None, "M50F.PRG runs"):
            return 1
        check(app(P, "app_reg") == 1, "M50F registered NM_APTERM: 1")
        r = ask(SD_PARTIAL, 120)
        check(r == 1, f"the shutdown is accepted, 1 ({r})")
        last = [app(P, "app_last", k) for k in range(8)]
        check(app(P, "app_terms") == 1 and last[0] == AP_TERM and last[5] == AP_TERM,
              f"AP_TERM arrived, msg[5] the reason, AP_TERM ({last})")
        check(app(P, "app_fail") == 1, "its AP_TFAIL was taken: shel_write "
                                       "(SWM_AESMSG) answered 1")
        msg = [acc("acc_shutmsg", k) for k in range(8)]
        check(acc("acc_shut") == 1 and msg[0] == SHUT_COMPLETED
              and msg[3:6] == [0, 0, 77],
              f"the accessory is told SHUT_COMPLETED 0: process 0 refused, "
              f"code 77 ({msg})")
        r = ask(ACC_ABORT)
        check(r == 0, f"the refusal ended the shutdown: an abort now answers 0 ({r})")
        runs = b.peek16(syms["sh_runs"])
        r = ask(SD_PARTIAL, 30)
        check(r == 1, f"asked again, accepted ({r})")
        back("M50F, asked a second time", runs)
        msg = [acc("acc_shutmsg", k) for k in range(8)]
        check(acc("acc_shut") == 2 and msg[3] == 1,
              f"...it ended, and SHUT_COMPLETED says 1 ({msg})")

        # 4: M50S never answers: pending, asked again, aborted
        P = run("M50S.PRG")
        if not check(P is not None, "M50S.PRG runs"):
            return 1
        r = ask(SD_PARTIAL, 120)
        check(r == 1 and app(P, "app_terms") == 1,
              f"M50S is sent AP_TERM and says nothing ({r})")
        r = ask(SD_PARTIAL)
        check(r == 1, f"the same caller asking again while it is pending: 1 ({r})")
        r = ask(ACC_ABORT)
        check(r == 1, f"...and it may abort its own shutdown: 1 ({r})")
        r = ask(ACC_ABORT)
        check(r == 0, f"...once: aborted, there is nothing to abort ({r})")
        shut = acc("acc_shut")
        poke16(b, P("app_quit"), 1)
        back("M50S")
        check(acc("acc_shut") == shut, "an aborted shutdown sends nothing when the "
                                       "program ends later")

        # 5: M50T ends on AP_TERM
        P = run("M50T.PRG")
        if not check(P is not None, "M50T.PRG runs"):
            return 1
        shut = acc("acc_shut")
        runs = b.peek16(syms["sh_runs"])
        r = ask(SD_PARTIAL, 0)
        check(r == 1, f"the shutdown is accepted ({r})")
        back("M50T", runs)
        msg = [acc("acc_shutmsg", k) for k in range(8)]
        check(acc("acc_shut") == shut + 1 and msg[0] == SHUT_COMPLETED and msg[3] == 1,
              f"M50T ended on AP_TERM, and SHUT_COMPLETED says 1 ({msg})")

        # 6: the desktop: AP_TERM is Quit, and GEM ends
        # sh_shutdone is GEM's memory, and once GEM has ended it is the
        # DOS's: it is watched WHILE the shutdown runs, a frame at a time,
        # not read afterwards.
        done = b.peek16(syms["sh_shutdone"])
        poke16(b, A("acc_req"), SD_PARTIAL)
        seen, most = False, done
        for _ in range(0, 6000):
            b.frames(1)
            if not seen:
                v = b.peek16(syms["sh_shutdone"])
                if v == done + 1:
                    most = v
                    seen = True
        ls = [ln.strip() for ln in screen(b) if ln.strip()]
        check(bool(ls) and ls[-1].endswith("$"),
              f"a shutdown with the desktop up ends it, and GEM, and G4DOS's "
              f"shell is back ({ls[-1] if ls else 'nothing on the screen'})")
        check(most == done + 1, f"...with its SHUT_COMPLETED sent as the desktop "
                                f"ended (sh_shutdone {done} -> {most})")
        b.screenshot(os.path.join(OUT, "shell.png"))
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m50: {'FAIL' if problems else 'PASS'} -- AES 4's shutdown, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
