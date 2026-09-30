#!/usr/bin/env python3
"""A packed program's fixups, against the linker (phase 80).

tools/mkg4a.py derives a .G4A format 5's ten fixup lists from six links
that each move one region by a page or a bank.  This checks them a third
way: the program is linked once more where a loader might put it -- near
region at $1300, code at $05:0300, far variables at $0A:0600 -- and the
file's bytes, with the fixups applied for exactly those places the way
src/sys/app.c app_load_v5 applies them, must be that link's bytes.  A
list that missed a byte, or put one in the wrong list, shows here as a
byte that differs.

Run on a large-data accessory (far variables, the case that splits) and
on the desktop (2,000-odd code fixups).
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mkg4a                                # noqa: E402

AT_NEAR, AT_CODE, AT_VARS = 0x1300, 0x050300, 0x0A0600


def load_v5(blob):
    """What app_load_v5 puts where, for the places above: the near part at
    AT_NEAR and the code at AT_CODE, patched -- through mkg4a's own reader
    (read_v5, apply_v5), which is the loader's reading on the host."""
    f = mkg4a.read_v5(blob)
    near, code = mkg4a.apply_v5(f, AT_NEAR, AT_CODE, AT_VARS)
    return near, code, f["link_near"], f["near_size"], f["code_size"]


class TestPacked(unittest.TestCase):
    def check(self, name):
        g4a = os.path.join(ROOT, "build", f"{name}.g4a")
        at_elf = os.path.join(ROOT, "build", f"{name}-at.elf")
        cc = os.path.expanduser("~/dev/toolchains/calypsi-65816/bin/cc65816")
        if not os.path.exists(os.environ.get("CC65816", cc)):
            self.skipTest("Calypsi not installed")
        # make's own names for them: a path with ../ in it is not a target
        r = subprocess.run(["make", "-s", f"build/{name}.g4a",
                            f"build/{name}-at.elf"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"cannot build {name}: {r.stderr[-300:]}")
        blob = open(g4a, "rb").read()
        if blob[3] != 5:
            self.fail(f"{name} is not packed (format {blob[3]})")
        near, code, link_near, near_size, code_size = load_v5(blob)
        segs, _ = mkg4a.read_elf_all(at_elf)
        want_near, near_mask = mkg4a.image(segs, AT_NEAR, AT_NEAR + near_size)
        want_code, code_mask = mkg4a.image(segs, AT_CODE, AT_CODE + code_size)
        bad = [f"near+{i:04X}: {a:02X} not {b:02X}"
               for i, (a, b, m) in enumerate(zip(near, want_near, near_mask))
               if m and a != b]
        bad += [f"code+{i:04X}: {a:02X} not {b:02X}"
                for i, (a, b, m) in enumerate(zip(code, want_code, code_mask))
                if m and a != b]
        self.assertEqual(bad[:10], [], f"{name}: {len(bad)} byte(s) differ")
        # and it was a real test: the places moved every kind of address
        self.assertNotEqual(AT_CODE >> 16, blob[18])

    def test_an_accessory_with_far_variables(self):
        self.check("cpanelacc")

    def test_the_desktop(self):
        self.check("desktop")


if __name__ == "__main__":
    unittest.main()
