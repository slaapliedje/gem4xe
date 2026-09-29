"""Options -> Install icon: the desk's drive icons as a person chooses them
(phase 74).

On the product disk, whose DOS's map gives the desk D1: and D2::

  1. Install icon with nothing selected, drive 5, label "apt": an icon
     called apt appears, and DISK D1: is still there -- the first change
     takes the set over from the desk as it stood, it does not replace it.
  2. Save desktop, then a COLD RESET: the machine boots, the desktop
     reads its DESKTOP.INF, and apt is on the desk again ("#M" lines).
  3. apt selected, Install icon, Remove: apt is gone and D1: stays.

The dialog's buttons are found by their text on the screen, not by
coordinates written down here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from deskrsc import OPTNMENU, IICNITEM, SAVEITEM       # noqa: E402
from m41_items import find_below              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "gem-shots.atr"))
OUT = os.path.join(ROOT, "build", "shots", "m43")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def has_icon(t, label):
    try:
        t.desk_icon(label)
        return True
    except KeyError:
        return False


def press(t, text, name):
    """Click the button that says text, in the dialog on the screen."""
    t.b.frames(20)
    shot = os.path.join(ROOT, "build", "shots", f"tour-m43-{name}.png")
    t.b.screenshot(shot)
    at = find_below(shot, text)
    if at is None:
        problems.append(f"no '{text}' on the screen ({shot})")
        return False
    t.click((at[0] + 4 * len(text), at[1] + 4))
    t.b.frames(40)
    t.settle()
    return True


def up(b, syms):
    boot(b, syms, OUT)
    poke16(b, syms["ptr_state"] + 6, PTR_NONE)
    t = Tour(b, syms, OUT)
    b.frames(20)
    t.settle()
    return t


def main():
    print("gem4xe-m43: Install icon")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    emu = launch(tag="m43", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        t = up(b, syms)
        check(has_icon(t, "DISK D1:") and not has_icon(t, "apt"),
              "the desk starts as the DOS's map: DISK D1:, and no apt")

        t.choose(OPTNMENU, IICNITEM)
        b.frames(30)
        t.settle()
        b.key("5")
        b.frames(4)
        b.key("TAB")
        b.frames(4)
        for k in "apt":
            b.key(k)
            b.frames(4)
        press(t, "Install", "install")
        check(has_icon(t, "apt") and has_icon(t, "DISK D1:"),
              "Install icon, drive 5, apt: the icon is there, beside DISK D1:")

        t.choose(OPTNMENU, SAVEITEM)
        b.frames(60)
        t.settle()
        b.key("RETURN")                         # the confirmation, if asked
        b.frames(120)
        t.settle()

        b.ok("COLD_RESET")
        t = up(b, syms)
        check(has_icon(t, "apt") and has_icon(t, "DISK D1:"),
              "saved, and after a cold reset apt is on the desk again")

        t.click(t.desk_icon("apt"))
        t.choose(OPTNMENU, IICNITEM)
        b.frames(30)
        t.settle()
        press(t, "Remove", "remove")
        check(not has_icon(t, "apt") and has_icon(t, "DISK D1:"),
              "apt selected, Remove: it is gone, and DISK D1: stays")
    finally:
        emu.stop()
    print(f"gem4xe-m43: {'FAIL' if problems else 'PASS'} -- Install icon, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
