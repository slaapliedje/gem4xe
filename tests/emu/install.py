#!/usr/bin/env python3
"""The installer: SpartaDOS X runs the floppies' INSTALL.BAT onto a drive,
and the machine boots GEM from that drive.

The floppies are where gem4xe starts, not where it lives (docs/media.md):
the system floppy and the applications floppy each carry an INSTALL.BAT
that copies what the disk holds onto a drive the user names
(tools/mkcf.py).  This gate is a user doing that on a machine with two
floppy drives and a third drive to install onto:

  D1:  a blank SDFS disk -- the drive being installed onto, which is D1:
       so that the cold start at the end boots from it
  D2:  gem-sdx.atr, the system
  D3:  gem-apps.atr, the applications and the desk accessory

  1. SpartaDOS X (the [spartados].sdx_cart fixture) comes up at D1:,
     which has nothing on it to run.
  2. D2:, then -INSTALL with no drive: the batch says to name one and
     copies nothing.
  3. -INSTALL D1: from D2:, then from D3:.  Every file each disk carries
     is copied, the drive is given the system's AUTOEXEC.BAT, and neither
     batch reports an error.  The drive's \\GEM\\, \\APPS\\ and root are
     listed and must hold exactly what tools/mkcf.py's two tables and
     AUTOEXEC.BAT say.
  4. The system's -INSTALL D1: again, over what is there: an upgrade.
     It says the AUTOEXEC.BAT is kept, and reports no error.
  5. A cold start.  SpartaDOS X runs D1:'s AUTOEXEC.BAT, GEM switches the
     Rapidus and comes up, the desktop reaches its first wait with
     nothing refused, and the three desk accessories -- CLOCK, CONTROL
     and CALC, which came from the applications disk -- have been loaded
     beside it.

The disk the batch writes stays in the emulator (its --disk mounts are
not written back), which is why steps 3 and 5 read the machine rather
than the image.

  python3 tests/emu/install.py --sdx=CART
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import atr, mkcf, symfile                   # noqa: E402
from m14_sparta import KEYS, screen, wait_prompt  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
SYSTEM = os.path.join(BUILD, "gem-sdx.atr")
APPS = os.path.join(BUILD, "gem-apps.atr")
TARGET = os.path.join(BUILD, "install-target.atr")
SYMS = os.path.join(BUILD, "gem.sym")
FIRST_WAIT = 43                             # the desktop's calls to its first wait
ERROR = re.compile(r"^\s*\d{3} [A-Z][a-z]") # "151 File exists", not "731 FREE SECTORS"
ENTRY = re.compile(r"^\s*([A-Z0-9_]{1,8})\s+(?:([A-Z0-9_]{1,3})\s+)?(?:\d+|<DIR>)\s")


def type_line(b, s, wait=30):
    for ch in s:
        name, shift = KEYS.get(ch, (ch.upper(), False))
        b.key(name, shift=shift)
        b.frames(3)
    b.key("RETURN")
    b.frames(wait)


def below(lines, command):
    """The screen's lines under the command's echo -- the prompt and the
    command on one line -- or all of them once the echo has scrolled off.
    What an earlier command left above it is not this one's output."""
    at = [i for i, ln in enumerate(lines) if ln.rstrip().endswith(command)]
    return lines[at[-1] + 1:] if at else lines


def run(b, command, done, prompt, limit=30000):
    """Type a command and collect what it prints until `done` has been
    seen and the prompt is back: (lines in the order they came, the
    screen's own lines under the echo at the end, frames), frames -1 if
    it never finished."""
    type_line(b, command)
    seen, order, out = set(), [], []
    for t in range(0, limit, 100):
        lines = [ln for ln in screen(b) if ln.strip()]
        out = below(lines, command)
        for ln in out:
            if ln not in seen:
                seen.add(ln)
                order.append(ln)
        if any(done in ln for ln in seen) and lines and lines[-1].rstrip().endswith(prompt):
            return order, out, t
        b.frames(100)
    return order, out, -1


def listed(lines):
    """NAME.EXT, or NAME for a directory, for each entry of a listing."""
    names = set()
    for ln in lines:
        m = ENTRY.match(ln)
        if m:
            names.add(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
    return names


def main(argv):
    cart = next((a[6:] for a in argv if a.startswith("--sdx=")), "")
    if not cart:
        print("gem4xe-install: needs --sdx=CART")
        return 2
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    img = atr.ATRImage(256, 1440)
    atr.Sdfs.format(img, "HARDDISK")
    img.save(TARGET)
    syms = symfile.load(SYMS)
    gem_want = {n.split(">")[1] for _, n in mkcf.SYSTEM + mkcf.APPS if n.startswith("GEM>")}
    apps_want = {n.split(">")[1] for _, n in mkcf.APPS if n.startswith("APPS>")}

    emu = launch(tag="install", memsize="1088K", require_real_rom=False,
                 extra_args=["--cart", cart, "--disk", TARGET, "--disk", SYSTEM,
                             "--disk", APPS])
    b = emu.bridge
    try:
        # -- 1. SpartaDOS X at a blank D1: ------------------------------------
        t = wait_prompt(b, "D1:", limit=4000)
        if not check(t >= 0, "SpartaDOS X never came to its D1: prompt"):
            return 1
        print(f"  SpartaDOS X at D1: after {t} frames")
        type_line(b, "D2:")

        # -- 2. no drive named --------------------------------------------------
        lines, _, t = run(b, "-INSTALL", "Which drive?", "D2:", limit=3000)
        check(t >= 0, "-INSTALL with no drive did not say to name one")
        check(not any(">GEM>" in ln for ln in lines),
              "-INSTALL with no drive copied something")

        # -- 3. the system, then the applications --------------------------------
        lines, _, t = run(b, "-INSTALL D1:", "The system is on D1:", "D2:")
        check(t >= 0, "the system disk's INSTALL.BAT never finished")
        errors = [ln for ln in lines if ERROR.match(ln)]
        check(not errors, f"the system's install reported {errors}")
        print(f"  -INSTALL D1: from the system disk: {t} frames")
        type_line(b, "D3:")
        lines, _, t = run(b, "-INSTALL D1:", "The applications are on D1:", "D3:")
        check(t >= 0, "the applications disk's INSTALL.BAT never finished")
        errors = [ln for ln in lines if ERROR.match(ln)]
        check(not errors, f"the applications' install reported {errors}")
        print(f"  -INSTALL D1: from the applications disk: {t} frames")

        # A trailing > lists what is IN a directory; without it, the entry.
        for path, want, what in ((">GEM>", gem_want, "\\GEM\\"),
                                 (">APPS>", apps_want, "\\APPS\\"),
                                 ("", {"GEM", "APPS", "AUTOEXEC.BAT"}, "the root")):
            _, out, t = run(b, f"DIR D1:{path}", "FREE SECTORS", "D3:", limit=2000)
            got = listed(out) if t >= 0 else set()
            check(got == want, f"D1:'s {what} holds {sorted(got)}, not {sorted(want)}")
        print(f"  D1: holds \\GEM\\ ({len(gem_want)} files), \\APPS\\ "
              f"({len(apps_want)}) and AUTOEXEC.BAT")

        # -- 4. an upgrade: the system again, over itself ---------------------------
        type_line(b, "D2:")
        lines, _, t = run(b, "-INSTALL D1:", "The system is on D1:", "D2:")
        check(t >= 0, "the second install never finished")
        check(any("AUTOEXEC.BAT is kept" in ln for ln in lines),
              "the second install did not say it kept D1:AUTOEXEC.BAT")
        errors = [ln for ln in lines if ERROR.match(ln)]
        check(not errors, f"installing over an install reported {errors}")
        print(f"  -INSTALL D1: again, over itself: {t} frames, the AUTOEXEC.BAT kept")

        # -- 5. and it boots ----------------------------------------------------------
        b.ok("COLD_RESET")
        n, n_prev, still = 0, None, 0
        for f in range(50, 12000, 50):
            b.frames(50)
            if b.peek(syms["irq_cio_swap"]) not in (1, 3):
                continue                    # gem4xe is not running yet
            n = b.peek16(syms["app_calls"])
            if n > 0x1000:
                continue
            still = still + 1 if (n and n == n_prev) else 0
            n_prev = n
            if n >= FIRST_WAIT or still >= 100:
                break
        check(n >= FIRST_WAIT, f"GEM from D1: stopped at the desktop's call {n}, "
                               f"short of its first wait at {FIRST_WAIT}")
        procs = b.peek16(syms["proc_n"])
        # The desktop and EVERY accessory the applications disk installed:
        # CLOCK.ACC, CONTROL.ACC and CALC.ACC (tools/mkcf.py's APPS table).
        # The Desk menu has six slots since phase 47, so this number is the
        # media's to change and not the engine's -- if it moves, the disk
        # gained or lost an accessory.
        check(procs == 4, f"{procs} process(es) after booting D1:, not the desktop "
                          f"and the three accessories")
        check(b.peek16(syms["gem_bad"]) == 0, f"{b.peek16(syms['gem_bad'])} call(s) refused")
        check(b.peek(syms["irq_fault"]) == 0, f"irq_fault {b.peek(syms['irq_fault'])}")
        print(f"  a cold start from D1: reaches the desktop's first wait "
              f"(call {n}) with {procs} processes")
    finally:
        emu.stop()

    print(f"gem4xe-install: {'PASS' if not fails else 'FAIL'} -- the floppies "
          f"install onto a drive, and it boots, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
