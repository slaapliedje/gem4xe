#!/usr/bin/env python3
"""MINES' field on the host: src/apps/minefld.c, the code the Atari runs,
through tests/host/mines_host.c.

The C is never asked to judge itself.  After the first open lays the
mines, a model written here from the rules in minefld.h replays every
move on that layout, and the two must agree after each one: the state,
the flags, the squares open, the square that went off, and the redraw
list -- every square whose look changed, each exactly once, nothing else.
The layout itself is checked against the rules too: the number of
mines, the first square and its neighbours clear where there is room,
and every count.

    python3 tests/host/test_mines.py
"""
import os
import random
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST = os.path.join(ROOT, "build", "mines_host")
FRESH, PLAYING, WON, LOST = 0, 1, 2, 3
LEVELS = [(9, 9, 10), (16, 16, 40), (30, 16, 99)]

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def host(seed, w, h, m, moves):
    args = [HOST, str(seed), str(w), str(h), str(m)] + moves
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    lines = out.splitlines()
    steps = []
    for ln in lines[:len(moves)]:
        f = ln.split()
        dirty = [] if f[11] == "-" else [int(v) for v in f[11].split(",")]
        steps.append(dict(state=int(f[3]), flags=int(f[5]), opened=int(f[7]),
                          boom=int(f[9]), dirty=dirty))
    rest = lines[len(moves):]
    hw = rest[0].split()
    W, H = int(hw[1]), int(hw[2])
    seen = rest[1:1 + H]
    truth = rest[1 + H:1 + 2 * H]
    return steps, W, H, seen, truth


def around(i, w, h):
    x, y = i % w, i // w
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            if (dx or dy) and 0 <= nx < w and 0 <= ny < h:
                yield ny * w + nx


class Model:
    """The field as minefld.h describes it, on a layout already laid."""

    def __init__(self, w, h, mines):
        self.w, self.h, self.mines = w, h, set(mines)
        self.count = [sum(1 for j in around(i, w, h) if j in self.mines)
                      for i in range(w * h)]
        self.open, self.flag = set(), set()
        self.state, self.boom = PLAYING, 0xFFFF

    def _open_one(self, i, dirty):
        if i in self.open or i in self.flag:
            return
        if i in self.mines:
            self.boom, self.state = i, LOST
            for k in range(self.w * self.h):
                if k in self.mines and k not in self.flag:
                    self.open.add(k)
                    dirty.append(k)
                elif k not in self.mines and k in self.flag:
                    dirty.append(k)
            return
        todo = [i]
        self.open.add(i)
        dirty.append(i)
        while todo:
            j = todo.pop()
            if self.count[j]:
                continue
            for k in around(j, self.w, self.h):
                if k in self.open or k in self.flag or k in self.mines:
                    continue
                self.open.add(k)
                dirty.append(k)
                todo.append(k)

    def _won(self, dirty):
        if self.state != PLAYING:
            return
        if len(self.open) != self.w * self.h - len(self.mines):
            return
        self.state = WON
        for k in sorted(self.mines):
            if k not in self.flag:
                self.flag.add(k)
                dirty.append(k)

    def move(self, op, x, y):
        dirty = []
        if not (0 <= x < self.w and 0 <= y < self.h):
            return dirty
        i = y * self.w + x
        if op == "o":
            if self.state in (WON, LOST) or i in self.flag:
                return dirty
            self._open_one(i, dirty)
            self._won(dirty)
        elif op == "f":
            if self.state in (WON, LOST) or i in self.open:
                return dirty
            self.flag ^= {i}
            dirty.append(i)
        elif op == "c":
            if self.state != PLAYING or i not in self.open or not self.count[i]:
                return dirty
            nb = list(around(i, self.w, self.h))
            if sum(1 for j in nb if j in self.flag) != self.count[i]:
                return dirty
            for j in nb:
                if self.state != PLAYING:
                    break
                self._open_one(j, dirty)
            self._won(dirty)
        return dirty

    def seen(self):
        rows = []
        for y in range(self.h):
            r = ""
            for x in range(self.w):
                i = y * self.w + x
                if i in self.open:
                    r += "*" if i in self.mines else str(self.count[i])
                else:
                    r += "F" if i in self.flag else "."
            rows.append(r)
        return rows


def layout(seed, w, h, m, first):
    steps, W, H, seen, truth = host(seed, w, h, m, [f"o:{first[0]},{first[1]}"])
    mines = [y * W + x for y in range(H) for x in range(W) if truth[y][x] == "M"]
    return mines, truth


def check_layout(seed, w, h, m, first, what):
    mines, truth = layout(seed, w, h, m, first)
    ok = check(len(mines) == m, f"{what}: {len(mines)} mines laid, want {m}")
    fi = first[1] * w + first[0]
    clear = {fi} | (set(around(fi, w, h)) if w * h - m >= 9 else set())
    ok &= check(not (clear & set(mines)),
                f"{what}: a mine on the first square or round it")
    model = Model(w, h, mines)
    want = ["".join("M" if y * w + x in model.mines else str(model.count[y * w + x])
                    for x in range(w)) for y in range(h)]
    ok &= check(truth == want, f"{what}: the counts are not the mines' neighbours")
    return mines


def replay(seed, w, h, m, moves, what):
    """The host and the model, move by move; the mines from the first."""
    steps, W, H, seen, truth = host(seed, w, h, m, moves)
    mines = [y * W + x for y in range(H) for x in range(W) if truth[y][x] == "M"]
    model = None
    for n, (mv, st) in enumerate(zip(moves, steps)):
        op, xy = mv.split(":")
        x, y = (int(v) for v in xy.split(","))
        if model is None:
            if op != "o":
                continue                # before the mines: nothing to model
            model = Model(w, h, mines)
            model.open, model.flag = set(), set()
            # the flags put up before the first open stand
            for pm in moves[:n]:
                pop, pxy = pm.split(":")
                px, py = (int(v) for v in pxy.split(","))
                if pop == "f":
                    model.flag ^= {py * w + px}
            if y * w + x in model.flag:
                model = None            # a flagged first square opens nothing
                continue
        dirty = model.move(op, x, y)
        got = (st["state"], st["flags"], st["opened"], st["boom"])
        want = (model.state, len(model.flag), len(model.open - model.mines),
                model.boom)
        if not check(got == want, f"{what}: move {n} {mv}: state/flags/opened/boom "
                                  f"{got}, the model says {want}"):
            return None
        if not check(len(st["dirty"]) == len(set(st["dirty"])),
                     f"{what}: move {n} {mv}: a square twice in the redraw list"):
            return None
        if not check(set(st["dirty"]) == set(dirty),
                     f"{what}: move {n} {mv}: redraw list {sorted(st['dirty'])}, "
                     f"the model's {sorted(dirty)}"):
            return None
    if model is not None:
        check(seen == model.seen(), f"{what}: the field as seen differs at the end")
    return model


def main():
    if not os.path.exists(HOST):
        print(f"no {HOST}: make build/mines_host")
        return 2
    print("MINES' field on the host (src/apps/minefld.c)")

    # THE LAYOUT, on every level and in every corner
    for w, h, m in LEVELS:
        for first in [(0, 0), (w - 1, h - 1), (w // 2, h // 2), (0, h - 1)]:
            for seed in (1, 77, 0xDEADBEEF):
                check_layout(seed, w, h, m, first, f"{w}x{h}/{m} seed {seed} first {first}")
    # ...a field too full for the first square's neighbours to be kept clear
    check_layout(5, 4, 4, 10, (1, 1), "4x4/10 (no room round the first)")
    # the same seed and square give the same field; another seed another
    a = layout(42, 16, 16, 40, (3, 3))[0]
    check(a == layout(42, 16, 16, 40, (3, 3))[0], "the same seed laid a different field")
    check(a != layout(43, 16, 16, 40, (3, 3))[0], "two seeds laid the same field")
    print("  layouts checked")

    # WON: every safe square opened, the mines flagged by the game
    for w, h, m in LEVELS:
        mines = set(layout(9, w, h, m, (0, 0))[0])
        moves = ["o:0,0"] + [f"o:{i % w},{i // w}" for i in range(w * h) if i not in mines]
        model = replay(9, w, h, m, moves, f"win {w}x{h}")
        if model:
            check(model.state == WON and model.flag == mines,
                  f"win {w}x{h}: state {model.state}, flags on the mines "
                  f"{model.flag == mines}")
    # LOST: a mine opened shows every mine, and the wrong flags
    mines = sorted(layout(3, 16, 16, 40, (8, 8))[0])
    safe = [i for i in range(256) if i not in mines]
    moves = ["o:8,8", f"f:{mines[0] % 16},{mines[0] // 16}",
             f"f:{safe[-1] % 16},{safe[-1] // 16}", f"o:{mines[1] % 16},{mines[1] // 16}"]
    model = replay(3, 16, 16, 40, moves, "lose")
    if model:
        check(model.state == LOST and model.boom == mines[1], "lose: not lost on the mine")
    # A FLAG PUT UP BEFORE THE FIRST OPEN, next to it, stands: the mines
    # are laid round it, and laying them must not take it down
    steps = host(21, 9, 9, 10, ["f:1,1", "o:0,0"])[0]
    check(steps[1]["flags"] == 1, f"a flag up before the first open was lost "
                                  f"(flags {steps[1]['flags']}, want 1)")
    seen = host(21, 9, 9, 10, ["f:1,1", "o:0,0"])[3]
    check(seen[1][1] == "F", f"the square under that flag shows {seen[1][1]!r}, want 'F'")
    # CHORD: the right flags open the rest, a wrong one loses
    w, h, m = 9, 9, 10
    seed = 11
    mines = set(layout(seed, w, h, m, (4, 4))[0])
    first = Model(w, h, mines)
    first.move("o", 4, 4)
    done = False
    for i in sorted(first.open):
        nb = list(around(i, w, h))
        bad = [j for j in nb if j in mines]
        shut = [j for j in nb if j not in first.open and j not in mines]
        if first.count[i] and bad and shut:
            right = ["o:4,4"] + [f"f:{j % w},{j // w}" for j in bad] + [f"c:{i % w},{i // w}"]
            model = replay(seed, w, h, m, right, "chord")
            check(model is not None and all(j in model.open for j in shut),
                  "chord: the unflagged squares round the number did not open")
            wrong = ["o:4,4"] + [f"f:{j % w},{j // w}" for j in shut[:len(bad)]] \
                + [f"c:{i % w},{i // w}"]
            if len(shut) >= len(bad):
                model = replay(seed, w, h, m, wrong, "chord, wrong flag")
                check(model is not None and model.state == LOST,
                      "chord with a wrong flag did not lose")
            done = True
            break
    check(done, "chord: no square to chord on (choose another seed)")

    # AT RANDOM: thousands of moves, every level, against the model
    rnd = random.Random(1234)
    games = 0
    for w, h, m in LEVELS:
        for g in range(40):
            seed = rnd.randrange(1, 1 << 32)
            moves = []
            for _ in range(rnd.randrange(1, 80)):
                op = rnd.choice("ooooffc")
                moves.append(f"{op}:{rnd.randrange(w)},{rnd.randrange(h)}")
            if replay(seed, w, h, m, moves, f"random {w}x{h} seed {seed}") is None \
                    and problems:
                break
            games += 1
    print(f"  {games} random games replayed against the model")

    print(f"test_mines: {'PASS' if not problems else 'FAIL'} ({len(problems)} problem(s))")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
