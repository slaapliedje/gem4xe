#!/usr/bin/env python3
"""Gate: linear RAM above bank $00 is found by probing, not by assumption.

gem4xe requires a 65C816 with linear RAM.  Rapidus and Antonia both provide it
and disagree about the map, so farmem_probe() writes each bank's own number
into it and reads them all back -- which sizes real RAM and rejects mirrors
without knowing anything about the board.

Only Rapidus can be tested here: Altirra does not emulate Antonia.  What this
gate proves is that the METHOD works and needs no board-specific knowledge, so
an untested board with linear RAM should work on the same code path.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mkxex                            # noqa: E402
import symfile                          # noqa: E402
from a8test.launcher import launch      # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m3-boot.atr"))
ELF = os.path.abspath(os.path.join(ROOT, "build", "m3.elf"))
SYMS = os.path.abspath(os.path.join(ROOT, "build", "m3.sym"))
STATUS = 0x0600
KINDS = {0: "NONE", 1: "RAPIDUS", 2: "UNKNOWN"}


def main(argv=()):
    # Where the far CODE is, so the gate can insist the far HEAP starts above
    # it.  This is the regression that motivates the check: the first version
    # probed and allocated from bank $01, which is where the code lives, and
    # quietly overwrote three bytes of it.
    segs, _ = mkxex.read_elf(ELF)
    far = [(a, len(d)) for a, d in segs if a > 0xFFFF]
    code_top = max(a + n - 1 for a, n in far)
    want_first = (code_top >> 16) + 1
    print(f"far code   : ${far[0][0]:06X}-${code_top:06X}  "
          f"-> heap must start at bank ${want_first:02X}")

    # --plain816 is the SECOND MACHINE: a bare 65C816 with high banks and
    # no accelerator at all, which is the shape of an Antonia and is what
    # proves nothing here depends on the Rapidus.  Altirra's core always
    # had the CPU model and the bank count as its own settings; only the
    # SDL front end could not reach them, and this tree's fork now can
    # (tools/altirra/altirra-sdl-cpu-highbanks.patch).
    plain = "--plain816" in argv
    emu = launch(tag="m5p" if plain else "m5", memsize="1088K",
                 rapidus=not plain, cpu816=15 if plain else 0,
                 extra_args=["--disk", DISK])
    b = emu.bridge
    fails = []
    try:
        b.frames(300)
        if not plain:
            b.poke(0xD1FF, 0x01)    # the Rapidus switches itself; a plain
            b.poke(0xD191, 0x00)    # 65C816 is already one
            b.frames(500)           # ...and takes a reset to settle
        for k in ("L", "M", "3", "RETURN"):
            b.key(k)
            b.frames(10)
        b.frames(250)
        # Ready, not merely alive -- and the ANSWER to that question is
        # what decides the gate.  An earlier version polled for readiness
        # and then read the buffer regardless, so a runner still probing
        # banks published a zeroed result and the gate announced "no
        # linear RAM found" about a machine that has 12 banks of it.  A
        # buffer that is not ready holds nothing; say so instead.
        # The ceiling is generous because it costs nothing when the runner
        # is ready early: the plain 65C816 loads M3.COM over SIO at the
        # stock speed, and by phase 117 that took 1,850 frames -- exactly
        # the old ceiling, which the runner's growth had used up.
        ready = False
        for _ in range(1000):
            st = bytes(b.memdump(STATUS, 3))
            if st[:2] == b"VD" and st[2] == 1:
                ready = True
                break
            b.frames(4)
        if not ready:
            print(f"runner     : NOT READY after the wait ({st!r})")
            fails.append("runner never published a result -- nothing below is its answer")
        s = bytes(b.memdump(STATUS, 24))
        kind, first, last, banks = s[16], s[17], s[18], s[19]
        mb = (s[20] | (s[21] << 8)) / 16.0
        print(f"board      : {KINDS.get(kind, kind)}")
        print(f"linear RAM : banks ${first:02X}-${last:02X}  "
              f"({banks} banks, {mb:.1f} MB)")
        print(f"alloc test : {'PASS' if s[22] else 'FAIL'} (4K at bank ${s[23]:02X})")

        if kind == 0:
            fails.append("no linear RAM found -- gem4xe cannot run on this machine")
        if plain:
            # A bare 65C816 is not a board the probe can name, and saying
            # so is the right answer rather than a shortcoming: FARMEM_
            # UNKNOWN means "linear RAM found, board not identified".
            if kind != 2:
                fails.append(f"expected an unidentified board, got {KINDS.get(kind)}")
            if banks < 8:
                fails.append(f"only {banks} banks found above the code")
        else:
            if kind != 1:
                fails.append(f"expected the probe to name Rapidus, got {KINDS.get(kind)}")
            if banks < 64:
                fails.append(f"only {banks} banks found; expected a megabyte-class board")
        # Rapidus: SRAM in the low banks is contiguous with the SDRAM above
        # it, so the probe sees one unbroken run reaching to bank $EF.
        # Hardcoding the documented "14.5 MB at $080000" would have missed the
        # first 448 KB.
        if not plain and last != 0xEF:
            fails.append(f"run ends at bank ${last:02X}, expected $EF")
        # ...and it must begin ABOVE the far code, or the program allocates
        # its own text.  Both numbers come from where the linker actually put
        # things, so this keeps working when the code grows into another bank.
        if first != want_first:
            fails.append(f"heap starts at bank ${first:02X}, but the far code "
                         f"reaches ${code_top:06X}: it must start at "
                         f"${want_first:02X}")
        if s[23] < want_first:
            fails.append(f"far_alloc returned bank ${s[23]:02X}, inside the code")
        if not s[22]:
            fails.append("far_alloc round-trip failed")
        if banks != (last - first + 1):
            fails.append("bank count does not match the reported range")
    finally:
        emu.stop()

    print()
    if fails:
        print(f"gem4xe-m5{'p' if plain else ''}: FAILED")
        for f in fails:
            print("   FAIL:", f)
        return 1
    print(f"gem4xe-m5{'p' if plain else ''}: PASSED -- linear RAM discovered and usable on "
          f"{'a plain 65C816' if plain else 'a Rapidus'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
