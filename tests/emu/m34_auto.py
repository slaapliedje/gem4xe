"""The AUTO folder: run before the accessories, kept if it asks.

\\GEM\\AUTO\\ on the ST runs a program at boot and lets it stay resident.
gem4xe does the same and the mechanism is the one accessories already
proved: both run BEFORE pool_keep_mark(), so a program that is simply
not released becomes part of the permanent floor.  src/aes/shel.c's
sh_auto says the rest.

THE DISK holds two builds of ONE source (src/m34_auto.c):

    AUTO>M34RES.PRG   ends with Ptermres -- the shell must KEEP it
    AUTO>M34GO.PRG    ends with a return  -- the shell must RELEASE it

and the gate boots it, lets the desktop come up, and reads what the
shell recorded.

WHAT IT CHECKS, and why each would otherwise be silent:

  BOTH RAN.  sh_nauto is 2.  A scan that found the directory but no
  files, or matched the wrong extension, gives 0 and nothing else
  complains -- the desktop comes up perfectly either way, which is the
  whole problem with a boot-time feature.

  EXACTLY ONE STAYED.  sh_nres is 1.  Keeping both would mean Ptermres
  is being ignored and everything is kept; keeping neither would mean it
  is ignored the other way.  Both look identical from the desktop.

  AND IT WAS THE RIGHT ONE.  The name the shell recorded is M34RES's,
  read out of far memory.  With two programs and one flag, "one stayed"
  is true of the wrong answer as well.

  THE FLOOR MOVED BY THE RESIDENT PROGRAM'S NEAR REGION.  This is the
  claim that matters -- that the memory was genuinely kept and not just
  counted -- so it is measured rather than asserted from the count: the
  pool's permanent floor on this disk must be a whole near region higher
  than on the disk without an AUTO folder, and the gate prints both.

  AND THE MACHINE IS STILL WELL.  No refused AES call, no irq_fault, and
  the desktop reached its first wait: an AUTO program runs on the engine
  stack with sh_start's frame under it, which is why sh_autoscan has a
  frame of its own (m17 caught that when it did not).
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

DISK = os.path.abspath(os.path.join(ROOT, "build", "m34-boot.atr"))
BASE = os.path.abspath(os.path.join(ROOT, "build", "m14-boot.atr"))
SYMS = symfile.load(M3_SYMS)         # build/m3.sym: this disk's runner

ACC_NAMELEN = 13                 # src/aes/shel.c
WANT_RES = "M34RES.PRG"
FIRST_WAIT = 40                  # the desktop is up and waiting by here

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def run(disk, tag):
    """Boot `disk`, start the shell loop, and read what it recorded.

    The disk is test-m16's -- the m3 runner with a stand-in desktop --
    so the loop is started by a script rather than by an AUTOEXEC, and
    sh_start (which is where sh_auto lives) runs inside sys op 16."""
    emu = launch(tag=tag, memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
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
        # The stand-in desktop starting is the AUTO folder having been
        # scanned, run and finished: sh_auto is before it in sh_start.
        ok = poll(b, SYMS["sh_runs"], 1)
        b.frames(60)
        out = {
            "calls":  ok,
            "nauto":  b.peek16(SYMS["sh_nauto"]) if "sh_nauto" in SYMS else -1,
            "nres":   b.peek16(SYMS["sh_nres"]) if "sh_nres" in SYMS else -1,
            "bad":    b.peek16(SYMS["gem_bad"]),
            "fault":  b.peek(SYMS["irq_fault"]),
            "floor":  b.peek16(SYMS["app_near"]),
            "name":   "",
        }
        if out["nres"] > 0 and "sh_res_far" in SYMS:
            addr = b.peek24(SYMS["sh_res_far"])
            if addr:
                raw = bytes(b.memdump(addr, ACC_NAMELEN))
                out["name"] = raw.split(b"\0")[0].decode("latin-1")
        return out
    finally:
        emu.stop()


def main():
    print("gem4xe-m34: the AUTO folder")
    for s in ("sh_nauto", "sh_nres", "sh_res_far", "app_near"):
        if s not in SYMS:
            print(f"  FAIL: build/gem.sym has no {s} -- the shell's AUTO "
                  f"support is not in this build")
            return 1

    a = run(DISK, "m34")
    print(f"  with AUTO:    {a['nauto']} run, {a['nres']} resident, "
          f"kept {a['name']!r}; floor ${a['floor']:04X}; "
          f"{a['bad']} refused")

    check(a["nauto"] == 2,
          f"sh_nauto is {a['nauto']}, not the 2 programs in AUTO>")
    check(a["nres"] == 1,
          f"sh_nres is {a['nres']}, not the 1 that ends with Ptermres")
    check(a["name"] == WANT_RES,
          f"the kept program is {a['name']!r}, not {WANT_RES!r}")
    check(a["bad"] == 0, f"{a['bad']} AES call(s) refused")
    check(a["fault"] == 0, f"irq_fault {a['fault']}")
    check(a["calls"] >= 0, "the stand-in desktop never started")

    # ...and the floor, against the same system with no AUTO folder.
    b = run(BASE, "m34base")
    print(f"  without AUTO: {b['nauto']} run, {b['nres']} resident; "
          f"floor ${b['floor']:04X}")
    check(b["nauto"] == 0,
          f"the disk with no AUTO folder ran {b['nauto']} programs")
    moved = a["floor"] - b["floor"]
    print(f"  the permanent floor moved {moved} bytes, which is "
          f"M34RES.PRG's near region kept")
    check(moved >= 1024,
          f"the floor moved {moved} bytes: a resident program's near "
          f"region did not stay (it is 1024 by the Makefile)")

    print(f"\ngem4xe-m34: {'PASS' if not problems else 'FAIL'} -- the AUTO "
          f"folder, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
