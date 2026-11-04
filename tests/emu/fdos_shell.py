#!/usr/bin/env python3
"""G4DOS's shell (src/shell/shell.c, docs/g4dos-plan.md step 4): the DOS's
commands at a prompt, booted and come back to by G4DOS's loader.

  1. A disk with G4DOS and SHELL.SYS and no GEM.COM or AUTORUN.SYS boots to
     the shell's prompt.  A session is typed at it -- listing, folders,
     a file shown, made, copied, moved and deleted -- and what each line
     prints is read off the screen; a program one folder down is run by
     its bare name, prints its line and RETURNS, and the shell is back
     (the loader calls RUNAD as a subroutine, DOSVEC is the shell's); a
     program two folders down is refused in so many words; RESET comes
     back to the shell too (WARMST).  Then the emulator's working copy of
     the disk is read with tools/atr.py: what the session made is there,
     what it moved and deleted is not, and Sdfs.check() is clean.
  2. The same disk with an AUTORUN.SYS on it boots that, not the shell.
  3. The system floppy, gem-sdx.atr: GEM's File -> Quit comes back to the
     shell, which lists the disk.
  4. BASIC on at a cold start -- OPTION not held, as at every cold start
     after the first on a Rapidus -- with leftovers in the RAM under BASIC
     that ask for a cartridge start ($BFFD bit 2, $BFFA aimed at a routine
     there that marks $BF80).  The OS saw BASIC as a cartridge, G4DOS
     switches it out, and the OS then reads those leftovers: it must still
     come to the shell, not run them.  A real machine's RAM holds such
     leftovers; the emulator's starts at zero, which is why only this,
     planted, shows it.

    python3 tests/emu/fdos_shell.py
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
import mkfloppy                               # noqa: E402
import symfile                                # noqa: E402
from m14_sparta import screen, KEYS           # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from deskrsc import FILEMENU, QUITITEM        # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "fdossh")
STEP = 50

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def prog(text, back=True):
    """A program in the Atari's binary format, at $3000: `text` put on the
    screen as a record, then an RTS -- or, `back` False, a loop."""
    body = bytes([0xA2, 0x00, 0xA9, 0x09, 0x9D, 0x42, 0x03,      # PUT RECORD
                  0xA9, 0x00, 0x9D, 0x44, 0x03, 0xA9, 0x00, 0x9D, 0x45, 0x03,
                  0xA9, 0x40, 0x9D, 0x48, 0x03, 0xA9, 0x00, 0x9D, 0x49, 0x03,
                  0x20, 0x56, 0xE4])
    tail = bytes([0x60]) if back else bytes([0x4C, 0x00, 0x00])
    at = 0x3000 + len(body) + len(tail)
    body = bytearray(body + tail)
    body[8], body[13] = at & 0xFF, at >> 8
    if not back:
        here = 0x3000 + len(body) - 3
        body[-2:] = bytes([here & 0xFF, here >> 8])
    body += text.encode() + b"\x9b"
    end = 0x3000 + len(body) - 1
    return (b"\xff\xff" + (0x3000).to_bytes(2, "little") + end.to_bytes(2, "little")
            + bytes(body) + b"\xe0\x02\xe1\x02" + (0x3000).to_bytes(2, "little"))


README = b"Line one\r\nLine two\r\n"


def make_disk(path, autorun=False):
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "SHTEST")
    fs.add_file("README.TXT", README)
    fs.mkdir("DOCS")
    fs.add_file("DOCS>A.TXT", b"hello from a\x9b")
    fs.add_file("DOCS>HELLO.COM", prog("HELLO FROM PROG"))
    fs.mkdir("DOCS>OLD")
    fs.add_file("DOCS>OLD>DEEP.COM", prog("TOO DEEP TO RUN"))
    with open(os.path.join(BUILD, "shell.sys"), "rb") as f:
        fs.add_file("SHELL.SYS", f.read())
    if autorun:
        fs.add_file("AUTORUN.SYS", prog("AUTORUN RAN", back=False))
    b1, b23, dos = mkfloppy.fdos_parts(os.path.abspath(ROOT))
    fs.boot_gem4xe(b1, b23, dos)
    img.save(path)


def lines(b):
    return [ln.strip() for ln in screen(b) if ln.strip()]


def wait_for(b, pred, limit=6000):
    for t in range(0, limit, STEP):
        if pred(lines(b)):
            return t
        b.frames(STEP)
    return -1


BANNER = "G4DOS shell -- help lists commands"


def at_prompt(ls):
    return bool(ls) and ls[-1].endswith("$")


def fresh(ls, where="D1:/"):
    """The shell just started: its banner, and the prompt under it."""
    return len(ls) >= 2 and ls[-2] == BANNER and ls[-1] == where + "$"


def run(b, cmd):
    """Type `cmd` at the prompt: what it printed, the lines between its echo
    and the next prompt."""
    for ch in cmd:
        name, shift = KEYS.get(ch, (ch.upper(), False))
        b.key(name, shift=shift)
        b.frames(3)
    b.key("RETURN")
    b.frames(20)
    t = wait_for(b, at_prompt, 3000)
    ls = lines(b)
    echo = cmd.upper()
    at = max((i for i, ln in enumerate(ls) if ln.endswith("$ " + echo)), default=-1)
    out = ls[at + 1:-1] if at >= 0 else ls
    return out, t


# (the line, what it must print: a list of lines, or a function of them)
SESSION = [
    ("ls", lambda o: sorted(" ".join(o).split()) ==
     ["DOCS/", "G4DOS.SYS", "README.TXT", "SHELL.SYS"]),
    ("cd docs", []),
    ("pwd", ["D1:/DOCS"]),
    ("cat a.txt", ["hello from a"]),
    ("mkdir new", []),
    ("cp a.txt new/b.txt", []),
    ("mv /readme.txt new/", []),
    ("ls new", ["B.TXT         README.TXT"]),
    ("cat new/readme.txt", ["Line one", "Line two"]),
    ("rm new/b.txt", []),
    ("rm new/b.txt", ["RM: NEW/B.TXT: no such file"]),
    ("old/deep", ["OLD/DEEP: more than one folder down"]),
    ("df", lambda o: len(o) == 2 and o[0] == "Drive Sectors   Free  Bytes free"
     and o[1].split()[:2] == ["D1:", "720"]),
]


def session():
    work = tempfile.mkdtemp(prefix="fdossh-")
    disk = os.path.join(work, "shell.atr")
    make_disk(disk)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("fdossh"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="fdossh", memsize="1088K",
                 extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    try:
        b.ok("COLD_RESET")
        t = wait_for(b, fresh, 20000)
        p = os.path.join(OUT, "prompt.png")
        b.screenshot(p)
        check(t >= 0 and lines(b)[-1] == "D1:/$",
              f"no GEM.COM, no AUTORUN.SYS: the disk booted to the shell's "
              f"prompt, {t} frames ({p})")
        if t < 0:
            print("\n".join(lines(b)))
            return
        for cmd, want in SESSION:
            out, t = run(b, cmd)
            ok = want(out) if callable(want) else out == want
            check(ok and t >= 0, f"`{cmd}` printed {out}"
                  + ("" if ok else f", not {want}"))
        # a program by its bare name, one folder down: it prints and RETURNS
        out, t = run(b, "hello")
        p = os.path.join(OUT, "hello.png")
        b.screenshot(p)
        check(any("HELLO FROM PROG" in ln for ln in out) and t >= 0
              and fresh(lines(b), "D1:/DOCS"),
              f"`hello` ran DOCS/HELLO.COM, which returned to the shell, in the "
              f"folder it was run from ({p}): {out[-4:]} {lines(b)[-1:]}")
        run(b, "cd /")                  # the screen no longer ends fresh,
        b.ok("WARM_RESET")              # and the folder is the root
        t = wait_for(b, fresh, 20000)
        p = os.path.join(OUT, "reset.png")
        b.screenshot(p)
        check(t >= 0, f"RESET came back to the shell, {t} frames ({p})")
        out, t = run(b, "ls docs")
        check(sorted(" ".join(out).split()) == ["A.TXT", "HELLO.COM", "NEW/", "OLD/"],
              f"...which still works: `ls docs` printed {out}")
    finally:
        emu.stop()
    if check(os.path.exists(written), "the emulator wrote its working copy"):
        fs = atr.Sdfs(atr.ATRImage.load(written))
        check(sorted(fs.list("")) == ["DOCS", "G4DOS.SYS", "SHELL.SYS"],
              f"the root has lost README.TXT to the move: {fs.list('')}")
        new = fs.list("DOCS>NEW") if "NEW" in fs.list("DOCS") else None
        check(new == ["README.TXT"], f"DOCS/NEW holds the moved file alone: {new}")
        if new == ["README.TXT"]:
            check(fs.read("DOCS>NEW>README.TXT") == README,
                  "...byte for byte, the ST's line ends and all")
        bad = fs.check()
        check(not bad, "the bitmap, the chains and the free count agree"
              + ("" if not bad else ": " + "; ".join(bad[:6])))
    shutil.rmtree(work, ignore_errors=True)


def autorun():
    work = tempfile.mkdtemp(prefix="fdossh-")
    disk = os.path.join(work, "autorun.atr")
    make_disk(disk, autorun=True)
    emu = launch(tag="fdossh", memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        b.ok("COLD_RESET")
        t = wait_for(b, lambda ls: any("AUTORUN RAN" in ln for ln in ls), 20000)
        p = os.path.join(OUT, "autorun.png")
        b.screenshot(p)
        check(t >= 0 and not any(ln.endswith("$") for ln in lines(b)),
              f"with an AUTORUN.SYS on it, the disk booted that and not the "
              f"shell ({p})")
    finally:
        emu.stop()
    shutil.rmtree(work, ignore_errors=True)


def gem_quits():
    syms = symfile.load(SYMS)
    emu = launch(tag="fdossh", memsize="1088K",
                 extra_args=["--disk", os.path.join(BUILD, "gem-sdx.atr")])
    b = emu.bridge
    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.choose(FILEMENU, QUITITEM)
        f = wait_for(b, fresh, 20000)
        p = os.path.join(OUT, "quit.png")
        b.screenshot(p)
        check(f >= 0, f"File -> Quit on the system floppy came back to the "
              f"shell, {f} frames ({p})")
        if f >= 0:
            out, _ = run(b, "ls")
            names = " ".join(out).split()
            check("GEM/" in names and "SHELL.SYS" in names,
                  f"...which lists the system floppy: {out}")
    finally:
        emu.stop()


def basic_leftovers():
    work = tempfile.mkdtemp(prefix="fdossh-")
    disk = os.path.join(work, "basic.atr")
    make_disk(disk)
    # a plain 65C816, so the shell starts without a CPU switch of its own
    emu = launch(tag="fdossh", memsize="64K", rapidus=False, cpu816=15,
                 extra_args=["--basic", "--disk", disk])
    b = emu.bridge
    try:
        b.ok("COLD_RESET")
        t = wait_for(b, fresh, 20000)
        if not check(t >= 0, "BASIC on at power-up: the disk still boots to the "
                             "shell"):
            return
        # BASIC is out now, so these land in the RAM under it: a routine
        # that marks $BF80 and loops, a start address at it, $BFFC zero and
        # $BFFD asking for the cartridge to be started
        b.memload(0xBF00, bytes([0xA9, 0xAA, 0x8D, 0x80, 0xBF,
                                 0x4C, 0x05, 0xBF]))
        b.memload(0xBF80, b"\x00")
        b.memload(0xBFFA, bytes([0x00, 0xBF, 0x00, 0x04]))
        b.poke(0x0244, 1)                       # COLDST: RESET starts cold
        b.ok("WARM_RESET")
        t = wait_for(b, fresh, 20000)
        p = os.path.join(OUT, "basic.png")
        b.screenshot(p)
        check(b.peek(0xBF80) != 0xAA and t >= 0,
              f"...and a cold start with BASIC on and leftovers under it that "
              f"ask for a cartridge start comes to the shell, not into them "
              f"({p}): $BF80 = ${b.peek(0xBF80):02X}")
    finally:
        emu.stop()
    shutil.rmtree(work, ignore_errors=True)


def main():
    print("gem4xe-fdossh: G4DOS's shell")
    os.makedirs(OUT, exist_ok=True)
    session()
    autorun()
    gem_quits()
    basic_leftovers()
    print(f"gem4xe-fdossh: {'FAIL' if problems else 'PASS'} -- G4DOS's shell, "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
