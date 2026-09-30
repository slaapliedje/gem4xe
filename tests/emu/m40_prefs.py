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
from farheap import far_heap  # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK   # noqa: E402
from deskrsc import OPTNMENU, PREFITEM        # noqa: E402

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
        # the far heap's blocks: a resource loaded is one more, and freed
        # the table is what it was (src/sys/farmem.c, phase 79)
        far = lambda: tuple((a, n) for a, n, _ in far_heap(b, syms).blocks)  # noqa: E731
        pool = lambda: b.peek16(syms["pool_brk"])             # noqa: E731
        far0, pool0 = far(), pool()

        t.choose(OPTNMENU, PREFITEM)
        b.frames(20)
        t.settle()
        far1 = far()
        check(len(far1) > len(far0), f"the chooser's resource was loaded "
                           f"(far blocks {len(far0)} -> {len(far1)})")
        b.key("RETURN")                         # OK: the default
        t.settle()
        check(far() == far0 and pool() == pool0,
              f"...and freed: {len(far())} far blocks, pool ${pool():04X}, as "
              f"before ({len(far0)}, ${pool0:04X})")
    finally:
        emu.stop()
    print(f"gem4xe-m40: {'FAIL' if problems else 'PASS'} -- Set preferences, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
