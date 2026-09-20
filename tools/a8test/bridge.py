#!/usr/bin/env python3
"""AltirraBridge client.

`AltirraSDL --bridge[=tcp:HOST:PORT|unix:/path]` embeds a TCP/unix debug server speaking
newline-delimited commands with one-line JSON replies.  On start it writes a 0600 token file
`<TMPDIR>/altirra-bridge-<pid>.token` holding the address and a session token; the first command
must be `HELLO <token>`.

Addresses inside verbs MUST be `$`- or `0x`-prefixed — bare numbers parse as DECIMAL.

Library:  b = Bridge(addr, token); b.cmd("REGS"); b.frames(60); b.memdump(0x9C00, 1024)
CLI:      bridge.py --token-dir DIR cmd "VERB ARGS" ...
(derived from the a8-u4r project's altirra-bridge skill)
"""
import base64
import glob
import json
import os
import socket
import sys
import time


class BridgeError(RuntimeError):
    pass


def read_token_file(path):
    lines = open(path, errors="ignore").read(512).splitlines()
    if len(lines) < 2:
        raise BridgeError(f"bad token file {path}")
    return lines[0].strip(), lines[1].strip()


def find_token(token_dir, timeout=30, newer_than=0.0):
    """Newest `*bridge*` token file in token_dir that is newer than `newer_than` (epoch)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        cands = [f for f in glob.glob(os.path.join(token_dir, "*bridge*")) if os.path.isfile(f)]
        cands.sort(key=os.path.getmtime, reverse=True)
        for f in cands:
            if os.path.getmtime(f) < newer_than:
                continue
            try:
                addr, tok = read_token_file(f)
            except (OSError, BridgeError):
                continue
            if addr.startswith(("tcp:", "unix:")):
                return addr, tok
        time.sleep(0.3)
    return None, None


class Bridge:
    def __init__(self, addr, token, connect_timeout=60):
        self.addr = addr
        last = None
        t0 = time.time()
        while time.time() - t0 < connect_timeout:
            try:
                if addr.startswith("unix:"):
                    self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.s.settimeout(600)
                    self.s.connect(addr[5:])
                else:
                    host, port = addr[4:].rsplit(":", 1)
                    self.s = socket.create_connection((host, int(port)), timeout=600)
                break
            except OSError as e:  # server answers once Init completes
                last = e
                time.sleep(0.5)
        else:
            raise BridgeError(f"bridge connect failed ({addr}): {last}")
        self.f = self.s.makefile("rwb")
        self._keyraw = None             # has_keyraw(), asked when first needed
        r = self.cmd(f"HELLO {token}")
        if not r.get("ok"):
            raise BridgeError(f"HELLO rejected: {r}")

    # -- raw protocol ---------------------------------------------------------------------------
    def cmd(self, line):
        self.f.write((line + "\n").encode())
        self.f.flush()
        resp = self.f.readline().decode().strip()
        if not resp:
            raise BridgeError(f"connection closed during: {line}")
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            return {"ok": False, "raw": resp}

    def ok(self, line):
        r = self.cmd(line)
        if not r.get("ok"):
            raise BridgeError(f"{line} -> {r}")
        return r

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

    # -- helpers --------------------------------------------------------------------------------
    def frames(self, n):
        """Run exactly n frames (chunked so each call returns promptly)."""
        r = None
        while n > 0:
            step = min(n, 250)
            r = self.ok(f"FRAME {step}")
            n -= step
        return r

    def memdump(self, addr, length):
        """`length` bytes from `addr`.  Above $FFFF the address is the
        65C816's 24-bit linear space, bank in the high byte, read through
        the emulator's banked debug path -- an accelerator's fast RAM
        included; a build without tools/altirra/altirra-sdl-bridge-
        memory-24bit.patch refuses it as a bad address.  The chunking per
        64K is for the 16-bit path's rule; the 24-bit one would not need it."""
        out = bytearray()
        while length > 0:
            chunk = min(length, 0x10000 - (addr & 0xFFFF))
            r = self.ok(f"MEMDUMP ${addr:04X} {chunk}")
            out += base64.b64decode(r["data"])
            addr += chunk
            length -= chunk
        return bytes(out)

    def memload(self, addr, data):
        return self.ok(f"MEMLOAD ${addr:04X} {base64.b64encode(bytes(data)).decode()}")

    def peek(self, addr):
        return self.memdump(addr, 1)[0]

    def peek16(self, addr):
        d = self.memdump(addr, 2)
        return d[0] | (d[1] << 8)

    def peek24(self, addr):
        """A Calypsi __far pointer as it lies in memory: the 16-bit offset
        then the BANK IN BYTE 2.  A near pointer read this way answers
        itself, because the byte above it is the bank 0 it means -- so this
        is the safe read for anything that MIGHT be far, which since the
        desktop moved to the large data model is most of what a gate
        follows (src/aes/aes.h's OBJECT FAR *)."""
        d = self.memdump(addr, 3)
        return d[0] | (d[1] << 8) | (d[2] << 16)

    def poke(self, addr, value):
        return self.ok(f"POKE ${addr:04X} ${value & 0xFF:02X}")

    def has_keyraw(self):
        """Whether this emulator carries the patches in tools/altirra/ -- and
        it is the CPU, not the keyboard, that makes the answer matter.
        Upstream PR #88 brought KEYRAW, CONFIG u1mb and the KEY modifier
        fix in the same change as the two 65C816 native-mode CPU fixes, so
        a build that does not know KEYRAW has the SEI/IRQ storm that walks
        the stack through bank $00, and launch() refuses it
        (require_patched=False to override).  `KEYRAW all up` releases
        nothing that is not held and is refused as an unknown verb by a
        build without it.  Asked once, remembered."""
        if self._keyraw is None:
            self._keyraw = bool(self.cmd("KEYRAW all up").get("ok"))
        return self._keyraw

    def key(self, name, shift=False, ctrl=False):
        """Press a key for one frame, with modifiers in the keyboard's sense.

        POKEY builds KBCODE as scan / shift = bit 6 / control = bit 7, and
        the XL OS's key table (KEYDEF, $79) is laid out the same way.  The
        stock AltirraSDL bridge has KEY's two words crossed: its `shift`
        sets bit 7 and `ctrl` bit 6 -- measured by injecting KEY A: `shift`
        yielded ctrl-A ($01) and `ctrl` a capital A.  The patched build
        (tools/altirra/) fixes it, so the words are crossed here only for a
        build without the patch, and a caller's `shift=True` means what
        SHIFT on the keyboard means either way.  The reply's kbcode is
        checked against that, so a build the probe misjudged fails loudly.

        The key reaches the program only if POKEY's keyboard IRQ is enabled
        (IRQEN bit 6) and acknowledged after every key; otherwise the bridge
        queues it forever.  The key is held for a single frame.
        """
        want = (0x40 if shift else 0) | (0x80 if ctrl else 0)
        s, c = (shift, ctrl) if self.has_keyraw() else (ctrl, shift)
        r = self.ok(f"KEY {name}" + (" shift" if s else "") + (" ctrl" if c else ""))
        code = int(r.get("kbcode", "$00")[1:], 16)
        if (code & want) != want:
            raise BridgeError(f"KEY {name}: the bridge pushed ${code:02X}, "
                              f"not the modifier bits ${want:02X} asked for")
        return r

    def key_raw(self, name, down=True, shift=False, ctrl=False):
        """Hold a key down in POKEY's matrix, or release it -- the way the
        keyboard does, rather than through the cooked queue `key` uses.

        The difference is who gets to see it.  KEY waits for the keyboard IRQ
        to be enabled and acknowledged, so a program that polls SKSTAT and
        KBCODE with the IRQ off (a firmware setup screen -- the U1MB BIOS)
        never gets one.  KEYRAW drives the scan emulation instead: KBCODE,
        SKSTAT bit 2 and the IRQ line all follow, and the key stays down
        until released.  The modifiers are the real SHIFT and CONTROL keys,
        not KBCODE bits, so nothing is crossed over here.  Needs the KEYRAW
        verb (the patched AltirraSDL in tools/altirra/).
        """
        words = ["down" if down else "up"]
        if shift: words.append("shift")
        if ctrl:  words.append("ctrl")
        return self.ok(f"KEYRAW {name} " + " ".join(words))

    def key_tap(self, name, hold=6, gap=6, shift=False, ctrl=False):
        """A raw press: hold `name` for `hold` frames, release, then run
        `gap` frames so a polling program sees the key go away before the
        next one.  Six frames is a tenth of a second, a human tap."""
        self.key_raw(name, True, shift, ctrl)
        self.frames(hold)
        self.key_raw(name, False, shift, ctrl)
        self.frames(gap)

    def joy(self, port, direction, fire=False):
        """Set joystick `port` (0..3) to one of the nine stick states --
        "centre", "up", "down", "left", "right", "upleft", "upright",
        "downleft", "downright" -- with the trigger pressed or not.  The
        state HOLDS until the next call; nothing runs a frame here.

        The verb writes the PIA's input lines directly (bridge_commands_write
        .cpp: RefreshJoystickInput), so PORTA's nibble reads the state
        active-low: up clears bit 0, down bit 1, left bit 2, right bit 3.
        That is a joystick's four switches and nothing else -- the nine
        states cannot make an arbitrary nibble, which limits what a
        quadrature device can be driven through here (tests/emu/m10_irq.py).
        """
        return self.ok(f"JOY {port} {direction}" + (" fire" if fire else ""))

    def screenshot(self, path):
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return self.ok(f"SCREENSHOT path={path}")

    def rawscreen(self, path):
        path = os.path.abspath(path)
        return self.ok(f"RAWSCREEN path={path}")

    def state_save(self, name):
        return self.ok(f"STATE_SAVE {name}")

    def state_load(self, name):
        return self.ok(f"STATE_LOAD {name}")

    def boot(self, path):
        return self.ok(f"BOOT {os.path.abspath(path)}")

    def mount(self, drive, path):
        return self.ok(f"MOUNT {drive} {os.path.abspath(path)}")


def cli(argv):
    import argparse
    ap = argparse.ArgumentParser(description="attach to a running AltirraSDL bridge and run verbs")
    ap.add_argument("--token-dir", default=os.environ.get("A8_TOKEN_DIR", "/tmp"))
    ap.add_argument("--addr")
    ap.add_argument("--token")
    ap.add_argument("verbs", nargs="+")
    a = ap.parse_args(argv)
    addr, tok = (a.addr, a.token) if a.addr else find_token(a.token_dir, timeout=5)
    if not addr:
        print(f"no bridge token found in {a.token_dir}", file=sys.stderr)
        return 1
    b = Bridge(addr, tok)
    for v in a.verbs:
        print(v, "->", json.dumps(b.cmd(v)))
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
