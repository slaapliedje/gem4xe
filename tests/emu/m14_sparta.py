#!/usr/bin/env python3
"""Phase 13 gate: SpartaGEM -- gem4xe on SpartaDOS.

The same program, on a SpartaDOS disk (tools/mkspdisk.py: a fresh SDFS
volume booting the 3.2 fixture's DOS, with a directory tree on it), run
under SpartaDOS 3.2g from that disk or, with --sdx=CART, under SpartaDOS
X 4.50 from the vendor's emulator cartridge with the disk as D1:.  The
DOS boots on the 6502, the CPU is switched, the DOS boots again, and the
program is typed at its prompt: it has to be loaded BY the DOS
(docs/spike-spartados.md), and this is what a user does.

Then what the DOS seam (src/sys/dos.h) makes of it -- which DOS, its
capabilities, its separator, the MEMTOP it left -- and the GEM-to-CIO
name mapping; CIO opens and reads in the subdirectories against the
image (tools/atr.py reads SDFS); the aux1 = 6 listings of each
directory parsed by the same rule fsel.c applies (tools/aesref.py's
fs_entry, with the folder marks the two SpartaDOSes make differently)
against the image's entries; and the file selector walking the tree --
into a folder, out through the closer, a mask that keeps the folders,
a name picked two levels down -- against the model, pixel for pixel
and string for string.  The CIO timings are printed next to the DOS 2
baseline the spike measured.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, vbxeref, symfile, atr, fselrsc  # noqa: E402
from m7_form import STATUS, SYMS, F, M, B, K, CLICK, DCLICK, RETURN, compare  # noqa: E402
from m4_aes import PRELUDE, SHOTDIR         # noqa: E402
from m12_file import (Runner, OPEN, CLOSE, READ, GETREC, CIONAME, ALLOC,  # noqa: E402
                      A_READ, A_DIR, OK, OK_EOF, E_EOF, E_NOTFOUND,
                      FAULT_I, ST_I, GOT_I, FRAMES_I, CALLS_I,
                      FSEL_INPUT, FSEL_EXINPUT, PATH_OFF, SEL_OFF, LABEL_OFF, LEN_PATH,
                      SETTLE, LISTED, fs_rects, run_planned)

# Absolute: the launcher runs the emulator in its own directory, and a
# relative --disk resolves there -- to nothing, and the machine boots to
# Self Test looking exactly like a DOS that did not come up.
DISK = os.path.abspath(os.path.join(ROOT, "build", "m14-boot.atr"))
# src/sys/dos.h
DOS_SPARTA, DOS_SDX, DOS_CAP_DIRS = 1, 2, 0x01
KIND = {DOS_SPARTA: "SpartaDOS 3.2", DOS_SDX: "SpartaDOS X"}
CIO_NAME_MAX = 63
# what the spike measured on DOS 2, in frames (docs/spike-spartados.md)
DOS2 = {"open": 14, "read": 6, "dir open": 7, "dir read": 48}


# -- the DOS's console, through the bridge -------------------------------------
KEYS = {" ": ("SPACE", False), ".": ("PERIOD", False), "-": ("MINUS", False),
        ":": ("SEMICOLON", True), ">": ("GREATER", False), "*": ("8", True)}
# > is a key of its own on the Atari; shift-period is ].  Nothing typed one
# until tests/emu/install.py, which is how the table carried that for so long.


def screen(b):
    """The OS text screen as 24 lines of ASCII."""
    # one read, not two: the OS rewrites SAVMSC while it boots, and two
    # peeks a bridge round trip apart once read $FE78 -- a torn value that
    # sent the dump past the top of memory (test-m17, 2026-09-16)
    savmsc = b.peek16(0x58)
    if not savmsc or savmsc + 960 > 0x10000:
        return []
    raw = bytes(b.memdump(savmsc, 960))
    out = []
    for c in raw:
        v = c & 0x7F
        ch = (v + 32) if v < 64 else (v - 64 if v < 96 else v)
        out.append(chr(ch) if 32 <= ch < 127 else " ")
    t = "".join(out)
    return [t[i:i + 40].rstrip() for i in range(0, 960, 40)]


def sayable_free(n):
    """What a SpartaDOS can put in the three characters its directory
    listing gives the free-sector count, and the two do not agree once it
    will not fit: 3.2g prints the low three digits (1,001 comes out as
    "001"), SDX stops at 999.  Nothing above 999 comes back through CIO
    at all, which is also the ceiling on GEMDOS's Dfree -- gd_dfree reads
    that same line, because it is the only thing CIO offers
    (src/sys/gemdos.c)."""
    return {n} if n < 1000 else {999, n % 1000}


def type_line(b, s, wait=60):
    for ch in s:
        name, shift = KEYS.get(ch, (ch.upper(), False))
        b.key(name, shift=shift)
        b.frames(3)
    b.key("RETURN")
    b.frames(wait)


def wait_prompt(b, prompt="D1:", limit=3000, step=50):
    """Poll the text screen until a line ends with the DOS prompt; the
    frames it took, or -1."""
    for t in range(0, limit, step):
        if any(ln.rstrip().endswith(prompt) for ln in screen(b)):
            return t
        b.frames(step)
    return -1


def boot(b, prepare=None, program="M3"):
    """The DOS up on the 6502, the CPU switched, the DOS up again, the
    program typed at its prompt and polled for.  Returns (frames the
    load took, the STATUS block), or (-1, None).  `prepare(b)`, if
    given, runs at the prompt just before the program is typed: the
    moment to paint memory the load will not touch (m16's stack), or to
    move the DOS's own directory (m15 --from-sub, which then types the
    program by its full path)."""
    t = wait_prompt(b, limit=4000)
    if t < 0:
        return -1, None
    print(f"  the DOS prompt after {t} frames on the 6502")
    b.poke(0xD1FF, 0x01)
    b.poke(0xD191, 0x00)
    b.frames(100)
    t = wait_prompt(b, limit=4000)
    if t < 0:
        return -1, None
    print(f"  and after {t + 100} frames on the 65816")
    bank = cart_bank(b)
    if prepare:
        prepare(b)
    type_line(b, program)
    for t in range(0, 8000, 50):
        st = bytes(b.memdump(STATUS, 14))
        if st[:2] == b"VD" and st[2] == 1:
            if cart_bank(b) != bank:
                # SpartaDOS X lives in the cartridge and only its bank 1 is
                # the DOS; anything else there is whatever the load put on
                # the bus at $D5xx.  See src/gem4xe.scm, THE HOLE.
                print(f"  FAIL: the cartridge bank changed under the load, "
                      f"{bank} -> {cart_bank(b)}: something touched $D5xx")
                return -1, None
            return t, st
        b.frames(50)
    return -1, None


def cart_bank(b):
    """The cartridge's current bank, or None with no cartridge."""
    info = b.cmd("CART_INFO")
    return info.get("bank") if isinstance(info, dict) else None


# -- the seam ------------------------------------------------------------------
def dos_cases(r, check, st, want_kind):
    b = r.b
    kind, caps, sep = st[8], st[9], st[10]
    memtop, nmax = st[11] | (st[12] << 8), st[13]
    os_memtop = b.peek16(0x02E5)
    print(f"  the seam: kind {kind} ({KIND.get(kind, '?')}), caps {caps:#04x}, dirsep {chr(sep)!r}, "
          f"MEMTOP ${memtop:04X}, names up to {nmax}")
    check(kind == want_kind, f"the DOS is identified as {kind}, this run boots {want_kind} ({KIND[want_kind]})")
    check(caps & DOS_CAP_DIRS, "a SpartaDOS without DOS_CAP_DIRS")
    check(sep == ord(">"), f"the separator is {chr(sep)!r}, not '>'")
    check(memtop == os_memtop, f"the seam's MEMTOP ${memtop:04X} is not the OS's ${os_memtop:04X}")
    check(nmax == CIO_NAME_MAX, f"CIO_NAME_MAX is {nmax}, the harness assumes {CIO_NAME_MAX}")
    # the program's own regions must lie under what the DOS left free
    lo = min(a for a in r.syms.values() if a >= 0x2000)
    check(r.sa + r.script_room <= os_memtop + 1,
          f"the test stage ends at ${r.sa + r.script_room:04X}, above MEMTOP ${os_memtop:04X}")
    print(f"  the program's bank-0 symbols run ${lo:04X}-${max(a for a in r.syms.values() if a < 0x10000):04X}")

    # the GEM-to-CIO mapping, against the model's fs_cioname
    for gem in ("A:\\SUB\\ONE.TXT", "A:\\*.*", "A:\\SUB\\DEEP\\*.*", "b:\\x.y", "NAME.EXT",
                "A:\\sub\\deep\\three.txt", "H:\\" + "\\".join(["ABCDEFGH"] * 8) + "\\NAME.EXT"):
        src = r.stage(0, gem.encode("latin-1") + b"\0")
        dst = r.stage(128, b"\xEE" * 70)
        rec = r.run([(CIONAME, (), (src, dst))])[0]
        check(rec[FAULT_I] == 0, f"cioname: fault {rec[FAULT_I]}")
        got = r.read(128, 70).split(b"\0", 1)[0].decode("latin-1")
        want = aesref.fs_cioname(gem, ">")
        check(got == want, f"cioname {gem!r} -> {got!r}, the model says {want!r}")
        print(f"    {gem[:40]!r:44} -> {got!r}")


# -- CIO against the image ------------------------------------------------------
def cio_cases(r, check, fs, syms):
    b = r.b
    frames = lambda: b.peek16(syms["irq_frames"])       # noqa: E731
    timing = {}

    def sysop(op, *ints):
        rec = r.run([(op, (), ints)])[0]
        check(rec[FAULT_I] == 0, f"op {op}: fault {rec[FAULT_I]} during the call")
        return rec

    def opened(name, aux1):
        addr = r.stage(0, name.encode("latin-1") + b"\0")
        t0 = frames()
        rec = sysop(OPEN, addr, aux1, 0)
        return rec[ST_I], (frames() - t0) & 0xFFFF

    buf = r.stage(64, b"\xEE" * 256)

    # -- files in the tree, read whole ------------------------------------------
    for cio, path in (("D1:>TEST.TXT", "TEST.TXT"), ("D1:>SUB>ONE.TXT", "SUB>ONE.TXT"),
                      ("D1:>SUB>DEEP>THREE.TXT", "SUB>DEEP>THREE.TXT"), ("D:SUB>TWO.DAT", "SUB>TWO.DAT")):
        want = fs.read(path)
        iocb, dt_open = opened(cio, A_READ)
        check(1 <= iocb <= 7, f"open {cio!r} returned {iocb}")
        if not 1 <= iocb <= 7:
            continue
        t0 = frames()
        rec = sysop(READ, iocb, buf, 256)
        dt_read = (frames() - t0) & 0xFFFF
        got = r.read(64, rec[GOT_I])
        check(rec[GOT_I] == len(want) and got == want,
              f"read {cio!r}: status ${rec[ST_I] & 0xFF:02X}, {rec[GOT_I]} bytes {got[:20]!r}; the image holds {len(want)}")
        check(rec[ST_I] in (OK, OK_EOF, E_EOF), f"read {cio!r}: status ${rec[ST_I] & 0xFF:02X}")
        sysop(CLOSE, iocb)
        print(f"    {cio:24} {len(want):4} bytes  open {dt_open:3} frames, read {dt_read:2}")
        timing.setdefault("open", dt_open)
        timing.setdefault("read", dt_read)
    st, _ = opened("D1:>SUB>NOPE.TXT", A_READ)
    check(st == -E_NOTFOUND, f"open of a missing file returned {st}, expected {-E_NOTFOUND}")
    st, _ = opened("D1:>NOSUCH>ONE.TXT", A_READ)
    check(st < 0, f"open through a missing directory returned {st}")
    check(all(b.peek(0x0340 + i * 16) == 0xFF for i in range(1, 8)), "an IOCB was left open by a failed open")

    # -- the listings, parsed as fsel.c parses them, against the image ------------
    for path in ("", "SUB", "SUB>DEEP"):
        cio = "D1:>" + (path + ">" if path else "") + "*.*"
        iocb, dt_open = opened(cio, A_DIR)
        check(1 <= iocb <= 7, f"open {cio!r} aux1=6 returned {iocb}")
        if not 1 <= iocb <= 7:
            continue
        lines = []
        t0 = frames()
        while True:
            rec = sysop(GETREC, iocb, buf, 80)
            if rec[GOT_I]:
                lines.append(r.read(64, rec[GOT_I]).rstrip(b"\x9b").decode("latin-1"))
            if rec[ST_I] not in (OK, OK_EOF):
                break
        dt_read = (frames() - t0) & 0xFFFF
        sysop(CLOSE, iocb)
        got = [e for e in (aesref.fs_entry(ln) for ln in lines) if e]
        want = [(aesref.FS_FOLDER if e.is_dir else "") + e.filename for e in fs.entries(path)]
        print(f"    {cio}: {len(lines)} records, open {dt_open} frames, read {dt_read}")
        for ln in lines:
            print(f"      |{ln}|  " + " ".join(f"{ord(c):02x}" for c in ln[:13]))
        check(sorted(got) == sorted(want), f"{cio} lists {got}, the image holds {want}")
        check(lines and re.match(r"^\s*\d+ FREE", lines[-1], re.I), f"{cio} does not end in the free-sector line")
        if path == "":
            m = re.match(r"^\s*(\d+) FREE", lines[-1], re.I)
            free = int(m.group(1)) if m else -1
            n = fs.free_count()
            check(free in sayable_free(n),
                  f"the DOS reports {free} free sectors, the image holds {n} "
                  f"(three digits allow {sorted(sayable_free(n))})")
            timing["dir open"], timing["dir read"] = dt_open, dt_read
            timing["dir lines"] = len(lines)
    return timing


# -- the selector over the tree ---------------------------------------------------
def fsel_cases(r, check, b, keep, syms, fs, tag):
    import fselrsc as fr
    sysop = lambda op, *ints: r.run([(op, (), ints)])[0][2:]     # noqa: E731

    ptr = syms["ptr_state"]
    r.run(PRELUDE)
    mark, room = sysop(ALLOC)[6] & 0xFFFF, sysop(ALLOC)[7]
    # the directories by their CIO names, as the model keys them; a
    # folder carries the selector's flag and sorts first
    dirs = {}
    for path in ("", "SUB", "SUB>DEEP"):
        key = "D1:>" + (path + ">" if path else "")
        dirs[key] = [(aesref.FS_FOLDER if e.is_dir else "") + e.filename for e in fs.entries(path)]
    root = sorted(dirs["D1:>"])
    sub = sorted(dirs["D1:>SUB>"])
    deep = sorted(dirs["D1:>SUB>DEEP>"])
    print(f"  the tree, by the image: {len(root)} in MAIN, {len(sub)} in SUB, {len(deep)} in SUB>DEEP; pool ${mark:04X}, {room} free")
    check(root[0] == aesref.FS_FOLDER + "SUB" and sub[0] == aesref.FS_FOLDER + "DEEP",
          f"the folders do not sort first: {root[0]!r}, {sub[0]!r}")
    check(len(root) <= fr.NM_NAMES, f"MAIN lists {len(root)} names, more than the {fr.NM_NAMES} lines")
    rects, _ = fs_rects(mark)

    def mid(obj):
        rc = rects[obj]
        return (rc.x + rc.w // 2, rc.y + rc.h // 2)
    name = lambda i: mid(fr.F1NAME + i)                          # noqa: E731
    OKB, CANCEL, CLOSER = mid(fr.FSOK), mid(fr.FSCANCEL), mid(fr.FCLSBOX)
    SHOT = ("shot", None)
    files = lambda names: [n for n in names if n[0] != aesref.FS_FOLDER]     # noqa: E731

    def typed(s):
        return [K("PERIOD", 0x2E) if c == "." else K(c, ord(c.lower())) for c in s]

    # A click on a folder or on the closer changes the listing, and the
    # listing is a CIO read: 30 to 50 frames on this disk, longer than
    # CLICK holds the button.  The model reads its listing in no time and
    # takes a still-held button for another turn (aesref's ev_wait: the
    # screen changed under a held button, as it does for a held scroll
    # arrow), so it would descend again where the target cannot.  A tap
    # -- pressed and released before the double-click delay delivers the
    # click -- leaves nothing held on either side.
    def TAP(xy):
        return [M(*xy), B(1), B(0), F(14)]
    sub_txt = sorted([n for n in sub if n[0] == aesref.FS_FOLDER] + [n for n in files(sub) if n.endswith(".TXT")])
    cases = [
        # title, op, path, sel, label, plan, (ret, button, path, sel)
        ("MAIN listed, the folder first; into SUB; Cancel", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE), SHOT] + TAP(name(0)) + [F(LISTED), SHOT] + CLICK(CANCEL)[:-1],
         (1, 0, "A:\\SUB\\*.*", "")),
        ("into SUB, into DEEP, the one name there, OK", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + TAP(name(0)) + [F(LISTED)] + TAP(name(0)) + [F(LISTED), SHOT]
         + CLICK(name(0)) + [F(4)] + CLICK(OKB)[:-1],
         (1, 1, "A:\\SUB\\DEEP\\*.*", deep[0])),
        ("started in DEEP: the closer twice, back at the root; a name; OK", FSEL_INPUT, "A:\\SUB\\DEEP\\*.*", "", None,
         [F(SETTLE)] + TAP(CLOSER) + [F(LISTED), SHOT] + TAP(CLOSER) + [F(LISTED)]
         + CLICK(name(2)) + [F(4)] + CLICK(OKB)[:-1],
         (1, 1, "A:\\*.*", root[2])),
        ("a mask in SUB keeps the folder; OK with nothing chosen", FSEL_INPUT, "A:\\SUB\\*.TXT", "", None,
         [F(SETTLE), SHOT] + CLICK(OKB)[:-1],
         (1, 1, "A:\\SUB\\*.TXT", "")),
        ("the closer at the root stays; a name typed, RETURN", FSEL_INPUT, "A:\\*.*", "", None,
         [F(SETTLE)] + TAP(CLOSER) + [F(LISTED)] + typed(files(root)[-1]) + [F(2), K("RETURN", RETURN)],
         (1, 1, "A:\\*.*", files(root)[-1])),
        ("fsel_exinput in SUB: the caller's title; a double-click on a file", FSEL_EXINPUT, "A:\\SUB\\*.*", "", "SPARTAGEM",
         [F(SETTLE), SHOT] + DCLICK(name(1)),
         (1, 1, "A:\\SUB\\*.*", sub[1])),
    ]
    os.makedirs(SHOTDIR, exist_ok=True)
    for idx, (title, op, path, sel, label, steps, want) in enumerate(cases):
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
            p = os.path.join(SHOTDIR, f"{tag}-fsel-{idx:02d}-{len(shots)}.png")
            bridge.screenshot(p)
            shots.append(p)
        steps = [("shot", take) if st[0] == "shot" else st for st in steps]
        plan = {len(PRELUDE): steps}
        pointer = (b.peek16(ptr), b.peek16(ptr + 2))
        ref_v, ref_a, want_recs = aesref.run(script, [], {}, plan={k: list(v) for k, v in plan.items()},
                                             pointer=pointer, dirs=dirs, pool=mark, buffers=dict(buffers),
                                             dirsep=">")
        got = (want_recs[-1][2], want_recs[-1][3], ref_a.fs_strings[path_addr], ref_a.fs_strings[sel_addr])
        err = None
        if got != want:
            err = f"the model gives {got}, the case wants {want}"
        else:
            err, recs = run_planned(r, ptr, script, plan)
            if err:
                n = b.peek16(r.count)
                blocked = os.path.join(SHOTDIR, f"{tag}-fsel-{idx:02d}-blocked.png")
                b.screenshot(blocked)
                if n <= len(script):
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
                p = os.path.join(SHOTDIR, f"{tag}-fsel-{idx:02d}.png")
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
        print(f"  [{idx}] {title:<66s} {'ok' if not err else 'FAIL'}"
              + (f"  -> {want[1]}, {want[2]!r}, {want[3]!r}" if not err else ""))
        if not err and not keep:
            for sp in shots:
                os.remove(sp)
        if err and ("blocked" in err or "did not" in err):
            print("   the target is blocked; the cases after this cannot run")
            return
    check(len(sub_txt) == 2, f"the mask case lists {sub_txt}; the tree wants a folder and one .TXT")


def main(argv):
    keep = "--shot" in argv
    cart = flash = None
    for a in argv:
        if a.startswith("--sdx="):
            cart = a[6:]
        elif a.startswith("--u1mb="):
            flash = a[7:]
    want_kind = DOS_SDX if (cart or flash) else DOS_SPARTA
    tag = "m14u" if flash else "m14x" if cart else "m14"
    syms = symfile.load(SYMS)
    # SDX keeps its own RAM banked in at $4000-$7FFF while it services a
    # call, and the bridge reads what the CPU sees: a word the harness
    # polls during a call cannot live there (src/m3_vdi.c).
    assert not 0x4000 <= syms["vdi_result_count"] < 0x8000, hex(syms["vdi_result_count"])
    fs = atr.Sdfs(atr.ATRImage.load(DISK))
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    # --u1mb=FLASH: SpartaDOS X from an Ultimate 1MB flash image, the way
    # a real machine runs it, through the patched emulator's --u1mbrom
    # (tools/altirra/).  The flash brings its own OS, so the XL ROM check
    # is off; the BIOS profile has to have been saved once (docs/phase14.md).
    args = ["--disk", DISK] + (["--cart", cart] if cart else []) \
        + (["--u1mbrom", flash] if flash else [])
    print(f"{KIND[want_kind]}: {os.path.basename(cart or flash or DISK)}"
          + (" (U1MB flash)" if flash else ""))
    emu = launch(tag=tag, memsize="1088K", extra_args=args, require_real_rom=not flash)
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
        print("the DOS seam:")
        dos_cases(r, check, st, want_kind)
        print("CIO in the tree, against the image:")
        timing = cio_cases(r, check, fs, syms)
        print("the file selector over the tree:")
        fsel_cases(r, check, b, keep, syms, fs, tag)
    finally:
        emu.stop()

    if timing:
        print(f"frames per call, {KIND[want_kind]} against the DOS 2 baseline:")
        for k in ("open", "read", "dir open", "dir read"):
            note = f"  ({timing['dir lines']} records)" if k == "dir read" else ""
            print(f"    {k:10} {timing.get(k, -1):4}   DOS 2 {DOS2[k]:3}{note}")
    print(f"gem4xe-m14: {'PASS' if not fails else 'FAIL'} -- {KIND[want_kind]}, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
