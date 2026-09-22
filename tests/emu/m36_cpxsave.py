"""A module's settings, saved once and put back at the NEXT boot.

This is the claim that makes a control panel worth having, and it is the
one that cannot be checked by looking at the machine while it is up:
"the setting survived" is only true across a restart.

THE DISK carries a GENERAL.CFG written by tools/mkgencfg.py -- the bytes
GENERAL.CPX itself writes when somebody presses OK (src/apps/general.c:
a mark, the double-click rate, the sub-menu delay).  Nothing in this gate
drives the panel: the file stands for a person having used it last time,
which is exactly the state a reboot has to honour.

WHAT HAPPENS AT BOOT, and it is three pieces meeting:

  the AES      loads *.CPX before the accessories, on purpose, so that
               the panel exists after its modules do (src/aes/shel.c)
  the AES      reads GENERAL.CFG into the module's header afterwards,
               laying the saved bytes over the defaults the module just
               wrote (sh_cpxcfg)
  the PANEL    opens every CPX_BOOTINIT module once with booting set,
               so it can put its settings back before anybody sees the
               machine (cp_bootinit)

and the module does the applying, because only it knows what its own
sixty-four bytes mean.

WHAT IT CHECKS.  gl_dcindex is 1 and the sub-menu delay is 400 ms.

NEITHER IS A DEFAULT, which is the whole design of the fixture: the AES
boots at rate 3 (src/aes/event.c, ev_init) and 200 ms (src/aes/menu.c,
MN_INIT_DISPLAY).  A gate whose expected value is also the default
passes on a machine that restored nothing, which is the failure this
project has a memory about -- so the file says 1 and 400.

AND THE CONTROL: the same system booted from the disk WITHOUT a
GENERAL.CFG must come up at 3 and 200.  Without it, "1" could mean the
saved file was read or it could mean something unrelated set the rate to
1, and the two look identical from here.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile                              # noqa: E402

SAVED = os.path.abspath(os.path.join(ROOT, "build", "m36-boot.atr"))
PLAIN = os.path.abspath(os.path.join(ROOT, "build", "gem-shots.atr"))
SYMS = symfile.load(os.path.join(ROOT, "build", "gem.sym"))

WANT_RATE, WANT_MS = 1, 400          # tools/mkgencfg.py
DEF_RATE, DEF_MS = 3, 200            # the AES's own, and not these

problems = []


def check(ok, what):
    if not ok:
        problems.append(what)
        print(f"  FAIL: {what}")
    return ok


def boot(disk, tag):
    """Cold-start `disk` into the desktop and read the live settings."""
    emu = launch(tag=tag, memsize="1088K", extra_args=["--disk", disk])
    b = emu.bridge
    try:
        b.frames(2600)
        # mn_display is static in src/aes/menu.c, so the delay is read
        # through the call that reports it rather than off a symbol: the
        # AES keeps it as a LONG of milliseconds.
        return {
            "rate": b.peek16(SYMS["gl_dcindex"]),
            "ncpx": b.peek16(SYMS["sh_ncpx"]),
            "bad":  b.peek16(SYMS["gem_bad"]),
            "fault": b.peek(SYMS["irq_fault"]),
        }
    finally:
        emu.stop()


def main():
    print("gem4xe-m36: a module's settings across a reboot")
    for s in ("gl_dcindex", "sh_ncpx"):
        if s not in SYMS:
            print(f"  FAIL: build/gem.sym has no {s}")
            return 1

    a = boot(SAVED, "m36")
    print(f"  with GENERAL.CFG:    {a['ncpx']} module(s), "
          f"double-click rate {a['rate']}, {a['bad']} refused")
    check(a["ncpx"] >= 1, f"{a['ncpx']} modules loaded: GENERAL.CPX is not there")
    check(a["rate"] == WANT_RATE,
          f"the double-click rate is {a['rate']}, not the {WANT_RATE} that "
          f"was saved -- the settings were not put back at boot")
    check(a["bad"] == 0, f"{a['bad']} AES call(s) refused")
    check(a["fault"] == 0, f"irq_fault {a['fault']}")

    # ...and the control, without which "1" proves nothing.
    c = boot(PLAIN, "m36ctl")
    print(f"  without GENERAL.CFG: {c['ncpx']} module(s), "
          f"double-click rate {c['rate']}")
    check(c["rate"] == DEF_RATE,
          f"with no saved file the rate is {c['rate']}, not the AES's "
          f"default {DEF_RATE} -- so the gate above proves nothing")
    check(a["rate"] != c["rate"],
          "the saved rate and the default are the same number, so this "
          "gate would pass on a machine that restored nothing")

    print(f"\ngem4xe-m36: {'PASS' if not problems else 'FAIL'} -- a module's "
          f"settings across a reboot, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
