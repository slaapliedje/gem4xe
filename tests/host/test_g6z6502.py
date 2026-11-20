"""src/sys6502/g6z6502.s, the 6502's G4Z unpacker, on tests/host/m6502.py
(docs/6502.md, "Disk").

The 6502 build's own bank images -- build/a6.elf's and build/desk6.elf's,
when they are built -- are packed by tools/mkxex.py's packer, the one the
65816's loader is held to, and unpacked by the assembly on the model:
every byte must come back, and the cycles a byte are reported (and held
under a ceiling, so a change that slows it says so).  One image is cut
into small chunks too, which is how a loader reads it, so the offset
carried from one chunk to the next is exercised; and a stream that asks
for more than its count must stop at the count.

b6_unz, the load-time hook, must unpack its stage and give the DOS its
_Zp bytes back, and stop the load on a bad stream.  And build/a6.xex,
written by tools/bsp6502/mkxex6502.py --pack, is LOADED here as a DOS
would load it -- each segment in, each INITAD called -- with a6.elf's own
b6_unz run on the model and the bank switch done in Python: every bank
must come out as the ELF has it.

Skipped when as6502 is not installed.
"""
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import weakref

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import m6502                            # noqa: E402
import mkxex                            # noqa: E402

CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))
AS, LN = (os.path.join(CAL, "bin", x) for x in ("as6502", "ln6502"))

STUB = """
              .rtmodel version, "1"
              .rtmodel cpu, "*"
              .public _Zp, b6_stop, stopped, fmap, unmap, mapped
              .section registers,bss
_Zp:          .space  48
              .section b6keep,noinit
stopped:      .space  1
mapped:       .space  1               ; fmap's bank byte, 0 after unmap
              .section code
b6_stop:      lda     #0x5a           ; the load stopped
              sta     stopped
              rts
fmap:         lda     zp:_Zp+2,x      ; far6502.s's, for one piece: FW
              sta     mapped
              lda     zp:_Zp+0,x
              sta     zp:_Zp+12
              lda     zp:_Zp+1,x
              and     #0x3f
              ora     #0x40
              sta     zp:_Zp+13
              rts
unmap:        pha                     ; keeps A
              lda     #0
              sta     mapped
              pla
              rts
"""
SCM = """
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80)))
    (memory Low (address (#x2000 . #x3eff)) (type rom) (section code b6init cdata))
    (memory LowRam (address (#x3f00 . #x3fff)) (type ram) (section b6keep))))
"""
SRC, DST = 0x8000, 0x4000               # the packed stream; the window
CEILING = 60                            # cycles a byte, at most (56.5 now)


def bank_images(elf):
    """The 16 KB images an ELF scatters to $10000 + (n - 1) * $4000."""
    path = os.path.join(ROOT, "build", elf)
    if not os.path.exists(path):
        return []
    d = open(path, "rb").read()
    phoff, = struct.unpack_from("<I", d, 28)
    phentsize, phnum = struct.unpack_from("<HH", d, 42)
    banks = {}
    for i in range(phnum):
        t, off, va, pa, fs, ms, fl, al = struct.unpack_from("<8I", d, phoff + i * phentsize)
        for a in (va, pa):
            if t == 1 and fs and a >= 0x10000:
                n = (a - 0x10000) >> 14
                img = banks.setdefault(n, bytearray(0x4000))
                o = a & 0x3FFF
                img[o:o + fs] = d[off:off + fs][:0x4000 - o]
                break
    return [bytes(banks[k]) for k in sorted(banks)]


@unittest.skipUnless(os.path.exists(AS), "as6502 not installed")
class G6z6502(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp(prefix="g6z6502-")
        weakref.finalize(cls, shutil.rmtree, d, True)
        for name, text in (("t.s", STUB), ("t.scm", SCM)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        src = os.path.join(ROOT, "src", "sys6502", "g6z6502.s")
        for cmd in ([AS, "--core", "6502", "t.s", "-o", "t.o"],
                    [AS, "--core", "6502", src, "-o", "g.o"],
                    [LN, "t.scm", "t.o", "g.o", "-o", "t.elf", "--no-tree-shaking",
                     "--list-file", "t.map"]):
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
            if r.returncode:
                raise AssertionError(" ".join(cmd) + "\n" + r.stdout + r.stderr)
        text = open(os.path.join(d, "t.map")).read()
        sym = {m.group(1): int(m.group(2), 16)
               for m in re.finditer(r"^\s+(\w+) = ([0-9a-f]{4})\s*$", text, re.M)}
        cls.entry, cls.zp = sym["g6z_unpack"], sym["_Zp"]
        cls.unz, cls.stopped = sym["b6_unz"], sym["stopped"]
        cls.far, cls.mapped = sym["g6z_far"], sym["mapped"]
        e = open(os.path.join(d, "t.elf"), "rb").read()
        img = bytearray(0x10000)
        phoff, = struct.unpack_from("<I", e, 28)
        phentsize, phnum = struct.unpack_from("<HH", e, 42)
        for i in range(phnum):
            t, off, va, pa, fs, ms, fl, al = struct.unpack_from("<8I", e, phoff + i * phentsize)
            if t == 1 and fs and va < 0x10000:
                img[va:va + fs] = e[off:off + fs]
        cls.img = bytes(img)

    def unpack(self, chunks, total, dst=DST):
        """Each (count, packed) chunk in turn, as a loader would; returns
        the output and the cycles."""
        cpu = m6502.Cpu(bytearray(self.img))
        z, last, at, cyc = self.zp, 0, dst, 0
        for count, packed in chunks:
            cpu.m[SRC:SRC + len(packed)] = packed
            for k, v in enumerate((SRC, at, count, last)):
                cpu.m[z + 2 * k] = v & 0xFF
                cpu.m[z + 2 * k + 1] = v >> 8
            cyc += cpu.call(self.entry)
            self.assertEqual(cpu.a, 0, "a chunk asked past its count")
            src_end = cpu.m[z] | cpu.m[z + 1] << 8
            self.assertEqual(src_end, SRC + len(packed), "the chunk not used to its end")
            at = cpu.m[z + 2] | cpu.m[z + 3] << 8
            last = cpu.m[z + 6] | cpu.m[z + 7] << 8
        return bytes(cpu.m[dst:dst + total]), cyc

    def images(self):
        imgs = bank_images("a6.elf") + bank_images("desk6.elf")
        if not imgs:                    # not built: something like code
            r = random.Random(65)
            words = [bytes(r.randrange(256) for _ in range(r.randrange(2, 9)))
                     for _ in range(300)]
            b = bytearray()
            while len(b) < 0x4000:
                b += r.choice(words) if r.random() < 0.8 else bytes([r.randrange(256)])
            imgs = [bytes(b[:0x4000])]
        return imgs

    def test_bank_images(self):
        total_in = total_out = total_cyc = 0
        for k, data in enumerate(self.images()):
            chunks = mkxex.chunks(data, 0x4000)
            out, cyc = self.unpack(chunks, len(data))
            self.assertEqual(out, data, "image %d" % k)
            total_in += sum(len(p) for _, p in chunks)
            total_out += len(data)
            total_cyc += cyc
        per = total_cyc / total_out
        print("\ng6z: %d images, %d KB packed to %d KB (%.0f%%), %.1f cycles a byte"
              % (len(self.images()), total_out >> 10, total_in >> 10,
                 100 * total_in / total_out, per), file=sys.stderr)
        self.assertLess(per, CEILING)

    def test_small_chunks_carry_the_offset(self):
        data = self.images()[0]
        chunks = mkxex.chunks(data, 1024)
        self.assertGreater(len(chunks), 3)
        out, _ = self.unpack(chunks, len(data))
        self.assertEqual(out, data)

    def test_runs_and_long_literals(self):
        r = random.Random(6502)
        data = (bytes(700) + bytes(r.randrange(256) for _ in range(900)) + b"AB" * 300
                + bytes(r.randrange(256) for _ in range(300)))
        chunks = mkxex.chunks(data, 0x4000)
        out, _ = self.unpack(chunks, len(data))
        self.assertEqual(out, data)

    def test_stops_at_its_count(self):
        data = bytes(range(256)) * 8
        (count, packed), = mkxex.chunks(data, 0x4000)
        cpu = m6502.Cpu(bytearray(self.img))
        cpu.m[DST:DST + 0x1000] = b"\xEE" * 0x1000
        cpu.m[SRC:SRC + len(packed)] = packed
        z = self.zp
        for k, v in enumerate((SRC, DST, count - 100, 0)):
            cpu.m[z + 2 * k] = v & 0xFF
            cpu.m[z + 2 * k + 1] = v >> 8
        cpu.call(self.entry)
        self.assertEqual(cpu.a, 1)
        self.assertTrue(all(b == 0xEE for b in cpu.m[DST + count - 100:DST + 0x1000]),
                        "wrote past its count")

    def stage(self, cpu, dst, count, packed):
        cpu.m[0x8000:0x8004] = bytes([dst & 0xFF, dst >> 8, count & 0xFF, count >> 8])
        cpu.m[0x8004:0x8004 + len(packed)] = packed

    def test_unz_unpacks_and_keeps_the_zero_page(self):
        data = self.images()[0][:5000]
        (count, packed), = mkxex.chunks(data, 0x1E00)
        cpu = m6502.Cpu(bytearray(self.img))
        zp = bytes(range(0x30, 0x30 + 15))
        cpu.m[self.zp:self.zp + 15] = zp
        self.stage(cpu, 0x4123, count, packed)
        cpu.call(self.unz)
        self.assertEqual(bytes(cpu.m[0x4123:0x4123 + count]), data)
        self.assertEqual(bytes(cpu.m[self.zp:self.zp + 15]), zp, "the DOS's _Zp bytes")
        self.assertEqual(cpu.m[self.stopped], 0)

    def test_unz_stops_a_bad_stream(self):
        data = bytes(range(256)) * 8
        (count, packed), = mkxex.chunks(data, 0x1E00)
        cpu = m6502.Cpu(bytearray(self.img))
        self.stage(cpu, 0x4000, count - 1, packed)
        cpu.call(self.unz)
        self.assertEqual(cpu.m[self.stopped], 0x5A, "a stream past its count went on")

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "build", "a6.xex")), "a6.xex not built")
    def test_a6_xex_loads(self):
        """build/a6.xex through a DOS's loader, on the model"""
        elf = os.path.join(ROOT, "build", "a6.elf")
        text = open(os.path.join(ROOT, "build", "a6.map")).read()
        sym = lambda n: int(re.search(r"^\s+%s = ([0-9a-f]+)\s*$" % n, text, re.M).group(1), 16)
        unz, sel, main, nxt = sym("b6_unz"), sym("b6_sel"), sym("b6_main"), sym("b6_next")
        xex = open(os.path.join(ROOT, "build", "a6.xex"), "rb").read()
        cpu = m6502.Cpu(bytearray(0x10000))
        banks, cur, i, calls = {}, 0, 2, 0
        while i < len(xex):
            if xex[i:i + 2] == b"\xff\xff":
                i += 2
            a, e = struct.unpack_from("<HH", xex, i)
            cpu.m[a:e + 1] = xex[i + 4:i + 5 + e - a]
            i += 5 + e - a
            if a <= 0x2E2 <= e:
                init = cpu.m[0x2E2] | cpu.m[0x2E3] << 8
                cpu.m[0x2E2] = cpu.m[0x2E3] = 0
                if init == unz:
                    cpu.call(unz)
                    calls += 1
                elif init in (sel, main):
                    if cur:
                        banks[cur] = bytes(cpu.m[0x4000:0x8000])
                    cur = cpu.m[nxt] if init == sel else 0
                    cpu.m[0x4000:0x8000] = banks.get(cur, bytes(0x4000))
        if not calls:
            self.skipTest("a6.xex is not packed")
        want = bank_images("a6.elf")
        self.assertEqual(sorted(banks), list(range(1, len(want) + 1)))
        for k, img in enumerate(want, 1):
            self.assertEqual(banks[k], img, "bank %d" % k)
        self.assertLess(len(xex), sum(len(w.rstrip(b"\0")) for w in want) * 0.6)

    def test_g6a_banks_unpack_in_place(self):
        """each packed bank of a .G6A, read into its top, unpacked by
        g6z_far from its start: what the ELF has, and the bank unmapped"""
        done = 0
        for name in ("desk6", "cpanel6", "p6mprog"):
            path = os.path.join(ROOT, "build", name + ".g6a")
            if not os.path.exists(path):
                continue
            g = open(path, "rb").read()
            n, np, fl = g[3], g[4], g[5]
            if not fl & 1:
                continue
            at = 6 + 4 * np
            lens = struct.unpack_from("<%dH" % n, g, at)
            outs = struct.unpack_from("<%dH" % n, g, at + 2 * n)
            o = at + 4 * n + sum(struct.unpack_from("<H", g, 6 + 4 * k + 2)[0]
                                 for k in range(np))
            want = bank_images(name + ".elf")
            for k in range(n):
                data = g[o:o + lens[k]]
                o += lens[k]
                if lens[k] == outs[k]:
                    continue
                cpu = m6502.Cpu(bytearray(self.img))
                cpu.m[0x8000 - lens[k]:0x8000] = data
                z = self.zp
                cpu.m[z:z + 8] = struct.pack("<IHH", 0x10000 + k * 0x4000,
                                             lens[k], outs[k])
                cpu.call(self.far)
                self.assertEqual(cpu.a, 0, "%s bank %d: a bad stream" % (name, k + 1))
                self.assertEqual(cpu.m[self.mapped], 0, "the bank left mapped")
                self.assertEqual(bytes(cpu.m[0x4000:0x4000 + outs[k]]),
                                 want[k][:outs[k]], "%s bank %d" % (name, k + 1))
                done += 1
            self.assertEqual(o, len(g), name + ": the file not read to its end")
        if not done:
            self.skipTest("no packed .G6A built")

    def test_g6a_pack_refuses_what_overruns(self):
        """a bank that would write over its packed bytes before reading
        them is stored as it is"""
        sys.path.insert(0, os.path.join(ROOT, "tools", "bsp6502"))
        import mkxex6502
        r = random.Random(6)
        noise = bytes(r.randrange(256) for _ in range(8384))
        self.assertIsNone(mkxex6502.pack_bank(bytes(8000) + noise))
        p = mkxex6502.pack_bank(noise + bytes(8000))
        self.assertIsNotNone(p)
        self.assertGreaterEqual(p[1], 0)


if __name__ == "__main__":
    unittest.main()
