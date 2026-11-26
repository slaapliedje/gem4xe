#!/usr/bin/env python3
"""Host tests for the application kit's 6502 half (tools/sdk/Makefile.6502).

As tests/host/test_sdk.py does for the 65C816: the kit is assembled
(tools/mksdk.py), copied to a directory with no relation to this tree,
and built from there with its own Makefile.6502 -- so a file left out of
the manifest fails here, not for the first person outside the tree.

Two programs are built out of the copy:

  * `example/hello.c`, the kit's own, unchanged from the 65C816's -- the
    same C builds for both, which is the kit's promise;
  * `src/p6m_prog.c`, the step-5c-1 program of three banks, whose .g6a
    must come out BYTE FOR BYTE identical to build/p6mprog.g6a -- which
    `make test-p6m` loads and runs on the emulated machine.  So what the
    kit builds is the program already proven to work.

And the kit's bank check must refuse a wrong call between banks: a copy
of the example whose call into another bank skips bankasm is a failed
build, not a program that jumps into whatever bank is mapped.

Skipped when cc6502 is not installed, as the tree's own 6502 rules are.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mksdk                                # noqa: E402

CALYPSI6 = os.environ.get("CALYPSI6",
                          os.path.expanduser("~/dev/toolchains/calypsi-6502"))
CC6 = os.path.join(CALYPSI6, "bin", "cc6502")
P6M_SRC = os.path.join(ROOT, "src", "p6m_prog.c")
P6M_G6A = os.path.join(ROOT, "build", "p6mprog.g6a")


@unittest.skipUnless(os.path.exists(CC6), "no cc6502")
class TestTheKitBuildsForThe6502(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="g4sdk6502-")
        cls.kit = os.path.join(cls.tmp, "gem4xe-sdk")
        mksdk.build(cls.kit)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def make(self, *args, cwd=None):
        return subprocess.run(["make", "-f", "Makefile.6502", f"CALYPSI6={CALYPSI6}", *args],
                              cwd=cwd or self.kit, capture_output=True, text=True)

    def test_hello_builds_unchanged(self):
        r = self.make()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        with open(os.path.join(self.kit, "hello.g6a"), "rb") as f:
            head = f.read(4)
        self.assertEqual(head[:3], b"G6\x02", "a .G6A of several banks (format 2)")

    def test_p6m_comes_out_byte_for_byte(self):
        if not os.path.exists(P6M_G6A):
            self.skipTest("build/p6mprog.g6a not built")
        shutil.copy(P6M_SRC, os.path.join(self.kit, "p6m_prog.c"))
        r = self.make("APP=p6m_prog.c", "NAME=p6mprog")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        with open(os.path.join(self.kit, "p6mprog.g6a"), "rb") as f:
            mine = f.read()
        with open(P6M_G6A, "rb") as f:
            want = f.read()
        self.assertEqual(len(mine), len(want), "the same length as build/p6mprog.g6a")
        self.assertEqual(mine, want, "the same bytes as build/p6mprog.g6a")

    def test_a_wrong_call_between_banks_is_refused(self):
        """bankcheck's half of the promise: one of bankasm's veneer calls
        put back to the plain `jsr` the compiler wrote -- as hand-written
        assembly or a rule of one's own would leave it -- after bankasm
        and before bankcheck.  The build must stop, in bankcheck."""
        kit2 = os.path.join(self.tmp, "kit-bad")
        shutil.copytree(self.kit, kit2, ignore=shutil.ignore_patterns("build", "*.g6a"))
        with open(os.path.join(kit2, "Makefile.6502")) as f:
            mk = f.read()
        # after bankasm, before bankcheck: one cross-bank call made plain
        mk = mk.replace("\tpython3 tools/bsp6502/bankcheck.py --asm",
                        "\tpython3 badcall.py $(B)/basm/$*.b.s\n"
                        "\tpython3 tools/bsp6502/bankcheck.py --asm", 1)
        with open(os.path.join(kit2, "Makefile.6502"), "w") as f:
            f.write(mk)
        with open(os.path.join(kit2, "badcall.py"), "w") as f:
            f.write("import re, sys\n"
                    "p = sys.argv[1]; s = open(p).read()\n"
                    "# a veneer call `jsr TU__F__vN` back to the plain `jsr F__b`\n"
                    "s2 = re.sub(r'jsr\\s+\\w+?__(\\w+?)__v\\d+\\b', r'jsr \\1__b', s, count=1)\n"

                    "open(p, 'w').write(s2)\n")
        r = self.make("BANK_gemlib=3", cwd=kit2)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0,
                            "a plain jsr into another bank must fail the build\n" + out[-2000:])
        self.assertIn("across a bank", out, "...and fail it in bankcheck, by name\n" + out[-2000:])


if __name__ == "__main__":
    unittest.main()
