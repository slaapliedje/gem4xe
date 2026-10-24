#!/usr/bin/env python3
"""Phase 1 gate: the VBXE surface, verified pixel for pixel.

Boots the m2 program on the 65C816, lets it bring up a 640x240 4bpp HR overlay
and draw a pattern entirely with the BLITTER, then compares every one of the
153,600 pixels against a host reference model of the same blits.

This is the pattern the VDI conformance suite in Phase 2 will use: the host
model in tools/vbxeref.py is the specification, and the Atari must match it
exactly -- not "look right".
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch, VBXE_VERSION  # noqa: E402
import vbxeref                          # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m2-boot.atr"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "m2.png"))
STATUS = 0x0600

# Must match pal16[] in src/m2_vbxe.c
PAL = bytes((
    0x00, 0x00, 0x00,  0xFF, 0xFF, 0xFF,  0xC0, 0x00, 0x00,  0x00, 0xC0, 0x00,
    0x00, 0x00, 0xC0,  0xC0, 0xC0, 0x00,  0xC0, 0x00, 0xC0,  0x00, 0xC0, 0xC0,
    0x60, 0x60, 0x60,  0x96, 0x96, 0x96,  0xFF, 0x80, 0x00,  0x80, 0x00, 0xFF,
    0x00, 0xFF, 0x80,  0x40, 0x20, 0x10,  0x10, 0x20, 0x40,  0x7F, 0x01, 0x7F))


def reference():
    """Reproduce, on the host, exactly what src/m2_vbxe.c asks the blitter to do."""
    s = vbxeref.Surface()
    S, H = vbxeref.STRIDE, vbxeref.SCR_H
    s.fill(0, S, S, H, 0x00)                                  # 1. clear
    for i in range(16):                                       # 2. colour bars
        s.fill(i * 20, S, 20, 120, (i << 4) | i)
    s.copy(0, S, S * 180, S, 80, 60)                          # 3. copy block
    s.fill(S * 150, S, S, 20, 0x99)                           # 4. full-stride band
    return s.to_rgb(0, PAL)


def main():
    emu = launch(tag="m2", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    fails = []
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)                    # -> 65C816 (resets; DOS reboots)
        b.frames(500)
        for k in ("M", "2", "RETURN"):
            b.key(k)
            b.frames(6)
        b.frames(250)

        st = b.cmd("HWSTATE")["cpu"]
        s = bytes(b.memdump(STATUS, 12))
        print(f"cpu={st['mode']}  status={s[:2]!r} stage=${s[2]:02X} "
              f"FX {s[3]}.{s[4]:02d} @ ${s[5]:02X}00")
        if s[:2] != b"VB":
            fails.append("program did not run (no 'VB' tag)")
        elif s[2] != 0xA5:
            fails.append(f"program stopped at stage ${s[2]:02X}, expected $A5")
        want = (1, int(VBXE_VERSION) % 100)     # the core the launcher asked for
        if (s[3], s[4]) != want:
            fails.append(f"on-target detection saw FX {s[3]}.{s[4]:02d}, "
                         f"expected {want[0]}.{want[1]:02d}")
        if st["mode"] != "65C816":
            fails.append(f"CPU is {st['mode']}")

        # Blitter throughput, measured on target.  1 VCOUNT tick = 2 scanlines;
        # a PAL frame is 156 ticks.
        fill_t = s[8] | (s[9] << 8)
        copy_t = s[10] | (s[11] << 8)
        nbytes = vbxeref.STRIDE * vbxeref.SCR_H
        print(f"blitter: full-screen FILL ({nbytes:,} B) = {fill_t:4d} ticks "
              f"= {fill_t / 156.0:.2f} frame")
        print(f"         full-screen COPY ({nbytes:,} B) = {copy_t:4d} ticks "
              f"= {copy_t / 156.0:.2f} frame")
        if fill_t == 0 or copy_t == 0:
            fails.append("blitter timing measured 0 ticks -- measurement is broken")

        b.screenshot(SHOT)
    finally:
        emu.stop()

    if not fails:
        bad, shown = vbxeref.compare_to_shot(reference(), SHOT)
        total = vbxeref.SCR_W * vbxeref.SCR_H
        print(f"pixels: {total - bad}/{total} match")
        if bad:
            fails.append(f"{bad} of {total} pixels differ from the reference")
            for x, y, want, got in shown:
                print(f"   ({x:3d},{y:3d}) want {want} got {got}")

    print()
    if fails:
        print(f"gem4xe-m2: FAILED")
        for f in fails:
            print("   FAIL:", f)
        return 1
    print("gem4xe-m2: PASSED -- 640x240x4bpp HR overlay, blitter-drawn, pixel exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
