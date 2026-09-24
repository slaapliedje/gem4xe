#!/usr/bin/env python3
"""Milestone 1: a C program compiled by Calypsi runs on the Rapidus 65C816.

Proves end to end: cc65816 -> ln65816 -> mkxex.py -> Atari DOS loader ->
65C816 native mode -> our code executes and 16-bit arithmetic is correct.

The CPU must be switched to the 65C816 before the program is STARTED,
because Calypsi's cstartup begins with `clc; xce` and `xce` is not a 6502
opcode -- and it must be switched while the machine is idle at the DOS
prompt, not during the boot, because a write made mid-SIO is lost and the
DOS hangs.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from a8test.launcher import launch  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m14_sparta import wait_prompt  # noqa: E402

SIG = 0x0600
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DISK = os.path.abspath(os.path.join(ROOT, "build", "hello-boot.atr"))
EXPECT_SUM = sum(i * i for i in range(1, 101)) & 0xFFFF


def main():
    emu = launch(tag="m1", memsize="1088K", extra_args=["--disk", DISK])
    b = emu.bridge
    fails = []
    try:
        # SWITCH ONLY WHEN THE MACHINE IS IDLE.  A write made while the DOS
        # is mid-SIO is lost and the DOS hangs (docs/shipping.md section 2,
        # which is why test-boot waits too).  This gate used to switch at
        # "frame 30" -- which is frame 30 after the bridge connected, and
        # the bridge connects 50-100 frames into a boot that is already
        # running, later on a loaded host.  So the switch sometimes landed
        # in the boot's disk I/O and the machine never reached a prompt:
        # four failures, all inside a full suite, 2026-09-24.  Now: the 6502
        # boot runs to its prompt, then the switch, then the prompt again.
        if wait_prompt(b) < 0:
            fails.append("the DOS never reached its D1: prompt on the 6502")
        b.poke(0xD1FF, 0x01)
        b.poke(0xD191, 0x00)                       # clear bit 6 -> 65C816 + reset
        b.frames(50)                               # past the reset, whose
                                                   # screen is a fresh one
        if wait_prompt(b) < 0:
            fails.append("the DOS never showed its D1: prompt after the switch")
        mode = b.cmd("HWSTATE")["cpu"]["mode"]
        print(f"CPU mode at the DOS prompt: {mode}")
        if mode != "65C816":
            fails.append(f"CPU is {mode}, expected 65C816")

        # DOS II+/D 6.4 boots to a "D1:" prompt, so type the program name.
        # Starting it here -- after the switch -- is the whole point: the
        # Rapidus cold-boots as a 6502 and switching resets the CPU, so a
        # program can never switch the CPU and keep running.
        for k in ("H", "E", "L", "L", "O", "RETURN"):
            b.key(k)
            b.frames(6)
        # ...and wait for the program's signature, not for a fixed time.
        for _ in range(0, 2000, 25):
            b.frames(25)
            if bytes(b.memdump(SIG, 4)) == b"GEM4":
                break
        b.frames(25)

        got = bytes(b.memdump(SIG, 8))
        st = b.cmd("HWSTATE")["cpu"]
        print(f"$0600 = {got.hex(' ')}   ({got[:4]!r})")
        print(f"CPU after run: mode={st['mode']} PC={st['PC']}")

        if got[:4] != b"GEM4":
            fails.append(f"signature is {got[:4]!r}, expected b'GEM4' -- program did not run")
        else:
            chk = got[4] | (got[5] << 8)
            print(f"checksum = {chk} (${chk:04X}), expected {EXPECT_SUM} (${EXPECT_SUM:04X})")
            if chk != EXPECT_SUM:
                fails.append(f"checksum {chk} != {EXPECT_SUM} -- 16-bit arithmetic is wrong")
            print(f"sizeof(int)={got[6]}  sizeof(void*)={got[7]}")
            if got[6] != 2:
                fails.append(f"sizeof(int) is {got[6]}, expected 2")
            if got[7] != 2:
                fails.append(f"sizeof(void*) is {got[7]}, expected 2 in the small data model")
        if st["mode"] != "65C816":
            fails.append(f"CPU left 65C816 mode (now {st['mode']})")
    finally:
        emu.stop()

    print()
    if fails:
        print(f"gem4xe-m1: {len(fails)} FAILED")
        for f in fails:
            print("   FAIL:", f)
        return 1
    print("gem4xe-m1: 5/5 checks passed -- Calypsi C runs on the 65C816")
    return 0


if __name__ == "__main__":
    sys.exit(main())
