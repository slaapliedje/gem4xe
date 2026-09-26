#!/usr/bin/env python3
"""Phase 60 gate: the desktop driven from the keyboard alone.

The product booted as test-boot and the screenshot tour boot it, and then
nothing but keys -- the TOS desktop's shortcuts, src/desk/desktop.c
hndl_kbd -- each checked by what it did rather than by a picture:

    1        opens drive A's window                  a window, holding GEM
    ^N       File -> New folder, KEYS typed, RETURN  KEYS in the listing
    down     (CONTROL and =) a line                  KEYS moves up
    ^D       File -> Delete of the selection, RETURN KEYS gone again
    ^U       File -> Close window                    no window
    ^Q       File -> Quit                            the shell asked to shut down

A dialog is given ten frames to reach its wait before a key goes to it:
a key sent sooner is typeahead, which form_do flushes (tests/emu/m19).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import shots                                  # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK   # noqa: E402

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    else:
        print(f"  ok: {what}")
    return ok


def windows(t):
    """Folder windows open: the window roots beside the desk that hold
    anything (tests/emu/shots.py Tour.item)."""
    tree = t.g_screen()
    return sum(1 for top in shots.children(t.b, tree, 0)
               if top != shots.DROOT and shots.children(t.b, tree, top))


def listed(t, name):
    try:
        t.item(name)
        return True
    except KeyError:
        return False


def main():
    print("gem4xe-m38: the desktop from the keyboard")
    syms = symfile.load(SYMS)
    out = os.path.join(HERE, "..", "..", "build", "shots", "m38")
    os.makedirs(out, exist_ok=True)
    emu = launch(tag="m38", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(10)
        check(windows(t) == 0, "the desk comes up with no window")

        b.key("1")
        t.settle()
        check(windows(t) == 1 and listed(t, "GEM"),
              "1 opens drive A's window, and GEM is in it")

        b.key("N", ctrl=True)
        b.frames(10)
        t.settle()
        for c in "KEYS":
            b.key(c)
            b.frames(3)
        b.key("RETURN")
        t.settle()
        check(listed(t, "KEYS"), "^N makes a folder, named at the keyboard")

        if listed(t, "KEYS"):
            # KEYS is the third row, below the window's edge: the down
            # arrow -- CONTROL and = on this keyboard -- scrolls a line
            y0 = t.item("KEYS")[1]
            b.key("EQUALS", ctrl=True)
            t.settle()
            y1 = t.item("KEYS")[1]
            check(y1 < y0, f"the down arrow scrolls the window a line "
                           f"(KEYS from y {y0} to {y1})")
            t.click(t.item("KEYS"))
            b.key("D", ctrl=True)
            b.frames(10)
            t.settle()
            b.key("RETURN")
            t.settle()
            check(not listed(t, "KEYS"), "^D deletes the selection")

        b.key("U", ctrl=True)
        t.settle()
        check(windows(t) == 0, "^U closes the window")

        # sh_doexec is the shell's pending request (src/aes/shel.c): -1
        # while the desktop runs, SHW_SHUTDOWN (4) once it has asked to end
        check(b.peek16(syms["sh_doexec"]) == 0xFFFF,
              "the desktop is still running before ^Q")
        b.key("Q", ctrl=True)
        t.settle()
        b.frames(100)
        check(b.peek16(syms["sh_doexec"]) == 4, "^Q quits: the shell was asked "
              "to shut down")
    finally:
        emu.stop()
    print(f"gem4xe-m38: {'FAIL' if problems else 'PASS'} -- the desktop from "
          f"the keyboard, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
