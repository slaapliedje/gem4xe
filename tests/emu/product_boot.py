#!/usr/bin/env python3
"""The product disks boot into the desktop, with nothing typed at all.

Two of them boot, and they come up the same way by different means:

  build/gem-boot.atr a double-density DOS 2 disk, the system named
                     AUTORUN.SYS because that is what the DOS runs at
                     boot, beside the DOS's own DUP.SYS, which is what
                     GEM returns to (tools/mkdisk.py --sweep, and
                     docs/shipping.md section 2);
  build/gem-sdx.atr  a double-sided double-density SDFS disk with NO DOS
                     on it (tools/mkfloppy.py): the one the release
                     carries, because the other boots a DOS that is not
                     gem4xe's to give away.  It boots under SpartaDOS X
                     from a cartridge (--sdx=CART, the fixture
                     [spartados].sdx_cart) or from Ultimate 1MB flash,
                     which reads its AUTOEXEC.BAT.  Without the fixture
                     its files are still checked; the boot is not.
  build/gem-apps.atr the applications and the desk accessory, with no DOS
                     and no AUTOEXEC.BAT: not a boot disk, so it is read
                     and not booted.

Each boot disk is the system and nothing else, since phase 42 took the
DOS 2 floppy under its floor of free sectors; the SDX one carries the
INSTALL.BAT that copies it onto a drive (tests/emu/install.py runs that).
A SpartaDOS 3.2 product floppy, gem-sp.atr, was retired after phase 42:
the installer is SpartaDOS X's.

This gate touches no key -- there is no b.key() in this file -- so what
comes up is what the disk itself started.  It runs the machine's real
sequence, which the Rapidus makes longer than it looks:

  1. the disk boots on the 6502 and the DOS starts GEM by itself, and
     the loader finds a Rapidus behind the 6502 it is running on and
     SWITCHES IT: COLDST ($0244) so that the restart is a cold one -- the
     switch resets the CPU, and the OS treats that reset as a warm start,
     which is exactly when a DOS does not run its start-up file -- then
     the PBI slot the card answers on, then the FPGA config register.
     The CPU resets mid-load and nothing below that write runs
     (src/farload.s, fl_no816);
  2. the machine comes up cold as a 65C816 and the DOS starts GEM again.
     Nothing is typed and nothing is poked: what this gate does to the
     machine after pressing power is NOTHING, which is the whole claim.
     On a machine with an Ultimate 1MB the question does not arise -- its
     Rapidus plugin sets the CPU over the M1 signal before the OS runs;
  3. this time GEM keeps the machine: first the boot screen on the OS's
     text screen -- the version, the processor, the memory, the DOS,
     which files it read, which screen, which clock, which pointer,
     which printer -- held for three seconds (src/sys/bootinfo.h), then
     the desk, its drive icons and the trash under the menu bar.

  The refusal itself -- a machine with no accelerator at all, told so and
  left alone -- is test-m6's, which boots the same image with the Rapidus
  taken out of the machine.

What is checked: the disk's own files, read out of the image; the CPU,
which must start as a 6502 and become a 65C816 with nothing driving it;
the boot screen, read off the text screen while it is held and compared
with what the machine then reports of itself -- the version in VERSION,
the memory the probe recorded, the DOS, the VBXE the fixture has, and
that LANG.RSC, which every product disk carries, and GEM4XE.CFG, which
the SpartaDOS X ones do, were the ones read;
the far image, spot checked against the linker's own output where a DOS
that mangles the staging would show (this gate found one that does -- MyDOS, section 2 of
docs/shipping.md); and the desk at the end, pixel for pixel against
tools/deskref.py, the desktop's own model run to its first wait.

Not checked here: G, the calls, the pool and the stacks.  GEM.COM has no
runner in it to answer a sys op, and the desktop's state is test-m17's
subject anyway; this gate is about the boot path.  The model is given the
pool base the linker gave the target (app_pool_lo, read out of the
machine) and the far heap's cursor as the target reports it, because the
model has to hand the desktop's Malloc a real address -- neither is on
the screen.

  python3 tests/emu/product_boot.py [--shot] [--sdx=CART] [NAME]
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vbxeref, symfile, atr, mkxex, mkcf  # noqa: E402
from deskref import Desktop                 # noqa: E402
from deskrsc import FILEMENU, QUITITEM      # noqa: E402
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m7_form import F                       # noqa: E402
from m14_sparta import screen               # noqa: E402
from langrsc import STRINGS as LANG, BOOT_LABEL  # noqa: E402  the boot screen's words
from m17_desktop import (header, listing, menu, rsc_imlen,  # noqa: E402
                         desk_places,
                         DESKTOP, DESK_RSC, DESK_SYM, SHOT)

BUILD = os.path.join(ROOT, "build")
SYMS = os.path.join(BUILD, "gem.sym")
ELF = os.path.join(BUILD, "gem.elf")
# two lines now: the system lives in \GEM\ on the install disk
BOOT_LINE = b"CD >GEM\x9bGEM\x9b"
COLDST = 0x0244                 # the OS: non-zero at RESET means come up cold
DRVBYT = 0x070A                 # DOS 2's drive map (src/sys/gemdos.c)
DOS_2 = 0                       # src/sys/dos.h
DOS_NAME = {0: "DOS 2", 1: "SpartaDOS 3", 2: "SpartaDOS X"}   # src/sys/bootinfo.c
FARMEM_FIRST, FARMEM_LAST, FARMEM_BANKS = 1, 2, 3   # FARMEM's bytes (src/sys/farmem.h)
BOOT_HOLD = 150                 # frames the screen is held on PAL (HOLD_SECONDS)
BOOT_WAIT = 3000                # frames from the CPU switch to give it to appear
BOOT_INK, BOOT_PAPER = "$00", "$0e"     # src/sys/bootinfo.c INK, PAPER, as HWSTATE prints them
REFUSAL = "gem4xe needs"        # src/farload.s msg_no816
FARMEM_BRK = 8                  # the cursor's offset in FARMEM (src/sys/farmem.h)
RAPIDUS_MCR_BEFORE = 1          # and in RAPIDUS (src/sys/rapidus.h): the MCR ...
RAPIDUS_CMCR_BEFORE = 5         # ... and the CMCR as the firmware left them
SEAM = 8                        # bytes checked either side of a chunk seam
STEP = 20                       # frames between screen reads while waiting for
                                # the refusal: see the poll in one()
HEAD = 64                       # and at the head of every chunk: where a DOS
                                # that loses part of one shows up

# (the image, what starts GEM on it, how it says so, the batch files an
# SDFS disk must carry, and whether it wants the SDX cartridge to boot)
PRODUCTS = [
    ("gem-boot.atr", "AUTORUN.SYS", "a double-density DOS 2, AUTORUN.SYS",
     (), False),
    ("gem-sdx.atr", "GEM.COM", "no DOS on the disk: SpartaDOS X from the "
     "cartridge, AUTOEXEC.BAT", ("AUTOEXEC.BAT",), True),
]


def desk_model(mark, brk, pointer, drvmap, dirs, dev=None, psystem=False):
    """The desktop against the model, up to its first wait: the same
    prelude and the same sh_main the desktop gates run (m17_desktop), and
    then one step producer, which photographs the desk and chooses
    File -> Quit so the model's session ends there.

    `dev` is the screen (tools/devref.py).  None is the VBXE, which is
    what these two product disks come up on; tests/emu/m26_fallback.py
    hands in an ANTIC one and gets the same desktop laid out for 320x168,
    which is the whole point of the seam."""
    v, a, _ = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark, dev=dev)
    v.close_virtuals()
    a.wm_init()
    a.mn_init()
    a.ratinit()
    a.gr_mouse(aesref.ARROW)   # the form is one global here (shel.c)
    a.tree = a.W_TREE
    a.draw(0, 0, (0, 0, a.gl_width, a.gl_height))
    pl = desk_places(brk)
    a.dos_brk = pl.pop("dos_brk")
    a.dos_dirs = dirs
    g_link = symfile.load(DESK_SYM)["G"]

    def first_wait(d):
        return [F(3), SHOT, *menu(d, FILEMENU, QUITITEM, False)[1:]]

    d = Desktop(v, a, mark, pl.pop("link_near"), pl.pop("near_size"),
                g_link, drvmap, [first_wait], **pl)
    a.psystem = psystem                 # the DOS's command processor, or not
    d.main()
    return v, a, d


def far_probes(far, chunk):
    """Where to read the far image back: the head of every chunk, and a
    few bytes either side of every seam.  The head is the part that
    matters -- a DOS that drops bytes out of a staged chunk drops them
    near its start, which is how MyDOS was caught."""
    want = set()
    for base, data in far:
        size = len(data)
        for dst, plain, _ in mkxex.far_chunks(base, data, chunk):
            want.update(a for a in range(dst, dst + HEAD) if a < base + size)
            for edge in (dst, dst + len(plain) - 1):
                want.update(a for a in range(edge - SEAM, edge + SEAM + 1)
                            if base <= a < base + size)
        want.add(base + size - 1)
    return sorted(want)


def far_byte(far, addr):
    for base, data in far:
        if base <= addr < base + len(data):
            return data[addr - base]
    return None


def dos2_listing(fs):
    """A DOS 2 root, in the shape the model wants.  Nothing in this gate
    opens a window, so the desktop never asks for it -- it is here so the
    model has an answer if it ever does."""
    return {"A:\\": [(e.filename.upper(), 0, 0, 0, e.count * fs.data_bytes)
                     for e in fs.entries() if e.in_use and e.nameable]}


def boot_screen(b):
    """The boot screen's report, as {label: value}, or None while the
    screen is not showing it.  The hint at the bottom says it is all
    there: the lines land one probe at a time (src/sys/bootinfo.c)."""
    words = dict(LANG)
    lines = screen(b)
    if not any(words["BOOT_HOLD"] in ln for ln in lines):
        return None
    # The rule says which column the block starts in: the screen puts it
    # INSET columns in, counting E:'s own left margin, so a DOS that has
    # moved LMARGN moves nothing here.  A label is BOOT_LABEL columns
    # and a gap; the value is the rest.
    col = next((ln.index("_") for ln in lines if "____" in ln), 2)
    labels = [words[k] for k in words if k.startswith("BOOT_")]
    report = {}
    for ln in lines:
        label = ln[col:col + BOOT_LABEL].strip()
        if label in labels:
            report[label] = ln[col + BOOT_LABEL + 1:].strip()
    return report


def check_boot(name, report, gtia, b, syms, check):
    """The report against the machine that wrote it; gtia is HWSTATE's
    reading of the colours, taken while the screen was held."""
    words = dict(LANG)
    L = lambda k: words["BOOT_" + k]        # noqa: E731
    with open(os.path.join(ROOT, "VERSION")) as f:
        version = f.read().strip()
    # the DOS 2 floppy carries no GEM4XE.CFG (phase 43): the boot screen
    # says the settings are the defaults, which is what the file says too
    cfg = L("DEFAULTS") if name == "gem-boot.atr" else "GEM4XE.CFG"
    for label, want in ((L("VERSION"), version),
                        (L("CPU"), "65C816, Rapidus"),
                        (L("CONFIG"), cfg),
                        (L("LANG"), "LANG.RSC"),
                        (L("VIDEO"), "VBXE 1.26 ($D640)")):
        check(report.get(label) == want,
              f"{name}: the boot screen says {label} '{report.get(label)}', "
              f"not '{want}'")
    # The vectors line: the regime irq_install() reached, the Rapidus
    # MCR/CMCR as the firmware left them, and which RAM under the ROM took
    # the copy (src/sys/bootinfo.c).  With the OS ROM in and window 3 slow
    # at boot, the ROM is copied under itself; Altirra's card always takes
    # the SRAM way (S), so anything else here is a change in the emulation.
    rap = syms["rapidus"]
    mcr, cmcr = b.peek(rap + RAPIDUS_MCR_BEFORE), b.peek(rap + RAPIDUS_CMCR_BEFORE)
    want = f"{L('IRQ_COPIED')} (${mcr:02X}/${cmcr:02X}/S)"
    check(report.get(L("IRQ")) == want,
          f"{name}: the boot screen says {L('IRQ')} '{report.get(L('IRQ'))}', "
          f"not '{want}'")
    kind = b.peek(syms["dos"])
    check(report.get(L("DOS")) == DOS_NAME[kind],
          f"{name}: the boot screen says DOS '{report.get(L('DOS'))}' on a "
          f"kind-{kind} DOS")
    fm = syms["farmem"]
    first, last, banks = (b.peek(fm + FARMEM_FIRST), b.peek(fm + FARMEM_LAST),
                          b.peek(fm + FARMEM_BANKS))
    tenths = (banks * 10 + 8) // 16
    want = f"{tenths // 10}.{tenths % 10} MB, {L('BANKS')} ${first:02X}-${last:02X}"
    check(report.get(L("MEMORY")) == want,
          f"{name}: the boot screen says memory '{report.get(L('MEMORY'))}', "
          f"the probe recorded '{want}'")
    for label in (L("CLOCK"), L("POINTER"), L("PRINTER")):
        check(bool(report.get(label)),
              f"{name}: the boot screen has no {label} line")
    # The colours, off GTIA itself while the screen was held: black ink
    # on white paper.  The XL OS's VBI copies COLOR1 to COLPF1 in its
    # first stage, before the CRITIC test, and every row is a CIO call
    # with that VBI live -- the first picture had DOS's grey ink ($CA)
    # for exactly that reason (src/sys/bootinfo.h).  Read then, not now:
    # boot_end puts DOS's colours back before the desktop starts.
    ink, paper = gtia["COLPF1"], gtia["COLPF2"]
    check((ink, paper) == (BOOT_INK, BOOT_PAPER),
          f"{name}: the boot screen's ink is {ink} on {paper}, not "
          f"{BOOT_INK} on {BOOT_PAPER} -- the OS's VBI put COLOR1 back?")


def one(name, progname, how, batches, cart, keep, check):
    disk = os.path.abspath(os.path.join(BUILD, name))
    syms = symfile.load(SYMS)
    segs, _ = mkxex.read_elf(ELF)
    far = sorted((a, d) for a, d in segs if a > 0xFFFF)
    chunk = symfile.load(SYMS)["_fl_end"] - symfile.load(SYMS)["_fl_buf"]

    # -- the disk, before anything boots it ---------------------------------
    img = atr.ATRImage.load(disk)
    fs = atr.open_fs(img)
    sdfs = isinstance(fs, atr.Sdfs)
    # The SpartaDOS product is an INSTALL disk: \GEM\ and \APPS\, the
    # same layout as the card, so that copying it onto an APT hard drive
    # is a directory copy.  What is listed here is therefore every file
    # in every directory, by the name it would be copied under.
    def walk(path=""):
        out = {}
        for e in fs.entries(path):
            here = (path + ">" if path else "") + e.filename.upper()
            if e.is_dir:
                out.update(walk(here))
            else:
                out[here] = e.size
        return out

    listed = (walk() if sdfs else
              {e.filename.upper(): None for e in fs.entries() if e.in_use})
    print(f"{name}: {img!r}, {how}")
    print(f"  {', '.join(sorted(listed))}")
    # Every product floppy is the system and nothing else since phase 42:
    # the applications and the desk accessory are on gem-apps.atr, which
    # apps_disk() reads (docs/media.md).
    want = ({"GEM>GEM.COM": "gem.xex", "GEM>DESKTOP.PRG": "desktop.g4a",
             "GEM>DESKTOP.RSC": "desktop.rsc", "GEM>LANG.RSC": "lang.rsc"} if sdfs else
            {progname: "gem.xex", "DESKTOP.PRG": "desktop.g4a",
             "DESKTOP.RSC": "desktop.rsc", "LANG.RSC": "lang.rsc"})
    strays = sorted(n for n in listed if n.startswith("APPS") or n.endswith(".ACC")
                    or (n.endswith(".G4A") and n not in want))
    check(not strays, f"{name}: carries {strays}, which belong on gem-apps.atr")
    for fname, built in want.items():
        check(fname in listed, f"{name}: {fname} is not on the disk")
        if sdfs and fname in listed:
            size = os.path.getsize(os.path.join(BUILD, built))
            check(listed[fname] == size,
                  f"{name}: {fname} is {listed[fname]} bytes, not build/{built}'s {size}")
    if sdfs:
        for batch in batches:
            check(batch in listed, f"{name}: {batch} is not on the disk")
            if batch in listed:
                check(fs.read(batch) == BOOT_LINE,
                      f"{name}: {batch} holds {fs.read(batch)!r}, not {BOOT_LINE!r}")
        # ...and the installer: what this disk holds, onto a drive the user
        # names (tools/mkcf.py; tests/emu/install.py runs it).
        check("INSTALL.BAT" in listed
              and fs.read("INSTALL.BAT") == mkcf.batch(mkcf.INSTALL_SYSTEM),
              f"{name}: INSTALL.BAT is not tools/mkcf.py's INSTALL_SYSTEM")
        check("APPS" not in {e.filename.upper() for e in fs.entries("")},
              f"{name}: has an \\APPS\\, which belongs on gem-apps.atr")
        # The release floppy carries no DOS: its superblock names no boot
        # file and its boot sectors are the blank disk's stub.  A DOS on
        # it would be somebody else's (tools/mkfloppy.py).
        if cart is not None:
            check(fs.boot_file_map == 0,
                  f"{name}: the superblock names a DOS file at map sector "
                  f"{fs.boot_file_map}, and this disk is meant to carry none")
    else:
        # DUP.SYS is on the disk (Makefile, build/gem-boot.atr): it is the
        # DOS's shell, and what GEM hands the machine back to.  It went,
        # for a while, when the system outgrew the disk with the shell on
        # it -- docs/shipping.md section 2 -- and came back when the far
        # image started travelling packed (tools/mkxex.py), which took a
        # third off GEM.COM.  Without it this DOS has nothing to return
        # to, so its absence is a regression and not a saving.
        check("DUP.SYS" in listed,
              f"{name}: DUP.SYS is not on the disk -- GEM has no shell to "
              f"return to")
        free = fs.free_count() * fs.data_bytes
        print(f"  {fs.free_count()} sectors free, {free // 1024} KB")
        # THE FLOOR, AND WHAT IT IS NOW FOR.  It used to keep room "for a
        # program of the user's own" and came down three times under that
        # banner -- 80, then 72 when File -> DOS command arrived, then 64
        # when wind_get(WF_OWNER) was put right (docs/shipping.md section
        # 1 has the history).  The fourth time, on 2026-09-19, the ten
        # remaining AES opcodes took it to 52 and the reason was read
        # again instead of the number being lowered again.
        #
        # THE REASON WAS STALE.  A DOS 2 cannot read gem-apps.atr, so
        # nobody puts a program on this disk -- the Makefile already calls
        # it "a gate's more than anybody's way in", and shipping.md
        # already argues the same thing at length.  The way in is the
        # INSTALLER: both floppies carry INSTALL.BAT, SpartaDOS X copies
        # them onto a drive and the machine boots from that (test-install,
        # docs/media.md).  So the floor was guarding a use the project had
        # already written off.
        #
        # WHAT IT GUARDS NOW is the one thing a person really can write to
        # this disk: DESKTOP.INF, when they arrange the desktop and choose
        # Options -> Save desktop.  Its size is bounded, not guessed --
        # inf_write builds it in the shell buffer (src/desk/deskwin.c) and
        # SIZE_SHELBUF is 4192 bytes, which is 17 sectors of 253, plus one
        # for the directory entry.  TWENTY, with the rest of the margin
        # given back, because a number with a reason stops being a
        # conversation every two hundred bytes.
        INF_SECTORS = 20
        check(fs.free_count() >= INF_SECTORS,
              f"{name}: {fs.free_count()} sectors free -- under the floor of "
              f"{INF_SECTORS}, which is the most DESKTOP.INF can take "
              f"(SIZE_SHELBUF 4192) and a directory entry")

    if cart == "":
        print(f"  not booted: no SDX cartridge fixture ([spartados].sdx_cart "
              f"in fixtures.toml), and this disk carries no DOS of its own")
        return
    emu = launch(tag="product", memsize="1088K",
                 extra_args=["--disk", disk] + (["--cart", cart] if cart else []))
    b = emu.bridge
    shot = os.path.join(SHOTDIR, f"product-{name.split('.')[0]}.png")
    try:
        # -- 1. and 2. the machine switches itself ---------------------------
        # Nothing is typed and nothing is poked.  The disk boots on the
        # 6502, the DOS starts GEM, and the loader finds a Rapidus behind
        # the 6502 it is running on and switches it (src/farload.s
        # fl_no816): COLDST so the restart is a cold one -- a DOS does not
        # run its start-up file on a warm start -- then the PBI slot and
        # the FPGA config register.  The CPU resets mid-load, the machine
        # comes up as a 65C816, and the DOS starts GEM again.
        #
        # What says it happened: the CPU.  The screen is a poor witness
        # here, because both passes look the same until the desk appears.
        # And the first look is taken from a cold reset: the machine runs
        # free until the bridge connects, 50 to 100 frames on the phase
        # of a 300 ms poll, and the switch comes about 100 frames in --
        # test-m26 went red on exactly that in the 10 September audit.
        b.ok("COLD_RESET")
        was = b.cmd("HWSTATE").get("cpu", {}).get("mode")
        check(was == "6502", f"{name}: the machine did not start as a 6502 "
                             f"(it is {was})")
        for t in range(0, 20000, STEP):
            b.frames(STEP)
            if b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502":
                break
        else:
            check(False, f"{name}: the loader never switched the CPU")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return
        mode = b.cmd("HWSTATE").get("cpu", {}).get("mode")
        print(f"  the loader switched the machine to {mode} by itself, "
              f"{t + STEP} frames in, with nothing typed")

        # -- 3. the boot screen, while it is held ---------------------------
        # Three seconds is 150 frames and the poll is 20, so it cannot be
        # missed; what is read is the whole report, because the hint is
        # the last thing written.  The picture is kept beside the desk's.
        gtia = {}
        for t in range(0, BOOT_WAIT, STEP):
            b.frames(STEP)
            report = boot_screen(b)
            if report:
                gtia = b.cmd("HWSTATE")["gtia"]       # while it is held
                break
        else:
            check(False, f"{name}: the boot screen never showed its hint")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            report = {}
        if report:
            print(f"  the boot screen, {t + STEP} frames after the switch:")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            os.makedirs(SHOTDIR, exist_ok=True)
            b.screenshot(os.path.join(SHOTDIR, f"boot-{name.split('.')[0]}.png"))

        # -- 4. the desktop, and the model it must match --------------------
        calls = syms["app_calls"]
        n, still = b.peek16(calls), 0
        for t in range(0, 20000, 250):
            b.frames(250)
            now = b.peek16(calls)
            still = still + 1 if now == n else 0
            n = now
            if still >= 2 and now:
                break
        else:
            check(False, f"{name}: GEM never settled ({n} calls)")
        print(f"  GEM settled after {t + 250} frames, {n} calls in")
        fault = b.peek(syms["irq_fault"])
        check(fault == 0, f"{name}: irq_fault {fault} (src/sys/irq.s)")
        check(not any(REFUSAL in ln for ln in screen(b)),
              f"{name}: GEM refused the 65C816 as well: the switch did not take")
        if report:
            check_boot(name, report, gtia, b, syms, check)

        # the far image, as the linker wrote it
        bad = []
        for a in far_probes(far, chunk):
            if b.cmd(f"EVAL db(${a:06x})").get("value") != far_byte(far, a):
                bad.append(a)
        check(not bad, f"{name}: the far image differs at {len(bad)} probed byte(s), "
                       f"first ${bad[0]:06X}" if bad else "")
        print(f"  the far image: {len(far_probes(far, chunk))} bytes probed, "
              f"{'all as the linker wrote them' if not bad else str(len(bad)) + ' wrong'}")

        kind = b.peek(syms["dos"])          # DOS_INFO.kind (src/sys/dos.h)
        drvmap = 0x03 if kind != DOS_2 else (b.peek(DRVBYT) or 1)
        # Where the DESKTOP's near region actually is, not where the pool
        # starts: an accessory is loaded before the first program and sits
        # below it (docs/phase36.md), so app_pool_lo stopped being the
        # answer the moment the product shipped one.
        mark = b.peek16(syms["app_near"])
        brk = int.from_bytes(bytes(b.memdump(syms["farmem"] + FARMEM_BRK, 4)), "little")
        pointer = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        # What the pool has left with everything the product ships
        # resident.  GEMDOS reads files and directories through a slice
        # of it, capped at 2 KB and falling back to sixty-four bytes of
        # stack below 128 (src/sys/gemdos.c), so this is the difference
        # between a desktop that lists a directory briskly and one that
        # does not -- and nothing else would fail if it went.
        # tools/memreport.py predicts the same figure from the build
        # artefacts; this is the machine agreeing with it.
        room = (b.peek16(syms["app_pool_hi"])
                - b.peek16(syms["pool_brk"])) & 0xFFFF
        check(room >= 2048,
              f"{name}: the pool has {room} bytes left, and GEMDOS wants "
              f"2,048 for a read slice")
        # The floor the shell marked once everything permanent was taken:
        # the accessories, their queues and resources, the process
        # records, the shell's own buffers (src/aes/shel.c).
        floor = b.peek16(syms["pool_low"])
        print(f"  the pool has {room} bytes left for GEMDOS's slices; "
              f"permanent up to ${floor:04X}")
        # Nothing should ever have tried to free below what the shell
        # marked permanent -- the accessories, the process records, the
        # shell's own buffers (src/sys/app.c).  A refusal here is a
        # lifetime bug that would otherwise be somebody's memory quietly
        # going away.
        check(b.peek16(syms["pool_refused"]) == 0,
              f"{name}: {b.peek16(syms['pool_refused'])} pool release(s) "
              f"refused -- something tried to free what is permanent")
        check(b.peek16(syms["far_refused"]) == 0,
              f"{name}: {b.peek16(syms['far_refused'])} far release(s) "
              f"refused")
        print(f"  DOS kind {kind}, drive map {drvmap:#04x}, pool ${mark:04X}, "
              f"far brk ${brk:06X}, pointer {pointer}")
        dirs = listing(disk) if sdfs else dos2_listing(fs)
        # File -> DOS command is greyed unless the DOS is a SpartaDOS X of
        # 4.4 or later whose jfsymbol is in place (src/sys/dos.c dos_command)
        psystem = kind == 2 and b.peek(0x0701) >= 0x44 and b.peek(0x07EB) == 0x4C
        ref_v, ref_a, d = desk_model(mark, brk, pointer, drvmap, dirs,
                                     psystem=psystem)
        print(f"  the model's desktop: {len(d.script)} calls to its first wait "
              f"at {d.waits[0]}, near ${d.near:04X}, G ${d.G:04X}")
        check(len(ref_a.shots) == 1, f"{name}: the model took {len(ref_a.shots)} shots")
        # The ABI's counter is the desktop's own: the shell and the AES do
        # not reach the machine through it, so the calls the target has
        # made are the calls the model's script has, and the wait it is
        # sitting in is the model's first (m17_desktop's read()).
        check((n - 1) & 0xFFFF == d.waits[0],
              f"{name}: the desktop is in call {(n - 1) & 0xFFFF}, not its first "
              f"wait {d.waits[0]}")

        b.screenshot(shot)
        bad_px, shown = vbxeref.compare_to_shot(ref_a.shots[0], shot)
        check(not bad_px, f"{name}: the desk, {bad_px} px differ from the model; "
                          f"first {shown[:3]}")
        print(f"  the desk {'ok' if not bad_px else 'FAIL'} against the model "
              f"({shot if bad_px or keep else 'not kept'})")
        if not bad_px and not keep:
            os.remove(shot)
    finally:
        emu.stop()


def apps_disk(check):
    """gem-apps.atr, read and not booted, because it is not a boot disk:
    every file of tools/mkcf.py's APPS table in its directory, byte for
    byte and nothing else, its own INSTALL.BAT, no AUTOEXEC.BAT and no
    DOS."""
    name = "gem-apps.atr"
    img = atr.ATRImage.load(os.path.join(BUILD, name))
    fs = atr.open_fs(img)
    print(f"{name}: {img!r}, the applications -- read, not booted")
    on_disk = set()
    for d in mkcf.DIRS:
        on_disk.update(f"{d}>{e.filename.upper()}" for e in fs.entries(d))
    want = {n for _p, n in mkcf.APPS}
    check(on_disk == want, f"{name}: holds {sorted(on_disk)}, not {sorted(want)}")
    for path, fname in mkcf.APPS:
        if fname in on_disk:
            with open(os.path.join(BUILD, os.path.basename(path)), "rb") as f:
                check(fs.read(fname) == f.read(),
                      f"{name}: {fname} is not {path}")
    root = {e.filename.upper() for e in fs.entries("")}
    check(root == set(mkcf.DIRS) | {"INSTALL.BAT"},
          f"{name}: its root holds {sorted(root)}")
    if "INSTALL.BAT" in root:
        check(fs.read("INSTALL.BAT") == mkcf.batch(mkcf.INSTALL_APPS),
              f"{name}: INSTALL.BAT is not tools/mkcf.py's INSTALL_APPS")
    check(fs.boot_file_map == 0, f"{name}: the superblock names a DOS file")
    print(f"  {', '.join(sorted(on_disk | root))}")


def main(argv):
    keep = "--shot" in argv
    only = [a for a in argv if not a.startswith("--")]
    # --sdx=CART, and `--sdx=` with nothing after it is what the Makefile
    # passes when fixtures.toml names no cartridge: the floppy that needs
    # one is then read but not booted, and says so.
    sdx = next((a[6:] for a in argv if a.startswith("--sdx=")), "")
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    os.makedirs(SHOTDIR, exist_ok=True)
    for name, progname, how, batches, wants_cart in PRODUCTS:
        if only and not any(o in name for o in only):
            continue
        one(name, progname, how, batches, sdx if wants_cart else None,
            keep, check)
    if not only or any("apps" in o for o in only):
        apps_disk(check)
    print(f"{'FAIL' if fails else 'PASS'}: the product disks boot into the "
          f"desktop with nothing typed -- the loader switches the CPU "
          f"itself, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
