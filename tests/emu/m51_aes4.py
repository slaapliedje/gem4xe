"""Phase 124 gate: AES 4.0, answered from inside a program.

The G4DOS system floppy with the phase 123 gate accessory (M50.ACC) in the
system's folder and the gate's program, M51.PRG (src/m51_app.c), in the
root beside two resource files: M51E.RSC (EDIT.RSC: plain, its tree 0 a
menu bar) and M51T.RSC (test.rsc: colour icons).  M51.PRG makes the calls
a program makes on seeing AES 4.0 and keeps every answer in a global; this
reads them by symbol once it says it is done.

  1  global[]: 0x0400; one application at a time (1, not MultiTOS's -1);
     the caller's id -- an accessory's own too, which was 0; [13] and [14]
     the character height
  2  appl_find: NULL is the caller; $FFFF|id and $FFFE|id convert (the
     same number, no MiNT); a nobody is -1
  3  appl_search lists the program (APP_APPLICATION, not the shell) and
     the accessory (APP_ACCESSORY), then says no more
  4  menu_register from the program takes no Desk slot (the accessory's is
     still the only one); REG_NEWNAME renames it for appl_find
  5  appl_getinfo says so: process 0,1,1,1; menu_bar's inquiry; WF_TOP's
     words and WF_BOTTOM; AP_TERM and the shutdown; 64 is not answered,
     and gem4xe's own subject has moved to AES_CPX
  6  rsrc_rcfix: EDIT.RSC from the program's memory, its menu bar the same
     width as rsrc_load makes it; a third resource and a file with colour
     icons are refused; rsrc_free gives nothing back
  7  menu_bar(0, MENU_INQUIRE): -1, the program's own id while its bar is
     up, -1 again
  8  WF_TOP: the top window, its owner, the window below
  9  an opcode not served answers 0, not -1

    make test-m51
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
OUT = os.path.join(BUILD, "shots", "m51")
ACC = os.path.join(BUILD, "m50_acc.g4a")
APP = os.path.join(BUILD, "m51_app.g4a")
TITLE = b"  Shutdown gate\x00"
APP_APPLICATION, APP_ACCESSORY, APP_SHELL = 2, 4, 8
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def make_disk(work):
    disk = os.path.join(work, "m51.atr")
    shutil.copy(os.path.join(BUILD, "gem-sys.atr"), disk)
    args = [sys.executable, os.path.join(ROOT, "tools", "sdk", "install.py"), disk,
            ACC, "GEM>M50.ACC", APP, "M51.PRG",
            os.path.join(BUILD, "edit.rsc"), "M51E.RSC",
            os.path.join(BUILD, "test.rsc"), "M51T.RSC"]
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"install.py: {r.stderr.strip()}")
    return disk


def main():
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    asym = symfile.load(os.path.join(BUILD, "m50_acc.sym"))
    psym = symfile.load(os.path.join(BUILD, "m51_app.sym"))
    alink, plink = header(ACC)[0], header(APP)[0]
    work = tempfile.mkdtemp(prefix="m51-")
    disk = make_disk(work)
    emu = launch(tag="m51", memsize="1088K", extra_args=["--disk", disk])
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
        acc_g2 = s16(b.peek16(asym["acc_g2"] - alink + near))
        check(acc_g2 == 1, f"an accessory's global[2] is its own id, 1 ({acc_g2})")

        runs = b.peek16(syms["sh_runs"])
        t.dclick(t.desk_icon("DISK D1:"))
        t.click(t.gadget(W_FULLER))
        t.dclick(t.item("M51.PRG"))
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
            if w("r_done") == 1:
                break
        if not check(w("r_done") == 1, "M51.PRG ran its calls to the end"):
            return 1
        b.screenshot(os.path.join(OUT, "m51.png"))

        # 1
        g = [w("r_global", k) for k in range(15)]
        hchar = b.peek16(syms["gl_hchar"])
        check(g[0] == 0x0400, f"global[0] is AES 4.0 (${g[0] & 0xFFFF:04X})")
        check(g[1] == 1, f"global[1]: one application at a time ({g[1]})")
        check(g[2] == 0, f"global[2]: the program's id, 0 ({g[2]})")
        check(g[13] == hchar and g[14] == hchar,
              f"global[13], [14]: the character height, {hchar} ({g[13]}, {g[14]})")
        # 2
        f = [w("r_find", k) for k in range(7)]
        check(f == [0, 0, 1, 1, 0, -1, -1],
              f"appl_find: NULL 0, its name 0, the accessory 1, $FFFF|1 1, "
              f"$FFFE|0 0, $FFFF|5 -1, a nobody -1 ({f})")
        # 3
        n = w("r_srch")
        found = []
        for k in range(min(n, 4)):
            name = bytes(b.memdump(P("r_names") + 10 * k, 9)).split(b"\0")[0]
            found.append((name.decode("latin-1"), w("r_types", k), w("r_ids", k)))
        check(found == [("M51     ", APP_APPLICATION, 0), ("M50     ", APP_ACCESSORY, 1)],
              f"appl_search: the program, an application, and the accessory, "
              f"then no more ({found})")
        # 4
        check(w("r_reg") == 6, f"menu_register from the program: a menu id no "
                               f"accessory has, 6 ({w('r_reg')})")
        accreg = b.peek16(syms["gl_accreg"])
        check(accreg == 1, f"...and no Desk slot: the accessory's is still the only "
                           f"one ({accreg})")
        check(w("r_newname") == 1 and w("r_findnew") == 0,
              f"REG_NEWNAME renames it for appl_find ({w('r_newname')}, "
              f"{w('r_findnew')})")
        # 5
        info = [[w("r_info", r * 5 + k) for k in range(5)] for r in range(6)]
        check(info[0][2:5] == [1, 1, 1], f"AES_PROCESS: appl_find converts, "
                                         f"appl_search, rsrc_rcfix ({info[0]})")
        check(info[1][3] == 1, f"AES_INQUIRE: menu_bar takes -1 ({info[1]})")
        check(info[2][1] & 0x41 == 0x41, f"AES_WINDOW: WF_TOP's words and WF_BOTTOM "
                                         f"(${info[2][1] & 0xFFFF:04X})")
        check(info[3][1] & 0x18 == 0x18, f"AES_MESSAGE: AP_TERM and the shutdown "
                                         f"(${info[3][1] & 0xFFFF:04X})")
        check(info[4] == [0, 0, 0, 0, 0], f"64, gemlib's AES_EXTENDED, is not "
                                          f"answered ({info[4]})")
        check(info[5][0] != 0, f"AES_CPX, gem4xe's own subject, is ({info[5]})")
        # 6
        rc = [w("r_rcfix", k) for k in range(3)]
        check(rc == [1, 0, 0], f"rsrc_rcfix: EDIT.RSC done 1, a third refused 0, "
                               f"colour icons refused 0 ({rc})")
        wd = [w("r_widths", k) for k in range(2)]
        check(wd[0] > 0 and wd[0] == wd[1],
              f"...its menu bar as wide as rsrc_load makes it ({wd})")
        check(w("r_free") == 1, f"rsrc_free of it: 1 ({w('r_free')})")
        # 7
        bar = [w("r_bar", k) for k in range(3)]
        check(bar == [-1, 0, -1], f"menu_bar(0, MENU_INQUIRE): none, its own, "
                                  f"none ({bar})")
        # 8
        wh = [w("r_wh", k) for k in range(2)]
        top = [w("r_top", k) for k in range(3)]
        check(top == [wh[1], 0, wh[0]],
              f"WF_TOP: the top window {wh[1]}, its owner 0, the one below "
              f"{wh[0]} ({top})")
        # 9
        check(w("r_bad") == 0, f"an opcode not served answers 0 ({w('r_bad')})")

        poke16(b, P("app_quit"), 1)
        for _ in range(0, 3000, 25):
            b.frames(25)
            if b.peek16(syms["sh_runs"]) != runs + 1:
                break
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"test-m51: {'FAIL' if problems else 'PASS'} -- AES 4.0, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
