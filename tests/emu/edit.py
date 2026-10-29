#!/usr/bin/env python3
"""EDIT on the Atari, reached the way a person reaches it: a document
double-clicked on the desktop, Show, then Return in the viewer
(docs/edit.md).  Every file it saves is read back off the disk image and
compared byte for byte with what the keys must have made.

build/edit-test.atr is the product SpartaDOS disk with EDIT.PRG and
EDIT.RSC in \\APPS\\.  The gate adds a DESKTOP.INF that asks nothing and
four documents to its root:

  ATARI.TXT  $9B line ends.  "XY", Return, ^S, Esc: XY on a line of its
             own, ended by $9B.
  CRLF.TXT   an ST file.  Down, "Z", ^S, Esc: Z at the start of the
             second line, and CR LF kept.
  GFX.TXT    ATASCII graphics and inverse video.  The window must show
             the Atari's own glyphs, read off the screen against the
             machine's character set, and inverse letters white on
             black; ^S, Esc writes it back unchanged.
  BIG.TXT    40,000 bytes, over EDIT's 32 KB.  Refused with an alert,
             and left as it was.

    python3 tests/emu/edit.py
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, config_dir_for   # noqa: E402
import atr                                    # noqa: E402
import deskref                                # noqa: E402
import symfile                                # noqa: E402
from sdx816 import find_text, glyph_rows      # noqa: E402
from shots import Tour, boot, poke16, PTR_NONE, SYMS  # noqa: E402
from aesref import W_FULLER                   # noqa: E402
from m41_items import set_mask, find_below    # noqa: E402
from vbxeref import SHOT_X0, SHOT_Y0, SCR_W, SCR_H   # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "edit-test.atr")
OUT = os.path.join(BUILD, "shots", "edit")

ATARI = b"ONE\x9bTWO\x9b"
CRLF = b"FIRST\r\nSECOND\r\n"
GFX = bytes([0x11, 0x12, 0x12, 0x05, 0x9B, 0x41, 0xC1, 0xC2, 0x9B])
BIG = (b"A" * 39 + b"\x9b") * 1000

WANT = {
    "ATARI.TXT": b"XY\x9b" + ATARI,
    "CRLF.TXT": b"FIRST\r\nZSECOND\r\n",
    "GFX.TXT": GFX,
    "BIG.TXT": BIG,
}

problems = []


def check(ok, what):
    print(f"  {'ok' if ok else 'FAIL'}: {what}")
    if not ok:
        problems.append(what)
    return ok


def make_disk(work):
    """The gate's copy: a DESKTOP.INF that confirms nothing (as
    tests/emu/m41_items.py quiet_disk) and the four documents."""
    disk = os.path.join(work, "edit.atr")
    shutil.copy(DISK, disk)
    img = atr.ATRImage.load(disk)
    fs = atr.open_fs(img)
    text = "#R 02\r\n#E 00 07 00 00 00\r\n"
    for y in deskref.WIN_YCELL:
        text += (f"#W 00 00 {deskref.WIN_XCELL:02X} {y:02X} "
                 f"{deskref.WIN_WCELL:02X} {deskref.WIN_HCELL:02X} 00 @\r\n")
    fs.add_file("DESKTOP.INF", text.encode("latin-1"))
    fs.add_file("ATARI.TXT", ATARI)
    fs.add_file("CRLF.TXT", CRLF)
    fs.add_file("GFX.TXT", GFX)
    fs.add_file("BIG.TXT", BIG)
    img.save(disk)
    return disk


def packed_screen(path):
    """The screenshot as one int per row, a bit per pixel, 1 = dark."""
    from PIL import Image
    px = Image.open(path).convert("RGB").load()
    rows = []
    for y in range(SCR_H):
        v = 0
        for x in range(SCR_W):
            v = (v << 1) | (1 if sum(px[SHOT_X0 + x, SHOT_Y0 + y]) < 192 else 0)
        rows.append(v)
    return rows


def find_rows(path, want, width):
    """Where eight rows of pixels `width` wide, `want`, stand on the
    screen."""
    packed = packed_screen(path)
    mask = (1 << width) - 1
    for y in range(SCR_H - 7):
        for x in range(SCR_W - width + 1):
            shift = SCR_W - width - x
            if all(((packed[y + r] >> shift) & mask) == want[r] for r in range(8)):
                return x, y
    return None


def atari_glyphs(b, codes):
    """The machine's own glyphs for ATASCII `codes`, side by side, eight
    rows: read off its character set at $E000, in the OS's internal
    order ($20-$5F first, then $00-$1F, then $60-$7F)."""
    rom = bytes(b.memdump(0xE000, 1024))
    rows = [0] * 8
    for c in codes:
        i = c + 0x40 if c < 0x20 else c - 0x20 if c < 0x60 else c
        for r in range(8):
            rows[r] = (rows[r] << 8) | rom[i * 8 + r]
    return rows, rom


def main():
    print("gem4xe-edit: EDIT, from the desktop's Show")
    os.makedirs(OUT, exist_ok=True)
    syms = symfile.load(SYMS)
    work = tempfile.mkdtemp(prefix="edit-")
    disk = make_disk(work)
    sha = hashlib.sha256(open(disk, "rb").read()).hexdigest()
    state = os.path.join(config_dir_for("edit"), "disk_state", sha)
    shutil.rmtree(state, ignore_errors=True)
    written = os.path.join(state, "disk.atr")
    emu = launch(tag="edit", memsize="1088K", extra_args=["--bootrw", "--disk", disk])
    b = emu.bridge
    n_shot = [0]

    def shot(name):
        n_shot[0] += 1
        p = os.path.join(OUT, f"{n_shot[0]:02d}-{name}.png")
        b.screenshot(p)
        return p

    def wait_for(text, name, most=6000):
        f = 0
        while f < most:
            b.frames(120)
            f += 120
            p = shot(name)
            if find_text(p, text) is not None:
                return p
            if f < most:
                os.remove(p)
                n_shot[0] -= 1
        return None                     # the last picture is kept

    def key(k, shift=False, ctrl=False, wait=20):
        b.key(k, shift=shift, ctrl=ctrl)
        b.frames(wait)

    try:
        boot(b, syms, OUT)
        poke16(b, syms["ptr_state"] + 6, PTR_NONE)
        t = Tour(b, syms, OUT)
        b.frames(10)
        t.dclick(t.desk_icon("DISK D1:"))
        t.click(t.gadget(W_FULLER))
        set_mask(t, ["ASTERISK", "PERIOD", "T", "X", "T"])

        def edit(name):
            """name opened in EDIT: double-click, Show, Return."""
            t.dclick(t.item(name))
            b.frames(40)
            t.settle()
            p = shot(f"{name}-alert")
            at = find_below(p, "Show")
            if not check(at is not None, f"{name}: Show / Print / Cancel"):
                return None
            t.click((at[0] + 16, at[1] + 4))
            b.frames(60)
            t.settle()
            key("RETURN", wait=60)
            return wait_for("Line 1", f"{name}-edit")

        def back():
            """Esc: EDIT ends and the desktop is back."""
            key("ESC", wait=200)
            t.settle(4000)

        # -- an Atari file: typed into, a line made, saved -------------------
        p = edit("ATARI.TXT")
        if check(p is not None, "Return in the viewer runs EDIT on ATARI.TXT"):
            check(find_text(p, "Atari ($9B)") is not None,
                  f"its info line says the line ends are Atari ones ({p})")
            key("X", shift=True)
            key("Y", shift=True)
            key("RETURN")
            key("S", ctrl=True, wait=300)
            p = shot("ATARI.TXT-saved")
            check(find_text(p, "XY") is not None and find_text(p, "Line 2") is not None,
                  f"XY on its own line, the cursor on line 2 ({p})")
            back()

        # -- an ST file -------------------------------------------------------
        p = edit("CRLF.TXT")
        if check(p is not None, "...and on CRLF.TXT"):
            check(find_text(p, "CR LF") is not None,
                  f"its info line says CR LF ({p})")
            key("EQUALS", ctrl=True)
            key("Z", shift=True)
            key("S", ctrl=True, wait=300)
            back()

        # -- ATASCII's own characters -----------------------------------------
        p = edit("GFX.TXT")
        if check(p is not None, "...and on GFX.TXT"):
            rows, _ = atari_glyphs(b, [0x12, 0x12, 0x05])
            at = find_rows(p, rows, 24)
            check(at is not None, "the graphics are drawn in the Atari's own "
                  f"glyphs, read off the machine's character set ({p})")
            inv = [(~r) & 0xFFFF for r in glyph_rows("AB")]
            check(find_rows(p, inv, 16) is not None,
                  f"inverse video is white on black ({p})")
            key("S", ctrl=True, wait=300)
            back()

        # -- too big ------------------------------------------------------------
        t.dclick(t.item("BIG.TXT"))
        b.frames(40)
        t.settle()
        p = shot("BIG.TXT-alert")
        at = find_below(p, "Show")
        if check(at is not None, "BIG.TXT: Show / Print / Cancel"):
            t.click((at[0] + 16, at[1] + 4))
            b.frames(60)
            t.settle()
            key("RETURN", wait=60)
            p = wait_for("too big", "BIG.TXT-refused")
            check(p is not None, "a file over 32 KB is refused with an alert")
            key("RETURN", wait=300)             # OK: EDIT ends
            t.settle(4000)
    finally:
        emu.stop()

    if not os.path.exists(written):
        check(False, f"the emulator wrote no working copy at {written}")
        return 1
    fs = atr.open_fs(atr.ATRImage.load(written))
    names = {e.filename.upper() for e in fs.entries("")}
    for name, want in WANT.items():
        got = fs.read(name) if name in names else None
        check(got == want, f"{name} on the disk: " + (
            "byte for byte as the keys made it" if got == want else
            "missing" if got is None else f"{got[:40]!r}..., wanted {want[:40]!r}"))
    check("EDIT.TMP" not in names, "no EDIT.TMP is left behind")
    shutil.rmtree(work)
    print(f"gem4xe-edit: {'FAIL' if problems else 'PASS'} -- EDIT from the "
          f"desktop, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
