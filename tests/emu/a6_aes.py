#!/usr/bin/env python3
"""6502 step 4c gate: the AES started on a stock 6502, its window manager
and menu bar drawn, held to the model (docs/6502.md).

build/a6-boot.atr carries A6.COM: src/a6_aes.c resident, starting the
AES as src/gem.c does on one process -- the process records, gsx_start,
ev_init, wm_init, mn_init -- with src/aes/wind.c, menu.c, event.c,
ctrl.c, proc.c, appl.c, grlib.c and form.c compiled by cc6502 into banks
of the PORTB window beside the VDI and the object library (sixteen banks;
tools/bsp6502/a6.scm).  Then src/a6_tree.c, banked, writes two trees into
far memory -- a desk and a menu bar laid out for this screen's 6x6 cell
-- and makes test-m8's and test-m9's calls: wind_set(WF_NEWDESK), two
windows created, named and opened, the second over the first, and
menu_bar.

The machine: an 800XL's 6502, no accelerator, no VBXE, 1088K of PORTB
memory, BASIC off.  The gate checks:

  - the program ran to its end ('A6' 'K' at $0600), on the 6502, and
    reached no stub that must not run (a letter at $0604: 'S' a context
    switch, 'R' a shell request -- step 4d's and later);
  - both trees went into far memory, and wm_create answered handles 1
    and 2, as the model does;
  - every one of the 61,440 pixels is what tools/aesref.py draws for the
    same calls on tools/devref.py's ANTIC device: the desk's pattern, both
    windows' frames, gadgets and titles with the second's over the first,
    the rectangle lists that decide what of the first is drawn, and the
    menu bar.

    python3 tests/emu/a6_aes.py [--shot]
"""
import copy
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref                               # noqa: E402
import devref                               # noqa: E402
from aesref import (Layout, Obj, NIL, LASTOB, NONE, NORMAL, DISABLED,  # noqa: E402
                    CHECKED, G_BOX, G_IBOX, G_TITLE, G_STRING, NAME, CLOSER,
                    FULLER, MOVER, INFO, SIZER, WF_NEWDESK, WF_NAME, WF_INFO,
                    WIND_CREATE, WIND_OPEN, WIND_SET, MENU_BAR)
from m4_aes import PRELUDE                  # noqa: E402
from anticref import AN_W, AN_H              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6-boot.atr"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "a6.png"))
STATUS = 0x0600
SHOT_X0, SHOT_Y0 = 8, 24
BANKS_NEEDED = 16
POOL = 0x4000                   # the model's addresses: any, consistent

KINDS = NAME | CLOSER | FULLER | MOVER | INFO | SIZER
W1 = (10, 20, 200, 110)
W2 = (100, 70, 200, 100)
MW = 120


def desk(L):
    """src/a6_tree.c's desk: test-m7's box, this screen's size."""
    return [Obj(NIL, NIL, NIL, G_BOX, LASTOB, NORMAL, 0x00001148, 0, 0, 320, 192)]


def menu(L):
    """src/a6_tree.c's menu bar, object for object."""
    t = L.text
    return [
        Obj(NIL, 1, 6, G_IBOX, NONE, NORMAL, 0, 0, 0, 320, 192),
        Obj(6, 2, 2, G_BOX, NONE, NORMAL, 0x00001100, 0, 0, 320, 8),
        Obj(1, 3, 5, G_IBOX, NONE, NORMAL, 0, 12, 0, 108, 9),
        Obj(4, NIL, NIL, G_TITLE, NONE, NORMAL, t(" Desk "), 0, 0, 36, 9),
        Obj(5, NIL, NIL, G_TITLE, NONE, NORMAL, t(" File "), 36, 0, 36, 9),
        Obj(2, NIL, NIL, G_TITLE, NONE, NORMAL, t(" View "), 72, 0, 36, 9),
        Obj(0, 7, 19, G_IBOX, NONE, NORMAL, 0, 0, 9, 320, 183),
        Obj(16, 8, 15, G_BOX, NONE, NORMAL, 0x00FF1100, 12, 0, MW, 48),
        Obj(9, NIL, NIL, G_STRING, NONE, NORMAL, t("  About gem4xe..."), 0, 0, MW, 6),
        Obj(10, NIL, NIL, G_STRING, NONE, DISABLED, t("-" * 20), 0, 6, MW, 6),
        Obj(11, NIL, NIL, G_STRING, NONE, NORMAL, t("1"), 0, 12, MW, 6),
        Obj(12, NIL, NIL, G_STRING, NONE, NORMAL, t("2"), 0, 18, MW, 6),
        Obj(13, NIL, NIL, G_STRING, NONE, NORMAL, t("3"), 0, 24, MW, 6),
        Obj(14, NIL, NIL, G_STRING, NONE, NORMAL, t("4"), 0, 30, MW, 6),
        Obj(15, NIL, NIL, G_STRING, NONE, NORMAL, t("5"), 0, 36, MW, 6),
        Obj(7, NIL, NIL, G_STRING, NONE, NORMAL, t("6"), 0, 42, MW, 6),
        Obj(19, 17, 18, G_BOX, NONE, NORMAL, 0x00FF1100, 48, 0, 60, 12),
        Obj(18, NIL, NIL, G_STRING, NONE, NORMAL, t("  Open"), 0, 0, 60, 6),
        Obj(16, NIL, NIL, G_STRING, NONE, NORMAL, t("  Quit"), 0, 6, 60, 6),
        Obj(6, 20, 20, G_BOX, NONE, NORMAL, 0x00FF1100, 84, 0, 60, 6),
        Obj(19, NIL, NIL, G_STRING, LASTOB, CHECKED, t("  Icons"), 0, 0, 60, 6),
    ]


def wset(wh, field, *words):
    return (WIND_SET, (), (wh, field) + tuple(words) + (0,) * (4 - len(words)))


def model():
    """src/a6_tree.c's calls, in its order, on test-m8's and test-m9's
    models: tools/vdiref.py and tools/aesref.py on tools/devref.py's ANTIC.
    wind_create's full size is the desk's work area, gl_rfull, which the
    program hands it too -- read from the model after gsx_start."""
    L = Layout(POOL, max_objs=21)
    objs = menu(L)
    L2 = Layout(L.next, max_objs=1)
    objs2 = desk(L2)
    mem = dict(L.mem)
    mem.update(L2.mem)
    probe = aesref.run(PRELUDE, copy.deepcopy(objs), dict(mem),
                       dev=devref.Antic())[1]
    f = probe.gl_rfull
    full = (f.x, f.y, f.w, f.h)
    script = PRELUDE + [
        wset(0, WF_NEWDESK, 0, L2.base, 0),
        (WIND_CREATE, (), (KINDS,) + full),
        wset(1, WF_NAME, 0, L2.text("First")),
        wset(1, WF_INFO, 0, L2.text("a window on a 6502")),
        (WIND_OPEN, (), (1,) + W1),
        (WIND_CREATE, (), (NAME | MOVER | CLOSER,) + full),
        wset(2, WF_NAME, 0, L2.text("Second")),
        (WIND_OPEN, (), (2,) + W2),
        (MENU_BAR, (), (1,)),
    ]
    mem.update(L2.mem)
    v, a, res = aesref.run(script, objs, mem, trees={L2.base: objs2}, home=L.base,
                           dev=devref.Antic())
    return v.dev, res, len(PRELUDE)


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-a6: the AES on one process, on a stock 6502")
    dev, res, pre = model()
    emu = launch(tag="a6", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(500)
        for t in range(0, 9000, 50):
            b.frames(50)
            st = bytes(b.memdump(STATUS, 3))
            if st == b"A6K" or b.peek(STATUS + 4):
                break
        st = bytes(b.memdump(STATUS, 3))
        stuck = b.peek(STATUS + 4)
        check(not stuck, f"no stub that must not run was reached "
                         f"({chr(stuck) if stuck else 'none'} at $0604)")
        if not check(st == b"A6K", f"the program ran to its end (status {st!r}, "
                                   f"stage {chr(b.peek(STATUS + 3))!r})"):
            b.screenshot(SHOT)
            print(f"  screen: {SHOT}")
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "6502", f"the CPU is a 6502 ({cpu})")
        banks = b.peek(STATUS + 8)
        check(banks >= BANKS_NEEDED, f"the probe found {banks} banks; {BANKS_NEEDED} "
                                     f"are needed")
        check(b.peek(STATUS + 0x5C) == 1 and b.peek(STATUS + 0x5D) == 1,
              "the desk and the menu went into far memory")
        h1, h2 = b.peek(STATUS + 0x60), b.peek(STATUS + 0x61)
        want = (res[pre + 1][2], res[pre + 5][2])      # wind_create's int_out[0]
        check((h1, h2) == (1, 2) and (h1, h2) == want,
              f"wm_create answered {h1} and {h2}; the model {want}")

        b.frames(20)
        b.screenshot(SHOT)
        from PIL import Image
        im = Image.open(SHOT).convert("RGB")
        px = im.load()
        seen = {px[SHOT_X0 + x, SHOT_Y0 + y] for y in range(AN_H) for x in range(AN_W)}
        if not check(len(seen) == 2, f"the playfield holds {len(seen)} colours, want 2"):
            return 1
        clear = next((x, y) for y in range(AN_H) for x in range(AN_W) if not dev.bit(x, y))
        setpx = next((x, y) for y in range(AN_H) for x in range(AN_W) if dev.bit(x, y))
        bg = px[SHOT_X0 + clear[0], SHOT_Y0 + clear[1]]
        fg = px[SHOT_X0 + setpx[0], SHOT_Y0 + setpx[1]]
        check(bg != fg, f"pen 0 {bg} and pen 1 {fg} differ")
        bad, first = 0, []
        for y in range(AN_H):
            for x in range(AN_W):
                exp = fg if dev.bit(x, y) else bg
                if px[SHOT_X0 + x, SHOT_Y0 + y] != exp:
                    bad += 1
                    if len(first) < 4:
                        first.append((x, y, dev.bit(x, y)))
        check(not bad, f"{AN_W * AN_H - bad:,} of {AN_W * AN_H:,} pixels as the model has "
                       f"them; first differing (x, y, wanted) {first}")
    finally:
        emu.stop()
    if not fails and not keep and os.path.exists(SHOT):
        os.remove(SHOT)
    print(f"gem4xe-a6: {'PASS' if not fails else 'FAIL'} -- the AES on one process, "
          f"on a stock 6502, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
