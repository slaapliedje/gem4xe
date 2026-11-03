#!/usr/bin/env python3
"""The system floppy boots by itself: no SpartaDOS X, only the disk's own
DOS, G4DOS (src/fdos.s, src/fdboot.s, docs/fdos.md).

build/gem-sdx.atr in D1: and build/gem-apps.atr in D2:, on a machine
with no SDX cartridge -- an emulator's default, or a machine without one:

  1. the boot sectors load G4DOS.SYS, which loads GEM.COM, and the desk
     comes up: gem4xe has started, GEMDOS knows the DOS for G4DOS, and
     its disks have folders -- gem4xe's own SDFS engine serves them
     (src/sys/sdcio.h), G4DOS's sector entry under it;
  2. D1:'s window is the disk's root, with the system's folder GEM in it
     and none of the system's files, and GEM opened lists DESKTOP.PRG and
     the rest: a folder, through the engine;
  3. Options > Save desktop saves: no alert, and when the run is over
     the emulator's working copy of the disk has DESKTOP.INF in its root,
     the layout gem4xe wrote, and tools/atr.py's check finds the bitmap,
     the chains and the free count in agreement -- the engine wrote it;
  4. File -> DOS command runs G4DOS's own commands (src/sys/doscmd.c,
     docs/g4dos-plan.md step 4): `ls -l` of the system's folder prints
     exactly what tools/atr.py says the folder holds, drawn in the
     command's window, and a `cp` writes a copy the working disk has
     afterwards, byte for byte;
  5. D2:'s window has \\APPS\\, and EDIT.PRG double-clicked in it RUNS: a
     program loaded out of a folder on the second drive.  EDIT given no
     file asks for one, so the file selector is what proves it started.

    python3 tests/emu/fdos_boot.py
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_FULLER, W_CLOSER         # noqa: E402
from deskrsc import OPTNMENU, SAVEITEM, FILEMENU, CMDITEM   # noqa: E402
from m14_sparta import KEYS                   # noqa: E402
from m17_desktop import header, DESKTOP, DESK_SYM   # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "fdos")

problems = []
PAINT, STACK_MARGIN = 0xA5, 128
CMD_TEXT = 64 + 4 + 48          # the command's text in the desktop's far
                                # buffer, after its title and the path of a
                                # file shown (deskcmd.c: LEN_ZCMD + 4 +
                                # LEN_ZPATH)
LS = "ls -l >gem"               # SpartaDOS's separator: '/' is the host test's
CP = "cp >gem>gem4xe.cfg cmd.cfg"


def stack_range():
    """GEM.COM's engine stack, from its link map: every application's GEM
    call runs on it (src/sys/abi.s), so G4DOS's disks, served by the engine
    in C (src/sys/sdcio.c), cost their depth here."""
    stk = [ln for ln in open(os.path.join(BUILD, "gem.map"))
           if ln.startswith("stack ")][0].split()
    return tuple(int(x, 16) for x in stk[1].split("-"))


def reg(v):
    return int(v.lstrip("$"), 16) if isinstance(v, str) else int(v or 0)


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def listing(fs, folder):
    """What `ls -l` prints of a folder, from the disk image: a line an
    entry, NAME.EXT (a folder's with a '/') to thirteen columns, the size
    to seven, then the date and time (src/sys/doscmd.c, ls_entry)."""
    out = b""
    for e in fs.entries(folder):
        name = e.filename + ("/" if e.is_dir else "")
        y = e.year + (2000 if e.year < 80 else 1900)
        out += (f"{name:13s}{e.size:7d} {y:04d}-{e.month:02d}-{e.day:02d} "
                f"{e.hour:02d}:{e.minute:02d}"
                .encode("latin-1") + b"\x9b")
    return out


def dos_command(t, b, syms, line):
    """File -> DOS command with `line` typed and OK'd: what it printed,
    read out of the desktop's far buffer once its window is open."""
    link_near, _, _ = header(DESKTOP)
    dsyms = symfile.load(DESK_SYM)
    near = b.peek16(syms["app_near"])

    def var(name):                      # a direct-page scalar of deskcmd.c
        return near + dsyms[name] - link_near

    t.choose(FILEMENU, CMDITEM)
    b.frames(60)
    for ch in line:
        name, shift = KEYS.get(ch, (ch.upper(), False))
        b.key(name, shift=shift)
        b.frames(3)
    b.key("RETURN")
    for _ in range(300):
        b.frames(10)
        if b.peek16(var("cmd_id")):
            break
    t.settle()
    n = b.peek16(var("cmd_len"))
    buf = int.from_bytes(b.memdump(var("cmd_buf"), 3), "little")
    return bytes(b.memdump(buf + CMD_TEXT, n)) if n and buf else b""


def has(t, name):
    """Is there an item called `name` in the top window?"""
    try:
        t.item(name)
        return True
    except KeyError:
        return False


def main():
    print("gem4xe-fdos: the system floppy boots by itself")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    # A copy, written to: the emulator keeps its working copy of it by its
    # hash in the run's configuration (tests/emu/gemarc.py does the same).
    work = tempfile.mkdtemp(prefix="fdos-")
    disk = os.path.join(work, "gem-sdx.atr")
    shutil.copy(os.path.join(BUILD, "gem-sdx.atr"), disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("fdos"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="fdos", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk,
                             "--disk", os.path.join(BUILD, "gem-apps.atr")])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        check(True, "the desk came up from gem-sdx.atr with no SpartaDOS X")
        # below S, idle in the desktop's evnt_multi, all of the engine
        # stack is free: painted, and read back at the end
        stk_lo, stk_hi = stack_range()
        regs = b.ok("REGS")
        sp = (reg(regs.get("SH", 0)) << 8) | reg(regs.get("S", 0))
        painted = stk_lo < sp - 64 <= stk_hi
        if painted:
            b.memload(stk_lo, bytes([PAINT]) * (sp - 64 - stk_lo))
        else:
            print(f"  NOTE: S ${sp:04X} is not on the engine stack "
                  f"${stk_lo:04X}-${stk_hi:04X}; its depth is not measured")
        kind, caps, sep = (b.peek(syms["dos"] + i) for i in range(3))
        check(kind == 3 and caps & 1 and sep == ord(">"),
              f"GEMDOS knows G4DOS, with folders (kind {kind}, caps ${caps:02X}, "
              f"separator {chr(sep)!r})")
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D1:"))
        t.click(t.gadget(W_FULLER))
        p = os.path.join(OUT, "d1.png")
        b.screenshot(p)
        root = [n for n in ("GEM", "G4DOS.SYS", "DESKTOP.PRG") if has(t, n)]
        check(root == ["GEM", "G4DOS.SYS"],
              f"D1:'s window is the root, the system in its folder: {root} ({p})")
        if has(t, "GEM"):
            t.dclick(t.item("GEM"))
            t.settle()
            p = os.path.join(OUT, "d1gem.png")
            b.screenshot(p)
            names = [n for n in ("DESKTOP.PRG", "DESKTOP.RSC", "GEM.COM", "LANG.RSC")
                     if has(t, n)]
            check(len(names) == 4, f"GEM opened lists the system: {names} ({p})")
            t.click(t.gadget(W_CLOSER))         # back to the root ...
            t.settle()
        t.click(t.gadget(W_CLOSER))             # ... and the D2: icon is under it
        t.settle()

        # Options > Save desktop: written, so nothing to say about it
        t.choose(OPTNMENU, SAVEITEM)
        b.frames(120)
        t.settle()
        p = os.path.join(OUT, "save.png")
        b.screenshot(p)
        check(find_text(p, "could not") is None,
              f"Save desktop puts up no alert ({p})")

        # File -> DOS command: G4DOS's commands, under GEM
        want = listing(atr.Sdfs(atr.ATRImage.load(disk)), "GEM")
        got = dos_command(t, b, syms, LS)
        p = os.path.join(OUT, "command.png")
        b.screenshot(p)
        check(got == want, f"File -> DOS command `{LS}` printed the folder as the "
              f"disk has it ({len(got)} bytes, {got.count(b'\x9b')} lines)"
              + ("" if got == want else f": {got[:80]!r}, not {want[:80]!r}"))
        check(find_text(p, "GEM.COM") is not None,
              f"...and its window shows it ({p})")
        t.click(t.gadget(W_CLOSER))
        t.settle()
        got = dos_command(t, b, syms, CP)
        check(got == b"", f"`{CP}` printed nothing: {got[:80]!r}")
        t.click(t.gadget(W_CLOSER))
        t.settle()

        t.dclick(t.desk_icon("DISK D2:"))
        t.click(t.gadget(W_FULLER))
        p = os.path.join(OUT, "d2.png")
        b.screenshot(p)
        at = None
        if check(has(t, "APPS"), f"D2:'s window has the APPS folder ({p})"):
            t.dclick(t.item("APPS"))
            t.settle()
            p = os.path.join(OUT, "d2apps.png")
            b.screenshot(p)
            at = t.item("EDIT.PRG") if has(t, "EDIT.PRG") else None
        if check(at is not None, f"APPS opened lists EDIT.PRG ({p})"):
            t.dclick(at)
            f, p, seen = 0, None, False
            while f < 6000 and not seen:
                b.frames(200)
                f += 200
                p = os.path.join(OUT, "edit.png")
                b.screenshot(p)
                seen = find_text(p, "Open a file") is not None
            check(seen, f"EDIT.PRG ran off D2: and asked for a file ({p})")
        if painted:
            d = b.memdump(stk_lo, sp - 64 - stk_lo)
            low = next((stk_lo + i for i, x in enumerate(d) if x != PAINT), sp - 64)
            print(f"  the engine stack: {stk_hi + 1 - low} of {stk_hi + 1 - stk_lo} "
                  f"bytes used at the deepest, {low - stk_lo} to spare")
            check(low - stk_lo >= STACK_MARGIN,
                  f"the engine stack: {low - stk_lo} bytes to spare, wanted {STACK_MARGIN}")
    finally:
        emu.stop()
    if check(os.path.exists(written), f"the emulator wrote its working copy ({written})"):
        fs = atr.Sdfs(atr.ATRImage.load(written))
        inf = fs.read("DESKTOP.INF") if "DESKTOP.INF" in fs.list("") else None
        check(inf is not None and inf[:1] == b"#",
              f"DESKTOP.INF is in the root, {len(inf or b'')} bytes of layout"
              + (f", starting {inf[:16]!r}" if inf else ""))
        made = fs.read("CMD.CFG") if "CMD.CFG" in fs.list("") else None
        check(made is not None and made == fs.read("GEM>GEM4XE.CFG"),
              f"`{CP}` made CMD.CFG, the same {len(made or b'')} bytes")
        bad = fs.check()
        check(not bad, "the bitmap, the chains and the free count agree"
              + ("" if not bad else ": " + "; ".join(bad[:6])))
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-fdos: {'FAIL' if problems else 'PASS'} -- the system floppy "
          f"boots by itself, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
