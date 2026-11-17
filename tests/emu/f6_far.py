#!/usr/bin/env python3
"""6502 step 3a gate: the far heap on a stock 6502 (docs/6502.md).

build/f6-boot.atr carries F6.COM: src/f6_far.c resident, src/sys/farmem.c's
allocator and src/f6_bank.c in bank 1, the far_* helpers resident
(src/sys6502/farmem6502.c), mapping PORTB data banks behind 24-bit
addresses.  On an 800XL's 6502 with 1088K:

  - the probe makes far banks of the PORTB banks after the code's: four to
    a 64 KB far bank, 14 of them from 64;
  - every address the allocator gave is the one tools/farref.py's model
    gives for the same requests -- the model test-host holds the 65C816's
    allocator to, here with the allocator running in a bank and reaching
    its table through the helpers;
  - the bytes: across a 16 KB PORTB boundary, far to far, a fill, a
    string, across a 64 KB far bank, near memory as bank 0, a bank's own
    code going on in its bank after the helpers have used the window, and
    a marker in every 16 KB piece of a long block reading back as itself.
    Broken on purpose: the helpers not putting the bank back stops the
    program; every piece of a far bank mapped to one PORTB bank passed
    every check until the last was added.

And with --axlon SIZE, on a 130XE with an Axlon of SIZE, whose banks
the probe takes over PORTB's four (src/sys6502/bank6502.s): 2048K makes
31 far banks, 4096K 63.  The top block a3 -- whose string is bit 3 -- stays under
the first megabyte, as the allocator prefers, so the program also writes
the heap's last bytes, far bank 31 (PORTB index 125) or
63 (253): past the 15
far banks fmap took until the Axlon came (src/sys6502/far6502.s).

    python3 tests/emu/f6_far.py [--axlon 2048K|4096K]
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from a8test.launcher import launch          # noqa: E402
import farref                               # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "f6-boot.atr"))
STATUS, ADDRS = 0x0600, 0x0640
CODE_BANKS = 1                          # F6.COM's: tools/bsp6502/rules.mk
BITS = ["16 KB boundary", "far to far", "fill", "string", "64 KB far bank",
        "a bank's code goes on", "bank 0 is near", "16 KB pieces distinct"]
# $0605: the field and string helpers, src/sys6502/far6502.s
FIELDS = ["16-bit field across a piece's end", "32-bit field across a piece's end",
          "string across a piece's end, and its max", "object fields, and the carry into a bank",
          "all of them on near memory"]


def model(banks):
    h = farref.Heap(1, banks)
    a1 = h.alloc(1000)
    a2 = h.alloc(20000)
    a3 = h.alloc_top(300)
    h.free(a1)
    a4 = h.alloc(500)
    a5 = h.alloc_span(70000)
    h.owner = 7
    a6 = h.alloc(100)
    a7 = h.alloc(200)
    h.free_owner(7)
    h.owner = 0
    a8 = h.alloc(150)
    return [a1, a2, a3, a4, a5, a6, a7, a8]


AXLON_BANKS = {"512K": 31, "1024K": 63, "2048K": 127,
               "4096K": 255}               # bank 0 is main


def main(argv):
    fails = []
    axlon = argv[argv.index("--axlon") + 1] if "--axlon" in argv else None

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-f6: the far heap on a stock 6502"
          + (f" with an Axlon of {axlon}" if axlon else ""))
    if axlon:
        # booted through the bridge: --disk with a memory size other than
        # 1088K is not booted (tests/emu/p6_prog.py)
        emu = launch(tag="f6", memsize="128K", vbxe=False, rapidus=False,
                     extra_args=["--axlonmemsize", axlon])
        emu.bridge.boot(DISK)
        found = AXLON_BANKS[axlon]
    else:
        emu = launch(tag="f6", memsize="1088K", vbxe=False, rapidus=False,
                     extra_args=["--disk", DISK])
        found = 64
    b = emu.bridge
    try:
        b.frames(500)
        for _ in range(0, 6000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"F6K":
                break
        st = bytes(b.memdump(STATUS, 3))
        if not check(st == b"F6K", f"the program ran to its end (status {st!r})"):
            return 1
        check(b.cmd("HWSTATE")["cpu"]["mode"] == "6502", "the CPU is a 6502")
        banks = b.peek(STATUS + 3)
        want_banks = (found - CODE_BANKS) // 4
        check(banks == want_banks, f"{banks} far banks; {found} banks less the code's "
                                   f"{CODE_BANKS}, four to a far bank, are {want_banks}")
        got = list(struct.unpack("<8I", bytes(b.memdump(ADDRS, 32))))
        want = model(banks)
        for k, (g, w) in enumerate(zip(got, want), 1):
            check(g == w, f"a{k} at ${g:06X}, the model's ${w:06X}")
        ok = b.peek(STATUS + 4)
        for i, name in enumerate(BITS):
            check(ok & (1 << i), f"bytes: {name}")
        ok = b.peek(STATUS + 5)
        for i, name in enumerate(FIELDS):
            check(ok & (1 << i), f"fields: {name}")
        top = b.peek(STATUS + 6)
        check(top == 1, f"the last far bank's last bytes (far bank {banks}) read back "
                        f"(${STATUS + 6:04X} {top})")
    finally:
        emu.stop()
    print(f"gem4xe-f6: {'PASS' if not fails else 'FAIL'} -- the far heap on a stock 6502, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
