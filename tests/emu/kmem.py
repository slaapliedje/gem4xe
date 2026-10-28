#!/usr/bin/env python3
"""gem4xe takes its high RAM from the OS, and gives it back (phase 112).

Under Rapidus OS -- which the Antonia II runs too -- the high RAM is
handed out by the kernel allocator, COP #$01 ("kmem"), and gem4xe now
asks it: the banks its own image was loaded into ($01 up) and the heap
are two blocks of its, taken at start-up and freed on the way back to
DOS (src/sys/farmem.c).  SpartaDOS X frees a finished program's blocks
itself, so test-sdx816 cannot tell whether gem4xe gave anything back --
it passed with farmem_release() taken out.  DOS 2 frees nothing.  So:

  1. the DOS 2 floppy boots under Rapidus OS and GEM starts by itself;
     gem4xe holds an image block at $0100 and a heap block where its
     heap starts, the OS lists both as allocated, and one bank of the
     free run is left for somebody else;
  2. File -> Quit (Ctrl-Q) back to DUP, and DUP's L loads AUTORUN.SYS --
     gem4xe a second time, on the same machine without a reboot;
  3. the second run's heap and blocks are the first's, its boot screen
     says the same Memory line and no second one;
  4. a cold boot of the same floppy with HIGHRAM=$10-$1F in GEM4XE.CFG:
     the heap is $10-$1E, the fence less the bank left over.

Without the release the second run found one bank free, $EF, and could
not start: "Memory 0.1 MB, banks $EF-$EF".

    python3 tests/emu/kmem.py --os=XLOS816A.ROM
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import atr                                  # noqa: E402
import symfile                              # noqa: E402
from m11_abi import os_profile              # noqa: E402
from m14_sparta import screen               # noqa: E402
from sdx816 import farmem                   # noqa: E402

BUILD = os.path.abspath(os.path.join(ROOT, "build"))
DISK = os.path.join(BUILD, "gem-boot.atr")
FENCED = os.path.join(BUILD, "kmem-highram.atr")
HIGHRAM = (0x10, 0x1F)
CFG_TEXT = "HIGHRAM = $10-$1F   ; the fence\x9b".encode("latin-1")
SYMS = os.path.join(BUILD, "gem.sym")
LOSEGM, HISEGM = 0x024D, 0x024E
MEMORY = "Memory"                           # the boot screen's label (LANG.RSC)


def wait_desk(b, syms, memlines):
    """Until the desktop has made its first calls; the boot screen's
    Memory lines as they went by."""
    for _ in range(600):
        b.frames(10)
        for ln in screen(b):
            s = ln.strip()
            if s.startswith(MEMORY) and s not in memlines:
                memlines.append(s)
        if b.peek(syms["irq_cio_swap"]) in (1, 3) and b.peek16(syms["app_calls"]) > 30:
            b.frames(200)
            # A sample can land while a line is still being printed:
            # "Memory 14.7 MB, banks $04-$" and then the whole of it.
            # Only whole lines count -- one that a later one starts with
            # was that later one, caught half written.
            memlines[:] = [m for m in memlines
                           if not any(o != m and o.startswith(m) for o in memlines)]
            return True
    return False


def main(argv):
    rom = next((a.split("=", 1)[1] for a in argv if a.startswith("--os=")), None)
    if not rom:
        print("gem4xe-kmem: needs --os=ROM (Rapidus OS)")
        return 2
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")

    syms = symfile.load(SYMS)
    if not os_profile(os.path.abspath(rom)):
        print("gem4xe-kmem: no firmware entry for the XL ROM to point at the OS")
        return 2
    emu = launch(tag="kmem", memsize="1088K", require_real_rom=False,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    try:
        b.poke(0xD1FF, 0x01)                # the 65C816 before the OS runs
        b.poke(0xD191, 0x00)
        runs = []
        for n in (1, 2):
            mem = []
            ok = wait_desk(b, syms, mem)
            check(ok, f"run {n}: the desktop never started")
            fm = farmem(b, syms)
            fm["mem"] = mem
            runs.append(fm)
            print(f"  run {n}: banks ${fm['first']:02X}-${fm['last']:02X}, image block "
                  f"${fm['km_image']:04X}, heap block ${fm['km_heap']:04X}, held "
                  f"{fm['held']}, clash ${fm['clash']:02X}; {mem}")
            if not ok:
                break
            if n == 1:
                hi = b.peek(HISEGM)
                print(f"  LOSEGM ${b.peek(LOSEGM):02X} HISEGM ${hi:02X}, km_ok "
                      f"{b.peek(syms['km_ok'])}")
                check(b.peek(syms["km_ok"]) == 1, "the OS's allocator was not found")
                check(fm["km_image"] == 0x0100,
                      f"the image's block is ${fm['km_image']:04X}, not $0100")
                check(fm["km_heap"] == fm["first"] << 8,
                      f"the heap's block is ${fm['km_heap']:04X}, not "
                      f"${fm['first'] << 8:04X}")
                check(fm["held"] == 1, "the OS does not list both blocks as allocated")
                check(fm["last"] == hi - 1,
                      f"the heap ends at ${fm['last']:02X}: one bank below HISEGM "
                      f"${hi:02X} is left for somebody else")
                # back to DUP, and gem4xe again -- its variables cleared,
                # so that the wait above is the second run's
                b.key("Q", ctrl=True)
                b.frames(900)
                b.key("L")
                b.frames(30)
                for k in "AUTORUN.SYS":
                    b.key({".": "PERIOD"}.get(k, k))
                    b.frames(6)
                b.poke(syms["irq_cio_swap"], 0)
                b.poke(syms["app_calls"], 0)
                b.poke(syms["app_calls"] + 1, 0)
                b.key("RETURN")
        if len(runs) == 2:
            a, c = runs
            for k in ("first", "last", "km_image", "km_heap", "held", "clash"):
                check(a[k] == c[k], f"the second run's {k} is {c[k]:#x}, the first's "
                                    f"{a[k]:#x}: the first did not give its memory back")
            check(c["mem"] == a["mem"] and len(c["mem"]) == 1,
                  f"the boot screens' Memory lines differ: {a['mem']} then {c['mem']}")
        check(b.peek(syms["irq_fault"]) == 0, f"irq_fault {b.peek(syms['irq_fault'])}")
    finally:
        emu.stop()

    img = atr.ATRImage.load(DISK)
    atr.open_fs(img).add_file("GEM4XE.CFG", CFG_TEXT)
    img.save(FENCED)
    emu = launch(tag="kmem", memsize="1088K", require_real_rom=False,
                 extra_args=["--disk", FENCED])
    b = emu.bridge
    try:
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)
        mem = []
        check(wait_desk(b, syms, mem), "fenced: the desktop never started")
        fm = farmem(b, syms)
        print(f"  HIGHRAM=${HIGHRAM[0]:02X}-${HIGHRAM[1]:02X}: banks ${fm['first']:02X}-"
              f"${fm['last']:02X}, heap block ${fm['km_heap']:04X}; {mem}")
        check((fm["first"], fm["last"]) == (HIGHRAM[0], HIGHRAM[1] - 1),
              f"the heap is ${fm['first']:02X}-${fm['last']:02X}, not "
              f"${HIGHRAM[0]:02X}-${HIGHRAM[1] - 1:02X}")
        check(fm["km_heap"] == HIGHRAM[0] << 8,
              f"the heap's block is ${fm['km_heap']:04X}, not ${HIGHRAM[0] << 8:04X}")
    finally:
        emu.stop()

    print(f"gem4xe-kmem: {'PASS' if not fails else 'FAIL'} -- high RAM taken from "
          f"Rapidus OS and given back: a second run finds it all, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
