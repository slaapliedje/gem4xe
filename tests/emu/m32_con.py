#!/usr/bin/env python3
"""Phase 42 gate: GEMDOS's console, its standard handles, the memory calls
and Pterm -- from a program that never calls the AES.

M32.PRG (src/m32_con.c) is run from test-m16's stand-in desktop, through
the shell loop, the way a TOS program would be:

    T  ->  M32.PRG writes a page of VT-52 -- every escape in the
           Compendium's table -- and waits at the console;
           K, then "hi", BACKSPACE, "ey", RETURN, then Z, ^C and Q;
           it points its standard handles at a file and back, and reads
           the file through them; it writes "done" and waits;
           SPACE, and it ends with Pterm(42) from inside a function
    Q  ->  shutdown

WHAT IS CHECKED:

  THE SCREEN, twice, against tools/conref.py: the page with the cursor
  waiting after it, and the page again with the echoes on it -- Cconin's,
  and Cconrs's line with its backspace taken back -- and nothing of what
  was written while handle 1 pointed at a file.

  WHAT EVERY CALL ANSWERED, out of the program's memory by symbol: the
  keys with their scan bytes, Cconrs's count, Cconis holding a key without
  taking it, Super's two answers, Mxalloc/Mshrink/Mfree moving the far
  heap by exactly the block, EIMBA for an address Malloc never gave and
  EGSBF for a bigger Mshrink, aux: and prn: with nothing behind them, the
  device handle Fopen("CON:") answers, Fdup's handle, the file handle 1
  wrote reading back byte for byte, and handle 0 reading it: 't', a line,
  '!', a line to the end, then 0xFF1A.

  PTERM: the shell's record of what the program returned is 42, not the
  7 its main() returns after the call -- so Pterm did not come back --
  and the desktop runs again, reads a key (interrupts are on) and draws
  over the console.  The program ended with a file open, forced onto
  handle 1 and duplicated: after shutdown no IOCB but the screen editor's
  is in use, and the pool and far heap are back where they were.

WHAT IS NOT: Tsetdate and Tsettime on a clock.  This machine has none,
and Altirra's DS1305 answers every read with the host's time, so a write
cannot be read back (src/sys/clock.c); they are checked to refuse.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vbxeref, symfile, conref     # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE,  # noqa: E402
                     SYMS)   # build/m3.sym: this disk's runner
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import Runner                 # noqa: E402
from m13_alert import ALLOC, SETTLE         # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL, poll, desktop_script  # noqa: E402
from m17_desktop import header              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m32-boot.atr"))
CON = os.path.join(ROOT, "build", "m32_con.g4a")
CON_SYM = os.path.join(ROOT, "build", "m32_con.sym")
DESKTOP = os.path.join(ROOT, "build", "m16_desk.g4a")

# src/m32_con.c's page[], byte for byte, and what follows it
E = b"\x1b"
PAGE = [
    E + b"Ejunk row zero\r\njunk row one" + E + b"Y\x22\x23" + E + b"d",
    E + b"Hgem4xe console\r\n",
    E + b"preverse" + E + b"q normal\r\n",
    E + b"b\x02ink 2 " + E + b"c\x03paper 3" + E + b"c " + E + b"b!\r\n",
    b"tab\tstop\r\n",
    E + b"Y\x25\x28at 5,8",
    E + b"Y\x26 xxxxxxxxxx" + E + b"Y\x26\x24" + E + b"K",
    E + b"Y\x27 abcdefgh" + E + b"Y\x27\x22" + E + b"D" + E + b"o",
    E + b"Y\x28 " + E + b"v" + b"0123456789" * 8 + b"01234",
    E + b"w" + E + b"Y\x2a " + b"abcdefghij" * 8 + b"klmno",
    E + b"Y\x2b wipe this line" + E + b"lkept",
    E + b"Y\x2c saved" + E + b"j" + E + b"Y\x30 elsewhere" + E + b"k restored",
    E + b"Y\x32 line to delete" + E + b"Y\x33 line below" + E + b"Y\x32 " + E + b"M",
    E + b"Y\x34 " + E + b"Linserted",
    E + b"Y\x37 keep this" + E + b"Y\x38 erase below" + E + b"Y\x37\x24" + E + b"J",
    E + b"H" + E + b"Iabove",
    E + b"Y\x3d bottom\r\n",
    E + b"A" + E + b"A" + E + b"C" + E + b"C" + E + b"Cup" + E + b"Bdown",
    b"\x07\x08\x08X",
]
AFTER = [b"!", b"fwrite", b"R", b"con:"]    # Cconout, Fwrite(1), Crawio, Fwrite(CON:)
TYPED = [("H", b"h"), ("I", b"i"), ("BACKSPACE", b"\b \b"), ("E", b"e"),
         ("Y", b"y"), ("RETURN", b"\r")]

EINVFN, EFILNF, EIHNDL, EIMBA, EGSBF = -32, -33, -37, -40, -67
KID_FILE = b"kid hello\r\nend"             # M32KID.PRG's line, then its parent's
CEOF = 0xFF1A - 0x10000                     # GD_CEOF as the WORD it is read into
HANDLE_BASE, DUP_BASE = 6, 14
TO_FILE = b"to file\r\n!abc"


def main(argv):
    keep = "--shot" in argv
    ntsc = "--ntsc" in argv                  # test-m32n: the same on an NTSC machine
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    csym = symfile.load(CON_SYM)
    runs, lastret, lastrc = syms["sh_runs"], syms["sh_lastret"], syms["sh_lastrc"]
    ptr = syms["ptr_state"]
    link_near, _, _ = header(CON)
    desk_len = (os.path.getsize(DESKTOP) + 3) & ~3     # far_alloc's rounding
    os.makedirs(SHOTDIR, exist_ok=True)

    def same(b, name, rgb, what):
        p = os.path.join(SHOTDIR, f"m32-{name}.png")
        b.screenshot(p)
        if ntsc:                            # the models are laid out on a PAL
            print(f"  {what:<58s} not compared on NTSC")   # frame: 262 lines, not 312
            if not keep:
                os.remove(p)
            return
        bad, shown = vbxeref.compare_to_shot(rgb, p)
        check(not bad, f"{what}: {bad} px differ from the model; first {shown[:3]}")
        print(f"  {what:<58s} {'ok' if not bad else 'FAIL'}")
        if not keep and not bad:
            os.remove(p)

    emu = launch(tag="m32n" if ntsc else "m32", memsize="1088K", extra_args=["--disk", DISK],
                 pal=not ntsc)
    b = emu.bridge
    try:
        t, st = boot(b)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  M3.COM loaded and running {t} frames after RETURN")
        r = Runner(b, syms)
        r.run(PRELUDE)
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark, room = rec[6] & 0xFFFF, rec[7]
        brk = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"before: pool ${mark:04X}, {room} free; far brk ${brk:06X}")

        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, _ = aesref.run(PRELUDE, [], {}, pointer=pointer, pool=mark)
        hbox = ref_a.gl_hbox

        def model_desk():
            ref_v.close_virtuals()
            ref_a.wm_init()
            ref_a.mn_init()
            ref_a.ratinit()
            ref_a.gr_mouse(aesref.ARROW)
            ref_a.tree = ref_a.W_TREE
            ref_a.draw(0, 0, (0, 0, ref_a.gl_width, ref_a.gl_height))

        def model_desktop():
            model_desk()
            aesref.resume(ref_v, ref_a, desktop_script(hbox))

        script = PRELUDE + [(SHELL, (), ())]
        words = aesref.encode(script, 0)
        b.memload(r.sa, b"".join(
            (w if w < 32768 else w - 65536).to_bytes(2, "little", signed=True)
            for w in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)

        t = poll(b, runs, 1)
        check(t >= 0, "the desktop never ran (sh_runs stayed 0)")
        if t < 0:
            return 1
        b.frames(SETTLE)
        model_desktop()
        same(b, "desktop", ref_v.to_rgb(), "the stand-in desktop")

        # ---- the program -------------------------------------------------
        b.key("T")
        t = poll(b, runs, 2)
        check(t >= 0, f"after T: M32.PRG did not run (sh_runs {b.peek16(runs)})")
        if t < 0:
            return 1
        near = b.peek16(syms["app_near"])

        def at(name):
            return csym[name] + near - link_near

        step = at("m32_step")

        def reached(n, what):
            tt = poll(b, step, n)
            check(tt >= 0, f"{what}: M32.PRG did not get to step {n} "
                           f"(it is at {b.peek16(step)})")
            return tt >= 0

        if not reached(2, "the page"):
            return 1
        b.frames(SETTLE)
        print(f"  M32.PRG up {t} frames after T; its near region is at ${near:04X}")

        model_desk()                        # app_free, the desk, then the program
        con = conref.Console(ref_a)
        for s in PAGE + AFTER:
            con.write(s)
        where = con.wait()                  # Cconin
        same(b, "page", ref_v.to_rgb(), "the VT-52 page, the cursor after it")

        b.key("K")
        reached(3, "after K")
        con.waited(where)
        con.write(b"k")
        for key, echo in TYPED:             # Cconrs, one wait a key
            b.key(key)
            b.frames(20)
            con.write(echo)
        reached(4, "after the line")
        b.key("Z")                          # Cnecin: no echo
        reached(5, "after Z")
        b.key("C", ctrl=True)               # Crawcin: ^C is only a key
        reached(6, "after ^C")
        b.frames(30)
        b.key("Q")                          # Cconis, then Cnecin
        reached(7, "after Q")
        if not reached(8, "the handles and the memory"):
            return 1
        b.frames(SETTLE)
        con.write(b"\r\ndone")
        con.wait()
        same(b, "done", ref_v.to_rgb(), "the echoes, and nothing of the file's")

        res = struct.unpack("<64h", b.memdump(at("m32_res"), 128))
        mem = struct.unpack("<6i", b.memdump(at("m32_mem"), 24))

        # -- the clock: Tgettimeofday and clock() across evnt_timer(500) ----
        # Seconds since 1970 from the RTC read once, microseconds from the
        # ~4 kHz timer (src/sys/irq.c, irq_clock).  The wait is measured in
        # frames -- 25 of 20 ms on a PAL machine, 30 of 16.7 on NTSC, where
        # vex_timv says 17 (src/vdi/vdi.c): a tick of 20 assumed there gave
        # 25 frames, 417 ms, which the floor below is placed to catch -- so
        # the span is 500 ms give or take a frame each side and the poll's
        # own slack; the
        # microseconds must be a real fraction of a second, and time must
        # not run backwards.  clock() reports the same span in the units
        # its header names, which the program hands back beside it.
        a_s, a_us, b_s, b_us, cspan, cps = struct.unpack("<6i", b.memdump(at("m32_time"), 24))
        check(res[59] == 0 and res[60] == 0,
              f"Tgettimeofday answered {res[59]} and {res[60]}, not 0")
        check(0 <= a_us < 1000000 and 0 <= b_us < 1000000,
              f"tv_usec is not a fraction of a second: {a_us}, {b_us}")
        check(a_s >= 315532800,
              f"tv_sec {a_s} is before 1 January 1980, the epoch with no RTC")
        span = (b_s - a_s) * 1000 + (b_us - a_us) // 1000
        check(440 <= span <= 600,
              f"Tgettimeofday saw {span} ms across evnt_timer(500), expected ~500")
        cms = cspan * 1000 // cps if cps else -1
        check(cps > 0 and abs(cms - span) <= 40,
              f"clock() saw {cspan} ticks at {cps}/s = {cms} ms, Tgettimeofday {span} ms")
        print(f"  Tgettimeofday: {a_s}.{a_us:06d} -> {b_s}.{b_us:06d}, {span} ms across "
              f"evnt_timer(500) on {'NTSC' if ntsc else 'PAL'}; clock() {cspan} ticks "
              f"at {cps}/s ({cms} ms)")
        line = b.memdump(at("m32_line"), 5)
        text = b.memdump(at("m32_text"), 5)

        def want(i, value, what):
            check(res[i] == value, f"{what} answered {res[i]}, not {value}")

        # the keyboard
        want(0, 0, "Cconis with no key")
        want(1, 0, "Crawio(0xFF) with no key")
        want(2, ord("k"), "Cconin's ASCII")
        want(3, 0, "Cconin's high word (no scan code for a letter)")
        check(line[1] == 3 and line[2:5] == b"hey",
              f"Cconrs gave {line[1]} bytes {line[2:5]!r}, not 3 b'hey'")
        want(5, ord("z"), "Cnecin")
        want(6, 3, "Crawcin on ^C")
        want(7, -1, "Cconis holding the Q it found")
        want(8, ord("q"), "Cnecin after Cconis")
        print(f"  keys: k, {line[2:5]!r}, z, ^C, q -- as typed")

        # Super, memory, the clock, aux: and prn:
        want(9, -1, "Super(SUP_INQUIRE)")
        want(10, 0x0100, "Super(0L)")
        m0, p, m2, m3, m4 = mem[:5]
        check(p > 0xFFFF, f"Mxalloc gave ${p & 0xFFFFFFFF:06X}, not far memory")
        check(m0 - m2 >= 1004, f"Mxalloc(1000) took {m0 - m2} bytes, not 1004")
        want(12, 0, "Mshrink to 100")
        check(m3 - m2 == 900, f"Mshrink to 100 gave back {m3 - m2} bytes, not 900")
        want(14, EGSBF, "Mshrink to more than the block")
        want(15, 0, "Mfree of the last block")
        check(m4 - m2 == 1004, f"Mfree gave back {m4 - m2} bytes, not the block's 1004")
        want(17, EIMBA, "a second Mfree of it")
        want(18, EIMBA, "Mfree of a bank-$00 address")
        print(f"  memory: Mxalloc ${p:06X}, 1004 taken, 900 back on Mshrink, "
              f"the rest on Mfree")
        want(19, -1, "Tsetdate with no clock")
        want(20, -1, "Tsetdate of day 0")
        want(21, -1, "Tsettime of 31:63:62")
        want(22, 0, "Cauxis")
        want(23, 0, "Cauxos")
        want(24, CEOF, "Cauxin")
        want(25, 0, "Cprnos with PRINTER=NONE")
        want(26, 0, "Cprnout with PRINTER=NONE")
        want(27, -1, "Cconos")

        # the device handle, and handle 1 into a file
        want(28, -1, 'Fopen("CON:")')
        want(29, 4, "Fwrite to CON:")
        want(30, 0, "Fclose of CON:")
        check(res[31] > HANDLE_BASE, f"Fcreate answered {res[31]}")
        want(32, DUP_BASE, "Fdup(1)")
        want(33, 0, "Fforce(1, file)")
        want(34, 3, "Fwrite(1) into the file")
        want(35, 0, "Fforce(1, the duplicate)")
        want(36, 0, "Fclose of the duplicate")
        want(37, 0, "Fclose of the file")
        want(38, EIHNDL, "a second Fclose of the file")
        check(res[39] > HANDLE_BASE, f"Fopen of what handle 1 wrote answered {res[39]}")
        want(40, len(TO_FILE), "Fread of it")
        want(41, 1, "its bytes against 'to file\\r\\n!abc'")

        # handle 0 from the file
        want(42, 0, "Fforce(0, file)")
        want(43, ord("t"), "Cconin from the file")
        want(44, 6, "Cconrs's first line from the file")
        want(45, ord("!"), "Crawcin from the file")
        want(46, -1, "Cconis before the file's end")
        want(47, 3, "Cconrs's last line from the file")
        check(text[2:5] == b"abc", f"that line is {text[2:5]!r}, not b'abc'")
        want(48, CEOF, "Cconin at the file's end")
        want(49, 0, "Fclose(0)")
        want(50, 0, "Fclose of the file")
        print("  handles: Cconws, Cconout and Fwrite(1) landed in the file; "
              "Cconin and Cconrs read it back")

        # Pexec
        want(52, 5, "Pexec of M32KID.PRG (its Pterm)")
        want(53, 1, "Malloc(-1) after the child is what it was before (1 = equal)")
        want(54, 3, "Fwrite to the parent's own file after the child")
        want(59, 0, "Fclose of the parent's file after the child")
        want(55, len(KID_FILE), "Fread of what the child and then the parent wrote")
        want(56, 1, "its bytes against 'kid hello\\r\\nend'")
        want(57, EFILNF, "Pexec of a program that is not there")
        want(58, EINVFN, "Pexec mode 3")
        print("  Pexec: the child read its tail, wrote through the handle it was "
              "given, and ended with Pterm(5); everything it took came back")

        # ---- Pterm -----------------------------------------------------------
        b.key("SPACE")
        t = poll(b, runs, 3)
        check(t >= 0, f"after SPACE: the desktop did not come back (sh_runs "
                      f"{b.peek16(runs)})")
        if t < 0:
            return 1
        got = b.peek16(lastret)
        check(got == 42, f"the program's end gave the shell {got}, not Pterm's 42"
                         + (" -- Pterm came back, and main() returned" if got == 7 else ""))
        check(b.peek16(lastrc) == 0, f"the last load's status {b.peek16(lastrc)}")
        print(f"  Pterm(42): the shell has {got}, the desktop back {t} frames after SPACE")
        b.frames(SETTLE)
        model_desktop()
        same(b, "after", ref_v.to_rgb(), "the desktop again, over the console")

        b.key("Q")
        for _ in range(300):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            check(False, "after Q: the runner did not finish")
            return 1
        b.frames(4)
        iocbs = b.memdump(0x0340, 16 * 8)
        still = [i for i in range(1, 8) if iocbs[i * 16] != 0xFF]
        check(not still, f"IOCBs still open after the program: {still}")
        rec = r.run([(ALLOC, (), ())])[0][2:]
        mark2, room2 = rec[6] & 0xFFFF, rec[7]
        brk2 = (rec[8] & 0xFFFF) | (rec[9] << 16)
        print(f"after:  pool ${mark2:04X}, {room2} free; far brk ${brk2:06X}")
        check((mark2, room2) == (mark, room),
              f"the pool after: mark ${mark2:04X}, {room2} free; was ${mark:04X}, {room}")
        check(brk2 == brk + desk_len,
              f"far brk moved {brk2 - brk} bytes; the desktop's file is {desk_len}")
    finally:
        emu.stop()

    print(f"gem4xe-m32{'n' if ntsc else ''}: {'PASS' if not fails else 'FAIL'} -- GEMDOS's console, "
          f"handles, memory, Pexec and Pterm, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
