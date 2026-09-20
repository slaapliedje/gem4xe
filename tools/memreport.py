#!/usr/bin/env python3
"""Where bank $00 has gone, and whether there is enough of it left.

WHY THIS EXISTS.  gem4xe's binding constraint is not the 14.5 MB of
linear RAM, it is the 64 KB bank the 65816 addresses DATA in: under the
small data model every C global is reached absolutely through the data
bank register, so `cdata`, `idata`, `data` and `zdata` are bank $00 by
requirement rather than by preference (src/gem4xe.scm).  On an Atari most
of that bank is spoken for before gem4xe starts -- the OS ROM, the
hardware, the DOS, the MEMAC window, a SpartaDOS X cartridge -- and what
is left is about 31 KB, of which the engine's data is 7.5 KB and the
application pool is 14 KB.

Running out of it is not a gentle failure.  It is a link that stops with
"Failed to place 1 section fragment(s)" in the middle of a change, or --
worse -- a pool that still holds the desktop but no longer leaves GEMDOS
a read slice worth having, which nothing fails on and everything gets
slower for.  So the budget is measured here and asserted, rather than
discovered.

WHAT IT READS.  The linker's own map for the regions, each .g4a's header
for what a program reserves, and each .RSC's header for what a resource
costs the pool once its icon bitmaps have gone to far memory
(src/aes/rsrc.c).  Nothing is written down that a build artefact already
knows, except the engine's own pool overhead, which is one constant with
its source named -- and test-boot asserts the LIVE figure on the real
machine, so a drift in that constant is caught rather than believed.
"""
import os
import re
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BUILD = os.path.join(ROOT, "build")

# The engine's own take from the pool, before any program: the process
# records (src/aes/proc.h, NUM_PROCS * sizeof(PROC)) and an eight-message
# queue for each accessory that loads.  test-boot checks the live number.
PROC_STORE = 7 * 52
ACC_QUEUE = 8 * 8 * 2

# What must be left, and why.
FLOORS = {
    "LoRAM": (256, "the engine's stack and every one of its globals; a "
                   "change that needs a new table has nowhere else to go"),
    "Near": (128, "near code and rodata"),
    "DirectPage": (32, "the compiler's register file travels with a "
                       "context switch (src/sys/ctx.s)"),
}
POOL_FLOOR = (2048, "GEMDOS reads files and directories through a slice of "
                    "whatever the pool has spare, capped at 2 KB and "
                    "falling back to 64 bytes of stack below 128 "
                    "(src/sys/gemdos.c)")


def regions(mapfile):
    """(name, size, used%, largest free) for each memory in a linker map."""
    out = {}
    for ln in open(mapfile):
        m = re.match(r"^(\w+)\s+([0-9a-f]{6})-([0-9a-f]{6})\s+([0-9a-f]+)\s+"
                     r"([\d.]+)%\s+\S+\s+(\S+)", ln)
        if m:
            free = 0 if m.group(6) == "none" else int(m.group(6), 16)
            out[m.group(1)] = (int(m.group(2), 16), int(m.group(4), 16),
                               float(m.group(5)), free)
    return out


def g4a_near(path):
    """What a .G4A reserves in the pool: its whole near region."""
    d = open(path, "rb").read(20)
    assert d[:3] == b"G4A" and d[3] in (3, 4), (path, d[:4])   # tools/mkg4a.py
    return struct.unpack("<H", d[6:8])[0]


def rsc_pool(path):
    """What a .RSC costs the pool: (resident, far, PEAK).

    The peak is not the resident cost and the difference is not small.
    rs_load reads rsh_rssize -- the WHOLE file -- into one pool_alloc and
    only then does rs_fixit move the icon bitmaps to far memory
    (src/aes/rsrc.c).  So while it is loading, the pool is carrying the
    file entire; the desktop's is 6,308 bytes against 4,772 resident.
    Reporting only the resident figure is how this tool once said
    "memory: ok" for a pool that could not load the desktop at all --
    test-m28 went red and said "DESKTOP.RSC is not on the boot disk".
    """
    d = open(path, "rb").read()
    h = struct.unpack(">18H", d[:36])
    vrsn, imdata, nbb, nimages, rssize = h[0], h[7], h[14], h[16], h[17]
    # A new-format resource keeps its colour icons past rssize; rs_load
    # streams that to far memory and brings ONE 50-byte mono header per
    # icon back into the pool, after rs_imfar's wind-back (src/aes/rsrc.c,
    # CICON_NEAR).  Count the icons the way the loader does: the table at
    # the offset the extension array names, up to its -1.
    near_icons = 0
    if (vrsn & 0x0004) and len(d) > rssize + 8:
        tab = struct.unpack(">I", d[rssize + 4:rssize + 8])[0]
        if tab not in (0, 0xFFFFFFFF) and tab < len(d):
            while struct.unpack(">i", d[tab + 4 * near_icons:tab + 4 * near_icons + 4])[0] != -1:
                near_icons += 1
    hdrs = 50 * near_icons
    # rs_imfar moves the image block only when it is the TAIL of the file:
    # nothing the header places may end above rsh_imdata, or winding the
    # pool back over the bits would take it too (HypView's does that).
    (o_obj, o_ted, o_ib, o_bb, o_frstr, o_str, _, o_frimg, o_tri) = h[1:10]
    nobs, ntree, nted, nib = h[10], h[11], h[12], h[13]
    tail = max(o_obj + 24 * nobs, o_ted + 28 * nted, o_ib + 34 * nib,
               o_bb + 14 * nbb, o_frstr + 4 * h[15], o_frimg + 4 * nimages,
               o_tri + 4 * ntree, o_str) <= imdata
    if nbb or nimages or not tail:
        return rssize + hdrs, len(d) - rssize, rssize + hdrs
    return imdata + hdrs, rssize - imdata + len(d) - rssize, max(rssize, imdata + hdrs)


def main(argv):
    quiet = "--quiet" in argv
    bad = []
    r = regions(os.path.join(BUILD, "gem.map"))

    def say(*a):
        if not quiet:
            print(*a)

    say("bank $00, as the linker left it")
    say(f"  {'region':<12} {'size':>6} {'used':>6}  {'free':>6}")
    for name in ("DirectPage", "LoRAM", "Near", "Window", "AppPool", "Stage"):
        if name not in r:
            continue
        base, size, pct, free = r[name]
        say(f"  {name:<12} {size:6d} {pct:5.1f}%  {free:6d}   ${base:04X}")
        floor = FLOORS.get(name)
        if floor and free < floor[0]:
            bad.append(f"{name} has {free} bytes free, wanted {floor[0]} -- "
                       f"{floor[1]}")

    desk = g4a_near(os.path.join(BUILD, "desktop.g4a"))
    desk_rsc, desk_far, desk_peak = rsc_pool(os.path.join(BUILD,
                                                          "desktop.rsc"))

    def large_data(name):
        """Was this program linked against the LARGE-data kit?  That is what
        decides where its resource goes: a program holding 32-bit pointers
        may be handed a far address, and rs_load puts the resource there
        rather than in the pool (src/aes/rsrc.c).  Read out of the map's
        own command line -- clib-lc-ld.a against clib-lc-sd.a -- so it
        follows the build instead of being restated here and drifting."""
        p = os.path.join(BUILD, name + ".map")
        try:
            with open(p, "r", errors="replace") as f:
                return "clib-lc-ld.a" in f.read(4096)
        except OSError:
            return False

    # THE DESKTOP'S RESOURCE GOES FAR TOO once it is a large-data program,
    # and it is the largest single thing the pool ever held.  Charged 0
    # here, with the whole file counted as far rather than just its icons.
    if large_data("desktop"):
        desk_far = desk_rsc + desk_far
        desk_rsc = desk_peak = 0

    def accessories(*want):
        """(name, near, resident, peak) for each accessory that loads."""
        out = []
        for name, rsc in want:
            p = os.path.join(BUILD, name + ".g4a")
            if not os.path.exists(p):
                continue
            if rsc and not large_data(name):
                pr, _, pk = rsc_pool(os.path.join(BUILD, rsc + ".rsc"))
            else:
                pr = pk = 0          # no resource, or one that goes far
            out.append((name.upper(), g4a_near(p), pr, pk))
        return out

    def walk(base, pool, accs, title, loud):
        """The bump allocator, in the order the machine runs it: proc_init,
        then each accessory (queue, near region, resource), then the
        desktop.  A PROGRAM's near region is page-aligned (app.c:
        pool_alloc(near_size, 0x100)) and everything else is word-aligned,
        so this is a simulation of pool_alloc rather than a sum -- which is
        what makes it agree with the figure test-boot reads off the live
        machine instead of being close to it.

        Returns (free, worst) where `worst` is the smallest the pool ever
        gets, counting each resource's TRANSIENT peak: rs_load holds the
        whole file before rs_fixit moves the icons far, so the moment of
        loading is tighter than anything the resident figures show.
        """
        brk, top, worst = base, base + pool, pool

        def take(n, align, what, peak=None):
            nonlocal brk, worst
            at = (brk + align - 1) & ~(align - 1)
            brk = at + n
            worst = min(worst, top - (at + (peak if peak else n)))
            if loud:
                note = f"   (peaks at {peak})" if peak and peak != n else ""
                say(f"  {what:<34} {-n:6d}   ${at:04X}{note}")

        if loud:
            say("")
            say(title)
            say(f"  {'pool':<34} {pool:6d}   ${base:04X}")
        take(PROC_STORE, 2, "process records")
        for nm, near, pr, pk in accs:
            take(ACC_QUEUE, 2, nm + " message queue")
            take(near, 0x100, nm + " near region")
            if pr:
                take(pr, 2, nm + " resource", pk)
        # Where the shell marks the floor: everything permanent is below it
        # and no program's exit may wind back past it (src/sys/app.c).  The
        # desktop and its resource are above it, and come and go with it.
        if loud:
            say(f"  {'-- permanent below here':<34} {'':6}   ${brk:04X}")
        take(desk, 0x100, "the desktop")
        if desk_rsc:
            take(desk_rsc, 2, "its resource", desk_peak)
        free = top - brk
        if loud:
            say(f"  {'= free':<34} {free:6d}   "
                f"({desk_far} bytes of resource are far, not here)")
            say(f"  {'= free while it was loading':<34} {worst:6d}   "
                f"(rs_load holds the whole file: src/aes/rsrc.c)")
        return free, worst

    # BOTH LAYOUTS, because the one that binds is not the product's.
    # GEM.COM gives the pool the whole banked window; the conformance
    # runner keeps $7900-$7FFF for its host-poked buffers, so its pool is
    # 1.5 KB smaller -- and m17/m18/m23/m28 load the desktop AND an
    # accessory into it.  Checking only gem.map is how this tool reported
    # "memory: ok" for a pool that could not load the desktop.
    #
    # Each layout is charged what IT loads, not a shared guess: the
    # product's resident accessory is the clock, with a resource; the
    # runner's is m28's gate accessory, which has none.
    # The 2 KB floor is the PRODUCT's budget -- how big a slice GEMDOS gets
    # to read through afterwards, which is a speed question.  The runner's
    # pool is deliberately smaller and has always been under it; what the
    # runner must satisfy is the hard one, that the peak fits at all.
    for mapname, accs, floor, title in (
            ("gem.map", accessories(("clockacc", "clock"),
                                    ("cpanelacc", "cpanel"),
                                    ("calcacc", "calc")), POOL_FLOOR[0],
             "the application pool, with everything the product "
             "ships resident"),
            ("m3desk.map", accessories(("m28_acc", None)), 0,
             "...and the conformance runner's pool, which is smaller and "
             "carries the desktop beside an accessory (test-m28)")):
        path = os.path.join(BUILD, mapname)
        if not os.path.exists(path):
            continue
        rr = regions(path)
        if "AppPool" not in rr:
            continue
        base, pool = rr["AppPool"][0], rr["AppPool"][1]
        free, worst = walk(base, pool, accs, title, not quiet)
        if worst < 0:
            bad.append(f"{mapname}: the pool runs out by {-worst} bytes "
                       f"while a resource is loading -- rs_load takes the "
                       f"whole file (src/aes/rsrc.c) and this is what "
                       f"test-m28's 'DESKTOP.RSC is not on the boot disk' "
                       f"looks like before the machine says it")
        elif free < floor:
            bad.append(f"{mapname}: the pool would have {free} bytes free, "
                       f"wanted {floor} -- {POOL_FLOOR[1]}")

    say("")
    if bad:
        for b in bad:
            print("FAIL:", b)
    say("memory: ok" if not bad else f"memory: {len(bad)} over budget")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
