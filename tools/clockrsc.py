#!/usr/bin/env python3
"""CLOCK.RSC: the clock's resource, built on the host.

    tools/clockrsc.py build/clock.rsc build/clockrsc.h

One tree, ADCLOCK: a panel with the time, the date under it and a Quit
button.  The program does NOT use form_do -- it waits on a timer with
evnt_multi and finds its own clicks with objc_find, because a clock that
blocks in form_do cannot tick -- so nothing here is an EXIT button
except Quit, which the program tests for itself.

Both fields are G_BOXTEXT over a TEDINFO the program writes in place.
The templates decide the SHAPE of what is shown -- "__:__:__" and
"__/__/__" -- and the program fills the runs of underscores in the
order it is given them, so a translation may write the date the other
way round without a line of C changing (src/apps/clock.c, the same
rule as the desktop's text view).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                  # noqa: E402
from rsc import ch, NIL                     # noqa: E402
from aesref import (G_BOX, G_STRING, G_BUTTON, G_BOXTEXT,  # noqa: E402
                    NONE, NORMAL, SELECTABLE, DEFAULT, EXIT, LASTOB,
                    TE_CNTR, IBM)

ADCLOCK = 0
(KROOT, KTITLE, KTIME, KDATE, KQUIT) = range(5)
NOBS_CLOCK = 5

W, H = 24, 11
TITLE = "CLOCK"
TIME_TMPL = "__:__:__"
DATE_TMPL = "__/__/__"


def clock_tree(r):
    objs = [
        (NIL, KTITLE, KQUIT, G_BOX, NONE, NORMAL, 0x00021100,
         ch(0), ch(0), ch(W), ch(H)),
        (KTIME, NIL, NIL, G_STRING, NONE, NORMAL, r.string(TITLE),
         ch((W - len(TITLE)) // 2), ch(1), ch(len(TITLE)), ch(1)),
        (KDATE, NIL, NIL, G_BOXTEXT, NONE, NORMAL,
         r.ted(" " * len(TIME_TMPL), TIME_TMPL, "9",
               font=IBM, just=TE_CNTR, thickness=0),
         ch((W - len(TIME_TMPL) - 2) // 2), ch(3), ch(len(TIME_TMPL) + 2), ch(1)),
        (KQUIT, NIL, NIL, G_BOXTEXT, NONE, NORMAL,
         r.ted(" " * len(DATE_TMPL), DATE_TMPL, "9",
               font=IBM, just=TE_CNTR, thickness=0),
         ch((W - len(DATE_TMPL) - 2) // 2), ch(5), ch(len(DATE_TMPL) + 2), ch(1)),
        (KROOT, NIL, NIL, G_BUTTON, SELECTABLE | DEFAULT | EXIT | LASTOB,
         NORMAL, r.string("Quit"), ch((W - 8) // 2), ch(7), ch(8), ch(2)),
    ]
    assert len(objs) == NOBS_CLOCK, (len(objs), NOBS_CLOCK)
    return r.tree(objs, look3d=True)


INDICES = [("ADCLOCK", ADCLOCK), ("KROOT", KROOT), ("KTITLE", KTITLE),
           ("KTIME", KTIME), ("KDATE", KDATE), ("KQUIT", KQUIT),
           ("NOBS_CLOCK", NOBS_CLOCK)]


def build():
    r = rsc.Rsc()
    assert clock_tree(r) == ADCLOCK
    return r


def c_header(data):
    lines = [f"/* {os.path.basename(sys.argv[0])}: CLOCK.RSC's indices "
             f"(the file is {len(data)} bytes).  Generated -- do not edit. */",
             "#ifndef GEM4XE_CLOCK_RSC_H", "#define GEM4XE_CLOCK_RSC_H",
             f"#define CLOCK_RSC_SIZE {len(data)}"]
    lines += [f"#define {name:<12s} {value}" for name, value in INDICES]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    data = build().file()
    with open(argv[1], "wb") as f:
        f.write(data)
    with open(argv[2], "w") as f:
        f.write(c_header(data))
    print(f"{argv[1]}: {len(data)} bytes, {NOBS_CLOCK} objects; {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
