#!/usr/bin/env python3
"""MINES on the Atari: a game won, a game lost, every square drawn as the
field says, on the VBXE in colour and on ANTIC in two.

build/mines-test.atr is an appliance floppy -- G4DOS starting MINES in
the desktop's place.  The field is read out of the program's memory by
symbol (build/mines.sym, against where the loader put its near region),
so the gate knows where the mines are; the rules themselves are
tests/host/test_mines.py's.  Here it is the program round them:

  - up: its window, the smallest field the screen holds, every square
    closed on the screen;
  - a click on the middle square opens it -- the mines laid then, none on
    it or round it -- and every square is drawn open or closed as the
    field says, each open number with something drawn in it and each
    empty one plain;
  - the right button flags a square and takes the flag down; the clock
    runs while the game does;
  - every safe square clicked: won, its alert, and Return starts a new
    game, all closed;
  - a mine clicked: lost, every mine shown, its alert, a new game;
  - Expert from the Game menu: a field of 30 x 16, all of it on the
    screen; ^N a new game in the middle of one; ^Q the end.

A square's LEFT EDGE says whether it is open on either screen -- a
closed square's is white (the raised tile's light side, or the dither's
clear column), an open one's dark (the grid line) -- so one pixel a
square is the check, read from the screenshot where the field is.

    python3 tests/emu/mines.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "build"))
from a8test.launcher import launch            # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text                  # noqa: E402
from m7_form import poke16, apply_step, F, CLICK   # noqa: E402
from m17_desktop import header                # noqa: E402
from demo_aes import path                     # noqa: E402
from shots import placed, middle, PTR_NONE    # noqa: E402
from minesrsc import GAMEMENU, EXPITEM        # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "mines-test.atr")
MSYM = os.path.join(BUILD, "mines.sym")
MG4A = os.path.join(BUILD, "mines.g4a")
SYMS = os.path.join(BUILD, "gem.sym")
OUT = os.path.join(BUILD, "shots", "mines")
EDGE = 3                                      # src/apps/mines.c
MF_COUNT, MF_MINE, MF_OPEN, MF_FLAG = 0x0F, 0x10, 0x20, 0x40
FRESH, PLAYING, WON, LOST = 0, 1, 2, 3
# Where the playfield's top left lands in a screenshot (tests/emu/
# m26_fallback.py, tools/vbxeref.py): the VBXE's overlay from column 16
# of a 672-wide frame, ANTIC's inset at 8, 24 of a 336-wide one.
ORIGIN = {True: (16, 0, 640, 240), False: (8, 24, 320, 192)}

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def run(vbxe):
    tag = "vbxe" if vbxe else "antic"
    print(f"mines on {'the VBXE' if vbxe else 'ANTIC'}")
    syms = symfile.load(SYMS)
    msym = symfile.load(MSYM)
    link_near = header(MG4A)[0]
    work = tempfile.mkdtemp(prefix="mines-")
    disk = os.path.join(work, "mines.atr")
    shutil.copy(DISK, disk)
    emu = launch(tag=f"mines-{tag}", memsize="1088K", vbxe=vbxe,
                 extra_args=["--disk", disk])
    b = emu.bridge
    ptr = syms["ptr_state"]
    x0, y0, scr_w, scr_h = ORIGIN[vbxe]
    n = [0]

    def at(name):
        return b.peek16(syms["app_near"]) + msym[name] - link_near

    def w(name):
        v = b.peek16(at(name))
        return v - 0x10000 if v & 0x8000 else v

    def byte(name):
        return b.peek(at(name))

    def field():
        fw, fh = byte("mf_w"), byte("mf_h")
        return fw, fh, bytes(b.memdump(at("mf_cell"), fw * fh))

    def settle(limit=3000):
        """Until the program is idle for thirty frames.  Idle is NEARLY no
        calls, not none: while a game runs MINES wakes four times a second
        for its clock, a call or two each time, where drawing a square
        alone is a dozen.  Waiting for none waited out the whole limit
        after every move of a game -- a minute each."""
        calls = syms["app_calls"]
        last, still = b.peek16(calls), 0
        for _ in range(0, limit, 10):
            b.frames(10)
            now = b.peek16(calls)
            still = still + 1 if (now - last) & 0xFFFF <= 4 else 0
            last = now
            if still >= 3:
                return
        print("  (still busy)")

    def shot(name):
        n[0] += 1
        p = os.path.join(OUT, f"{tag}-{n[0]:02d}-{name}.png")
        b.screenshot(p)
        return p

    def here():
        return (b.peek16(ptr), b.peek16(ptr + 2))

    def go(xy):
        for st in [F(2)] + path(here(), xy) + [F(4)]:
            apply_step(b, ptr, st)

    def click_at(xy, buttons=1):
        go(xy)
        b.frames(4)
        poke16(b, ptr + 4, buttons)
        b.frames(8)
        poke16(b, ptr + 4, 0)
        b.frames(4)
        settle()

    def square_xy(c, r):
        fx, fy, cw, ch = w("fx"), w("fy"), w("cw"), w("chh")
        return (fx + c * cw + cw // 2, fy + r * ch + ch // 2)

    def click(c, r, buttons=1):
        click_at(square_xy(c, r), buttons)

    def park():
        """The pointer off the window: it covers a square's pixels."""
        go((4, scr_h - 8))
        b.frames(4)

    def look(p, what):
        """Every square on the screen against the field: (mismatches,
        squares with a number drawn that should not, or none that should,
        flags not drawn)."""
        from PIL import Image
        px = Image.open(p).convert("RGB").load()
        fx, fy, cw, ch = w("fx"), w("fy"), w("cw"), w("chh")
        fw, fh, cells = field()
        wrong, nums, flags = [], [], []

        def pix(x, y):
            return px[x0 + x, y0 + y]

        def dark(x, y):
            return sum(pix(x, y)) < 384

        def inside(c, r):
            sx, sy = fx + c * cw, fy + r * ch
            return [(x, y) for y in range(sy + 2, sy + ch - 2)
                    for x in range(sx + 2, sx + cw - 2)]
        closed_dark = 0
        for i, v in enumerate(cells):
            c, r = i % fw, i // fw
            if not v & MF_OPEN and not v & MF_FLAG:
                closed_dark = max(closed_dark, sum(1 for q in inside(c, r) if dark(*q)))
        for i, v in enumerate(cells):
            c, r = i % fw, i // fw
            edge_dark = dark(fx + c * cw, fy + r * ch + ch // 2)
            if edge_dark != bool(v & MF_OPEN):
                wrong.append((c, r))
            if v & MF_OPEN and not v & MF_MINE:
                drawn = len({pix(*q) for q in inside(c, r)}) > 1
                if drawn != bool(v & MF_COUNT):
                    nums.append((c, r, v & MF_COUNT))
            if not v & MF_OPEN and v & MF_FLAG:
                if sum(1 for q in inside(c, r) if dark(*q)) <= closed_dark:
                    flags.append((c, r))
        check(not wrong, f"{what}: every square drawn open or closed as the field "
                         f"says -- wrong: {wrong[:8]} ({p})")
        check(not nums, f"{what}: a number in every open square that has one, "
                        f"none in the rest -- wrong: {nums[:8]}")
        check(not flags, f"{what}: every flag drawn -- missing: {flags[:8]}")

    try:
        # UP: the program's window, read by symbol once the loader has put
        # it somewhere and main() has opened it
        f = 0
        while f < 40000:
            b.frames(300)
            f += 300
            if b.peek16(syms["app_near"]) and w("wh") > 0 and byte("mf_w") == 9:
                break
        poke16(b, ptr + 6, PTR_NONE)
        settle()
        check(w("wh") > 0 and byte("mf_w") == 9 and byte("mf_h") == 9
              and w("mf_mines") == 10,
              f"its window is up with the 9 x 9 field, 10 mines, after {f} frames")
        check(w("colour") == (1 if vbxe else 0),
              f"colour {w('colour')}: {'sixteen pens' if vbxe else 'two'}")
        park()
        p = shot("up")
        look(p, "up")
        if vbxe:
            check(find_text(p, "Mines") is not None, "the title says Mines")
            check(find_text(p, "Mines left 10") is not None, "the information line: Mines left 10")

        # THE FIRST CLICK: the middle square, safe, the mines laid round it
        click(4, 4)
        fw, fh, cells = field()
        mines = [i for i, v in enumerate(cells) if v & MF_MINE]
        near = {(4 + dx) + (4 + dy) * 9 for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        check(byte("mf_state") == PLAYING and cells[40] & MF_OPEN and len(mines) == 10
              and not near & set(mines),
              f"the first click opened the middle square: state {byte('mf_state')}, "
              f"{len(mines)} mines, none on it or round it")
        park()
        look(shot("first"), "after the first click")

        # A FLAG, put up and taken down, with the right button
        flag = next(i for i, v in enumerate(cells) if not v & MF_OPEN)
        click(flag % 9, flag // 9, buttons=2)
        cells = field()[2]
        check(w("mf_flags") == 1 and cells[flag] & MF_FLAG,
              f"the right button flagged square {flag}: flags {w('mf_flags')}")
        park()
        p = shot("flag")
        look(p, "a flag up")
        if vbxe:
            check(find_text(p, "Mines left 9") is not None, "the information line: Mines left 9")
        click(flag % 9, flag // 9, buttons=2)
        check(w("mf_flags") == 0 and not field()[2][flag] & MF_FLAG,
              "the right button again took it down")

        # THE CLOCK runs while the game does
        s0 = w("secs")
        b.frames(300)
        s1 = w("secs")
        check(5 <= s1 - s0 <= 7, f"the clock kept time: {s0} s, then {s1} s, 300 frames "
                                 f"(6 s of PAL) on; want 5 to 7 more")

        # WON: every safe square that is still closed, clicked
        for _ in range(81):
            cells = field()[2]
            todo = [i for i, v in enumerate(cells) if not v & (MF_OPEN | MF_MINE)]
            if not todo or byte("mf_state") != PLAYING:
                break
            click(todo[0] % 9, todo[0] // 9)
        b.frames(100)
        p = shot("won")
        check(byte("mf_state") == WON and w("mf_flags") == 10,
              f"every safe square open: state {byte('mf_state')} (won is {WON}), "
              f"the mines flagged ({w('mf_flags')})")
        if vbxe:
            check(find_text(p, "The field is clear") is not None, "the alert: The field is clear")
        b.key("RETURN")
        b.frames(60)
        settle()
        check(byte("mf_state") == FRESH and w("mf_opened") == 0,
              f"Return chose New game: state {byte('mf_state')}, {w('mf_opened')} open")
        park()
        look(shot("new"), "a new game")

        # LOST: the first click, then a mine
        click(0, 0)
        cells = field()[2]
        mine = next(i for i, v in enumerate(cells) if v & MF_MINE)
        # held down: MINES draws the move on the press and puts its alert
        # up only once the button is let go, so the field is looked at
        # with the button still down, and the alert after
        go(square_xy(mine % 9, mine // 9))
        b.frames(4)
        poke16(b, ptr + 4, 1)
        b.frames(8)
        settle()
        check(byte("mf_state") == LOST and w("mf_boom") == mine,
              f"a mine clicked: state {byte('mf_state')} (lost is {LOST}), boom {w('mf_boom')}")
        park()
        look(shot("lost-field"), "lost, every mine shown")
        poke16(b, ptr + 4, 0)
        b.frames(60)
        settle()
        p = shot("lost")
        if vbxe:
            check(find_text(p, "That was a mine") is not None, "the alert: That was a mine")
        b.key("RETURN")
        b.frames(60)
        settle()
        check(byte("mf_state") == FRESH, f"Return chose New game: state {byte('mf_state')}")

        # EXPERT, from the Game menu
        tree = b.peek24(syms["gl_mntree"])
        rects = placed(b, tree)
        t = middle(rects[GAMEMENU])
        go(t)
        b.frames(12)
        it = (t[0], middle(rects[EXPITEM])[1])
        for st in path(here(), it, speed=4) + [F(6)] + CLICK():
            apply_step(b, ptr, st)
        settle()
        b.frames(60)
        settle()
        fw, fh = byte("mf_w"), byte("mf_h")
        right = w("fx") + fw * w("cw") + EDGE
        check(w("level") == 2 and fw == 30 and fh == 16 and w("mf_mines") == 99
              and right <= scr_w,
              f"Expert: level {w('level')}, {fw} x {fh}, {w('mf_mines')} mines, "
              f"the field's right edge at {right} of {scr_w}")
        park()
        look(shot("expert"), "Expert, all closed")
        click(15, 8)
        check(byte("mf_state") == PLAYING, "a first click on Expert")
        b.key("N", ctrl=True)
        b.frames(30)
        settle()
        check(byte("mf_state") == FRESH and w("mf_opened") == 0, "^N: a new game")
        park()
        look(shot("ctrl-n"), "^N, all closed")

        # ^Q: the end of it
        b.key("Q", ctrl=True)
        b.frames(300)
        p = shot("quit")
        if vbxe:
            check(find_text(p, "Mines left") is None, "^Q: the window has gone")
    finally:
        emu.stop()
        shutil.rmtree(work, ignore_errors=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for vbxe in (True, False):
        run(vbxe)
    print(f"mines: {'PASS' if not problems else 'FAIL'} ({len(problems)} problem(s))")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
