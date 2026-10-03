#!/usr/bin/env python3
"""The system on MyDOS 4.50, booted into the desktop.

WHAT WAS WRONG, for as long as the product floppies have existed: under
MyDOS twelve bytes of the far image at $010020 arrived as zeros, the
first gemdos_call ran into them and took a BRK.  docs/shipping.md
recorded it as "MyDOS mangles the staged image, cause unknown".

THE CAUSE is MyDOS doing something a 6502 allows and a 65816 does not.
Around its INITAD call it saves CIO's zero-page IOCB, $20-$2B, like this:

    $1282  ldy #$F4
    $1284  lda $FF2C,y     ; $FF2C + $F4 wraps to $0020 on a 6502 ...
    $1287  sta ICHID,x
    $1291  jsr $1300       ; -> jmp (INITAD): gem4xe's unpacker
    $1297  ldy #$F4
    $1299  lda ICHID,x
    $129c  sta $FF2C,y     ; ... and to $010020 on a 65816

A 65816 carries absolute indexing into the next bank EVEN IN EMULATION
MODE, so on the real chip as in Altirra it snapshots $010020-$01002B
before the unpacker runs and writes the snapshot back after -- and the
chunk that filled those bytes was reverted to zeros every time.  Found
with a copy of GEM.COM whose every INITAD went through a logger first:
MyDOS delivered all twenty chunks exactly as sent, and the bytes went
bad between one call and the next (docs/phase50.md).

THE FIX is on this side: bank $01's first page is nobody's
(src/gem4xe.scm, wrap-page-end), because $010000-$0100FE is where ANY
6502 code lands when it leans on the wrap.  So this gate checks the
link first, on the host, and then the boot.

AND A SECOND THING MyDOS DOES DIFFERENTLY: its $070A is not DOS 2's
DRVBYT.  It holds $08 on a one-drive machine, which Drvmap returned as a
bitmap and the desktop drew as its only icon, at D:.  MyDOS signs its
boot flag at $0700 with 'M' the way a SpartaDOS signs with 'S', and
dos_ident uses that; the drive map expected here is worked out from the
DISK'S boot sector, not asked of the machine.

AND QUIT, which stalled (0.12's item 8).  It was never gem4xe: the DISK
was broken.  The fixture is a 1440-sector MyDOS volume, whose files are
chained by MyDOS's extended links -- the next sector's whole number, no
file number -- and tools/atr.py read them as DOS 2 links.  Sweeping the
fixture down to its DOS followed other files' chains into DUP.SYS's
sectors, freed them, and AUTORUN.SYS was written over them.  Booting
never reads DUP.SYS, so the desktop came up; Quit goes back through
DOSVEC, MyDOS loads DUP.SYS, and ran what was left of it.  So this gate
holds the disk's DOS.SYS and DUP.SYS to the fixture's, byte for byte,
then quits (Ctrl+Q) and gives MyDOS a command: A, its directory, which
must list AUTORUN.SYS (docs/phase106.md).

    python3 tests/emu/mydos_boot.py [--shot]
"""
import os
import sys
import tomllib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
from farheap import far_heap, heap_text  # noqa: E402
import atr, mkxex, symfile, vbxeref         # noqa: E402
from m4_aes import SHOTDIR                  # noqa: E402
from m14_sparta import screen               # noqa: E402
from product_boot import desk_model, dos2_listing, REFUSAL  # noqa: E402

BUILD = os.path.join(ROOT, "build")
DISK = os.path.abspath(os.path.join(BUILD, "gem-mydos.atr"))
SYMS = os.path.join(BUILD, "gem.sym")
ELF = os.path.join(BUILD, "gem.elf")
WRAP_END = 0x010100             # src/gem4xe.scm wrap-page-end
MYDOS_FLAG = ord("M")           # the boot record's first byte (src/sys/dos.c)
DOS_2 = 0                       # src/sys/dos.h

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def main(argv):
    keep = "--shot" in argv
    print("gem4xe-mydos: the system on MyDOS 4.50")

    # -- the link, on the host: nothing of the far image in the wrap page --
    segs, _ = mkxex.read_elf(ELF)
    far = sorted((a, d) for a, d in segs if a > 0xFFFF)
    lo = far[0][0]
    check(lo >= WRAP_END,
          f"the far image starts at ${lo:06X}, inside bank $01's first page, "
          f"which is where a 6502's wrapped index lands on a 65816 -- MyDOS "
          f"writes $010020-$01002B on every INITAD")
    print(f"  the far image starts at ${lo:06X}, "
          f"{'above' if lo >= WRAP_END else 'INSIDE'} the wrap page")

    # -- the disk -----------------------------------------------------------
    img = atr.ATRImage.load(DISK)
    fs = atr.Dos2(img)
    names = {e.filename.upper() for e in fs.entries() if e.in_use}
    for n in ("DOS.SYS", "DUP.SYS", "AUTORUN.SYS", "DESKTOP.PRG",
              "DESKTOP.RSC", "LANG.RSC"):
        check(n in names, f"{n} is not on the disk")
    with open(os.path.join(BUILD, "gem.xex"), "rb") as f:
        check(fs.read("AUTORUN.SYS") == f.read(),
              "AUTORUN.SYS is not build/gem.xex byte for byte")
    flag = img.read_sector(1)[0]
    check(flag == MYDOS_FLAG, f"the boot flag is ${flag:02X}, not 'M': this "
                              f"fixture is not MyDOS")
    # MyDOS's own files, as the fixture has them: the sweep must not have
    # touched a byte of either (tools/atr.py, extended links)
    with open(os.path.join(ROOT, "fixtures.toml"), "rb") as f:
        src = atr.Dos2(atr.ATRImage.load(tomllib.load(f)["dos"]["mydos"]))
    for n in ("DOS.SYS", "DUP.SYS"):
        if n in names:
            got, want = fs.read(n), src.read(n)
            check(got == want, f"{n} on the disk is {len(got)} bytes that are "
                               f"not the fixture's {len(want)}: the sweep "
                               f"wrote over it")
    want_map = 0x03 if flag == MYDOS_FLAG else None
    print(f"  {DISK}: {img!r}, boot flag {chr(flag)!r}, "
          f"{', '.join(sorted(names))}")

    # -- the boot -----------------------------------------------------------
    syms = symfile.load(SYMS)
    emu = launch(tag="mydos", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        calls = syms["app_calls"]
        n, still = 0, 0
        for t in range(0, 20000, 250):
            b.frames(250)
            now = b.peek16(calls)
            still = still + 1 if now == n and now else 0
            n = now
            if still >= 2:
                break
        else:
            check(False, f"GEM never settled ({n} calls)")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  GEM settled after {t + 250} frames, {n} calls in")
        check(b.cmd("HWSTATE").get("cpu", {}).get("mode") != "6502",
              "the machine is still a 6502")
        check(not any(REFUSAL in ln for ln in screen(b)),
              "GEM refused the machine")
        check(b.peek(syms["irq_fault"]) == 0,
              f"irq_fault {b.peek(syms['irq_fault'])} (src/sys/irq.s)")

        # EVERY byte, not a sample: the old failure was twelve of them.
        bad = []
        for base, data in far:
            got = bytes(b.memdump(base, len(data)))
            bad += [base + k for k, (x, y) in enumerate(zip(got, data)) if x != y]
        total = sum(len(d) for _, d in far)
        check(not bad, f"the far image differs in {len(bad)} of {total} bytes, "
                       f"first ${bad[0]:06X}" if bad else "")
        print(f"  the far image: {total} bytes, "
              f"{'every one as the linker wrote it' if not bad else str(len(bad)) + ' wrong'}")
        # What MyDOS left in the wrap page, which nothing now owns: shown,
        # not asserted -- it is MyDOS's business and harmless where it is.
        print(f"  MyDOS's writes in the wrap page: $010020-$01002B = "
              f"{bytes(b.memdump(0x010020, 12)).hex()}")

        kind = b.peek(syms["dos"])
        check(kind == DOS_2, f"the system calls this a kind-{kind} DOS")
        mark = b.peek16(syms["app_near"])
        brk = far_heap(b, syms)
        pointer = (b.peek16(syms["ptr_state"]), b.peek16(syms["ptr_state"] + 2))
        ref_v, ref_a, d = desk_model(mark, brk, pointer, want_map,
                                     dos2_listing(fs))
        check(len(ref_a.shots) == 1, f"the model took {len(ref_a.shots)} shots")
        check((n - 1) & 0xFFFF == d.waits[0],
              f"the desktop is in call {(n - 1) & 0xFFFF}, not its first wait "
              f"{d.waits[0]}")
        os.makedirs(SHOTDIR, exist_ok=True)
        shot = os.path.join(SHOTDIR, "mydos-desk.png")
        b.screenshot(shot)
        bad_px, shown = vbxeref.compare_to_shot(ref_a.shots[0], shot)
        check(not bad_px, f"the desk, {bad_px} px differ from the model with "
                          f"drive map {want_map:#04x}; first {shown[:3]}")
        print(f"  the desk {'ok' if not bad_px else 'FAIL'} against the model, "
              f"drive map {want_map:#04x} from the disk's boot flag")
        if not bad_px and not keep:
            os.remove(shot)

        # -- back to MyDOS, and a command there -------------------------------
        b.key("Q", ctrl=True)               # File -> Quit
        for t in range(0, 1500, 25):
            b.frames(25)
            if any("Select Item" in ln for ln in screen(b)):
                break
        else:
            check(False, "Quit: MyDOS's menu never came up (DUP.SYS)")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        print(f"  Quit: MyDOS's menu {t + 25} frames later")
        b.frames(30)
        b.key("A")                          # Disk Directory ...
        b.frames(30)
        b.key("RETURN")                     # ... of D1:, to the screen
        b.frames(300)
        lines = [ln for ln in screen(b) if ln.strip()]
        check(any("AUTORUN SYS" in ln for ln in lines),
              "MyDOS's directory, A then RETURN, did not list AUTORUN.SYS")
        for ln in lines[-6:]:
            print("   |" + ln)
    finally:
        emu.stop()

    print(f"\ngem4xe-mydos: {'PASS' if not problems else 'FAIL'} -- the system "
          f"on MyDOS 4.50, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
