#!/usr/bin/env python3
"""GENERAL.CFG for test-m36: what a person saved last time.

    tools/mkgencfg.py build/general.cfg

The bytes are GENERAL.CPX's own (src/apps/general.c): a mark, the
double-click rate, and which sub-menu delay.  NEITHER VALUE IS THE AES's
DEFAULT -- the machine boots at rate 3 and delay 2 (200 ms) -- so a gate
that reads them back has proved the file was found, read and applied,
rather than that nothing happened.

The mark is the reason a file is needed at all rather than an empty
buffer: a buffer that has never been saved is all zeroes, and every
field in it is a legal value, so without a byte that cannot occur by
accident a fresh machine would come up claiming rate 0.
"""
import sys

GN_MARK = 0x47          # 'G'
RATE = 1                # evnt_dclick 0..4; the AES boots at 3
DELAY = 3               # "Slow" (400 ms); the AES boots at 2 (200 ms)
LEN = 64                # CPXH_BUFLEN


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    buf = bytearray(LEN)
    buf[0] = GN_MARK
    buf[1] = RATE
    buf[2] = DELAY
    with open(argv[1], "wb") as f:
        f.write(bytes(buf))
    print(f"{argv[1]}: {LEN} bytes; rate {RATE}, delay {DELAY}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
