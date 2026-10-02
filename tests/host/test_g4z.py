"""src/sys/g4z.s in the vendor's simulator, against tools/mkxex.py.

Each sample is squeezed here, as tools/mkg4a.py squeezes a program (one
G4Z stream for the whole file), and written into a C harness as a far
constant.  The harness copies the packed bytes to an address that
straddles a bank boundary (in a scratch section: the simulator has memory
only where the ELF has a segment), unpacks them to another that straddles one
too, and folds what came out into a checksum, which must be the sample's.
It also unpacks with a count short of the stream's: g4z_unpack must answer
1 and leave the byte after the count as it was.

The samples: the desktop as it is built (a real program file), and a made
one with long runs and matches reaching back nearly the whole 65,535 an
offset allows.
"""
import os
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
G4Z_S = os.path.join(ROOT, "src", "sys", "g4z.s")

sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import mkxex                               # noqa: E402
import check as ccbug                      # noqa: E402  (the simulator driver)

M = 0xffffffff
SRC = 0x02ff80          # the packed bytes, across $02/$03
DST = 0x03f000          # what they unpack to, across $03/$04 (and $04/$05)
SHORT = 1000            # the cut-short unpack's count

# The vendor's example link, with far constants and a scratch over both
# ranges.  The simulator has memory only where the ELF has a segment, so
# the scratch is a section -- zeroed, by tests/host/g4z_scratch.s -- and
# the near memory is moved out of its way.
LINK = """
(define memories
  '((memory flash (address (#x10000 . #x1ffff))
            (section farcode idata cdata switch))
    (memory LoRAM (address (#x4000 . #xefff))
            (section stack data zdata heap))
    (memory NearRAM (address (#x200000 . #x20ffff))
            (section znear))
    (memory DirectPage (address (#xf000 . #xf0ff))
            (section (registers ztiny)))
    (memory Vector (address (#xff00 . #xffff))
            (section (reset #xfffc)))
    (memory LoCode (address (#xf100 . #xfeff))
            (section code cdata data_init_table))
    (memory Scratch (address (#x02f000 . #x05ffff))
            (section gzscratch))
    (memory FarConst (address (#x080000 . #x0bffff))
            (section cfar))
    (block stack (size #x1000))
    (block heap (size #x1000))
    (base-address _DirectPageStart DirectPage 0)
    (base-address _NearBaseAddress NearRAM    0)
    ))
"""
SCRATCH = """
              .section gzscratch, bss
              .public gz_scratch
gz_scratch:   .space  0x31000
"""


def made():
    """Runs, near and far matches, and noise: 80 KB."""
    r = random.Random(4)
    words = [bytes(r.randrange(256) for _ in range(r.randrange(3, 40)))
             for _ in range(60)]
    out = bytearray()
    while len(out) < 80000:
        k = r.randrange(10)
        if k == 0:
            out += bytes([r.randrange(256)]) * r.randrange(1, 6000)
        elif k == 1 and len(out) > 70000:
            back = r.randrange(60000, 65535)
            n = r.randrange(5, 300)
            for _ in range(n):
                out.append(out[-back])
        elif k < 4:
            out += bytes(r.randrange(256) for _ in range(r.randrange(1, 200)))
        else:
            out += r.choice(words)
    return bytes(out[:80000])


def fold(data):
    """Fletcher's two sums, sixteen bits each: a byte's position counts, so
    a periodic sample does not cancel itself out (a rotate-and-xor did)."""
    a = c = 0
    for b in data:
        a = (a + b) & 0xffff
        c = (c + a) & 0xffff
    return c << 16 | a


def squeeze(data):
    res = mkxex.chunks(data, 1 << 30, 1 << 30)
    assert len(res) == 1 and res[0][0] == len(data)
    return res[0][1]


HARNESS = r"""
#include <stdint.h>
extern int16_t g4z_unpack(uint32_t src, uint32_t dst, uint32_t count);
extern const uint8_t __far packed[%(plen)d];

uint32_t gz_sum;
int16_t gz_rc, gz_short_rc;
uint16_t gz_after;

static uint8_t rd(uint32_t a) { return *(volatile uint8_t __far *)a; }
static void wr(uint32_t a, uint8_t v) { *(volatile uint8_t __far *)a = v; }

int main(void)
{
    uint32_t i;
    uint16_t a = 0, c = 0;

    for (i = 0; i < %(plen)dUL; i++)
        wr(%(src)dUL + i, packed[i]);
    gz_rc = g4z_unpack(%(src)dUL, %(dst)dUL, %(n)dUL);
    for (i = 0; i < %(n)dUL; i++) {
        a += rd(%(dst)dUL + i);
        c += a;
    }
    gz_sum = (uint32_t)c << 16 | a;
    /* cut short: the byte after the count is a marker it must not touch */
    wr(%(dst)dUL + %(short)dUL, 0xA5);
    gz_short_rc = g4z_unpack(%(src)dUL, %(dst)dUL, %(short)dUL);
    gz_after = rd(%(dst)dUL + %(short)dUL);
    return 0;
}
"""


class G4z(unittest.TestCase):
    def run_sample(self, data):
        cc, asm, ld, db = (os.path.join(CALYPSI, "bin", t)
                           for t in ("cc65816", "as65816", "ln65816", "db65816"))
        if not os.path.exists(cc):
            self.skipTest("Calypsi not installed")
        p = squeeze(data)
        with tempfile.TemporaryDirectory() as d:
            scm = os.path.join(d, "linker.scm")
            with open(scm, "w") as f:
                f.write(LINK)
            with open(os.path.join(d, "s.s"), "w") as f:
                f.write(SCRATCH)
            c = os.path.join(d, "h.c")
            with open(c, "w") as f:
                f.write(HARNESS % dict(plen=len(p), src=SRC, dst=DST,
                                       n=len(data), short=SHORT))
            with open(os.path.join(d, "p.c"), "w") as f:
                f.write("#include <stdint.h>\nconst uint8_t __far packed[%d] = {\n"
                        % len(p))
                for o in range(0, len(p), 24):
                    f.write(",".join(str(b) for b in p[o:o + 24]) + ",\n")
                f.write("};\n")
            objs = []
            for src in ("h.c", "p.c"):
                o = os.path.join(d, src + ".o")
                subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                                "-O2", "-o", o, os.path.join(d, src)],
                               check=True, capture_output=True)
                objs.append(o)
            g, sc = os.path.join(d, "g4z.o"), os.path.join(d, "s.o")
            subprocess.run([asm, "-o", g, G4Z_S], check=True, capture_output=True)
            subprocess.run([asm, "-o", sc, os.path.join(d, "s.s")], check=True,
                           capture_output=True)
            elf = os.path.join(d, "h.elf")
            subprocess.run([ld, "-g", scm] + objs + [g, sc, "-o", elf,
                            "clib-lc-sd.a", "--rtattr", "exit=simplified",
                            "--root-symbol", "gz_scratch"],
                           check=True, capture_output=True)
            got = ccbug.simulate(db, elf, ["gz_sum", "gz_rc", "gz_short_rc",
                                           "gz_after"])
        self.assertEqual(got["gz_rc"], 0, "a whole stream reported an overrun")
        self.assertEqual(got["gz_sum"] & M, fold(data),
                         f"{len(data)} bytes from {len(p)} unpacked wrong")
        self.assertEqual(got["gz_short_rc"], 1, "a cut-short unpack said nothing")
        self.assertEqual(got["gz_after"] & 0xff, 0xA5,
                         "a cut-short unpack wrote past its count")

    def test_the_desktop(self):
        path = os.path.join(ROOT, "build", "desktop.g4a")
        if not os.path.exists(path):
            self.skipTest("no build/desktop.g4a: make first")
        import mkg4a
        self.run_sample(mkg4a.read_file(path))

    def test_runs_and_far_matches(self):
        data = made()
        far = [e for e in mkxex.parse(data) if e[0] == "M" and e[1] > 60000]
        self.assertTrue(far, "the made sample has no match reaching 60 KB back")
        self.run_sample(data)


if __name__ == "__main__":
    unittest.main()
