#!/usr/bin/env python3
"""Phase 9 gate: native-mode interrupts, and the way back to DOS.

The 65816 in native mode takes its vectors from $FFE4-$FFEF, which the
Atari OS ROM never filled; src/sys/irq.c copies the ROM into the RAM under
it and fills them.  This checks each step against something the target did
not write itself:

  the shadow     $C000-$CFFF and $D800-$FFE3 as the CPU now reads them equal
                 the OS ROM image the emulator was booted with, byte for
                 byte, and the checksums the target reports equal the file's
  the vectors    $FFE4-$FFEF hold the five stub addresses the linker gave
                 (build/m3.sym), the emulation-mode set is untouched
  the VBI        irq_frames advances by exactly the frames the emulator ran
  the timer      irq_timer advances at POKEY's rate for the divisor the
                 target reports -- derived from the frame length it measured,
                 not from a PAL/NTSC assumption
  the keyboard   one KEY becomes one entry in the handler's count, and the
                 runner's idle loop drains the ring
  the pointer    a CX80 trak-ball, selected through the script, counted in
                 the handler while the target busy-waits with NOTHING
                 polling, then read back through vq_mouse
  the exit       the script asks for DOS; RTCLOK then advances under the
                 OS's own VBI, the OS's E: is open again, and a typed key
                 is echoed on DOS's prompt -- the OS keyboard IRQ running

What the joystick verb can and cannot drive: the bridge's JOY sets the four
switch lines, active low, so the only pair transitions it can make on the
trak-ball's direction-and-pulse lines are pulses with the direction line
HIGH -- +x and +y in the decode this checks.  -x/-y, and the ST and Amiga
Gray codes, are exercised in tests/host/test_pointer.py against Altirra's
device models instead.  Everything here is Altirra; no hardware has run it.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile, vdiref                      # noqa: E402
from vdiref import VQ_MOUSE                 # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
SYMS = os.path.join(ROOT, "build", "m3.sym")
SHOTDIR = os.path.join(ROOT, "build", "shots")
XLROM = os.environ.get("ATARIXL_ROM", "/opt/altirra/roms/ATARIXL.ROM")
STATUS, ST_GO, ST_DONE, ST_VC_PERIOD = 0x0600, 3, 4, 7
ST_IRQ = 30                     # how, fail, fast, timer_div, rom_sum, ram_sum
RTCLOK, CH = 0x0012, 0x02FC
ROWCRS, COLCRS, SAVMSC = 0x0054, 0x0055, 0x0058

# The sys ops src/m3_vdi.c understands, and the device numbers pointer.h gives.
SYS_PTR, SYS_EXIT, SYS_WAIT, SYS_POLL = 3000, 3001, 3002, 3003
SYS_BUTLOG = 3019
PTR_TRAKBALL = 3

# The two runs the shadow covers, and where the native vectors sit in them.
RUNS = ((0xC000, 0xD000), (0xD800, 0x10000))
VEC_BASE, VEC_LEN = 0xFFE4, 12


def poke16(b, addr, value):
    b.poke(addr, value & 0xFF)
    b.poke(addr + 1, (value >> 8) & 0xFF)


def run_script(b, sa, count_addr, words):
    b.memload(sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                           for w in words))
    b.poke(STATUS + ST_DONE, 0)
    poke16(b, count_addr, 0xFFFF)
    b.poke(STATUS + ST_GO, 1)


def wait_done(b, limit=300):
    for _ in range(limit):
        if b.peek(STATUS + ST_DONE) == 0xA5:
            return True
        b.frames(4)
    return False


def main(argv):
    os.makedirs(SHOTDIR, exist_ok=True)
    syms = symfile.load(SYMS)
    sa = syms["vdi_script"]
    results_addr, count_addr = syms["vdi_results"], syms["vdi_result_count"]
    with open(XLROM, "rb") as f:
        rom = f.read()
    assert len(rom) == 0x4000, (XLROM, len(rom))
    rom_at = lambda a: rom[a - 0xC000]        # noqa: E731

    fails = []

    def check(name, cond, detail=""):
        print(f"  {name:<60s} {'PASS' if cond else 'FAIL'}"
              + (f"   {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    emu = launch(tag="m10", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.frames(300)
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        b.frames(500)
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(250)
        for _ in range(200):            # ready, not merely alive
            s = bytes(b.memdump(STATUS, 3))
            if s[:2] == b"VD" and s[2] == 1:
                break
            b.frames(4)
        s = bytes(b.memdump(STATUS, 40))
        if s[:2] != b"VD" or s[2] != 1:
            print("runner did not come up:", s[:8].hex())
            return 1
        how, fail, fast, div = s[ST_IRQ:ST_IRQ + 4]
        rom_sum = s[ST_IRQ + 4] | (s[ST_IRQ + 5] << 8)
        ram_sum = s[ST_IRQ + 6] | (s[ST_IRQ + 7] << 8)
        rapidus = s[25]
        print(f"install: how={how} fail={fail} fast={fast} timer_div={div} "
              f"rom_sum=${rom_sum:04X} ram_sum=${ram_sum:04X}")

        # -- the shadow -----------------------------------------------------
        print("shadow")
        check("installed (ROM copied under itself or RAM found)",
              how in (1, 2) and fail == 0, f"how={how} fail={fail}")
        check("window 3 fast iff a Rapidus is present", fast == rapidus)
        want_sum = sum(sum(rom[lo - 0xC000:hi - 0xC000]) for lo, hi in RUNS) & 0xFFFF
        check("target's ROM checksum equals the image file's",
              rom_sum == want_sum, f"${rom_sum:04X} vs ${want_sum:04X}")
        check("RAM copy checksum equals the ROM's", ram_sum == rom_sum)
        # As the CPU reads it now: the copy, with the ROM switched out.
        for lo, hi in RUNS:
            hi_cmp = min(hi, VEC_BASE)
            got = b.memdump(lo, hi_cmp - lo)
            want = rom[lo - 0xC000:hi_cmp - 0xC000]
            diff = next((i for i in range(len(got)) if got[i] != want[i]), None)
            check(f"${lo:04X}-${hi_cmp - 1:04X} reads as the ROM image",
                  diff is None, "" if diff is None else f"first diff at ${lo + diff:04X}")
        got = b.memdump(0xFFF0, 16)
        check("$FFF0-$FFFF as the OS had them (emulation vectors kept)",
              got == rom[0x3FF0:], got.hex())

        # -- the vectors ----------------------------------------------------
        print("vectors")
        vec = b.memdump(VEC_BASE, VEC_LEN)
        names = ("_irq_vec_cop", "_irq_vec_brk", "_irq_vec_abort",
                 "_irq_vec_nmi", None, "_irq_vec_irq")
        want = b"".join(struct.pack("<H", syms[n] if n else 0) for n in names)
        check("$FFE4-$FFEF hold the linker's stub addresses", vec == want,
              f"{vec.hex()} vs {want.hex()}")
        for n in names:
            if n:
                check(f"{n} is a JML (bank $00, 4-byte stub)",
                      b.peek(syms[n]) == 0x5C and syms[n] < 0x10000)

        # -- the VBI --------------------------------------------------------
        print("sources")
        f0 = b.peek16(syms["irq_frames"])
        b.frames(50)
        f1 = b.peek16(syms["irq_frames"])
        check("irq_frames +50 over FRAME 50", abs((f1 - f0) & 0xFFFF) - 50 <= 1,
              f"+{(f1 - f0) & 0xFFFF}")

        # -- the timer ------------------------------------------------------
        # POKEY's 64 kHz clock is the CPU clock / 28 and a frame is 2 *
        # STATUS[7] lines of 114 cycles (ANTIC; the target measured the
        # line count), so a frame holds this many timer periods:
        lines = 2 * s[ST_VC_PERIOD]
        per_frame = lines * 114 / (28 * (div + 1))
        t0 = b.peek16(syms["irq_timer"])
        b.frames(100)
        t1 = b.peek16(syms["irq_timer"])
        got = ((t1 - t0) & 0xFFFF) / 100.0
        check("irq_timer rate within 3% of POKEY's for the divisor",
              abs(got - per_frame) <= 0.03 * per_frame,
              f"{got:.2f}/frame, expected {per_frame:.2f} ({lines} lines, div {div})")
        check("no COP/BRK/ABORT taken", b.peek(syms["irq_fault"]) == 0)

        # -- the keyboard ---------------------------------------------------
        k0 = b.peek(syms["irq_kb_count"])
        b.key("A")
        b.frames(5)
        k1 = b.peek(syms["irq_kb_count"])
        check("KEY A: one more key counted by the handler", ((k1 - k0) & 0xFF) == 1,
              f"+{(k1 - k0) & 0xFF}")
        check("the idle loop drained the ring",
              b.peek(syms["irq_kb_head"]) == b.peek(syms["irq_kb_tail"]))

        # -- the trak-ball --------------------------------------------------
        print("trak-ball")
        b.joy(1, "centre")
        script = vdiref.encode([
            (SYS_PTR, (), (PTR_TRAKBALL, 300, 100)),
            (SYS_WAIT, (), (120,)),
            (SYS_POLL, (), ()),
            (VQ_MOUSE, (), ()),
        ])
        run_script(b, sa, count_addr, script)
        for _ in range(40):
            if b.peek16(count_addr) == 1:       # ptr_init done; inside the wait
                break
            b.frames(1)
        else:
            check("target entered the wait", False)
        # 20 changes of state on the x pulse line, 10 on y's, one a frame.
        for i in range(20):
            b.joy(1, "down" if i % 2 == 0 else "centre")
            b.frames(1)
        for i in range(10):
            b.joy(1, "right" if i % 2 == 0 else "centre")
            b.frames(1)
        check("wait finished and the script completed", wait_done(b))
        n = b.peek16(count_addr)
        recs = vdiref.decode(b.memdump(results_addr, n * vdiref.RESULT_WORDS * 2), n)
        # A record is (contrl[2], contrl[4], intout[0..14], ptsout[0..2]).
        after_wait = recs[1]
        qlo, qhi = after_wait[2 + 2], after_wait[2 + 3]
        check("handler counted +20 on x during the wait", qlo == 20, f"qlo={qlo}")
        check("handler counted +10 on y during the wait", qhi == 10, f"qhi={qhi}")
        mouse = recs[3]
        x, y = mouse[2 + vdiref.RESULT_INTOUT], mouse[2 + vdiref.RESULT_INTOUT + 1]
        check("vq_mouse after one poll: (320, 110)", (x, y) == (320, 110), f"({x}, {y})")
        check("no COP/BRK/ABORT taken", b.peek(syms["irq_fault"]) == 0)

        # -- a click while nothing polls (phase 95) --------------------------
        # The trak-ball is still the pointer.  Its fire button is pressed and
        # let go twice -- a double click -- while the target busy-waits and
        # polls nothing; one poll afterwards must hand the button vector all
        # four changes, in order, from the vertical blank's trigger ring.
        # Before, the poll saw the button up, as it was, and nothing else.
        print("a click while busy")
        script = vdiref.encode([
            (SYS_BUTLOG, (), (1,)),
            (SYS_WAIT, (), (150,)),
            (SYS_POLL, (), ()),
            (SYS_BUTLOG, (), (0,)),
        ])
        run_script(b, sa, count_addr, script)
        for _ in range(40):
            if b.peek16(count_addr) == 1:       # the log is set; inside the wait
                break
            b.frames(1)
        else:
            check("target entered the wait", False)
        b.frames(10)
        for fire in (True, False, True, False):
            b.joy(1, "centre", fire=fire)
            b.frames(4)
        check("wait finished and the script completed", wait_done(b))
        n = b.peek16(count_addr)
        recs = vdiref.decode(b.memdump(results_addr, n * vdiref.RESULT_WORDS * 2), n)
        log = recs[3][2:2 + 15]
        states = list(log[7:7 + min(log[6], 8)])
        check("the poll replayed press, release, press, release",
              states == [1, 0, 1, 0], f"{log[6]} change(s): {states}")
        check("no COP/BRK/ABORT taken", b.peek(syms["irq_fault"]) == 0)

        # -- the way back ---------------------------------------------------
        print("exit")
        run_script(b, sa, count_addr, vdiref.encode([(SYS_EXIT, (), ())]))
        check("exit script reported done", wait_done(b))
        b.frames(20)
        c0 = b.memdump(RTCLOK, 3)
        b.frames(50)
        c1 = b.memdump(RTCLOK, 3)
        t0 = c0[2] | (c0[1] << 8) | (c0[0] << 16)
        t1 = c1[2] | (c1[1] << 8) | (c1[0] << 16)
        check("RTCLOK advances under the OS VBI after the exit",
              abs(((t1 - t0) & 0xFFFFFF) - 50) <= 2, f"+{(t1 - t0) & 0xFFFFFF}")
        check("STATUS block still says VD (page 6 not clobbered)",
              b.memdump(STATUS, 2) == b"VD")
        got = b.memdump(0xFFF0, 16)
        check("the OS ROM is back in ($FFF0-$FFFF from the ROM)", got == rom[0x3FF0:])
        # Coming back to DOS reloads DUP.SYS from the disk, which takes
        # rather longer than a keystroke; type into it only once it is up.
        b.frames(600)
        b.key("A")
        b.frames(60)
        # The OS keyboard IRQ puts the key in CH and DOS, a CIO GET RECORD
        # on E:, takes it out again (CH back to $FF) and echoes it -- so
        # the evidence is both: the key was consumed, and an 'A' ($21 in
        # display codes) appeared on the screen where DOS echoes it.
        savmsc = b.peek(SAVMSC) | (b.peek(SAVMSC + 1) << 8)
        page = bytes(b.memdump(savmsc, 960))
        for r in range(24):        # what the DOS is showing, for the record
            ln = "".join(chr((c & 0x7F) + 32 if (c & 0x7F) < 64 else
                             (c & 0x7F) - 64 if (c & 0x7F) < 96 else 32)
                         for c in page[r * 40:r * 40 + 40]).rstrip()
            if ln:
                print(f"    |{ln}")
        ch = b.peek(CH)
        check("a typed key goes through the OS keyboard IRQ to DOS",
              ch == 0xFF and 0x21 in page,
              f"CH=${ch:02X}, {'an A is' if 0x21 in page else 'no A'} on the screen")
        b.frames(50)
        shot = os.path.join(SHOTDIR, "m10_dos.png")
        b.screenshot(shot)
        print(f"  screenshot of the DOS prompt: {shot} (not asserted)")
    finally:
        emu.stop()

    print()
    print("m10: " + ("PASS" if not fails else f"FAIL ({len(fails)}): " + ", ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
