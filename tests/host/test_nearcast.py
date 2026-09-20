"""No 24-bit address may be truncated into sixteen bits by a cast.

tools/nearcast.py explains the failure this guards against.  The short
version: ob_spec, te_ptext and their kind are LONGs holding ADDRESSES,
and since rs_load began putting a resource in FAR memory for any caller
that can hold a 32-bit pointer, `(uint16_t)` on one of them throws the
bank away and the write lands on the engine.

It does not announce itself.  The calculator accessory hit it on
2026-09-20 and the only symptom was the desktop coming up to an hourglass
on an empty desk, hung inside a GEMDOS call -- no refused call, no BRK,
no irq_fault.  It was found by bisecting disk images.

THE CHECK IS ALSO TESTED, not merely run: test_it_can_fail puts the
fault back into a copy of a real file and requires the tool to say so.  A
check that passes by saying nothing is not a check yet.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TOOL = os.path.join(ROOT, "tools", "nearcast.py")


class NearCast(unittest.TestCase):
    def test_tree_is_clean(self):
        r = subprocess.run([sys.executable, TOOL], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_it_can_fail(self):
        """Put the fault back and require the tool to find it."""
        src = os.path.join(ROOT, "src", "apps", "calc.c")
        with open(src, "r", errors="replace") as f:
            text = f.read()
        broken = text.replace("(TEDINFO *)(uint32_t)tree[CDISP]",
                              "(TEDINFO *)(uint16_t)tree[CDISP]")
        self.assertNotEqual(broken, text,
                            "src/apps/calc.c no longer has the line this "
                            "test breaks; point it at another one")
        with tempfile.TemporaryDirectory() as d:
            apps = os.path.join(d, "src", "apps")
            os.makedirs(apps)
            with open(os.path.join(apps, "calc.c"), "w") as f:
                f.write(broken)
            # the tool resolves its own ROOT from __file__, so run a copy
            # of it that looks at the temporary tree instead
            with open(TOOL, "r") as f:
                tool_src = f.read()
            tool_src = tool_src.replace(
                'ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")',
                f'ROOT = {d!r}')
            probe = os.path.join(d, "nearcast_probe.py")
            with open(probe, "w") as f:
                f.write(tool_src)
            r = subprocess.run([sys.executable, probe], capture_output=True,
                               text=True)
        self.assertEqual(r.returncode, 1,
                         "the truncation was put back and nearcast.py did "
                         "not report it:\n" + r.stdout + r.stderr)
        self.assertIn("calc.c", r.stdout)

    def test_it_honours_a_stated_reason(self):
        """A cast marked nearcast-ok: is left alone -- so the escape hatch
        exists and a deliberate one need not be deleted."""
        with tempfile.TemporaryDirectory() as d:
            apps = os.path.join(d, "src", "apps")
            os.makedirs(apps)
            with open(os.path.join(apps, "x.c"), "w") as f:
                f.write("char *p = (char *)(uint16_t)ted->te_ptext;"
                        "  /* nearcast-ok: the AES's own near tree */\n")
            with open(TOOL, "r") as f:
                tool_src = f.read()
            tool_src = tool_src.replace(
                'ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")',
                f'ROOT = {d!r}')
            probe = os.path.join(d, "nearcast_probe.py")
            with open(probe, "w") as f:
                f.write(tool_src)
            r = subprocess.run([sys.executable, probe], capture_output=True,
                               text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
