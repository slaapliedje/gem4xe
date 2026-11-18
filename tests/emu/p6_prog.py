#!/usr/bin/env python3
"""p6_prog.py -- make test-p6: a program in a bank of its own, read from
the disk, on a stock 6502 (docs/6502.md, steps 5a and 5b).

src/p6_prog.c is built with the application kit alone -- src/app/gem.h,
gemlib.c, the 6502's gates and start-up -- and linked whole into one 16 KB
bank (src/app/gemapp6502.scm) and written to A6's boot disk as
P6PROG.G6A (tools/bsp6502/mkxex6502.py --g6a); when $060C is 1 at the go
A6 (src/a6_evt.c) reads it through CIO into a bank from the far heap
(step 5b) and starts it as a process of its own.  It knows one address of the
system's, the gate's at $2000 (src/sys6502/gate6502.s), and every call
goes through src/sys/abi.c, which turns its window addresses into its
bank's far ones.  The gate holds it to:

  - the pseudo-registers -- _Zp, _Vsp, _Vfp, which the calling convention
    shares -- at the same addresses in its link and the system's;
  - it was read from the disk: CIO's status 1 and every byte of the file;
    and timer 1, the pointer's sampler, counting at its rate after SIO
    had POKEY.  That guards the timer, not irq_pokey_resync: the XL OS's
    SIO leaves timer 1 alone, and this passes with the resync turned off,
    with --siopatch and with real serial timing alike;
  - it ran: its header found, its first turn over ($060C 'R'), main run to
    its end ($0640 'E'), no stub that must not run reached, and not one
    call refused (gem_bad);
  - the AES's answers, written into ITS bank through the far helpers:
    appl_init's ap_id 2 (A6's application 0, its accessory 1);
    global[0] the AES's version; a workstation from v_opnvwk; window 3,
    as the model numbers it; graf_handle's cell height;
  - its messages: its first is WM_REDRAW for its window; wind_get's work
    area is the model's; its redraw walked one rectangle; and its
    appl_write to process 0 arrived in A6's log with its ap_id and
    window -- a message buffer read from its bank;
  - the screen over its window, frame and shadow, pixel for pixel what
    tools/aesref.py and tools/vdiref.py draw for A6's calls and then its
    own: the title read from its bank at every redraw (wind_set's pair,
    made far in abi.c), its white inside and its text.

Broken on purpose (each fails): window addresses not made far; the
title's pair left as it came; the gate not recording the caller's bank;
the file not on the disk; the read not put into the slot.

And with --axlon SIZE (an Axlon of SIZE on a 130XE, whose 4 PORTB banks
are fewer): the same, on banks switched by $CFFF -- src/sys6502/
bank6502.s finds the Axlon's banks and rewrites every bank switch to
write its register.  Either way the probe's answer is checked: which
kind of bank, and how many.

    python3 tests/emu/p6_prog.py [--shot] [--axlon 2048K]
"""
import copy
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref                               # noqa: E402
import devref                               # noqa: E402
import a6_aes as A6                         # noqa: E402  A6's own calls
import p6rsc as P6RSC                       # noqa: E402  the program's resource
from aesref import (Layout, NAME, WF_NAME, WIND_CREATE, WIND_OPEN,  # noqa: E402
                    WIND_GET, G_STRING, SELECTED, FORM_ALERT, RETURN)
from vdiref import (VSWR_MODE, VSF_INTERIOR, VSF_COLOR, VS_CLIP,  # noqa: E402
                    VR_RECFL, V_GTEXT)

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6-boot.atr"))
G6A = os.path.abspath(os.path.join(ROOT, "build", "p6prog.g6a"))
G6A_NAME = "D1:P6PROG.G6A"
IRQ_TIMER_DIV, IRQ_PAL = 7, 8               # src/sys/irq.h's IRQ_STATE
FRAME = {0: 114 * 262, 1: 114 * 312}        # machine cycles a frame, NTSC and PAL
POKMSK = 0x0010
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
PMAP = os.path.abspath(os.path.join(ROOT, "build", "p6prog.map"))
SHARED = ("_Zp", "_Vsp", "_Vfp")            # the calling convention's, both links
SHOT = os.path.abspath(os.path.join(ROOT, "build", "p6.png"))
ASHOT = os.path.abspath(os.path.join(ROOT, "build", "p6-alert.png"))
STATUS = 0x0600
SHOT_X0, SHOT_Y0 = 8, 24
P6_HELLO = 0x4138
WM_REDRAW = 20
AES_VERSION = 0x0400
WIN3 = (30, 40, 180, 60)                    # src/p6_prog.c's window
TEXT = P6RSC.TEXT                           # object 1's string, which it draws
AWAY = (300, 180)                           # the pointer, off the window
STACK_PAINT, STACK_GUARD, STACK_MARGIN = 0xA5, 128, 64
RSC = os.path.abspath(os.path.join(ROOT, "build", "p6prog.rsc"))
# GEMDOS's answers (src/sys/gemdos.h, gemdos.c), written down again here
SVERSION = 0x1500                           # what TOS 1.04 says
GD_EFILNF = -33
GD_HANDLE_BASE, CIO_IOCBS = 6, 8            # a file's handle is 6 + its IOCB
GD_CALLS = 11                               # the program's, src/p6_prog.c files()
# its alert (step 5b-5), read out of the program's source: the model
# draws the same string
with open(os.path.join(ROOT, "src", "p6_prog.c")) as _f:
    ALERT = re.search(r'alert\[\] = "([^"]*)";', _f.read()).group(1)
ALERT_DEF, ALERT_ADDR = 2, 0x2021           # Return answers the default; the
                                            # address is the model's to choose


def model():
    """A6's calls (tests/emu/a6_aes.py), then the program's: its window
    created, titled and opened, and its redraw -- on the physical
    workstation, which draws what its virtual one does on this device."""
    L = Layout(A6.POOL, max_objs=21)
    objs = A6.menu(L)
    L2 = Layout(L.next, max_objs=1)
    objs2 = A6.desk(L2)
    mem = dict(L.mem)
    mem.update(L2.mem)
    probe = aesref.run(A6.PRELUDE, copy.deepcopy(objs), dict(mem),
                       dev=devref.Antic())[1]
    f = probe.gl_rfull
    full = (f.x, f.y, f.w, f.h)
    head = A6.PRELUDE + [
        A6.wset(0, A6.WF_NEWDESK, 0, L2.base, 0),
        (WIND_CREATE, (), (A6.KINDS,) + full),
        A6.wset(1, WF_NAME, 0, L2.text("First")),
        A6.wset(1, A6.WF_INFO, 0, L2.text("a window on a 6502")),
        (WIND_OPEN, (), (1,) + A6.W1),
        (WIND_CREATE, (), (A6.NAME | A6.MOVER | A6.CLOSER,) + full),
        A6.wset(2, WF_NAME, 0, L2.text("Second")),
        (WIND_OPEN, (), (2,) + A6.W2),
        (A6.MENU_BAR, (), (1,)),
        (WIND_CREATE, (), (NAME,) + WIN3),
        A6.wset(3, WF_NAME, 0, L2.text(" BANKED ")),
        (WIND_OPEN, (), (3,) + WIN3),
        (WIND_GET, (), (3, 4)),             # WF_WORKXYWH
    ]
    mem.update(L2.mem)
    _, _, res = aesref.run(head, copy.deepcopy(objs), dict(mem),
                           trees={L2.base: objs2}, home=L.base, dev=devref.Antic())
    wh = res[len(A6.PRELUDE) + 9][2]
    x, y, w, h = res[-1][3:7]
    pxy = (x, y, x + w - 1, y + h - 1)      # one rectangle: the top window
    script = head + [
        (VSWR_MODE, (), (1,)),
        (VSF_INTERIOR, (), (1,)),
        (VSF_COLOR, (), (0,)),
        (VS_CLIP, pxy, (1,)),
        (VR_RECFL, pxy, ()),
        (V_GTEXT, (x + 4, y + 12), tuple(ord(c) for c in TEXT)),
        (VS_CLIP, pxy, (0,)),
        (FORM_ALERT, (), (ALERT_DEF,), ALERT_ADDR),
    ]
    # the alert: drawn, the screen as it shows, then Return
    plan = {len(script) - 1: [("frames", 1), ("shot",), ("key", "RETURN", RETURN)]}
    v, a, res = aesref.run(script, objs, mem, trees={L2.base: objs2}, home=L.base,
                           dev=devref.Antic(), plan=plan, pointer=AWAY,
                           pool=ALERT_ADDR, buffers={ALERT_ADDR: ALERT})
    return v.dev, wh, (x, y, w, h), a.shots[0], res[-1][2]


# what the probe should find: (b6_kind, b6_count)
PORTB_1088K = ("P", 64)
AXLON_BASE = "128K"                         # a 130XE's 4 PORTB banks beside it: the
                                            # probe must take the Axlon's, which are more
AXLON_BANKS = {"64K": 3, "128K": 7, "256K": 15, "512K": 31, "1024K": 63,
               "2048K": 127, "4096K": 255}             # its bank 0 is main memory


def main(argv):
    keep = "--shot" in argv
    axlon = argv[argv.index("--axlon") + 1] if "--axlon" in argv else None
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-p6: a program in a bank of its own, read from the disk, on a stock 6502"
          + (f" with an Axlon of {axlon}" if axlon else ""))
    dev, want_wh, want_work, alert_shot, want_alert = model()
    text = open(MAP).read()

    def sym(n):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", text, re.M).group(1), 16)

    ptext = open(PMAP).read()
    for n in SHARED:
        a, p = (re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", t, re.M) for t in (text, ptext))
        check(a and p and a.group(1) == p.group(1),
              f"{n} is at ${a.group(1) if a else '?'} in the system and "
              f"${p.group(1) if p else '?'} in the program")

    if axlon:
        want_banks = ("A", AXLON_BANKS[axlon])
        # booted through the bridge: a --disk given with a memory size
        # other than the emulator's 1088K is not booted (it starts the
        # Memo Pad)
        emu = launch(tag="p6", memsize=AXLON_BASE, vbxe=False, rapidus=False,
                     extra_args=["--axlonmemsize", axlon])
        emu.bridge.boot(DISK)
    else:
        want_banks = PORTB_1088K
        emu = launch(tag="p6", memsize="1088K", vbxe=False, rapidus=False,
                     extra_args=["--disk", DISK])
    b = emu.bridge

    def w16(at):
        return b.peek(at) | (b.peek(at + 1) << 8)

    def poke16(at, v):
        b.poke(at, v & 0xFF)
        b.poke(at + 1, (v >> 8) & 0xFF)
    try:
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        # THE SYSTEM'S C STACK, 1 KB shared by every call (docs/6502.md,
        # 5b-3): its bottom GUARD bytes painted now, while A6 waits near the
        # top, and at least MARGIN of them must still be paint at the end.
        # It overflowed into the VDI's workstation table, silently, until
        # a program got a stack of its own and vdi.c lost its inlining.
        cs_lo = int(re.search(r"^cstack\s+([0-9a-f]+)-", text, re.M).group(1), 16)
        b.memload(cs_lo, bytes([STACK_PAINT]) * STACK_GUARD)
        b.poke(STATUS + 0x62, 0)            # its alert waits for this
        b.poke(STATUS + 12, 1)              # the program, at the go
        b.poke(STATUS + 6, 1)

        def until(*stages):
            for _ in range(600):
                b.frames(5)
                if b.peek(STATUS + 0x40) in stages or b.peek(STATUS + 4):
                    break
        until(ord("a"), ord("E"))
        # ITS ALERT (step 5b-5): the pointer off it, the alert raised and
        # photographed, then Return, which presses the default button
        alert_px = None
        if b.peek(STATUS + 0x40) == ord("a"):
            ptr = sym("ptr_state")
            poke16(ptr + 6, 0)              # PTR_NONE: the gate moves it
            poke16(ptr, AWAY[0])
            poke16(ptr + 2, AWAY[1])
            b.frames(30)
            b.poke(STATUS + 0x62, 1)
            b.frames(400)
            b.screenshot(ASHOT)
            from PIL import Image
            alert_px = Image.open(ASHOT).convert("RGB").load()
            b.key("RETURN")
            until(ord("E"))
        b.frames(60)
        kind, count = chr(b.peek(sym("b6_kind"))), b.peek(sym("b6_count"))
        check((kind, count) == want_banks,
              f"the probe found {count} banks of kind {kind!r}; want {want_banks[1]} "
              f"of {want_banks[0]!r} ({'an Axlon of ' + axlon if axlon else 'PORTB, 1088K'})")
        stuck = b.peek(STATUS + 4)
        check(not stuck, f"no stub that must not run was reached "
                         f"({chr(stuck) if stuck else 'none'} at $0604)")
        rd, n_rd = b.peek(STATUS + 13), w16(STATUS + 14)
        check(rd == 1 and n_rd == os.path.getsize(G6A),
              f"it was read from the disk: CIO status {rd}, {n_rd} bytes; "
              f"{G6A_NAME} is {os.path.getsize(G6A)}")
        slot = b.peek(STATUS + 12)
        check(slot == ord("R"), f"the slot held a program and its first turn ended "
                                f"($060C {chr(slot) if slot > 31 else slot!r})")
        # its bank: 16 KB from the far heap, on a 16 KB boundary, and the
        # veneer's bank byte the PORTB bank that maps it (far bank k,
        # piece p is b6_far_base + (k-1)*4 + p, src/sys6502/farmem6502.c)
        at = sym("p6_slot")
        ps = w16(at) | (w16(at + 2) << 16)
        k, p = ps >> 16, (ps >> 14) & 3
        want_b = b.peek(sym("b6_far_base")) + (k - 1) * 4 + p
        vb = b.peek(sym("p6_ven") + 5)
        check(ps and not ps & 0x3FFF and 1 <= k,
              f"its bank came from the far heap at ${ps:06X}, 16 KB-aligned")
        check(vb == want_b and want_b < count,
              f"its veneer maps bank {vb}; far bank {k} piece {p} is {want_b} "
              f"of {count}")
        stage = b.peek(STATUS + 0x40)
        if not check(stage == ord("E"), f"the program ran to its end "
                                        f"(stage {chr(stage) if stage > 31 else stage!r})"):
            b.screenshot(SHOT)
            print(f"  screen: {SHOT}")
            return 1
        # SIO has had POKEY: timer 1, the pointer's sampler, counts on at its rate
        irq = sym("irq")
        t0 = w16(sym("irq_timer")) | (w16(sym("irq_timer") + 2) << 16)
        b.frames(100)
        t1 = w16(sym("irq_timer")) | (w16(sym("irq_timer") + 2) << 16)
        div, pal = b.peek(irq + IRQ_TIMER_DIV), b.peek(irq + IRQ_PAL)
        want = 100 * FRAME[pal] / (28 * (div + 1))
        check(abs((t1 - t0) - want) <= want * 0.02 and b.peek(POKMSK) & 1,
              f"after the read, timer 1 counted {t1 - t0} in 100 frames, want {want:.0f}; "
              f"POKMSK ${b.peek(POKMSK):02X}")
        paint = bytes(b.memdump(cs_lo, STACK_GUARD))
        spare = next((i for i, x in enumerate(paint) if x != STACK_PAINT), STACK_GUARD)
        check(spare >= STACK_MARGIN,
              f"the system's C stack kept {spare} of its bottom {STACK_GUARD} bytes "
              f"untouched (${cs_lo:04X} up); want {STACK_MARGIN}")
        bad, op = w16(sym("gem_bad")), w16(sym("gem_badop"))
        check(bad == 0, f"no call refused (gem_bad {bad}, last opcode {op:#x})")

        ap, ver = b.peek(STATUS + 0x41), w16(STATUS + 0x42)
        vh, wh, hc = b.peek(STATUS + 0x44), b.peek(STATUS + 0x45), b.peek(STATUS + 0x46)
        check(ap == 2, f"appl_init answered ap_id {ap}, want 2")
        check(ver == AES_VERSION, f"global[0], written in its bank, is {ver:#06x}, "
                                  f"want {AES_VERSION:#06x}")
        check(vh > 0, f"v_opnvwk answered workstation {vh}")
        check(wh == want_wh, f"wind_create answered window {wh}; the model {want_wh}")
        check(hc == 6, f"graf_handle's cell height {hc}, want 6")

        mt, mw = b.peek(STATUS + 0x47), b.peek(STATUS + 0x48)
        check((mt, mw) == (WM_REDRAW, wh), f"its first message was {mt} for window {mw}, "
                                          f"want WM_REDRAW ({WM_REDRAW}) for {wh}")
        work = tuple(w16(STATUS + 0x49 + 2 * k) for k in range(4))
        check(work == want_work, f"its work area {work}; the model {want_work}")
        # its resource (step 5b-3): loaded far, its tree read and written
        # through far_fetch/far_store, and read by the AES itself
        ld, ga = b.peek(STATUS + 0x52), b.peek(STATUS + 0x53)
        check((ld, ga) == (1, 1), f"rsrc_load answered {ld} and rsrc_gaddr {ga}, want 1 and 1")
        tr = w16(STATUS + 0x54) | (w16(STATUS + 0x56) << 16)
        check(tr >> 16 >= 1 and not ps <= tr < ps + 0x4000,
              f"its tree is at ${tr:06X}: in the far heap, outside its own bank ${ps:06X}")
        ty, st = b.peek(STATUS + 0x58), b.peek(STATUS + 0x59)
        check(ty == G_STRING, f"object 1, fetched, is of type {ty}; want G_STRING ({G_STRING})")
        check(st == SELECTED, f"object 2's state, stored SELECTED and fetched back, is {st}")
        wc = b.peek(STATUS + 0x5E)
        ox, oy = w16(STATUS + 0x5A), w16(STATUS + 0x5C)
        want_o = ((P6RSC.ROOT_X + P6RSC.OK_X) * wc, (P6RSC.ROOT_Y + P6RSC.OK_Y) * hc)
        check((ox, oy) == want_o, f"objc_offset of object 2, read by the AES from the far "
                                  f"tree, is {(ox, oy)}; cells of {wc}x{hc} make {want_o}")
        fr = b.peek(STATUS + 0x5F)
        check(fr == 1, f"rsrc_free answered {fr}, want 1")

        # GEMDOS from a bank (docs/6502.md, 5b-4): every address the
        # program passes is in its own bank, and comes back through it
        rsc = open(RSC, "rb").read()
        with open(DISK, "rb") as f:
            secsize = int.from_bytes(f.read(6)[4:6], "little")
        g = bytes(b.memdump(STATUS + 0x80, 0x44))
        check(g[0] | g[1] << 8 == SVERSION, f"Sversion answered ${g[0] | g[1] << 8:04X}, "
                                            f"want ${SVERSION:04X}")
        check(g[2] == 1, "Fgetdta gave back the program's own DTA, the one Fsetdta set")
        name = g[0x10:0x1E].split(b"\0")[0]
        # GEMDOS's rule for a DOS 2 directory: its sectors times 125
        want_len = -(-len(rsc) // (secsize - 3)) * 125
        dlen = int.from_bytes(g[4:8], "little")
        check(g[3] == 0 and name == b"P6PROG.RSC" and dlen == want_len,
              f"Fsfirst(\"*.RSC\") answered {g[3]}, into its DTA {name!r} of {dlen} "
              f"bytes; want 0, b'P6PROG.RSC', {want_len}")
        h = g[8] | g[9] << 8
        check(GD_HANDLE_BASE <= h < GD_HANDLE_BASE + CIO_IOCBS,
              f"Fopen(\"P6PROG.RSC\") gave handle {h}, want a file's, "
              f"{GD_HANDLE_BASE}-{GD_HANDLE_BASE + CIO_IOCBS - 1}")
        check(g[0xA] == 18 and g[0x20:0x32] == rsc[:18],
              f"Fread of 18 bytes read {g[0xA]}: {g[0x20:0x32].hex()}, "
              f"want the file's {rsc[:18].hex()}")
        check(g[0xB] == 0 and g[0xC] == 4 and g[0x34:0x38] == rsc[:4],
              f"Fseek(0) answered {g[0xB]}, and a read of 4 then gave {g[0xC]}: "
              f"{g[0x34:0x38].hex()}, want 0, 4, {rsc[:4].hex()}")
        check(g[0xE] == 0, f"Fclose answered {g[0xE]}, want 0")
        check(g[0xF] == 0 and g[0x38] == 0,
              f"Dgetpath answered {g[0xF]} and {g[0x38:0x40]!r}, want 0 and \"\" "
              f"(no Dsetpath yet)")
        nf = int.from_bytes(g[0x40:0x44], "little", signed=True)
        check(nf == GD_EFILNF, f"Fopen of a file that is not there answered {nf}, "
                               f"want {GD_EFILNF}")
        lo, hi = w16(sym("b6init_lo")), w16(sym("b6init_hi"))
        peak, refused = w16(sym("pool6_peak")), w16(sym("pool6_refused"))
        check(lo < peak <= hi and refused == 0,
              f"the pool went to ${peak:04X} of ${lo:04X}-${hi:04X} (the load-time "
              f"code's), refusing {refused}")
        calls, bad = w16(sym("gemdos_calls")), w16(sym("gemdos_bad"))
        check(calls == GD_CALLS and bad == 0,
              f"GEMDOS served {calls} call(s), {bad} of them unknown; want {GD_CALLS}, 0")
        pieces = b.peek(STATUS + 0x51)
        check(pieces == 1, f"its redraw painted {pieces} rectangle(s), want 1")

        # its alert: the screen while it showed, against the model's, over
        # the rectangle the alert changed (and a margin); the answer Return
        # gave; and, below, the window under it put back as it was
        if check(alert_px is not None, "the program reached its alert"):
            ink = devref.Antic.INK
            sw, sh = len(alert_shot[0]), len(alert_shot)
            moved = [(x, y) for y in range(sh) for x in range(sw)
                     if (alert_shot[y][x] == ink) != bool(dev.bit(x, y))]
            ax0 = max(min(x for x, _ in moved) - 4, 0)
            ax1 = min(max(x for x, _ in moved) + 5, sw)
            ay0 = max(min(y for _, y in moved) - 4, 0)
            ay1 = min(max(y for _, y in moved) + 5, sh)
            on = next((x, y) for y in range(ay0, ay1) for x in range(ax0, ax1)
                      if alert_shot[y][x] == ink)
            off = next((x, y) for y in range(ay0, ay1) for x in range(ax0, ax1)
                       if alert_shot[y][x] != ink)
            afg = alert_px[SHOT_X0 + on[0], SHOT_Y0 + on[1]]
            abg = alert_px[SHOT_X0 + off[0], SHOT_Y0 + off[1]]
            abad, afirst = 0, []
            for y in range(ay0, ay1):
                for x in range(ax0, ax1):
                    want_ink = alert_shot[y][x] == ink
                    if alert_px[SHOT_X0 + x, SHOT_Y0 + y] != (afg if want_ink else abg):
                        abad += 1
                        if len(afirst) < 4:
                            afirst.append((x, y, want_ink))
            atotal = (ax1 - ax0) * (ay1 - ay0)
            check(afg != abg and not abad,
                  f"the alert {ALERT!r}: {atotal - abad:,} of {atotal:,} pixels over "
                  f"({ax0},{ay0})-({ax1 - 1},{ay1 - 1}) as the model draws it; first "
                  f"differing (x, y, wanted) {afirst}")
        got_alert = w16(STATUS + 0x60)
        check(got_alert == want_alert == ALERT_DEF,
              f"form_alert answered {got_alert} to Return; the model {want_alert}, "
              f"the default button {ALERT_DEF}")

        n, base = w16(sym("a6_nlog")), sym("a6_log")
        got = []
        for k in range(min(n, 8)):
            r = [w16(base + (k * 10 + j) * 2) for j in range(10)]
            if r[7] == P6_HELLO:
                got.append((r[8], r[9]))
        check(got == [(ap, wh)], f"process 0 got its appl_write, ap_id and window "
                                 f"{got}, want {[(ap, wh)]}")

        # the pointer off the window, then the window's pixels
        ptr = sym("ptr_state")
        poke16(ptr + 6, 0)                  # PTR_NONE: the gate moves it
        poke16(ptr, AWAY[0])
        poke16(ptr + 2, AWAY[1])
        b.frames(30)
        b.screenshot(SHOT)
        from PIL import Image
        px = Image.open(SHOT).convert("RGB").load()
        x0, y0, ww, hh = WIN3
        x1, y1 = x0 + ww + 2, y0 + hh + 2   # and the drop shadow
        clear = next((x, y) for y in range(y0, y1) for x in range(x0, x1) if not dev.bit(x, y))
        setpx = next((x, y) for y in range(y0, y1) for x in range(x0, x1) if dev.bit(x, y))
        bg = px[SHOT_X0 + clear[0], SHOT_Y0 + clear[1]]
        fg = px[SHOT_X0 + setpx[0], SHOT_Y0 + setpx[1]]
        bad_px, first = 0, []
        for y in range(y0, y1):
            for x in range(x0, x1):
                exp = fg if dev.bit(x, y) else bg
                if px[SHOT_X0 + x, SHOT_Y0 + y] != exp:
                    bad_px += 1
                    if len(first) < 4:
                        first.append((x, y, dev.bit(x, y)))
        total = (x1 - x0) * (y1 - y0)
        check(bg != fg and not bad_px,
              f"{total - bad_px:,} of {total:,} pixels over its window as the model has "
              f"them; first differing (x, y, wanted) {first}")
    finally:
        emu.stop()
    for shot in (SHOT, ASHOT):
        if not fails and not keep and os.path.exists(shot):
            os.remove(shot)
    print(f"gem4xe-p6: {'PASS' if not fails else 'FAIL'} -- a program in a bank of its "
          f"own, read from the disk, on a stock 6502, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
