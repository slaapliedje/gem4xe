#!/usr/bin/env python3
"""Host tests for the application kit (tools/mksdk.py).

The kit is what somebody who is not this repository needs in order to
build a program that runs on gem4xe.  The only way to know it is
complete is to use it as they would: assemble it, copy it somewhere
with no relation to the source tree, and build from there.  A file left
out of the manifest is then a failure here rather than a discovery
somebody else makes.

Two programs are built out of the copy:

  * `example/hello.c`, the kit's own -- which proves the kit builds new
    code, and pins the memory budget its README quotes;
  * `src/m11_app.c`, the Phase 10 gate application, whose `.g4a` must
    come out **byte for byte identical** to the one this tree builds --
    and `make test-m11` says that exact binary loads, relocates and
    runs on the emulated machine.  So the kit is not merely
    self-contained; the program it produces is the one already proven
    to work.
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mksdk                                # noqa: E402

CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))
M11_APP = os.path.join(ROOT, "src", "m11_app.c")
HELLO_SIM = os.path.join(ROOT, "tests", "host", "hello_sim.c")
M11_G4A = os.path.join(ROOT, "build", "m11_app.g4a")
# The kit's default budget, as its Makefile and its README have it:
# a page of direct page, 2048 bytes without bits, 256 with.
NEAR_SIZE = 0x100 + 2048 + 256


def g4a_header(path):
    """The .g4a header the loader reads (src/sys/app.c, tools/mkg4a.py)."""
    with open(path, "rb") as f:
        d = f.read(20)
    assert d[:4] == b"G4A\x03", d[:4]
    near_base, near_size, far_off = struct.unpack("<HHH", d[4:10])
    far_size, = struct.unpack("<I", d[10:14])
    return dict(near_base=near_base, near_size=near_size, far_off=far_off,
                far_size=far_size, far_bank=d[14], far_banks=d[15])


class TestTheObjectLayoutIsTheSTs(unittest.TestCase):
    """An OBJECT is 24 bytes with ob_spec at offset 12, in BOTH data
    models -- which is what lets ob_spec be declared as gemlib's union
    rather than a bare LONG.

    The union is only safe because of an accident worth pinning down: a
    pointer is two bytes under --data-model=small and lands on the low
    word, which is where a bank-$00 address is kept, and four bytes under
    --data-model=large, little-endian with the bank in byte 2, so the
    whole four bytes read as a far pointer whose bank is the high word's
    zero.  Either way a member sees the address the AES put there.

    MEASURED OUT OF THE GENERATED CODE, not out of an array bound.  The
    usual trick -- char p[(sizeof(X)==N)?1:-1] -- asks the compiler's
    constant-expression evaluator, and that evaluator rounds a struct's
    size UP to its alignment where the code generator does not
    (tools/ccbug, B7).  For ICONBLK it answers 36 where every real use
    is 34, and this project spent an evening on a bug that was not there
    before the machine settled it.  So each size here is read back from a
    function that returns it: `lda ##24` is the answer, and nothing else
    is.
    """

    SIZES = (("an OBJECT", "sizeof(OBJECT)", 24),
             ("ob_spec", "sizeof(OBSPEC)", 4),
             ("ob_spec's bit-field", "sizeof(OBSPEC_BITS)", 4),
             ("the six words before ob_spec",
              "sizeof(struct { WORD a, b, c; UWORD d, e, f; })", 12),
             ("a TEDINFO", "sizeof(TEDINFO)", 28),
             ("an ICONBLK", "sizeof(ICONBLK)", 34),
             ("a BITBLK", "sizeof(BITBLK)", 14),
             ("the four words after ob_spec",
              "sizeof(struct { WORD a, b, c, d; })", 8))
    # ob_spec's OFFSET is pinned by those three between them -- 12 before
    # it, 4 of it, 8 after, and 24 in all leaves no room for padding
    # anywhere.  Measured directly it would want a pointer difference, and
    # this compiler answers that with an internal error.

    @classmethod
    def setUpClass(cls):
        cls.cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cls.cc):
            raise unittest.SkipTest("Calypsi not installed")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-sdk-")
        cls.kit = os.path.join(cls.dir, "gem4xe-sdk")
        mksdk.build(cls.kit)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def measure(self, model, exprs):
        """Compile one function per expression and read the immediate the
        compiler put in it.  This is the only honest way to ask this
        compiler how big a struct is (B7)."""
        src = os.path.join(self.dir, "layout.c")
        with open(src, "w") as f:
            f.write('#include "gem.h"\n')
            for i, e in enumerate(exprs):
                f.write(f"unsigned long probe{i}(void) "
                        f"{{ return (unsigned long)({e}); }}\n")
        asm = os.path.join(self.dir, "layout.s")
        r = subprocess.run(
            [self.cc, "--code-model=large", f"--data-model={model}", "-O2",
             "-I", os.path.join(self.kit, "include"),
             "--assembly-source", asm, "-c",
             "-o", os.path.join(self.dir, "layout.o"), src],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = open(asm).read()
        out = []
        for i in range(len(exprs)):
            m = re.search(rf"^probe{i}:.*?lda\s+##(\d+)", text,
                          re.S | re.M)
            self.assertIsNotNone(m, f"probe{i} has no immediate:\n{text[:400]}")
            out.append(int(m.group(1)))
        return out

    def layout(self, model):
        got = self.measure(model, [e for _, e, _ in self.SIZES])
        bad = [f"{what} is {g} bytes, expected {want}"
               for (what, _, want), g in zip(self.SIZES, got) if g != want]
        sizes = dict(zip((w for w, _, _ in self.SIZES), got))
        if (sizes["the six words before ob_spec"] + sizes["ob_spec"]
                + sizes["the four words after ob_spec"] != sizes["an OBJECT"]):
            bad.append("the parts of an OBJECT do not add up to the whole, "
                       "so something is padded and ob_spec has moved")
        self.assertEqual(bad, [], f"--data-model={model}: " + "; ".join(bad))

    def test_the_layout_holds_in_the_small_data_model(self):
        self.layout("small")

    def test_the_layout_holds_in_the_large_data_model(self):
        self.layout("large")

    def test_the_bit_field_ends_are_where_the_st_puts_them(self):
        """ob_spec.obspec is declared in the reverse of gemlib's order,
        because this compiler allocates a bit-field from the LOW end
        where the 68000's allocate from the high one.  Get it wrong and a
        box's character is read out of its interior colour -- four bytes
        that are still four bytes, so nothing else would notice.

        Read back out of the generated code, which is where the fact came
        from: the two ENDS of the word are what pin the direction, so
        `interiorcol` must come off the low word and `character` must
        come from the top byte."""
        src = os.path.join(self.dir, "bits.c")
        with open(src, "w") as f:
            f.write('#include "gem.h"\n'
                    "int low(OBSPEC *u) { return u->obspec.interiorcol; }\n"
                    "int high(OBSPEC *u) { return u->obspec.character; }\n")
        asm = os.path.join(self.dir, "bits.s")
        r = subprocess.run(
            [self.cc, "--code-model=large", "--data-model=small", "-O2",
             "-I", os.path.join(self.kit, "include"),
             "--assembly-source", asm, "-c",
             "-o", os.path.join(self.dir, "bits.o"), src],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = open(asm).read()

        def body(name):
            out, on = [], False
            for line in text.splitlines():
                if line.startswith(name + ":") or (on and not line.strip()
                                                   .startswith(name)):
                    on = True
                    out.append(line)
                if on and "rtl" in line:
                    break
            return "\n".join(out)

        lo, hi = body("low"), body("high")
        self.assertIn("##15", lo,
                      "interiorcol does not mask four bits off the low "
                      f"word -- the bit-field is the wrong way round:\n{lo}")
        self.assertNotIn("2,x", lo,
                         f"interiorcol reaches the high word:\n{lo}")
        self.assertIn("2,x", hi,
                      "character is not read from the top byte -- the "
                      f"bit-field is mirrored:\n{hi}")

    def test_a_pointer_is_the_size_the_union_argument_rests_on(self):
        small, = self.measure("small", ["sizeof(char *)"])
        large, = self.measure("large", ["sizeof(char *)"])
        self.assertEqual((small, large), (2, 4),
                         "a small-model pointer must be the low word and a "
                         "large-model one the whole four bytes, or the union "
                         f"does not overlay ob_spec: got {small} and {large}")


class TestManifest(unittest.TestCase):
    """These read the sources; no toolchain needed."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gem4xe-sdk-")
        self.kit = os.path.join(self.dir, "gem4xe-sdk")
        mksdk.build(self.kit)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_every_manifest_file_arrives(self):
        for dest, _ in mksdk.MANIFEST:
            self.assertTrue(os.path.isfile(os.path.join(self.kit, dest)), dest)

    def test_nothing_in_the_build_reaches_outside_the_kit(self):
        """A path that climbs out, or an absolute one into this tree,
        would work here and nowhere else."""
        bad = []
        for name in ("Makefile", "lib/gemapp.scm"):
            with open(os.path.join(self.kit, name)) as f:
                for i, line in enumerate(f, 1):
                    code = line.split(";;;")[0].split("#")[0]
                    if "../" in code or ROOT.rstrip("/.") in code:
                        bad.append(f"{name}:{i}: {line.strip()}")
        self.assertEqual(bad, [])

    def test_the_kit_carries_its_own_licence(self):
        with open(os.path.join(self.kit, "COPYING")) as f:
            self.assertIn("GNU GENERAL PUBLIC LICENSE", f.read())


class TestBuildsFromACopy(unittest.TestCase):
    """The kit, used the way somebody else would use it."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(CALYPSI, "bin", "cc65816")):
            raise unittest.SkipTest("Calypsi not installed")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-sdk-")
        cls.kit = os.path.join(cls.dir, "gem4xe-sdk")
        mksdk.build(cls.kit)
        # the gate application's source travels in as an author's would
        shutil.copyfile(M11_APP, os.path.join(cls.kit, "m11_app.c"))
        # ...with its one COP that is not gem4xe's, in assembly (src/m11_cop.s)
        shutil.copyfile(os.path.join(os.path.dirname(M11_APP), "m11_cop.s"),
                        os.path.join(cls.kit, "m11_cop.s"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make(self, *args):
        env = dict(os.environ, CALYPSI=CALYPSI)
        p = subprocess.run(["make", "-s"] + list(args), cwd=self.kit,
                           capture_output=True, text=True, env=env, timeout=600)
        self.assertEqual(p.returncode, 0,
                         f"make {' '.join(args)} failed:\n{p.stdout}\n{p.stderr}")
        return p.stdout

    def test_the_example_builds_and_is_a_loadable_program(self):
        self.make()
        out = os.path.join(self.kit, "hello.g4a")
        self.assertTrue(os.path.isfile(out))
        h = g4a_header(out)
        # what the kit's Makefile asked for, and what the loader needs
        self.assertEqual(h["near_size"], NEAR_SIZE)
        self.assertEqual(h["near_base"], 0x1000)
        self.assertEqual(h["far_banks"], 1, "one bank, as the loader takes")
        self.assertTrue(0 < h["far_size"] < 0x10000, h["far_size"])

    def test_it_builds_a_desk_accessory(self):
        """An accessory is built exactly like a program -- what makes it
        one is the shape of its main() -- so this proves the example
        compiles and links, not that the AES will load it.  m28 and m22
        are what prove the latter, on real accessories."""
        self.make("KIND=acc", "APP=example/acc.c")
        out = os.path.join(self.kit, "acc.g4a")
        self.assertTrue(os.path.isfile(out), "example/acc.c made no .g4a")
        self.assertEqual(g4a_header(out)["near_base"], 0x1000)

    def test_it_builds_a_control_panel_extension(self):
        """A CPX needs THREE things the kit did not hand out until 0.6.1:
        include/cpx.h, lib/cpxmain.c -- whose main() it links instead of
        writing its own -- and a --data-model=large build with Calypsi's
        clib-lc-ld.a beside it.  0.6 shipped the feature and shipped no
        way to write one."""
        self.make("KIND=cpx", "APP=example/cpx.c")
        out = os.path.join(self.kit, "cpx.g4a")
        self.assertTrue(os.path.isfile(out), "example/cpx.c made no .g4a")
        self.assertEqual(g4a_header(out)["near_base"], 0x1000)

    def test_the_library_the_readme_promises_actually_links(self):
        """gemtime.c and gemcompat.c SHIPPED IN THE KIT AND WERE NEVER
        COMPILED: they were not in the Makefile's object list, so a
        program that called clock() -- which README.md promises by name,
        saying a program written against mintlib's runs unchanged -- did
        not link.  A promise in a README is not a mechanism, so this
        calls every one of them.

        gemtime.o is built at -O0 on purpose (the Makefile says why);
        tests/host/test_gemtime.py holds the tree's copy of that rule and
        this holds the kit's, because the naive fix for the missing
        object is to add it to the pattern rule at -O2 and get silently
        wrong dates."""
        src = os.path.join(self.kit, "promised.c")
        with open(src, "w") as f:
            f.write(
                '#include "gem.h"\n'
                "#include <time.h>\n"
                "#include <support.h>\n"
                "#include <dirent.h>\n"
                "int main(void) {\n"
                "    time_t t; struct tm *g; char b[40]; clock_t c; DIR *d;\n"
                "    appl_init();\n"
                "    c = clock(); t = time(0); g = gmtime(&t);\n"
                '    strftime(b, sizeof b, "%Y-%m-%d", g);\n'
                '    if (stricmp(b, "x") == 0) b[0] = 0;\n'
                '    d = opendir("A:\\\\"); if (d) closedir(d);\n'
                "    appl_exit(); return (int)(c & 1);\n"
                "}\n")
        self.make("APP=promised.c")
        self.assertTrue(os.path.isfile(os.path.join(self.kit, "promised.g4a")))

    def test_the_kits_calendar_is_built_at_O0(self):
        """The reason is a miscompile, so the flag is checked rather than
        trusted: at -O1 and above this compiler mangles civil_from_days
        and a date comes back wrong with nothing to say so."""
        mk = open(os.path.join(self.kit, "Makefile"), errors="replace").read()
        line = [l for l in mk.splitlines()
                if "gemtime.c" in l and "$(CC)" in l or
                ("-O0" in l and "gemtime" in l)]
        self.assertTrue(
            any("-O0" in l for l in mk.splitlines()
                if "gemtime" in l or "-O0" in l),
            "the kit's Makefile no longer builds gemtime.o at -O0")

    def test_the_kit_rebuilds_the_gate_application_byte_for_byte(self):
        if not os.path.isfile(M11_G4A):
            self.skipTest("build/m11_app.g4a is not built "
                          "(make build/m11_app.g4a)")
        self.make("APP=m11_app.c", "ASM=m11_cop.s", "BSS=2048", "BITS=256", "STACK=256")
        with open(os.path.join(self.kit, "m11_app.g4a"), "rb") as f:
            kit = f.read()
        with open(M11_G4A, "rb") as f:
            tree = f.read()
        self.assertEqual(kit, tree,
                         "the kit's build of the gate application differs "
                         "from this tree's, so what test-m11 proves does "
                         "not carry over to the kit")

    def test_a_program_linked_with_the_old_gates_is_refused_on_the_host(self):
        """tools/mkg4a.py checks the gates it is about to stamp format 3 or
        4 over.  Objects built from an older kit's gemabi.s -- COP #$73,
        #$C8, #$01 -- must stop the build here, not come out as a file the
        Atari's loader accepts and whose every call it then refuses."""
        old = os.path.join(self.dir, "old-gates")
        shutil.copytree(self.kit, old,
                        ignore=shutil.ignore_patterns("build", "*.g4a"))
        p = os.path.join(old, "lib", "gemabi.s")
        with open(p) as f:
            s = f.read()
        for new, was in (("#0x56", "#0x73"), ("#0x41", "#0xc8"), ("#0x44", "#0x01")):
            self.assertIn(new, s)
            s = s.replace(new, was)
        with open(p, "w") as f:
            f.write(s)
        env = dict(os.environ, CALYPSI=CALYPSI)
        r = subprocess.run(["make", "-s"], cwd=old, capture_output=True,
                           text=True, env=env, timeout=600)
        self.assertNotEqual(r.returncode, 0,
                            "a program with the old gates was packed")
        self.assertIn("not COP #$56", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(old, "hello.g4a")))


class TestTheExampleIsShapedLikeAGemProgram(unittest.TestCase):
    """The example is the file an author copies first, so the ORDER of
    what it does is what matters: announce, ask, open, draw, close,
    leave.  It is run in the compiler's simulator against a recorder
    that answers plausibly (tests/host/hello_sim.c)."""

    APPL_INIT, APPL_EXIT, GRAF_HANDLE = 1010, 1019, 1077
    V_OPNVWK, V_CLSVWK = 100, 101

    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t)
                  for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-sdk-")
        kit = os.path.join(cls.dir, "gem4xe-sdk")
        mksdk.build(kit)
        objs = []
        for src in (os.path.join(kit, "lib", "gemlib.c"),
                    os.path.join(kit, "example", "hello.c"), HELLO_SIM):
            obj = os.path.join(cls.dir, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large",
                            "--data-model=small", "-O2",
                            "-I", os.path.join(kit, "include"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        elf = os.path.join(cls.dir, "hello.elf")
        subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified"], check=True)
        p = subprocess.run([db, "--nh", "--nx", "--exit-breakpoint", elf],
                           input="run\nprint hello_n\nprint hello_op\nquit\n",
                           capture_output=True, text=True, timeout=180)
        txt = p.stdout + p.stderr
        m = re.search(r"\$\d+ = (\d+)", txt)
        if not m:
            raise AssertionError(f"the simulator said nothing:\n{txt[-2000:]}")
        n = int(m.group(1))
        cls.ops = [int(v) for v in
                   re.findall(r"\[\s*\d+\s*\] = (-?\d+)", txt)][:n]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_announces_itself_first_and_leaves_last(self):
        self.assertEqual(self.ops[0], self.APPL_INIT)
        self.assertEqual(self.ops[-1], self.APPL_EXIT)

    def test_it_asks_the_aes_before_it_opens_a_workstation(self):
        self.assertLess(self.ops.index(self.GRAF_HANDLE),
                        self.ops.index(self.V_OPNVWK))

    def test_nothing_is_drawn_outside_the_workstation(self):
        first, last = (self.ops.index(self.V_OPNVWK),
                       self.ops.index(self.V_CLSVWK))
        drawing = [i for i, op in enumerate(self.ops)
                   if op < 1000 and op not in (self.V_OPNVWK, self.V_CLSVWK)]
        self.assertTrue(drawing, "the example draws nothing at all")
        self.assertGreater(min(drawing), first)
        self.assertLess(max(drawing), last)


if __name__ == "__main__":
    unittest.main()
