"""Options -> Install devices: an icon for every drive that answers, and
none for one that does not (EmuTOS's ins_devices, over gem4xe's Dprobe).

Two machines, each booted with D1: only:

  DOS 2 (gem-shots.atr).  DOS 2 keeps a map of the drives it serves,
     and the desk starts with what it says, D1: and D2:.  Nothing is
     attached as D2:, so Install devices takes its icon away.
  SpartaDOS X from its cartridge (gem-sdx.atr).  A SpartaDOS keeps no
     map, so the desk starts with a guess, D1: and D2:.  A disk is
     attached as D3: once the desk is up, as a person would mount one
     from a loader; Install devices gives it an icon and takes D2:'s
     away.

Then Save desktop and a cold reset: the set comes back, without asking
the drives again (DESKTOP.INF's "#M" lines).  How long the asking took
is printed: every absent drive costs the OS's retries.

    python3 tests/emu/m46_devices.py [SDX-CARTRIDGE]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from deskrsc import OPTNMENU, IDSKITEM, SAVEITEM       # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DOS2 = os.path.join(BUILD, "gem-boot.atr")
SPARTA = os.path.join(BUILD, "gem-shots.atr")      # SpartaDOS 3.2
SDX = os.path.join(BUILD, "gem-sdx.atr")
D3 = os.path.join(BUILD, "gem-apps.atr")      # any disk will do
OUT = os.path.join(BUILD, "shots", "m46")

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def icons(t):
    out = []
    for n in range(1, 9):
        try:
            t.desk_icon(f"DISK D{n}:")
            out.append(n)
        except KeyError:
            pass
    return out


def up(b, syms):
    boot(b, syms, OUT)
    poke16(b, syms["ptr_state"] + 6, PTR_NONE)
    t = Tour(b, syms, OUT)
    b.frames(20)
    t.settle()
    return t


def install_devices(t, b, syms):
    """The item chosen, and waited out: the asking makes no AES calls, so
    a desktop that looks idle may be in the middle of it -- the answer
    being kept (gemdos.c gd_probed) is what says it is done."""
    b.memload(syms["gd_probed"], [0, 0])
    start = time.monotonic()
    t.choose(OPTNMENU, IDSKITEM)
    frames = 0
    while frames < 6000 and b.peek16(syms["gd_probed"]) == 0:
        b.frames(30)
        frames += 30
    t.settle()
    print(f"  Install devices: the drives answered within {frames} frames "
          f"({frames / 50:.1f} s; {time.monotonic() - start:.1f} s here)")


def run(name, disk, cart, attach, want_before, want_after, syms):
    print(f"{name}:")
    args = ["--disk", disk] + (["--cart", cart] if cart else [])
    emu = launch(tag="m46" + name[:3].lower(), memsize="1088K", extra_args=args)
    b = emu.bridge
    try:
        t = up(b, syms)
        got = icons(t)
        check(got == want_before, f"{name}: the desk starts with drives "
              f"{got}, expected {want_before}")
        if attach:
            b.mount(2, attach)                  # D3:
            b.frames(10)
        install_devices(t, b, syms)
        got = icons(t)
        check(got == want_after, f"{name}: after Install devices the "
              f"drives are {got}, expected {want_after}")

        t.choose(OPTNMENU, SAVEITEM)
        b.frames(60)
        t.settle()
        b.key("RETURN")                         # the confirmation, if asked
        b.frames(120)
        t.settle()
        b.ok("COLD_RESET")
        t = up(b, syms)
        got = icons(t)
        check(got == want_after, f"{name}: saved, and after a cold reset "
              f"the drives are {got}, expected {want_after}")
    finally:
        emu.stop()


def main(argv):
    print("gem4xe-m46: Install devices")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    run("DOS 2", DOS2, None, None, [1, 2], [1], syms)
    run("SpartaDOS 3.2", SPARTA, None, None, [1, 2], [1], syms)
    cart = argv[1] if len(argv) > 1 else os.environ.get("SDX_CART")
    if cart:
        run("SDX", SDX, cart, D3, [1, 2], [1, 3], syms)
    else:
        print("  SDX: not run, no cartridge fixture ([spartados].sdx_cart)")
    print(f"gem4xe-m46: {'FAIL' if problems else 'PASS'} -- Install devices, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
