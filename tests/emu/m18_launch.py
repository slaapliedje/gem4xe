#!/usr/bin/env python3
"""Phase 14, milestone 6 gate: a program run from the desktop, and the
desktop's windows back afterwards.

DESKTOP.G4A under sh_main on the SpartaDOS disk, with the harness at the
mouse: a double-click on drive A opens its window; the fuller grows it
to the desk; a double-click on M11.G4A runs it -- do_aopen sets the
default directory, hands the name to shel_write(SHW_EXEC), and the
desktop returns to the shell with its window recorded through
shel_put; M11.G4A runs by itself and returns; the shell runs the
desktop again, which reads the record back through shel_get and
opens the window where it was; File -> Quit ends the session.  Four
things are checked, as test-m17 checks them --

  the screen against the model at every stop of both runs: the desk
  up, the window on A:, full, the window back on A: after M11.G4A,
  the File menu dropped, Quit under the pointer;

  the desktop's globals G, read out of the target at every stop and
  compared byte for byte with the model's -- the window slots and the
  shell-buffer copy in its far arena are not in G, but every window
  opened from them is;

  the calls: the ABI's counter counts the three programs' calls in
  one run of the counter, so the second desktop's plans key on the
  first's calls plus M11.G4A's -- 18 AES and VDI calls and 7 + n
  GEMDOS calls, n the root entries the model's listing answers -- and
  the sys op's record at the end must say three programs ran, the
  model's calls in all, none refused;

  the pool and the far heap afterwards, back where the first desktop
  found them (the shell winds the far heap back to the desktop's blob
  after every program, which is why the second run's Malloc lands
  where the first's did), and both stacks' low-water marks.

The model is tools/deskref.py twice against one AES model: the first
desktop's shel_put leaves the record in the model's shell buffer, the
second's shel_get finds it there.  M11.G4A's calls are not replayed on
the model -- the shell's restart (m16_shell) resets everything of the
AES it touches -- only counted.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vdiref, vbxeref, symfile     # noqa: E402
import deskref                              # noqa: E402
from deskref import Desktop, DROOT, GLOBES_SIZE, STACK_STRING  # noqa: E402
from aesref import W_FULLER, FA_SUBDIR, RSRC_LOAD, Text    # noqa: E402
from deskrsc import FILEMENU, QUITITEM      # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE,  # noqa: E402
                     F, DCLICK, drive, compare, storm_check)
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m11_abi import app_calls, UNRECORDED_AES   # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC                 # noqa: E402
from m14_sparta import DISK as M14_DISK, boot, screen   # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402
from m17_desktop import (DISK, DESKTOP, DESK_RSC, rsc_imlen,  # noqa: E402
                         DESK_SYM, SYMS, SHOT, PROBE, DRVBYT,
                         GCLICK, header, listing, menu)
from demo_aes import path                   # noqa: E402

PROGRAM = "M11.G4A"                         # what the desktop runs
# the stops, in the order the plans take them: the first desktop's, then
# the second's
STOPS1 = ["desktop", "window-a", "full"]
STOPS2 = ["restored", "file-menu", "quit-item"]
STOPS = STOPS1 + STOPS2


def inputs_before(memo):
    """The first desktop's step producers, one per wait."""
    def probe(d):
        memo.setdefault("globes", []).append(d.globes())
        return PROBE

    def open_a(d):
        # the first evnt_multi: the desk is up.  Two clicks on drive A's
        # icon select it and open a window on A:\*.* (hndl_button,
        # do_dopen)
        icon = d.centre(d.g_screen_addr, d.screen[DROOT].ob_head)
        return [F(3), probe(d), SHOT, *path(d.pointer(), icon), F(4), *DCLICK(icon)]

    def window_a(d):
        # the fuller: the window grows to the desk, and every item shows
        pw = d.win_ontop()
        memo["wh"] = pw.id
        g = d.gadget(pw.id, W_FULLER)
        return [F(3), probe(d), SHOT, *path(d.pointer(), g), F(2), *GCLICK(g)]

    def full(d):
        # two clicks on the program: do_aopen -- shel_write, and the
        # desktop returns with the window put away
        item = d.item(d.win_ontop(), PROGRAM)
        return [F(3), probe(d), SHOT, *path(d.pointer(), item), F(4), *DCLICK(item)]

    return [open_a, window_a, full]


def inputs_after(memo):
    """The second desktop's: one wait, with the window back."""
    def probe(d):
        memo.setdefault("globes", []).append(d.globes())
        return PROBE

    def restored(d):
        # the first evnt_multi of the desktop's second run: the window is
        # back on A:\*.* where it was; File -> Quit
        return [F(3), probe(d), SHOT, *menu(d, FILEMENU, QUITITEM, True)[1:]]

    return [restored]


def program_calls(a):
    """M11.G4A's ABI calls (src/m11_app.c): the AES and VDI calls test-m11
    lists, then Sversion, Dgetdrv, Fsetdta, Fsfirst on A:\\*.* and Fsnext
    until there is nothing more, Fopen, Malloc, Fgetdta -- the directory
    walk made on the model's listing, as M11.G4A makes it."""
    a.mem[STACK_STRING] = Text("A:\\*.*")
    r = a.gemdos(0x4E, (STACK_STRING & 0xFFFF, STACK_STRING >> 16, FA_SUBDIR))
    n = 0
    while r == 0:
        n += 1
        r = a.gemdos(0x4F, ())
    # ...AND THE PROBES M11.G4A MAKES WITHOUT RECORDING THEM.  app_calls()
    # is the sequence test-m11 compares against the model, and the
    # objc_sysvar, appl_find and appl_getinfo probes are deliberately
    # outside it -- but the ABI's counter, which is what this offset
    # indexes into, counts every call.  Imported rather than written
    # again, so the next probe added to src/m11_app.c is counted in both
    # places or in neither: it was counted in neither when objc_sysvar
    # arrived, and this gate spent five commits red for it.
    return len(app_calls(0, 0)) + UNRECORDED_AES + 7 + n


def model_desk(v, a):
    """sh_main between programs: the last program's workstations closed,
    the window manager, the menu and the pointer started, the desk drawn
    (m16_shell.model_desk)."""
    v.close_virtuals()
    a.wm_init()
    a.mn_init()
    a.ratinit()
    a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
    a.tree = a.W_TREE
    a.draw(0, 0, (0, 0, a.gl_width, a.gl_height))


def model(mark, brk, pointer, drvmap):
    """The prelude and both desktops against one model: (v, a, want, d1,
    d2, memo, m11).  `brk` is the far heap's cursor before the shell
    reads the desktop's file to it; `m11` is M11.G4A's call count."""
    v, a, want = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
    link_near, near_size, far_banks = header(DESKTOP)
    # the far heap as the desktop's Malloc finds it on either run: the
    # file's blob at brk (shel.c far_read_file, kept between programs),
    # the code's banks from the next boundary (app.c app_load, farmem.c
    # far_alloc_banks); app_free winds the heap back to the blob's end
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3
    # ...and the resource's icon bitmaps, taken by rs_load before the
    # desktop Mallocs anything and given back by app_free with the rest
    # (src/aes/rsrc.c).  Each run of the desktop takes them again, which
    # is why the arena is the same on both.
    im_base = ((brk + desk_len + 0xFFFF) & ~0xFFFF) + (far_banks << 16)
    im_len = rsc_imlen(DESK_RSC)
    arena = im_base + ((im_len + 3) & ~3)
    if not im_len:
        im_base = None                  # they stayed in the pool
    a.dos_dirs = listing(DISK)
    g_link = symfile.load(DESK_SYM)["G"]
    memo = {}

    model_desk(v, a)
    a.dos_brk = arena
    d1 = Desktop(v, a, mark, link_near, near_size, g_link, drvmap,
                 inputs_before(memo), imbase=im_base)
    d1.main()
    # M11.G4A: counted, not replayed
    m11 = program_calls(a)
    model_desk(v, a)
    a.dos_brk = arena
    d2 = Desktop(v, a, mark, link_near, near_size, g_link, drvmap,
                 inputs_after(memo), imbase=im_base)
    d2.main()
    return v, a, want, d1, d2, memo, m11


def main(argv):
    keep = "--shot" in argv
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    calls, ptr = syms["app_calls"], syms["ptr_state"]
    runs, lastret, lastrc = syms["sh_runs"], syms["sh_lastret"], syms["sh_lastrc"]
    for addr in (calls, ptr, runs, lastret, lastrc):
        assert not 0x4000 <= addr < 0x8000, hex(addr)
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3   # far_alloc's rounding
    os.makedirs(SHOTDIR, exist_ok=True)
    shots = []

    def shot(b, name):
        p = os.path.join(SHOTDIR, f"m18-{name}.png")
        b.screenshot(p)
        shots.append(p)
        return p

    def map_range(path, name):
        ln = [ln for ln in open(os.path.join(ROOT, "build", path))
              if ln.startswith(name + " ")][0].split()
        return tuple(int(x, 16) for x in ln[1].split("-"))

    # m3desk's own map: the runner this gate boots.  m3's shares its
    # layout only until one of them relinks -- a stale m3.map once put
    # the painted range eleven bytes into live variables and read the
    # stack as touching bottom (2026-09-16)
    stk_lo, stk_hi = map_range("m3desk.map", "stack")
    dstk = map_range("desktop.map", "stack")         # at the link's near base
    dlink = map_range("desktop.map", "AppDP")[0]
    PAINT, MARGIN, DESK_MARGIN = 0xA5, 256, 64

    def paint(b):
        b.memload(stk_lo, bytes([PAINT]) * (stk_hi - stk_lo + 1))

    def low_water(b):
        dmp = b.memdump(stk_lo, stk_hi - stk_lo + 1)
        for i, x in enumerate(dmp):
            if x != PAINT:
                return stk_lo + i
        return stk_hi + 1

    assert DISK != M14_DISK
    emu = launch(tag="m18", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        t, st = boot(b, prepare=paint)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  M3.COM loaded and running {t} frames after RETURN")
        kind = st[8]
        drvmap = 0x03 if kind else (b.peek(DRVBYT) or 1)
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room, brk = rec[6] & 0xFFFF, rec[7], (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}; "
              f"DOS kind {kind}, drive map {drvmap:#04x}")

        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want, d1, d2, memo, m11 = model(mark, brk, pointer, drvmap)
        check(d1.G == d2.G, f"the desktops' G differ: ${d1.G:04X}, ${d2.G:04X}")
        print(f"  the model's desktop: {len(d1.script)} calls, waits at {d1.waits}, "
              f"near ${d1.near:04X}, G ${d1.G:04X}, arena ${d1.dta:06X}; "
              f"{PROGRAM}: {m11} calls; the desktop again: {len(d2.script)} calls, "
              f"waits at {d2.waits}")
        check(len(ref_a.shots) == len(STOPS),
              f"the model took {len(ref_a.shots)} shots, not {len(STOPS)}")
        # the second desktop's calls, as the one counter counts them
        offset = len(d1.script) + m11

        stage = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(stage, 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        poke16(b, calls, 0)
        b.poke(STATUS + ST_GO, 1)

        def read():
            return (b.peek16(calls) - 1) & 0xFFFF

        # Set by paint_desk, cleared by catch: the low-water report below
        # is meaningless unless THIS run's stack was painted.
        painted = [False]

        def reach(first, what):
            """Frames until the counter says the desktop is in call
            `first`, the first wait of a run; the load from disk is slower
            than drive() waits for a start."""
            for t in range(0, 4000, 5):
                n = read()
                if n != NOT_STARTED and n >= first:
                    break
                b.frames(5)
            else:
                check(False, f"{what} did not reach its first wait (call {read()})")
                return None
            check(n == first, f"{what} is in call {n}, not its first wait {first}")
            return t

        def catch(k, what, limit=4000):
            painted[0] = False      # each run's loader zeroes the region
                                    # again, so the last run's paint is gone
            """Frames until the counter says the desktop is in call `k`
            -- its rsrc_load, whose read from disk holds it inside the ABI
            for frames, so the S the ABI saved is the desktop's own at
            that moment (src/sys/abi.s gem_api_sp); None if the call went
            by between frames."""
            for t in range(limit):
                n = read()
                if n != NOT_STARTED and n >= k:
                    break
                b.frames(1)
            else:
                check(False, f"{what} did not reach its rsrc_load (call {read()})")
                return None
            if n != k:
                check(False, f"{what} was caught in call {n}, past its rsrc_load {k}")
                return None
            return t

        # The desktop's own stack, painted below where it stands in its
        # rsrc_load -- the loader zeroed it, and each run's loader zeroes
        # it again, so each run is painted and read on its own -- and
        # read at the run's last call.  Its extent is the map's, moved
        # where the loader put the near region.
        dstk_lo, dstk_hi = (x + d1.near - dlink for x in dstk)

        def paint_desk():
            painted[0] = True
            app_s = b.peek16(b.peek16(syms["gem_api_sp"]) - 1)
            ok = dstk_lo <= app_s <= dstk_hi
            check(ok, f"the desktop's S ${app_s:04X} is off its stack "
                      f"${dstk_lo:04X}-${dstk_hi:04X}")
            if ok:
                b.memload(dstk_lo, bytes([PAINT]) * (app_s + 1 - dstk_lo))
            return app_s

        def desk_low_water(bb):
            dmp = bb.memdump(dstk_lo, dstk_hi - dstk_lo + 1)
            for i, x in enumerate(dmp):
                if x != PAINT:
                    return dstk_lo + i
            return dstk_hi + 1

        probes = iter(enumerate(memo["globes"]))

        def probe(bb):
            k, want_g = next(probes)
            got = bb.memdump(d1.G, GLOBES_SIZE)
            if got == want_g:
                print(f"  G at ${d1.G:04X}, probe {k} (call {read()}): "
                      f"{GLOBES_SIZE} bytes as the model has them")
                return
            bad = [i for i in range(GLOBES_SIZE) if got[i] != want_g[i]]
            field = [f for f, _ in deskref.GLOBES
                     if deskref.g_offset(f) <= bad[0]][-1]
            check(False, f"G at probe {k} (call {read()}) differs at {len(bad)} "
                         f"byte(s), first at +{bad[0]} ({field} +"
                         f"{bad[0] - deskref.g_offset(field)}): target "
                         f"{got[bad[0]:bad[0] + 8].hex()} model "
                         f"{want_g[bad[0]:bad[0] + 8].hex()}")

        stops = iter(STOPS)

        def take(bb):
            shot(bb, next(stops))

        def plan_of(d, base):
            return {base + k: [("shot", take) if s == SHOT else
                               ("probe", probe) if s == PROBE else s for s in v]
                    for k, v in d.plan.items()}

        def stall(what):
            # where it stuck: the screen, the CPU, and the last few frames
            # of history (the patched bridge; --shot keeps the picture)
            storm = storm_check(b)
            if storm:
                print(f"  {storm}")
            print(f"  screen at the stall: {shot(b, 'stall')}")
            fault = b.peek(syms["irq_fault"])          # src/sys/irq.s
            lw = desk_low_water(b)
            # An UNPAINTED region reads exactly like an overflowed one --
            # every byte is something other than PAINT -- so the low
            # water means nothing until paint_desk() has run.  It said
            # "OVERFLOWED" for five commits while the desktop was using
            # 279 of its 640 bytes, because the catch above bailed out
            # before the paint and the report did not know.
            where = (f"low water ${lw:04X}"
                     f"{' -- OVERFLOWED' if lw == dstk_lo else ''}"
                     if painted[0] else
                     "never painted, so its low water says nothing")
            print(f"  irq_fault {fault} ({'none' if fault == 0 else 'BRK' if fault == 2 else 'ABORT' if fault == 3 else 'IRQ'}); "
                  f"the desktop's stack ${dstk_lo:04X}-${dstk_hi:04X}, {where}")
            try:
                print(f"  REGS: {b.ok('REGS')}")
                b.ok("CONFIG history true")
                b.frames(2)
                for h in b.ok("HISTORY 32").get("entries", []):
                    print(f"    {h.get('k', '')}:{h['pc']} {h.get('bytes', h['op'])} "
                          f"a={h['a']} x={h['x']} y={h['y']} s={h.get('sh', '')}{h['s']} "
                          f"p={h['p']} e={h.get('e', '')}")
            except Exception as e:          # an unpatched build
                print(f"  no post-mortem: {e}")

        def rsrc_load(d):
            return [i for i, rec in enumerate(d.script) if rec[0] == RSRC_LOAD][0]

        def at_exit(what, base, d):
            """The desktop's stack at its appl_exit -- the last call the
            counter sees before the shell loads the next program over
            the near region -- and its low-water mark."""
            last = base + len(d.script) - 1
            for t in range(600):
                if read() >= last:
                    break
                b.frames(1)
            else:
                check(False, f"{what} did not reach its appl_exit (call {read()})")
            lw = desk_low_water(b)
            used, size = dstk_hi + 1 - lw, dstk_hi - dstk_lo + 1
            print(f"  {what}'s stack: {used} of {size} bytes used at the low-water "
                  f"mark (${lw:04X}), read {t} frames after its last wait")
            check(lw - dstk_lo >= DESK_MARGIN,
                  f"{what}'s stack came within {lw - dstk_lo} bytes of its bottom ${dstk_lo:04X}")

        # 1. the first desktop: open A, full, run the program
        t = catch(rsrc_load(d1), "the desktop")
        if t is None:
            return 1
        app_s = paint_desk()
        print(f"  the desktop in its rsrc_load {t} frames after GO, S ${app_s:04X}")
        t = reach(d1.waits[0], "the desktop")
        if t is None:
            return 1
        print(f"  the desktop up {t} frames later, in call {read()}")
        err = drive(b, None, ptr, plan_of(d1, 0), read=read)
        check(not err, f"driving the desktop: {err}")
        if err:
            stall("the desktop")
            return 1
        at_exit("the desktop", 0, d1)

        # 2. the program runs and returns; the desktop is run again
        t = poll(b, runs, 3, limit=4000)
        check(t >= 0, f"sh_runs did not reach 3 (reads {b.peek16(runs)}, call {read()})")
        if t < 0:
            stall(PROGRAM)
            return 1
        got = b.peek16(lastret)
        check(got == len(app_calls(0, 0)),
              f"{PROGRAM}'s main() returned {got}, not {len(app_calls(0, 0))}")
        check(b.peek16(lastrc) == 0, f"the last load's status {b.peek16(lastrc)}")
        print(f"  {PROGRAM} ran and returned {got}; the desktop's second run "
              f"{t} frames after the double-click")
        check(d1.near == d2.near, "the second desktop's near region moved")
        t = catch(offset + rsrc_load(d2), "the desktop again")
        if t is None:
            stall("the desktop again")
            return 1
        app_s = paint_desk()
        print(f"  the desktop again in its rsrc_load {t} frames later, S ${app_s:04X}")
        t = reach(offset + d2.waits[0], "the desktop again")
        if t is None:
            stall("the desktop again")
            return 1
        print(f"  the desktop back up {t} frames later, in call {read()} "
              f"= {len(d1.script)} + {m11} + {d2.waits[0]}")

        # 3. the second desktop: the window back, Quit
        err = drive(b, None, ptr, plan_of(d2, offset), read=read)
        check(not err, f"driving the desktop again: {err}")
        if err:
            stall("the desktop again")
        poke16(b, ptr + 4, 0)               # the button, held since Quit
        at_exit("the desktop again", offset, d2)
        check(next(probes, None) is None, "not every probe was taken")
        for name, rgb in zip(STOPS, ref_a.shots):
            p = os.path.join(SHOTDIR, f"m18-{name}.png")
            if not os.path.exists(p):
                check(False, f"no screenshot at {name}")
                continue
            bad, shown = vbxeref.compare_to_shot(rgb, p)
            check(not bad, f"{name}: {bad} px differ from the model; first {shown[:3]}")
            print(f"  {name:<58s} {'ok' if not bad else 'FAIL'}")

        # the sys op's return
        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            check(False, f"after Quit: the runner did not finish (call {read()})")
            return 1
        b.frames(4)
        n = b.peek16(r.count)
        check(n == len(stage), f"{n} records, not {len(stage)}")
        recs = vdiref.decode(b.memdump(r.results, n * vdiref.RESULT_WORDS * 2), n)
        err = compare(b, r.results, len(PRELUDE), PRELUDE, want)
        check(not err, f"the prelude: {err}")
        rec = recs[-1][2:]
        ret, nruns, lret, lrc, ncalls, bad = rec[6:12]
        total = len(d1.script) + m11 + len(d2.script)
        print(f"  sh_main returned {ret}: {nruns} run, last returned {lret}, "
              f"last load {lrc}; {ncalls} ABI calls, {bad} refused")
        check(ret == 3, f"sh_main returned {ret}, not the 3 programs run")
        check(nruns == 3, f"sh_runs {nruns}, not 3")
        check(lret == 0, f"the desktop's main() returned {lret}, not 0")
        check(lrc == 0, f"the last load's status {lrc}, not 0")
        check(ncalls == total,
              f"the three programs made {ncalls} ABI calls; the model counts {total} "
              f"= {len(d1.script)} + {m11} + {len(d2.script)}")
        # M11.G4A's one COP that is not gem4xe's (src/m11_cop.s), refused on
        # this OS and counted as refused only -- which is why ncalls above
        # does not include it.
        check(bad == 1, f"{bad} ABI calls refused, not M11.G4A's one foreign COP")

        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        brk2 = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"after:  pool ${mark2:04X}, {room2} free; far brk ${brk2:06X}")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; was ${mark:04X}, {room}")
        check(brk2 == brk + desk_len,
              f"far brk moved {brk2 - brk} bytes; the desktop's file is {desk_len}")
        lw = low_water(b)
        used, size = stk_hi + 1 - lw, stk_hi - stk_lo + 1
        print(f"stack:  {used} of {size} bytes used at the low-water mark (${lw:04X})")
        check(lw - stk_lo >= MARGIN,
              f"the stack came within {lw - stk_lo} bytes of its bottom ${stk_lo:04X}")
    finally:
        emu.stop()

    if not fails and not keep:
        for p in shots:
            os.remove(p)
    print(f"gem4xe-m18: {'PASS' if not fails else 'FAIL'} -- a program from the "
          f"desktop, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--model" in sys.argv:
        # a dry run on the host: the model alone, both desktops listed
        v, a, want, d1, d2, memo, m11 = model(0x4800, 0x020000, (0, 0), 0x03)
        for d, name in ((d1, "before"), (d2, "after")):
            print(f"-- the desktop {name}")
            deskref.describe(d)
            print(len(d.script), "calls; waits at", d.waits)
            for pw in d.wlist:
                print(f"  wnode root {pw.root} id {pw.id} cv {pw.cvrow} "
                      f"col {pw.pncol} row {pw.pnrow} vn {pw.vnrow} "
                      f"spec {pw.path.spec.s!r} count {pw.path.count} size {pw.path.size}")
        print(f"{PROGRAM}: {m11} calls; shots {len(a.shots)}; probes "
              f"{len(memo['globes'])}; shell buffer {a.sh_buf[:160]!r}")
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
