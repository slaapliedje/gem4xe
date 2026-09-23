"""A gem4xe cartridge: the format, and the boot path.

WHY A CARTRIDGE AT ALL.  The release's own disk answers BOOT ERROR on
its own -- it carries no DOS by design and wants SpartaDOS X in the
machine -- so "download one file and look at it" does not work today.  A
cartridge needs no DOS, because gem4xe asks a D1: for reads and nothing
else at boot (docs/cartridge.md).

WHAT THIS GATE PROVES, which is the first of three steps and
deliberately only the first:

  THE IMAGE IS A CARTRIDGE.  tools/mkcar.py's header, type and checksum
  are what an Atari reads as one.  A wrong type or a wrong checksum
  gives a machine that boots straight past it -- SILENCE, not an error
  -- which is indistinguishable from broken code, and is why this is
  gated before any code goes on top of it.

  BANK 127 IS THE ONE THAT COMES UP.  An AtariMax 1 Mbit maps its LAST
  bank at reset.  Putting the bootstrap in bank 0 produces a perfectly
  valid cartridge that does nothing at all.

  THE OS CALLED BOTH ENTRIES.  CARTSTEP counts how far it got: 1 is
  CARTINI during the OS's own start-up, 2 is the jump to CARTRUN once
  the machine is up, 3 is after it printed.  A number short of 3 says
  WHICH of those did not happen, rather than leaving a blank screen to
  be guessed at.

WHAT IT DOES NOT PROVE, said plainly: nothing about the CPU switch and
nothing about staging.  Those are steps two and three and they get their
own checks.  This is the piece that makes their failures legible.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import mkcar                                # noqa: E402

CAR = os.path.abspath(os.path.join(ROOT, "build", "gem4xe.car"))
CARTSIG, CARTSTEP = 0x0600, 0x0602          # src/cart.s
WANT_SIG = b"G4"
WANT_STEP = 3                               # init, run, printed

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def main():
    print("gem4xe-m37: a cartridge")

    # The file first, on the host: a bad header is cheaper to find here
    # than by watching a machine ignore it.
    with open(CAR, "rb") as f:
        car = f.read()
    check(car[:4] == b"CART", f"the file starts {car[:4]!r}, not b'CART'")
    ctype = int.from_bytes(car[4:8], "big")
    check(ctype == mkcar.CART_TYPE_MAXFLASH_1M,
          f"cartridge type {ctype}, not {mkcar.CART_TYPE_MAXFLASH_1M} "
          f"(AtariMax 1 Mbit)")
    rom = car[16:]
    check(len(rom) == mkcar.BANK * mkcar.BANKS,
          f"{len(rom)} bytes of ROM, not {mkcar.BANK * mkcar.BANKS}")
    want = int.from_bytes(car[8:12], "big")
    check(sum(rom) & 0xFFFFFFFF == want,
          "the checksum in the header is not the sum of the ROM, so "
          "Altirra will refuse the image")

    # ...and that the bootstrap is in the bank the machine comes up on.
    boot = rom[mkcar.BOOT_BANK * mkcar.BANK:(mkcar.BOOT_BANK + 1) * mkcar.BANK]
    check(boot[-4] == 0,
          f"$BFFC of bank {mkcar.BOOT_BANK} is ${boot[-4]:02X}, not 0: the "
          f"OS does not see a cartridge there")
    check(boot[-3] & 0x04,
          f"$BFFD is ${boot[-3]:02X}, and bit 2 is what makes the OS jump "
          f"to CARTRUN")
    check(boot != bytes([mkcar.ERASED]) * mkcar.BANK,
          f"bank {mkcar.BOOT_BANK} is erased -- the bootstrap went "
          f"somewhere else, and a cartridge that maps an empty bank at "
          f"reset is valid and does nothing")

    emu = launch(tag="m37", memsize="1088K", extra_args=["--cart", CAR])
    b = emu.bridge
    try:
        b.frames(400)
        sig = bytes(b.memdump(CARTSIG, 2))
        step = b.peek(CARTSTEP)
        print(f"  CARTSIG {sig!r}, CARTSTEP {step}")
        check(step >= 1, "the OS never called CARTINI: it did not see a "
                         "cartridge at all (the header, or the type)")
        check(step >= 2, "CARTINI ran and the OS never jumped to CARTRUN: "
                         "$BFFD bit 2")
        check(step == WANT_STEP, f"CARTSTEP {step}, not {WANT_STEP}")
        check(sig == WANT_SIG, f"CARTSIG {sig!r}, not {WANT_SIG!r}")
        b.screenshot(os.path.join(ROOT, "build", "shots", "m37_cart.png"))
    finally:
        emu.stop()

    print(f"\ngem4xe-m37: {'PASS' if not problems else 'FAIL'} -- a "
          f"cartridge, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
