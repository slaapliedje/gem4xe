#!/usr/bin/env python3
"""Phase 11 gate: the file layer.

CIO first.  gem4xe runs in native mode with the OS's vectors replaced,
and the OS's I/O runs in emulation mode through the vectors it filled
itself; src/sys/cio.s is the round trip between the two (S, D, DB,
POKMSK, CRITIC, the emulation vectors left intact when the ROM was
copied, the frames RTCLOK counted while the handlers were bypassed, and
a key the OS put in CH).  The runner's sys ops 3005-3009 make one CIO
call each, so the host can open, read, write and list the disk it built
(tools/mkdisk.py, with TEST.TXT alongside the runner) and compare what
came back with what it put there -- and check, after each call, that
the native handlers are still counting and nothing faulted.

Then the AES on top of it.  rsrc_load reads the resource the host built
(tools/mkrsc.py) and fixes it up in the application pool; the gate reads
the whole image back out of bank $00 and compares it byte for byte with
what tools/rsc.py says the fixup leaves -- every pointer, every rectangle,
every TEDINFO length -- then asks rsrc_gaddr for every address the file
holds, fixes a raw tree object by object through rsrc_obfix, and draws the
loaded dialog against tools/aesref.py on the screen.  The shell library's
buffers round-trip through far memory, its environment hands back a
bank-$00 string, and shel_find asks the disk.  The scrap manager's
directory round-trips the same way: it is the other thing the AES keeps
on the applications' behalf rather than its own, and the clipboard is
files in the directory it names (src/aes/scrap.c).
"""
import os
import re
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import vdiref, aesref, vbxeref, symfile, atr, mkrsc, rsc, fselrsc  # noqa: E402
from m7_form import poke16, NOT_STARTED, STATUS, ST_GO, ST_DONE, DISK, SYMS  # noqa: E402
from m4_aes import PRELUDE, FULL, OBJC_DRAW, SHOTDIR    # noqa: E402

SYS = 3000
OPEN, CLOSE, READ, WRITE, GETREC, FRAMES = SYS + 5, SYS + 6, SYS + 7, SYS + 8, SYS + 9, SYS + 2
CIONAME, ALLOC = SYS + 10, SYS + 11
# the runner's AES ops for the file layer (src/m3_vdi.c)
RSRC_LOAD, RSRC_FREE, RSRC_GADDR, RSRC_SADDR, RSRC_OBFIX = 1110, 1111, 1112, 1113, 1114
SHEL_READ, SHEL_WRITE, SHEL_GET, SHEL_PUT, SHEL_FIND, SHEL_ENVRN = 1120, 1121, 1122, 1123, 1124, 1125
SCRP_READ, SCRP_WRITE = 1080, 1081
# the AES's character cell and screen width, what the fixup scales by
WCHAR, HCHAR, WIDTH = 8, 8, 640
RSC_FILE = os.path.join(ROOT, "build", "test.rsc")
# src/sys/cio.h
A_READ, A_DIR, A_WRITE = 4, 6, 8
OK, OK_EOF, E_EOF, E_NOTFOUND = 1, 3, 0x88, 0xAA
EOL = 0x9B
# a sys op's record: intout[0..5] the handler's state, then the op's own
FRAMES_I, TIMER_I, KEYS_I, FAULT_I, ST_I, GOT_I, CALLS_I = 2, 3, 6, 7, 8, 9, 10

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "test.txt")


class Runner:
    """One script per run: the runner resets its record count each time,
    so a call whose result the next call needs (an IOCB number) gets its
    own run."""

    def __init__(self, b, syms):
        self.b, self.syms = b, syms
        self.sa, self.sc = syms["vdi_script"], syms["vdi_scratch"]
        self.results, self.count = syms["vdi_results"], syms["vdi_result_count"]
        self.script_room = min(a for a in syms.values() if a > self.sa) - self.sa
        self.scratch_room = min(a for a in syms.values() if a > self.sc) - self.sc

    def run(self, script):
        b = self.b
        words = aesref.encode(script, 0)
        assert len(words) * 2 <= self.script_room
        b.memload(self.sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                                    for w in words))
        b.poke(STATUS + ST_DONE, 0)
        poke16(b, self.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)
        for _ in range(600):
            if b.peek(STATUS + ST_DONE) == 0xA5:
                break
            b.frames(4)
        else:
            raise RuntimeError("the runner did not finish")
        # ST_DONE is set the moment the last op returns, which can be in
        # the middle of a frame the screenshot would otherwise show: the
        # frame is scanned out as the blits land, so a shot of it catches
        # a string half drawn.  One more frame is scanned after the
        # drawing has stopped; two is the margin.
        b.frames(2)
        n = b.peek16(self.count)
        assert n == len(script), (n, len(script))
        return vdiref.decode(b.memdump(self.results, n * vdiref.RESULT_WORDS * 2), n)

    def stage(self, off, data):
        assert off + len(data) <= self.scratch_room
        self.b.memload(self.sc + off, bytes(data))
        return self.sc + off

    def read(self, off, n):
        return bytes(self.b.memdump(self.sc + off, n))


def cio_cases(r, check):
    """Open, read, list, write, read back -- against the disk the host built."""
    fixture = open(FIXTURE, "rb").read()
    b = r.b

    def sysop(op, *ints):
        rec = r.run([(op, (), ints)])[0]
        check(rec[FAULT_I] == 0, f"op {op}: fault {rec[FAULT_I]} during the call")
        return rec

    def opened(name, aux1):
        addr = r.stage(0, name.encode("latin-1") + b"\0")
        rec = sysop(OPEN, addr, aux1, 0)
        return rec[ST_I], rec

    # -- the handlers keep time across a call ------------------------------
    before = sysop(FRAMES, 1)
    iocb, rec = opened("D:TEST.TXT", A_READ)
    print(f"  open D:TEST.TXT -> IOCB {iocb}, {rec[CALLS_I]} round trip(s), "
          f"frames {before[FRAMES_I]} -> {rec[FRAMES_I]}, timer {before[TIMER_I]} -> {rec[TIMER_I]}")
    check(1 <= iocb <= 7, f"open returned {iocb}")
    check((rec[FRAMES_I] - before[FRAMES_I]) & 0xFFFF >= 1,
          "irq_frames did not advance across the open: RTCLOK was not folded in")
    check((rec[TIMER_I] - before[TIMER_I]) & 0xFFFF >= 1,
          "irq_timer stopped: POKEY was not given back after the call")
    if not 1 <= iocb <= 7:
        return

    # -- read exactly the file, then past its end ---------------------------
    buf = r.stage(64, b"\xEE" * 256)
    rec = sysop(READ, iocb, buf, len(fixture))
    got = r.read(64, len(fixture))
    # the FMS reports the end with the last byte: $03, not $01
    check(rec[ST_I] in (OK, OK_EOF) and rec[GOT_I] == len(fixture),
          f"read {len(fixture)}: status ${rec[ST_I] & 0xFF:02X}, {rec[GOT_I]} bytes")
    check(got == fixture, "the bytes read differ from the fixture")
    rec = sysop(READ, iocb, buf, 16)
    check(rec[ST_I] == E_EOF and rec[GOT_I] == 0,
          f"read at end: status ${rec[ST_I] & 0xFF:02X}, {rec[GOT_I]} bytes; expected EOF and 0")
    rec = sysop(CLOSE, iocb)
    check(rec[ST_I] == OK, f"close: status ${rec[ST_I] & 0xFF:02X}")
    check(b.peek(0x0340 + iocb * 16) == 0xFF, "the IOCB is not free after close")

    # -- a short read, then the record reader --------------------------------
    iocb, _ = opened("D:TEST.TXT", A_READ)
    rec = sysop(READ, iocb, buf, 256)
    check(rec[ST_I] == E_EOF and rec[GOT_I] == len(fixture),
          f"read 256 of {len(fixture)}: status ${rec[ST_I] & 0xFF:02X}, {rec[GOT_I]} bytes")
    sysop(CLOSE, iocb)
    iocb, _ = opened("TEST.TXT", A_READ)            # no device: cio_open adds D:
    lines = []
    while True:
        rec = sysop(GETREC, iocb, buf, 80)
        if rec[GOT_I]:          # the unterminated last line comes with $88
            lines.append(r.read(64, rec[GOT_I]))
        if rec[ST_I] not in (OK, OK_EOF):
            break
    want = fixture.split(b"\x9b")
    got = [ln.rstrip(b"\x9b") for ln in lines]
    check(got == want, f"getrec lines {got} differ from the fixture's {want}")
    check(rec[ST_I] == E_EOF, f"getrec after the last line: status ${rec[ST_I] & 0xFF:02X}")
    sysop(CLOSE, iocb)

    # -- a name that is not there ----------------------------------------------
    st, rec = opened("D:NOSUCH.FIL", A_READ)
    check(st == -E_NOTFOUND, f"open of a missing file returned {st}, expected {-E_NOTFOUND}")
    check(all(b.peek(0x0340 + i * 16) == 0xFF for i in range(1, 8)),
          "an IOCB was left open by the failed open")

    # -- the directory ---------------------------------------------------------
    def listing():
        iocb, _ = opened("D:*.*", A_DIR)
        out = []
        while True:
            rec = sysop(GETREC, iocb, buf, 80)
            if rec[GOT_I]:
                out.append(r.read(64, rec[GOT_I]).rstrip(b"\x9b").decode("latin-1"))
            if rec[ST_I] not in (OK, OK_EOF):
                break
        sysop(CLOSE, iocb)
        return out

    names = listing()
    print("  directory:")
    for ln in names:
        print(f"    |{ln}|")
    # DOS 2: "NNN FREE SECTORS"; DOS II+: "NNNN Free NN Fil-S".  The count
    # first, the word after -- what src/aes/fsel.c goes by too.
    check(names and re.match(r"^\s*\d+ FREE", names[-1], re.I),
          "the listing does not end in the free-sector line")
    for fn in ("M3         ", "TEST    TXT"):
        check(any(fn in ln for ln in names), f"{fn!r} is not in the listing")
    # The disk is DOUBLE density (tools/mkdisk.py, and the Makefile's note
    # about why): getting this far means the fixture DOS read 256-byte
    # sectors to load the runner.  Its free count must be the one
    # tools/atr.py computed, and the runner's size the sectors it was
    # given -- a DOS reading the disk as single density would show
    # neither.
    disk = atr.Dos2(atr.ATRImage.load(DISK))
    m3 = disk.find("M3")
    want_free = disk.free_count()
    m = re.match(r"^\s*(\d+) FREE", names[-1], re.I)
    got_free = int(m.group(1)) if m else -1
    check(got_free == want_free,
          f"the DOS reports {got_free} free sectors, the image holds {want_free}")
    check(any(re.search(rf"M3\s+0*{m3.count}\b", ln) for ln in names),
          f"M3 is not listed with its {m3.count} sectors")
    print(f"  {disk.img!r}: M3 {m3.count} sectors from {m3.start}, flag ${m3.flag:02X}; "
          f"{got_free} free, as the image says")

    # -- write, then read back -------------------------------------------------
    # OUT.TXT is already on the image (DISK_FILES in the Makefile) holding
    # other bytes: the emulator's disk changes under this run and the host's
    # image does not, so a name written here would be one the file selector
    # lists later and the model, reading the image, does not.  Overwriting a
    # file that is there leaves the directory alone -- and makes the read-back
    # the proof of the write, since the fixture's own bytes are what a failed
    # write would leave behind.
    text = b"written by gem4xe\x9bthrough CIO\x9b"
    src = r.stage(128, text)
    iocb, rec = opened("D:OUT.TXT", A_WRITE)
    check(1 <= iocb <= 7, f"open for write returned {iocb}")
    if 1 <= iocb <= 7:
        rec = sysop(WRITE, iocb, src, len(text))
        check(rec[ST_I] == OK, f"write: status ${rec[ST_I] & 0xFF:02X}")
        rec = sysop(CLOSE, iocb)
        check(rec[ST_I] == OK, f"close after write: status ${rec[ST_I] & 0xFF:02X}")
        iocb, _ = opened("D:OUT.TXT", A_READ)
        r.stage(64, b"\xEE" * 64)
        rec = sysop(READ, iocb, buf, len(text))
        check(rec[ST_I] in (OK, OK_EOF) and r.read(64, len(text)) == text,
              f"read back: status ${rec[ST_I] & 0xFF:02X}, bytes {r.read(64, len(text))!r}")
        sysop(CLOSE, iocb)
        names = listing()
        check(any("OUT     TXT" in ln for ln in names), "OUT.TXT is not in the listing after the write")

    # -- and time still passes ---------------------------------------------------
    t0, t1 = r.run([(FRAMES, (), (1,)), (FRAMES, (), (10,))])   # one run: no host latency between
    df, dt = (t1[FRAMES_I] - t0[FRAMES_I]) & 0xFFFF, (t1[TIMER_I] - t0[TIMER_I]) & 0xFFFF
    print(f"  after the calls: {df} frames, {dt} timer ticks over a 10-frame wait; "
          f"{t1[KEYS_I]} key(s) queued; {rec[CALLS_I]} round trips in all")
    check(10 <= df <= 11, f"{df} frames counted over a 10-frame wait")
    check(dt >= 10 * 40, f"only {dt} timer ticks over 10 frames: the sampler is not running")


def region_of(r, off):
    """Which part of the resource file an offset falls in, for a report."""
    marks = [("header", 0), ("strings", r.o_string), ("image data", r.o_imdata),
             ("BITBLKs", r.o_bitblk), ("ICONBLKs", r.o_iconblk),
             ("TEDINFOs", r.o_tedinfo), ("OBJECTs", r.o_object),
             ("frstr table", r.o_frstr), ("frimg table", r.o_frimg),
             ("trindex", r.o_trindex)]
    name = marks[0][0]
    for n, start in marks:
        if off >= start:
            name = n
    return name


def rsrc_cases(r, check, b, keep):
    # a record is contrl[2], contrl[4], then intout[]: the helpers hand back
    # intout so an index here is the runner's (src/m3_vdi.c)
    sysop = lambda op, *ints: r.run([(op, (), ints)])[0][2:]     # noqa: E731
    aes = lambda op, ints=(), addr=0: r.run([(op, (), ints, addr)])[0][2:]  # noqa: E731

    # The AES's cell size and screen width come from gsx_start, and so
    # the fixup's; the PRELUDE puts both sides in the same state.
    r.run(PRELUDE)
    R = mkrsc.build()
    R.layout()                      # sizes and offsets, before anything asks
    rsc_bytes = open(RSC_FILE, "rb").read()
    before = sysop(ALLOC)
    print(f"  pool: mark ${before[6] & 0xFFFF:04X}, {before[7]} bytes free; "
          f"far break ${before[9] & 0xFFFF:02X}{before[8] & 0xFFFF:04X}")

    # -- the GEM name --------------------------------------------------------------
    for gem, want in (("A:\\TEST.RSC", "D1:TEST.RSC"), ("b:\\gem\\test.rsc", "D2:TEST.RSC"),
                      ("test.rsc", "TEST.RSC"), ("D2:X.Y", "D2:X.Y")):
        src = r.stage(0, gem.encode("latin-1") + b"\0")
        dst = r.stage(64, b"\xEE" * 40)
        sysop(CIONAME, src, dst)
        got = r.read(64, 40).split(b"\0", 1)[0].decode("latin-1")
        check(got == want, f"sh_cioname({gem!r}) gave {got!r}, expected {want!r}")

    # -- rsrc_load ----------------------------------------------------------------
    name = r.stage(0, b"A:\\TEST.RSC\0")
    rec = aes(RSRC_LOAD, (), name)
    ret, hdr, size, room, trindex = rec[0], rec[1] & 0xFFFF, rec[2], rec[3], rec[4] & 0xFFFF
    check(ret == 1, f"rsrc_load returned {ret}")
    if ret != 1:
        return
    print(f"  rsrc_load: {size} bytes at ${hdr:04X}, trindex at ${trindex:04X}, "
          f"{room} bytes of pool left")
    # rsh_rssize is the classic part; a new-format file runs on past it with
    # the colour-icon extension, which rs_load streams to far memory.  What
    # the pool keeps of that is one 56-byte record per icon, after the file,
    # word-aligned (src/aes/rsrc.c, CICON_NEAR).
    check(size == R.size, f"rsh_rssize {size} != tools/rsc.py's {R.size}")
    check(len(rsc_bytes) == R.file_len,
          f"the file is {len(rsc_bytes)} bytes, tools/rsc.py says {R.file_len}")
    want_take = ((size + 1) & ~1) + rsc.CICON_NEAR * len(R.cicons) if R.cicons else size
    check(before[7] - room == want_take,
          f"the load took {before[7] - room} bytes of pool, expected {want_take} "
          f"({size} of file, {len(R.cicons)} colour-icon record(s) near)")
    # where the loader put the colour-icon extension: the model needs it to
    # predict the far addresses in the near records (rs_ciaddr's answer)
    ci = r.syms["rs_cibase"]
    cibase = b.peek16(ci) | (b.peek16(ci + 2) << 16)
    image, trees, mem = R.expect(hdr, WCHAR, HCHAR, WIDTH, cibase=cibase)
    check(trindex == hdr + R.o_trindex, f"trindex at ${trindex:04X}, expected ${hdr + R.o_trindex:04X}")
    got = bytes(b.memdump(hdr, size))
    if got != image:
        bad = next(i for i in range(size) if got[i] != image[i])
        check(False, f"the fixed-up image differs at offset {bad} ({region_of(R, bad)}): "
                     f"target {got[bad:bad + 8].hex()} != {image[bad:bad + 8].hex()}")
    else:
        print(f"  the fixed-up image matches tools/rsc.py, all {size} bytes")
    if R.cicons:
        # The near records of the colour icons: the ICONBLK with its bits
        # and mask FAR (in the extension at cibase), its text beside it,
        # and where its colour forms are.  Byte for byte, as the model
        # lays them out (tools/rsc.py, expect).
        hb, want = R.ci_near
        got = bytes(b.memdump(hb, len(want)))
        check(cibase != 0, "rs_cibase is 0: the extension was not placed in far memory")
        if got != want:
            bad = next(i for i in range(len(want)) if got[i] != want[i])
            check(False, f"colour-icon record differs at byte {bad} of {len(want)}: "
                         f"target {got[bad:bad + 8].hex()} != {want[bad:bad + 8].hex()}")
        else:
            print(f"  {len(R.cicons)} colour-icon record(s) at ${hb:04X} match, "
                  f"extension at ${cibase:06X}")

    # -- rsrc_gaddr, every address the file holds ------------------------------------
    counts = {rsc.R_TREE: len(R.trees), rsc.R_OBJECT: len(R.objects),
              rsc.R_OBSPEC: len(R.objects), rsc.R_TEDINFO: len(R.teds),
              rsc.R_TEPTEXT: len(R.teds), rsc.R_TEPTMPLT: len(R.teds),
              rsc.R_TEPVALID: len(R.teds), rsc.R_ICONBLK: len(R.iconblks),
              rsc.R_IBPMASK: len(R.iconblks), rsc.R_IBPDATA: len(R.iconblks),
              rsc.R_IBPTEXT: len(R.iconblks), rsc.R_BITBLK: len(R.bitblks),
              rsc.R_BIPDATA: len(R.bitblks), rsc.R_STRING: len(R.frstr),
              rsc.R_FRSTR: len(R.frstr), rsc.R_IMAGEDATA: len(R.frimg),
              rsc.R_FRIMG: len(R.frimg)}
    n = 0
    for rtype, count in counts.items():
        for i in range(count):
            want = R.addr(rtype, i, hdr)
            rec = aes(RSRC_GADDR, (rtype, i))
            got = (rec[1] & 0xFFFF) | ((rec[2] & 0xFFFF) << 16)
            check(rec[0] == 1 and got == want,
                  f"rsrc_gaddr({rtype}, {i}) = {rec[0]}, ${got:04X}; expected ${want:04X}")
            n += 1
    rec = aes(RSRC_GADDR, (17, 0))
    check(rec[0] == 0, f"rsrc_gaddr of an unknown type returned {rec[0]}")
    print(f"  rsrc_gaddr: {n} addresses over {len(counts)} types checked")

    # -- rsrc_saddr: point free string 0 at free string 1 and back ---------------------
    s0, s1 = R.addr(rsc.R_STRING, 0, hdr), R.addr(rsc.R_STRING, 1, hdr)
    rec = aes(RSRC_SADDR, (rsc.R_FRSTR, 0, s1 & 0xFFFF, s1 >> 16))
    check(rec[0] == 1, f"rsrc_saddr returned {rec[0]}")
    rec = aes(RSRC_GADDR, (rsc.R_STRING, 0))
    check((rec[1] & 0xFFFF) == s1, f"after rsrc_saddr, string 0 is at ${rec[1] & 0xFFFF:04X}, not ${s1:04X}")
    aes(RSRC_SADDR, (rsc.R_FRSTR, 0, s0 & 0xFFFF, s0 >> 16))
    check(bytes(b.memdump(hdr, size)) == image, "the image is not as it was after rsrc_saddr restored it")

    # -- rsrc_obfix: a raw copy of the dialog, fixed one object at a time -------------
    first, count = R.trees[mkrsc.DIALOG]
    raw = b"".join(struct.pack("<hhhHHHIHHHH", o.nxt, o.head, o.tail, o.typ, o.flags,
                               o.state, R._spec(o), o.x, o.y, o.w, o.h)
                   for o in R.objects[first:first + count])
    at = r.stage(512, raw)
    for i in range(count):
        aes(RSRC_OBFIX, (i,), at)
    got = r.read(512, len(raw))
    for i in range(count):
        g, w = got[i * 24:(i + 1) * 24], raw[i * 24:i * 24 + 16] + trees[mkrsc.DIALOG][i].pack()[16:]
        check(g == w, f"rsrc_obfix object {i}: {g.hex()} != {w.hex()}")

    # -- a second load NESTS over the first; a third is refused ---------------------------
    # A program may put up a dialog kept in a resource of its own without
    # freeing the one its trees point into (src/aes/rsrc.c): the pool is a
    # stack and the nested one comes off first.  Two is the limit.
    rec = aes(RSRC_LOAD, (), name)
    check(rec[0] == 1, f"a nested rsrc_load returned {rec[0]}")
    nested = rec[1] & 0xFFFF
    check(nested != hdr,
          f"the nested resource is at ${nested:04X}, the same as the outer")
    rec = aes(RSRC_LOAD, (), name)
    check(rec[0] == 0,
          f"a third rsrc_load returned {rec[0]}: one resident and one nested is all")
    rec = aes(RSRC_FREE)
    check(rec[0] == 1, f"freeing the nested resource returned {rec[0]}")
    rec = aes(RSRC_GADDR, (rsc.R_TREE, 0))
    check((rec[1] & 0xFFFF) == hdr + R.objects[R.trees[mkrsc.DIALOG][0]].off
          or rec[0] != 0,
          "the outer resource did not survive the nested one being freed")

    # -- the loaded dialog, drawn ---------------------------------------------------
    tree_addr = hdr + R.objects[first].off
    script = PRELUDE + [(OBJC_DRAW, FULL, (0, 8), tree_addr)]
    ref_v, ref_a, want = aesref.run(script, trees[mkrsc.DIALOG], mem,
                                        trees={tree_addr: trees[mkrsc.DIALOG]})
    got = r.run(script)
    for i, rec in enumerate(got):
        if rec != want[i]:
            check(False, f"draw script call {i} (op {script[i][0]}) returned {rec}, expected {want[i]}")
            break
    os.makedirs(SHOTDIR, exist_ok=True)
    shot = os.path.join(SHOTDIR, "m12-rsrc.png")
    b.screenshot(shot)
    bad, shown = vbxeref.compare_to_shot(ref_v.to_rgb(), shot)
    check(not bad, f"the drawn dialog: {bad} px differ from tools/aesref.py; first {shown[:3]}")
    if not bad:
        print(f"  the loaded dialog draws pixel for pixel as the model draws it")
        if not keep:
            os.remove(shot)
    check(bytes(b.memdump(hdr, size)) == image, "drawing changed the resource image")

    # -- rsrc_free --------------------------------------------------------------------
    rec = aes(RSRC_FREE)
    check(rec[0] == 1 and rec[1] == before[7],
          f"rsrc_free returned {rec[0]} with {rec[1]} bytes of pool, expected {before[7]}")
    rec = aes(RSRC_GADDR, (rsc.R_TREE, 0))
    check(rec[0] == 0, f"rsrc_gaddr after rsrc_free returned {rec[0]}")
    after = sysop(ALLOC)
    check(after[6:10] == before[6:10], f"the allocators after the free: {after[6:10]} != {before[6:10]}")

    # -- a missing resource ---------------------------------------------------------
    rec = aes(RSRC_LOAD, (), r.stage(0, b"NOSUCH.RSC\0"))
    check(rec[0] == 0 and rec[1] == 0, f"rsrc_load of a missing file returned {rec[0]}, rs_hdr ${rec[1] & 0xFFFF:04X}")
    check(sysop(ALLOC)[7] == before[7], "a failed rsrc_load kept pool memory")


def shel_cases(r, check, b):
    aes = lambda op, ints=(), addr=0: r.run([(op, (), ints, addr)])[0][2:]  # noqa: E731

    # -- shel_write records, shel_read returns ----------------------------------------
    cmd, tail = b"A:\\APP.PRG\0", bytes([5]) + b"a b c" + b"\0"
    rec = aes(SHEL_WRITE, (1, 1, 0, r.stage(128, tail)), r.stage(0, cmd))
    check(rec[0] == 1 and rec[1] == 1 and rec[2] == 1,
          f"shel_write(1, 1) returned {rec[0]}, doexec {rec[1]}, isgem {rec[2]}")
    r.stage(0, b"\xEE" * 128)
    r.stage(128, b"\xEE" * 128)
    rec = aes(SHEL_READ, (r.sc + 128,), r.sc)
    check(rec[0] == 1, f"shel_read returned {rec[0]}")
    got_cmd = r.read(0, 128).split(b"\0", 1)[0]
    check(got_cmd == cmd[:-1], f"shel_read command {got_cmd!r} != {cmd[:-1]!r}")
    check(r.read(128, len(tail)) == tail, f"shel_read tail {r.read(128, len(tail))!r} != {tail!r}")
    rec = aes(SHEL_WRITE, (0, 1, 0, r.sc + 128), r.sc)
    check(rec[1] == 0 and rec[2] == 1, f"shel_write(0): doexec {rec[1]}, isgem {rec[2]}")
    rec = aes(SHEL_WRITE, (4, 0, 0, r.sc + 128), r.sc)
    check(rec[1] == 4 and rec[2] == 0, f"shel_write(4): doexec {rec[1]}, isgem {rec[2]}")
    print(f"  shel_write/shel_read: {cmd[:-1]!r} with a {tail[0]}-byte tail, round-tripped through far memory")

    # -- shel_put / shel_get ----------------------------------------------------------------
    pattern = bytes((i * 7 + 3) & 0xFF for i in range(1024))
    aes(SHEL_PUT, (len(pattern),), r.stage(0, pattern))
    r.stage(1024, b"\xEE" * 1024)
    aes(SHEL_GET, (len(pattern),), r.sc + 1024)
    check(r.read(1024, len(pattern)) == pattern, "shel_get did not return what shel_put stored")
    aes(SHEL_GET, (16,), r.stage(1024, b"\xEE" * 32))
    check(r.read(1024, 32) == pattern[:16] + b"\xEE" * 16, "shel_get wrote past its length")

    # -- shel_envrn: a value in bank $00 ------------------------------------------------------
    rec = aes(SHEL_ENVRN, (), r.stage(0, b"PATH=\0"))
    val = rec[1] & 0xFFFF
    check(val != 0, "shel_envrn found no PATH")
    if val:
        # TOS's layout, which the donor's sh_find expects: the NUL that ends
        # "PATH=" comes first, the search list after it, then its own NUL.
        got = bytes(b.memdump(val, 8))
        check(got[:4] == b"\0D:\0", f"after PATH= at ${val:04X}: {got[:4]!r}, expected b'\\0D:\\0'")
        print(f"  shel_envrn: PATH= at ${val:04X}, followed by {got[1:3].decode()}")
    rec = aes(SHEL_ENVRN, (), r.stage(0, b"NOPE=\0"))
    check((rec[1] & 0xFFFF) == 0, f"shel_envrn found NOPE at ${rec[1] & 0xFFFF:04X}")

    # -- shel_find asks the disk -------------------------------------------------------------
    for path, want in (("A:\\TEST.TXT", 1), ("TEST.RSC", 1), ("A:\\NOSUCH.FIL", 0)):
        rec = aes(SHEL_FIND, (), r.stage(0, path.encode("latin-1") + b"\0"))
        check(rec[0] == want, f"shel_find({path!r}) returned {rec[0]}, CIO status ${rec[1] & 0xFF:02X}")

    # -- the scrap manager: the directory the AES keeps for everybody ------------------------
    # Nothing has written one yet, and an answer is still owed: TOS stopped
    # validating this and the donor follows it (aes/gemsclib.c), because a
    # program that asks before anybody has written wants an empty path it can
    # act on rather than a refusal.
    r.stage(0, b"\xEE" * 128)
    rec = aes(SCRP_READ, (), r.sc)
    check(rec[0] == 1, f"scrp_read on a fresh AES returned {rec[0]}")
    check(r.read(0, 1) == b"\0", f"scrp_read gave {r.read(0, 8)!r}, expected an empty path")

    for path in (b"C:\\CLIPBRD\\", b"A:\\"):
        rec = aes(SCRP_WRITE, (), r.stage(0, path + b"\0"))
        check(rec[0] == 1, f"scrp_write({path!r}) returned {rec[0]}")
        r.stage(64, b"\xEE" * 128)
        rec = aes(SCRP_READ, (), r.sc + 64)
        got = r.read(64, 128).split(b"\0", 1)[0]
        check(rec[0] == 1 and got == path, f"scrp_read gave {got!r}, expected {path!r}")
    print(f"  scrp_write/scrp_read: {path.decode()} round-tripped through far memory, "
          f"and the second write replaced the first")

    # And it is bounded: a path longer than the buffer is cut and still ends
    # in a NUL, so the far allocation after it is not walked into.
    long_path = b"D:\\" + b"X" * 200
    aes(SCRP_WRITE, (), r.stage(0, long_path + b"\0"))
    r.stage(256, b"\xEE" * 160)
    aes(SCRP_READ, (), r.sc + 256)
    got = r.read(256, 160).split(b"\0", 1)[0]
    check(len(got) < 128, f"scrp_read gave {len(got)} bytes: the path was not bounded at 128")
    check(got == long_path[:len(got)], "the truncated path is not a prefix of what was written")
    print(f"  a {len(long_path)}-byte path came back cut to {len(got)} and NUL-terminated")


# -- the file selector -----------------------------------------------------------
D2 = os.path.abspath(os.path.join(ROOT, "build", "m12-d2.atr"))
FSEL_INPUT, FSEL_EXINPUT = aesref.FSEL_INPUT, aesref.FSEL_EXINPUT
PATH_OFF, SEL_OFF, LABEL_OFF = 0, 64, 96        # the caller's strings, in scratch
LEN_PATH = fselrsc.LEN_DIRECT + 9               # fsel.c's LEN_FSPATH: what pipath may hold
# Settles.  The model reads a directory in no time; the target reads it
# through CIO, and while it is reading it is not polling -- the AES's event
# layer sees the pointer only from inside its own wait.  A press that is
# made AND released before the selector reaches that wait is not seen at
# all: the button is a level, and nothing samples it.  So a settle must
# cover the whole listing, not most of it.  Measured on this machine: the
# dialog is up and listening 28 frames after fsel_input is called for a
# nine-name directory, and over 57 when the emulator's disk timing runs
# long.  These are bounds with room, not measurements; the plan's frames
# are polls on both sides and nothing happens in them, so spending more
# costs only wall-clock.  An absent drive adds CIO's timeout (~59 frames,
# docs/phase11.md) and then the old directory is read again.
SETTLE, LISTED, ABSENT = 120, 120, 250


def dir_names(path):
    """What the selector lists for a disk: the directory lines DOS 2
    prints for the image's in-use entries -- flag, name, extension,
    sectors -- through the rule both sides apply (aesref.fs_entry is
    fsel.c's fs_entry), so the prediction comes from the image, not from
    the target.  The fixture DOS's placeholder entries ("--------.---",
    in use, no sectors) fall out here as they do there."""
    names = []
    for e in atr.Dos2(atr.ATRImage.load(path)).entries():
        if e.in_use:
            line = (("*" if e.flag & 0x20 else " ") + " " + e.name.ljust(8)
                    + e.ext.ljust(3) + " " + f"{e.count:03d}")
            name = aesref.fs_entry(line)
            if name:
                names.append(name)
    return names


def fs_rects(base):
    """Where the selector's objects land on the screen, as the model
    places them (fs_input: ob_center, then the scroll bar's widths), so
    a plan can aim at them: obj -> Rect, and the model with them."""
    import fselrsc
    _, a, _ = aesref.run(PRELUDE, [], {})
    _, trees, _ = fselrsc.build().expect(base, a.gl_wchar, a.gl_hchar, a.gl_width)
    tree = trees[0]
    with a.on_tree(tree):
        a.ob_center()
        tree[fselrsc.FTITLE].ob_width -= tree[fselrsc.SCRLBAR].ob_width - a.gl_wbox
        for obj in (fselrsc.SCRLBAR, fselrsc.FUPAROW, fselrsc.FDNAROW,
                    fselrsc.FSVSLID, fselrsc.FSVELEV):
            tree[obj].ob_width = a.gl_wbox
        return [a.ob_actxywh(i) for i in range(len(tree))], a


def run_planned(r, ptr, script, plan):
    """Runner.run with the harness driving the pointer and the keyboard
    while the target is inside the planned ops (m7_form.drive).  Returns
    (error, records)."""
    from m7_form import drive
    b = r.b
    words = aesref.encode(script, 0)
    assert len(words) * 2 <= r.script_room
    b.memload(r.sa, b"".join(struct.pack("<h", w if w < 32768 else w - 65536)
                             for w in words))
    b.poke(STATUS + ST_DONE, 0)
    poke16(b, r.count, NOT_STARTED)
    b.poke(STATUS + ST_GO, 1)
    err = drive(b, r.count, ptr, plan)
    if err:
        return err, None
    for _ in range(300):
        if b.peek(STATUS + ST_DONE) == 0xA5:
            break
        b.frames(4)
    else:
        return "the runner did not finish", None
    b.frames(4)
    n = b.peek16(r.count)
    return None, vdiref.decode(b.memdump(r.results, n * vdiref.RESULT_WORDS * 2), n)


def fs_cases(A, B2, rects):
    """The cases: (title, op, path, sel, label, plan, (ret, button, path,
    sel)) over the sorted listings of D1 (A) and D2 (B2) and the objects'
    rectangles.  Returns them and the counts the masks find."""
    from m7_form import F, M, B, K, CLICK, DCLICK, RETURN
    import fselrsc as fr

    def mid(obj, dy=0):
        rc = rects[obj]
        return (rc.x + rc.w // 2, rc.y + rc.h // 2 + dy)
    name = lambda i: mid(fr.F1NAME + i)                          # noqa: E731
    drv = lambda i: mid(fr.FS1STDRV + i)                         # noqa: E731
    OK, CANCEL, CLOSER = mid(fr.FSOK), mid(fr.FSCANCEL), mid(fr.FCLSBOX)
    UP, DOWN = mid(fr.FUPAROW), mid(fr.FDNAROW)
    slid = rects[fr.FSVSLID]
    top = (slid.x + slid.w // 2, slid.y + 3)     # the elevator's head, list unscrolled
    SHOT = ("shot", None)
    # an exit button's click ends the op on the release: no frame after it

    def typed(s):
        return [K("PERIOD", 0x2E) if c == "." else K(c, ord(c.lower())) for c in s]

    def matching(names, mask):
        return [n for n in names if aesref.fs_wildcmp(mask, n)]

    def drag(frm, dy):
        """Press on the elevator, wait out the double-click delay (a
        TOUCHEXIT press is delivered after it), move, release.  The
        release scrolls the list, a page of names redrawn: five frames
        on the target, so the settle after it is a bound, not a
        measurement, like drive's FINISH."""
        return [M(*frm), B(1), F(14), M(frm[0], frm[1] + dy), F(2), B(0), F(8)]

    # The arrows and the slider's track are TOUCHEXIT objects the selector
    # keeps asking form_do about, and a button wait is satisfied by the
    # button's level: held down, they come back turn after turn, as fast
    # as the scroll redraws, until the release -- GEM's auto-repeat.  How
    # many turns fit in a hold is the target's speed, so a hold is only
    # predictable where it runs to a stop; one line is a tap, released
    # before the double-click delay delivers the click.
    def TAP(xy):
        return [M(*xy), B(1), B(0), F(14)]

    def HOLD(xy, n):
        return [M(*xy), B(1), F(n), B(0), F(2)]

    txt = matching(A, "*.TXT")
    c_files = matching(B2, "*.C")
    if not txt or not c_files:
        return [], (len(txt), len(c_files))
    # where the drive-B case has the list's top line when it picks a name:
    # the slider dragged to its end shows the last page; a page up, two
    # lines up, one down -- each stopping at the ends, as fs_1scroll does
    nm, count = fr.NM_NAMES, len(B2)
    curr = max(count - nm - nm, 0)
    curr = max(curr - 2, 0)
    curr = min(curr + 1, count - nm)
    cases = [
        # name, op, path, sel, label, plan, (ret, button, path, sel)
        ("click the second name, OK", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + CLICK(name(1)) + [F(4), SHOT] + CLICK(OK)[:-1],
         (1, 1, "A:\\*.*", A[1])),
        ("double-click the first name", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + DCLICK(name(0)),
         (1, 1, "A:\\*.*", A[0])),
        ("a selection in, the closer, a name, Cancel", FSEL_INPUT, "A:\\*.*", A[2], None,
         [F(SETTLE), SHOT] + CLICK(CLOSER) + [F(4)] + CLICK(name(3)) + [F(4)] + CLICK(CANCEL)[:-1],
         (1, 0, "A:\\*.*", A[3])),
        ("an empty path means A:\\*.*", FSEL_INPUT, "", "", None,
         [F(SETTLE)] + CLICK(CANCEL)[:-1],
         (1, 0, "A:\\*.*", "")),
        ("a mask, *.TXT; OK with nothing chosen", FSEL_INPUT, "A:\\*.TXT", "", None,
         [F(SETTLE), SHOT] + CLICK(OK)[:-1],
         (1, 1, "A:\\*.TXT", "")),
        ("a name typed, RETURN", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + typed(A[-1]) + [F(2), K("RETURN", RETURN)],
         (1, 1, "A:\\*.*", A[-1])),
        ("drive B: the slider dragged, paged, the arrows; a name; OK", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + CLICK(drv(1)) + [F(LISTED), SHOT]
         + drag(top, slid.h) + [SHOT]                    # to the bottom: the last page
         + TAP(top)                                      # above the elevator: a page up
         + TAP(UP) + TAP(UP) + TAP(DOWN) + [SHOT]
         + CLICK(name(2)) + [F(4)]
         + HOLD(DOWN, 30) + [F(4), SHOT]                 # auto-repeat to the end; the choice stays
         + CLICK(OK)[:-1],
         (1, 1, "B:\\*.*", B2[curr + 2])),
        ("drive C is absent: the error path, back to A:", FSEL_INPUT, "A:\\*.*", A[0], None,
         [F(SETTLE)] + CLICK(drv(2)) + [F(ABSENT), SHOT] + CLICK(CANCEL)[:-1],
         (1, 0, "A:\\*.*", "")),
        ("fsel_exinput: the caller's title, a mask on B:", FSEL_EXINPUT, "B:\\*.C", "", "OPEN A FILE",
         [F(LISTED), SHOT] + CLICK(name(0)) + [F(4)] + CLICK(OK)[:-1],
         (1, 1, "B:\\*.C", c_files[0])),
    ]
    return cases, (len(txt), len(c_files))


def fsel_cases(r, check, b, keep, syms):
    """The selector under the host's hand, against tools/aesref.py: what
    it lists for each disk, what a click, a double-click, the arrows, the
    slider, a drive button, an absent drive and a typed name do to it,
    and what it hands back -- the strings as well as the button.  Each
    case names its own outcome too, so the model is checked against the
    intent and the target against the model."""
    from m7_form import compare
    import fselrsc as fr
    sysop = lambda op, *ints: r.run([(op, (), ints)])[0][2:]     # noqa: E731
    aes = lambda op, ints=(), addr=0: r.run([(op, (), ints, addr)])[0][2:]  # noqa: E731

    ptr = syms["ptr_state"]
    r.run(PRELUDE)
    mark, room = sysop(ALLOC)[6] & 0xFFFF, sysop(ALLOC)[7]
    dirs = {"D1:": dir_names(DISK), "D2:": dir_names(D2)}
    A, B2 = sorted(dirs["D1:"]), sorted(dirs["D2:"])
    print(f"  the disks, by the images: D1 {len(A)} name(s), D2 {len(B2)}; pool ${mark:04X}, {room} free")
    # the cases lean on D1 fitting the box and D2 overflowing it by a page
    check(fr.NM_NAMES // 2 < len(A) <= fr.NM_NAMES,
          f"D1 lists {len(A)} names; the cases want a list that fits the {fr.NM_NAMES} lines")
    check(len(B2) > 2 * fr.NM_NAMES, f"D2 lists {len(B2)} names; the scroll cases want more than {2 * fr.NM_NAMES}")
    if not A or len(B2) <= fr.NM_NAMES:
        return
    rects, _ = fs_rects(mark)
    cases, masks = fs_cases(A, B2, rects)
    check(all(masks), f"the masks find {masks} names on D1 (*.TXT) and D2 (*.C)")
    os.makedirs(SHOTDIR, exist_ok=True)
    for idx, (title, op, path, sel, label, steps, want) in enumerate(cases):
        # the caller's buffers, and the strings the model sees in them
        path_addr = r.stage(PATH_OFF, path.encode("latin-1") + b"\0" * (LEN_PATH - len(path)))
        sel_addr = r.stage(SEL_OFF, sel.encode("latin-1") + b"\0" * (16 - len(sel)))
        buffers = {path_addr: path, sel_addr: sel}
        ints = (sel_addr,)
        if label is not None:
            label_addr = r.stage(LABEL_OFF, label.encode("latin-1") + b"\0")
            buffers[label_addr] = label
            ints = (sel_addr, label_addr)
        script = PRELUDE + [(op, (), ints, path_addr)]
        shots = []

        def take(bridge, shots=shots, idx=idx):
            p = os.path.join(SHOTDIR, f"m12-fsel-{idx:02d}-{len(shots)}.png")
            bridge.screenshot(p)
            shots.append(p)
        steps = [("shot", take) if st[0] == "shot" else st for st in steps]
        plan = {len(PRELUDE): steps}
        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want_recs = aesref.run(script, [], {}, plan={k: list(v) for k, v in plan.items()},
                                             pointer=pointer, dirs=dirs, pool=mark, buffers=dict(buffers))
        got = (want_recs[-1][2], want_recs[-1][3], ref_a.fs_strings[path_addr], ref_a.fs_strings[sel_addr])
        err = None
        if got != want:
            err = f"the model gives {got}, the case wants {want}"
        else:
            err, recs = run_planned(r, ptr, script, plan)
            if err:
                # the screen at the moment it stopped: the one thing that
                # says whether the dialog is still up and what it shows
                n = b.peek16(r.count)
                blocked = os.path.join(SHOTDIR, f"m12-fsel-{idx:02d}-blocked.png")
                b.screenshot(blocked)
                err += "; " + (compare(b, r.results, n, script, want_recs) or f"the {n} records so far match")
                err += (f"; fault {b.peek(syms['irq_fault'])}, frames {b.peek16(syms['irq_frames'])}"
                        f", pointer {b.peek16(ptr)},{b.peek16(ptr + 2)} button {b.peek16(ptr + 4)}"
                        f"; the screen is in {blocked}")
            else:
                err = compare(b, r.results, len(recs), script, want_recs)
                if len(recs) != len(want_recs):
                    err = err or f"{len(recs)} records, expected {len(want_recs)}"
                back = (r.read(PATH_OFF, LEN_PATH).split(b"\0", 1)[0].decode("latin-1"),
                        r.read(SEL_OFF, 16).split(b"\0", 1)[0].decode("latin-1"))
                if not err and back != want[2:]:
                    err = f"the buffers came back as {back}, expected {want[2:]}"
                after = sysop(ALLOC)
                if not err and (after[6] & 0xFFFF, after[7]) != (mark, room):
                    err = f"the pool after: mark ${after[6] & 0xFFFF:04X}, {after[7]} free; was ${mark:04X}, {room}"
                p = os.path.join(SHOTDIR, f"m12-fsel-{idx:02d}.png")
                b.screenshot(p)
                shots.append(p)
                images = ref_a.shots + [ref_v.to_rgb()]
                if len(images) != len(shots):
                    err = err or f"{len(shots)} shots taken, the model has {len(images)}"
                for k, (rgb, sp) in enumerate(zip(images, shots)):
                    bad, shown = vbxeref.compare_to_shot(rgb, sp)
                    if bad and not err:
                        err = f"shot {k}: {bad} px differ from the model; first {shown[:3]}"
        check(not err, f"[{idx}] {title}: {err}")
        print(f"  [{idx}] {title:<62s} {'ok' if not err else 'FAIL'}"
              + (f"  -> {want[1]}, {want[2]!r}, {want[3]!r}" if not err else ""))
        if not err and not keep:
            for sp in shots:
                os.remove(sp)
        if err and err.startswith("the model"):
            continue
        if err and ("blocked" in err or "did not" in err):
            print("   the target is blocked; the cases after this cannot run")
            return

    # -- refused while an application holds the pool ----------------------------
    # The selector's tree and work area need more than the pool has left
    # once an application's resource and its own takings are in it: it
    # says no, takes nothing, draws nothing (docs/phase11.md).  The test
    # resource alone no longer fills an 8 KB pool (docs/phase13.md), so
    # the runner takes the rest on the application's behalf, leaving
    # less than the selector's tree.
    rec = aes(RSRC_LOAD, (), r.stage(128, b"A:\\TEST.RSC\0"))
    check(rec[0] == 1, f"rsrc_load before the refusal returned {rec[0]}")
    tree_bytes = len(fr.build().file())
    held = sysop(ALLOC)[6] & 0xFFFF
    rec = sysop(ALLOC, max(rec[3] - tree_bytes // 2, 0))
    left = rec[7]
    check(left < tree_bytes, f"the pool still has {left} bytes, more than the selector's tree")
    before = os.path.join(SHOTDIR, "m12-fsel-before.png")
    b.screenshot(before)
    path_addr = r.stage(PATH_OFF, b"A:\\*.*\0")
    sel_addr = r.stage(SEL_OFF, b"\0")
    rec = aes(FSEL_INPUT, (sel_addr,), path_addr)
    check(rec[0] == 0 and rec[1] == -1,
          f"fsel_input with {left} bytes of pool returned {rec[0]}, button {rec[1]}")
    check(sysop(ALLOC)[7] == left, f"the refused selector left {sysop(ALLOC)[7]} bytes of pool, not {left}")
    from PIL import Image
    after = os.path.join(SHOTDIR, "m12-fsel-after.png")
    b.screenshot(after)
    same = Image.open(before).convert("RGB").tobytes() == Image.open(after).convert("RGB").tobytes()
    check(same, "the refused selector drew something")
    if not keep:
        os.remove(before)
        os.remove(after)
    print(f"  refused with {left} bytes of pool: the tree alone is {tree_bytes}; nothing taken, nothing drawn")
    sysop(ALLOC, 0, held)
    rec = aes(RSRC_FREE)
    check(rec[0] == 1, f"rsrc_free after the refusal returned {rec[0]}")


def main(argv):
    keep = "--shot" in argv
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    emu = launch(tag="m12", memsize="1088K", extra_args=["--disk", DISK, "--disk", D2])
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
        # "VD" says the runner is alive; STATUS[2] == 1 says it is
        # ready for scripts, which is what staging one needs.
        for _ in range(200):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                break
            b.frames(4)
        if st[:2] != b"VD" or st[2] != 1:
            print("FAIL: runner did not come up")
            return 1
        r = Runner(b, syms)
        print("CIO through the OS:")
        cio_cases(r, check)
        print("the resource library:")
        rsrc_cases(r, check, b, keep)
        print("the shell library:")
        shel_cases(r, check, b)
        print("the file selector:")
        fsel_cases(r, check, b, keep, syms)
    finally:
        emu.stop()

    print(f"gem4xe-m12: {'PASS' if not fails else 'FAIL'} -- the file layer, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
