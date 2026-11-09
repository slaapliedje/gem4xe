"""Control panel extensions: listed from their headers, and loaded only
when they ask.

A CPX is the shape XCONTROL made: the HOST owns the window and the event
loop, the MODULE owns the dialog, and they meet at a vtable the module
publishes when it loads (src/app/cpx.h).  Since phase 133 the file is the
module's 512-byte header and then the module, and the AES lists a module
by READING its header -- nothing runs to be listed -- and loads at boot
only the ones whose flags ask (src/aes/shel.c, sh_cpx).

THE DISK carries nine *.CPX: M35B.CPX, whose header says CPX_BOOTINIT;
M35.CPX and T1-T6.CPX, the same module under a header with no flags --
seven, more than the six there used to be room for; and BAD.CPX, a bare
.G4A with no header at all.

WHAT IT CHECKS, and why each would otherwise be invisible:

  EIGHT LISTED, ONE REFUSED.  sh_ncpx is 8 and sh_cpxbad is 1.  A scan
  that stopped at six, or listed a file with no header, leaves the
  machine working perfectly and the panel quietly wrong.

  THE TITLES CAME FROM THE FILES.  One slot says "Boot CPX" and seven
  say "Test CPX", read from the headers' title fields -- one module
  under two headers, which only a header in front of the code allows.

  ONE LOADED AT BOOT, AND IT WENT.  sh_cpxruns is 1: the module that
  asked was run, and the seven that did not were not.  Since phase 118 a
  module that is not CPX_RESIDENT is freed once the panel has
  boot-initialised it (there is no panel on this disk, so nothing calls
  it), so sh_cpxdrops is 1, every slot's vtable is 0 -- a vtable left
  pointing into freed memory is what the next program would overwrite --
  and the desktop's near region lands exactly where it does on the same
  system with no module on the disk: nothing of any module's was kept.
  Loading one when it is opened is test-m44's, which opens General and
  Color from the panel.

WHAT IT DOES NOT CHECK, said here rather than left to be assumed:
calling back INTO a module through its vtable.  The runner cannot stand
in for the panel -- it is blocked inside the shell loop, which is what
loaded the module -- so that is the panel's gates' (test-m44, make shots).
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

WANT = {"Boot CPX": 1, "Test CPX": 7}     # titles, from the headers
HDR_TITLE = 122                  # src/app/cpx.h's map
SHEL_C = os.path.join(ROOT, "src", "aes", "shel.c")


def define(name):
    """A number out of src/aes/shel.c, where the table is laid out: the
    owners in front, then the slots.  Read rather than restated, since a
    restated layout is a second place for it to drift."""
    import re
    src = open(SHEL_C).read()
    m = re.search(rf"^#define\s+{name}\s+(\S+)", src, re.M)
    return int(m.group(1), 0)


CPX_MAX = define("CPX_MAX")
CPXE_HDR = define("CPXE_HDR")
CPXE_SIZE = CPXE_HDR + define("CPX_HDR_SZ")

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
    for s in ("sh_ncpx", "sh_cpxbad", "app_near", "sh_cpxdrops", "sh_cpxruns"):
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
        print(f"  {n} module(s) listed, {bad} refused")
        check(n == 8, f"sh_ncpx is {n}, not the 8 modules with headers")
        check(bad == 1, f"sh_cpxbad is {bad}, not 1: BAD.CPX has no header")
        if n < 1:
            return 1

        # The headers, as read off the front of each file into the table.
        far = b.peek24(SYMS["sh_cpx_far"]) if "sh_cpx_far" in SYMS else 0
        titles, infos = {}, []
        for i in range(n if far else 0):
            slot = far + CPX_MAX + i * CPXE_SIZE
            raw = bytes(b.memdump(slot + CPXE_HDR + HDR_TITLE, 18))
            t = raw.split(b"\0")[0].decode("latin-1")
            titles[t] = titles.get(t, 0) + 1
            infos.append(b.peek24(slot))
        print(f"  their headers say {titles}")
        check(titles == WANT, f"the titles in the table are {titles}, not {WANT}")

        runs = b.peek16(SYMS["sh_cpxruns"])
        drops = b.peek16(SYMS["sh_cpxdrops"])
        print(f"  {runs} loaded at boot, {drops} freed after it; vtables "
              f"{' '.join(f'${v:06X}' for v in infos)}")
        check(runs == 1, f"sh_cpxruns is {runs}, not 1: only M35B.CPX asks")
        check(drops == 1, f"sh_cpxdrops is {drops}, not 1")
        check(infos and not any(infos),
              "a slot's vtable is not 0: a module was kept, or left a "
              "pointer behind")
        floor = b.peek16(SYMS["app_near"])
        print(f"  the desktop's near region is at ${floor:04X}")
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
        print(f"  without a module: the desktop at ${base_floor:04X}")
        check(floor == base_floor,
              f"the desktop is at ${floor:04X} with the module freed and "
              f"${base_floor:04X} with none: something of the module's stayed")
    finally:
        emu.stop()

    print(f"\ngem4xe-m35: {'PASS' if not problems else 'FAIL'} -- a control "
          f"panel extension, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
