#!/usr/bin/env python3
"""6502 step 1 gate: the VDI, banked, on a stock 6502 (docs/6502.md).

build/v6-boot.atr carries V6.COM: src/v6_vdi.c resident, calling the
same src/vdi/vdi.c and src/vdi/dev_antic.c the 65C816 build ships, which
cc6502 compiled into banks of the PORTB window -- vdi.c in three, the
device in two, the far heap's allocator (src/sys/farmem.c) in a sixth --
each call into a bank through a veneer and the trampoline in
src/sys6502/bank6502.s.  The link was refused unless no
reference crossed a bank without one (tools/bsp6502/bankcheck.py).

The machine: an 800XL's 6502, no accelerator, no VBXE, 1088K of PORTB
memory, BASIC off.  The gate checks:

  - the program ran to its end ('AVK' at $0600), on the 6502;
  - the loader's probe found the banks: at least the six it needs, and
    the far heap made at least one far bank of those after them;
  - vqt_name names the ANTIC face's cell, "gem4xe system 6x6";
  - every one of the 61,440 pixels is what tools/vdiref.py draws for the
    same calls on tools/devref.py's ANTIC device -- the model test-m25
    holds the 65C816 to, with nothing changed but the program's calls.
    "BIG", at twice the face's size, is drawn from a raster the VDI builds
    in far memory, so a far read or write that lost its bank shows here.

    python3 tests/emu/v6_vdi.py [--shot]
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref                               # noqa: E402
import devref                               # noqa: E402
from m4_aes import Layout, GSX_START, OBJC_DRAW, FULL   # noqa: E402
import m25_antic_vdi                        # noqa: E402  test-m25's tree
from anticref import AN_W, AN_H              # noqa: E402
from vdiref import (V_OPNWK, V_CLRWK, WORK_IN, VSF_COLOR,   # noqa: E402
                    VSF_INTERIOR, VSWR_MODE, VST_COLOR, VR_RECFL, V_GTEXT,
                    VS_CLIP, VRO_CPYFM, VST_HEIGHT, VSF_UDPAT, V_PLINE,
                    VSL_TYPE, VSL_UDSTY, V_ESCAPE, ESC_XLINE)

FIS_SOLID, FIS_USER, MD_REPLACE, MD_TRANS, MD_XOR, MD_ERASE = 1, 4, 1, 2, 3, 4
PAT = (0xF00F, 0x0FF0, 0x8001, 0x7FFE, 0xC3A5, 0x3C5A, 0xFF00, 0x00FF,
       0x1248, 0x8421, 0xAA55, 0x55AA, 0xE007, 0x07E0, 0x9009, 0x6FF6)
BANKS_NEEDED = 10

# src/v6_vdi.c's calls, in its order
SCRIPT = [
    (V_OPNWK, (), WORK_IN),
    (V_CLRWK,),
    (VSF_COLOR, (), (1,)),
    (VSF_INTERIOR, (), (FIS_SOLID,)),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VR_RECFL, (20, 20, 200, 60), ()),
    (VSWR_MODE, (), (MD_XOR,)),
    (VR_RECFL, (60, 30, 160, 50), ()),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VST_COLOR, (), (1,)),
    (V_GTEXT, (20, 80), tuple(ord(c) for c in "GEM ON A 6502")),
    (VS_CLIP, (213, 140, 244, 160), (1,)),
    (V_GTEXT, (210, 150), tuple(ord(c) for c in "CLIPPED")),
    (VS_CLIP, (), (0,)),
    (VS_CLIP, (20, 184, 120, 185), (1,)),   # two rows through the cells:
    (V_GTEXT, (20, 188), tuple(b"ROWS CUT")),   # the raster's y clip
    (VS_CLIP, (), (0,)),
    (VRO_CPYFM, (21, 21, 120, 58, 203, 75, 302, 112), (6,)),
    (VRO_CPYFM, (21, 21, 120, 58, 203, 115, 302, 152), (1,)),
    (VST_HEIGHT, (0, 8), ()),
    (V_GTEXT, (230, 180), tuple(b"BIG")),
    (VST_HEIGHT, (0, 0), ()),
    (VSF_UDPAT, (), PAT),               # halves that differ, an odd byte
    (VSF_INTERIOR, (), (FIS_USER,)),
    (VR_RECFL, (9, 156, 197, 175), ()),
    (VR_RECFL, (203, 156, 206, 165), ()),
    (VR_RECFL, (212, 156, 219, 165), ()),
    (VSF_INTERIOR, (), (FIS_SOLID,)),
    (VSL_TYPE, (), (7,)),               # styled vertical lines (an_vline6)
    (VSL_UDSTY, (), (0xF0C9,)),
    (V_PLINE, (310, 21, 310, 187), ()),
    (VSWR_MODE, (), (MD_XOR,)),
    (V_PLINE, (315, 37, 315, 120), ()),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VSWR_MODE, (), (MD_XOR,)),         # the AES's dotted box (ESC_XLINE)
    (V_ESCAPE, (130, 181, 200, 181, 200, 190, 131, 190, 131, 181), (), None,
     ESC_XLINE),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (VSL_TYPE, (), (1,)),
    (VSWR_MODE, (), (MD_TRANS,)),       # text that reads the screen
    (V_GTEXT, (23, 33), tuple(b"TRANS 1")),
    (VSWR_MODE, (), (MD_XOR,)),
    (V_GTEXT, (101, 45), tuple(b"XOR WJ")),
    (VSWR_MODE, (), (MD_ERASE,)),
    (V_GTEXT, (61, 55), tuple(b"ERASE")),
    (VSWR_MODE, (), (MD_XOR,)),
    (V_GTEXT, (1, 70), tuple(b"I")),
    (VSWR_MODE, (), (MD_REPLACE,)),
    (GSX_START,),
    (OBJC_DRAW, FULL, (0, 8)),
]
FIND_AT, FIND_WANT = (30 + 56 + 18, 100 + 30 + 5), 3     # the OK button

DISK = os.path.abspath(os.path.join(ROOT, "build", "v6-boot.atr"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "v6.png"))
STATUS = 0x0600
SHOT_X0, SHOT_Y0 = 8, 24
FONT_W, FONT_H = 6, 6


def model():
    """test-m25's models, as test-m25 runs them: tools/vdiref.py and
    tools/aesref.py's object library on tools/devref.py's ANTIC, the tree
    test-m25's own."""
    L = Layout(m25_antic_vdi.POOL)
    v, a, _ = aesref.run(SCRIPT, m25_antic_vdi.tree(L), L.mem, dev=devref.Antic())
    return v.dev


def main(argv):
    keep = "--shot" in argv
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-v6: the VDI, banked, on a stock 6502")
    emu = launch(tag="v6", memsize="1088K", vbxe=False, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(500)
        for t in range(0, 6000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"AVK":
                break
        st = bytes(b.memdump(STATUS, 3))
        if not check(st == b"AVK", f"the program ran to its end (status {st!r}, "
                                   f"stage {chr(b.peek(STATUS + 3))!r})"):
            if b.peek(STATUS + 3) == ord("9"):  # the tree was written, then stuck
                good = b.peek(0x0655)
                check(good == 4, f"far_get reads back {good} of the 4 objects OB_SET "
                                 f"wrote, want 4")
            b.screenshot(SHOT)
            print(f"  screen: {SHOT}")
            return 1
        cpu = b.cmd("HWSTATE")["cpu"]["mode"]
        check(cpu == "6502", f"the CPU is a 6502 ({cpu})")
        banks = b.peek(STATUS + 8)
        check(banks >= BANKS_NEEDED, f"the probe found {banks} banks; {BANKS_NEEDED} are needed")
        far = b.peek(STATUS + 9)
        check(far >= 1, f"the far heap has {far} far bank(s) of 64 KB, want at least one")

        fb = b.peek(STATUS + 10)
        check(fb >= 1, f"the round-trip form is in far memory: bank {fb}")
        tree = int.from_bytes(bytes(b.memdump(0x0650, 4)), "little")
        check(tree >> 16 >= 1, f"the tree is in far memory: ${tree:06X}, bank {tree >> 16}")
        good = b.peek(0x0655)
        check(good == 4, f"far_get reads back {good} of the 4 objects OB_SET wrote at the "
                         f"tree's far address, want 4")
        found = b.peek(0x0654)
        check(found == FIND_WANT, f"objc_find at the OK button's middle {FIND_AT} "
                                  f"answered {found}, want {FIND_WANT}")
        name = bytes(b.memdump(0x0630, 20)).split(b"\0")[0].decode("latin-1")
        want = f"gem4xe system {FONT_W}x{FONT_H}"
        check(name == want, f"vqt_name says {name!r}, want {want!r}")

        b.frames(20)
        b.screenshot(SHOT)
        from PIL import Image
        im = Image.open(SHOT).convert("RGB")
        px = im.load()
        dev = model()
        seen = {px[SHOT_X0 + x, SHOT_Y0 + y] for y in range(AN_H) for x in range(AN_W)}
        if not check(len(seen) == 2, f"the playfield holds {len(seen)} colours, want 2"):
            return 1
        clear = next((x, y) for y in range(AN_H) for x in range(AN_W) if not dev.bit(x, y))
        setpx = next((x, y) for y in range(AN_H) for x in range(AN_W) if dev.bit(x, y))
        bg = px[SHOT_X0 + clear[0], SHOT_Y0 + clear[1]]
        fg = px[SHOT_X0 + setpx[0], SHOT_Y0 + setpx[1]]
        check(bg != fg and sum(bg) > sum(fg), f"pen 0 {bg} lighter than pen 1 {fg}")
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
    print(f"gem4xe-v6: {'PASS' if not fails else 'FAIL'} -- the VDI, banked, on a stock "
          f"6502, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
