#!/usr/bin/env python3
"""An application whose far IMAGE is bigger than a bank, loaded and run.

Nothing in this tree had one until GACS's GEM shell was linked for the
65816 -- 102,862 bytes of farcode and another 11 KB of constants, which is
not close to a bank and cannot be made to fit one.  Two limits had been
sitting undisturbed behind that, and NEITHER WOULD HAVE ANNOUNCED ITSELF:

  THE FAR FIXUP OFFSETS WERE u16.  An address needing relocation past
  $FFFF of the image could not be named at all.  tools/mkg4a.py refused a
  multi-bank image up front, which hid it -- and that refusal was itself
  wrong, guarding an invariant the packer does not own: no single FUNCTION
  crosses a bank because each is its own linker fragment placed inside one
  memory, which src/app/gemapp.scm arranges.  Format 2 wrote three bytes;
  it is format 4 now, the same layout renumbered with the COP signatures
  (docs/phase41.md).

  AND app_load COPIED THE IMAGE WITH memcpy_far, WHOSE size_t IS SIXTEEN
  BITS -- gem4xe is built --data-model=small.  A 115 KB image would have
  been copied modulo 65,536, the loader would have reported success, every
  fixup would have applied, and the program would have run into whatever
  was left of the previous tenant partway through.  src/sys/app.c copies in
  chunks a size_t can count.

tests/host/test_g4a.py proves the FILE: that applying its fixups reproduces
ln65816's own far-shifted link byte for byte, which is a stronger statement
than any single run, because it covers every byte rather than the paths one
run happens to take.  What it cannot reach is the LOADER, and that is this.

WHAT THE PROGRAM CHECKS, and why each would otherwise be silent:

  EVERY BLOCK READS BACK AS ITSELF.  Three 20,000-byte far constants whose
  bytes depend on the index and on which block they are in -- so a block
  copied from the wrong place, or not copied at all, is wrong rather than
  merely identical to its neighbour.  The third one lives past 64 KB of
  image and is what a truncated copy loses.

  AND FOUR THOUSAND FAR POINTERS STILL POINT WHERE THEY WERE AIMED.  Bytes
  past 64 KB prove the copy; only an ADDRESS past 64 KB proves the fixup
  offsets, and a byte array holds none.  Each of m31_ptrs[i] was linked
  pointing at m31_blk0 + i, so each is a bank byte the loader must add to,
  and 4,000 of them sit at image offsets a u16 cannot name.  A missing
  fixup leaves one pointing a bank low -- into the program's own code, or
  into the far heap's next tenant -- and reading through it gives a byte
  that is wrong rather than a crash.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, symfile                      # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO,  # noqa: E402
                     SYMS)
from m4_aes import PRELUDE                  # noqa: E402
from m12_file import Runner                 # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402
from m17_desktop import header              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m31-boot.atr"))
HUGE = os.path.join(ROOT, "build", "m31_huge.g4a")
HUGE_SYM = os.path.join(ROOT, "build", "m31_huge.sym")

BLK, NBLK, NPTR = 20000, 3, 4000


def fill(b, i):
    return (i * 7 + b * 131 + 5) & 0xFF


def main(argv):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    hsym = symfile.load(HUGE_SYM)
    link_near, near_size, far_banks = header(HUGE)

    with open(HUGE, "rb") as f:
        hdr = f.read(32)
    ver = hdr[3]
    far_size = int.from_bytes(hdr[10:14], "little")
    check(ver == 4, f"M31.PRG is format {ver}, expected 4 -- an image over "
                    f"a bank cannot be written in format 3")
    check(far_size > 0x10000,
          f"M31.PRG's far image is {far_size} bytes, which is not over a "
          f"bank: this gate would not be testing what it exists to test")
    print(f"  M31.PRG: format {ver}, far image {far_size} bytes over "
          f"{far_banks} bank(s)")

    emu = launch(tag="m31", memsize="1088K", extra_args=["--disk", DISK])
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
        script = aesref.encode(PRELUDE + [(SHELL, (), ())], 0)
        b.memload(r.sa, b"".join(
            (x if x < 32768 else x - 65536).to_bytes(2, "little", signed=True)
            for x in script))
        poke16(b, r.count, NOT_STARTED)
        b.poke(STATUS + ST_GO, 1)

        runs = syms["sh_runs"]
        check(poll(b, runs, 1) >= 0, "the stand-in desktop never started")

        # H: the shell loads M31.PRG and calls it.  It is a bigger file than
        # anything else on the disk, so it gets longer to arrive.
        b.key("H")
        tt = poll(b, runs, 2, limit=9000)
        if tt < 0:
            # sh_lastrc is app_load's own verdict (src/aes/shel.c), which
            # is the difference between "did not load" and "loaded and
            # wedged" -- and between the two of those and a gate that was
            # simply not patient enough with a 100 KB file.
            rc = b.peek16(syms["sh_lastrc"])
            if rc >= 0x8000:
                rc -= 0x10000
            why = {0: "APP_OK", -1: "APP_E_MAGIC (not a G4A, or a version "
                                    "this loader lacks)",
                   -2: "APP_E_SHORT", -3: "APP_E_POOL (no bank-$00 room)",
                   -4: "APP_E_FAR (no far bank)",
                   -5: "APP_E_FIXUP (an offset outside its part)",
                   -6: "APP_E_FILE", -7: "APP_E_READ"}.get(rc, f"status {rc}")
            check(False, f"after H: M31.PRG did not run -- sh_runs "
                         f"{b.peek16(runs)}, last load {why}")
            for ln in screen(b):
                if ln.strip():
                    print("   |" + ln)
            return 1
        near = b.peek16(syms["app_near"])
        m = {n: hsym[n] + near - link_near
             for n in ("m31_ran", "m31_step", "m31_ok", "m31_badblk",
                       "m31_ptrok", "m31_sum")}
        print(f"  M31.PRG ran {tt} frames after H; its near region is at "
              f"${near:04X}")
        # Polled rather than given a fixed number of frames: it reads
        # 60,000 far bytes and dereferences 4,000 far pointers, and how
        # long that takes is the emulated machine's business.
        done = poll(b, m["m31_ran"], 1, limit=6000)
        if done < 0:
            print(f"  (it stopped at step {b.peek16(m['m31_step'])} after "
                  f"6000 frames)")

        step = b.peek16(m["m31_step"])
        check(b.peek16(m["m31_ran"]) == 1,
              f"M31.PRG did not reach its end -- it got to step {step} of 9 "
              f"(1 entered main, 2 past appl_init, 3-5 read the three "
              f"blocks, 8 read the pointer table)")

        bad = b.peek16(m["m31_badblk"])
        if bad >= 0x8000:
            bad -= 0x10000
        check(bad == -1,
              f"block {bad} did not read back as itself -- past 64 KB of "
              f"image that is a copy truncated by a 16-bit size_t")
        check(b.peek16(m["m31_ptrok"]) == 1,
              f"the {NPTR} far pointers do not point where they were aimed "
              f"-- a fixup offset past $FFFF that format 1 could not name")
        check(b.peek16(m["m31_ok"]) == 1, "the program reported a failure")

        want = sum(fill(blk, i) for blk in range(NBLK)
                   for i in range(BLK)) & 0xFFFF
        got = b.peek16(m["m31_sum"])
        check(got == want,
              f"the sum over {NBLK * BLK} far constant bytes is ${got:04X}, "
              f"expected ${want:04X}")
        print(f"  {NBLK} blocks of {BLK} bytes summed to ${want:04X}, and "
              f"all {NPTR} far pointers still point where they were aimed")

        b.key("RETURN")
        check(poll(b, runs, 3) >= 0,
              "the shell did not come back to the desktop after M31.PRG")
    finally:
        emu.stop()

    print(f"gem4xe-m31: {'PASS' if not fails else 'FAIL'} -- an application "
          f"whose far image is bigger than a bank, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
