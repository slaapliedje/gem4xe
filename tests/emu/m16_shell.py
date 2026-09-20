#!/usr/bin/env python3
"""Phase 14, milestone 3 gate: the shell loop.

GEM's sh_main runs the desktop, runs what the desktop asks for, and runs
the desktop again when that returns, until it asks to shut down.  Here it
is the whole of that on a SpartaDOS disk: the runner's sys op 16 hands
control to src/aes/shel.c and blocks in it until the loop ends, while
the harness plays the user at the keyboard --

    DESKTOP.PRG (v0)  R  ->  M11.PRG runs and returns  ->  the desktop
                      V  ->  shel_wdef names A:\SUB as the desktop's
                             directory, then M11.PRG again -- so the run
                             after it starts where the shell was told
                      X  ->  NOPE.PRG is not there: the alert, RETURN,
                             the desktop
                      Q  ->  shel_rdef and shel_wdef checked, then
                             shutdown, and sys op 16 returns.  What the
                             desktop's main() returns is the five bits
                             src/m16_desk.c describes.

-- and checks three things.  The screen, against the model, at each stop:
the desk drawn edge to edge with the desktop's line of help on it, and
the shell's own alert when a program cannot be found.  The counters the
shell keeps, polled while it is inside the loop (the sys op's record is
not written until the loop ends): programs run, what the last one
returned, the last load's status.  And the pool afterwards: back where it
was, with the desktop's file kept in far memory and everything else
released.

The desktop's line reads the keyboard through evnt_keybd, so a key is a
bridge KEY press, as in the form gates; the keys are pressed only after
the counter shows the program that wants them is up.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vdiref, vbxeref, symfile     # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE, SYMS,  # noqa: E402
                     F, K, RETURN, compare)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC, SHOT, SETTLE   # noqa: E402
from m14_sparta import DISK, boot, screen   # noqa: E402
from m11_abi import app_calls               # noqa: E402

SHELL = 3016                                # sys op 16: sh_main
APP_E_FILE = -6                             # src/sys/app.h
DESKTOP = os.path.join(ROOT, "build", "m16_desk.g4a")
# what the desktop draws (src/m16_desk.c), and what the shell says
# when a program cannot be found (src/aes/shel.c)
HELP = "gem4xe desktop -- R M11, C CALC, K CLOCK, B M29, H M31, T M32, X none, Q quits"
NOT_FOUND = "[1][This application|cannot be found.][ OK ]"
STR_OFF = 0                                 # the model's copy of it, in scratch


def desktop_script(hbox):
    """The desktop's calls that draw: its workstation, the colour, the
    line of help."""
    return [(V_OPNVWK, (), vdiref.WORK_IN), (VST_COLOR, (), (1,)),
            (V_GTEXT, (8, hbox + 16), tuple(ord(c) for c in HELP))]


V_OPNVWK, VST_COLOR, V_GTEXT = vdiref.V_OPNVWK, vdiref.VST_COLOR, vdiref.V_GTEXT


def poll(b, addr, want, limit=3000, step=10):
    """Frames until the word at addr reads want; -1 if it never does."""
    for t in range(0, limit, step):
        if b.peek16(addr) == want & 0xFFFF:
            return t
        b.frames(step)
    return -1


def main(argv):
    keep = "--shot" in argv
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    runs, lastret, lastrc = syms["sh_runs"], syms["sh_lastret"], syms["sh_lastrc"]
    ptr = syms["ptr_state"]
    # polled while SpartaDOS may have its bank in at $4000-$7FFF (m14)
    for a in (runs, lastret, lastrc, ptr, syms["vdi_result_count"]):
        assert not 0x4000 <= a < 0x8000, hex(a)
    ncalls = len(app_calls(0, 0))           # what M11.PRG's main() returns
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3   # far_alloc's rounding
    os.makedirs(SHOTDIR, exist_ok=True)
    shots = []

    def shot(b, name):
        p = os.path.join(SHOTDIR, f"m16-{name}.png")
        b.screenshot(p)
        shots.append(p)
        return p

    def same(b, name, rgb, what):
        p = shot(b, name)
        bad, shown = vbxeref.compare_to_shot(rgb, p)
        check(not bad, f"{what}: {bad} px differ from the model; first {shown[:3]}")
        print(f"  {what:<58s} {'ok' if not bad else 'FAIL'}")

    # The stack, from the linker's map: painted before the program is
    # loaded (the load writes nothing there, and the startup zeroes zdata,
    # not the stack), read back at the end for its low-water mark.  A
    # kilobyte of stack was not enough for a program under the shell
    # under the runner (docs/phase14.md, milestone 3); this is the number
    # that says how much of the 2 KB the loop actually uses.
    stk = [ln for ln in open(os.path.join(ROOT, "build", "m3.map"))
           if ln.startswith("stack ")][0].split()
    stk_lo, stk_hi = (int(x, 16) for x in stk[1].split("-"))
    PAINT, MARGIN = 0xA5, 256

    def paint(b):
        b.memload(stk_lo, bytes([PAINT]) * (stk_hi - stk_lo + 1))

    def low_water(b):
        d = b.memdump(stk_lo, stk_hi - stk_lo + 1)
        for i, x in enumerate(d):
            if x != PAINT:
                return stk_lo + i
        return stk_hi + 1

    emu = launch(tag="m16", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        t, st = boot(b, prepare=paint)
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
        mark, room, brk = rec[6] & 0xFFFF, rec[7], (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}")

        # The model: the runner's prelude, then what the shell draws for
        # the desktop and what the desktop draws for itself.
        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
        hbox = ref_a.gl_hbox

        def model_desk():
            ref_v.close_virtuals()      # the program before ended: app_free
            ref_a.wm_init()
            ref_a.mn_init()
            ref_a.ratinit()
            ref_a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
            ref_a.tree = ref_a.W_TREE
            ref_a.draw(0, 0, (0, 0, ref_a.gl_width, ref_a.gl_height))

        def model_desktop():
            model_desk()
            aesref.resume(ref_v, ref_a, desktop_script(hbox))

        # The target: the prelude and the shell, staged by hand -- the
        # runner blocks inside sh_main, so its record is read at the end.
        script = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(script, 0)
        b.memload(r.sa, b"".join(
            (w if w < 32768 else w - 65536).to_bytes(2, "little", signed=True)
            for w in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)

        # 1. the desktop
        t = poll(b, runs, 1)
        check(t >= 0, "the desktop never ran (sh_runs stayed 0)")
        if t < 0:
            return 1
        print(f"  the desktop up {t} frames after GO")
        b.frames(SETTLE)
        model_desktop()
        same(b, "desktop", ref_v.to_rgb(), "the desk and the desktop's line of help")

        # 2. R: M11.PRG, then the desktop again
        b.key("R")
        t = poll(b, runs, 3)
        check(t >= 0, f"after R: sh_runs did not reach 3 (reads {b.peek16(runs)})")
        if t >= 0:
            got = b.peek16(lastret)
            check(got == ncalls, f"M11.PRG's main() returned {got}, not {ncalls}")
            check(b.peek16(lastrc) == 0, f"the last load's status {b.peek16(lastrc)}")
            print(f"  M11.PRG ran and returned {got}; the desktop back {t} frames after R")
            b.frames(SETTLE)
            model_desktop()
            same(b, "after-m11", ref_v.to_rgb(), "the desktop again, after M11.PRG")

        # 2b. V: the desktop's directory named, then M11.PRG again.  The
        # run after this one is the first that starts in A:\SUB, and the
        # bit for it is folded into what Q returns.
        b.key("V")
        t = poll(b, runs, 5)
        check(t >= 0, f"after V: sh_runs did not reach 5 (reads {b.peek16(runs)})")
        if t >= 0:
            check(b.peek16(lastrc) == 0, f"after V: load status {b.peek16(lastrc)}")
            print(f"  shel_wdef, M11.PRG again, the desktop back {t} frames after V")
            b.frames(SETTLE)
            model_desktop()
            same(b, "after-wdef", ref_v.to_rgb(),
                 "the desktop again, now run from A:\\SUB")

        # 3. X: NOPE.PRG cannot be found -- the shell's alert, then the desktop
        b.key("X")
        t = poll(b, lastrc, APP_E_FILE)
        check(t >= 0, f"after X: sh_lastrc did not read APP_E_FILE "
                      f"(reads {b.peek16(lastrc)})")
        if t >= 0:
            b.frames(SETTLE)
            model_desk()
            addr = r.sc + STR_OFF
            ref_a.fs_strings[addr] = NOT_FOUND
            ref_a.pool_mark = mark
            aesref.resume(ref_v, ref_a, [(aesref.FORM_ALERT, (), (1,), addr)],
                          plan={0: [F(SETTLE), SHOT, K("RETURN", RETURN)]})
            same(b, "alert", ref_a.shots[-1], "the shell's alert: cannot be found")
            b.key("RETURN")
            t = poll(b, runs, 6)
            check(t >= 0, f"after the alert: sh_runs did not reach 6 "
                          f"(reads {b.peek16(runs)})")
            if t >= 0:
                print(f"  the alert dismissed, the desktop back {t} frames after RETURN")
                b.frames(SETTLE)
                model_desktop()
                same(b, "after-alert", ref_v.to_rgb(), "the desktop again, after the alert")

        # 4. Q: shutdown, and the sys op returns
        b.key("Q")
        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            check(False, "after Q: the runner did not finish")
            return 1
        b.frames(4)
        n = b.peek16(r.count)
        check(n == len(script), f"{n} records, not {len(script)}")
        recs = vdiref.decode(b.memdump(r.results, n * vdiref.RESULT_WORDS * 2), n)
        err = compare(b, r.results, len(PRELUDE), PRELUDE, want)
        check(not err, f"the prelude: {err}")
        rec = recs[-1][2:]
        ret, nruns, lret, lrc, calls, bad = rec[6:12]
        print(f"  sh_main returned {ret}: {nruns} runs, last returned {lret}, "
              f"last load {lrc}; {calls} ABI calls, {bad} refused")
        check(ret == 6, f"sh_main returned {ret}, not the 6 programs run")
        check(nruns == 6, f"sh_runs {nruns}, not 6")
        # THE FIVE BITS src/m16_desk.c sets: the name and the directory
        # shel_rdef gave back, a fresh pair read back after shel_wdef,
        # and -- the one that says the call does something rather than
        # remembers something -- the desktop having been RUN in the
        # directory V named.
        check(lret == 0x1F, f"the desktop's main() returned {lret:#x}, not 0x1f: "
                            f"shel_rdef/shel_wdef")
        check(lrc == 0, f"the last load's status {lrc}, not 0")
        # TWO refusals, and only two -- one per run of M11.PRG, which R
        # and V each ask for.  It makes a COP that is not gem4xe's
        # (src/m11_cop.s), and on this OS nobody else takes COPs
        # (src/sys/abi.s); it is counted as refused, never as a call.
        check(calls > 0 and bad == 2, f"{calls} ABI calls, {bad} refused, "
                                      f"not M11.PRG's foreign COP once per run")

        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        brk2 = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"after:  pool ${mark2:04X}, {room2} free; far brk ${brk2:06X}")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; was ${mark:04X}, {room}")
        check(brk2 == brk + desk_len,
              f"far brk moved {brk2 - brk} bytes; the desktop's file is {desk_len}")
        lw = low_water(b)
        used, size = stk_hi + 1 - lw, stk_hi - stk_lo + 1
        print(f"stack:  {used} of {size} bytes used at the low-water mark (${lw:04X})")
        check(lw - stk_lo >= MARGIN,
              f"the stack came within {lw - stk_lo} bytes of its bottom ${stk_lo:04X}")
    finally:
        emu.stop()

    if not fails and not keep:
        for p in shots:
            os.remove(p)
    print(f"gem4xe-m16: {'PASS' if not fails else 'FAIL'} -- the shell loop, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
