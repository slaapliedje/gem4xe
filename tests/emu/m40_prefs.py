#!/usr/bin/env python3
"""0.8.1's gate: Options -> Set preferences loads its resource.

PREFS.RSC is a NESTED resource, loaded over the desktop's while the
chooser is up.  From the control panel's arrival until 0.8.1 it could not
be: the AES runs control panel modules in the process record the desktop
is started in, GENERAL.CPX loads GENERAL.RSC there and keeps it, and that
record went on claiming it -- so DESKTOP.RSC was already the nested one
and a third was refused, reported as "PREFS.RSC is not on the disk".  Set
preferences, File -> DOS command and a .TTP's parameters all went that
way, on every disk with GENERAL.CPX (src/aes/rsrc.c rs_hold).

The witness is the far heap, not a picture: the desktop is a large-data
program, so the resource is streamed into FAR memory while the dialog is
up, and the refused load allocates nothing there.  So: the heap's cursor
rises while the chooser is open, and both heaps are back where they were
once it is closed.  Seen red on 0.8 itself.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK   # noqa: E402
from deskrsc import OPTNMENU, PREFITEM        # noqa: E402

FARMEM_BRK = 8          # src/sys/farmem.h: four bytes, a LONG, then brk
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)


def main():
    print("gem4xe-m40: Set preferences loads PREFS.RSC")
    syms = symfile.load(SYMS)
    out = os.path.join(HERE, "..", "..", "build", "shots", "m40")
    os.makedirs(out, exist_ok=True)
    emu = launch(tag="m40", memsize="1088K",
                 extra_args=["--disk", os.path.abspath(DISK)])
    b = emu.bridge
    try:
        boot(b, syms, out)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, out)
        b.frames(10)
        far = lambda: b.peek24(syms["farmem"] + FARMEM_BRK)   # noqa: E731
        pool = lambda: b.peek16(syms["pool_brk"])             # noqa: E731
        far0, pool0 = far(), pool()

        t.choose(OPTNMENU, PREFITEM)
        b.frames(20)
        t.settle()
        far1 = far()
        check(far1 > far0, f"the chooser's resource was loaded "
                           f"(far heap ${far0:06X} -> ${far1:06X})")
        b.key("RETURN")                         # OK: the default
        t.settle()
        check(far() == far0 and pool() == pool0,
              f"...and freed: far ${far():06X}, pool ${pool():04X}, as "
              f"before (${far0:06X}, ${pool0:04X})")
    finally:
        emu.stop()
    print(f"gem4xe-m40: {'FAIL' if problems else 'PASS'} -- Set preferences, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
