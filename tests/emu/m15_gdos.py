#!/usr/bin/env python3
"""Phase 14 gate, milestone 1: GEMDOS on CIO.

The ST's trap #1, as src/sys/gemdos.h lays it out in a call block, made
through the runner's sys op 3012 on a block the host stages in bank $00
-- the same block an application will hand the ABI through COP #$44 --
and every answer compared with what the disk image says (tools/atr.py
reads both DOS 2 and SDFS): Fsfirst/Fsnext over the root and, where the
DOS has directories, down the tree, name by name with attribute, size
and stamp; Dsetpath and Dgetpath keeping a directory per drive without
moving the DOS's own; Fopen/Fread/Fclose against the fixture, into bank
$00 and into far memory; Fcreate/Fwrite/Frename/Fattrib/Fdelete round
trips seen again through Fsfirst; Dcreate/Ddelete; Dfree against the
image's bitmap; the errors -- EFILNF, EPTHNF, EIHNDL, ENMFIL, EINVFN --
where the ST says them; and the application's exit closing what it left
open.  The round trips each call cost are printed: a directory listing
is one open and one read whatever its length.

    python3 tests/emu/m15_gdos.py            SpartaDOS 3.2g, build/m14-boot.atr
    python3 tests/emu/m15_gdos.py --sdx=CART SpartaDOS X 4.50 from the cartridge
    python3 tests/emu/m15_gdos.py --u1mb=ROM SpartaDOS X from an Ultimate 1MB flash image
    python3 tests/emu/m15_gdos.py --dos2     a DOS 2 (the fixture is DOS II+/D 6.4), build/m3-boot.atr
"""
import datetime
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile, atr                         # noqa: E402
from m7_form import poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE, SYMS  # noqa: E402
from m12_file import Runner, D2, FAULT_I, FRAMES_I, SYS  # noqa: E402
from m14_sparta import boot, screen, DISK as SPDISK  # noqa: E402

GDOS, RELEASE = SYS + 12, SYS + 13
SCRAP = SYS + 18                            # sc_write then sc_clear (src/m3_vdi.c)
CIO_I, CALLS_I, BAD_I = 8, 9, 10            # the op's own words
DOS2DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test.txt")

# src/sys/gemdos.h
FN = dict(Dsetdrv=0x0E, Dgetdrv=0x19, Fsetdta=0x1A, Tgetdate=0x2A, Fgetdta=0x2F,
          Sversion=0x30, Dfree=0x36, Dcreate=0x39, Ddelete=0x3A, Dsetpath=0x3B,
          Tgettime=0x2C, Tsetdate=0x2B, Maddalt=0x14,
          Fcreate=0x3C, Fopen=0x3D, Fclose=0x3E, Fread=0x3F, Fwrite=0x40,
          Fdelete=0x41, Fseek=0x42, Fattrib=0x43, Dgetpath=0x47, Malloc=0x48,
          Fdatime=0x57,
          Mfree=0x49,
          Fsfirst=0x4E, Fsnext=0x4F, Frename=0x56)
EINVFN, EFILNF, EPTHNF, EACCDN, EIHNDL, ENMFIL = -32, -33, -34, -36, -37, -49
ERANGE = -64                          # a seek past the end
FA_RDONLY, FA_SUBDIR = 0x01, 0x10
DATE0 = 0x0021
HANDLE_BASE = 6
DOS_2, DOS_SPARTA, DOS_SDX = 0, 1, 2
KIND = {DOS_2: "DOS 2", DOS_SPARTA: "SpartaDOS 3.2", DOS_SDX: "SpartaDOS X"}

# the scratch: the block, strings, the DTA, a buffer
PB, STR, DTA, BUF = 0, 16, 208, 256
STR_SLOT, BUF_ROOM = 48, 1024


def W(v):
    return ("w", v)


def L(v):
    return ("l", v)


class Gdos:
    """The trap, one call a run; the answers and the DTA read back.  The
    round trips and frames each call cost are the counters' deltas."""

    def __init__(self, r, check):
        self.r, self.check = r, check
        self.frames = self.trips = 0
        self.calls = None

    def string(self, s, slot=0):
        return self.r.stage(STR + slot * STR_SLOT, s.encode("latin-1") + b"\0")

    def call(self, name, *args):
        blk = struct.pack("<lh", 0, FN[name])
        for t, v in args:
            blk += struct.pack("<h" if t == "w" else "<l", v)
        addr = self.r.stage(PB, blk.ljust(16, b"\0"))
        before, rec = self.r.run([(SYS + 2, (), (1,)), (GDOS, (), (addr,))])
        self.check(rec[FAULT_I] == 0, f"{name}: fault {rec[FAULT_I]} during the call")
        self.frames = (rec[FRAMES_I] - before[FRAMES_I]) & 0xFFFF
        if self.calls is not None:
            self.trips = (rec[CIO_I] - self.calls) & 0xFFFF
        self.calls = rec[CIO_I]
        ret = struct.unpack("<l", self.r.read(PB, 4))[0]
        return ret, rec

    def dta(self):
        raw = self.r.read(DTA, 44)
        attrib = raw[21]
        time, date, length = struct.unpack("<HHI", raw[22:30])
        name = raw[30:44].split(b"\0")[0].decode("latin-1")
        return dict(name=name, attr=attrib, size=length, date=date, time=time)

    def listing(self, spec, attr):
        """Fsfirst and Fsnext until ENMFIL: {name: entry}, and the calls."""
        out, cost = {}, []
        ret, rec = self.call("Fsfirst", L(self.string(spec)), W(attr))
        cost.append((self.trips, self.frames))
        while ret == 0:
            e = self.dta()
            out[e["name"]] = e
            ret, rec = self.call("Fsnext")
            cost.append((self.trips, self.frames))
        self.check(ret == ENMFIL, f"listing {spec}: ended with {ret}, not ENMFIL")
        return out, cost


# -- what the image says ---------------------------------------------------------
def packed(e):
    y = e.year + (1900 if e.year >= 80 else 2000)
    return (((y - 1980) << 9) | (e.month << 5) | e.day,
            (e.hour << 11) | (e.minute << 5) | (e.second >> 1))


def image_listing(fs, path=""):
    """{NAME.EXT: (is_dir, size, date, time, read_only)} the way the DTA
    would say it: DOS 2's size is sectors of 125 and its stamp the origin."""
    out = {}
    if isinstance(fs, atr.Dos2):
        for e in fs.entries():
            if e.in_use and e.nameable:
                out[e.filename] = (False, e.count * 125, DATE0, 0, bool(e.flag & 0x20))
    else:
        for e in fs.entries(path):
            d, t = packed(e)
            out[e.filename] = (e.is_dir, e.size, d, t, bool(e.status & 0x01))
    return out


def compare_listing(check, what, got, want, dirs=True):
    names = set(got)
    wnames = {n for n, v in want.items() if dirs or not v[0]}
    check(names == wnames, f"{what}: listed {sorted(names)}, the image has {sorted(wnames)}")
    for n in sorted(names & wnames):
        e, (is_dir, size, date, time, ro) = got[n], want[n]
        check(bool(e["attr"] & FA_SUBDIR) == is_dir, f"{what}: {n} attr ${e['attr']:02X}")
        check(bool(e["attr"] & FA_RDONLY) == ro, f"{what}: {n} read-only {bool(e['attr'] & 1)}, image {ro}")
        if not is_dir:
            check(e["size"] == size, f"{what}: {n} size {e['size']}, image {size}")
        check((e["date"], e["time"]) == (date, time),
              f"{what}: {n} stamp ${e['date']:04X}/${e['time']:04X}, image ${date:04X}/${time:04X}")


# -- the cases -------------------------------------------------------------------
def cases(g, r, check, fs, kind, b, clock=False, dos_clock=False):
    fixture = open(FIXTURE, "rb").read()
    tree = kind != DOS_2
    free0 = fs.free_count()
    g.call("Sversion")                              # primes the counters

    # -- the trivial ones, and the refusal -------------------------------------
    ret, _ = g.call("Sversion")
    check(ret == 0x1500, f"Sversion {ret:#x}")
    ret, _ = g.call("Dgetdrv")
    check(ret == 0, f"Dgetdrv {ret}")
    ret, _ = g.call("Dsetdrv", W(0))
    check(ret & 1, f"Dsetdrv's map {ret:#x} lacks A")
    print(f"  drive map {ret:#04x}")
    # A call this seam does not have: the counter of refusals is what
    # says so, and Maddalt is one -- there is no memory the probe missed
    # to add.  Tsetdate used to be the example; it is served now (phase
    # 42), and a date with day 0 is refused as a bad date, -1, on every
    # machine -- one with a clock too -- without counting as a refusal.
    ret, rec = g.call("Maddalt", L(0), L(0))
    check(ret == EINVFN and rec[BAD_I] == 1, f"Maddalt {ret}, refused {rec[BAD_I]}")
    ret, rec = g.call("Tsetdate", W(0))
    check(ret == -1 and rec[BAD_I] == 1, f"Tsetdate of day 0 {ret}, refused {rec[BAD_I]} "
                                         f"(the count is Maddalt's 1 still)")
    dta = r.sc + DTA
    ret, _ = g.call("Fsetdta", L(dta))
    ret, _ = g.call("Fgetdta")
    check(ret == dta, f"Fgetdta ${ret:06X}, set ${dta:06X}")

    # -- the root, as the image has it -------------------------------------------
    got, cost = g.listing("A:\\*.*", FA_SUBDIR)
    compare_listing(check, "A:\\*.*", got, image_listing(fs))
    print(f"  A:\\*.*  {len(got)} entries: Fsfirst {cost[0][0]} round trip(s), {cost[0][1]} frames; "
          f"Fsnext {max(c[0] for c in cost[1:])} round trip(s) at most, {sum(c[1] for c in cost[1:])} frames")
    check(cost[0][0] <= 3, f"Fsfirst took {cost[0][0]} round trips: no read-ahead")
    check(all(c[0] == 0 for c in cost[1:-1]), "an Fsnext went to the DOS with the cache unread")
    got, _ = g.listing("*.TXT", 0)
    want = {n: v for n, v in image_listing(fs).items() if n.endswith(".TXT")}
    compare_listing(check, "*.TXT", got, want)
    got, _ = g.listing("A:\\*.*", 0)
    check(not any(e["attr"] & FA_SUBDIR for e in got.values()), "attr 0 listed a directory")
    ret, _ = g.call("Fsfirst", L(g.string("A:\\*.ZZZ")), W(0))
    check(ret == ENMFIL, f"Fsfirst *.ZZZ {ret}")
    ret, _ = g.call("Fsfirst", L(g.string("A:\\NOPE\\*.*")), W(FA_SUBDIR))
    check(ret == EPTHNF, f"Fsfirst in a missing directory {ret}, not EPTHNF")
    ret, _ = g.call("Fsfirst", L(g.string("Z:\\*.*")), W(FA_SUBDIR))
    check(ret == -46, f"Fsfirst on Z: {ret}, not EDRIVE")

    # -- directories ---------------------------------------------------------------
    def getpath(drv=0):
        ret, _ = g.call("Dgetpath", L(r.sc + BUF), W(drv))
        check(ret == 0, f"Dgetpath {ret}")
        return r.read(BUF, 64).split(b"\0")[0].decode("latin-1")

    check(getpath() == "", f"Dgetpath at the root: {getpath()!r}")
    ret, _ = g.call("Dsetpath", L(g.string("A:\\SUB")))
    if tree:
        check(ret == 0, f"Dsetpath A:\\SUB {ret}")
        check(getpath() == "\\SUB", f"Dgetpath {getpath()!r}")
        got, _ = g.listing("*.*", FA_SUBDIR)
        compare_listing(check, "SUB", got, image_listing(fs, "SUB"))
        ret, _ = g.call("Dsetpath", L(g.string("deep")))
        check(ret == 0 and getpath() == "\\SUB\\DEEP", f"Dsetpath deep: {ret}, {getpath()!r}")
        got, _ = g.listing("*.*", FA_SUBDIR)
        compare_listing(check, "SUB\\DEEP", got, image_listing(fs, "SUB>DEEP"))
        got, _ = g.listing("..\\*.*", FA_SUBDIR)
        compare_listing(check, "..", got, image_listing(fs, "SUB"))
        ret, _ = g.call("Dsetpath", L(g.string("..")))
        check(ret == 0 and getpath() == "\\SUB", f"Dsetpath ..: {ret}, {getpath()!r}")
        ret, _ = g.call("Dsetpath", L(g.string("A:\\NOPE")))
        check(ret == EPTHNF and getpath() == "\\SUB", f"Dsetpath A:\\NOPE: {ret}, {getpath()!r}")
        check(getpath(2) == "", f"B:'s directory moved: {getpath(2)!r}")
        # the DOS's own current directory did not move: a root name still opens
        ret, _ = g.call("Fopen", L(g.string("A:\\TEST.TXT")), W(0))
        check(ret >= HANDLE_BASE, f"Fopen A:\\TEST.TXT from \\SUB: {ret}")
        g.call("Fclose", W(ret))
        ret, _ = g.call("Fopen", L(g.string("TEST.TXT")), W(0))
        check(ret == EFILNF, f"Fopen TEST.TXT in \\SUB: {ret}, not EFILNF")
    else:
        check(ret == EPTHNF, f"Dsetpath on a flat DOS {ret}, not EPTHNF")
    ret, _ = g.call("Dsetpath", L(g.string("\\")))
    check(ret == 0 and getpath() == "", f"Dsetpath \\: {ret}, {getpath()!r}")

    # -- files, into bank $00 ---------------------------------------------------------
    ret, rec = g.call("Fopen", L(g.string("a:\\test.txt")), W(0))
    check(ret >= HANDLE_BASE, f"Fopen {ret}")
    print(f"  Fopen {g.trips} round trip(s), {g.frames} frames")
    h = ret
    ret, rec = g.call("Fread", W(h), L(BUF_ROOM), L(r.sc + BUF))
    check(ret == len(fixture), f"Fread {ret}, the fixture is {len(fixture)}")
    check(r.read(BUF, len(fixture)) == fixture, "Fread's bytes differ from the fixture")
    print(f"  Fread of {len(fixture)} into bank $00: {g.trips} round trip(s), {g.frames} frames")
    ret, _ = g.call("Fread", W(h), L(BUF_ROOM), L(r.sc + BUF))
    check(ret == 0, f"Fread at the end {ret}")

    # -- Fseek: the count GEMDOS keeps, and where the bytes come from -------------------
    # The file is at its end after the reads above, so this walks back
    # through every mode.  A seek backwards reopens the file on its own
    # IOCB (src/sys/gemdos.c, gd_seek), which the handle staying valid
    # is the visible proof of.
    n = len(fixture)
    ret, _ = g.call("Fseek", L(0), W(h), W(1))
    check(ret == n, f"Fseek(0, h, 1) at the end says {ret}, not {n}")
    ret, _ = g.call("Fseek", L(0), W(h), W(0))
    check(ret == 0, f"Fseek(0, h, 0) says {ret}, not 0")
    ret, _ = g.call("Fread", W(h), L(4), L(r.sc + BUF))
    check(ret == 4 and r.read(BUF, 4) == fixture[:4],
          f"after a rewind: {ret} bytes {r.read(BUF, 4)!r}, not {fixture[:4]!r}")
    ret, _ = g.call("Fseek", L(5), W(h), W(0))
    check(ret == 5, f"Fseek(5, h, 0) says {ret}, not 5")
    ret, _ = g.call("Fread", W(h), L(4), L(r.sc + BUF))
    check(ret == 4 and r.read(BUF, 4) == fixture[5:9],
          f"at 5: {r.read(BUF, 4)!r}, not {fixture[5:9]!r}")
    ret, _ = g.call("Fseek", L(-2), W(h), W(1))     # back two, within the file
    check(ret == 7, f"Fseek(-2, h, 1) says {ret}, not 7")
    ret, _ = g.call("Fseek", L(0), W(h), W(2))
    check(ret == n, f"Fseek(0, h, 2) says {ret}, not the {n} the file is")
    ret, _ = g.call("Fseek", L(-4), W(h), W(2))
    check(ret == n - 4, f"Fseek(-4, h, 2) says {ret}, not {n - 4}")
    ret, _ = g.call("Fread", W(h), L(4), L(r.sc + BUF))
    check(ret == 4 and r.read(BUF, 4) == fixture[-4:],
          f"the last four: {r.read(BUF, 4)!r}, not {fixture[-4:]!r}")
    ret, _ = g.call("Fseek", L(1), W(h), W(2))
    check(ret == ERANGE, f"a seek past the end says {ret}, not ERANGE")
    ret, _ = g.call("Fseek", L(-1), W(h), W(0))
    check(ret == ERANGE, f"a seek before the start says {ret}, not ERANGE")
    print(f"  Fseek through all three modes: {g.trips} round trip(s), {g.frames} frames")

    # -- Fdatime: the stamp out of the directory, without disturbing a search --------
    # A DOS 2 disk has no stamps and answers zeros, which is what the ST
    # answers for a file system without them; a SpartaDOS carries them,
    # and the image says what they are.
    want = None
    for e in fs.entries("") if tree else fs.entries():
        if e.filename.upper() == "TEST.TXT":
            want = e
    g.call("Fsfirst", L(g.string("A:\\*.*")), W(FA_SUBDIR))    # a walk to disturb
    first = r.read(DTA + 30, 14)
    ret, _ = g.call("Fdatime", L(r.sc + BUF), W(h), W(0))
    check(ret == 0, f"Fdatime {ret}")
    t, d = struct.unpack("<2H", r.read(BUF, 4))
    if tree:
        y = 2000 + want.year if want.year < 80 else 1900 + want.year
        wd = ((y - 1980) << 9) | (want.month << 5) | want.day
        wt = (want.hour << 11) | (want.minute << 5) | (want.second >> 1)
        check((t, d) == (wt, wd),
              f"Fdatime says {t:#06x}/{d:#06x}, the image says {wt:#06x}/{wd:#06x}")
    else:
        # No stamps on the disk: the same epoch Fsfirst reports for one,
        # 1 January 1980, so the two answers agree about the same file.
        check((t, d) == (0, DATE0),
              f"Fdatime on a DOS with no stamps says {t:#06x}/{d:#06x}, "
              f"not the 0/{DATE0:#06x} its directory reports")
    check(r.read(DTA + 30, 14) == first,
          "Fdatime moved the application's DTA: a search would lose its place")
    ret, _ = g.call("Fsnext")
    check(ret == 0, f"Fsnext after Fdatime {ret}: the search did not survive")
    print(f"  Fdatime: {t:#06x}/{d:#06x}, the search kept its place")

    # -- Tgetdate and Tgettime: the machine's clock ----------------------------------
    # The Atari has none; the Ultimate 1MB does, a DS1305 bit-banged
    # through $D3E2 (src/sys/clock.c).  A machine without one reads a
    # register nothing drives and fails the check that what came back is a
    # plausible time -- and then ASKS THE DOS, because a SpartaDOS may have
    # a clock driver for hardware gem4xe knows nothing about (an IDE Plus
    # 2, an R-Time 8).  SpartaDOS X always answers kd_gettd: from that
    # driver where one is loaded, and from its own software clock where
    # none is, which is why the X in a cartridge on a clockless machine
    # has a time and SpartaDOS 3.2 -- which is not asked -- has the epoch.
    # `clock` is a chip the host drives; `dos_clock` is the DOS's answer.
    date, _ = g.call("Tgetdate")
    time, _ = g.call("Tgettime")
    y, mo, dd = 1980 + (date >> 9), (date >> 5) & 15, date & 31
    hh, mi, ss = time >> 11, (time >> 5) & 63, (time & 31) * 2
    print(f"  Tgetdate/Tgettime: {y:04d}-{mo:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}"
          + ("" if clock else "  (the DOS's own clock)" if dos_clock
             else "  (no clock: the epoch)"))
    if clock:
        now = datetime.datetime.now()
        check((y, mo, dd) == (now.year, now.month, now.day),
              f"Tgetdate says {y:04d}-{mo:02d}-{dd:02d}, the host says "
              f"{now.year:04d}-{now.month:02d}-{now.day:02d}")
        near = abs((hh * 3600 + mi * 60 + ss)
                   - (now.hour * 3600 + now.minute * 60 + now.second))
        check(near < 120 or near > 86280,
              f"Tgettime says {hh:02d}:{mi:02d}:{ss:02d}, the host says "
              f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}")
    elif dos_clock:
        # Not the host's time -- it is the X's own, made up and fixed -- so
        # what is asserted is that it came from the DOS at all rather than
        # being invented here.  A user who typed DATE has set it, and then
        # it is the right answer (src/sys/clock.c, dos_clock).
        check((date, time) != (DATE0, 0),
              f"SpartaDOS X answers kd_gettd, so Tgetdate/Tgettime should be "
              f"the DOS's clock, not the epoch {DATE0:#06x}/0")
    else:
        check((date, time) == (DATE0, 0),
              f"with no clock Tgetdate/Tgettime say {date:#06x}/{time:#06x}, "
              f"not the epoch {DATE0:#06x}/0")

    # ...AND THE PIA IS STILL THE PIA.  $D3E2 is the U1MB's RTC, but on a
    # machine without one it is the PIA mirrored -- $D3E2 & 3 == 2 is
    # PACTL -- and bit 2 of PACTL is what makes $D300 the joystick port
    # rather than its direction register.  Bit-banging the clock through
    # an address that is really PACTL leaves it at 0, and then the mouse's
    # quadrature reads a flat 0 and the pointer never moves again.  It did
    # exactly that until the probe went read-only (docs/phase30.md).  So
    # the two calls above are followed by the question no gate asked: is
    # the joystick port still there?
    pactl = b.ok("EVAL db($d302)").get("value")
    check(pactl & 0x04,
          f"after Tgetdate/Tgettime PACTL is ${pactl:02X}: bit 2 is clear, so "
          f"$D300 now reads DDRA and not the joystick port -- the clock was "
          f"driven through the PIA")
    print(f"  PACTL after the clock: ${pactl:02X} "
          f"({'the joystick port' if pactl & 4 else 'DDRA -- BROKEN'})")

    ret, _ = g.call("Fclose", W(h))
    check(ret == 0, f"Fclose {ret}")
    ret, _ = g.call("Fseek", L(0), W(h), W(0))
    check(ret == EIHNDL, f"Fseek on a closed handle {ret}, not EIHNDL")
    ret, _ = g.call("Fdatime", L(r.sc + BUF), W(h), W(0))
    check(ret == EIHNDL, f"Fdatime on a closed handle {ret}, not EIHNDL")
    ret, _ = g.call("Fclose", W(h))
    check(ret == EIHNDL, f"Fclose twice {ret}, not EIHNDL")
    # A standard handle is there to close: it goes back to its device
    # and answers E_OK, as EmuTOS's xclose does (bdos/fsopnclo.c).
    ret, _ = g.call("Fclose", W(3))
    check(ret == 0, f"Fclose of a standard handle {ret}, not E_OK")
    ret, _ = g.call("Fopen", L(g.string("A:\\NOPE.TXT")), W(0))
    check(ret == EFILNF, f"Fopen NOPE.TXT {ret}, not EFILNF")
    if tree:
        ret, _ = g.call("Fopen", L(g.string("A:\\SUB\\DEEP\\THREE.TXT")), W(0))
        check(ret >= HANDLE_BASE, f"Fopen three levels down {ret}")
        n, _ = g.call("Fread", W(ret), L(64), L(r.sc + BUF))
        check(n == 6 and r.read(BUF, 6) == b"three\x9b", f"THREE.TXT: {n} bytes {r.read(BUF, 6)!r}")
        g.call("Fclose", W(ret))
    else:
        ret, _ = g.call("Fopen", L(g.string("A:\\SUB\\ONE.TXT")), W(0))
        check(ret == EPTHNF, f"Fopen with a directory on a flat DOS {ret}, not EPTHNF")

    # -- far memory: Malloc, Fread into it, Fwrite out of it ----------------------------
    ret, _ = g.call("Malloc", L(-1))
    check(ret > 0x10000, f"Malloc(-1) {ret:#x}")
    print(f"  Malloc(-1): {ret} bytes free above bank $00")
    far, _ = g.call("Malloc", L(4096))
    check(far > 0xFFFF, f"Malloc(4096) ${far:06X} is not far")
    h, _ = g.call("Fopen", L(g.string("TEST.TXT")), W(0))
    ret, rec = g.call("Fread", W(h), L(4096), L(far))
    check(ret == len(fixture), f"Fread into far memory {ret}")
    print(f"  Fread of {len(fixture)} into ${far:06X}: {g.trips} round trip(s), {g.frames} frames")
    g.call("Fclose", W(h))
    sample = bytes(b.cmd(f"EVAL db(${far + i:06X})").get("value") for i in range(8))
    check(sample == fixture[:8], f"far bytes {sample!r}, fixture {fixture[:8]!r}")
    h, _ = g.call("Fcreate", L(g.string("A:\\GDOUT.TXT")), W(0))
    check(h >= HANDLE_BASE, f"Fcreate {h}")
    ret, _ = g.call("Fwrite", W(h), L(len(fixture)), L(far))
    check(ret == len(fixture), f"Fwrite from far memory {ret}")
    ret, _ = g.call("Fclose", W(h))
    check(ret == 0, f"Fclose after Fwrite {ret}")
    h, _ = g.call("Fopen", L(g.string("GDOUT.TXT")), W(0))
    r.stage(BUF, b"\xEE" * BUF_ROOM)
    ret, _ = g.call("Fread", W(h), L(BUF_ROOM), L(r.sc + BUF))
    check(ret == len(fixture) and r.read(BUF, len(fixture)) == fixture,
          f"GDOUT.TXT read back: {ret} bytes, {'the same' if r.read(BUF, len(fixture)) == fixture else 'DIFFERENT'}")
    g.call("Fclose", W(h))

    # -- rename, lock, delete, each seen through Fsfirst --------------------------------
    ret, _ = g.call("Frename", W(0), L(g.string("GDOUT.TXT")), L(g.string("A:\\GDOUT2.TXT", 1)))
    check(ret == 0, f"Frename {ret}")
    got, _ = g.listing("GDOUT*.*", 0)
    check(set(got) == {"GDOUT2.TXT"}, f"after Frename: {sorted(got)}")
    ret, _ = g.call("Fattrib", L(g.string("GDOUT2.TXT")), W(1), W(FA_RDONLY))
    check(ret == 0, f"Fattrib read-only {ret}")
    got, _ = g.listing("GDOUT2.TXT", 0)
    locked = bool(got.get("GDOUT2.TXT", {}).get("attr", 0) & FA_RDONLY)
    if not locked and kind == DOS_SDX and ret == 0:
        # SpartaDOS X before 4.49f: "XIO 35 worked by accident, fixed"
        # (whatsnew-450.txt).  The 4.49b in a 2016 U1MB flash answers the
        # lock with OK and does nothing; that is the DOS, not the port.
        print("  NOTE: the DOS accepted the lock and did not apply it "
              "(SpartaDOS X before 4.49f); the locked-file checks are skipped")
    else:
        check(locked, f"not read-only after Fattrib: {got}")
        ret, _ = g.call("Fdelete", L(g.string("GDOUT2.TXT")))
        check(ret == EACCDN, f"Fdelete of a locked file {ret}, not EACCDN")
        ret, _ = g.call("Fattrib", L(g.string("GDOUT2.TXT")), W(1), W(0))
    ret, _ = g.call("Fdelete", L(g.string("GDOUT2.TXT")))
    check(ret == 0, f"Fdelete {ret}")
    ret, _ = g.call("Fsfirst", L(g.string("GDOUT*.*")), W(0))
    check(ret == ENMFIL, f"after Fdelete: {ret}")
    ret, _ = g.call("Fdelete", L(g.string("GDOUT2.TXT")))
    check(ret == EFILNF, f"Fdelete twice {ret}, not EFILNF")

    # -- the scrap: SCRAP.* deleted, and NOTHING else ----------------------------------
    # scrp_clear (opcode 82) is the one AES call that reaches the disk,
    # so it is gated here rather than against a host model: the files are
    # made with GEMDOS, cleared through the runner's sys op 18, and
    # looked for again with Fsfirst.  SCRIP.TXT is the control -- one
    # letter away from the mask, and a walk that deletes it is a walk
    # that would take a program's own files with the scrap.
    #
    # In a FOLDER, made and removed here, and not in the root: three
    # files in the root grow a SpartaDOS directory by a sector that
    # deleting them does not give back, and the Dfree check below wants
    # the disk it started with.  It is also the shape the Compendium
    # describes (p.352) -- C:\CLIPBRD\, the trailing backslash and all.
    # A flat DOS has no folder, so there it is the root, whose directory
    # is a fixed eight sectors and cannot grow.
    scrapdir = "A:\\CLIPBRD\\" if tree else "A:\\"
    if tree:
        ret, _ = g.call("Dcreate", L(g.string("A:\\CLIPBRD")))
        check(ret == 0, f"Dcreate CLIPBRD {ret}")
    for name in ("SCRAP.TXT", "SCRAP.DAT", "SCRIP.TXT"):
        h, _ = g.call("Fcreate", L(g.string(scrapdir + name)), W(0))
        check(h >= HANDLE_BASE, f"Fcreate {name} {h}")
        g.call("Fclose", W(h))
    got, _ = g.listing(scrapdir + "SCR*.*", 0)
    check(set(got) == {"SCRAP.TXT", "SCRAP.DAT", "SCRIP.TXT"},
          f"the three files were not made: {sorted(got)}")
    rec = r.run([(SCRAP, (), (g.string(scrapdir),))])[0][2:]
    check(rec[6] == 1, f"scrp_write answered {rec[6]}")
    check(rec[7] == 1, f"scrp_clear answered {rec[7]}, not TRUE")
    got, _ = g.listing(scrapdir + "SCR*.*", 0)
    check(set(got) == {"SCRIP.TXT"},
          f"after scrp_clear {scrapdir} holds {sorted(got)}")
    # WHAT IS THERE, not what should be: the line above is a check and
    # this is a report, and a report that names the expected answer says
    # "SCRIP.TXT kept" just as cheerfully when the walk has deleted it.
    print(f"  scrp_clear in {scrapdir}: SCR*.* now {sorted(got) or 'empty'}")
    ret, _ = g.call("Fdelete", L(g.string(scrapdir + "SCRIP.TXT")))
    check(ret == 0, f"Fdelete of the control file {ret}")
    if tree:
        ret, _ = g.call("Ddelete", L(g.string("A:\\CLIPBRD")))
        check(ret == 0, f"Ddelete CLIPBRD {ret}")
    # AND IT REFUSES WHEN THERE IS NO SCRAP DIRECTORY, which is the
    # donor's only refusal and the one an application acts on.
    rec = r.run([(SCRAP, (), (g.string(""),))])[0][2:]
    check(rec[7] == 0, f"scrp_clear with no scrap directory answered {rec[7]}, not FALSE")

    # -- directories made and removed --------------------------------------------------
    ret, _ = g.call("Dcreate", L(g.string("A:\\NEWDIR")))
    if tree:
        check(ret == 0, f"Dcreate {ret}")
        got, _ = g.listing("A:\\NEWDIR", FA_SUBDIR)
        check(got.get("NEWDIR", {}).get("attr") == FA_SUBDIR, f"NEWDIR after Dcreate: {got}")
        ret, _ = g.call("Dsetpath", L(g.string("A:\\NEWDIR")))
        check(ret == 0, f"Dsetpath into the new directory {ret}")
        ret, _ = g.call("Fsfirst", L(g.string("*.*")), W(FA_SUBDIR))
        check(ret == ENMFIL, f"the new directory lists {ret}")
        g.call("Dsetpath", L(g.string("\\")))
        # A FOLDER renamed, which is what the desktop's Show info asks
        # for when the item selected is one (src/desk/deskfun.c).
        ret, _ = g.call("Frename", W(0), L(g.string("A:\\NEWDIR")),
                        L(g.string("A:\\NEWDIR2", 1)))
        got, _ = g.listing("A:\\*.*", FA_SUBDIR)
        print(f"  Frename of a folder: {ret}; the root now has "
              f"{'NEWDIR2' if 'NEWDIR2' in got else 'NEWDIR'}")
        gone = "A:\\NEWDIR2" if "NEWDIR2" in got else "A:\\NEWDIR"
        ret, _ = g.call("Ddelete", L(g.string(gone)))
        check(ret == 0, f"Ddelete {ret}")
        ret, _ = g.call("Fsfirst", L(g.string("A:\\NEWDIR")), W(FA_SUBDIR))
        check(ret == ENMFIL, f"NEWDIR after Ddelete: {ret}")
    else:
        check(ret == EACCDN, f"Dcreate on a flat DOS {ret}, not EACCDN")

    # -- Dfree against the bitmap ------------------------------------------------------
    ret, rec = g.call("Dfree", L(r.sc + BUF), W(0))
    check(ret == 0, f"Dfree {ret}")
    b_free, b_total, secsiz, clsiz = struct.unpack("<4l", r.read(BUF, 16))
    print(f"  Dfree: {b_free} free sectors of {secsiz} (image {free0}), "
          f"{g.trips} round trip(s), {g.frames} frames")
    # EXACT, and it did not use to be.  Dfree reads the file system's own
    # count now -- the VTOC on a DOS 2 disk, the superblock on a SpartaDOS
    # one, one sector through SIO -- rather than the three characters a
    # directory listing gives it, which could not say more than 999 and
    # which the two DOSes spell differently when it overflows (the old
    # rule is m14_sparta.sayable_free, and the listing is still the
    # fallback for a drive that will not answer SIO).
    check(b_free == free0,
          f"Dfree says {b_free} free, the image's bitmap says {free0}")
    check(secsiz == fs.img.sector_size,
          f"Dfree says {secsiz}-byte sectors, the image has {fs.img.sector_size}")
    check(b_total >= free0,
          f"Dfree says {b_total} sectors in all, fewer than the {free0} free")
    check(clsiz == 1, f"Dfree says {clsiz} sectors to a cluster, not 1")

    # -- the exit ----------------------------------------------------------------------
    h, _ = g.call("Fopen", L(g.string("TEST.TXT")), W(0))
    ret, _ = g.call("Fsfirst", L(g.string("A:\\*.*")), W(FA_SUBDIR))
    check(ret == 0, f"Fsfirst before the exit {ret}")
    rec = r.run([(RELEASE, (), ())])[0]
    check(rec[FAULT_I] == 0, "fault in gemdos_release")
    g.calls = None
    ret, _ = g.call("Fclose", W(h))
    check(ret == EIHNDL, f"Fclose after the exit {ret}: the handle was not closed")
    ret, _ = g.call("Fsnext")
    check(ret == ENMFIL, f"Fsnext after the exit {ret}: the search was not freed")
    ret, _ = g.call("Fgetdta")
    check(ret != dta, "the DTA was not reset at the exit")
    h, _ = g.call("Fopen", L(g.string("TEST.TXT")), W(0))
    check(h >= HANDLE_BASE, f"Fopen after the exit {h}: the IOCB was not given back")
    g.call("Fclose", W(h))


def main(argv):
    cart = flash = None
    dos2 = "--dos2" in argv
    for a in argv:
        if a.startswith("--sdx="):
            cart = a[6:]
        elif a.startswith("--u1mb="):
            flash = a[7:]
    kind = DOS_2 if dos2 else DOS_SDX if (cart or flash) else DOS_SPARTA
    tag = {DOS_2: "m15d", DOS_SPARTA: "m15", DOS_SDX: "m15u" if flash else "m15x"}[kind]
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    if dos2:
        disk = DOS2DISK
        fs = atr.Dos2(atr.ATRImage.load(disk))
        args = ["--disk", disk, "--disk", D2]
    else:
        disk = SPDISK
        fs = atr.Sdfs(atr.ATRImage.load(disk))
        args = ["--disk", disk] + (["--cart", cart] if cart else []) \
            + (["--u1mbrom", flash] if flash else [])   # see m14_sparta.py
    print(f"{KIND[kind]}: {os.path.basename(cart or flash or disk)}"
          + (" (U1MB flash)" if flash else ""))
    emu = launch(tag=tag, memsize="1088K", extra_args=args, require_real_rom=not flash)
    b = emu.bridge
    try:
        if dos2:
            b.frames(300)
            b.poke(0xD1FF, 0x01)
            b.poke(0xD191, 0x00)
            b.frames(500)
            for k in ("L", "M", "3", "RETURN"):
                b.key(k)
                b.frames(10)
            b.frames(200)
            st = b""
            for _ in range(200):
                st = bytes(b.memdump(STATUS, 14))
                if st[:2] == b"VD" and st[2] == 1:
                    break
                b.frames(4)
            if st[:2] != b"VD" or st[2] != 1:
                st = None
        else:
            _, st = boot(b)
        if st is None:
            print("FAIL: the runner did not come up")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        check(st[8] == kind, f"the seam says DOS kind {st[8]}, expected {kind}")
        r = Runner(b, syms)
        g = Gdos(r, check)
        print("GEMDOS on CIO, against the image:")
        cases(g, r, check, fs, kind, b, clock=bool(flash),
              dos_clock=(kind == DOS_SDX and not flash))
    finally:
        emu.stop()

    print(f"gem4xe-m15: {'PASS' if not fails else 'FAIL'} -- GEMDOS on {KIND[kind]}, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
