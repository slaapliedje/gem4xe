#!/usr/bin/env python3
"""d6_sio.py -- make test-d6sio: the pointer sampler is silent through SIO.

src/sys/cio.c takes timer 1 out of POKMSK and IRQEN for every CIO and SIO
call on the 6502, as src/sys/cio.s does on the 65C816, and puts it back
after.  Running through SIO, the sampler hung the desktop's load on
MiSTer's Atari800 core every time: the machine stopped inside SIO, and
the core's drive was left with half a command frame.  Altirra loads the
desktop either way, so the gate holds the rule itself rather than the
symptom.

Loads the desktop as test-d6 does (A6 on D1:, the desktop on D2:), but
with real serial timing (--nosiopatch): under --siopatch SIO finishes
inside one instruction and is never seen.

Every other frame of the load it reads CRITIC ($42), set while SIO moves
bytes, and POKMSK ($10): timer 1 (bit 0) must be clear in every sample
taken inside SIO, and there must be at least 20 such samples.  Then the load must have worked: CIO's 1 and
the desktop's first turn over ($060C 'R').

    python3 tests/emu/d6_sio.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import a8test.launcher as L                 # noqa: E402

DISK = os.path.abspath(os.path.join(ROOT, "build", "a6d-boot.atr"))
DESK = os.path.abspath(os.path.join(ROOT, "build", "a6d-desk.atr"))
STATUS = 0x0600
CRITIC = 0x42
POKMSK = 0x10
MIN_SIO = 20


def main():
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)

    print("gem4xe-d6sio: the pointer sampler is silent through SIO")
    L.BASE_ARGS = ["--nosiopatch" if a == "--siopatch" else a for a in L.BASE_ARGS]
    emu = L.launch(tag="d6sio", memsize="1088K", vbxe=False, rapidus=False,
                   extra_args=["--disk", DISK])
    b = emu.bridge
    b.mount(1, DESK)
    try:
        b.frames(500)
        for _ in range(0, 12000, 50):
            b.frames(50)
            if bytes(b.memdump(STATUS, 3)) == b"A6K" or b.peek(STATUS + 4):
                break
        b.poke(STATUS + 12, 2)              # the desktop, at the go
        b.poke(STATUS + 6, 1)
        in_sio = loud = 0
        for _ in range(4000):
            b.frames(2)
            if b.peek(CRITIC):
                in_sio += 1
                loud += b.peek(POKMSK) & 1
            if b.peek(STATUS + 12) in (ord("R"), ord("H")):
                break
        check(in_sio >= MIN_SIO and not loud,
              f"timer 1 out of POKMSK through SIO: in it in {loud} of the {in_sio} "
              f"samples taken inside SIO; want 0, of at least {MIN_SIO}")
        rd, slot = b.peek(STATUS + 13), b.peek(STATUS + 12)
        check(rd == 1 and slot == ord("R"),
              f"the desktop loaded (CIO {rd}) and its first turn ended "
              f"({chr(slot) if slot > 31 else slot}); want 1, 'R'")
    finally:
        emu.stop()
    print(f"gem4xe-d6sio: {'PASS' if not fails else 'FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
