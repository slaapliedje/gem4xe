#!/usr/bin/env python3
"""Launch AltirraSDL headless for the gem4xe target machine.

    from a8test.launcher import launch
    emu = launch(tag="p0")           # 800XL, VBXE FX1.26 @ $D640, Rapidus 65C816
    emu.bridge.frames(60)
    emu.stop()

Differences from the vbxetxtadv launcher this is derived from:
  * adds the Rapidus 65C816 accelerator (--adddevice rapidus)
  * memsize defaults to 1088K so PORTB banking is present for MEMAC coexistence tests
  * U1MB is off by default and pinned off in BASE_ARGS (see --noultimate1mb
    below); a gate that wants it passes --u1mbrom, which the patched
    emulator in tools/altirra/ understands (docs/phase14.md, and
    tests/emu/cf_boot.py for the machine that needs all of it).

Never opens a window.  Never uses `pkill -f`: the emulator is stopped by pid.

The host's joysticks are kept out of the machine.  AltirraSDL opens every
joystick-class device SDL can see and routes it to port 1 through its input
maps, and a keyboard or mouse with a stray HID "joystick" interface (a
Keychron Q6 Max reports a one-axis controller whose axis sits below its own
minimum, which SDL reads as full left) then holds a PORTA direction line low
for the whole run -- found when the CX80 gate counted every pulse backwards.
The ports are driven through the bridge, so launch() enumerates the host's
joystick devices from sysfs and hands SDL their ids as a blacklist.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

from a8test.bridge import Bridge, BridgeError, find_token  # noqa: E402

# The emulator is read from ALTIRRASDL when a machine is LAUNCHED, not when
# this module is imported.  It used to be read once at import, so a script
# that imported the launcher and then set ALTIRRASDL silently ran whatever
# AltirraSDL was on PATH -- and a probe of the patched build reported it
# lacking KEYRAW, the opposite of the truth.
def altirra():
    return os.environ.get("ALTIRRASDL", "AltirraSDL")


ALTIRRA = altirra()     # as found at import, for anything that names it
XLROM = os.environ.get("ATARIXL_ROM", "/opt/altirra/roms/ATARIXL.ROM")

# --noultimate1mb: the emulator saves its profile on exit, U1MB state
# included, so a run that switched it on (--u1mbrom) would leave it on for
# every run after.  Each run now gets a config directory of its own
# (private_config), so that particular leak is closed at the source, but
# the machine is still stated rather than inherited.  Pinned off here; an
# extra_args --u1mbrom comes later on the line and wins.  Only the patched
# emulator (tools/altirra/) knows the switch; the installed one logs it
# and goes on.
#
# --diskemu generic: the drive the gates run.  This said "fastestpossible"
# for thirteen phases, which is not one of the emulator's names for a mode
# (disk.cpp's enum table says "fastest") -- it was rejected with one line
# in the log and every gate ran the generic drive anyway.  Asking for
# "fastest" properly does not work either: the SpartaDOS disk then does not
# boot at all, where under "generic" it is up in 400 frames.  So the gates
# say what they have always actually run, and a 92 KB load costs its five
# thousand frames.
# The video standard is not here: launch() puts --pal or --ntsc in front of
# these by its `pal` argument.  Every gate ran PAL until the NTSC one
# (test-m32n), because the frame is what evnt_timer and the double-click
# window are measured in and a 20 ms tick assumed on a 16.7 ms machine is
# a fifth short (src/vdi/vdi.c vdi_vex_timv).
BASE_ARGS = ["--hardware", "800xl", "--kernel", "xl", "--nobasic",
             "--diskemu", "generic", "--siopatch", "--nofastboot",
             "--noultimate1mb"]
# The core the emulated VBXE models: 126 by default, the core most boards
# carry; GEM4XE_VBXE=127 runs the gates against FX 1.27 (Altirra 4.50
# test26 and later model it; an older build quietly gives 1.26).
VBXE_VERSION = os.environ.get("GEM4XE_VBXE", "126")
VBXE_DEVICE = f"vbxe,version={VBXE_VERSION},alt_page=false,shared_mem=false"
RAPIDUS_DEVICE = "rapidus"


class Emu:
    def __init__(self, proc, run_dir, bridge):
        self.proc = proc
        self.run_dir = run_dir
        self.bridge = bridge
        self.log = os.path.join(run_dir, "altirra.log")

    def log_tail(self, n=2000):
        try:
            return open(self.log, errors="ignore").read()[-n:]
        except OSError:
            return ""

    def stop(self):
        for fn in (lambda: self.bridge.cmd("QUIT"), self.bridge.close):
            try:
                fn()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        pidfile = os.path.join(self.run_dir, "pid")
        if os.path.exists(pidfile):
            os.remove(pidfile)


def host_joystick_ids():
    """VID/PID pairs of every input device on this host, in the form
    SDL_JOYSTICK_BLACKLIST_DEVICES wants ("0xVVVV/0xPPPP,...").  Every event
    device, not just the kernel's js* ones: SDL classifies evdev devices by its
    own heuristics (the Keychron interface above is a joystick to SDL and not
    to joydev), and the list only ever governs what SDL opens AS a joystick, so
    a keyboard's id on it costs nothing.  Read from sysfs, not configured:
    whatever is plugged in today is what SDL would open."""
    ids = set()
    for js in glob.glob("/sys/class/input/event*/device/id"):
        try:
            with open(os.path.join(js, "vendor")) as f:
                vid = int(f.read(), 16)
            with open(os.path.join(js, "product")) as f:
                pid = int(f.read(), 16)
        except (OSError, ValueError):
            continue
        ids.add(f"0x{vid:04x}/0x{pid:04x}")
    return ",".join(sorted(ids))


def verify_kernel(b):
    """The real XL OS must be loaded (AltirraOS differs at $E000)."""
    if not os.path.exists(XLROM):
        return None
    rom = open(XLROM, "rb").read()
    return b.memdump(0xE000, 32) == rom[0x2000:0x2020]


# The longest path a Unix socket can bind: sun_path is 108 bytes on Linux,
# its terminating NUL included.  AltirraSDL does not refuse a longer one --
# it comes up, never listens, and this used to wait `timeout` seconds and
# then blame a missing token.  A tree under a deep temporary directory is
# enough to cross it: the socket lives four levels below the checkout.
SUN_PATH_MAX = 107


def check_socket_path(sock):
    """Refuse a bridge socket path the kernel cannot bind, before anything
    is made or started."""
    n = len(os.fsencode(sock))
    if n > SUN_PATH_MAX:
        raise BridgeError(
            f"the bridge socket path is {n} bytes and a Unix socket takes at "
            f"most {SUN_PATH_MAX}: {sock} -- the emulator would start and "
            "never listen.  Run from a checkout at a shorter path.")


def check_patched(bridge, exe=None):
    """Refuse an emulator without the patches in tools/altirra/.

    The keyboard is not the reason.  Upstream PR #88 brought KEYRAW in the
    same change as two 65C816 native-mode CPU fixes, so a build that does
    not answer KEYRAW has the SEI-with-an-IRQ-pending storm that walks the
    stack through all of bank $00.  It is intermittent and worse under
    load, so a gate can pass on such a build -- which is exactly why a
    pass from one proves nothing (tools/altirra/README.md)."""
    exe = exe or altirra()
    if not bridge.has_keyraw():
        raise BridgeError(
            f"{exe} does not answer KEYRAW, so it is a build without "
            "upstream AltirraSDL PR #88 -- and #88 also carries the 65C816 "
            "native-mode CPU fixes (tools/altirra/README.md).  On this build "
            "an SEI with an IRQ pending re-enters the handler at every fetch "
            "and walks the stack through bank $00, intermittently, so no "
            "native-mode result from it can be trusted, a green one "
            "included.  Point ALTIRRASDL at a patched build: "
            "ALTIRRASDL=/path/to/patched/AltirraSDL")


def run_dir_for(tag):
    """Where launch(tag=...) will put this run's files.  Derived, not
    remembered, so a gate that needs to know before it launches -- m19 and
    m30 drop the emulator's working copy of their disk -- asks the same
    function launch() uses instead of rebuilding the path itself."""
    return os.path.join(ROOT, "build", "emu", f"{tag}-{os.getpid()}")


def config_dir_for(tag):
    """The emulator's configuration directory for that run.  It is the
    run's own (see private_config), not the user's ~/.config/altirra, and
    disk_state lives under it."""
    return os.path.join(run_dir_for(tag), "config", "altirra")


def private_config(run_dir):
    """A config directory of this run's own, seeded from the user's.

    The emulator SAVES its machine settings on exit -- CPU type, high
    banks, memory mode, U1MB -- so with a shared ~/.config/altirra each
    gate inherits whatever the last one left behind, and a switch that
    was never honoured can be covered for by a profile that remembers it.
    That is not hypothetical: an emulator build with no --cpu switch at
    all PASSED the plain-65C816 gate here, because an earlier run had
    persisted "CPU: Chip type = 2" and it was simply still there.

    Only settings.ini is copied.  The rest of the directory is a game
    library, thumbnails and disk state -- 85 MB of it, and nothing a
    headless gate reads.
    """
    cfg = os.path.join(run_dir, "config")
    os.makedirs(os.path.join(cfg, "altirra"), exist_ok=True)
    src = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                      os.path.expanduser("~/.config")),
                       "altirra", "settings.ini")
    if os.path.exists(src):
        with open(src, errors="ignore") as f:
            ini = f.read()
        # ...and the CPU is never inherited.  Every caller states the
        # machine it wants -- a Rapidus device, --cpu/--highbanks, or the
        # 6502 that is the default -- so a remembered chip type can only
        # ever disagree with the one that was asked for, silently.
        ini = re.sub(r'("CPU: Chip type"|"Memory: High banks") = -?\d+',
                     r"\1 = 0", ini)
        with open(os.path.join(cfg, "altirra", "settings.ini"), "w") as f:
            f.write(ini)
    return cfg


def launch(tag="run", extra_args=(), vbxe=True, rapidus=True, memsize="1088K",
           timeout=60, require_real_rom=True,
           require_patched=True, pal=True, cpu816=0):
    run_dir = run_dir_for(tag)
    sock = os.path.join(run_dir, "bridge.sock")
    check_socket_path(sock)             # before anything is made or started
    os.makedirs(run_dir, exist_ok=True)
    if os.path.exists(sock):
        os.remove(sock)
    env = dict(os.environ, SDL_VIDEODRIVER="offscreen", SDL_AUDIODRIVER="dummy", TMPDIR=run_dir)
    env["XDG_CONFIG_HOME"] = private_config(run_dir)
    blacklist = host_joystick_ids()
    if blacklist:
        env["SDL_JOYSTICK_BLACKLIST_DEVICES"] = blacklist
    exe = altirra()
    args = [exe, f"--bridge=unix:{sock}", "--pal" if pal else "--ntsc", *BASE_ARGS,
            "--memsize", memsize, "--cleardevices"]
    if vbxe:
        args += ["--adddevice", VBXE_DEVICE]
    if rapidus:
        args += ["--adddevice", RAPIDUS_DEVICE]
    elif cpu816:
        # A PLAIN 65C816, no accelerator: the machine an Antonia is, and
        # the one that proves nothing here depends on the Rapidus.  The
        # CPU and its high banks are the simulator's own settings, which
        # only this fork's front end can reach (--cpu, --highbanks).
        # cpu816 is the bank count; 15 is a megabyte above bank $00,
        # which is where gem4xe wants its far code anyway.
        args += ["--cpu", "65c816", "--highbanks", str(cpu816)]
    args += list(extra_args)

    logf = open(os.path.join(run_dir, "altirra.log"), "w")
    t0 = time.time()
    proc = subprocess.Popen(args, env=env, stdout=logf, stderr=subprocess.STDOUT, cwd=run_dir)
    with open(os.path.join(run_dir, "pid"), "w") as f:
        f.write(str(proc.pid))
    addr, tok = find_token(run_dir, timeout=timeout, newer_than=t0 - 1)
    if not addr:
        proc.kill()
        tail = open(os.path.join(run_dir, "altirra.log"), errors="ignore").read()[-1500:]
        raise BridgeError(f"no bridge token in {run_dir} after {timeout}s; log tail:\n{tail}")
    b = Bridge(addr, tok, connect_timeout=timeout)
    emu = Emu(proc, run_dir, b)
    if require_patched:
        try:
            check_patched(b, exe)
        except BridgeError:
            emu.stop()
            raise
    if cpu816 and not rapidus:
        # --cpu is THIS tree's patch, not upstream's, and an emulator that
        # does not know the switch logs it and carries on as a 6502 -- so
        # the caller would get a machine with no linear RAM and a gate
        # would report that as a finding about gem4xe.  Ask the CPU.
        mode = b.ok("REGS").get("mode")
        if mode != "65C816":
            emu.stop()
            raise BridgeError(
                f"asked for a plain 65C816 and got a {mode}: this build has no "
                "--cpu switch (tools/altirra/altirra-sdl-cpu-highbanks.patch)")
    if vbxe and not b.cmd("DEVICE_GET vbxe").get("ok"):
        b.ok(f"DEVICE_SET vbxe on version={VBXE_VERSION} base=d600")
    if verify_kernel(b) is False and require_real_rom:
        emu.stop()
        raise BridgeError("emulated $E000 does not match the real ATARIXL.ROM (AltirraOS in use?)")
    return emu


def cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--shot")
    ap.add_argument("--memsize", default="1088K")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-vbxe", action="store_true")
    ap.add_argument("--no-rapidus", action="store_true")
    ap.add_argument("verbs", nargs="*")
    a = ap.parse_args(argv)
    emu = launch(tag=a.tag, vbxe=not a.no_vbxe, rapidus=not a.no_rapidus, memsize=a.memsize)
    b = emu.bridge
    print("bridge:", b.addr, "run_dir:", emu.run_dir)
    print("devices:", b.cmd("DEVICE_LIST"))
    if a.boot:
        print("boot:", b.boot(a.boot))
    b.frames(a.frames)
    for v in a.verbs:
        print(v, "->", b.cmd(v))
    if a.shot:
        print("shot:", b.screenshot(a.shot))
    if a.keep:
        print(f"left running, pid {emu.proc.pid}; stop with: kill {emu.proc.pid}")
    else:
        emu.stop()
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
