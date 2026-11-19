"""src/sys6502/enter6502.s's 16-bit division, run on a 6502 model and held
to Python's arithmetic (docs/6502.md, speed 7).

The routines are assembled and linked with Calypsi's own tools into a
small image, its code loaded into the model below, and each one called as
the compiler calls it: the dividend in _Zp0-1, the divisor in _Zp10-11,
the quotient back in _Zp0-1 and the remainder in _Zp2-3.  The unsigned
one must keep Y, which the signed one carries its signs in across it.

The model has only the instructions these routines use; any other stops
the test, so a change that reaches for one says so.

Skipped when as6502 is not installed.
"""
import os
import random
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import weakref

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))
AS, LN = (os.path.join(CAL, "bin", x) for x in ("as6502", "ln6502"))

STUB = """
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .public _Zp, _Vsp, _Vfp, __program_start
              .extern b6_UDivMod16, b6_DivMod16
              .section registers,bss
_Zp:          .space  48
_Vsp:         .space  2
_Vfp:         .space  2
              .section code
__program_start:
              jsr     b6_UDivMod16
              jsr     b6_DivMod16
              rts
"""
SCM = """
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80)))
    (memory Low (address (#x2000 . #x3fff)) (type rom) (section code))))
"""
SENTINEL = 0xFFF0                       # where the call returns to


class Cpu:
    """A 6502, the instructions the routines use and no more."""

    def __init__(self, mem):
        self.m = mem
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.s = 0xFF
        self.pc = 0

    def nz(self, v):
        self.z = int(v == 0)
        self.n = v >> 7
        return v

    def push(self, v):
        self.m[0x100 + self.s] = v
        self.s = (self.s - 1) & 0xFF

    def pull(self):
        self.s = (self.s + 1) & 0xFF
        return self.m[0x100 + self.s]

    def call(self, addr, limit=20000):
        self.push((SENTINEL - 1) >> 8)
        self.push((SENTINEL - 1) & 0xFF)
        self.pc = addr
        steps = 0
        while self.pc != SENTINEL:
            self.step()
            steps += 1
            if steps > limit:
                raise AssertionError("runs away")
        return steps

    def sbc(self, v):
        r = self.a - v - (1 - self.c)
        self.c = int(r >= 0)
        self.a = self.nz(r & 0xFF)

    def step(self):
        m = self.m
        op = m[self.pc]
        b1 = m[(self.pc + 1) & 0xFFFF]
        pc = self.pc + 2

        def branch(cond):
            return (pc + (b1 - 256 if b1 & 0x80 else b1)) & 0xFFFF if cond else pc

        if op == 0xA5:   self.a = self.nz(m[b1])
        elif op == 0xA9: self.a = self.nz(b1)
        elif op == 0xA6: self.x = self.nz(m[b1])
        elif op == 0xA2: self.x = self.nz(b1)
        elif op == 0xA0: self.y = self.nz(b1)
        elif op == 0x85: m[b1] = self.a
        elif op == 0x86: m[b1] = self.x
        elif op == 0x06:
            v = m[b1] << 1
            self.c = v >> 8
            m[b1] = self.nz(v & 0xFF)
        elif op == 0x26:
            v = (m[b1] << 1) | self.c
            self.c = v >> 8
            m[b1] = self.nz(v & 0xFF)
        elif op == 0x2A:
            v = (self.a << 1) | self.c
            self.c = v >> 8
            self.a = self.nz(v & 0xFF)
            pc -= 1
        elif op == 0x4A:
            self.c = self.a & 1
            self.a = self.nz(self.a >> 1)
            pc -= 1
        elif op == 0xC5:
            r = self.a - m[b1]
            self.c = int(r >= 0)
            self.nz(r & 0xFF)
        elif op == 0xE5: self.sbc(m[b1])
        elif op == 0xE9: self.sbc(b1)
        elif op == 0xE6: m[b1] = self.nz((m[b1] + 1) & 0xFF)
        elif op == 0x49: self.a = self.nz(self.a ^ b1)
        elif op == 0xCA:
            self.x = self.nz((self.x - 1) & 0xFF)
            pc -= 1
        elif op == 0x98:
            self.a = self.nz(self.y)
            pc -= 1
        elif op == 0xA8:
            self.y = self.nz(self.a)
            pc -= 1
        elif op == 0x38:
            self.c = 1
            pc -= 1
        elif op == 0xB0: pc = branch(self.c)
        elif op == 0x90: pc = branch(not self.c)
        elif op == 0xD0: pc = branch(not self.z)
        elif op == 0xF0: pc = branch(self.z)
        elif op == 0x10: pc = branch(not self.n)
        elif op == 0x20:
            ret = self.pc + 2
            self.push(ret >> 8)
            self.push(ret & 0xFF)
            pc = b1 | (m[(self.pc + 2) & 0xFFFF] << 8)
        elif op == 0x60:
            lo = self.pull()
            pc = ((self.pull() << 8) | lo) + 1
        else:
            raise AssertionError("opcode $%02X at $%04X is not in the model" % (op, self.pc))
        self.pc = pc & 0xFFFF


def load(elf):
    d = open(elf, "rb").read()
    mem = bytearray(0x10000)
    phoff, = struct.unpack_from("<I", d, 28)
    phentsize, phnum = struct.unpack_from("<HH", d, 42)
    for i in range(phnum):
        t, off, va, pa, fs, ms, fl, al = struct.unpack_from("<8I", d, phoff + i * phentsize)
        if t == 1 and fs and va < 0x10000:
            mem[va:va + fs] = d[off:off + fs]
    return mem


@unittest.skipUnless(os.path.exists(AS), "as6502 not installed")
class Div6502(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp(prefix="div6502-")
        weakref.finalize(cls, shutil.rmtree, d, True)
        for name, text in (("t.s", STUB), ("t.scm", SCM)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        enter = os.path.join(ROOT, "src", "sys6502", "enter6502.s")
        for cmd in ([AS, "--core", "6502", "t.s", "-o", "t.o"],
                    [AS, "--core", "6502", enter, "-o", "e.o"],
                    [LN, "t.scm", "t.o", "e.o", "-o", "t.elf", "--no-tree-shaking",
                     "--list-file", "t.map"]):
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
            if r.returncode:
                raise AssertionError(" ".join(cmd) + "\n" + r.stdout + r.stderr)
        text = open(os.path.join(d, "t.map")).read()
        cls.sym = {m.group(1): int(m.group(2), 16)
                   for m in re.finditer(r"^\s+(\w+) = ([0-9a-f]{4})\s*$", text, re.M)}
        cls.img = load(os.path.join(d, "t.elf"))
        cls.zp = cls.sym["_Zp"]

    def run_div(self, name, a, b, y=0x5A):
        cpu = Cpu(bytearray(self.img))
        z = self.zp
        cpu.m[z], cpu.m[z + 1] = a & 0xFF, (a >> 8) & 0xFF
        cpu.m[z + 10], cpu.m[z + 11] = b & 0xFF, (b >> 8) & 0xFF
        cpu.y = y
        steps = cpu.call(self.sym[name])
        q = cpu.m[z] | (cpu.m[z + 1] << 8)
        r = cpu.m[z + 2] | (cpu.m[z + 3] << 8)
        return q, r, cpu.y, steps

    VALUES = sorted(set([0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 15, 16, 17, 100, 127, 128,
                         129, 191, 200, 254, 255, 256, 257, 300, 319, 320, 511,
                         512, 1000, 4095, 0x1234, 0x7FFE, 0x7FFF, 0x8000, 0x8001,
                         0xC000, 0xFFFE, 0xFFFF]
                        + random.Random(6502).sample(range(0x10000), 60)))

    def test_unsigned(self):
        bad = []
        for a in self.VALUES:
            for b in self.VALUES:
                q, r, y, _ = self.run_div("b6_UDivMod16", a, b)
                want = (0xFFFF, a) if b == 0 else (a // b, a % b)
                if (q, r) != want or y != 0x5A:
                    bad.append((a, b, q, r, y, want))
        self.assertEqual(bad[:5], [], "%d of %d wrong" % (len(bad), len(self.VALUES) ** 2))

    def test_signed(self):
        bad = []
        for ua in self.VALUES:
            for ub in self.VALUES:
                a = ua - 0x10000 if ua & 0x8000 else ua
                b = ub - 0x10000 if ub & 0x8000 else ub
                if b == 0 or (a == -0x8000 and b == -1):
                    continue                    # undefined in C
                q, r, _, _ = self.run_div("b6_DivMod16", ua, ub)
                wq = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                wr = a - wq * b
                if (q, r) != (wq & 0xFFFF, wr & 0xFFFF):
                    bad.append((a, b, q, r, wq, wr))
        self.assertEqual(bad[:5], [], "%d wrong" % len(bad))

    def test_byte_divisors_are_short(self):
        """the fast paths are taken: a byte by a byte in under half the
        long way's instructions, two bytes by a byte in fewer"""
        _, _, _, small = self.run_div("b6_UDivMod16", 200, 6)
        _, _, _, mid = self.run_div("b6_UDivMod16", 3000, 6)
        _, _, _, long_ = self.run_div("b6_UDivMod16", 3000, 600)
        self.assertLess(small * 2, long_)
        self.assertLess(mid, long_)


if __name__ == "__main__":
    unittest.main()
