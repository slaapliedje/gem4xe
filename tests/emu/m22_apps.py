#!/usr/bin/env python3
"""Phase 28 gate: the two accessories, run through the shell loop.

CALC.PRG and CLOCK.PRG (src/apps) are the first programs written to
gem4xe's application ABI that are not tests.  They are gated here the
way the desktop is: not against a picture kept from a previous run, but
against what the HOST AES makes of the same resource with the same text
in it -- tools/calcrsc.py and tools/clockrsc.py build the file, aesref
draws the tree, and the two are compared pixel for pixel.

    C  ->  the calculator, out of \\APPS\\ with its resource beside it:
           its panel, then 7 x 6 = 42 at the keypad,
           then Quit and back to the stand-in desktop
    K  ->  the clock: its panel, left to tick, then a key and back
    Q  ->  shutdown

WHAT THE CLOCK'S CHECK IS, EXACTLY.  A clock is the one thing whose
right answer depends on how long the run took, so the check is in two
halves that cannot prop each other up.  The TIMEKEEPING half reads the
program's own `second` out of memory by symbol and requires it to have
advanced by the number of seconds the frames driven are worth, within
one.  The DRAWING half then renders the model's panel from that same
number and compares the screen: what it proves is that the program drew
what it believed, and the first half is what says the belief was right.
Neither half is the other's evidence.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vdiref, vbxeref, symfile     # noqa: E402
import calcrsc, clockrsc                    # noqa: E402
from rsc import R_TREE                      # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE, SYMS,  # noqa: E402
                     F, M, B, compare)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC, SHOT, SETTLE   # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import HELP, desktop_script, poll, SHELL  # noqa: E402
from m17_desktop import header              # noqa: E402

DISK = os.path.join(ROOT, "build", "m22-boot.atr")
CALC = os.path.join(ROOT, "build", "calc.g4a")
CLOCK = os.path.join(ROOT, "build", "clock.g4a")
CALC_SYM = os.path.join(ROOT, "build", "calc.sym")
CLOCK_SYM = os.path.join(ROOT, "build", "clock.sym")

FMD_START, FMD_GROW, FMD_SHRINK, FMD_FINISH = 0, 1, 2, 3
MAX_DEPTH = 7
TICK_FRAMES = 50                            # PAL frames in the app's 1000 ms
CLOCK_TICKS = 5                             # how long the clock is watched

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def shot(b, name):
    p = os.path.join(SHOTDIR, f"m22-{name}.png")
    b.screenshot(p)
    return p


class Panel:
    """One accessory's resource as both sides have it: the file the target
    loaded, the trees the model draws, and where the text buffers are."""

    def __init__(self, ref_a, module, base, wchar, hchar):
        self.r = module.build()
        image, trees, mem = self.r.expect(base, wchar, hchar, ref_a.gl_width)
        self.base, self.trees = base, trees
        for t, objs in enumerate(trees):
            ref_a.trees[self.r.addr(R_TREE, t, base)] = objs
        ref_a.mem.update(mem)
        self.addr = self.r.addr(R_TREE, 0, base)
        self.objs = trees[0]

    def put(self, ref_a, obj, text):
        """Into a field's te_ptext, where objc_draw reads it -- what the
        program does to its own display."""
        ted = ref_a.mem[self.objs[obj].ob_spec]
        ref_a.mem[ted.ptext].s = text


def calc_display(keys):
    """What the calculator's display says after `keys` -- the mirror of
    src/apps/calc.c, and the only place the arithmetic is written twice."""
    acc, shown, pending, fresh = 0, 0, 0, True
    digits = {calcrsc.C0: 0, calcrsc.C1: 1, calcrsc.C2: 2, calcrsc.C3: 3,
              calcrsc.C4: 4, calcrsc.C5: 5, calcrsc.C6: 6, calcrsc.C7: 7,
              calcrsc.C8: 8, calcrsc.C9: 9}

    def apply(op, a, b):
        if op == calcrsc.CADD:
            return a + b
        if op == calcrsc.CSUB:
            return a - b
        if op == calcrsc.CMUL:
            return a * b
        if op == calcrsc.CDIV:
            return a if b == 0 else int(a / b) if a * b < 0 else a // b
        return b

    out = []
    for k in keys:
        if k == calcrsc.CCLR:
            acc, shown, pending, fresh = 0, 0, 0, True
        elif k == calcrsc.CSIGN:
            shown, fresh = -shown, False
        elif k in (calcrsc.CADD, calcrsc.CSUB, calcrsc.CMUL, calcrsc.CDIV):
            acc = apply(pending, acc, shown) if pending else shown
            shown, pending, fresh = acc, k, True
        elif k == calcrsc.CEQ:
            acc = apply(pending, acc, shown) if pending else shown
            shown, pending, fresh = acc, 0, True
        else:
            v = 0 if fresh else abs(shown)
            v = v * 10 + digits[k]
            shown, fresh = -v if (not fresh and shown < 0) else v, False
        out.append((shown, f"{shown:d}".rjust(calcrsc.DISP_PLACES)))
    return out


def clock_text(tmpl, values):
    """The runs of underscores of a template filled in order, which is
    what src/apps/clock.c's fill() does."""
    out, i, n = "", 0, 0
    while i < len(tmpl):
        if tmpl[i] != "_":
            out += tmpl[i]
            i += 1
            continue
        run = 0
        while i + run < len(tmpl) and tmpl[i + run] == "_":
            run += 1
        v = values[n] if n < len(values) else 0
        out += str(v % (10 ** run)).rjust(run, "0")
        n += 1
        i += run
    return out


def main(argv):
    keep = "--shot" in argv
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    ptr = syms["ptr_state"]
    runs, lastret, lastrc = (syms["sh_runs"], syms["sh_lastret"],
                             syms["sh_lastrc"])

    def same(b, name, rgb, what):
        p = shot(b, name)
        bad, shown = vbxeref.compare_to_shot(rgb, p)
        check(not bad, f"{what}: {bad} px differ from the model; first {shown[:3]}")
        print(f"  {what:<58s} {'ok' if not bad else 'FAIL'}")
        if not keep:
            os.remove(p)

    emu = launch(tag="m22", memsize="1088K", extra_args=["--disk", DISK])
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
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room = rec[6] & 0xFFFF, rec[7]
        print(f"before: pool ${mark:04X}, {room} free")

        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
        hbox = ref_a.gl_hbox

        def model_desk():
            ref_v.close_virtuals()
            ref_a.wm_init()
            ref_a.mn_init()
            ref_a.ratinit()
            ref_a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
            ref_a.tree = ref_a.W_TREE
            ref_a.draw(0, 0, (0, 0, ref_a.gl_width, ref_a.gl_height))

        def model_desktop():
            model_desk()
            aesref.resume(ref_v, ref_a, desktop_script(hbox))

        script = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(script, 0)
        b.memload(r.sa, b"".join(
            (w if w < 32768 else w - 65536).to_bytes(2, "little", signed=True)
            for w in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)

        t = poll(b, runs, 1)
        check(t >= 0, "the desktop never ran (sh_runs stayed 0)")
        if t < 0:
            return 1
        b.frames(SETTLE)
        model_desktop()
        same(b, "desktop", ref_v.to_rgb(), "the stand-in desktop")

        # ---- the calculator ------------------------------------------------
        link_near, near_size, _ = header(CALC)
        near = (mark + 0xFF) & ~0xFF
        rsc_base = (near + near_size + 1) & ~1
        csym = symfile.load(CALC_SYM)
        b.key("C")
        t = poll(b, runs, 2)
        check(t >= 0, f"after C: the calculator did not run (sh_runs "
                      f"{b.peek16(runs)})")
        if t < 0:
            return 1
        b.frames(SETTLE)
        print(f"  CALC.PRG up {t} frames after C; near ${near:04X}, "
              f"resource ${rsc_base:04X}")

        model_desk()                        # app_free, then the program draws
        panel = Panel(ref_a, calcrsc, rsc_base, ref_a.gl_wchar, ref_a.gl_hchar)
        x, y, w, h = form_centre(ref_v, ref_a, panel.addr)
        panel.put(ref_a, calcrsc.CDISP, "0".rjust(calcrsc.DISP_PLACES))
        aesref.resume(ref_v, ref_a, [
            (aesref.FORM_DIAL, (), (FMD_START, 0, 0, 0, 0, x, y, w, h)),
            (aesref.FORM_DIAL, (), (FMD_GROW, 0, 0, 0, 0, x, y, w, h)),
            (aesref.OBJC_DRAW, (x, y, w, h), (0, MAX_DEPTH), panel.addr)])
        same(b, "calc", ref_v.to_rgb(), "the calculator's panel, cleared")

        # 7 x 6 = 42, at the keypad.  Each key is waited FOR rather than
        # waited out: the program's own `shown` is polled until it reads
        # what that key means, so a lost click is reported as the key it
        # was and not as a picture that differs somewhere.
        shown_at = csym["shown"] + near - link_near
        keys = [calcrsc.C7, calcrsc.CMUL, calcrsc.C6, calcrsc.CEQ]
        for k, (value, text) in zip(keys, calc_display(keys)):
            cx, cy = panel_centre(ref_a, panel, k)
            model_pointer(ref_v, cx, cy)
            press(b, ptr, cx, cy)
            got = poll_long(b, shown_at, value)
            if not check(got == value, f"after the key at object {k} the "
                                       f"calculator holds {got}, not {value}"):
                break
            panel.put(ref_a, calcrsc.CDISP, text)
            aesref.resume(ref_v, ref_a, [
                (aesref.OBJC_DRAW, (x, y, w, h), (k, 1), panel.addr),
                (aesref.OBJC_DRAW, (x, y, w, h), (calcrsc.CDISP, 0), panel.addr)])
        b.frames(SETTLE)
        same(b, "calc-42", ref_v.to_rgb(), "7 x 6 = 42 on the display")

        cx, cy = panel_centre(ref_a, panel, calcrsc.CQUIT)
        model_pointer(ref_v, cx, cy)
        press(b, ptr, cx, cy)
        t = poll(b, runs, 3)
        check(t >= 0, f"after Quit: the desktop did not come back (sh_runs "
                      f"{b.peek16(runs)})")
        check(b.peek16(lastret) == 0,
              f"CALC.PRG's main() returned {b.peek16(lastret)}, not 0")
        b.frames(SETTLE)
        model_desktop()
        same(b, "after-calc", ref_v.to_rgb(), "the desktop again, after the calculator")

        # ---- the clock -----------------------------------------------------
        link_near, near_size, _ = header(CLOCK)
        rsc_base = (near + near_size + 1) & ~1
        ksym = symfile.load(CLOCK_SYM)
        b.key("K")
        t = poll(b, runs, 4)
        check(t >= 0, f"after K: the clock did not run (sh_runs "
                      f"{b.peek16(runs)})")
        if t < 0:
            return 1
        b.frames(SETTLE)
        started = b.peek16(ksym["second"] + near - link_near)
        # Every frame driven between the two readings counts, the settle
        # included: the clock does not know which of them the harness
        # meant, and an expectation that ignores some of them is one that
        # fails when a load takes a moment longer.
        drove = TICK_FRAMES * CLOCK_TICKS + SETTLE
        b.frames(drove)
        secs = b.peek16(ksym["second"] + near - link_near)
        mins = b.peek16(ksym["minute"] + near - link_near)
        hrs = b.peek16(ksym["hour"] + near - link_near)
        ran = (secs - started) % 60
        want_ticks = drove // TICK_FRAMES
        check(abs(ran - want_ticks) <= 1,
              f"the clock advanced {ran} seconds over {drove} frames, not the "
              f"{want_ticks} they are worth, give or take one")
        print(f"  CLOCK.PRG ticked {ran} of {want_ticks} seconds; it says "
              f"{hrs:02d}:{mins:02d}:{secs:02d}")

        model_desk()
        kpanel = Panel(ref_a, clockrsc, rsc_base, ref_a.gl_wchar, ref_a.gl_hchar)
        kx, ky, kw, kh = form_centre(ref_v, ref_a, kpanel.addr)
        kpanel.put(ref_a, clockrsc.KTIME,
                   clock_text(clockrsc.TIME_TMPL, (hrs, mins, secs)))
        kpanel.put(ref_a, clockrsc.KDATE,
                   clock_text(clockrsc.DATE_TMPL, (1, 1, 80)))
        aesref.resume(ref_v, ref_a, [
            (aesref.FORM_DIAL, (), (FMD_START, 0, 0, 0, 0, kx, ky, kw, kh)),
            (aesref.FORM_DIAL, (), (FMD_GROW, 0, 0, 0, 0, kx, ky, kw, kh)),
            (aesref.OBJC_DRAW, (kx, ky, kw, kh), (0, MAX_DEPTH), kpanel.addr)])
        same(b, "clock", ref_v.to_rgb(), "the clock, ticking from the epoch")

        b.key("SPACE")                      # any key quits it
        t = poll(b, runs, 5)
        check(t >= 0, f"after SPACE: the desktop did not come back (sh_runs "
                      f"{b.peek16(runs)})")
        check(b.peek16(lastret) == 0,
              f"CLOCK.PRG's main() returned {b.peek16(lastret)}, not 0")
        b.frames(SETTLE)
        model_desktop()
        same(b, "after-clock", ref_v.to_rgb(), "the desktop again, after the clock")

        # ---- and out -------------------------------------------------------
        b.key("Q")
        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            check(False, "after Q: the runner did not finish")
            return 1
        b.frames(4)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        print(f"after:  pool ${mark2:04X}, {room2} free")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; "
              f"was ${mark:04X}, {room}")
    finally:
        emu.stop()

    print(f"gem4xe-m22: {'PASS' if not problems else 'FAIL'} -- the "
          f"calculator and the clock, {len(problems)} problem(s)")
    return 1 if problems else 0


def form_centre(ref_v, ref_a, tree):
    """form_center through the model, which is what the program calls and
    what puts the panel where the target has it."""
    rec = aesref.resume(ref_v, ref_a, [(aesref.FORM_CENTER, (), (), tree)])[0]
    # the record is (contrl[2], contrl[4], intout[0..14], ptsout[0..2]);
    # form_center answers x, y, w in intout and h in ptsout (deskref
    # start_dialog reads the same words)
    return rec[2], rec[3], rec[4], rec[17]


def panel_centre(ref_a, panel, obj):
    """The middle of one of a panel's objects, where the AES has put it
    (aesref ob_actxywh, the same call the desktop gate's centre() makes)."""
    ref_a.tree = panel.objs
    r = ref_a.ob_actxywh(obj)
    return r.x + r.w // 2, r.y + r.h // 2


def poll_long(b, addr, want, limit=400, step=4):
    """Frames until the LONG at addr reads want; what it holds if it never
    does.  A dialog's click is answered when the AES has held it for the
    double-click time, so how long that takes is the machine's business
    and not a number to guess."""
    for _ in range(0, limit, step):
        got = read_long(b, addr)
        if got == want:
            return got
        b.frames(step)
    return read_long(b, addr)


def read_long(b, addr):
    v = b.peek16(addr) | (b.peek16(addr + 2) << 16)
    return v - (1 << 32) if v & 0x80000000 else v


def model_pointer(ref_v, x, y):
    """The model's pointer where press() is about to put the target's.
    An accessory's CALLS are replayed on the model, but its INPUT is not,
    so where the pointer went is the one thing the model cannot learn by
    itself -- and the cursor is painted into the picture both sides are
    compared on."""
    ref_v.ptr_x, ref_v.ptr_y = x, y
    ref_v.input_poll(tick=True)


def press(b, ptr, x, y):
    """The pointer there and a click, held past the double-click time as
    the form gates hold theirs (m7_form CLICK)."""
    poke16(b, ptr, x)
    poke16(b, ptr + 2, y)
    b.frames(4)
    poke16(b, ptr + 4, 1)
    b.frames(16)
    poke16(b, ptr + 4, 0)
    b.frames(8)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
