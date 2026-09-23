"""The opcode audit must stay true, and must stay able to say no.

tools/opcodes.py reads the DISPATCHERS -- what actually has a case in
crysbind and what sits in the VDI's two jump tables -- rather than the
names a header declares.  It is the thing that found WF_SCREEN and
WF_OWNER served-but-undeclared and WF_BOTTOM declared-but-unserved
(docs/phase45.md), and it is how "79 of 79" is a measurement rather than
a claim.

It had no gate.  A tool that exists to stop a silent gap had no way of
telling anybody when IT broke, and its counts appear in the README, in
docs/phase45.md and docs/phase46.md and in the argument for whether a
release is ready.  So they are asserted here.

THE `(nop)` MARKER, which is the subtle part.  Five VDI slots dispatch
to v_nop on purpose: v_clswk, because nothing closes the physical
workstation on this machine; cellarray, vq_cellarray and valuator,
because DRI's own GEM/3.1 screen driver nops them too; and 34, which is
not an opcode.  The table marks each `(nop)` and vdi.c says why.

Before 2026-09-20 the tool reported all five as MISS, which read as five
things to go and do -- and it did, to somebody deciding whether 0.5 was
ready.  Now a MARKED nop counts as dispatched and an UNMARKED one is
still a gap.  That is a real distinction and not a blanket exemption,
which test_an_unmarked_nop_is_still_a_gap exists to prove: without it,
"0 not served" would be unfalsifiable and the audit worthless.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TOOL = os.path.join(ROOT, "tools", "opcodes.py")
VDI_C = os.path.join(ROOT, "src", "vdi", "vdi.c")
EMUTOS = os.path.expanduser("~/dev/emutos")

# The rest of this file runs the tool as a subprocess, on purpose: what it
# PRINTS is what a person reads.  ServedReference below needs its parsed
# tables instead, so it imports it -- vdi_table() reads src/vdi/vdi.c and
# wants neither EmuTOS nor a tool chain.
sys.path.insert(0, os.path.join(ROOT, "tools"))
import opcodes                                          # noqa: E402


def run(cwd=None):
    return subprocess.run([sys.executable, TOOL], capture_output=True,
                          text=True, cwd=cwd or ROOT)


@unittest.skipUnless(os.path.isdir(EMUTOS),
                     "the AES names come from EmuTOS's include/aesdefs.h")
class Opcodes(unittest.TestCase):
    def setUp(self):
        self.r = run()
        self.assertEqual(self.r.returncode, 0, self.r.stdout + self.r.stderr)

    def test_every_opcode_is_served(self):
        self.assertIn("0 AES and 0 VDI opcodes are not served", self.r.stdout,
                      self.r.stdout)

    def test_the_counts_are_what_the_docs_say(self):
        """79 and 71 appear in README.md and the phase notebooks.  If the
        tables grow, this fails and the prose gets updated with it."""
        self.assertRegex(self.r.stdout, r"AES: 79 of 79 opcodes served")
        self.assertRegex(self.r.stdout, r"VDI: 71 of 71 opcodes served")

    def test_the_deliberate_nops_are_named(self):
        """Not just counted -- named, so that 'on purpose' is a list a
        reader can check against vdi.c rather than a reassurance."""
        self.assertIn("dispatch to v_nop ON PURPOSE", self.r.stdout)
        for name in ("v_clswk", "cellarray", "vq_cellarray", "valuator"):
            self.assertRegex(self.r.stdout, rf"nop\s+\d+\s+{re.escape(name)}",
                             self.r.stdout)

    def test_an_unmarked_nop_is_still_a_gap(self):
        """THE ONE THAT MAKES THE REST MEAN ANYTHING.  Take the `(nop)`
        off a slot -- leaving the handler exactly as it was -- and the
        tool must call it MISS again.  If it did not, `0 not served`
        would be true of any tree at all."""
        with open(VDI_C, errors="ignore") as f:
            text = f.read()
        broken = text.replace("/* 10 cellarray (nop) */", "/* 10 cellarray */")
        self.assertNotEqual(broken, text,
                            "opcode 10's marker is not spelt as this test "
                            "expects; point it at another marked slot")
        with tempfile.TemporaryDirectory() as d:
            # the tool resolves ROOT from its own __file__, so give it a
            # tree whose src/vdi/vdi.c is the broken one and whose tools/
            # and src/sys/ are the real ones
            os.makedirs(os.path.join(d, "src", "vdi"))
            os.makedirs(os.path.join(d, "src", "sys"))
            os.makedirs(os.path.join(d, "tools"))
            with open(os.path.join(d, "src", "vdi", "vdi.c"), "w") as f:
                f.write(broken)
            shutil.copy(os.path.join(ROOT, "src", "sys", "abi.c"),
                        os.path.join(d, "src", "sys", "abi.c"))
            shutil.copy(TOOL, os.path.join(d, "tools", "opcodes.py"))
            r = subprocess.run([sys.executable,
                                os.path.join(d, "tools", "opcodes.py")],
                               capture_output=True, text=True, cwd=d)
        self.assertIn("MISS   10", r.stdout,
                      "an UNMARKED v_nop was not reported as a gap -- the "
                      "marker has become a blanket exemption:\n" + r.stdout)
        self.assertIn("1 VDI opcodes are not served", r.stdout, r.stdout)



class ServedReference(unittest.TestCase):
    """tools/sdk/served.md, which the kit ships so a porter can ask "will
    menu_popup work" without reading 1,255 lines of header.

    It is GENERATED and COMMITTED, because the AES half of it needs
    EmuTOS's name table and this suite must run on a machine with no
    tool chain and no donor tree.  A committed generated file drifts, so
    the VDI half -- which needs neither -- is checked against the
    dispatcher here.  That is the half that changes when somebody adds an
    opcode.
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "tools", "sdk", "served.md")
        if not os.path.exists(path):
            raise unittest.SkipTest("tools/sdk/served.md not generated "
                                    "(make served)")
        with open(path, errors="replace") as f:
            cls.doc = f.read()
        cls.vdi = cls.doc[cls.doc.index("## VDI"):]

    def test_every_vdi_opcode_the_dispatcher_has_is_in_it(self):
        rows = {int(m.group(1)) for m in
                re.finditer(r"^\| (\d+) \| `", self.vdi, re.M)}
        have = set()
        for tbl in ("jmptb1", "jmptb2"):
            have |= set(opcodes.vdi_table(tbl))
        self.assertEqual(sorted(have - rows), [],
                         "tools/sdk/served.md is missing VDI opcodes the "
                         "dispatcher serves -- run `make served`")
        self.assertEqual(sorted(rows - have), [],
                         "tools/sdk/served.md lists VDI opcodes that are not "
                         "in the dispatcher any more -- run `make served`")

    def test_the_deliberate_nops_are_marked_as_deliberate(self):
        """A reader must be able to tell "returns cleanly and draws
        nothing, on purpose" from "not there"."""
        for tbl in ("jmptb1", "jmptb2"):
            for op, (handler, _note, settled) in opcodes.vdi_table(tbl).items():
                if handler == "v_nop" and settled:
                    row = re.search(rf"^\| {op} \| .*$", self.vdi, re.M)
                    self.assertIsNotNone(row, f"VDI {op} is not in served.md")
                    self.assertIn("on purpose", row.group(0),
                                  f"VDI {op} is a deliberate v_nop and "
                                  f"served.md does not say so")

    def test_it_is_not_empty(self):
        """Both checks above pass for a file that failed to parse."""
        self.assertGreater(self.doc.count("\n| "), 100, self.doc[:200])

if __name__ == "__main__":
    unittest.main()
