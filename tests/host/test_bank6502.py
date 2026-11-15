"""The 6502 build's banking tools, held to fixtures that must speak
(docs/6502.md).

A small C file has what the VDI has: a static helper in bank 1 called from
bank 2 across a BANK_TEXT cut, a table of static functions, a public
function in each bank, and resident code calling both -- and a C comment
spread over two lines after a declaration, which as6502 once read as a
comment over the assembly between (tools/bsp6502/bankasm.py).

  - Linked as the compiler leaves it, tools/bsp6502/bankcheck.py must
    REFUSE it: the map and the code scan see resident code calling the
    banks, and the assembly check sees bank 2 calling bank 1's static --
    which the code scan cannot, because it lands at $4000, where bank 2's
    own first function starts too.
  - Through bankasm.py, it must assemble, link and check clean, with a
    veneer for every reference across a bank.

Skipped when cc6502 is not installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import weakref

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TOOLS = os.path.join(ROOT, "tools", "bsp6502")
CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))
CC, AS, LN = (os.path.join(CAL, "bin", x) for x in ("cc6502", "as6502", "ln6502"))

SRC = r"""
#pragma clang section text="bank1"
static int count;      /* a comment that runs
                        * onto a second line */
__attribute__((noinline)) static int helper(int x) { count++; return x * 3 + count; }
int fa(int x) { return helper(x) + 1; }
#pragma clang section text="bank2"
typedef int (*fn)(int);
__attribute__((noinline)) static int twice(int x) { return x + x; }
const fn table[2] = { helper, twice };
int fb(int x) { return helper(x) + table[1](x); }
"""
MAIN = r"""
int fa(int); int fb(int);
int main(void) { return fa(1) + fb(2); }
"""
SCM = """
(define memories
  '((memory ZeroPage (address (#x80 . #xff)) (type ram) (qualifier zpage)
            (section (registers #x80) zzpage zpage))
    (memory StackPage (address (#x100 . #x1ff)) (type ram) (section stack))
    (memory Low (address (#x2000 . #x3fff)) (type rom)
            (section veneer code switch cdata data_init_table idata reset))
    (memory HiText (address (#xa000 . #xa0ff)) (type rom) (section (hicdata #xa000)))
    (memory Ram (address (#xa100 . #xbfff)) (type ram)
            (section b6keep data zdata cstack heap))
    (memory Bank1 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store1) (section bank1))
    (memory Bank2 (address (#x4000 . #x7fff)) (type rom) (scatter-to Store2) (section bank2))
    (memory Store1 (address (#x10000 . #x13fff)) (section Store1))
    (memory Store2 (address (#x14000 . #x17fff)) (section Store2))
    (block cstack (size #x400)) (block heap (size #x10)) (block stack (size #x100))))
"""


def run(*cmd, cwd):
    return subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)


@unittest.skipUnless(os.path.exists(CC), "cc6502 not installed")
class Bank6502(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="bank6502-")
        weakref.finalize(cls, shutil.rmtree, cls.d, True)
        d = cls.d
        for name, text in (("s.c", SRC), ("m.c", MAIN), ("t.scm", SCM)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        # an object, and (for s.c) the assembly: --assembly-source writes
        # only the assembly
        for c, extra in (("s", []), ("s", ["--assembly-source=s.s"]), ("m", [])):
            r = run(CC, "-O2", "--core", "6502", "--no-cross-call", "-c", f"{c}.c",
                    "-o", f"{c}.o", *extra, cwd=d)
            assert r.returncode == 0, r.stderr
        r = run(AS, "--core", "6502", os.path.join(ROOT, "src", "sys6502", "bank6502.s"),
                "-o", "bank.o", cwd=d)
        assert r.returncode == 0, r.stderr

    def link_and_check(self, objs, tag):
        d = self.d
        r = run(LN, "t.scm", *objs, "bank.o", "-o", f"{tag}.elf",
                os.path.join(CAL, "lib", "clib-6502.a"), "--verbose",
                "--list-file", f"{tag}.map", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), f"{tag}.map",
                   "--elf", f"{tag}.elf", cwd=d)

    def test_as_compiled_is_refused(self):
        r = self.link_and_check(["s.o", "m.o"], "raw")
        self.assertEqual(r.returncode, 1, r.stdout)
        out = r.stdout
        self.assertIn("is referred to from main in resident", out,
                      "the map check did not see resident code calling a bank")
        self.assertIn("resident code jumps into the window", out,
                      "the code scan did not see resident code calling a bank")
        # bank 2's call to bank 1's static lands at $4000, where bank 2's own
        # first function starts too: the bytes cannot tell, the names can
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", "s.s",
                "--bank", "bank1=1", "--bank", "bank2=2", cwd=self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"jsr helper -- in bank 1, from bank 2",
                         "the assembly check did not see bank 2 calling bank 1's static")
        self.assertRegex(r.stdout, r"\.word helper, twice -- |\.word helper -- in bank 1, "
                                   r"from resident|helper -- in bank 1, from resident",
                         "the assembly check did not see the table of statics")

    def test_through_bankasm_is_clean(self):
        d = self.d
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), "s.s", "s.b.s",
                "--tu", "s", "--bank", "bank1=1", "--bank", "bank2=2", cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(d, "s.b.s")) as f:
            text = f.read()
        self.assertIn("s__helper__v:", text, "no veneer for the static called from bank 2")
        self.assertIn(".word   s__helper__v", text, "the table does not name the veneer")
        self.assertIn("fa__b:", text)
        r = run(AS, "--core", "6502", "s.b.s", "-o", "s.b.o", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.link_and_check(["s.b.o", "m.o"], "veneered")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 problem(s)", r.stdout)
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", "s.b.s",
                "--bank", "bank1=1", "--bank", "bank2=2", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
