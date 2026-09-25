#!/usr/bin/env python3
"""The desktop, timed, on either screen: what a person waits for.

    python3 tests/emu/bench_desk.py vbxe|antic [--profile]

The product -- GEM.COM and the desktop off build/gem-shots.atr, the disk
`make shots` photographs -- booted on a machine with a VBXE or without
one, and driven through the things people do: open a drive's window, drag
it somewhere that is not a whole number of bytes across on a 1-bit screen,
full it, put it back.  Each is timed from the end of its input to the
desktop's last call, in frames (20 ms on PAL), which is how long the
machine was busy answering it.

--profile adds where the time went, by function, with the IDLE loop taken
off: the first row times a stretch with nothing to do, and its cycles per
frame, function by function, come off every row after it -- without that,
the idle loop's own divides and multiplies are half of every profile and
say nothing.  The profiler reports addresses without their bank, so each
name is every function that could own one; the ones on the other device
are not running and can be read past.

Written to answer "the ANTIC screen is slow" with numbers (docs/phase52.md)
rather than impressions.  The dismissive reading of a slow screen is the
bus; the measured one was a pixel-at-a-time icon blit, a copy and a cursor
that went pixel by pixel, and a switch per byte.
"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shots
from shots import Tour, boot, poke16, PTR_NONE, SYMS, DISK
from a8test.launcher import launch
import symfile, bench_vdi
from deskrsc import DESKMENU, FILEMENU
from aesref import W_FULLER, W_NAME

vbxe = sys.argv[1] == "vbxe"
prof = "--profile" in sys.argv
syms = symfile.load(SYMS)
mapfile = os.path.splitext(SYMS)[0] + ".map"
ranges = bench_vdi.far_ranges(mapfile)
place = bench_vdi.placements(mapfile)
emu = launch(tag="benchdesk", memsize="1088K", vbxe=vbxe,
             extra_args=["--disk", os.path.abspath(DISK)])
b = emu.bridge
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "build", "shots", "bench")
os.makedirs(out, exist_ok=True)
calls = syms["app_calls"]
FR = [0]
_frames = b.frames
def counting(n):
    FR[0] += n
    return _frames(n)
b.frames = counting
IDLE = {}

def timed(label, act):
    if prof:
        b.ok("PROFILE_START mode=insns")
    f0 = FR[0]
    n0 = b.peek16(calls)
    act()
    n, last, f = b.peek16(calls), 0, 0
    while f - last < 20 and f < 6000:
        b.frames(2); f += 2
        now = b.peek16(calls)
        if now != n:
            n, last = now, f
    frames = FR[0] - f0
    print(f"{label:22s} busy {last:4d} frames after the input ({last * 20} ms), {n - n0} calls, profile over {frames} frames")
    if not prof:
        return
    b.ok("PROFILE_STOP")
    r = b.ok("PROFILE_DUMP top=4096")
    cyc = collections.Counter()
    for h in r["hot"]:
        a = int(str(h["addr"]).lstrip("$"), 16)
        cyc[bench_vdi.where(place, syms, ranges, a)] += h["cycles"]
    if not IDLE:
        for fn, c in cyc.items():
            IDLE[fn] = c / frames
        print(f"      idle: {sum(cyc.values()) / frames:.0f} cycles a frame")
        return
    excess = {fn: c - IDLE.get(fn, 0) * frames for fn, c in cyc.items()}
    work = sum(v for v in excess.values() if v > 0)
    print(f"      work above idle: {work:.0f} cycles")
    for fn, c in sorted(excess.items(), key=lambda kv: -kv[1])[:16]:
        print(f"      {fn:40s} {100 * c / work:5.1f}%  {c:9.0f}")

try:
    boot(b, syms, out)
    poke16(b, syms["ptr_state"] + 6, PTR_NONE)
    t = Tour(b, syms, out)
    b.frames(10)
    timed("idle, nothing to do", lambda: b.frames(30))
    t.go(t.desk_icon("DISK A"))
    timed("open DISK A", lambda: t.run(shots.DCLICK(t.desk_icon("DISK A"))))
    nm = t.gadget(W_NAME); t.go(nm)
    def drag():
        t.run([shots.B(1), shots.F(4)] + shots.path(nm, (nm[0] + 36, nm[1] + 24))
              + [shots.F(4), shots.B(0), shots.F(2)])
    timed("move the window", drag)
    g = t.gadget(W_FULLER); t.go(g)
    timed("full the window", lambda: t.run(shots.CLICK()))
    m = t.menu(DESKMENU); t.go(m)
    timed("drop the Desk menu", lambda: t.run([shots.F(2)]))
    t.cancel_menu(); t.settle()
    g = t.gadget(W_FULLER); t.go(g)
    timed("unfull (desk redraw)", lambda: t.run(shots.CLICK()))
    b.screenshot(os.path.join(out, f"end-{sys.argv[1]}.png"))
finally:
    emu.stop()
