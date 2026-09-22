"""A control panel extension: loaded, entered, published, kept.

A CPX is the shape XCONTROL made: the HOST owns the window and the event
loop, the MODULE owns the dialog, and they meet at a vtable the module
publishes when it loads (src/app/cpx.h).  This gate proves the meeting
point, which is the part that can go silently wrong.

WHAT IT CHECKS, and why each would otherwise be invisible:

  IT LOADED.  sh_ncpx is 1 and sh_cpxbad is 0.  A scan that finds
  nothing, or a module that declines, leaves the machine working
  perfectly and the panel simply empty.

  IT FILLED THE HEADER, AND ITS DATA WAS REAL WHEN IT DID.  The title in
  the slot is "Test CPX" -- written by cpx_init, across a bank boundary,
  into memory the SHELL owns.  That is also what says the module was
  entered through its own crt: a program's initialised data is installed
  by data_init_table and is NOT in the image, so a module whose cpx_init
  had been called straight through a far pointer would have written
  whatever was in that memory before.  The pointer call compiles to a
  proper long-indirect jsl and would have looked like it worked.

  IT STAYED.  The permanent floor moved by the module's whole near
  region, measured against the same system with no module on the disk.
  A module that was loaded, entered and then released would pass every
  check above and leave a vtable pointing into memory the next program
  takes.

WHAT IT DOES NOT CHECK YET, said here rather than left to be assumed:
calling back INTO the module through the published vtable.  That needs
an application-visible way to ask the AES for a module's CPXINFO, which
is the panel's API and a decision of its own -- appl_getinfo has a
subject mechanism made for exactly this question and is the likely
answer.  The runner cannot stand in: it is blocked inside the shell loop,
which is what loaded the module in the first place.  Until that exists
this gate proves the module is there and correct, not that it can be
driven.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, symfile                      # noqa: E402
from m7_form import poke16, NOT_STARTED, STATUS, ST_GO, SYMS as M3_SYMS  # noqa: E402
from m4_aes import PRELUDE                  # noqa: E402
from m12_file import Runner                 # noqa: E402
from m14_sparta import boot                 # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m35-boot.atr"))
BASE = os.path.abspath(os.path.join(ROOT, "build", "m14-boot.atr"))
SYMS = symfile.load(M3_SYMS)
MOD_SYM = os.path.join(ROOT, "build", "m35_cpx.sym")

M35_SIG = 0x3535
WANT_TITLE = "Test CPX"
CPXE_HDR = 20                    # src/aes/shel.c: info, the file name,
                                 # then the header.  tests/host/test_cpx.py
                                 # holds all three writings of this to one
                                 # number; this one is the fourth, from the
                                 # running machine.
HDR_TITLE = 122                  # src/app/cpx.h's map

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def start(b):
    """Boot and run the shell loop until the stand-in desktop is up."""
    t, st = boot(b)
    if st is None:
        return None
    r = Runner(b, SYMS)
    r.run(PRELUDE)
    script = aesref.encode(PRELUDE + [(SHELL, (), ())], 0)
    b.memload(r.sa, b"".join(
        (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
        for x in script))
    poke16(b, r.count, NOT_STARTED)
    b.poke(STATUS + ST_GO, 1)
    return (r, poll(b, SYMS["sh_runs"], 1))


def main():
    print("gem4xe-m35: a control panel extension")
    for s in ("sh_ncpx", "sh_cpxbad", "app_near"):
        if s not in SYMS:
            print(f"  FAIL: build/m3.sym has no {s}")
            return 1

    emu = launch(tag="m35", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        got = start(b)
        if got is None or got[1] < 0:
            print("  FAIL: the stand-in desktop never started")
            return 1
        r = got[0]
        b.frames(60)

        n = b.peek16(SYMS["sh_ncpx"])
        bad = b.peek16(SYMS["sh_cpxbad"])
        print(f"  {n} module(s) loaded, {bad} refused")
        check(n == 1, f"sh_ncpx is {n}, not the 1 module on the disk")
        check(bad == 0, f"{bad} module(s) were found and refused")
        if n != 1:
            return 1

        # The header the module wrote into the shell's table.
        hdr = b.peek24(SYMS["sh_cpx_far"]) if "sh_cpx_far" in SYMS else 0
        title = ""
        if hdr:
            raw = bytes(b.memdump(hdr + CPXE_HDR + HDR_TITLE, 18))
            title = raw.split(b"\0")[0].decode("latin-1")
        print(f"  its header says {title!r}")
        check(title == WANT_TITLE,
              f"the title in the slot is {title!r}, not {WANT_TITLE!r}")

        floor = b.peek16(SYMS["app_near"])
        print(f"  the permanent floor is ${floor:04X}")
    finally:
        emu.stop()

    # ...and the same system with no module on the disk, so that "it
    # stayed" is measured rather than inferred from a counter.
    emu = launch(tag="m35base", memsize="1088K", extra_args=["--disk", BASE])
    b = emu.bridge
    try:
        got = start(b)
        check(got is not None and got[1] >= 0,
              "the stand-in desktop never started on the base disk")
        b.frames(60)
        n0 = b.peek16(SYMS["sh_ncpx"])
        base_floor = b.peek16(SYMS["app_near"])
        print(f"  without a module: {n0} loaded, floor ${base_floor:04X}")
        check(n0 == 0, f"the disk with no module loaded {n0}")
        moved = floor - base_floor
        print(f"  the floor moved {moved} bytes, which is the module kept")
        check(moved >= 1536,
              f"the floor moved {moved} bytes: the module did not stay "
              f"(its near region is 1536 by the Makefile)")
    finally:
        emu.stop()

    print(f"\ngem4xe-m35: {'PASS' if not problems else 'FAIL'} -- a control "
          f"panel extension, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
