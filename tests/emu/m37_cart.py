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

  THE CPU SWITCH, BOTH WAYS.  A Rapidus ALWAYS cold-boots as a 6502, so
  a cartridge that ran only on a machine somebody had already switched
  by hand would be a poor first screen.  This finds the card, switches
  it, and the reset brings the machine straight back to the cartridge --
  which is EASIER here than from a disk, where farload has to force a
  cold start so the DOS runs its start-up file again.  The cartridge is
  still in the slot; the OS calls it again by itself.

  AND IT CANNOT LOOP, which is worth proving rather than reasoning
  about.  Switching resets the CPU and nothing else -- the card keeps
  its mode across it -- so the second pass finds a 65816 and stops.  The
  same image is then booted on a machine with NO Rapidus, where it must
  say so and stop rather than search forever.  Two machines, two
  answers, and they have to differ or the pair proves nothing.

WHAT IT DOES NOT PROVE, said plainly: nothing about staging and nothing
about the read-only D1:.  Those are steps two and three and they get
their own checks.  This is the piece that makes their failures legible.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import mkcar                                # noqa: E402

CAR = os.path.abspath(os.path.join(ROOT, "build", "gem4xe.car"))
CARTSIG, CARTSTEP, CARTCPU = 0x0600, 0x0602, 0x0603      # src/cart.s
WANT_SIG = b"G4"
STEP_PRINTED, STEP_816, STEP_NO816 = 3, 6, 6
STEP_STAGED, STEP_NORAM = 8, 9
CPU_816, CPU_NO816 = 1, 2
DEST = 0x010000                             # src/cart.s DEST_BANK
PAY_BANKS = 2                               # ...and PAY_BANKS

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

    for tag, rapidus, want_step, want_cpu, what in (
            ("m37", True, STEP_STAGED, CPU_816,
             "a Rapidus, cold-booted as a 6502 as one always is"),
            ("m37no816", False, STEP_NO816, CPU_NO816,
             "a plain 6502 with no accelerator")):
        emu = launch(tag=tag, memsize="1088K", rapidus=rapidus,
                     extra_args=["--cart", CAR])
        b = emu.bridge
        try:
            # Long enough for the switch, the CPU reset and the second pass.
            b.frames(900)
            sig = bytes(b.memdump(CARTSIG, 2))
            step, cpu = b.peek(CARTSTEP), b.peek(CARTCPU)
            print(f"  {what}: CARTSIG {sig!r}, CARTSTEP {step}, CARTCPU {cpu}")
            check(step >= 1, f"{tag}: the OS never called CARTINI -- it did "
                             f"not see a cartridge at all (the header, or "
                             f"the type)")
            check(step >= 2, f"{tag}: CARTINI ran and the OS never jumped to "
                             f"CARTRUN: $BFFD bit 2")
            check(step >= STEP_PRINTED,
                  f"{tag}: CARTRUN ran and never finished printing")
            check(sig == WANT_SIG, f"{tag}: CARTSIG {sig!r}, not {WANT_SIG!r}")
            check(step == want_step, f"{tag}: CARTSTEP {step}, not {want_step}")
            check(cpu == want_cpu, f"{tag}: CARTCPU {cpu}, not {want_cpu}")
            if want_cpu == CPU_816:
                # ...and every byte of the payload, out of the cartridge
                # and into far memory.  Compared HERE rather than by the
                # cartridge: what the machine says about its own copy is
                # worth less than what the copy says.
                bad = 0
                for k in range(PAY_BANKS):
                    got = bytes(b.memdump(DEST + k * mkcar.BANK, mkcar.BANK))
                    want = mkcar.test_pattern(k)
                    n = sum(1 for x, y in zip(got, want) if x != y)
                    print(f"    bank {k} -> ${DEST + k * mkcar.BANK:06X}: "
                          f"{mkcar.BANK - n}/{mkcar.BANK} bytes")
                    bad += n
                check(bad == 0, f"{tag}: {bad} byte(s) of the payload did not "
                                f"arrive -- the pattern depends on the offset "
                                f"AND the bank, so a swap or a doubled bank "
                                f"shows here too")
            b.screenshot(os.path.join(ROOT, "build", "shots", f"{tag}.png"))
        finally:
            emu.stop()

    # ...and the two answers must differ, or the pair proves nothing: a
    # cartridge that said CPU_816 on every machine would pass the first
    # case and be wrong about the second.
    check(CPU_816 != CPU_NO816, "the two machines are expected to give the "
                                "same answer, so this gate is vacuous")

    print(f"\ngem4xe-m37: {'PASS' if not problems else 'FAIL'} -- a "
          f"cartridge, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
