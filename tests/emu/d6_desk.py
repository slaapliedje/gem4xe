#!/usr/bin/env python3
"""d6_desk.py -- make test-d6: the desktop on a stock 6502 (docs/6502.md,
step 5c-3).

src/desk/*.c, the 65C816's desktop, built for the 6502 through gem.h's far
accessors (step 5c-2) as a program of eight banks (tools/bsp6502/rules.mk,
build/desk6.g6a) on its own disk in D2:, which A6 loads when $060C is 2 at
the go -- closing its own test windows first -- beside its resources on
D1:.  The gate holds it to:

  - the load: CIO's status 1, eight banks from the far heap, its first
    turn over ($060C 'R'), nothing stopped at $0604, no call refused;
  - the desk is the desktop's: the input owner is its process once it has
    put its desk up (src/aes/wind.c, WF_NEWDESK), not A6's;
  - a double-click on DISK D1: opens a window on it: its title " D1:\\*.* "
    and its information line in the desktop's own memory, under the ROM,
    with the count and the bytes of D1:'s files -- worked out here from
    the disk image itself, by GEMDOS's rule for a DOS 2 directory, its
    sectors times 125 -- which says the listing went through Fsfirst and
    Fsnext into the far DTA and the FNODEs and was counted from there;
  - a desktop that does not load is read again until it does (D2: empty
    at the go, then the disk put in), and an application that does not
    load gives way to the desktop;
  - the pointer is the arrow once the Control Panel is up: the VDI's form
    (vdi.c's cur_xhot, cur_yhot, cur_data), not the hourglass the desktop
    put up to start it, which stayed over the panel on the 600XL.

With --vbxe (make test-d6v, docs/6502.md step 6) the machine has a VBXE,
which A6 takes as its screen: the same desktop at 640x240 in colour, the
same steps and checks, clicked where that screen puts things (VBXE_AT).

With --axlon SIZE (make test-d6a) the machine is a 64K XL with an Axlon
of SIZE and no PORTB banks -- a 600XL with a SUBCart, which the desktop
never reached until the Axlon's switches put the ROM in for themselves
(ax_sw, src/sys6502/bank6502.s): the same steps on the Axlon's banks.

    python3 tests/emu/d6_desk.py [--vbxe | --axlon 4096K] [--shot]
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
from atr import ATRImage, Dos2              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6d-boot.atr"))
DESK = os.path.abspath(os.path.join(ROOT, "build", "a6d-desk.atr"))
MAP = os.path.abspath(os.path.join(ROOT, "build", "a6.map"))
DMAP = os.path.abspath(os.path.join(ROOT, "build", "desk6.map"))
CMAP = os.path.abspath(os.path.join(ROOT, "build", "cpanel6.map"))
SHOT = os.path.abspath(os.path.join(ROOT, "build", "d6.png"))
STATUS = 0x0600
SHARED = (0xD800, 0x2600)           # a program's RAM under the ROM
D1_ICON = (34, 28)                  # DISK D1:, the desk's first cell
D1_CLOSE = (17, 43)                 # D1:'s window's close box
AUTORUN = (56, 71)                  # AUTORUN.SYS, first in D1:'s window
SHOW = (102, 120)                   # the document alert's Show
VIEW_CLOSE = (17, 19)               # the viewer's close box
VIEW_LEN = 16384 - (64 + 4 + 48)    # deskcmd.c: CMD_BUF - CMD_TEXT
D2_ICON = (114, 28)                 # DISK D2:, the second
D2_FULL = (240, 42)                 # its window's full box, where it opens
P6M_ICON = (196, 100)               # P6M.G6A, seventh in the full window
CPANEL_ICON = (114, 46)             # CPANEL.G6A, second
GENERAL = (96, 56)                  # the panel's first slot: General
GENERAL_OK = (116, 133)             # its form's OK
PANEL_CLOSE = (67, 23)              # the panel window's closer
NBANKS = 8
# ...and where the VBXE's 640x240 screen with its 8x8 cell puts them,
# found from its screenshots (the trash and the desk's cells move with
# the cell; the windows open where the desktop lays them out)
VBXE_AT = dict(
    D1_ICON=(48, 30), D1_CLOSE=(24, 52), AUTORUN=(69, 90), SHOW=(244, 144),
    VIEW_CLOSE=(20, 20), D2_ICON=(154, 30), D2_FULL=(314, 52), P6M_ICON=(54, 92),
    CPANEL_ICON=(154, 50), GENERAL=(240, 76), GENERAL_OK=(274, 189), PANEL_CLOSE=(196, 44),
)


class NoDesktop(Exception):
    """The desktop did not start: the rest is not worth waiting for."""


def main(argv):
    keep = "--shot" in argv
    vbxe = "--vbxe" in argv
    axlon = argv[argv.index("--axlon") + 1] if "--axlon" in argv else None
    if vbxe:
        globals().update(VBXE_AT)
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    what = "on a stock 6502" + (" with a VBXE" if vbxe else "") \
        + (f" (64K) with an Axlon of {axlon}" if axlon else "")
    print(f"gem4xe-d6: the desktop {what}, and a program from it")
    text = open(MAP).read()

    def sym(n, t=None):
        return int(re.search(rf"^\s+{n} = ([0-9a-f]+)\s*$", t or text, re.M).group(1), 16)

    def static(n):                      # a file's static: placed, not listed
        return int(re.search(rf"^{n} in section 'zdata'  placed at address "
                             rf"([0-9a-f]+)-", text, re.M).group(1), 16)
    ARROW_DATA1 = 0x4000                # tools/gemdata.py: ARROW's second row
    dtext = open(DMAP).read()
    ctext = open(CMAP).read()

    d1 = [e for e in Dos2(ATRImage.load(DISK)).entries() if e.in_use and e.nameable]
    want_info = f" {sum(e.count for e in d1) * 125} bytes used in {len(d1)} items.".encode()

    if axlon:       # a launch at another size boots no --disk: the bridge does
        emu = launch(tag="d6a", memsize="64K", vbxe=False, rapidus=False,
                     extra_args=["--axlonmemsize", axlon])
        emu.bridge.boot(DISK)
    else:
        emu = launch(tag="d6v" if vbxe else "d6", memsize="1088K", vbxe=vbxe,
                     rapidus=False, extra_args=["--disk", DISK])
    b = emu.bridge

    def w16(a):
        return b.peek(a) | (b.peek(a + 1) << 8)

    def poke16(a, v):
        b.poke(a, v & 0xFF)
        b.poke(a + 1, (v >> 8) & 0xFF)

    def rom_out():
        """The RAM under the ROM reads as RAM only with the ROM out: the
        system switches it in for CIO and an interrupt, and a read then
        is the ROM's bytes (docs/6502.md, 5c-1).  Between frames until
        PORTB says it is out."""
        for _ in range(50):
            if not b.peek(0xD301) & 1:
                return
            b.frames(1)

    def shared():
        rom_out()
        return bytes(b.memdump(*SHARED))

    def dw16(n):                        # a desktop variable, under the ROM
        rom_out()
        return w16(sym(n, dtext))

    def cw16(n):                        # the control panel's
        rom_out()
        return w16(sym(n, ctext))
    try:
        b.frames(500)
        for _ in range(0, 9000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        b.poke(STATUS + 12, 2)              # the desktop, at the go
        b.poke(STATUS + 6, 1)
        # A DESKTOP THAT DOES NOT LOAD IS READ AGAIN (src/a6_evt.c,
        # host_run): D2: is empty at the go, so the desktop's first reads
        # fail -- on MiSTer's drive one failed now and then, and A6 used
        # to wait on nothing with the hourglass up -- and A6 must go on
        # trying, a second apart, until the disk is in
        for _ in range(100):
            b.frames(100)
            if b.peek(STATUS + 0x3E) >= 3:
                break
        tries, why = b.peek(STATUS + 0x3E), b.peek(STATUS + 13)
        slot = b.peek(STATUS + 12)
        check(tries >= 3 and slot == ord("H") and why != 1,
              f"no desktop disk: A6 reads again, {tries} tries, the last "
              f"'{chr(slot) if slot > 31 else slot}' with CIO {why}; want 3 or more, 'H'")
        b.mount(1, DESK)
        for _ in range(100):
            b.frames(100)
            if b.peek(STATUS + 12) == ord("R"):
                break
        b.frames(3000)

        stuck = b.peek(STATUS + 4)
        check(not stuck, f"nothing stopped at $0604 ({chr(stuck) if stuck else 'none'})")
        if axlon:
            check(b.peek(sym("b6_kind")) == ord("A") and b.peek(sym("b6_count")) == 255,
                  f"on the Axlon's banks: kind {chr(b.peek(sym('b6_kind')))!r}, "
                  f"{b.peek(sym('b6_count'))} banks, want 'A', 255")
        scr = chr(b.peek(STATUS + 5) or 32)
        check(scr == ("V" if vbxe else "A"), f"the screen A6 chose is {scr!r} at $0605 "
                                            f"(V the VBXE, A ANTIC)")
        rd, slot, nb = b.peek(STATUS + 13), b.peek(STATUS + 12), b.peek(sym("p6_nbanks"))
        if not check(rd == 1 and nb == NBANKS and slot == ord("R"),
                     f"it was read (CIO {rd}) into {nb} banks and its first turn ended "
                     f"({chr(slot) if slot > 31 else slot}); want 1, {NBANKS}, 'R'"):
            raise NoDesktop                 # every step after needs it
        pin, ptab = w16(sym("proc_input")), w16(sym("proc_tab"))
        check(pin != ptab, f"the input owner is the desktop's process (${pin:04X}), not "
                           f"A6's (${ptab:04X})")

        ptr = sym("ptr_state")
        poke16(ptr + 6, 0)                  # PTR_NONE: the gate moves it
        poke16(ptr, D1_ICON[0])
        poke16(ptr + 2, D1_ICON[1])
        b.frames(20)
        for v in (1, 0, 1, 0):              # a double click
            poke16(ptr + 4, v)
            b.frames(4)
        b.frames(5000)

        ram = shared()
        check(b" D1:\\*.* " in ram, "a window titled \" D1:\\*.* \" in the desktop's memory")
        found = re.search(rb" \d+ bytes used in \d+ items\.", ram)
        got = found.group(0) if found else None
        check(got == want_info, f"its information line {got!r}; D1:'s {len(d1)} files make "
                                f"{want_info!r}")

        # THE VIEWER (deskcmd.c): a document's Show reads it into a 16 KB
        # far block and shows it in a window of its own -- its variables
        # landed on the system's zero page until 5d (TINY)
        def click0(xy, n=1):
            poke16(ptr, xy[0])
            poke16(ptr + 2, xy[1])
            b.frames(20)
            for _ in range(n):
                poke16(ptr + 4, 1)
                b.frames(4)
                poke16(ptr + 4, 0)
                b.frames(4)
        click0(AUTORUN, 2)
        b.frames(4000)
        click0(SHOW)
        for _ in range(100):
            b.frames(100)
            if dw16("cmd_id") and dw16("cmd_len") == VIEW_LEN:
                break
        vid, vlen, vlines = dw16("cmd_id"), dw16("cmd_len"), dw16("cmd_lines")
        check(vid > 0 and vlen == VIEW_LEN and vlines > 0,
              f"Show on AUTORUN.SYS: the viewer is window {vid} with {vlen} bytes of it in "
              f"{vlines} lines; want a window, {VIEW_LEN} bytes (all the buffer takes)")
        b.frames(3000)                      # its window drawn before it closes
        click0(VIEW_CLOSE)
        b.frames(3000)
        # A PROGRAM FROM THE DESKTOP (step 5d): D2:'s window, full, and a
        # double-click on P6M.G6A -- the desktop asks for it (shel_write)
        # and ends; A6's shell runs it; when it ends, the desktop again
        def click(xy, n=1, wait=0):
            poke16(ptr, xy[0])
            poke16(ptr + 2, xy[1])
            b.frames(20)
            for _ in range(n):
                poke16(ptr + 4, 1)
                b.frames(4)
                poke16(ptr + 4, 0)
                b.frames(4)
            b.frames(wait)
        starts0 = b.peek(STATUS + 0x3E)
        click(D1_CLOSE, 1, 3000)            # D2:'s then opens where D1:'s was
        click(D2_ICON, 2, 5000)
        click(D2_FULL, 1, 0)
        for _ in range(100):                # polled: the redraw's pace varies
            b.frames(100)
            ram = shared()
            if b"P6M.G6A" in ram and b"P6PROG.G6A" in ram:
                break
        b.frames(500)
        check(b"P6M.G6A" in ram and b"P6PROG.G6A" in ram,
              "D2:'s window lists P6M.G6A and P6PROG.G6A by name")
        b.poke(STATUS + 0x40, 0)
        b.poke(STATUS + 0x62, 0)
        click(P6M_ICON, 2, 0)
        for _ in range(120):
            b.frames(50)
            if b.peek(STATUS + 0x40) == ord("a"):
                break
        starts1 = b.peek(STATUS + 0x3E)
        check(b.peek(STATUS + 0x40) == ord("a") and starts1 == starts0 + 1,
              f"P6M.G6A ran from the desktop: at its alert (stage "
              f"{chr(b.peek(STATUS + 0x40)) if b.peek(STATUS + 0x40) > 31 else 0}), "
              f"programs started {starts0} -> {starts1}")
        check((w16(STATUS + 0x42), w16(STATUS + 0x44)) == (26, 55),
              f"...and did its sums across its banks ({w16(STATUS + 0x42)}, "
              f"{w16(STATUS + 0x44)}; want 26, 55)")
        b.poke(STATUS + 0x62, 1)
        b.frames(300)
        b.key("RETURN")
        for _ in range(120):
            b.frames(50)
            if b.peek(STATUS + 0x3E) == starts1 + 1:
                break
        b.frames(3000)
        starts2 = b.peek(STATUS + 0x3E)
        check(b.peek(STATUS + 0x40) == ord("E") and starts2 == starts1 + 1
              and b.peek(STATUS + 13) == 1,
              f"it ended (stage {chr(b.peek(STATUS + 0x40)) if b.peek(STATUS + 0x40) > 31 else 0})"
              f" and the desktop was started again ({starts1} -> {starts2}, CIO "
              f"{b.peek(STATUS + 13)})")
        for _ in range(100):                # polled, as above
            ram = shared()
            if b"DISK D1:" in ram:
                break
            b.frames(100)
        check(b"DISK D1:" in ram, "the desktop again built its desk: \"DISK D1:\" in its "
                                  "memory (its resource found, on D1: again)")
        pin = w16(sym("proc_input"))
        check(pin != ptab and b.peek(sym("p6_nbanks")) == NBANKS,
              f"the desktop again: {b.peek(sym('p6_nbanks'))} banks, the input its own "
              f"(${pin:04X})")
        # THE CONTROL PANEL (step 5f): CPANEL.G6A from D2:'s window, which
        # the desktop restored -- General and Color built in -- General
        # opened and OK'd (its settings saved, as a plain file here), and
        # the panel closed: the desktop again
        # D2:'s window comes back with the desktop, read from the disk
        # again; clicked before it is, the double-click met an empty desk
        # (one run in three, the panel never started)
        for _ in range(100):
            ram = shared()
            if b"CPANEL.G6A" in ram and re.search(rb" bytes used in 8 items\.", ram):
                break
            b.frames(100)
        b.frames(500)
        check(b"CPANEL.G6A" in ram, "D2:'s window is back, listing CPANEL.G6A")
        starts3 = b.peek(STATUS + 0x3E)
        click(CPANEL_ICON, 2, 0)
        # ONCE MORE if it only selected the icon: on the VBXE the 6502
        # draws the selection slowly enough that the second press can come
        # while the desktop is still at it, and is one more click, not a
        # double one (a person clicks again too)
        for _ in range(30):
            b.frames(100)
            if b.peek(STATUS + 0x3E) == starts3 + 1:
                break
        else:
            click(CPANEL_ICON, 2, 0)
        for _ in range(150):
            b.frames(100)
            if b.peek(STATUS + 0x3E) == starts3 + 1 and cw16("cp6_runs") == 1:
                break
        b.frames(2000)
        runs, rows = cw16("cp6_runs"), cw16("cp_rows")
        check(b.peek(STATUS + 0x3E) == starts3 + 1 and runs == 1 and rows == 2,
              f"CPANEL.G6A ran from the desktop: its window up ({runs}), listing {rows} "
              f"modules; want 1, 2 (General, Color)")
        # THE ARROW OVER IT (a6_evt.c, prog_start): the hot spot and the
        # second row of the form the VDI has, ARROW's (0, 0) and $4000 --
        # the HOURGLASS's are (8, 8) and $7FFE
        hot = (w16(static("cur_xhot")), w16(static("cur_yhot")))
        row1 = w16(static("cur_data") + 2)
        check(hot == (0, 0) and row1 == ARROW_DATA1,
              f"the pointer over the panel is the arrow: hot spot {hot}, row 1 "
              f"${row1:04X}; want (0, 0), ${ARROW_DATA1:04X} (the hourglass: (8, 8), $7FFE)")
        # SELECTED, THEN RETURN, not a double-click: a press that lands
        # while the panel is between its waits -- its clock's tick, every
        # second -- is counted as one click, as GEM counts it, and one run
        # in a suite's worth opened nothing.  The keyboard has no window.
        click(GENERAL, 1, 1000)
        b.key("RETURN")
        for _ in range(100):
            b.frames(100)
            if cw16("cp_opens") == 1:
                break
        b.frames(3000)
        check(cw16("cp_opens") == 1, f"General, selected, opened with Return "
                                     f"(cp_opens {cw16('cp_opens')})")
        click(GENERAL_OK, 1, 4000)
        click(PANEL_CLOSE, 1, 0)
        for _ in range(150):
            b.frames(100)
            if b.peek(STATUS + 0x3E) == starts3 + 2:
                break
        for _ in range(100):
            ram = shared()
            if b"DISK D1:" in ram:
                break
            b.frames(100)
        check(b.peek(STATUS + 0x3E) == starts3 + 2 and b"DISK D1:" in ram,
              f"the panel closed and the desktop came back "
              f"({starts3} -> {b.peek(STATUS + 0x3E)} programs started)")
        # General's OK saved its settings: GENERAL.CFG beside the panel on
        # D2:, which the desktop's window, read again as it came back,
        # counts -- eight files on the disk, and now a ninth
        info = None
        for _ in range(100):
            m = re.search(rb" \d+ bytes used in (\d+) items\.", shared())
            if m and m.group(1) == b"9":
                info = m.group(0)
                break
            b.frames(100)
        check(info is not None, f"General's settings were saved: D2:'s window counts 9 "
                                f"items, GENERAL.CFG among them ({info!r})")
        # AN APPLICATION THAT DOES NOT LOAD GIVES WAY TO THE DESKTOP
        # (host_run), as on the 65C816: the panel once more, and while it
        # is up A6's next program is named as one D2: does not have.  When
        # the panel ends, that load must fail and the desktop come back.
        starts4 = b.peek(STATUS + 0x3E)
        b.frames(3000)                      # the window's redraw over first
        for _ in range(3):                  # a press while it is busy is lost
            click(CPANEL_ICON, 2, 0)
            for _ in range(30):
                b.frames(100)
                if b.peek(STATUS + 0x3E) == starts4 + 1:
                    break
            if b.peek(STATUS + 0x3E) == starts4 + 1:
                break
        check(b.peek(STATUS + 0x3E) == starts4 + 1,
              f"CPANEL.G6A ran again ({starts4} -> {b.peek(STATUS + 0x3E)} programs started)")
        b.frames(4000)                      # its window up
        for i, c in enumerate(b"D2:NOSUCH.G6A\0"):
            b.poke(sym("g6_run") + i, c)
        click(PANEL_CLOSE, 1, 0)
        for _ in range(100):
            b.frames(100)
            if b.peek(STATUS + 0x3E) >= starts4 + 3 and b.peek(STATUS + 12) == ord("R"):
                break
        for _ in range(100):
            ram = shared()
            if b"DISK D1:" in ram:
                break
            b.frames(100)
        got = b.peek(STATUS + 0x3E) - starts4
        check(got == 3 and b.peek(STATUS + 12) == ord("R") and b.peek(STATUS + 13) == 1
              and b"DISK D1:" in ram,
              f"a program that is not there: the desktop instead ({got} starts after the "
              f"panel's, want 3: the panel, the missing one, the desktop; "
              f"'{chr(b.peek(STATUS + 12))}', CIO {b.peek(STATUS + 13)})")
        bad, op = w16(sym("gem_bad")), w16(sym("gem_badop"))
        check(bad == 0, f"no call refused (gem_bad {bad}, last opcode {op:#x})")
        b.screenshot(SHOT)
    except NoDesktop:
        b.screenshot(SHOT)
    finally:
        emu.stop()
    if not fails and not keep and os.path.exists(SHOT):
        os.remove(SHOT)
    print(f"gem4xe-d6: {'PASS' if not fails else 'FAIL'} -- the desktop {what}, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
