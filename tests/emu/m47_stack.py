#!/usr/bin/env python3
"""A program whose stack leaves its own memory is stopped, and its parent
carries on (src/sys/abi.c, docs/phase114.md).

build/m47-boot.atr: DOS 2, GEM, and two programs.  The desktop is
src/m47_parent.c; it Pexecs CHILD.PRG (src/m47_child.c), which recurses
200 bytes a level on a 384-byte stack and calls the AES at every level.

  - gem4xe stops the child at the first call it makes from below its
    floor: gem_stack_stops goes to 1, and the child never returns 7;
  - Pexec gives the parent GEM_STOPPED (-9), and the parent's own twenty
    calls afterwards are served -- its floor, not the child's;
  - the parent returns 3 (both of those), which the shell keeps in
    sh_lastret, and nothing has faulted.

Without the check the child's stack runs on through its direct page and
into whatever is below it.

    python3 tests/emu/m47_stack.py
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
import mkg4a                                  # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "m47-boot.atr")
PARENT = os.path.join(BUILD, "m47_parent.g4a")
# CTX's floor, after sp 2, save 4, len 2, deep 2, entry 4, live 2, pb 4,
# api_sp 2, which 2, depth 2, owner 2 (src/sys/ctx.h; the compiler pads
# nothing)
CTX_FLOOR = 28
FLOOR_OFF = 0x40                    # src/sys/ctx.h CTX_FLOOR: past the registers


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def main():
    print("gem4xe-m47: a runaway stack is stopped")
    g = symfile.load(os.path.join(BUILD, "gem.sym"))
    fails = []

    def check(ok, what):
        print(f"  {'ok' if ok else 'FAIL'}: {what}")
        if not ok:
            fails.append(what)

    psym = symfile.load(os.path.join(BUILD, "m47_parent.sym"))
    link_near, = struct.unpack("<H", mkg4a.read_file(PARENT)[4:6])
    emu = launch(tag="m47", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        # The parent's memory, found through the floor gem4xe keeps for
        # the context it runs in (src/sys/ctx.h) -- its own again after
        # its child's, which is half of what is being tested.  m47_done
        # says the result is written: a mark, because before GEM.COM has
        # started every one of these addresses holds what memory did.
        f, base, done = 0, 0, 0
        while f < 40000:
            b.frames(200)
            f += 200
            root = b.peek16(g["ctx_root"])
            if 0x2000 <= root < 0x8000:
                fl = b.peek16(root + CTX_FLOOR)
                if 0x4000 < fl < 0x8000 and fl & 0xFF == FLOOR_OFF:
                    base = fl - FLOOR_OFF
                    done = b.peek16(psym["m47_done"] - link_near + base)
                    if done == 0x4D47:
                        break
        check(done == 0x4D47, f"the parent ran to its end ({f} frames; "
              f"near base ${base:04X})")
        stops = b.peek(g["gem_stack_stops"])
        ret = b.peek16(psym["m47_result"] - link_near + base)
        pex = s16(b.peek16(psym["m47_pexec"] - link_near + base))
        fault = b.peek(g["irq_fault"])
        print(f"  gem_stack_stops {stops}, Pexec {pex}, result {ret}, irq_fault {fault}")
        check(stops == 1, f"the child was stopped once (gem_stack_stops {stops})")
        check(pex == -9, f"Pexec gave the parent GEM_STOPPED (-9), not {pex}")
        check(ret & 2 == 2, "the parent's twenty calls after it were served")
        check(fault == 0, f"nothing faulted (irq_fault {fault})")
    finally:
        emu.stop()
    print(f"gem4xe-m47: {'FAIL' if fails else 'PASS'} -- a runaway stack is "
          f"stopped and its parent carries on, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
