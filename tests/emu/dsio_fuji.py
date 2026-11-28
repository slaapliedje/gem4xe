#!/usr/bin/env python3
"""Dsio: a program's SIO frame to the FujiNet (docs/fujinet-plan.md, step 2).

The runner on G4DOS (build/m15g-boot.atr) makes the calls through its
sys op, as test-m62 makes Drwsec's.  The machine has Altirra's NetSIO
device on its bus, and through the NetSIO hub a FujiNet-PC answers as
device $70 -- the rig of the plan's step 1, which must be running:

    FUJINET_SD   the FujiNet-PC's SD folder (default ~/dev/fujinet-run/SD),
                 its Host 1, listed here on the host to know the answers
    NETSIO_DEV   Altirra's netsio.atdevice

What is checked, all through Dsio:

  - Read host slots: Host 1 is "SD".
  - Mount host 1; Open directory /GAMES/ (a write); Read directory
    entry with the extra details until $7F $7F; Close directory.  The
    names, the folder flags and the sizes must be the SD folder's.
  - The read into FAR memory (Malloc) as well as into bank $00: the
    bounce through the pool.
  - Open directory on a folder that is not there: ERROR or EDRVNR (the
    OS's retry of a refused write times out), and the FujiNet answering
    after it.
  - Read device slots: 304 bytes, more than a sector, in one frame;
    the rig mounts nothing, so all eight empty (host $FF).
  - The refusals: device $31 (a disk: never around G4DOS) EINVFN; 513
    bytes, a read of 0 bytes, a direction of 3 EBADRQ.

With no hub every frame times out (EDRVNR): the gate FAILS then, it does
not skip.  It is not in `make test` until the gates start the rig
themselves.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a8test.launcher import launch          # noqa: E402
import symfile                              # noqa: E402
from m7_form import SYMS                    # noqa: E402
from m12_file import Runner                 # noqa: E402
import m15_gdos as m15                      # noqa: E402
from m15_gdos import Gdos, W, L, BUF        # noqa: E402
from m62_drive import boot                  # noqa: E402

m15.FN.update(Dsio=0x1FB)
ERROR, EDRVNR, EBADRQ, EINVFN = -1, -2, -5, -32
DS_NONE, DS_READ, DS_WRITE = 0, 1, 2
FUJI = 0x70
F_READ_DEVS = 0xF2
F_READ_HOSTS, F_MOUNT_HOST, F_OPEN_DIR, F_READ_ENTRY, F_CLOSE_DIR = 0xF4, 0xF9, 0xF7, 0xF6, 0xF5
ENTRY_LEN = 64
EXTRA = 0x80                                # AUX2: the 13 bytes of details first

G4DISK = os.path.abspath(os.path.join(ROOT, "build", "m15g-boot.atr"))
SD = os.path.expanduser(os.environ.get("FUJINET_SD", "~/dev/fujinet-run/SD"))
NETSIO = os.environ.get("NETSIO_DEV", "/run/media/jfergus/Stuff/claude-scratch/gem4xe/"
                        "fujinet/fujinet-emulator-bridge/altirra-custom-device/netsio.atdevice")
FOLDER = "GAMES"


def expected():
    """The folder as the host has it: {name: (is_dir, size)}."""
    out = {}
    for n in os.listdir(os.path.join(SD, FOLDER)):
        p = os.path.join(SD, FOLDER, n)
        out[n] = (os.path.isdir(p), 0 if os.path.isdir(p) else os.path.getsize(p))
    return out


def main():
    syms = symfile.load(SYMS)
    fails = []

    def check(cond, msg):
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            fails.append(msg)
        return cond

    print("gem4xe-dsio: a program's SIO frames to a FujiNet")
    emu = launch(tag="dsio", memsize="1088K",
                 extra_args=["--disk", G4DISK, "--adddevice", f"custom,path={NETSIO}"])
    b = emu.bridge
    try:
        if boot(b) is None:
            print("FAIL: the runner did not come up")
            return 1
        r = Runner(b, syms)
        g = Gdos(r, check)
        near = r.sc + BUF

        def dsio(cmd, aux, d, n, buf=near, dev=FUJI):
            ret, _ = g.call("Dsio", W(dev), W(cmd), W(aux - 0x10000 if aux > 0x7FFF else aux),
                            W(d), W(n), L(buf))
            return ret

        # -- the host slots ----------------------------------------------------
        r.stage(BUF, b"\xEE" * 256)
        ret = dsio(F_READ_HOSTS, 0, DS_READ, 256)
        if not check(ret == 0, f"Read host slots answered {ret}"
                     + (" -- is the NetSIO hub running?" if ret == EDRVNR else "")):
            return 1
        hosts = r.read(BUF, 256)
        names = [hosts[i * 32:(i + 1) * 32].split(b"\0")[0] for i in range(8)]
        check(names[0] == b"SD", f"Host 1 is {names[0]!r}, not 'SD'")

        far, _ = g.call("Malloc", L(512))
        check(far > 0xFFFF, f"Malloc(512) ${far:06X} is far")
        ret = dsio(F_READ_HOSTS, 0, DS_READ, 256, buf=far)
        sample = bytes(b.cmd(f"EVAL db(${far + i:06X})").get("value") for i in range(32))
        check(ret == 0 and sample == hosts[:32],
              f"Read host slots into far ${far:06X}: {ret}, {sample[:8]!r}")

        r.stage(BUF, b"\xEE" * 304)
        ret = dsio(F_READ_DEVS, 0, DS_READ, 304)
        devs = r.read(BUF, 304)
        hostbytes = [devs[i * 38] for i in range(8)]
        check(ret == 0 and hostbytes == [0xFF] * 8,
              f"Read device slots, 304 bytes: {ret}, the drives' hosts {hostbytes}")

        # -- a folder ----------------------------------------------------------
        check(dsio(F_MOUNT_HOST, 0, DS_NONE, 0) == 0, "Mount host 1")
        r.stage(BUF, f"/{FOLDER}/".encode().ljust(256, b"\0"))
        check(dsio(F_OPEN_DIR, 0, DS_WRITE, 256) == 0, f"Open directory /{FOLDER}/")
        got = {}
        for _ in range(64):
            r.stage(BUF, b"\xEE" * ENTRY_LEN)
            ret = dsio(F_READ_ENTRY, ENTRY_LEN | (EXTRA << 8), DS_READ, ENTRY_LEN)
            if not check(ret == 0, f"Read directory entry {len(got)}: {ret}"):
                break
            e = r.read(BUF, ENTRY_LEN)
            if e[:2] == b"\x7f\x7f":
                break
            name = e[13:].split(b"\0")[0].decode("latin-1")
            is_dir = bool(e[10])
            check(name.endswith("/") == is_dir, f"{name!r}: the slash and the folder flag agree")
            got[name.rstrip("/")] = (is_dir, 0 if is_dir else struct.unpack("<I", e[6:10])[0])
        check(dsio(F_CLOSE_DIR, 0, DS_NONE, 0) == 0, "Close directory")
        want = expected()
        check(got == want, f"/{FOLDER}/ listed {sorted(got.items())}, the SD folder has "
              f"{sorted(want.items())}")

        r.stage(BUF, b"/NOT-THERE/".ljust(256, b"\0"))
        # The FujiNet answers the first try with an error, the OS's SIO tries
        # the command once more, and that try's data frame is not taken:
        # the call ends in a timeout (seen 2026-11-27 over NetSIO, in the
        # FujiNet-PC's log).  So a failed open is ERROR or EDRVNR, and the
        # FujiNet must still answer after it: the browser asks again
        # before it says there is no FujiNet.
        ret = dsio(F_OPEN_DIR, 0, DS_WRITE, 256)
        check(ret in (ERROR, EDRVNR),
              f"Open directory on a folder that is not there: {ret}, want ERROR or EDRVNR")
        dsio(F_CLOSE_DIR, 0, DS_NONE, 0)
        check(dsio(F_READ_HOSTS, 0, DS_READ, 256) == 0,
              "the FujiNet still answers after the failed open")

        # -- the refusals ------------------------------------------------------
        check(dsio(0x53, 0, DS_READ, 4, dev=0x31) == EINVFN,
              "a disk drive (device $31) refused: EINVFN")
        check(dsio(F_READ_HOSTS, 0, DS_READ, 513) == EBADRQ, "513 bytes refused: EBADRQ")
        check(dsio(F_READ_HOSTS, 0, DS_READ, 0) == EBADRQ, "a read of nothing refused: EBADRQ")
        check(dsio(F_READ_HOSTS, 0, 3, 256) == EBADRQ, "direction 3 refused: EBADRQ")
    finally:
        emu.stop()
    print(f"gem4xe-dsio: {'PASS' if not fails else 'FAIL'} -- Dsio to the FujiNet, "
          f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
