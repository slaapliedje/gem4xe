#!/usr/bin/env python3
"""n6_menu.py -- make test-n6: the desktop's MENUS on a stock 6502.

No gate chose a desktop menu item on the 6502 until a real 600XL did:
the drop-down opened, the click closed it, the title stayed selected and
nothing happened.  The AES sent MN_SELECTED to proc_app, its slot 0 --
on the 65C816 always the program whose bar it is, on the 6502 A6, which
runs the desktop as another process (src/aes/ctrl.c, hctl_rect).  The
gate holds the desktop, loaded as test-d6 loads it, to:

  - Desk > About gem4xe...: the desktop's own message buffer (G.g_rmsg,
    in its RAM under the ROM) holds MN_SELECTED for DESKMENU/ABOUITEM;
    the About box is drawn over the desk, and says what the machine is:
    6502, ANTIC or VBXE, 1088K -- which this gate knows because it chose
    the machine, read out of the box's own strings in the desktop's far
    memory; Return closes it, and the desk
    and the Desk title are back as they were -- the title put back is
    the desktop's menu_tnormal, so it is the desktop having ACTED;
  - View > Show as text, then Show as icons: G.g_iview goes 0 -> 1 -> 0,
    a change only the desktop's own handler makes, and the View title is
    put back each time;
  - no call refused.

G's offsets are read from desk.h's layout and checked first: g_desk must
be the desk under the bar (0, hbox, the screen's width, the rest of its
height), so a moved field fails here by name, not as a silent miss.

With --vbxe (make test-n6v) the same on a VBXE machine, 640x240.

    python3 tests/emu/n6_menu.py [--vbxe] [--shot]
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6d-boot.atr"))
DESK = os.path.abspath(os.path.join(ROOT, "build", "a6d-desk.atr"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
DMAP = os.path.abspath(os.path.join(ROOT, "build", "desk6.map"))
RSCH = os.path.abspath(os.path.join(ROOT, "build", "deskrsc.h"))
STATUS = 0x0600
MN_SELECTED = 10
# desk.h's DESKTOP_GLOBALS on the 6502: six 4-byte tree/far pointers,
# then g_handle, g_wchar, g_hchar, g_wbox, g_hbox, g_desk ...
G_HBOX, G_DESK, G_IVIEW, G_RMSG = 0x20, 0x22, 0x2E, 0x4C
G_AINFO = 0x04                          # G.a_info, the About tree (far)
OBJ_SIZE, OB_SPEC = 24, 12              # an OBJECT on the 6502
# where the screen puts things (screen pixels; found from screenshots)
AT = dict(W=320, H=192, DESK_T=(14, 3), ABOUT=(30, 13), VIEW_T=(100, 3),
          ICONS=(110, 11), TEXT=(110, 17), PARK=(200, 120),
          TITLES=(0, 0, 180, 8), MIDDLE=(60, 60, 260, 140), OFF=(8, 24),
          D1=(34, 26), D2=(114, 26), FILE_T=(52, 3), OPEN=(62, 13),
          T_BACK=(108, 38, 152, 43), T_FRONT=(108, 50, 152, 55), DIGIT=(6, 12))
VBXE_AT = dict(W=640, H=240, DESK_T=(30, 4), ABOUT=(50, 15), VIEW_T=(135, 4),
               ICONS=(150, 15), TEXT=(150, 23), PARK=(400, 150),
               TITLES=(0, 0, 360, 10), MIDDLE=(120, 70, 520, 170), OFF=(16, 0))


def main(argv):
    vbxe = "--vbxe" in argv
    keep = "--shot" in argv
    at = VBXE_AT if vbxe else AT
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    what = "on a stock 6502" + (" with a VBXE" if vbxe else "")
    print(f"gem4xe-n6: the desktop's menus {what}")
    text = open(MAP).read()
    dtext = open(DMAP).read()
    rsch = open(RSCH).read()

    def sym(n, t=None):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", t or text, re.M).group(1), 16)

    def rsc(n):
        return int(re.search(rf"^#define {n}\s+(\d+)", rsch, re.M).group(1))
    G = sym("G", dtext)
    DESKMENU, VIEWMENU = rsc("DESKMENU"), rsc("VIEWMENU")
    ABOUITEM, ICONITEM, TEXTITEM = rsc("ABOUITEM"), rsc("ICONITEM"), rsc("TEXTITEM")
    DECPU, DEVIDEO, DEMEM = rsc("DECPU"), rsc("DEVIDEO"), rsc("DEMEM")
    shots = os.path.join(ROOT, "build", "n6v" if vbxe else "n6")
    os.makedirs(shots, exist_ok=True)

    emu = launch(tag="n6v" if vbxe else "n6", memsize="1088K", vbxe=vbxe, rapidus=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    ptr = sym("ptr_state")

    def w16(a):
        return b.peek(a) | (b.peek(a + 1) << 8)

    def rom_out():                      # RAM under the ROM reads as RAM
        for _ in range(50):             # only with the ROM out (d6_desk.py)
            if not b.peek(0xD301) & 1:
                return
            b.frames(1)

    def gw(off, n=1):
        rom_out()
        m = bytes(b.memdump(G + off, 2 * n))
        return [m[2 * k] | m[2 * k + 1] << 8 for k in range(n)]

    def far(a, n):
        """n bytes at far address a (src/sys6502/farmem6502.c): far bank
        k's piece p is PORTB bank b6_far_base + (k - 1) * 4 + p, read
        through the debugger by its PORTB value, whatever is mapped."""
        if a < 0x10000:
            rom_out()
            return bytes(b.memdump(a, n))
        base, table = b.peek(sym("b6_far_base")), sym("b6_portb")
        out = bytearray()
        for i in range(n):
            k, off = (a + i) >> 16, (a + i) & 0xFFFF
            pb = b.peek(table + base + (k - 1) * 4 + (off >> 14))
            # Altirra's PP'AAAA: bank by PORTB value; only $ on the first
            out.append(b.ok(f"EVAL db(${pb:02X}'{0x4000 + (off & 0x3FFF):04X})")["value"])
        return bytes(out)

    def cstr(a):
        s = far(a, 17)
        return s[:s.index(0)].decode("latin-1") if 0 in s else repr(s)

    def move(xy):
        b.poke(ptr, xy[0] & 0xFF)
        b.poke(ptr + 1, xy[0] >> 8)
        b.poke(ptr + 2, xy[1])
        b.poke(ptr + 3, 0)
        b.frames(40)

    def click():                        # the ST mouse's button: port 2's trigger
        b.joy(1, "centre", True)
        b.frames(6)
        b.joy(1, "centre", False)
        b.frames(6)

    tries = []

    def choose(title, item, done):
        """Into the bar over the title (the drop-down opens on arrival),
        down onto the item, a click; then the pointer off the bar -- until
        `done()` says the desktop acted, polled, never one fixed wait: a
        6502 drawing ANTIC's screen is slow, and how slow moves with every
        build.  Three tries; how many it took is reported."""
        for k in range(1, 4):
            move(title)
            b.frames(40)
            move((item[0], title[1] + 4))
            move(item)
            b.frames(60)
            click()
            for _ in range(30):
                b.frames(20)
                if done():
                    break
            move(at["PARK"])
            b.frames(300)
            if done():
                tries.append(k)
                return True
        tries.append(0)
        return False

    def region(name, tag):
        """The screen's pixels in a rectangle, from a screenshot."""
        from PIL import Image
        path = os.path.join(shots, f"{tag}.png")
        b.screenshot(path)
        x0, y0, x1, y1 = at[name]
        ox, oy = at["OFF"]
        return bytes(Image.open(path).convert("L").crop((x0 + ox, y0 + oy, x1 + ox, y1 + oy)).tobytes())

    def differ(a, c):
        return sum(1 for p, q in zip(a, c) if p != q)
    try:
        b.mount(1, DESK)
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        b.poke(STATUS + 12, 2)              # the desktop, at the go
        b.poke(STATUS + 6, 1)
        for _ in range(300):
            b.frames(100)
            if b.peek(STATUS + 12) == ord('R'):
                break
        b.frames(2000)
        if not check(b.peek(STATUS + 12) == ord('R') and b.peek(STATUS + 4) == 0,
                     f"the desktop is up (stage {b.peek(STATUS + 12):#x}, stop {b.peek(STATUS + 4)})"):
            return 1
        hbox = gw(G_HBOX)[0]
        desk = gw(G_DESK, 4)
        if not check(desk == [0, hbox, at["W"], at["H"] - hbox],
                     f"G's layout: g_desk {desk} is the desk under a {hbox}-line bar "
                     f"(0, {hbox}, {at['W']}, {at['H'] - hbox})"):
            return 1
        move(at["PARK"])
        b.frames(200)
        titles0 = region("TITLES", "0-titles")
        middle0 = region("MIDDLE", "0-middle")

        # Desk > About gem4xe...
        def about_chosen():
            m = gw(G_RMSG, 5)
            return m[0] == MN_SELECTED and m[3] == DESKMENU and m[4] == ABOUITEM
        choose(at["DESK_T"], at["ABOUT"], about_chosen)
        msg = gw(G_RMSG, 5)
        check(msg[0] == MN_SELECTED and msg[3] == DESKMENU and msg[4] == ABOUITEM,
              f"Desk > About: the desktop's message buffer holds MN_SELECTED "
              f"(words {msg}; want {MN_SELECTED}, -, -, {DESKMENU}, {ABOUITEM})")
        d = differ(region("MIDDLE", "1-about"), middle0)
        check(d > 2000, f"...and the About box is drawn over the desk ({d} pixels changed)")
        rom_out()
        info = bytes(b.memdump(G + G_AINFO, 4))
        info = info[0] | info[1] << 8 | info[2] << 16
        got = []
        for o in (DECPU, DEVIDEO, DEMEM):
            sp = far(info + o * OBJ_SIZE + OB_SPEC, 4)
            got.append(cstr(sp[0] | sp[1] << 8 | sp[2] << 16))
        want = ["6502", "VBXE" if vbxe else "ANTIC", "1088K"]
        check(got == want, f"...and says what the machine is: {got} (want {want})")
        b.key_tap("RETURN")
        b.frames(600)
        d = differ(region("MIDDLE", "2-closed"), middle0)
        check(d == 0, f"Return closes it: the desk is as it was ({d} pixels differ)")
        d = differ(region("TITLES", "2-titles"), titles0)
        check(d == 0, f"...and the Desk title is put back, by the desktop ({d} pixels differ)")

        # View > Show as text, then Show as icons
        v0 = gw(G_IVIEW)[0]
        choose(at["VIEW_T"], at["TEXT"], lambda: gw(G_IVIEW)[0] == 1)
        v1 = gw(G_IVIEW)[0]
        d = differ(region("TITLES", "3-titles"), titles0)
        check(v0 == 0 and v1 == 1 and d == 0,
              f"View > Show as text: g_iview {v0} -> {v1} (want 0 -> 1), the title back ({d} pixels differ)")
        choose(at["VIEW_T"], at["ICONS"], lambda: gw(G_IVIEW)[0] == 0)
        v2 = gw(G_IVIEW)[0]
        d = differ(region("TITLES", "4-titles"), titles0)
        check(v2 == 0 and d == 0,
              f"View > Show as icons: g_iview {v1} -> {v2} (want 0), the title back ({d} pixels differ)")

        # Two windows: D1's, then D2's in front of it
        for n, icon in enumerate((at["D1"], at["D2"]) if not vbxe else ()):
            move(icon)
            click()                     # selected, then File > Open
            b.frames(100)
            before = region("MIDDLE", f"5-before{n}")
            choose(at["FILE_T"], at["OPEN"],
                   lambda: differ(region("MIDDLE", "5-poll"), before) > 2000)
        if not vbxe:
            # The back window's title must be READABLE: its text the
            # same pixels as the front one's, but for the drive's digit.
            # Dimmed (DISABLED: every other pixel lost), ANTIC's 6x6 face
            # was noise -- seen first on a real 600XL.
            back, front = region("T_BACK", "5-windows"), region("T_FRONT", "5-windows")
            w = at["T_BACK"][2] - at["T_BACK"][0]
            lo, hi = at["DIGIT"]
            d = sum(1 for i, (p, q) in enumerate(zip(back, front))
                    if p != q and not lo <= i % w < hi)
            ink = sum(1 for p in back if p < 128)
            check(d == 0 and ink > 40,
                  f"two windows: the back one's title is drawn whole, like the front's "
                  f"({d} pixels differ outside the digit, {ink} dark)")

        print(f"  (clicks it took, per choice: {tries})")
        bad, op = w16(sym("gem_bad")), w16(sym("gem_badop"))
        check(bad == 0, f"no call refused (gem_bad {bad}, last opcode {op:#x})")
    finally:
        emu.stop()
        if not keep and not fails:
            for f in os.listdir(shots):
                os.remove(os.path.join(shots, f))
    word = "FAIL" if fails else "PASS"
    print(f"gem4xe-n6: {word} -- the desktop's menus {what}, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
