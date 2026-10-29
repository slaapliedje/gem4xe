#!/usr/bin/env python3
"""EDIT's text engine on the host: src/apps/edbuf.c, the code the Atari
runs, through tests/host/ed_host.c.

Three kinds of check, none of which asks edbuf.c to judge itself:

  BY HAND: short files and keys, with the bytes that must come out
  written down here from the rules in edbuf.h -- each kind of line end,
  a CR LF stepped over whole, a lone CR in a CR LF file, a $9B in an ST
  file, ATASCII graphics and inverse video kept.

  UNTOUCHED: every kind of file, loaded and written with no key pressed,
  comes back byte for byte.

  AT RANDOM: thousands of keys on awkward files, against a model in
  Python written from the same rules; the text, the cursor and the line
  count must agree after every run.

    python3 tests/host/test_edit.py
"""
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST = os.path.join(ROOT, "build", "ed_host")
CAP = 4096

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def run(data, keys, cap=CAP):
    with tempfile.TemporaryDirectory(prefix="edit-") as d:
        src, out = os.path.join(d, "in"), os.path.join(d, "out")
        open(src, "wb").write(data)
        # bytes, not str: a str argument goes out as UTF-8, and $9B
        # would arrive as two bytes
        r = subprocess.run([HOST, src, out, str(cap)]
                           + [k.encode("latin-1") for k in keys],
                           capture_output=True)
        if r.returncode:
            return None, r.stdout.decode("latin-1").strip()
        st = r.stdout.decode().split()
        info = {st[i]: int(st[i + 1]) for i in range(0, len(st), 2)}
        return open(out, "rb").read(), info


def t(text):
    """A typing key: the bytes as one argument (no NUL in an argv)."""
    return "t:" + text.decode("latin-1")


ATARI, CRLF, LF, CR = 0, 1, 2, 3
EOLS = {ATARI: b"\x9b", CRLF: b"\r\n", LF: b"\n", CR: b"\r"}


# -- the model ----------------------------------------------------------------
def kind_of(data):
    """The first $9B, CR or LF decides; none at all is an Atari file."""
    for i, c in enumerate(data):
        if c == 0x9B:
            return ATARI
        if c == 0x0A:
            return LF
        if c == 0x0D:
            return CRLF if data[i + 1:i + 2] == b"\n" else CR
    return ATARI


class Model:
    """A list of bytes and a cursor, written from edbuf.h's rules."""

    def __init__(self, data):
        self.t = bytearray(data)
        self.kind = kind_of(data)
        self.eol = EOLS[self.kind]
        self.cur = 0
        self.goal = 0

    def eol_at(self, p):
        e = self.eol
        return len(e) if self.t[p:p + len(e)] == e else 0

    def eol_before(self, p):
        e = self.eol
        return len(e) if p >= len(e) and self.t[p - len(e):p] == e else 0

    def lines(self):
        n, p = 0, 0
        while p < len(self.t):
            k = self.eol_at(p)
            n += 1 if k else 0
            p += k or 1
        return n + 1

    def bol(self, p):
        while p > 0 and not self.eol_before(p):
            p -= 1
        return p

    def eolpos(self, p):
        while p < len(self.t) and not self.eol_at(p):
            p += 1
        return p

    def width(self, c, col):
        if c == 9 and self.kind != ATARI:
            return 8 - col % 8
        return 1

    def col(self, bol, p):
        c = 0
        for q in range(bol, p):
            c += self.width(self.t[q], c)
        return c

    def atcol(self, bol, goal):
        c, q = 0, bol
        while q < len(self.t) and not self.eol_at(q):
            w = self.width(self.t[q], c)
            if c + w > goal:
                break
            c += w
            q += 1
        return q

    def key(self, k):
        keep = False
        p = self.cur
        if k.startswith("t:"):
            for ch in k[2:].encode("latin-1"):
                self.t[p:p] = bytes([ch])
                p += 1
        elif k == "n":
            self.t[p:p] = self.eol
            p += len(self.eol)
        elif k == "b":
            if p:
                n = self.eol_before(p) or 1
                del self.t[p - n:p]
                p -= n
        elif k == "x":
            if p < len(self.t):
                n = self.eol_at(p) or 1
                del self.t[p:p + n]
        elif k == "l":
            if p:
                p -= self.eol_before(p) or 1
        elif k == "r":
            if p < len(self.t):
                p += self.eol_at(p) or 1
        elif k == "u":
            keep = True
            b = self.bol(p)
            if b:
                p = self.atcol(self.bol(b - len(self.eol)), self.goal)
        elif k == "d":
            keep = True
            q = self.eolpos(p)
            if self.eol_at(q):
                p = self.atcol(q + len(self.eol), self.goal)
        elif k == "h":
            p = self.bol(p)
        elif k == "e":
            p = self.eolpos(p)
        self.cur = p
        if not keep:
            self.goal = self.col(self.bol(p), p)


# -- by hand ------------------------------------------------------------------
HAND = [
    # (what, file, keys, the bytes that must come out, lines)
    ("type at the start of an Atari file",
     b"ONE\x9bTWO\x9b", [t(b"XY")], b"XYONE\x9bTWO\x9b", 3),
    ("Return in an Atari file puts in $9B",
     b"ONE\x9bTWO\x9b", ["r", "n"], b"O\x9bNE\x9bTWO\x9b", 4),
    ("Return in a CR LF file puts in CR LF",
     b"ONE\r\nTWO\r\n", ["d", "r", "n"], b"ONE\r\nT\r\nWO\r\n", 4),
    ("Return in an LF file puts in LF",
     b"ONE\nTWO\n", ["e", "n"], b"ONE\n\nTWO\n", 4),
    ("Return in a CR file puts in CR",
     b"ONE\rTWO\r", ["e", "n"], b"ONE\r\rTWO\r", 4),
    ("a new, empty file is an Atari one",
     b"", [t(b"HI"), "n", t(b"THERE")], b"HI\x9bTHERE", 2),
    ("right steps over CR LF whole, and Backspace takes both",
     b"AB\r\nCD", ["e", "r", "b"], b"ABCD", 1),
    ("Delete at a line's end joins the lines",
     b"AB\x9bCD\x9b", ["e", "x"], b"ABCD\x9b", 2),
    ("a lone CR in a CR LF file is a character",
     b"X\r\nA\rB\r\nC", ["d", "r", "r", "x"], b"X\r\nA\r\r\nC", 3),
    ("...and deleting what parts it from an LF makes a line end",
     b"X\r\nA\rB\nC\r\n", ["d", "r", "r", "x"], b"X\r\nA\r\nC\r\n", 4),
    ("typing between a lone CR and an LF keeps the count",
     b"X\r\n", ["r", t(b"Q")], b"XQ\r\n", 2),
    ("$9B in an ST file is a character, not a line end",
     b"FIRST\r\nPRICE 5\x9b\r\nNEXT\r\n", ["d", "e", "b"],
     b"FIRST\r\nPRICE 5\r\nNEXT\r\n", 4),
    ("a CR in an Atari file is a character",
     b"ONE\x9bA\rB\x9bC", ["d", "d", t(b"Z")], b"ONE\x9bA\rB\x9bZC", 3),
    ("...the first $9B, CR or LF decides, so a $9B first is Atari",
     b"A\x9bB\r\nC", ["e", "x"], b"AB\r\nC", 1),
    ("ATASCII graphics and inverse video stay as they were",
     bytes([0x11, 0x12, 0x05, 0x9b, 0xC1, 0xE2, 0x7F, 0x60, 0x9b]),
     ["d", "r", "x", t(b"z")],
     bytes([0x11, 0x12, 0x05, 0x9b, 0xC1, 0x7A, 0x7F, 0x60, 0x9b]), 3),
    ("up and down keep the column through a short line",
     b"ABCDEF\x9bX\x9bABCDEF\x9b", ["e", "d", "d", t(b"!")],
     b"ABCDEF\x9bX\x9bABCDEF!\x9b", 4),
    ("a tab is eight columns in an ST file, so down lands under it",
     b"\tA\r\n12345678B\r\n", ["r", "d", t(b"!")],
     b"\tA\r\n12345678!B\r\n", 3),
    ("...and one column in an Atari file, where $7F is the tab",
     b"\tA\x9b12345678B\x9b", ["r", "d", t(b"!")],
     b"\tA\x9b1!2345678B\x9b", 3),
    ("Backspace at the very start and Delete at the end do nothing",
     b"AB", ["b", "e", "x"], b"AB", 1),
]


def by_hand():
    for what, data, keys, want, lines in HAND:
        got, info = run(data, keys)
        if not check(got is not None, f"{what}: ed_host failed ({info})"):
            continue
        check(got == want, f"{what}: {got!r}, wanted {want!r}")
        check(info["lines"] == lines,
              f"{what}: {info['lines']} lines, wanted {lines}")


# -- untouched ----------------------------------------------------------------
def untouched():
    rnd = random.Random(14)
    files = [b"", b"\x9b", b"\r\n", b"\r", b"\n", b"\r\r\n\n\r",
             bytes(range(256)), bytes(range(256)) * 15,
             bytes(rnd.randrange(256) for _ in range(4000)),
             b"no line end at all"]
    for i, data in enumerate(files):
        got, info = run(data, ["d", "d", "e", "l", "u", "h", "r"])
        check(got == data, f"untouched file {i} ({len(data)} bytes) came back "
              f"{'as it was' if got == data else 'changed'}")
        if got is not None:
            check(info["lines"] == Model(data).lines(),
                  f"untouched file {i}: {info['lines']} lines, the model "
                  f"counts {Model(data).lines()}")
    got, info = run(b"x" * 100, [], cap=99)
    check(got is None and info == "too big",
          f"a file bigger than the buffer is refused: {info!r}")
    got, info = run(b"x" * 98, [t(b"ab"), t(b"c")], cap=99)
    check(got == b"a" + b"x" * 98, f"a full buffer takes no more: {len(got or b'')} bytes")


# -- at random ----------------------------------------------------------------
KEYS = ["l", "r", "u", "d", "h", "e", "b", "x", "n"]
ALPHABET = [b"a", b"\r", b"\n", b"\x9b", b"\t", b"\xc1", b"\x7f"]


def at_random():
    rnd = random.Random(1987)
    runs = 0
    for kind in (ATARI, CRLF, LF, CR):
        for _ in range(60):
            e = EOLS[kind]
            lines = []
            for _ in range(rnd.randrange(1, 8)):
                lines.append(b"".join(rnd.choice(ALPHABET[:1] * 6 + ALPHABET)
                                      for _ in range(rnd.randrange(0, 12))))
            data = e + e.join(lines)        # starts with the end: kind is known
            if kind_of(data) != kind:
                continue
            keys = []
            for _ in range(rnd.randrange(1, 60)):
                if rnd.random() < 0.3:
                    keys.append("t:" + rnd.choice(ALPHABET).decode("latin-1"))
                else:
                    keys.append(rnd.choice(KEYS))
            m = Model(data)
            for k in keys:
                m.key(k)
            got, info = run(data, keys)
            runs += 1
            if not check(got == bytes(m.t), f"random run {runs} ({kind}): "
                         f"{got!r} vs the model's {bytes(m.t)!r}, keys {keys}"):
                continue
            check(info["cur"] == m.cur, f"random run {runs}: cursor "
                  f"{info['cur']}, the model's {m.cur}, keys {keys}")
            check(info["lines"] == m.lines(), f"random run {runs}: "
                  f"{info['lines']} lines, the model counts {m.lines()}")
    return runs


def main():
    print("edit-host: EDIT's text engine")
    by_hand()
    untouched()
    n = at_random()
    print(f"edit-host: {'FAIL' if problems else 'PASS'} -- {len(HAND)} cases by "
          f"hand, untouched files, {n} random runs; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
