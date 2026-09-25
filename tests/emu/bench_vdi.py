"""What the VDI's primitives cost on the target, and where the cycles go.

Not a gate: a tool for the per-pixel work Phase 8b left on the list.
Feeds the m3 runner one primitive N times and reports frames and
milliseconds per op; with --profile, Altirra's instruction profiler
runs across the op and the hottest addresses come back resolved to the
nearest symbol, with cycles per instruction -- the number that says
whether the CPU is fast (about 0.4 at 11x, with the code in SRAM) or
the code is long.  `docs/phase8b.md` has the readings this replaced.

  python3 tests/emu/bench_vdi.py [--profile] [--mode insns|functions|basicblock]
                                 [--by-function] [--top N] [NAME ...]

Addresses come back with their bank from the patched emulator (hot_name,
below); from one without it, ones inside a far section of the map are
resolved against that bank's symbols, the rest against bank $00.
--by-function sums the whole profile per function instead of listing
addresses, which is the number to compare a rewrite by: a function's
instructions per op, idle polling and the runner's own work shown beside
it.  The compiler's `?L` labels are not functions: a shared code fragment
it factors out of one or more of them (`--assembly-source` shows which) is
placed by the linker among the other small sections, far from any of them,
so it is counted under its MODULE -- `vdi.o ?L` -- which is what the map
records of it; the raster expander's store fragment is the usual one.
"""
import bisect
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import m3_vdi as m                                                  # noqa: E402
import symfile                                                      # noqa: E402
import vdiref as V                                                  # noqa: E402
from m3_vdi import (STATUS, ST_GO, ST_DONE, launch, DISK, pack_mfdb,  # noqa: E402
                    ICON_W, ICON_H, ICON_WDW)

ONES = bytes([0xFF]) * 96
N = 16

ICON = lambda mode, x: (V.VRT_CPYFM, (0, 0, 31, 23, x, 40), (mode, 1, 0), "icon")
CLIP_CORNER = (V.VS_CLIP, (620, 230, 639, 239), (1,))
CLIP_OFF = (V.VS_CLIP, (0, 0, 639, 239), (0,))

# name: (script of N ops, ops counted, form bits)
CASES = {
    "pline-h":     ([(V.V_PLINE, (10, 10 + 8 * i, 610, 10 + 8 * i)) for i in range(N)], N),
    "pline-diag":  ([CLIP_OFF] + [(V.V_PLINE, (0, i, 100, 100 + i)) for i in range(N)], N),
    "pline-clipped": ([CLIP_CORNER] + [(V.V_PLINE, (0, i, 600, 200 + i)) for i in range(N)], N),
    "icon-trans":  ([ICON(V.MD_TRANS, 64 * (i & 3)) for i in range(N)], N),
    "icon-replace": ([ICON(V.MD_REPLACE, 64 * (i & 3)) for i in range(N)], N),
    "icon-xor":    ([ICON(V.MD_XOR, 64 * (i & 3)) for i in range(N)], N),
    "cursor":      ([(V.VSC_FORM, (), m.cursor_form())]
                    + [(V.V_SHOW_C, (), (0,)), (V.V_HIDE_C,)] * N, 2 * N),
    "vsc_form":    ([(V.VSC_FORM, (), m.cursor_form())] * N, N),
    "vswr_mode":   ([(V.VSWR_MODE, (), (1,))] * N, N),
}


def far_ranges(mapfile):
    """Every far section placement in the linker map -- bank $01 upwards,
    one memory per bank -- as (bank, lo, hi) with lo and hi the low 16
    bits.  The bridge reports a profile address without its bank (it masks
    the profiler's 24-bit record to 16), so this is what puts it back."""
    out = []
    with open(mapfile) as f:
        for line in f:
            mm = re.match(r"\s*\S+\s+([0-9a-f]{2})([0-9a-f]{4})-([0-9a-f]{2})([0-9a-f]{4})"
                          r"\s+[0-9a-f]{6}\s+\S+\s+\d+\s*$", line)
            if mm and mm.group(1) == mm.group(3) and mm.group(1) != "00":
                out.append((int(mm.group(1), 16), int(mm.group(2), 16),
                            int(mm.group(4), 16)))
    return out


def banks_of(ranges, addr):
    """The banks a bankless address could be in: every far bank with a
    section covering it, or bank $00.  More than one is possible once the
    code has spilled into a second bank, and then the attribution is
    honestly ambiguous -- the caller shows every candidate."""
    banks = sorted({b for b, lo, hi in ranges if lo <= addr <= hi})
    return banks or [0]


def placements(mapfile):
    """Every placed section in the linker map, sorted: (lo, hi, name,
    module), the addresses 24-bit.  A `?L` fragment's module is recorded
    here and nowhere else."""
    text = open(mapfile).read()
    out = []
    for mm in re.finditer(r"`?([?\w]+)`? in section '\w+'\s+placed at address "
                          r"([0-9a-f]{6})-([0-9a-f]{6}) of size [0-9a-f]+\s*\n\((\S+)",
                          text):
        name, lo, hi, mod = mm.groups()
        out.append((int(lo, 16), int(hi, 16), name, os.path.basename(mod)))
    return sorted(out)


def where(place, syms, ranges, addr):
    """What a profile address (its bank dropped) belongs to: the function
    whose section holds it -- a static one's section is named by a `?L`
    label in the map, but the function's own symbol starts it -- or, for a
    section holding no function, a fragment, its module: `vdi.o ?L`."""
    return "|".join(where_in(place, syms, bank, addr)
                    for bank in banks_of(ranges, addr))


def hot_name(place, syms, ranges, h):
    """What a PROFILE_DUMP row belongs to.

    The patched emulator reports each row's bank (`addr24`,
    ~/dev/altirra-patched BUILT-FROM.txt, branch gem4xe/profile-bank), so
    the row is named in ITS bank: the OS ROM as the OS ROM, bank $00
    outside the program as the DOS or the OS's RAM, and far code by the
    map.  An emulator without the field gets the old answer -- every bank
    the offset could be in, `a|b`, with the bank-$00 candidates beside
    them, because the profiler's 16-bit address named bank $00's OS ROM
    after far functions at the same offset (docs/phase53.md)."""
    if "addr24" in h:
        a = int(str(h["addr24"]).lstrip("$"), 16)
        bank, off = a >> 16, a & 0xFFFF
        if bank == 0 and (off >= 0xD800 or 0xC000 <= off < 0xD000):
            return "OS ROM"
        i = bisect.bisect_right(place, (a, 0xFFFFFF, "", "")) - 1
        if i >= 0 and place[i][0] <= a <= place[i][1]:
            return where_in(place, syms, bank, off)
        if bank == 0:
            return "bank $00, not the program (DOS, OS RAM)"
        return f"${bank:02X}:{off & 0xFF00:04X} page, not the program"
    a = int(str(h["addr"]).lstrip("$"), 16)
    fn = where(place, syms, ranges, a)
    if 0xC000 <= a < 0xD000 or a >= 0xD800:
        fn = "OS ROM|" + fn
    elif 0x2000 <= a < 0x4000:
        fn = "near|" + fn
    return fn


def where_in(place, syms, bank, addr):
    a = (bank << 16) | addr
    i = bisect.bisect_right(place, (a, 0xFFFFFF, "", "")) - 1
    if i >= 0 and place[i][0] <= a <= place[i][1]:
        lo, hi, name, mod = place[i]
        if not name.startswith("?L"):
            return name
        best = None
        for sym, sa in syms.items():
            if lo <= sa <= a and not sym.startswith("?L") and \
                    (best is None or sa > best[0]):
                best = (sa, sym)
        return best[1] if best else f"{mod} ?L"
    return nearest_in(syms, bank, addr).split("+")[0]


def nearest(syms, ranges, addr):
    """The symbol at or below addr in the bank(s) the map says it could be
    in -- every candidate when a second far bank makes that ambiguous."""
    return "|".join(nearest_in(syms, bank, addr) for bank in banks_of(ranges, addr))


def nearest_in(syms, bank, addr):
    best = None
    for name, a in syms.items():
        if (a >> 16) != bank:
            continue
        lo = a & 0xFFFF
        if lo <= addr and (best is None or lo > best[0]):
            best = (lo, name)
    return f"{best[1]}+{addr - best[0]:x}" if best else "?"


def run(b, syms, ranges, place, label, script, ops, profile, top, by_function):
    sa, sc = syms["vdi_script"], syms["vdi_scratch"]
    script_room = min(a for a in syms.values() if a > sa) - sa
    b.memload(sc, ONES)
    b.memload(sc + 512, pack_mfdb(sc, ICON_W, ICON_H, ICON_WDW))
    b.memload(sc + 532, pack_mfdb(0, 0, 0, 0))
    full = [(V.V_OPNWK, (), V.WORK_IN), (m.V_CLRWK,)] + script
    resolved = [(r[0], r[1] if len(r) > 1 else (), r[2] if len(r) > 2 else (),
                 (True if r[3] == "icon" else None) if len(r) > 3 else None)
                for r in full]
    m.poke_script(b, sa, resolved, sc + 512, script_room, screen_mfdb=sc + 532)
    b.poke(STATUS + ST_DONE, 0)
    if profile:
        b.ok(f"PROFILE_START mode={profile}")
    b.poke(STATUS + ST_GO, 1)
    f = 0
    for _ in range(3000):
        b.frames(1)
        f += 1
        if b.peek(STATUS + ST_DONE) == 0xA5:
            break
    print(f"{label:14s} {ops:3d} ops in {f:3d} frames: {f / ops:5.2f} frames, "
          f"{f * 20 / ops:5.1f} ms per op")
    if profile:
        b.ok("PROFILE_STOP")
        r = b.ok(f"PROFILE_DUMP top={4096 if by_function else top}")
        tc, ti = r["total_cycles"], r["total_insns"]
        print(f"    {ti} insns in {tc} machine cycles: {tc / max(ti, 1):.2f} cycles/insn, "
              f"{ti / ops:.0f} insns/op")
        if by_function:
            insns, cycles = collections.Counter(), collections.Counter()
            for h in r["hot"]:
                fn = hot_name(place, syms, ranges, h)
                insns[fn] += h["insns"]
                cycles[fn] += h["cycles"]
            for fn, n in insns.most_common(top):
                print(f"    {fn:30s} insns {n:7d} ({n / ops:6.0f}/op)  "
                      f"cycles {cycles[fn]:7d} ({cycles[fn] / ops:6.0f}/op)")
            return
        for h in r["hot"]:
            a = int(str(h["addr"]).lstrip("$"), 16)
            lab = nearest(syms, ranges, a)
            if lab.startswith("?L"):
                lab += f" ({where(place, syms, ranges, a)})"
            print(f"    {a:04x} {lab:30s} insns {h['insns']:7d}  "
                  f"cycles {h['cycles']:7d}  {h['cycles'] / max(h['insns'], 1):.2f}"
                  + (f"  calls {h['calls']}" if profile != "insns" else ""))


def main(argv):
    profile = "insns" if "--profile" in argv else None
    by_function = "--by-function" in argv
    if by_function and not profile:
        profile = "insns"
    top = 24
    names = []
    it = iter(a for a in argv if a not in ("--profile", "--by-function"))
    for a in it:
        if a == "--top":
            top = int(next(it))
        elif a == "--mode":
            profile = next(it)
        else:
            names.append(a)
    names = names or list(CASES)
    for n in names:
        if n not in CASES:
            print(f"no such case: {n}; cases: {' '.join(CASES)}")
            return 2
    syms = symfile.load(m.SYMS)
    mapfile = os.path.splitext(m.SYMS)[0] + ".map"
    ranges = far_ranges(mapfile)
    place = placements(mapfile)
    emu = launch(tag="bench", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(200)
        if bytes(b.memdump(STATUS, 3))[:2] != b"VD":
            print("FAIL: runner did not come up")
            return 1
        st = bytes(b.memdump(STATUS + 25, 5))
        print("rapidus: present %d  MCR %02x -> %02x  CMCR %02x  synced %02x" % tuple(st))
        for n in names:
            script, ops = CASES[n]
            run(b, syms, ranges, place, n, script, ops, profile, top, by_function)
    finally:
        emu.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
