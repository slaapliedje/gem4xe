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
        self.assertRegex(r.stdout, r"\.word helper -- the address of a function in bank 1",
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


class SharedTail(unittest.TestCase):
    """bankcheck's code scan, on bytes made here (no compiler needed).

    Bank 1 has two functions, the second jumping into the middle of the
    first -- the optimiser's shared tail -- at an address where bank 2's
    function starts.  As a JMP onto one of bank 1's instructions that is
    a tail and passes (step 3b's antic_cursor_restore); the same address
    from a JSR, or a JMP between two of bank 1's instructions, is refused
    as a call into bank 2."""

    def scan(self, op, target, h_at=0x4002, f_defs=()):
        sys.path.insert(0, TOOLS)
        import bankcheck
        sys.path.remove(TOOLS)
        # bank 1: f at $4000 = LDA #0 / LDA #0 / RTS (tail at $4002),
        #         g at $4005 = <op> target / RTS
        # bank 2: h at h_at, NOPs before it
        b1 = bytes([0xA9, 0, 0xA9, 0, 0x60, op, target & 0xFF, target >> 8, 0x60])
        b2 = bytes([0xEA] * (h_at - 0x4000) + [0x60])
        mem = {}
        for k, v in enumerate(b1):
            mem[0x10000 + k] = v
        for k, v in enumerate(b2):
            mem[0x14000 + k] = v
        frags = {
            "f": dict(name="f", section="bank1", bank="Store1", run=(0x4000, 0x4004),
                      store=(0x10000, 0x10004), defs=list(f_defs)),
            "g": dict(name="g", section="bank1", bank="Store1", run=(0x4005, 0x4008),
                      store=(0x10005, 0x10008)),
            "p": dict(name="p", section="bank2", bank="Store2", run=(0x4000, h_at - 1),
                      store=(0x14000, 0x10000 + h_at - 1)),
            "h": dict(name="h", section="bank2", bank="Store2", run=(h_at, h_at),
                      store=(0x10000 + h_at, 0x10000 + h_at)),
        }
        bad, _ = bankcheck.check_code(frags, mem)
        return bad

    def test_jmp_onto_an_instruction_is_a_tail(self):
        self.assertEqual(self.scan(0x4C, 0x4002), [])

    def test_jsr_there_is_a_call_into_bank_2(self):
        bad = self.scan(0x20, 0x4002)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("a function in Store2", bad[0])

    def test_jsr_to_a_label_the_fragment_defines_passes(self):
        # an assembly file's section is one fragment with several entry
        # points: an_cpaint6 inside an_fill6's fragment, at an address
        # where another bank's function starts (speed 3)
        self.assertEqual(self.scan(0x20, 0x4002, f_defs=(0x4000, 0x4002)), [])

    def test_jmp_between_instructions_is_refused(self):
        # bank 2's function at $4003, the middle of LDA #0 in bank 1
        bad = self.scan(0x4C, 0x4003, h_at=0x4003)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("a function in Store2", bad[0])


# two files, one program: ga in bank 1 (a.c); gb in bank 1 and gc in bank 2
# calling it, and a table in b.c taking its address (b.c)
SRC_A = r"""
#pragma clang section text="bank1"
int ga(int x) { return x * 5 + 1; }
"""
SRC_B = r"""
int ga(int);
typedef int (*fn)(int);
#pragma clang section text="bank1"
int gb(int x) { return ga(x) + 2; }
#pragma clang section text="bank2"
const fn tab[1] = { ga };
int gc(int x) { return ga(x) + tab[0](x); }
"""
MAIN2 = r"""
int gb(int); int gc(int);
int main(void) { return gb(1) + gc(2); }
"""


@unittest.skipUnless(os.path.exists(CC), "cc6502 not installed")
class AcrossFiles(unittest.TestCase):
    """bankasm.py's index: a call into another FILE'S function in the same
    bank goes straight to it (no trampoline), a call from another bank
    through a veneer in the CALLER'S bank, and only an address taken needs
    the resident veneer.  bankcheck --asm --index must refuse a direct
    call into another file's function in another bank."""

    BANKS = ["--bank", "bank1=1", "--bank", "bank2=2"]

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="bank6502x-")
        weakref.finalize(cls, shutil.rmtree, cls.d, True)
        d = cls.d
        for name, text in (("a.c", SRC_A), ("b.c", SRC_B), ("m.c", MAIN2), ("t.scm", SCM)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        for c in ("a", "b"):
            r = run(CC, "-O2", "--core", "6502", "--no-cross-call", "-c", f"{c}.c",
                    "-o", f"{c}.o", f"--assembly-source={c}.s", cwd=d)
            assert r.returncode == 0, r.stderr
        r = run(CC, "-O2", "--core", "6502", "-c", "m.c", "-o", "m.o", cwd=d)
        assert r.returncode == 0, r.stderr
        r = run(AS, "--core", "6502", os.path.join(ROOT, "src", "sys6502", "bank6502.s"),
                "-o", "bank.o", cwd=d)
        assert r.returncode == 0, r.stderr
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), "--index", "p.idx",
                *cls.BANKS, "a.s", "b.s", cwd=d)
        assert r.returncode == 0, r.stdout + r.stderr
        for c in ("a", "b"):
            r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), f"{c}.s", f"{c}.b.s",
                    "--tu", c, *cls.BANKS, "--index", "p.idx", cwd=d)
            assert r.returncode == 0, r.stdout + r.stderr
        with open(os.path.join(d, "b.b.s")) as f:
            cls.text = f.read()

    def test_the_index(self):
        with open(os.path.join(self.d, "p.idx")) as f:
            self.assertIn("ga 1", f.read().split("\n"))

    def test_same_bank_is_direct(self):
        # gb, in bank 1, calls ga__b itself
        body = self.text.split("gb__b:")[1].split(".section")[0]
        self.assertRegex(body, r"j(sr|mp)\s+ga__b\b", body)

    def test_other_bank_through_its_own_veneer(self):
        self.assertIn("b__ga__v2:", self.text, "no veneer in bank 2 for its call to ga")
        tail = self.text.split("b__ga__v2:")[0].rsplit(".section", 1)[1]
        self.assertTrue(tail.startswith(" bank2"), "bank 2's veneer is not in bank 2: " + tail)

    def test_an_address_takes_the_resident_veneer(self):
        self.assertRegex(self.text, r"\.word\s+ga\b", "the table does not name ga's veneer")

    def test_links_and_checks_clean(self):
        d = self.d
        for c in ("a", "b"):
            r = run(AS, "--core", "6502", f"{c}.b.s", "-o", f"{c}.b.o", cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(LN, "t.scm", "a.b.o", "b.b.o", "m.o", "bank.o", "-o", "x.elf",
                os.path.join(CAL, "lib", "clib-6502.a"), "--verbose", "--list-file", "x.map",
                cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "x.map", "--elf", "x.elf",
                cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout)
        for c in ("a", "b"):
            r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", f"{c}.b.s",
                    *self.BANKS, "--index", "p.idx", cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_direct_call_into_another_bank_is_refused(self):
        d = self.d
        # bank 2's calls straight to ga__b, the veneer left unused
        broken = self.text.replace("b__ga__v2:", "b__ga__vx:")
        broken = broken.replace(".public b__ga__v2", ".public b__ga__vx")
        broken = broken.replace("b__ga__v2", "ga__b")
        with open(os.path.join(d, "bad.b.s"), "w") as f:
            f.write(broken)
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", "bad.b.s",
                *self.BANKS, "--index", "p.idx", cwd=d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"j(sr|mp) ga__b -- in bank 1, from bank 2")


# BANK_DATA (src/portab.h): an array in bank 1's own memory, used there
SRC_D = r"""
#pragma clang section text="bank1"
__attribute__((section("bank1__bank"))) static int pool[40];
int fd(int i) { pool[i] = i + 7; return pool[i]; }
"""
SRC_D_BAD = r"""
#pragma clang section text="bank1"
__attribute__((section("bank1__bank"))) static int pool[40];
int fd(int i) { pool[i] = i + 7; return pool[i]; }
#pragma clang section text="bank2"
void fe(int i) { pool[i] = 3; }
"""
MAIN_D = r"""
int fd(int);
int main(void) { return fd(1); }
"""
SCM_D = SCM.replace("(section bank1))", "(section bank1 bank1__bank))")


@unittest.skipUnless(os.path.exists(CC), "cc6502 not installed")
class BankData(unittest.TestCase):
    """A BANK_DATA array: bankasm.py makes its section bits in the bank, the
    link puts them in bank 1's store with the code, and the checks pass;
    a store to it from bank 2 is refused by the assembly check."""

    BANKS = ["--bank", "bank1=1", "--bank", "bank2=2"]

    def build(self, src, tag):
        d = self.d
        with open(os.path.join(d, f"{tag}.c"), "w") as f:
            f.write(src)
        r = run(CC, "-O2", "--core", "6502", "--no-cross-call", "-c", f"{tag}.c",
                "-o", f"{tag}.o", f"--assembly-source={tag}.s", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), "--index", f"{tag}.idx",
                *self.BANKS, f"{tag}.s", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), f"{tag}.s", f"{tag}.b.s",
                "--tu", tag, *self.BANKS, "--index", f"{tag}.idx", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", f"{tag}.b.s",
                   *self.BANKS, "--index", f"{tag}.idx", cwd=d)

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="bank6502d-")
        weakref.finalize(cls, shutil.rmtree, cls.d, True)
        for name, text in (("m.c", MAIN_D), ("t.scm", SCM_D)):
            with open(os.path.join(cls.d, name), "w") as f:
                f.write(text)
        r = run(CC, "-O2", "--core", "6502", "-c", "m.c", "-o", "m.o", cwd=cls.d)
        assert r.returncode == 0, r.stderr
        r = run(AS, "--core", "6502", os.path.join(ROOT, "src", "sys6502", "bank6502.s"),
                "-o", "bank.o", cwd=cls.d)
        assert r.returncode == 0, r.stderr

    def test_in_the_bank_and_clean(self):
        d = self.d
        r = self.build(SRC_D, "dd")
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(os.path.join(d, "dd.b.s")) as f:
            self.assertIn(".section bank1__bank,text", f.read())
        r = run(AS, "--core", "6502", "dd.b.s", "-o", "dd.b.o", cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(LN, "t.scm", "dd.b.o", "m.o", "bank.o", "-o", "dd.elf",
                os.path.join(CAL, "lib", "clib-6502.a"), "--verbose", "--list-file", "dd.map",
                cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(d, "dd.map")) as f:
            m = f.read()
        self.assertRegex(m, r"bank1__bank\s+4[0-9a-f]{3}-4[0-9a-f]{3}\s+0050\s+Bank1",
                         "the array is not 80 bytes in bank 1's window")
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "dd.map", "--elf", "dd.elf",
                cwd=d)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_used_from_another_bank_is_refused(self):
        r = self.build(SRC_D_BAD, "db")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"sta pool -- in bank 1, from bank 2")


# step 4c's crash: a function in bank 1 hands a pointer to a static in its
# OWN bank to code in another bank, which calls it there
SRC_P = r"""
typedef int (*cbf)(int);
int walk(cbf f, int x);
#pragma clang section text="bank1"
__attribute__((noinline)) static int cb(int x) { return x + 7; }
int fp(int x) { return walk(cb, x); }
#pragma clang section text="bank2"
int walk(cbf f, int x) { return f(x) + f(x + 1); }
"""


@unittest.skipUnless(os.path.exists(CC), "cc6502 not installed")
class SameBankPointer(unittest.TestCase):
    """A function pointer is called from whatever bank holds when it is
    called, so its address must be the resident veneer even when the
    function taking it is in the pointer's own bank (newrect handing
    everyobj mkrect, step 4c).  bankasm.py must emit the veneer, and the
    assembly check must refuse the raw address."""

    BANKS = ["--bank", "bank1=1", "--bank", "bank2=2"]

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="bank6502p-")
        weakref.finalize(cls, shutil.rmtree, cls.d, True)
        d = cls.d
        with open(os.path.join(d, "p.c"), "w") as f:
            f.write(SRC_P)
        r = run(CC, "-O2", "--core", "6502", "--no-cross-call", "-c", "p.c", "-o", "p.o",
                "--assembly-source=p.s", cwd=d)
        assert r.returncode == 0, r.stderr
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), "--index", "p.idx",
                *cls.BANKS, "p.s", cwd=d)
        assert r.returncode == 0, r.stdout + r.stderr
        r = run(sys.executable, os.path.join(TOOLS, "bankasm.py"), "p.s", "p.b.s", "--tu", "p",
                *cls.BANKS, "--index", "p.idx", cwd=d)
        assert r.returncode == 0, r.stdout + r.stderr
        with open(os.path.join(d, "p.b.s")) as f:
            cls.text = f.read()

    def test_the_pointer_is_the_resident_veneer(self):
        self.assertRegex(self.text, r"#\.byte0 p__cb__v\b", "fp hands walk cb's own address")
        self.assertIn("p__cb__v:", self.text)

    def test_the_raw_address_is_refused(self):
        d = self.d
        with open(os.path.join(d, "raw.b.s"), "w") as f:
            f.write(self.text.replace("#.byte0 p__cb__v", "#.byte0 cb")
                    .replace("#.byte1 p__cb__v", "#.byte1 cb"))
        r = run(sys.executable, os.path.join(TOOLS, "bankcheck.py"), "--asm", "raw.b.s",
                *self.BANKS, "--index", "p.idx", cwd=d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"cb -- the address of a function in bank 1")


if __name__ == "__main__":
    unittest.main()
