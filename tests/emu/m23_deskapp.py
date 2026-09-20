#!/usr/bin/env python3
"""Phase 29 gate: an accessory opened from a folder, and used.

The path a person actually takes, which no gate covered before: the real
desktop, at the mouse, into a FOLDER, and an application launched from
inside it that then WAITS FOR THE MOUSE ITSELF.

    double-click drive A      ->  a window on A:\\*.*
    the fuller                ->  it grows to the desk, every item shown
    double-click APPS         ->  do_fopen: the same window, on A:\\APPS\\*.*
    double-click CALC.G4A     ->  do_aopen: shel_write, the desktop returns,
                                  the shell loads the calculator
    a key on the panel        ->  the calculator answers it
    Quit                      ->  the desktop again, its window restored

Every gate before this one launched M11.G4A, which makes its calls and
returns without ever reading the mouse (test-m18), or launched the
calculator from a stand-in desktop by a KEYPRESS (test-m22).  Neither
crosses the seam this one does -- what the AES's input state is left
holding when one program stops mid-gesture and the next one starts and
asks for a click.  Two things are checked there that nothing else checks:

  THE POINTER'S FORM.  The desktop turns it into an hourglass before
  shel_write and never turns it back, because in the donor the form
  belongs to the process and the new process brings its own.  There is
  one process here, so the shell has to.  The gate reads the VDI's own
  cur_data/cur_xhot out of the target and names the form it finds.

  THE CLICK.  A key of the panel is pressed and the calculator's own
  `shown` is polled until it reads what that key means -- so a click that
  is never delivered is reported as a dead click, not as a picture that
  differs somewhere.

The desktop's screens and its G are checked against tools/deskref.py as
test-m18 checks them; the calculator's panel against the same host AES
drawing the same resource, as test-m22 checks it.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vdiref, vbxeref, symfile     # noqa: E402
import calcrsc, gemdata                     # noqa: E402
import deskref                              # noqa: E402
from deskref import Desktop, DROOT, GLOBES_SIZE    # noqa: E402
from aesref import W_FULLER, RSRC_LOAD      # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE,  # noqa: E402
                     F, DCLICK, drive, storm_check)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m11_abi import app_calls               # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC, SHOT, SETTLE   # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402
from m17_desktop import (DESKTOP, DESK_RSC, rsc_imlen, desk_places,  # noqa: E402
                         DESK_SYM, SYMS, PROBE, DRVBYT,
                         GCLICK, header, listing)
from m18_launch import model_desk           # noqa: E402
from m22_apps import (Panel, form_centre, panel_centre, calc_display,  # noqa: E402
                      press, poll_long, read_long)
from demo_aes import path                   # noqa: E402

DISK = os.path.join(ROOT, "build", "m23-boot.atr")
CALC = os.path.join(ROOT, "build", "calc.g4a")
CALC_SYM = os.path.join(ROOT, "build", "calc.sym")

FOLDER = "APPS"                             # the folder the desktop opens
PROGRAM = "CALC.G4A"                        # and the program inside it
FMD_START, FMD_GROW, FMD_SHRINK, FMD_FINISH = 0, 1, 2, 3
MAX_DEPTH = 7
KEY = calcrsc.C7                            # the one key the gate presses

STOPS = ["desktop", "window-a", "full", "folder"]

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)
        print(f"  FAIL: {msg}")
    return cond


def mouse_form(b, syms):
    """The pointer's form as the VDI holds it (src/vdi/vdi.c cur_*): the
    name from tools/gemdata.py it matches, or None."""
    data = [b.peek16(syms["cur_data"] + 2 * i) for i in range(16)]
    hot = (b.peek16(syms["cur_xhot"]), b.peek16(syms["cur_yhot"]))
    for name, f in gemdata.MFORMS.items():
        if list(f["data"]) == data and tuple(f["hot"]) == hot:
            return name
    return None


def inputs(memo):
    """The desktop's step producers, one per wait."""
    def probe(d):
        memo.setdefault("globes", []).append(d.globes())
        return PROBE

    def open_a(d):
        # the desk is up: two clicks on drive A open a window on A:\*.*
        icon = d.centre(d.g_screen_addr, d.screen[DROOT].ob_head)
        return [F(3), probe(d), SHOT, *path(d.pointer(), icon), F(4), *DCLICK(icon)]

    def window_a(d):
        # the fuller, so that every item of the root is in the work area
        g = d.gadget(d.win_ontop().id, W_FULLER)
        return [F(3), probe(d), SHOT, *path(d.pointer(), g), F(2), *GCLICK(g)]

    def full(d):
        # two clicks on the FOLDER: do_fopen -- the same window, deeper
        item = d.item(d.win_ontop(), FOLDER)
        return [F(3), probe(d), SHOT, *path(d.pointer(), item), F(4), *DCLICK(item)]

    def folder(d):
        # and two on the program inside it: do_aopen -- shel_write, and
        # the desktop returns to the shell
        item = d.item(d.win_ontop(), PROGRAM)
        return [F(3), probe(d), SHOT, *path(d.pointer(), item), F(4), *DCLICK(item)]

    return [open_a, window_a, full, folder]


def poll_nonzero(b, addr, limit=2000, step=10):
    """Frames until the word at addr is not 0; -1 if it never is."""
    for t in range(0, limit, step):
        if b.peek16(addr):
            return t
        b.frames(step)
    return -1


def model(mark, brk, pointer, drvmap):
    """The prelude and the desktop against the model: (v, a, want, d, memo)."""
    v, a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
    # Each run of the desktop takes the resource again, which is why the
    # arena is the same on both (desk_places, in m17_desktop.py).
    pl = desk_places(brk)
    arena = pl.pop("dos_brk")
    a.dos_dirs = listing(DISK)
    g_link = symfile.load(DESK_SYM)["G"]
    memo = {}

    model_desk(v, a)
    a.dos_brk = arena
    d = Desktop(v, a, mark, pl.pop("link_near"), pl.pop("near_size"),
                g_link, drvmap, inputs(memo), **pl)
    d.main()
    return v, a, want, d, memo


def main(argv):
    keep = "--shot" in argv
    syms = symfile.load(SYMS)
    ptr = syms["ptr_state"]
    runs, lastret, lastrc = syms["sh_runs"], syms["sh_lastret"], syms["sh_lastrc"]
    calls = syms["app_calls"]
    os.makedirs(SHOTDIR, exist_ok=True)
    shots = []

    def shot(b, name):
        p = os.path.join(SHOTDIR, f"m23-{name}.png")
        b.screenshot(p)
        shots.append(p)
        return p

    def same(b, name, rgb, what):
        p = shot(b, name)
        bad, shown = vbxeref.compare_to_shot(rgb, p)
        check(not bad, f"{what}: {bad} px differ from the model; first {shown[:3]}")
        print(f"  {what:<58s} {'ok' if not bad else 'FAIL'}")
        if not keep:
            os.remove(p)

    emu = launch(tag="m23", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        t, st = boot(b)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  M3.COM loaded and running {t} frames after RETURN")
        kind = st[8]
        drvmap = 0x03 if kind else (b.peek(DRVBYT) or 1)
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room = rec[6] & 0xFFFF, rec[7]
        brk = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}; "
              f"DOS kind {kind}, drive map {drvmap:#04x}")

        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want, d, memo = model(mark, brk, pointer, drvmap)
        print(f"  the model's desktop: {len(d.script)} calls, waits at {d.waits}, "
              f"near ${d.near:04X}, G ${d.G:04X}")
        check(len(ref_a.shots) == len(STOPS),
              f"the model took {len(ref_a.shots)} shots, not {len(STOPS)}")

        stage = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(stage, 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        poke16(b, calls, 0)
        b.poke(STATUS + ST_GO, 1)

        def read():
            return (b.peek16(calls) - 1) & 0xFFFF

        def reach(first, what):
            for t in range(0, 4000, 5):
                n = read()
                if n != NOT_STARTED and n >= first:
                    break
                b.frames(5)
            else:
                check(False, f"{what} did not reach its first wait (call {read()})")
                return None
            check(n == first, f"{what} is in call {n}, not its first wait {first}")
            return t

        probes = iter(enumerate(memo["globes"]))

        def probe(bb):
            k, want_g = next(probes)
            got = bb.memdump(d.G, GLOBES_SIZE)
            if got == want_g:
                print(f"  G at ${d.G:04X}, probe {k} (call {read()}): "
                      f"{GLOBES_SIZE} bytes as the model has them")
                return
            bad = [i for i in range(GLOBES_SIZE) if got[i] != want_g[i]]
            field = [f for f, _ in deskref.GLOBES
                     if deskref.g_offset(f) <= bad[0]][-1]
            check(False, f"G at probe {k} (call {read()}) differs at {len(bad)} "
                         f"byte(s), first at +{bad[0]} ({field} +"
                         f"{bad[0] - deskref.g_offset(field)}): target "
                         f"{got[bad[0]:bad[0] + 8].hex()} model "
                         f"{want_g[bad[0]:bad[0] + 8].hex()}")

        stops = iter(STOPS)

        def take(bb):
            shot(bb, next(stops))

        def plan_of(dd, base):
            return {base + k: [("shot", take) if s == SHOT else
                               ("probe", probe) if s == PROBE else s for s in v]
                    for k, v in dd.plan.items()}

        def stall(what):
            storm = storm_check(b)
            if storm:
                print(f"  {storm}")
            print(f"  screen at the stall: {shot(b, 'stall')}")
            fault = b.peek(syms["irq_fault"])
            print(f"  irq_fault {fault}; E={b.ok('REGS').get('e', '?')}")
            try:
                print(f"  REGS: {b.ok('REGS')}")
            except Exception as e:
                print(f"  no post-mortem: {e}")

        # 1. the desktop: open A, full, into APPS, run the program
        t = reach(d.waits[0], "the desktop")
        if t is None:
            stall("the desktop")
            return 1
        print(f"  the desktop up {t} frames after GO, in call {read()}")
        err = drive(b, None, ptr, plan_of(d, 0), read=read)
        check(not err, f"driving the desktop: {err}")
        if err:
            stall("the desktop")
            return 1

        # 2. the calculator, loaded by the shell out of the folder
        t = poll(b, runs, 2, limit=4000)
        check(t >= 0, f"{PROGRAM} did not run (sh_runs {b.peek16(runs)}, "
                      f"call {read()})")
        if t < 0:
            stall(PROGRAM)
            return 1
        b.frames(SETTLE)
        link_near, near_size, _ = header(CALC)
        near = (mark + 0xFF) & ~0xFF
        rsc_base = (near + near_size + 1) & ~1
        csym = symfile.load(CALC_SYM)
        print(f"  {PROGRAM} up {t} frames after the double-click; "
              f"near ${near:04X}, resource ${rsc_base:04X}")

        # THE POINTER'S FORM.  The desktop's last act was desk_busy(TRUE).
        form = mouse_form(b, syms)
        check(form == "ARROW", f"the pointer over the calculator is the "
                               f"{form or 'unknown'} form, not the ARROW: the "
                               f"shell left the desktop's hourglass on")
        print(f"  the pointer over the calculator: {form or 'unknown'} form")

        model_desk(ref_v, ref_a)
        panel = Panel(ref_a, calcrsc, rsc_base, ref_a.gl_wchar, ref_a.gl_hchar)
        x, y, w, h = form_centre(ref_v, ref_a, panel.addr)
        panel.put(ref_a, calcrsc.CDISP, "0".rjust(calcrsc.DISP_PLACES))
        aesref.resume(ref_v, ref_a, [
            (aesref.FORM_DIAL, (), (FMD_START, 0, 0, 0, 0, x, y, w, h)),
            (aesref.FORM_DIAL, (), (FMD_GROW, 0, 0, 0, 0, x, y, w, h)),
            (aesref.OBJC_DRAW, (x, y, w, h), (0, MAX_DEPTH), panel.addr)])
        same(b, "calc", ref_v.to_rgb(), "the calculator's panel, cleared")

        # THE CLICK: one key, waited FOR through the program's own `shown`
        def model_pointer(px, py):
            """The model's pointer where press() is about to put the
            target's.  The calculator's CALLS are replayed on the model
            below, but its INPUT is not -- so where the pointer went is
            the one thing the model cannot learn by itself, and the
            cursor is painted into the picture both sides are compared
            on."""
            ref_v.ptr_x, ref_v.ptr_y = px, py
            ref_v.input_poll(tick=True)

        shown_at = csym["shown"] + near - link_near
        value, text = calc_display([KEY])[0]
        cx, cy = panel_centre(ref_a, panel, KEY)
        model_pointer(cx, cy)
        press(b, ptr, cx, cy)
        got = poll_long(b, shown_at, value)
        clicked = check(got == value,
                        f"the key at object {KEY} was clicked and the "
                        f"calculator holds {got}, not {value}: the click "
                        f"never reached it")
        if clicked:
            panel.put(ref_a, calcrsc.CDISP, text)
            aesref.resume(ref_v, ref_a, [
                (aesref.OBJC_DRAW, (x, y, w, h), (KEY, 1), panel.addr),
                (aesref.OBJC_DRAW, (x, y, w, h), (calcrsc.CDISP, 0), panel.addr)])
            b.frames(SETTLE)
            same(b, "calc-key", ref_v.to_rgb(), f"{value} on the display")

        # 3. Quit: the desktop again, with its window on the folder
        cx, cy = panel_centre(ref_a, panel, calcrsc.CQUIT)
        press(b, ptr, cx, cy)
        t = poll(b, runs, 3, limit=4000)
        check(t >= 0, f"after Quit the desktop did not come back (sh_runs "
                      f"{b.peek16(runs)})")
        check(b.peek16(lastret) == 0,
              f"{PROGRAM}'s main() returned {b.peek16(lastret)}, not 0")
        check(b.peek16(lastrc) == 0, f"the last load's status {b.peek16(lastrc)}")
        if t >= 0:
            # ...and UP: its menu bar showing, which is after its resource
            # has loaded.  The shell counts the run before the desktop's
            # main() and a load that fails is main()'s alert, not a load
            # status: without this the gate passed while the desktop came
            # back saying DESKTOP.RSC was not on the boot disk, because it
            # looked in the folder the program had been run from.
            t2 = poll_nonzero(b, syms["gl_mntree"], 2000)
            check(t2 >= 0, "after Quit the desktop's menu bar never came back: "
                           "its resource was not found")
            b.frames(SETTLE * 4)
            print(f"  the desktop again {t} frames after Quit, its bar "
                  f"{t2} after that, in call {read()}")

        print(f"after:  {b.peek16(runs)} programs run, {read()} ABI calls")
    finally:
        emu.stop()

    ok = not problems
    print(f"gem4xe-m23: {'PASS' if ok else 'FAIL'} -- an accessory from a "
          f"folder, {len(problems)} problem(s)")
    if keep:
        for p in shots:
            print(f"  {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
