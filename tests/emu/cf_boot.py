#!/usr/bin/env python3
"""The product CF card boots into the desktop, on the machine this
project is for: an Ultimate 1MB with SpartaDOS X and the PBI BIOS in its
flash, a SIDE 2 with the card on its IDE bus, VBXE and a Rapidus.

    build/gem-cf.img   16 MB, two APT partitions (tools/mkcf.py):
                       D1: GEM4XE, \\GEM\\GEM.COM and the desktop beside
                       it, AUTOEXEC.BAT changing into \\GEM and running
                       GEM; D2: DOCS, empty.

Nothing on the card is a driver.  The U1MB's own PBI BIOS reads the APT
table, mounts the mapping-slot partitions as D1: and D2: before any DOS
runs, and SpartaDOS X -- from the same flash -- then finds AUTOEXEC.BAT
on D1: exactly as it would on a floppy.  That is why the gate needs the
U1MB fixture ([u1mb].flash in fixtures.toml) and the patched emulator:
`--u1mbrom` and `KEYRAW` are ours (tools/altirra/).

Three things about this machine had to be measured, and each is a step
of the run below:

  * A fresh U1MB profile boots into the BIOS setup screen, and the
    settings that matter are off by default: PBI BIOS, and its Hard
    disk.  The gate walks that setup with KEYRAW -- RIGHT and LEFT step
    the pages along the icon row, UP and DOWN move the field cursor,
    RETURN changes the field under it, and the last page saves and boots
    -- reading the screen after every key: the menu is ANTIC character
    rows, which the bridge's DLIST finds, so each field is found by its
    name and its value is watched until it reads right.  A count of keys
    fits one firmware release and sets the wrong field on the next
    (bios_setup below), and `--flash ROM` runs the gate on any U1MB
    image, 1.25 to 4.20.  So the gate runs the machine's documented setup
    rather than a profile someone prepared by hand, and it starts from a
    config directory of its own (build/altirra-cf) so it is the same run
    every time and the user's own emulator profile is left alone.
  * The PBI device ID must not be 0.  Setting 0 is PBI bit 0, which is
    the Rapidus's, and the two would collide on real hardware
    (docs/phase14.md).
  * The PBI BIOS will not touch the disk while the cartridge port is
    claimed.  Its first act is a wait:

        $D803  LDA #$80 / STA $D5E4 / BIT $D384 / BVS $D803

    $D384 bit 6 is the U1MB's "external cart active" sense and the SIDE
    holds it while its own SDX module is mapped -- the state of a SIDE 2
    whose SDX switch is on.  A machine that runs SpartaDOS X from the
    U1MB has that switch off; AltirraSDL exposes the switch as a device
    button with no command line or bridge verb, so the gate unmaps the
    SDX bank the way the switch does, by writing $80 to the SIDE's bank
    register at $D5E1.  A reset puts the bank back, so it is written
    again through the run.

The rest is the boot the floppy gate runs (tests/emu/product_boot.py):
the card starts GEM on the 6502 the machine came up as, the loader finds
the Rapidus behind it and switches the CPU itself, and the desktop comes
up on the
restart and is compared with the model.

  python3 tests/emu/cf_boot.py [--shot] [--card build/gem-sd.img] [--flash ROM]

`--card` boots another image the same way: `build/gem-sd.img` is the
SD-card shape (`tools/mkcf.py --fat`), a FAT32 partition first and the
APT table after it, which is what a SubCart's or an AVGCART's SIDE 2
emulation hands the PBI BIOS -- so the same gate proves the BIOS finds
the table through the MBR when the table is not at LBA 1.
"""
import os
import re
import shutil
import sys
import tomllib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
# The emulator keeps the U1MB's NVRAM in its profile, and a fresh NVRAM
# is what puts the BIOS into setup.  Set before the launcher is imported
# so the emulator it starts inherits it.
PROFILE = os.path.join(BUILD, "altirra-cf")
os.environ["XDG_CONFIG_HOME"] = PROFILE

from a8test.launcher import launch          # noqa: E402
import apt, atr, mkxex, symfile, vbxeref    # noqa: E402
from m4_aes import SHOTDIR                  # noqa: E402
from m14_sparta import screen               # noqa: E402
from m17_desktop import listing             # noqa: E402
from product_boot import (BOOT_WAIT, FARMEM_BRK, REFUSAL, STEP,     # noqa: E402
                          boot_screen, desk_model, far_byte, far_probes)

CARD = os.path.join(BUILD, "gem-cf.img")
SYMS = os.path.join(BUILD, "gem.sym")
ELF = os.path.join(BUILD, "gem.elf")
FIXTURES = os.path.join(ROOT, "fixtures.toml")
BOOT_LINE = b"CD >GEM\x9bGEM\x9b"
WANT = {"GEM>GEM.COM": "gem.xex", "GEM>DESKTOP.PRG": "desktop.g4a",
        "GEM>DESKTOP.RSC": "desktop.rsc"}
# The PBI BIOS names itself as it mounts the card: "Ultimate PBI" in 1.25,
# "U1MB SIDE2 PBI BIOS v.4.20, dev. 6" in 4.20.
PBI_BANNER = "PBI"
SDX_BANK = 0xD5E1               # the SIDE's SDX bank register; $80 unmaps it
DRVMAP = 0x03                   # D1: and D2:, the card's two partitions
RTC_U1MB = 0xD3E2               # src/sys/clock.c: the chip the U1MB carries
CLOCK_CARD = {0: "none", 1: "U1MB", 2: "SIDE", 3: "the DOS"}   # src/sys/clock.h
# the boot screen's Clock line starts with the card (src/sys/bootinfo.c)
CLOCK_LINE = {1: "U1MB, ", 2: "SIDE, ", 3: "DOS, "}

# The BIOS setup is walked by what its screen says, not by a count of keys.
# The fields move between firmware releases -- 2.0 put a PBI logo row
# between the device ID and Hard disk, 4.0 made the device ID a field that
# RETURN opens for editing -- and a key count written for one release
# enables the wrong field on the next and saves it: a card that is never
# mounted, and a gate that says only that the loader never ran.  What each
# field must read when the walk is done:
BIOS_WANT = [("PBI BIOS", lambda v: v.startswith("Enabled")),
             # not 0, which is PBI bit 0, the Rapidus's (docs/phase14.md)
             ("PBI device ID", lambda v: v.isdigit() and v != "0"),
             ("Hard disk", lambda v: v.startswith("Enabled"))]
# the switch for the banner: "PBI logo" in 2.0, "PBI notice" from 3.10
NOTICE = ("pbi logo", "pbi notice")
FIELD = re.compile(r"\s*(\S.*?):?\s{2,}(\S.*?)\s*$")    # label, value
SAVE = re.compile(r"save changes and (cold )?boot", re.I)


def bios_text(raw, internal):
    """A row of screen bytes as text, bit 7 (inverse) aside: in the OS's
    internal character order, or as plain ASCII codes drawn in a font of
    the BIOS's own."""
    text = ""
    for c in raw:
        v = c & 0x7F
        a = (v + 32 if v < 64 else v - 64 if v < 96 else v) if internal else v
        text += chr(a) if 32 <= a < 127 else " "
    return text


def bios_rows(b):
    """The U1MB BIOS setup screen as the character rows ANTIC is showing.
    The bridge's DLIST gives each text row's playfield address, and its
    DMACTL the width: 32 columns for the menu, 40 for the lines around
    it.  Every release from 1.25 to 4.20 draws its menu this way, in mode
    3 before 4.0 and mode 2 from it, and none through the OS's SAVMSC --
    but not in one encoding: 1.25 to 3.10 store ASCII codes under a font
    of their own and 4.0 the OS's internal codes, so both readings are
    made and the one with capital letters in it is the screen.  Lower
    case is the same code in both, and each reads the other's capitals
    as punctuation or blanks; a count of fields cannot tell them apart,
    because blanks are all a field needs.  Each row is (width, text,
    inverse), one inverse flag a column: the field cursor is inverse
    video."""
    raws, seen = [], set()
    for e in b.cmd("DLIST").get("entries", []):
        if e.get("kind") != "graphics" or e.get("mode") not in (2, 3):
            continue
        width = {1: 32, 2: 40, 3: 48}.get(int(e["dmactl"].lstrip("$"), 16) & 3)
        if not width or e["addr"] in seen:
            continue
        seen.add(e["addr"])
        raws.append((width, bytes(b.memdump(int(e["pf"].lstrip("$"), 16), width))))
    readings = [[(w, bios_text(raw, internal), [bool(c & 0x80) for c in raw])
                 for w, raw in raws] for internal in (True, False)]
    return max(readings, key=lambda rows: sum(c.isupper() for _, t, _ in rows for c in t))


def bios_fields(rows):
    """The menu's fields in screen order, (label, value, on_label,
    on_value): the last two say which half the inverse video is on."""
    menu = min((w for w, _, _ in rows), default=0)
    out = []
    for w, text, inv in rows:
        m = FIELD.match(text) if w == menu else None
        if m:
            out.append((m.group(1), m.group(2), any(inv[m.start(1):m.end(1)]),
                        any(inv[m.start(2):m.end(2)])))
    return out


def bios_setup(b, check):
    """Walk the BIOS setup from its first page to BIOS_WANT, then save and
    boot, reading the screen after every key.  Returns the fields' values
    by label, with "keys" and "notice" (the banner switch's value, None
    where the release has none); None if the screen was never the one
    expected, with the reason checked."""
    keys = [0]

    def tap(key):
        b.key_tap(key)
        b.frames(15)
        keys[0] += 1

    def find(label):
        fs = bios_fields(bios_rows(b))
        at = [i for i, f in enumerate(fs) if f[0].lower() == label.lower()]
        cur = [i for i, f in enumerate(fs) if f[2] or f[3]]
        return fs, (at[0] if at else None), (cur[0] if cur else None)

    for _ in range(12):                     # the page, along the icon row
        if find("Hard disk")[1] is not None:
            break
        tap("right")
    else:
        check(False, "the BIOS setup never showed a page with Hard disk on it")
        return None
    got = {}
    for label, ok in BIOS_WANT:
        for _ in range(16):                 # the cursor, down the page
            fs, at, cur = find(label)
            if at is None:
                check(False, f"the PBI page has no {label} field")
                return None
            if cur == at:
                break
            tap("down" if cur is None or cur < at else "up")
        else:
            check(False, f"the field cursor never reached {label}")
            return None
        # Which half the cursor inverts says what an open field looks
        # like: from 4.0 the cursor is on the label and RETURN moves it to
        # the value, where UP steps it and RETURN closes it; before 4.0
        # the cursor is on the value and RETURN steps it.
        on_label = fs[at][2]
        for _ in range(16):
            fs, at, _ = find(label)
            _, value, lab, val = fs[at]
            editing = on_label and val and not lab
            if ok(value) and not editing:
                break
            tap("up" if editing and not ok(value) else "return")
        else:
            check(False, f"{label} never came to a usable value (it reads {value!r})")
            return None
        got[label] = value
    got["notice"] = next((f[1] for f in bios_fields(bios_rows(b))
                          if f[0].lower() in NOTICE), None)
    # Save and Exit: "Save changes and boot" before 4.0, "Save changes
    # and cold boot" from it, with its key at the end of the row -- [B],
    # or B in an inverse keycap.
    for _ in range(12):
        save = [t for _, t, _ in bios_rows(b) if SAVE.search(t)]
        if save:
            break
        tap("right")
    else:
        check(False, "the BIOS setup never showed Save changes and boot")
        return None
    key = save[0].rstrip().rstrip("]")[-1:].lower()
    tap(key if key.isalpha() else "b")
    got["keys"] = keys[0]
    return got


def flash():
    with open(FIXTURES, "rb") as f:
        return tomllib.load(f).get("u1mb", {}).get("flash")


def keep_switch(b, frames, step=50):
    """Frames, with the SIDE's SDX bank kept unmapped -- see the header."""
    for _ in range(0, frames, step):
        b.cmd(f"HWPOKE ${SDX_BANK:04X} $80")
        b.frames(step)


def card_checks(check, card=CARD):
    """The card as tools/mkcf.py wrote it, read back through the same
    table the firmware reads: two partitions in mapping slots 1 and 2, so
    they arrive as D1: and D2:, and the system where the batch file
    looks for it."""
    img = apt.Image.load(card)
    parts = apt.read_table(img)
    fat = apt.read_fat(img)
    print(f"{os.path.basename(card)}: {img!r}, {len(parts)} partitions"
          + (f", FAT32 at block {fat[0]}" if fat else ""))
    if fat:
        check(fat[0] + fat[1] <= parts[0].start, "the FAT partition overlaps D1:")
    check(len(parts) == 2, f"the card has {len(parts)} partitions, not 2")
    fs = atr.Sdfs(parts[0])
    listed = {e.filename.upper(): e.size for e in fs.entries("")}
    print(f"  D1: {fs.volname}, {', '.join(sorted(listed))}, "
          f"{fs.free_count()} sectors free")
    for path, built in WANT.items():
        name = path.split(">")[-1]
        where = path.split(">")[0] if ">" in path else ""
        sizes = {e.filename.upper(): e.size for e in fs.entries(where)}
        check(name in sizes, f"{path} is not on the card")
        if name in sizes:
            size = os.path.getsize(os.path.join(BUILD, built))
            check(sizes[name] == size,
                  f"{path} is {sizes[name]} bytes, not build/{built}'s {size}")
    check("AUTOEXEC.BAT" in listed, "no AUTOEXEC.BAT: nothing would start GEM")
    if "AUTOEXEC.BAT" in listed:
        check(fs.read("AUTOEXEC.BAT") == BOOT_LINE,
              f"AUTOEXEC.BAT holds {fs.read('AUTOEXEC.BAT')!r}, not {BOOT_LINE!r}")
    return fs


def cfg_clock(fs):
    """What the card's GEM4XE.CFG says the clock is: the CLOCK= line if
    it has one, else AUTO (src/sys/config.c reads it the same way)."""
    try:
        text = fs.read("GEM>GEM4XE.CFG").replace(b"\x9b", b"\n").decode("latin-1")
    except Exception:
        return "AUTO"
    for ln in text.splitlines():
        ln = ln.split("#")[0].split(";")[0].strip().upper()
        if ln.startswith("CLOCK") and "=" in ln:
            return ln.split("=", 1)[1].strip() or "AUTO"
    return "AUTO"


def clock_checks(check, b, syms, want, report):
    """Which clock src/sys/clock.c settled on, read back from its own
    statics once the boot screen has asked it, against what the card's
    GEM4XE.CFG asked for; and the boot screen's own Clock line, which
    is the time it read.  With CLOCK=DOS the SpartaDOS X kernel is the
    clock, and the date and time it answered must be the emulated
    chip's, which is the host's own in Altirra, to within the boot's
    few minutes.  (Page 7 itself is no use here: by the time the
    desktop is up it holds the stamp of the last file the DOS touched.)
    That is the only gate on dos_call (src/sys/cio.s) and dos_clock: on
    the plain card both chips are found first and the DOS is never
    asked."""
    import datetime
    probed = b.peek(syms["rtc_probed"])
    card = 3 if b.peek(syms["rtc_dos"]) else (
        0 if b.peek16(syms["rtc"]) == 0 else
        1 if b.peek16(syms["rtc"]) == RTC_U1MB else 2)
    check(probed, "the boot screen never asked src/sys/clock.c for the clock")
    line = report.get("Clock", "")
    print(f"  the clock: {CLOCK_CARD[card]} (CLOCK={want}); "
          f"the boot screen said {line!r}")
    if want == "DOS":
        check(card == 3, f"CLOCK=DOS, but the clock found is {CLOCK_CARD[card]}")
    else:
        check(card == 1, f"the U1MB's chip was not the clock found ({CLOCK_CARD[card]})")
    check(line.startswith(CLOCK_LINE.get(card, "?")),
          f"the boot screen's Clock line does not name {CLOCK_CARD[card]}")
    now = datetime.datetime.now()
    try:
        then = datetime.datetime.strptime(line.split(", ", 1)[1], "%Y-%m-%d %H:%M:%S")
        off = abs((now - then).total_seconds())
    except (IndexError, ValueError):
        off = None
    check(off is not None and off < 15 * 60,
          f"the clock read {line!r}, the host's says {now:%Y-%m-%d %H:%M:%S}")


def main(argv):
    keep = "--shot" in argv
    card = (os.path.abspath(argv[argv.index("--card") + 1])   # the emulator's cwd is not ours
            if "--card" in argv else CARD)
    rom = (os.path.abspath(argv[argv.index("--flash") + 1])
           if "--flash" in argv else flash())
    if not rom or not os.path.exists(rom):
        print("gem4xe-cf: no U1MB fixture -- set [u1mb].flash in fixtures.toml")
        return 2
    if not os.path.exists(card):
        print(f"gem4xe-cf: no {card} -- run make")
        return 2
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    syms = symfile.load(SYMS)
    segs, _ = mkxex.read_elf(ELF)
    far = sorted((a, d) for a, d in segs if a > 0xFFFF)
    chunk = syms["_fl_end"] - syms["_fl_buf"]
    fs = card_checks(check, card)

    # A profile of the gate's own, thrown away first: a fresh NVRAM is
    # what makes the BIOS open its setup screen.
    shutil.rmtree(PROFILE, ignore_errors=True)
    os.makedirs(PROFILE)
    os.makedirs(SHOTDIR, exist_ok=True)
    shot = os.path.join(SHOTDIR, "cf-desk.png")
    print(f"the machine: U1MB {rom}, SIDE 2, VBXE, Rapidus")
    emu = launch(tag="cf", memsize="1088K", require_real_rom=False,
                 extra_args=["--u1mbrom", rom, "--adddevice", "side2"])
    b = emu.bridge
    try:
        added = b.cmd(f"DEVICE_ADD harddisk parent=/side2/idebus path={card} "
                      f"write_enabled=1").get("ok")
        check(added, "the card would not attach to the SIDE 2's IDE bus")
        b.cmd("COLD_RESET")
        b.frames(300)
        check(b.has_keyraw(), "this emulator has no KEYRAW: see tools/altirra/")

        # -- 1. the BIOS setup, read off its screen --------------------------
        got = bios_setup(b, check)
        if got is None:
            for _, text, _ in bios_rows(b):
                if text.strip():
                    print("   |" + text.rstrip())
            return 1
        print(f"  the BIOS configured in {got['keys']} keys: PBI BIOS "
              f"{got['PBI BIOS']}, device ID {got['PBI device ID']}, Hard disk "
              f"{got['Hard disk']}, banner {got['notice'] or 'always'}")

        # -- 2. and 3. the card boots and the machine switches itself ------
        # As on the floppies (tests/emu/product_boot.py): the PBI BIOS
        # mounts the card, SpartaDOS X runs AUTOEXEC.BAT, GEM begins
        # loading on the 6502 this machine came up as, and the loader
        # finds the Rapidus behind it and switches it (src/farload.s
        # fl_no816).  Nothing here types or pokes.
        #
        # The PBI BIOS that mounted the card is itself a PBI device, and
        # the probe writes the select register: it selects the slot the
        # card answers on, and the CPU resets inside that same write, so
        # what the BIOS had selected never has to be put back.
        was = b.cmd("HWSTATE").get("cpu", {}).get("mode")
        check(was == "6502", f"the machine did not start as a 6502 (it is {was})")
        banner = False
        for t in range(0, 20000, 100):
            keep_switch(b, 100)
            lines = [ln for ln in screen(b) if ln.strip()]
            banner = banner or any(PBI_BANNER in ln for ln in lines)
            if b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502":
                break
        else:
            check(False, "the loader never switched the CPU")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        if (got["notice"] or "Enabled").startswith("Enabled"):
            check(banner, "no PBI BIOS banner: the card was not mounted by it")
        mode = b.cmd("HWSTATE").get("cpu", {}).get("mode")
        print(f"  the PBI BIOS mounted the card, SpartaDOS X ran "
              f"AUTOEXEC.BAT, and the loader switched the machine to "
              f"{mode} by itself, {t + 100} frames in")

        # -- 3b. the boot screen, while it is held ---------------------------
        # As the floppy gate reads it (tests/emu/product_boot.py): the
        # Clock line is the time GEM read, from whichever clock it found.
        for t in range(0, BOOT_WAIT, STEP):
            keep_switch(b, STEP, STEP)
            report = boot_screen(b)
            if report:
                break
        else:
            check(False, "the boot screen never showed its hint")
            report = {}
        if report:
            print(f"  the boot screen, {t + STEP} frames after the switch:")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)

        # -- 4. the desktop ------------------------------------------------
        calls = syms["app_calls"]
        n, still = b.peek16(calls), 0
        for t in range(0, 30000, 250):
            keep_switch(b, 250)
            now = b.peek16(calls)
            still = still + 1 if now == n else 0
            n = now
            if still >= 2 and now:
                break
        else:
            check(False, f"GEM never settled ({n} calls)")
        print(f"  GEM settled after {t + 250} frames, {n} calls in")
        fault = b.peek(syms["irq_fault"])
        check(fault == 0, f"irq_fault {fault} (src/sys/irq.s)")
        check(not any(REFUSAL in ln for ln in screen(b)),
              "GEM refused the 65C816 as well: the switch did not take")
        clock_checks(check, b, syms, cfg_clock(fs), report)

        bad = []
        for a in far_probes(far, chunk):
            if b.cmd(f"EVAL db(${a:06x})").get("value") != far_byte(far, a):
                bad.append(a)
        check(not bad, f"the far image differs at {len(bad)} probed byte(s), "
                       f"first ${bad[0]:06X}" if bad else "")
        print(f"  the far image: {len(far_probes(far, chunk))} bytes probed, "
              f"{'all as the linker wrote them' if not bad else str(len(bad)) + ' wrong'}")

        mark = b.peek16(syms["app_pool_lo"])
        brk = int.from_bytes(bytes(b.memdump(syms["farmem"] + FARMEM_BRK, 4)), "little")
        pointer = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        print(f"  pool ${mark:04X}, far brk ${brk:06X}, pointer {pointer}")
        ref_v, ref_a, d = desk_model(mark, brk, pointer, DRVMAP, listing(fs))
        check(len(ref_a.shots) == 1, f"the model took {len(ref_a.shots)} shots")
        check((n - 1) & 0xFFFF == d.waits[0],
              f"the desktop is in call {(n - 1) & 0xFFFF}, not its first "
              f"wait {d.waits[0]}")
        b.screenshot(shot)
        bad_px, shown = vbxeref.compare_to_shot(ref_a.shots[0], shot)
        check(not bad_px, f"the desk, {bad_px} px differ from the model; "
                          f"first {shown[:3]}")
        print(f"  the desk {'ok' if not bad_px else 'FAIL'} against the model "
              f"({shot if bad_px or keep else 'not kept'})")
        if not bad_px and not keep:
            os.remove(shot)
    finally:
        emu.stop()

    print(f"gem4xe-cf: {'PASS' if not fails else 'FAIL'} -- the CF card, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
