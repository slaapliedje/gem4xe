#!/usr/bin/env python3
"""6502 step 4e gate: the input poll and the event loop on a stock 6502.

build/a6-boot.atr is test-a6's program (src/a6_aes.c): the AES on one
process, its desk, two windows and a menu bar drawn.  Told to go ($0606),
it installs the interrupt handlers (src/sys6502/irq6502.s, step 4d),
selects the CX80 trak-ball, which a GEM4XE.CFG on a copy of the disk
names (MOUSE=TRAKBALL: no file is an ST mouse, src/a6_cfg.c), and runs an application's loop
(src/a6_evt.c): evnt_multi for a key, a click and a message, every answer
filed in a6_log.

  the handlers   in: irq.how IRQ_OS_CHAINED, VVBLKI and VIMIRQ theirs
  the trak-ball  JOY pulses move the AES's pointer, one axis at a time,
                 the handler counting and the poll turning counts into
                 pixels
  the keyboard   real keys, through the handler's ring and the VDI's
                 table: MU_KEYBD with the ST key word, Shift's with the
                 shift state
  the pointer    drawn: an arrow where it is, nothing where it was
  the menu       the pointer onto File drops it (the control manager's
                 own entry rectangle); Open clicked: MN_SELECTED with the
                 title and the item, and the screen under the drop-down put
                 back from its save in far memory
  the close box  the top window's, clicked: WM_CLOSED with its handle;
                 the loop closes it, and the window under it is told to
                 redraw and does: not a pixel of the closed one left in it
  the desk       a click: MU_BUTTON where it was, one click; two quick
                 ones: two
  a second       src/a6_evt.c's a6_acc, an accessory built in, with its
  process        own record, queue and context (step 4f): it parked, it
                 is given turns while the application waits (its timer
                 counts), and a key P makes the application send it
                 A6_PING, which it answers with A6_PONG -- the ping's
                 number, and the running pid the AES gave it, its own;
                 everything above runs with it there
  nothing else   nothing stopped: no stub that must not run, no far
                 address in a bank that is not there (the cc6502 fault
                 step 4e found in ob_change sent one); and no context
                 switch was refused: proc_yield offered turns nobody took

From the trak-ball on the pointer is the harness's (PTR_NONE in
ptr_state, positions and buttons written between frames), as the 65C816
gates drive it: JOY can only pulse a line once a frame.

  the tick       the AES's tick length the frame's: 20 ms on PAL, 17 on
                 NTSC (--ntsc, make test-e6n), and the double-click
                 window 220 ms of it -- the handlers, which find the
                 standard, go in before ev_init

    python3 tests/emu/a6_evt.py [--ntsc]
"""
import os
import re
import shutil
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
from atr import ATRImage, Dos2              # noqa: E402

BOOT = os.path.abspath(os.path.join(ROOT, "build", "a6-boot.atr"))
TRAKBALL_CFG = b"MOUSE=TRAKBALL\r\n"
MAP = os.path.join(ROOT, "build", "a6.map")
STATUS = 0x0600
VIMIRQ, VVBLKI = 0x0216, 0x0222
IRQ_OS_CHAINED, PTR_NONE = 3, 0
MU_KEYBD, MU_BUTTON, MU_MESAG = 0x01, 0x02, 0x10
MN_SELECTED, WM_REDRAW, WM_CLOSED = 10, 20, 22
A6_PING, A6_PONG = 0x4136, 0x4137       # src/a6_evt.c
A6_LOG, A6_REC = 8, 10                  # src/a6_evt.c
TITLE_FILE, ITEM_OPEN = 4, 17           # src/a6_tree.c's menu
FILE_AT, OPEN_AT = (60, 4), (66, 12)    # File's title; Open, in its box
CLOSER_AT = (102, 72)                   # window 2's close box: at 100,70
DESK_AT, DESK2_AT = (300, 180), (290, 170)
SCREEN, SCREEN_LEN = 0x8000, 0x1F00     # ANTIC's (src/antic/antic.h)
FB, STRIDE = 0x8100, 40                 # the framebuffer, 1 bit a pixel
FILE_BOX = (46, 9, 64, 14)              # File's drop-down and its frame
W1_UNDER = (104, 74, 196, 116)          # window 1's inside, where 2 was
AWAY = (260, 178)                       # the desk, clear of both boxes


def symbols():
    out = {}
    for line in open(MAP):
        m = re.match(r"\s+(\w+) = ([0-9a-f]{4})\s*$", line)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


def main():
    fails = []
    pal = "--ntsc" not in sys.argv

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    std = "PAL" if pal else "NTSC"
    print(f"gem4xe-e6: the input poll, the event loop and a second process, on a stock 6502 ({std})")
    sym = symbols()
    disk = os.path.abspath(os.path.join(ROOT, "build", f"a6-{'e6' if pal else 'e6n'}.atr"))
    shutil.copyfile(BOOT, disk)
    img = ATRImage.load(disk)
    Dos2(img).add_file("GEM4XE.CFG", TRAKBALL_CFG)
    img.save(disk)
    emu = launch(tag="e6" if pal else "e6n", memsize="1088K", vbxe=False, rapidus=False, pal=pal,
                 extra_args=["--disk", disk])
    b = emu.bridge

    def word(a):
        d = bytes(b.memdump(a, 2))
        v = d[0] | (d[1] << 8)
        return v - 0x10000 if v & 0x8000 else v

    def poke16(a, v):
        b.poke(a, v & 0xFF)
        b.poke(a + 1, (v >> 8) & 0xFF)

    ptr = sym["ptr_state"]

    def here():
        return word(sym["xrat"]), word(sym["yrat"])

    def still():
        """The pointer once it has stopped: the poll turns the handler's
        counts into pixels on the application's turns, and with a second
        process those come a little further apart -- a switch there and back
        is ~40 ms, more than 4 of NTSC's frames: still means still for 10."""
        last = here()
        for _ in range(30):
            b.frames(10)
            now = here()
            if now == last:
                return now
            last = now
        return last

    def move(xy):
        poke16(ptr, xy[0])
        poke16(ptr + 2, xy[1])
        b.frames(6)

    def button(v, n):
        poke16(ptr + 4, v)
        b.frames(n)

    def click(xy):
        move(xy)
        button(1, 14)
        button(0, 4)
        settle()

    def area(x0, y0, x1, y1):
        """The bytes covering x0..x1, rows y0..y1, as they are now."""
        return [bytes(b.memdump(FB + y * STRIDE + x0 // 8, x1 // 8 - x0 // 8 + 1))
                for y in range(y0, y1 + 1)]

    def inked(x, y, w=16, h=16):
        """Pixels set in the w x h box at x, y."""
        return sum(bin(v).count("1") for row in area(x, y, x + w - 1, y + h - 1) for v in row)

    def settle(limit=2000):
        """Until the screen has not changed for 20 frames and the loop is
        not closing a window: a redraw on a 1.79 MHz 6502 takes seconds,
        and a fixed wait cannot tell slow from wrong."""
        last, still = None, 0
        for _ in range(0, limit, 5):
            b.frames(5)
            scr = bytes(b.memdump(SCREEN, SCREEN_LEN))
            still = still + 1 if scr == last else 0
            last = scr
            if still >= 4 and b.peek(STATUS + 10) != 1:
                return True
        print("    (still drawing)")
        return False

    def log_since(mark):
        n = word(sym["a6_nlog"]) & 0xFFFF
        out = []
        for k in range(mark, n):
            a = sym["a6_log"] + (k % A6_LOG) * A6_REC * 2
            out.append([word(a + 2 * i) for i in range(A6_REC)])
        return n, out

    def show(r):
        return (f"which ${r[0] & 0xFFFF:02X} at {r[1]},{r[2]} buttons {r[3]} "
                f"kstate ${r[4] & 0xFFFF:X} key ${r[5] & 0xFFFF:04X} clicks {r[6]} "
                f"msg {r[7]} {r[8]} {r[9]}")

    try:
        b.frames(500)
        for _ in range(0, 3000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        if not check(bytes(b.memdump(STATUS, 3)) == b"A6K",
                     f"the AES started and drew (stage {chr(b.peek(STATUS + 3) or 32)!r}, "
                     f"stub ${b.peek(STATUS + 4):02X})"):
            return 1
        b.poke(STATUS + 6, 1)
        for _ in range(40):
            b.frames(5)
            if b.peek(STATUS + 7) == ord("L"):
                break
        if not check(b.peek(STATUS + 7) == ord("L"), "the event loop runs"):
            return 1
        check(b.peek(STATUS + 11) == ord("P") and word(sym["proc_n"]) == 2,
              f"a second process started and parked ($060B {b.peek(STATUS + 11):02X}, "
              f"proc_n {word(sym['proc_n'])})")
        b.frames(20)
        settle()
        # the pointer: on, an arrow, at the trak-ball's start, over window 2's
        # white inside -- and gone from there when it moves on
        on = inked(160, 96)

        # -- the handlers -----------------------------------------------------
        irq = sym["irq"]
        check(b.peek(irq) == IRQ_OS_CHAINED and
              word(VVBLKI) & 0xFFFF == sym["irq6_vbi"] and
              word(VIMIRQ) & 0xFFFF == sym["irq6_irq"],
              f"the handlers in: irq.how {b.peek(irq)}, VVBLKI ${word(VVBLKI) & 0xFFFF:04X}, "
              f"VIMIRQ ${word(VIMIRQ) & 0xFFFF:04X}")
        f0 = word(sym["irq_frames"]) & 0xFFFF
        b.frames(50)
        f1 = word(sym["irq_frames"]) & 0xFFFF
        check(((f1 - f0) & 0xFFFF) == 50, f"irq_frames counts beside the AES ({(f1 - f0) & 0xFFFF} in 50)")
        tick, dc = word(sym["gl_ticktime"]), word(sym["gl_dclick"])
        want = 20 if pal else 17
        check(tick == want and dc == 220 // want,
              f"the AES's tick is the {std} frame: {tick} ms (want {want}), the double-click "
              f"window {dc} ticks (want {220 // want})")

        # -- the trak-ball ----------------------------------------------------
        b.joy(1, "centre")
        x0, y0 = still()
        for i in range(30):
            b.joy(1, "down" if i % 2 == 0 else "centre")
            b.frames(1)
        x1, y1 = still()
        for i in range(30):
            b.joy(1, "right" if i % 2 == 0 else "centre")
            b.frames(1)
        x2, y2 = still()
        b.joy(1, "centre")
        check(x1 != x0 and y1 == y0, f"trak-ball pulses on one line move the AES's x: "
              f"({x0},{y0}) -> ({x1},{y1})")
        check(y2 != y1 and x2 == x1, f"...and on the other its y: ({x1},{y1}) -> ({x2},{y2})")

        bt = word(sym["ptr_seen"] + 4)
        check(bt == 0, f"no button held: the trak-ball has no right button, and its "
              f"paddle line reads free ({bt})")

        # the harness's pointer from here
        poke16(ptr + 6, PTR_NONE)
        move((200, 150))
        check(here() == (200, 150), f"the pointer is the harness's ({here()})")
        settle()
        check(on >= 20 and inked(160, 96) == 0 and inked(200, 150) >= 20,
              f"the pointer is drawn: {on} pixels of arrow where it started, none "
              f"there once it moved, {inked(200, 150)} where it went")

        # -- the keyboard -----------------------------------------------------
        mark = word(sym["a6_nlog"]) & 0xFFFF
        b.key("A")
        b.frames(20)
        b.key("A", shift=True)
        b.frames(20)
        mark, got = log_since(mark)
        keys = [r for r in got if r[0] & MU_KEYBD]
        for r in got:
            print("    " + show(r))
        check(len(keys) == 2 and keys[0][5] & 0xFFFF == 0x1E61,
              f"KEY A: MU_KEYBD, key $1E61 ({[hex(r[5] & 0xFFFF) for r in keys]})")
        check(len(keys) == 2 and keys[1][5] & 0xFFFF == 0x1E41 and keys[1][4] & 3,
              "SHIFT A: $1E41, with a shift in the state")

        # -- the second process -----------------------------------------------
        missing = [n for n in ("a6_acc_ticks", "a6_acc_pings", "a6_acc_got") if n not in sym]
        if check(not missing, f"the second process is in the program (missing: {missing})"):
            t0, n0 = word(sym["a6_acc_ticks"]) & 0xFFFF, word(sym["proc_turns"]) & 0xFFFF
            b.frames(100)                   # two seconds: twenty of its ticks
            t1, n1 = word(sym["a6_acc_ticks"]) & 0xFFFF, word(sym["proc_turns"]) & 0xFFFF
            check(10 <= (t1 - t0) & 0xFFFF <= 30,
                  f"it has turns while the application waits: its 100 ms timer "
                  f"{(t1 - t0) & 0xFFFF} times in 2 s, {(n1 - n0) & 0xFFFF} turns handed over")
            b.key("P")
            b.frames(30)
            b.key("P")
            b.frames(30)
            mark, got = log_since(mark)
            for r in got:
                print("    " + show(r))
            pong = [r for r in got if r[0] & MU_MESAG and r[7] == A6_PONG]
            acc = [word(sym["a6_acc_got"] + 2 * i) for i in range(4)]
            check(word(sym["a6_acc_pings"]) == 2 and acc == [A6_PING, 0, 2, 1],
                  f"key P twice: two A6_PINGs reached it, the last from pid 0, number 2, "
                  f"and it ran as pid 1 ({word(sym['a6_acc_pings'])}, {acc})")
            check([(r[8], r[9]) for r in pong] == [(1, 1), (2, 1)],
                  f"...and its A6_PONGs came back, numbered 1 and 2, from pid 1 "
                  f"({[(r[8], r[9]) for r in pong]})")

        # -- the menu ---------------------------------------------------------
        under = area(*FILE_BOX)
        move(FILE_AT)
        settle()                        # the drop-down drawn
        move(OPEN_AT)
        settle()
        click(OPEN_AT)
        mark, got = log_since(mark)
        for r in got:
            print("    " + show(r))
        sel = [r for r in got if r[0] & MU_MESAG and r[7] == MN_SELECTED]
        check(len(sel) == 1 and sel[0][8] == TITLE_FILE and sel[0][9] == ITEM_OPEN,
              f"File, then Open: MN_SELECTED, title {TITLE_FILE} item {ITEM_OPEN}")
        check(not any(r[0] & MU_BUTTON for r in got),
              "...and the click that chose it is the menu's, not the program's")
        move(AWAY)                      # the arrow out of the way
        settle()
        back = area(*FILE_BOX)
        diff = sum(a != c for ra, rc in zip(under, back) for a, c in zip(ra, rc))
        check(diff == 0, f"the drop-down gone, what it covered put back from the save "
              f"(far memory): {diff} byte(s) differ")

        # -- the close box ----------------------------------------------------
        move((200, 150))
        settle()
        click(CLOSER_AT)
        mark, got = log_since(mark)
        for r in got:
            print("    " + show(r))
        closed = [r for r in got if r[0] & MU_MESAG and r[7] == WM_CLOSED]
        check(len(closed) == 1 and closed[0][8] == 2,
              "window 2's close box: WM_CLOSED, handle 2")
        redraw = [r for r in got if r[0] & MU_MESAG and r[7] == WM_REDRAW]
        check(any(r[8] == 1 for r in redraw),
              f"closed, window 1 under it is told to redraw ({[r[8] for r in redraw]})")
        move(AWAY)
        settle()
        left = sum(bin(v).count("1") for row in area(*W1_UNDER) for v in row)
        check(left == 0, f"...and redraws it: no pixel of window 2 left inside window 1 "
              f"({left})")

        # -- the desk ---------------------------------------------------------
        # a held button answers every call while it is down (GEM's rule for
        # a wait already satisfied): the press is the first
        click(DESK_AT)
        mark, got = log_since(mark)
        for r in got[:3]:
            print("    " + show(r))
        btn = [r for r in got if r[0] & MU_BUTTON]
        check(btn and (btn[0][1], btn[0][2]) == DESK_AT and btn[0][6] == 1,
              f"a click on the desk: MU_BUTTON at {DESK_AT}, one click")
        move(DESK2_AT)
        button(1, 2)
        button(0, 2)
        button(1, 2)
        button(0, 2)
        settle()
        mark, got = log_since(mark)
        for r in got:
            print("    " + show(r))
        btn = [r for r in got if r[0] & MU_BUTTON]
        check(len(btn) == 1 and btn[0][6] == 2,
              f"two quick ones: one MU_BUTTON, two clicks ({[r[6] for r in btn]})")

        # -- nothing else -----------------------------------------------------
        stub = b.peek(STATUS + 4)
        check(stub == 0, f"nothing stopped at $0604 -- a stub that must not run, or "
              f"a far address in no bank (src/sys6502/farmem6502.c) (${stub:02X})")
        over = word(sym["ctx_over"]) & 0xFFFF
        check(over == 0, f"no context switch refused ({over})")
    finally:
        emu.stop()
        os.remove(disk)
    print(f"gem4xe-e6: {'PASS' if not fails else 'FAIL'} -- the input poll, the event "
          f"loop and a second process, on a stock 6502 ({std}), {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
