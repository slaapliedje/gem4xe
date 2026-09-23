"""GEMBench, shaped for this machine: what the things GEMBench times cost
on the target, in milliseconds, not in per cent of an ST.

GEMBench times a GEM dialog box, VDI text (plain, with effects, small),
VDI graphics, a GEM window, integer division, float maths, RAM and ROM
access and blitting, and reports each as a percentage of an ST.  Its
source is not public and no ST is measured here, so the numbers are
absolute: milliseconds per unit of work and units per second, on the
emulated machine (Altirra: a Rapidus at 11x with VBXE FX 1.26 -- not
hardware).  Two of its rows do not apply -- vst_effects is a no-op in this
driver and it has one font -- and are reported as such, not dropped.
Rows are grouped under GEMBench's headings, one machine number each.

Timing is exact to a VCOUNT tick (two scanlines, 0.13 ms), not to a
frame: the runner stamps VCOUNT when it sees GO and just before it sets
DONE (STATUS[5..6]); the host reads the emulator's cycle counter at the
frame boundary before GO and at the one where DONE is seen, and the idle
tail between DONE and that boundary comes off.  The runner measures how
many VCOUNT values a frame has (STATUS[7]) and the host how many cycles,
so the video standard is not assumed.  The counter the emulator exposes
leaves out the cycles ANTIC halts the CPU for (32520 a PAL frame, not
35568), so cycles become milliseconds through the frame -- a frame is
`period` VCOUNT ticks of two 114-cycle lines at the machine clock --
rather than through the clock directly.  A watchpoint on DONE would be
exact to the cycle, but a halt inside a FRAME leaves the bridge's gate
closed, so it cannot be used.

The VDI and AES rows are the harness's scripts (tests/emu/m3..m8) run
for time; the CPU and memory rows are the runner's 2000+n ops
(src/m3_vdi.c bench_op).  The memory rows walk 256 bytes through a far
pointer whatever the space, so they differ only in the bus behind them;
the bank-$00 row is the loop's own cost, the rest is the bus.

  python3 tests/emu/bench_gem.py [--profile] [--top N] [--json PATH] [--list] [NAME ...]

--profile runs Altirra's instruction profiler across one script of each
selected row and sums it per function (tests/emu/bench_vdi.py's
attribution).  NAME selects groups by case-insensitive substring.
"""
import collections
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import aesref                                                       # noqa: E402
import bench_vdi                                                    # noqa: E402
import m3_vdi as m                                                  # noqa: E402
import symfile                                                      # noqa: E402
import vdiref as V                                                  # noqa: E402
from a8test.launcher import BASE_ARGS                               # noqa: E402
from aesref import (Layout, FORM_DIAL,                                # noqa: E402
                    FMD_START, FMD_FINISH, WIND_CLOSE, WIND_DELETE, WF_NEWDESK)
from m3_vdi import (STATUS, ST_GO, ST_DONE, launch, DISK, pack_mfdb,  # noqa: E402
                    ICON_W, ICON_H, ICON_WDW)
from m4_aes import dialog, draw, PRELUDE                            # noqa: E402
from m7_form import desk                                            # noqa: E402
from m8_wind import create, wopen, setaddr, ALL, FULL               # noqa: E402

ST_VC_GO, ST_VC_DONE, ST_VC_PERIOD = 5, 6, 7
ST_FAR_FIRST, ST_FAR_LAST, ST_FAR_BLOCK = 17, 18, 23

BENCH = 2000
B_DIV16, B_DIV32, B_FLOAT, B_READ, B_WRITE, B_COPY, B_UPLOAD = range(1, 8)
B_MVN, B_MVNCHK = 8, 9          # src/sys/blkmove.s, and does it copy right
SP_CPU, SP_VRAM, SP_STACK, SP_STACK2 = 0, 1, 2, 3
BENCH_BYTES = 256                 # what the runner's memory ops move per unit

# The machine clock, from the video standard the launcher chose.
MHZ = 1.773447 if "--pal" in BASE_ARGS else 1.789773

# Enough time per row to make the tick resolution irrelevant: a run is
# repeated until its measured total reaches this, or MAX_RUNS.
MIN_MS, MAX_RUNS = 300.0, 40

ONES = bytes([0xFF]) * 96
TEXT = tuple(b"The quick brown fox jumps over the lazy dog.")[:40]
DIALOG_RECT = (160, 60, 320, 110)               # where m4's dialog sits
WINDOW = (100, 40, 400, 160)


def bench(op, *ints):
    return (BENCH + op, (), tuple(ints))


def split(addr):
    return addr & 0xFFFF, (addr >> 16) & 0xFFFF


class Row:
    """One measured line: `script` is run whole and costs `units` units
    of work; `aes` says which encoder the script needs; `bytes_per_unit`
    turns a memory row's rate into KB/s."""

    def __init__(self, label, script, units, aes=False, bytes_per_unit=0):
        self.label, self.script, self.units = label, script, units
        self.aes, self.bytes_per_unit = aes, bytes_per_unit


class NotApplicable:
    def __init__(self, label, why):
        self.label, self.why = label, why


def near2_free(mapfile):
    """The Near2 memory's placement if the linker left it empty: bank-$00
    RAM in the slow $8000-$BFFF block that nothing uses, read off the map
    rather than assumed.  None when it is used or absent."""
    with open(mapfile) as f:
        for line in f:
            mm = re.match(r"\s*Near2\s+00([0-9a-f]{4})-00([0-9a-f]{4})\s+[0-9a-f]+"
                          r"\s+([\d.]+)%", line)
            if mm and float(mm.group(3)) == 0.0:
                return int(mm.group(1), 16)
    return None


def build_rows(st, mapfile, tree_base, desk_base, icon_mfdb):
    """The rows, grouped under GEMBench's headings, for the environment the
    runner reported (st = STATUS[0..31]) and the map it was linked with."""
    far_lo = st[ST_FAR_BLOCK] << 16           # the runner's own 4K far block
    far_hi = st[ST_FAR_LAST] << 16            # the highest bank the probe found
    slow = near2_free(mapfile)
    rom = 0xE000                              # the OS ROM: never on the fast bus
    vram = 0                                  # VR_SCREEN0: harmless to scribble on
    N = 20

    def text(x):
        return [(V.V_GTEXT, (x, 16 + 8 * i), TEXT) for i in range(N)]

    def recfl(x0):
        return [(V.VR_RECFL, (x0 + 8 * (i & 7), 20 + 4 * i,
                              x0 + 8 * (i & 7) + 99, 20 + 4 * i + 49), ())
                for i in range(N)]

    def box(x0):
        return [(V.V_PLINE, (x0 + 8 * (i & 7), 20 + 4 * i, x0 + 8 * (i & 7) + 99, 20 + 4 * i,
                             x0 + 8 * (i & 7) + 99, 20 + 4 * i + 49, x0 + 8 * (i & 7), 20 + 4 * i + 49,
                             x0 + 8 * (i & 7), 20 + 4 * i)) for i in range(N)]

    def diag():
        return [(V.V_PLINE, (300 + 2 * i, 20, 400 + 2 * i, 120)) for i in range(N)]

    def icon(mode):
        return [(V.VRT_CPYFM, (0, 0, 31, 23, 64 * (i & 7), 40 + 24 * (i >> 3)),
                 (mode, 1, 0), "icon") for i in range(N)]

    def mem(op, label, addr, space, n):
        lo, hi = split(addr)
        return Row(label, [bench(op, n, lo, hi, space)], n, bytes_per_unit=BENCH_BYTES)

    def copy(label, src, sspace, dst, dspace, n, op=B_COPY):
        slo, shi = split(src)
        dlo, dhi = split(dst)
        return Row(label, [bench(op, n, slo, shi, sspace, dlo, dhi, dspace)], n,
                   bytes_per_unit=BENCH_BYTES)

    dialog_unit = [(FORM_DIAL, (), (FMD_START, 0, 0, 0, 0) + DIALOG_RECT),
                   draw(),
                   (FORM_DIAL, (), (FMD_FINISH, 0, 0, 0, 0) + DIALOG_RECT)]
    window_unit = [create(ALL, *FULL), wopen(1, *WINDOW),
                   (WIND_CLOSE, (), (1,)), (WIND_DELETE, (), (1,))]

    groups = [
        ("GEM dialog box", [
            Row("form_dial START, objc_draw of 5 objects, form_dial FINISH",
                dialog_unit * 8, 8, aes=True),
            Row("objc_draw of the dialog alone", [draw()] * N, N, aes=True),
        ]),
        ("VDI text", [
            Row("v_gtext, 40 characters, even x", text(16), N),
            Row("v_gtext, 40 characters, odd x", text(17), N),
        ]),
        ("VDI text effects", [
            NotApplicable("vst_effects", "a no-op in this driver, as in DRI's own (opcode 106)")]),
        ("VDI small text", [
            NotApplicable("vst_height / vst_point", "one font, 8x8, in this driver")]),
        ("VDI graphics", [
            Row("vr_recfl 100x50, solid", [(V.VSF_INTERIOR, (), (1,))] + recfl(20), N),
            Row("vr_recfl 100x50, pattern 4", [(V.VSF_INTERIOR, (), (2,)),
                                               (V.VSF_STYLE, (), (4,))] + recfl(120), N),
            Row("box 100x50 as a 5-point v_pline", box(220), N),
            Row("diagonal 100x100 v_pline", diag(), N),
        ]),
        ("GEM window", [
            Row("wind_create, open (400x160, every gadget), close, delete",
                window_unit * 6, 6, aes=True),
        ]),
        ("Integer division", [
            Row("16-bit signed divide (_Div16)", [bench(B_DIV16, 5000)], 5000),
            Row("32-bit signed divide (_Div32)", [bench(B_DIV32, 2000)], 2000),
        ]),
        ("Float math", [
            Row("float32: multiply, add, divide", [bench(B_FLOAT, 1000)], 1000),
        ]),
        ("RAM access", [
            mem(B_READ, "read, bank $00 (the stack, fast SRAM)", 0, SP_STACK, 400),
            mem(B_READ, f"read, far RAM bank ${far_lo >> 16:02X}", far_lo, SP_CPU, 400),
            mem(B_READ, f"read, far RAM bank ${far_hi >> 16:02X}", far_hi, SP_CPU, 400),
        ] + ([mem(B_READ, f"read, bank $00 ${slow:04X} (the slow block)", slow, SP_CPU, 100)]
             if slow is not None else []) + [
            mem(B_READ, "read, VRAM through the MEMAC window", vram, SP_VRAM, 100),
            mem(B_WRITE, "write, bank $00 (the stack)", 0, SP_STACK, 400),
            mem(B_WRITE, f"write, far RAM bank ${far_lo >> 16:02X}", far_lo, SP_CPU, 400),
        ] + ([mem(B_WRITE, f"write, bank $00 ${slow:04X} (the slow block)", slow, SP_CPU, 100)]
             if slow is not None else []) + [
            mem(B_WRITE, "write, VRAM through the MEMAC window", vram, SP_VRAM, 100),
            copy("copy, bank $00 to bank $00", 0, SP_STACK, 0, SP_STACK2, 400),
            copy(f"copy, bank $00 to far bank ${far_lo >> 16:02X}", 0, SP_STACK, far_lo, SP_CPU, 400),
            copy(f"copy, far bank ${far_lo >> 16:02X} to bank $00", far_lo, SP_CPU, 0, SP_STACK, 400),
            copy("copy, bank $00 to VRAM through the window", 0, SP_STACK, vram, SP_VRAM, 100),
            Row("vram_write, the driver's upload, 256 bytes",
                [bench(B_UPLOAD, 100, *split(vram))], 100, bytes_per_unit=BENCH_BYTES),
        ]),
        # THE SAME MOVES, BY MVN.  The rows above are C: a loop through a
        # far pointer, which is what the language offers.  These are the
        # CPU's own block move (src/sys/blkmove.s), and the pair is the
        # point -- what a byte of memory costs is not a property of the
        # machine until you have asked it both ways.  The number decides
        # whether a near region can be parked and fetched back at a timer
        # tick, which is what holding two applications rests on
        # (docs/multitasking.md).
        ("Block move (MVN)", [
            copy("MVN, bank $00 to bank $00", 0, SP_STACK, 0, SP_STACK2, 400,
                 op=B_MVN),
            copy(f"MVN, bank $00 to far bank ${far_lo >> 16:02X}",
                 0, SP_STACK, far_lo, SP_CPU, 400, op=B_MVN),
            copy(f"MVN, far bank ${far_lo >> 16:02X} to bank $00",
                 far_lo, SP_CPU, 0, SP_STACK, 400, op=B_MVN),
            copy(f"MVN, far bank ${far_lo >> 16:02X} to far bank ${far_hi >> 16:02X}",
                 far_lo, SP_CPU, far_hi, SP_CPU, 400, op=B_MVN),
        ]),
        ("ROM access", [
            mem(B_READ, f"read, the OS ROM at ${rom:04X}", rom, SP_CPU, 100),
        ]),
        ("Blitting", [
            Row("vro_cpyfm 320x100 screen to screen, aligned",
                [(V.VRO_CPYFM, (0, 20, 319, 119, 320, 120, 639, 219), (3,))] * 10, 10),
            Row("vro_cpyfm 320x100 screen to screen, odd x (the pixel path)",
                [(V.VRO_CPYFM, (1, 20, 320, 119, 320, 120, 639, 219), (3,))] * 2, 2),
            Row("vrt_cpyfm 32x24 icon, transparent", icon(V.MD_TRANS), N),
            Row("vrt_cpyfm 32x24 icon, replace", icon(V.MD_REPLACE), N),
        ]),
    ]
    return groups


class Clock:
    """Cycles per frame and per VCOUNT tick, measured, and the elapsed
    cycles of one script run with the idle tail taken off."""

    def __init__(self, b):
        c0 = b.ok("REGS")["cycles"]
        b.frames(1)
        c1 = b.ok("REGS")["cycles"]
        self.cpf = (c1 - c0) & 0xFFFFFFFF
        self.period = b.peek(STATUS + ST_VC_PERIOD)
        self.tick = self.cpf / self.period
        # Wall time: VCOUNT steps every two lines, a line is 114 cycles.
        self.frame_ms = self.period * 2 * 114 / (MHZ * 1000)

    def run(self, b, timeout=3000):
        b.poke(STATUS + ST_DONE, 0)
        c0 = b.ok("REGS")["cycles"]
        b.poke(STATUS + ST_GO, 1)
        for f in range(1, timeout + 1):
            b.frames(1)
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
        else:
            raise RuntimeError("script did not finish")
        c1 = b.ok("REGS")["cycles"]
        v_go, v_done = b.peek(STATUS + ST_VC_GO), b.peek(STATUS + ST_VC_DONE)
        tail = ((v_go - v_done) % self.period) * self.tick
        return ((c1 - c0) & 0xFFFFFFFF) - tail, f

    def ms(self, cycles):
        return cycles / self.cpf * self.frame_ms


def encode(row, tree_base, mfdb, screen_mfdb):
    if row.aes:
        return aesref.encode(row.script, tree_base, mfdb)
    return V.encode(row.script, mfdb, screen_mfdb)


def load_script(b, sa, room, words):
    data = b"".join(struct.pack("<h", w if w < 32768 else w - 65536) for w in words)
    assert len(data) <= room, (len(data), room)
    b.memload(sa, data)


def measure(b, clock, row, sa, room, tree_base, mfdb, screen_mfdb):
    load_script(b, sa, room, encode(row, tree_base, mfdb, screen_mfdb))
    total, runs = 0.0, 0
    while runs < MAX_RUNS and (runs < 2 or clock.ms(total) < MIN_MS):
        cycles, _ = clock.run(b)
        total += cycles
        runs += 1
    return total, runs


def profile(b, clock, row, syms, ranges, place, top):
    b.ok("PROFILE_START mode=insns")
    clock.run(b)
    b.ok("PROFILE_STOP")
    r = b.ok("PROFILE_DUMP top=4096")
    tc, ti = r["total_cycles"], r["total_insns"]
    print(f"      {ti} insns in {tc} machine cycles: {tc / max(ti, 1):.2f} cycles/insn, "
          f"{ti / row.units:.0f} insns/unit")
    insns, cycles = collections.Counter(), collections.Counter()
    for h in r["hot"]:
        a = int(str(h["addr"]).lstrip("$"), 16)
        fn = bench_vdi.where(place, syms, ranges, a)
        insns[fn] += h["insns"]
        cycles[fn] += h["cycles"]
    for fn, n in insns.most_common(top):
        print(f"      {fn:30s} insns {n:7d} ({n / row.units:7.0f}/unit)  "
              f"cycles {cycles[fn]:7d} ({cycles[fn] / row.units:7.0f}/unit)")


def main(argv):
    prof = "--profile" in argv
    top = 12
    out_json = None
    names = []
    it = iter(a for a in argv if a != "--profile")
    for a in it:
        if a == "--top":
            top = int(next(it))
        elif a == "--json":
            out_json = next(it)
        elif a == "--list":
            names.append(a)
        else:
            names.append(a.lower())
    syms = symfile.load(m.SYMS)
    mapfile = os.path.splitext(m.SYMS)[0] + ".map"
    ranges = bench_vdi.far_ranges(mapfile)
    place = bench_vdi.placements(mapfile)
    sa, sc = syms["vdi_script"], syms["vdi_scratch"]
    script_room = min(a for a in syms.values() if a > sa) - sa
    scratch_room = min(a for a in syms.values() if a > sc) - sc

    # The dialog and the desk trees, then the icon and the two MFDBs, all
    # in vdi_scratch -- which is in the slow block: the trees are read
    # over the 1.79 MHz bus, as the conformance suites read them.
    L = Layout(sc, max_objs=8)
    dialog_objs = dialog(L)
    L2 = Layout(L.next, max_objs=1)
    desk_objs = desk(L2)
    icon_addr = (L2.next + 1) & ~1
    mfdb, screen_mfdb = icon_addr + len(ONES), icon_addr + len(ONES) + 20
    assert screen_mfdb + 20 - sc <= scratch_room

    if "--list" in names:
        for g, rows in build_rows(bytes(32), mapfile, sc, L2.base, mfdb):
            print(g)
            for r in rows:
                print(f"    {r.label}")
        return 0

    emu = launch(tag="bench", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    results = []
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        # Ready is STATUS[2] == 1, not the signature, as m3_vdi waits for
        # it: the runner raises 'VD' early and finishes starting up some
        # frames later, and how many moves with the size of the image.
        for _ in range(200):
            tag = bytes(b.memdump(STATUS, 3))
            if tag[:2] == b"VD" and tag[2] == 1:
                break
            b.frames(4)
        st = bytes(b.memdump(STATUS, 32))
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1
        print("rapidus: present %d  MCR %02x -> %02x  CMCR %02x  synced %02x" % tuple(st[25:30]))
        clock = Clock(b)
        print(f"clock: {clock.cpf} cycles per frame, {clock.period} VCOUNT values, "
              f"{clock.tick:.0f} cycles per tick ({clock.frame_ms:.2f} ms per frame)")

        b.memload(sc, L.pack(dialog_objs))
        b.memload(L2.base, L2.pack(desk_objs))
        b.memload(icon_addr, ONES)
        b.memload(mfdb, pack_mfdb(icon_addr, ICON_W, ICON_H, ICON_WDW))
        b.memload(screen_mfdb, pack_mfdb(0, 0, 0, 0))

        # Open the workstation, start the AES and hand it the desk tree
        # once; every row's script then runs against that state.
        setup = Row("setup", PRELUDE + [setaddr(0, WF_NEWDESK, L2.base)], 1, aes=True)
        load_script(b, sa, script_room, encode(setup, sc, mfdb, screen_mfdb))
        clock.run(b)

        # What a script costs to run when it does nothing: the runner's
        # own parse and record, taken off every row.
        empty = Row("empty", [bench(B_DIV16, 0)], 1)
        total, runs = measure(b, clock, empty, sa, script_room, sc, mfdb, screen_mfdb)
        overhead = total / runs
        print(f"an empty script: {overhead:.0f} cycles ({clock.ms(overhead) * 1000:.0f} us)")

        # DOES MVN COPY THE RIGHT BYTES, before any of its timings are
        # believed.  `MVN src,dst` assembles to $54, DST, SRC -- backwards
        # from the syntax -- and a swapped pair moves real bytes to a real
        # place with nothing to say so.  A fast wrong copy is worth less
        # than no copy, so the rate is only printed if this is 0.
        chk = Row("mvn-check", [bench(B_MVNCHK, 1, *split(st[ST_FAR_BLOCK] << 16))], 1)
        load_script(b, sa, script_room, encode(chk, sc, mfdb, screen_mfdb))
        clock.run(b)
        nbad = b.peek16(syms["intout"])
        mvn_ok = (nbad == 0)
        print(f"MVN out to far memory and back: "
              f"{'all 256 bytes came back' if mvn_ok else f'{nbad} of 256 bytes wrong'}")

        for group, rows in build_rows(st, mapfile, sc, L2.base, mfdb):
            if names and not any(n in group.lower() for n in names):
                continue
            print(group)
            for row in rows:
                if isinstance(row, NotApplicable):
                    print(f"    {row.label}: n/a -- {row.why}")
                    results.append({"group": group, "label": row.label, "na": row.why})
                    continue
                total, runs = measure(b, clock, row, sa, script_room, sc, mfdb, screen_mfdb)
                per = max(total / runs - overhead, 0.0) / row.units
                ms = clock.ms(per)
                rate = f"{row.bytes_per_unit / (ms / 1000) / 1024:8.0f} KB/s" if row.bytes_per_unit \
                    else f"{1000 / ms:8.1f} /s" if ms else "        -"
                print(f"    {row.label:66s} {ms:9.3f} ms {rate}   "
                      f"({per:.0f} cycles/unit, {runs} runs)")
                results.append({"group": group, "label": row.label, "units": row.units,
                                "runs": runs, "cycles_per_unit": per, "ms_per_unit": ms,
                                "bytes_per_unit": row.bytes_per_unit})
                if prof:
                    profile(b, clock, row, syms, ranges, place, top)
    finally:
        emu.stop()
    if out_json:
        with open(out_json, "w") as f:
            json.dump({"cycles_per_frame": clock.cpf, "vcount_period": clock.period,
                       "mhz": MHZ, "rows": results}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
