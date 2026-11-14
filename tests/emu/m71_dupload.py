#!/usr/bin/env python3
"""Phase 166 gate: DUP's L and B (docs/run8-plan.md, step 5).

DUP.PRG asks the AES to run a plain Atari program (L) or the cartridge (B)
as the desktop's icons do, shel_write(SHW_EXEC), and quits: GEM ends, the
program or the cartridge runs, and GEM comes back -- here DUP again, since
build/dup-test.atr is the appliance floppy that starts DUP in the
desktop's place.  D2 is an SDFS holding:

  GAMES>PROG.XEX  prints PROGRAM RAN and returns (tests/emu/fdos_shell.py)
  README.TXT      not a binary file
  ODD.BIN         a binary file, but not of a kind GEM runs by its name

  1. L README.TXT: ERROR- 180, DOS 2's "not a binary file"; DUP stays.
  2. L ODD.BIN: GEM RUNS .COM .XEX .EXE AND .OBJ FILES ONLY; DUP stays.
  3. K: still NOT UNDER GEM.
  4. L D2:GAMES>PROG.XEX: PROGRAM RAN, then GEM and DUP's menu again.
  5. B: the emulator's XL has BASIC, so READY; DOS typed, and DUP again,
     with BASIC switched out.

    python3 tests/emu/m71_dupload.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import boot, poke16, PTR_NONE, SYMS  # noqa: E402
from fdos_shell import prog, lines, wait_for as wait_lines   # noqa: E402
from m67_run8 import gem_back                 # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "dup-test.atr")
OUT = os.path.join(BUILD, "shots", "dupload")
KEYS = {":": ("SEMICOLON", True), ",": ("COMMA", False), ".": ("PERIOD", False),
        ">": ("GREATER", False), " ": ("SPACE", False)}
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def make_d2(path):
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "DUPLOAD")
    fs.mkdir("GAMES")
    fs.add_file("GAMES>PROG.XEX", prog("PROGRAM RAN"))
    fs.add_file("README.TXT", b"read me\x9b")
    fs.add_file("ODD.BIN", prog("ODD RAN"))
    img.save(path)


def main():
    print("gem4xe-m71: DUP's L and B")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="m71-")
    d1, d2 = os.path.join(work, "d1.atr"), os.path.join(work, "d2.atr")
    shutil.copy(DISK, d1)
    make_d2(d2)
    emu = launch(tag="m71", memsize="1088K", extra_args=["--disk", d1, "--disk", d2])
    b = emu.bridge
    n = [0]

    def typ(s, wait=12):
        for c in s:
            if c.isalnum():
                b.key(c.upper())
            elif c == "\n":
                b.key("RETURN")
            else:
                k, sh = KEYS[c]
                b.key(k, shift=sh)
            b.frames(wait)

    def wait_for(text, name, most=20000, step=100):
        f = 0
        while f < most:
            b.frames(step)
            f += step
            p = os.path.join(OUT, f"wait-{name}.png")
            b.screenshot(p)
            if find_text(p, text) is not None:
                n[0] += 1
                q = os.path.join(OUT, f"{n[0]:02d}-{name}.png")
                os.replace(p, q)
                return q
        return None

    def dup_up(name):
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        return check(wait_for("SELECT ITEM", name) is not None, f"DUP's menu ({name})")

    try:
        if not dup_up("menu"):
            return 1
        typ("L")
        check(wait_for("LOAD FROM WHAT FILE?", "lask") is not None, "L asks LOAD FROM WHAT FILE?")
        typ("D2:README.TXT\n")
        check(wait_for("ERROR- 180", "notbin") is not None,
              "L of a text file: ERROR- 180 (not a binary file)")
        typ("L")
        b.frames(30)
        typ("D2:ODD.BIN\n")
        check(wait_for("FILES ONLY", "notplain") is not None,
              "L of ODD.BIN: GEM runs .COM .XEX .EXE and .OBJ files only")
        typ("K")
        check(wait_for("NOT UNDER GEM", "k") is not None, "K is still refused")
        print("  L's two refusals and K: DUP stayed")

        typ("L")
        b.frames(30)
        typ("D2:GAMES>PROG.XEX\n")
        f = wait_lines(b, lambda ls: any("PROGRAM RAN" in ln for ln in ls), 20000)
        p = os.path.join(OUT, "prog-ran.png")
        b.screenshot(p)
        check(f >= 0, f"L D2:GAMES>PROG.XEX: PROGRAM RAN ({p}): {lines(b)[-3:]}")
        check(gem_back(b, syms) >= 0, "...and GEM came back")
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        if not check(wait_for("SELECT ITEM", "back1") is not None, "...with DUP's menu"):
            return 1

        typ("B")
        f = wait_lines(b, lambda ls: any(ln.strip() == "READY" for ln in ls), 20000)
        p = os.path.join(OUT, "basic.png")
        b.screenshot(p)
        if check(f >= 0, f"B: BASIC's READY ({p}): {lines(b)[-3:]}"):
            typ("DOS\n", wait=4)
            check(gem_back(b, syms) >= 0, "...DOS, and GEM came back")
            poke16(b, syms["ptr_state"] + 6, PTR_NONE)
            check(wait_for("SELECT ITEM", "back2") is not None, "...with DUP's menu")
            check(b.peek(0xD301) & 0x02,
                  f"BASIC switched out again under GEM: PORTB {b.peek(0xD301):#04x}")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m71: {'PASS' if not problems else 'FAIL'} -- DUP's L and B, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
