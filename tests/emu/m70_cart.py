#!/usr/bin/env python3
"""Phase 165 gate: the cartridge's icon on the desk
(docs/run8-plan.md, step 4).

The AES looks at $A000-$BFFF once at boot (src/sys/dos.c, dos_cart_probe):
a cartridge plugged in, else the XL/XE's own BASIC, else nothing.  The
desktop asks for the cookie G4CT and puts an icon after the drives: BASIC
or CARTRIDGE, a lower-case c on it as TOS showed the cartridge's drive.

  1. The system floppy and the emulator's XL, whose BASIC is always
     there: dos_cart 1 and a BASIC icon.  A file dragged from D2:'s window
     onto it is NOT deleted -- the desktop took every desk icon that was
     not a drive for the trash until this phase -- and no dialog comes.
     Then BASIC double-clicked: GEM ends, the shell switches BASIC in and
     starts it, READY; DOS typed, and GEM comes back.
  2. Our own 8 KB cartridge plugged in (it prints CART RAN and leaves
     through DOSVEC, as BASIC's DOS does; flags $05, as BASIC's): dos_cart
     2 and a CARTRIDGE icon.  Double-clicked: CART RAN, then GEM again.
  5. BASIC under SpartaDOS X: its ROM at $A000 hides BASIC and any
     cartridge on top, so the icon is BASIC, run by SDX's own BASIC
     command from the batch file (src/aes/run8sdx.c); DOS, and GEM.
  3. BASIC and 4. the cartridge on MyDOS 4.50, from its own GEM floppy:
     the same, through the stub GEM leaves
     at $0400 (src/run8.s) -- as on G4DOS, where the shell has no room
     with a cartridge in and the stub takes the cartridge there too.

    python3 tests/emu/m70_cart.py
"""
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch            # noqa: E402
import atr                                    # noqa: E402
import symfile                                # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS   # noqa: E402
from aesref import W_CLOSER                   # noqa: E402
from m7_form import F, B, M                   # noqa: E402
from demo_aes import path                     # noqa: E402
from sdx816 import find_text                  # noqa: E402
from fdos_shell import lines, wait_for        # noqa: E402
from m14_sparta import KEYS                   # noqa: E402
from m67_run8 import gem_back                 # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
OUT = os.path.join(BUILD, "shots", "cart")
NOTE = 0x0444                                 # src/sys/runnote.h
CART_BASIC, CART_ROM = 1, 2                   # src/sys/dos.h DOS_CART_*
problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def make_cart(path):
    """An 8 KB left cartridge, standard type: start prints CART RAN through
    CIO and jumps through DOSVEC; init is an RTS; flags $05."""
    a = 0xA000
    img = bytearray(b"\xff" * 0x2000)
    msg = b"CART RAN\x9b"
    code = bytearray([
        0xA2, 0x00,                     # LDX #0
        0xA9, 0x09, 0x9D, 0x42, 0x03,   # PUT RECORD
        0xA9, 0x00, 0x9D, 0x44, 0x03,   # the message, low...
        0xA9, 0x00, 0x9D, 0x45, 0x03,   # ...and high
        0xA9, 0x40, 0x9D, 0x48, 0x03,
        0xA9, 0x00, 0x9D, 0x49, 0x03,
        0x20, 0x56, 0xE4,               # JSR CIOV
        0x6C, 0x0A, 0x00,               # JMP (DOSVEC)
    ])
    at = a + len(code)
    code[8], code[13] = at & 0xFF, at >> 8
    img[:len(code)] = code
    img[len(code):len(code) + len(msg)] = msg
    img[0x100] = 0x60                   # init: RTS
    img[0x1FFA:0x1FFC] = struct.pack("<H", a)
    img[0x1FFC] = 0x00
    img[0x1FFD] = 0x05
    img[0x1FFE:0x2000] = struct.pack("<H", a + 0x100)
    car = b"CART" + struct.pack(">II", 1, sum(img) & 0xFFFFFFFF) + b"\0" * 4 + bytes(img)
    with open(path, "wb") as f:
        f.write(car)


def sdx_cart():
    import tomllib
    try:
        with open(os.path.join(ROOT, "fixtures.toml"), "rb") as f:
            return tomllib.load(f)["spartados"]["sdx_cart"]
    except (OSError, KeyError):
        return ""


def make_d2(path):
    img = atr.ATRImage(256, 720)
    fs = atr.Sdfs.format(img, "CARTTEST")
    fs.add_file("README.TXT", b"keep me\x9b")
    img.save(path)


def one(name, disk, symname, extra, want_cart, label, work, drag=False, note=True):
    print(f"  -- {name}")
    syms = symfile.load(os.path.join(BUILD, symname))
    d1, d2 = os.path.join(work, "d1.atr"), os.path.join(work, "d2.atr")
    shutil.copy(os.path.join(BUILD, disk), d1)
    disks = ["--disk", d1]
    if drag:
        make_d2(d2)
        disks += ["--disk", d2]
    emu = launch(tag="m70", memsize="1088K", extra_args=disks + extra)
    b = emu.bridge

    def shot(what):
        p = os.path.join(OUT, f"{name}-{what}.png")
        b.screenshot(p)
        return p

    def tour():
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        return t

    try:
        boot(b, syms, OUT)
        got = b.peek(syms["dos_cart"])
        check(got == want_cart, f"{name}: dos_cart {got}, wanted {want_cart}")
        t = tour()
        try:
            icon = t.desk_icon(label)
        except KeyError:
            check(False, f"{name}: no {label} icon on the desk ({shot('desk')})")
            return
        print(f"  {name}: the {label} icon at {icon}")
        if drag:
            t.dclick(t.desk_icon("DISK D2:"))
            src = t.item("README.TXT")
            t.go(src)
            t.run([F(3), B(1), F(30), M(src[0] + 8, src[1] + 4)]
                  + path((src[0] + 8, src[1] + 4), icon) + [F(6), B(0)])
            t.settle()
            b.frames(60)
            p = shot("dropped")
            # the delete's dialog says DELETE FILE(S), in capitals, and then
            # its counts: a check for "Delete" passed with the bug put back
            check(find_text(p, "Number of files") is None,
                  f"{name}: README.TXT dropped on {label}: no delete dialog ({p})")
            b.key("ESC")
            t.settle()
            try:
                t.item("README.TXT")
                kept = True
            except KeyError:
                kept = False
            check(kept, f"{name}: README.TXT still in D2:'s window after the drop")
            t.click(t.gadget(W_CLOSER))         # the icon in view again
            t = tour()
        t.dclick(t.desk_icon(label))
        if want_cart == CART_BASIC:
            f = wait_for(b, lambda ls: any(ln.strip() == "READY" for ln in ls), 20000)
            p = shot("basic")
            if not check(f >= 0, f"{name}: BASIC double-clicked: READY ({p}): {lines(b)[-3:]}"):
                return
            for ch in "DOS":
                b.key(*KEYS.get(ch, (ch, False)))
                b.frames(4)
            b.key("RETURN")
        else:
            f = wait_for(b, lambda ls: any("CART RAN" in ln for ln in ls), 20000)
            p = shot("ran")
            check(f >= 0, f"{name}: CARTRIDGE double-clicked: CART RAN ({p}): {lines(b)[-3:]}")
        f = gem_back(b, syms)
        p = shot("back")
        if check(f >= 0, f"{name}: ...and GEM came back ({p}): {lines(b)[-3:]}"):
            if note:                    # G4DOS's shell's note, $0444
                check(b.peek(NOTE) == 0, f"{name}: the note is gone: {b.peek(NOTE):#x}")
            check(b.peek(0xD301) & 0x02 or want_cart == CART_ROM,
                  f"{name}: BASIC switched out again under GEM: PORTB {b.peek(0xD301):#04x}")
            print(f"  {name}: GEM back {f} frames later")
    finally:
        emu.stop()


def main():
    print("gem4xe-m70: the cartridge's icon on the desk")
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="m70-")
    try:
        car = os.path.join(work, "test8k.car")
        make_cart(car)
        one("g4dos-basic", "gem-sys.atr", "gem.sym", [], CART_BASIC, "BASIC", work,
            drag=True)
        one("g4dos-cart", "gem-sys.atr", "gem.sym", ["--cart", car], CART_ROM,
            "CARTRIDGE", work)
        one("mydos-basic", "gem-mydos.atr", "gem.sym", [], CART_BASIC, "BASIC", work)
        one("mydos-cart", "gem-mydos.atr", "gem.sym", ["--cart", car], CART_ROM,
            "CARTRIDGE", work)
        sdx = sdx_cart()
        if sdx:
            one("sdx-basic", "gem-sys.atr", "gem.sym", ["--cart", sdx], CART_BASIC,
                "BASIC", work, note=False)
        else:
            print("  -- sdx-basic: skipped, no [spartados].sdx_cart in fixtures.toml")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"gem4xe-m70: {'PASS' if not problems else 'FAIL'} -- the cartridge's icon "
          f"on the desk, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
