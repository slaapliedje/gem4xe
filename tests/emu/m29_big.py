#!/usr/bin/env python3
"""Phase 37 gate: an application whose variables live in far memory.

The two programs gem4xe exists for -- GACS and RetroWP -- are written to
`--data-model=large`, where a pointer is 24 bits and the compiler puts
every global above bank $00.  GACS's engine is 24 KB of code, 56 KB of
data and 18 KB of constants, and it wants **84 bytes of bank $00** when
compiled that way (`make gacs-check`, docs/gacs.md).  An application here
gets 2 KB of bank $00, so that model is not a preference, it is the only
way either program fits.

Until now the application linker map had nowhere to put such a program's
variables: it named `farcode`, `switch`, `cfar`, `libcode` and `code`,
and none of those is where a large-data compiler puts a global.  This
gate is the smallest program that proves the map, run through the real
shell loop.

WHAT IT CHECKS, and why each one would otherwise be silent:

  ZFAR ARRIVED ZEROED.  A far bss section is made at start-up, not
  loaded.  If the loader gave the program a bank somebody else was
  using, it would arrive full of their bytes.

  FAR ARRIVED INITIALISED.  An initialised far array is the harder case:
  its values are COPIED there by the crt's data_init_table walk, from an
  initialiser the linker puts elsewhere.  If that does not happen the
  array reads as zeroes and nothing else goes wrong.

  THE SUM IS RIGHT ACROSS 3,000 ENTRIES.  The pattern depends on the
  index, so a pointer that wrapped inside a bank -- which is what 16-bit
  arithmetic on a far array would do -- sums differently rather than
  crashing.  The gate computes the same sum in Python.

  AND THE PROGRAM'S FAR REGION IS TWO BANKS.  Its variables are in the
  bank above its code, and the loader allocates whole banks from a count
  in the .G4A header.  That count is taken from the linker's map and not
  from the image, because a far bss carries no bytes: sizing it from the
  image would have given the program one bank and left its variables in
  memory the far heap goes on to hand somebody else, with nothing failing
  at the time (tools/mkg4a.py, far_span).
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import aesref, symfile, vbxeref             # noqa: E402
from m7_form import (poke16, NOT_STARTED, STATUS, ST_GO,  # noqa: E402
                     SYMS)   # build/m3.sym: this disk's runner
from m4_aes import PRELUDE                  # noqa: E402
from m12_file import Runner                 # noqa: E402
from m14_sparta import boot, screen         # noqa: E402
from m16_shell import SHELL, poll           # noqa: E402
from m17_desktop import header              # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "m29-boot.atr"))
BIG = os.path.join(ROOT, "build", "m29_big.g4a")
BIG_SYM = os.path.join(ROOT, "build", "m29_big.sym")

N = 3000
SEED = [11, 22, 33, 44, 55, 66, 77, 88]

# The window M29.PRG opens, and the strip of it the title lives in.  The
# gate reads the SCREEN for the title rather than a returned word,
# because wind_set answering 1 says only that the AES took the address.
TITLE_X, TITLE_Y, TITLE_W, TITLE_H = 0, 16, 320, 20


def titlebar(path):
    """The window's title strip out of an Altirra screenshot, as pixels."""
    from PIL import Image
    px = Image.open(path).convert("RGB").load()
    return [px[vbxeref.SHOT_X0 + TITLE_X + x, vbxeref.SHOT_Y0 + TITLE_Y + y]
            for y in range(TITLE_H) for x in range(TITLE_W)]


def main(argv):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print(f"  FAIL: {msg}")
        return cond

    syms = symfile.load(SYMS)
    bsym = symfile.load(BIG_SYM)
    link_near, near_size, far_banks = header(BIG)
    check(far_banks == 2,
          f"M29.PRG's header asks for {far_banks} far bank(s), expected 2 -- "
          f"its variables are in the bank above its code")

    emu = launch(tag="m29", memsize="1088K", extra_args=["--disk", DISK])
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

        # B: the shell loads M29.PRG and calls it.
        b.key("B")
        tt = poll(b, runs, 2)          # it waits for a key before it exits
        check(tt >= 0, f"after B: M29.PRG did not run (sh_runs "
                       f"{b.peek16(runs)})")
        if tt < 0:
            return 1
        b.frames(120)

        near = b.peek16(syms["app_near"])
        big = {n: bsym[n] + near - link_near
               for n in ("m29_ran", "m29_zeroed", "m29_seedok", "m29_sum",
                         "m29_first", "m29_last", "m29_step", "m29_alert", "m29_wfar", "m29_wnear")}
        print(f"  M29.PRG ran {tt} frames after B; its near region is at "
              f"${near:04X}, {far_banks} far banks")

        step = b.peek16(big["m29_step"])
        check(b.peek16(big["m29_ran"]) == 1,
              f"M29.PRG did not reach its end -- it got to step {step} of 9 "
              f"(1 entered main, 2 past appl_init, 3 read the far bss, "
              f"4 read the initialised far array, 5 wrote and summed them, "
              f"6-8 drew the window with a far, a near and an empty title, "
              f"9 drew the alert)")
        check(b.peek16(big["m29_zeroed"]) == 1,
              "its far bss did not arrive zeroed -- the bank it was given "
              "held somebody else's bytes")
        check(b.peek16(big["m29_seedok"]) == 1,
              "its initialised far array did not arrive initialised -- the "
              "crt's data_init_table walk did not reach it")

        want = [(SEED[i & 7] + i) & 0xFFFF for i in range(N)]
        want = [w - 0x10000 if w >= 0x8000 else w for w in want]
        check(b.peek16(big["m29_first"]) == (want[0] & 0xFFFF),
              f"big[0] is {b.peek16(big['m29_first'])}, expected {want[0]}")
        check(b.peek16(big["m29_last"]) == (want[-1] & 0xFFFF),
              f"big[{N - 1}] is {b.peek16(big['m29_last'])}, expected "
              f"{want[-1]}")
        exp = sum(want) & 0xFFFF
        got = b.peek16(big["m29_sum"])
        check(got == exp,
              f"the sum over {N} far entries is {got}, expected {exp} -- a "
              f"pointer that wrapped inside the bank would read like this")
        print(f"  {N} far entries: big[0]={want[0]}, big[{N - 1}]="
              f"{want[-1]}, sum ${exp:04X} -- all as the model has them")

        # THE WINDOW TITLE.  The program is blocked with its window open
        # and a FAR title on it; a key moves it to the same eleven
        # characters NEAR, and another to an empty title.  What is
        # asserted is the SCREEN: far and near must draw identically --
        # the near path is m8's to prove -- and both must differ from
        # empty, so two blank title bars cannot pass the first test.
        bars = {}
        for stage, which in ((6, "far"), (7, "near"), (8, "empty")):
            if not check(poll(b, big["m29_step"], stage) >= 0,
                         f"M29.PRG never reached step {stage} (the {which} "
                         f"title); it is at {b.peek16(big['m29_step'])}"):
                return 1
            b.frames(10)
            p = os.path.join(ROOT, "build", f"m29-title-{which}.png")
            b.screenshot(p)
            bars[which] = titlebar(p)
            b.key("RETURN")

        wfar, wnear = b.peek16(big["m29_wfar"]), b.peek16(big["m29_wnear"])
        check(wfar == 1, f"wind_set(WF_NAME) with a FAR title answered "
                         f"{wfar}, not 1")
        check(wnear == 1, f"wind_set(WF_NAME) with a NEAR title answered "
                          f"{wnear}, not 1")
        diff = sum(1 for a, c in zip(bars["far"], bars["near"]) if a != c)
        check(diff == 0,
              f"the title bar drawn from a FAR address differs from the same "
              f"eleven characters drawn from a NEAR one in {diff} of "
              f"{len(bars['far'])} pixels -- the far title was not brought "
              f"down at draw time (w_ptext, src/aes/wind.c)")
        blank = sum(1 for a, c in zip(bars["far"], bars["empty"]) if a != c)
        check(blank > 0,
              "the FAR title bar is pixel-identical to the EMPTY one -- "
              "nothing was drawn, and the comparison above passed only "
              "because both titles were blank")
        print(f"  WF_NAME: a far title drawn exactly as the same near one "
              f"({diff} px differ), and {blank} px of it that an empty "
              f"title does not have")

        # The app is now blocked in form_alert with a FAR string literal --
        # in --data-model=large that literal is far, and near_of would have
        # nulled it (the peer's GACS bug).  RETURN picks the default button.
        check(poll(b, big["m29_step"], 9) >= 0,
              "M29.PRG never reached its form_alert")
        b.frames(60)            # the modal is drawn and waiting by now
        b.screenshot(os.path.join(ROOT, "build", "m29-alert.png"))
        b.key("RETURN")
        # poll for the button rather than reading at a fixed frame: an
        # alert still being drawn reads the same as one that failed
        poll(b, big["m29_alert"], 1)
        al = b.peek16(big["m29_alert"])
        check(al == 1, f"form_alert with a far string returned {al}, not the "
              f"button -- the shim did not bounce the far literal, which at "
              f"102 bytes is past the 64-byte near scratch and goes through "
              f"the AES's pool instead (pool_str, src/sys/abi.c)")
        print(f"  form_alert: a 102-byte FAR string answered with button {al} "
              f"-- bounced through the pool, not the near scratch")

        # Let it go, and see the shell put the desktop back over it.
        b.key("RETURN")
        check(poll(b, runs, 3) >= 0,
              "the shell did not come back to the desktop after M29.PRG")
    finally:
        emu.stop()

    print(f"gem4xe-m29: {'PASS' if not fails else 'FAIL'} -- an application "
          f"with its variables in far memory, {len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
