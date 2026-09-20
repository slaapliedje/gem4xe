#!/usr/bin/env python3
"""GEM under Rapidus OS with SpartaDOS X's 65816.SYS loaded.

SpartaDOS X's Toolkit carries 65C816 drivers, and 65816.SYS is the one a Rapidus
OS machine loads first.  With it loaded, gem4xe 0.1.2 and 0.2 both stopped at the
desktop's first rsrc_load and said DESKTOP.RSC was not on the boot disk.  Nothing was
wrong with the disk or the DOS: proc_init() cleared a process record field by field,
and not the two resource slots added to the record later, so the desktop started out
holding two resources it had never loaded and rs_load refused a third.  The record is
taken from the bank-$00 pool, which is zero on a plain SpartaDOS X machine and holds
bytes of the driver once 65816.SYS has been loaded through it (docs/phase41.md).

The machine: Rapidus OS as the XL kernel (--os, from a private emulator profile, as
test-m11-os), the 65C816 selected before it runs, the SpartaDOS X cartridge (--cart),
and the SDX product disk's files (tools/mkfloppy.py) with a CONFIG.SYS that loads
65816.SYS (--driver) after SIO -- before SIO, SDX cannot read D1: to load it.

The gate: SpartaDOS X says the driver loaded, and the desktop reaches its first wait
with nothing refused and no interrupt fault.

Then the one thing only this machine can do -- File -> DOS command.  The desktop hands
a line to SpartaDOS X's own command processor (XCOMLI, Programming Guide 4.50 18.9.2)
through GEMDOS's Psystem, with what it prints caught in a far buffer and shown in a
window (src/sys/dos.c dos_command, src/desk/deskcmd.c).  The gate pulls the File menu
at the pointer, chooses the item, types VER into the dialog and Return, and reads the
buffer back: VER's banner, a window on it, MEMLO where it was, nothing refused.

  python3 tests/emu/sdx816.py --os=ROM --cart=CAR --driver=65816.SYS [--shot]
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import mkfloppy, symfile                    # noqa: E402
from aesref import RETURN, DISABLED         # noqa: E402
import fontref                              # noqa: E402
from vbxeref import SHOT_X0, SHOT_Y0, SCR_W, SCR_H   # noqa: E402
from deskrsc import (THEBAR, THEACTIVE, FILEMENU, THEDROPS, FILEBOX,  # noqa: E402
                     CMDITEM)
from demo_aes import path                   # noqa: E402
from m4_aes import SHOTDIR                  # noqa: E402
from m7_form import F, B, K, apply_step     # noqa: E402
from m11_abi import os_profile              # noqa: E402
from m14_sparta import screen               # noqa: E402
from m17_desktop import (header, DESKTOP, DESK_SYM,   # noqa: E402
                         desk_g)

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "sdx816-boot.atr")
SYMS = os.path.join(BUILD, "gem.sym")
CONFIG = ["DEVICE SPARTA OSRAM", "DEVICE SIO", "DEVICE D1:65816",
          "DEVICE ATARIDOS", "DEVICE JIFFY"]
LOADED = "65816 v."                         # what 65816.SYS prints as it installs
FIRST_WAIT = 43                             # the desktop's calls to its first wait
LIMIT = 12000                               # frames
COMMAND = "VER"                             # what the dialog is given
BANNER = "SpartaDOS"                        # ...and what it prints, drawn
MEMLO = 0x02E7
OB_SIZE = 24
W_NAME = 3                                  # the title in the frame tree
                                            # (src/aes/aes.h, W_ACTIVE[])
CMD_TEXT = 64 + 4                           # where the text starts in the far
                                            # buffer: its title comes first
                                            # (src/desk/deskcmd.c)


def obj(b, tree, i):
    """One OBJECT out of the target, as the AES has it in memory."""
    d = bytes(b.memdump(tree + i * OB_SIZE, OB_SIZE))
    (nxt, head, tail, typ, flags, state, spec,
     x, y, w, h) = struct.unpack("<hhhHHHIhhhh", d)
    return dict(next=nxt, head=head, tail=tail, type=typ, flags=flags,
                state=state, spec=spec, x=x, y=y, w=w, h=h)


def centre(b, tree, chain):
    """The screen centre of the last object of a parent chain."""
    x = y = 0
    for i in chain:
        o = obj(b, tree, i)
        x += o["x"]
        y += o["y"]
    return x + o["w"] // 2, y + o["h"] // 2


def glyph_rows(text):
    """The eight rows of `text` in the system font, one bit a pixel, the
    leftmost pixel the highest bit (tools/fontref.py: a row strip)."""
    rows = []
    for r in range(8):
        v = 0
        for ch in text:
            v = (v << 8) | fontref.FONT_8X8[r * fontref.FONT_STRIDE + (ord(ch) & 0xFF)]
        rows.append(v)
    return rows


def find_text(shot_path, text):
    """Where `text` stands on the screenshot, drawn dark on light in the
    system font at any pixel position; None when it is nowhere.  This
    is the proof that the window DREW the text; the buffer itself is
    read through the bridge, which reads above $FFFF now."""
    from PIL import Image
    px = Image.open(shot_path).convert("RGB").load()
    packed = []
    for y in range(SCR_H):
        v = 0
        for x in range(SCR_W):
            v = (v << 1) | (1 if sum(px[SHOT_X0 + x, SHOT_Y0 + y]) < 192 else 0)
        packed.append(v)
    want = glyph_rows(text)
    width = 8 * len(text)
    mask = (1 << width) - 1
    for y in range(SCR_H - 7):
        for x in range(SCR_W - width + 1):
            shift = SCR_W - width - x
            if all(((packed[y + r] >> shift) & mask) == want[r] for r in range(8)):
                return x, y
    return None


def command(b, syms, shot):
    """File -> DOS command, VER, and what came of it.  The failures."""
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    # the desktop's own variables, where the loader put them (app.c app_near)
    link_near, _, _ = header(DESKTOP)
    dsyms = symfile.load(DESK_SYM)
    near = b.peek16(syms["app_near"])
    # G is not in the near region when the desktop is a large-data
    # program -- it is in far bss (src/sys/app.c, app_far).
    g = desk_g(b, syms)

    def var(name):                              # a direct-page scalar of deskcmd.c
        return near + dsyms[name] - link_near
    a_menu = b.peek24(g)                        # G.a_menu: a far pointer now
    # The bridge reads memory above $FFFF now (tools/altirra/
    # altirra-sdl-bridge-memory-24bit.patch): first a fact -- a far string
    # of gem4xe's own, in the accelerator's RAM -- then the command's
    # buffer itself, which the screen search below used to stand in for.
    try:
        far = bytes(b.memdump(syms["gd_devnames"], 12))
    except Exception as e:                      # an unpatched build refuses
        check(False, f"the bridge does not read far memory ({e}); the emulator "
                     f"needs tools/altirra/altirra-sdl-bridge-memory-24bit.patch")
        return fails
    check(far == b"CON:AUX:PRN:",
          f"far memory read back {far!r} at gd_devnames ${syms['gd_devnames']:06X}, "
          f"not the string src/sys/gemdos.c keeps there")
    item = obj(b, a_menu, CMDITEM)
    check(item["state"] & DISABLED == 0,
          "the item is greyed: Psystem says this DOS has no command processor")
    if fails:
        return fails
    title_xy = centre(b, a_menu, [THEBAR, THEACTIVE, FILEMENU])
    item_xy = centre(b, a_menu, [THEDROPS, FILEBOX, CMDITEM])
    # straight down from the title into its drop-down: a slant would
    # cross the next title first and drop that menu instead
    item_xy = (title_xy[0], item_xy[1])
    memlo = b.peek16(MEMLO)
    ptr = syms["ptr_state"]
    here = (b.peek16(ptr), b.peek16(ptr + 2))
    print(f"  the File title at {title_xy}, DOS command at {item_xy}; MEMLO ${memlo:04X}")
    steps = ([F(3)] + path(here, title_xy) + [F(10)]
             + path(title_xy, item_xy, speed=4) + [F(10), B(1)])
    def state(what):
        """The AES's double-click machine and the pointer records, for
        the log: what a press that goes nowhere looks like."""
        w = {k: b.peek16(syms[k]) for k in ("gl_btrue", "gl_bpend", "gl_bclick",
                                            "gl_bdely", "gl_bdesired", "app_calls",
                                            "irq_frames")}
        w["ptr_state"] = tuple(b.peek16(syms["ptr_state"] + 2 * i) for i in range(3))
        w["ptr_seen"] = tuple(b.peek16(syms["ptr_seen"] + 2 * i) for i in range(3))
        print(f"  {what}: " + ", ".join(f"{k} {v}" for k, v in w.items()))

    # The pointer's place is poked, as every gate pokes it; the BUTTON is
    # not, because this is the product binary with the product's config,
    # an ST mouse, whose sampler reads the trigger every tick and would
    # overwrite a poke (src/vdi/pointer.c).  So the press is the port's
    # trigger, through the emulator: the way a mouse button arrives.
    press = steps.index(B(1))
    for step in steps[:press]:
        apply_step(b, ptr, step)
    b.joy(1, "center", fire=True)
    b.frames(14)
    b.joy(1, "center", fire=False)
    b.frames(20)
    state("after the press")
    b.frames(90)                                # PREFS.RSC read, the dialog drawn
    for ch in COMMAND:
        apply_step(b, ptr, K(ch, 0))
        b.frames(3)
    apply_step(b, ptr, K("RETURN", RETURN))     # OK, the default button
    # the command runs inside the desktop's Psystem; the window opens after
    for _ in range(300):
        b.frames(10)
        if b.peek16(var("cmd_len")):
            break
    b.frames(60)
    n = b.peek16(var("cmd_len"))
    lines = b.peek16(var("cmd_lines"))
    wh = b.peek16(var("cmd_id"))
    buf = int.from_bytes(b.memdump(var("cmd_buf"), 3), "little")
    # The window's title is FAR and nothing brings it near any more: since
    # phase 47 w_ptext assigns the 24-bit address straight into the frame
    # TEDINFO's te_ptext and the VDI reads the string where it lies.  So
    # follow what the DRAWING follows -- the frame tree's W_NAME object,
    # its TEDINFO, and te_ptext at offset 0 of it -- rather than reading a
    # near copy, which is what gl_nbuf was and is now deleted.
    ted = obj(b, b.peek24(syms["gl_awind"]), W_NAME)["spec"]
    title = bytes(b.memdump(b.peek24(ted), 41)).split(b"\0")[0].decode("latin-1")
    b.screenshot(shot)
    where = find_text(shot, BANNER)
    text = bytes(b.memdump(buf + CMD_TEXT, n)) if n and buf else b""
    first = next((ln for ln in text.split(b"\x9b") if ln), b"").decode("latin-1")
    print(f"  {COMMAND}: {n} bytes, {lines} line(s), window {wh} titled {title!r}, "
          f"buffer ${buf:06X} starting {first!r}; {BANNER!r} on the screen at {where}")
    check(n > 0, f"{COMMAND} printed nothing the desktop caught")
    check(BANNER.encode() in text, f"the buffer does not hold {BANNER!r}: {text[:40]!r}")
    check(lines >= 1, f"{n} bytes made {lines} lines")
    check(wh > 0, "no window opened on the output")
    # the bridge types the line in lower case and the dialog keeps what was
    # typed, as SpartaDOS X takes it either way
    check(title.upper() == f" {COMMAND} ", f"the window is titled {title!r}, not ' {COMMAND} '")
    check(where is not None, f"{BANNER!r} is not drawn on the screen")
    check(b.peek16(MEMLO) == memlo,
          f"MEMLO is ${b.peek16(MEMLO):04X} afterwards, was ${memlo:04X}")
    check(b.peek16(syms["gem_bad"]) == 0, f"{b.peek16(syms['gem_bad'])} ABI call(s) refused")
    check(b.peek(syms["irq_fault"]) == 0, f"irq_fault {b.peek(syms['irq_fault'])}")
    return fails


def arg(argv, name):
    return next((os.path.abspath(a.split("=", 1)[1]) for a in argv
                 if a.startswith(f"--{name}=")), None)


def main(argv):
    rom, cart, driver = arg(argv, "os"), arg(argv, "cart"), arg(argv, "driver")
    if not (rom and cart and driver):
        print("gem4xe-sdx816: needs --os=ROM --cart=CAR --driver=65816.SYS")
        return 2
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    cfg = os.path.join(BUILD, "sdx816-config.sys")
    with open(cfg, "wb") as f:
        f.write(b"".join(ln.encode() + b"\x9b" for ln in CONFIG))
    if os.path.exists(DISK):
        os.remove(DISK)
    mkfloppy.build(DISK, [(driver, "65816.SYS"), (cfg, "CONFIG.SYS")],
                   root=os.path.abspath(ROOT))
    syms = symfile.load(SYMS)
    if not os_profile(rom):
        print("gem4xe-sdx816: no firmware entry for the XL ROM in "
              "~/.config/altirra/settings.ini to point at the OS")
        return 2
    print(f"the machine: {os.path.basename(rom)}, {os.path.basename(cart)}, 65816.SYS from D1:")
    os.makedirs(SHOTDIR, exist_ok=True)
    shot = os.path.join(SHOTDIR, "sdx816-desk.png")
    emu = launch(tag="sdx816", memsize="1088K", require_real_rom=False,
                 extra_args=["--disk", DISK, "--cart", cart])
    b = emu.bridge
    try:
        b.poke(0xD1FF, 0x01)                # the 65C816 before the OS runs
        b.poke(0xD191, 0x00)
        loaded, n, n_prev, still, f = False, 0, None, 0, 0
        for f in range(50, LIMIT, 50):
            b.frames(50)
            if not loaded:
                loaded = any(LOADED in ln for ln in screen(b))
            # gem4xe's variables mean nothing until it is running
            if b.peek(syms["irq_cio_swap"]) not in (1, 3):
                continue
            n = b.peek16(syms["app_calls"])
            if n > 0x1000:
                continue
            still = still + 1 if (n and n == n_prev) else 0
            n_prev = n
            if n >= FIRST_WAIT or still >= 100:
                break
        check(loaded, "SpartaDOS X never said 65816.SYS loaded: the gate is not testing it")
        print(f"  65816.SYS {'loaded' if loaded else 'NOT loaded'}; the desktop "
              f"{'reached its first wait' if n >= FIRST_WAIT else 'stopped'} "
              f"at call {n}, frame {f}")
        check(n >= FIRST_WAIT,
              f"the desktop stopped at call {n}, short of its first wait at {FIRST_WAIT} "
              f"(DESKTOP.RSC refused: see proc_init)")
        check(b.peek16(syms["gem_bad"]) == 0, f"{b.peek16(syms['gem_bad'])} ABI call(s) refused")
        check(b.peek(syms["irq_fault"]) == 0, f"irq_fault {b.peek(syms['irq_fault'])}")
        b.screenshot(shot)
        cmdshot = os.path.join(SHOTDIR, "sdx816-cmd.png")
        if not fails:
            fails += command(b, syms, cmdshot)
        if not fails and not keep:
            os.remove(shot)
            if os.path.exists(cmdshot):
                os.remove(cmdshot)
    finally:
        emu.stop()

    print(f"gem4xe-sdx816: {'PASS' if not fails else 'FAIL'} -- GEM with SpartaDOS X's "
          f"65816.SYS under Rapidus OS, and a DOS command from the desktop, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
