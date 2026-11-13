#!/usr/bin/env python3
"""The kit's tools/install.py (tools/sdk/install.py): what it promises,
that "a name that is already there is replaced", on both file systems a
gem4xe disk has.  It did not: on an SDFS disk -- the release's floppies,
G4DOS's -- it stopped at "exists", found putting a program on the system
floppy as its desktop (g4paint, 2026-11-04).

A replaced file must read back as the new one, be the only entry of its
name, give back the old one's sectors, and leave a disk whose bitmap,
chains and free count agree (Sdfs.check).  A name that is not there is
added as before.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr                                  # noqa: E402

INSTALL = os.path.join(ROOT, "tools", "sdk", "install.py")
OLD = bytes(range(256)) * 20               # 5,120 bytes: twenty sectors
NEW = b"the new one\x9b" * 30


def run(*args):
    # the kit ships it beside a copy of tools/atr.py; here that is ../
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tools"))
    return subprocess.run([sys.executable, INSTALL, *args],
                          capture_output=True, text=True, env=env)


class TestInstallReplaces(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kitinst-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.new = os.path.join(self.dir, "NEW.PRG")
        with open(self.new, "wb") as f:
            f.write(NEW)

    def sdfs(self):
        img = atr.ATRImage(256, 720)
        fs = atr.Sdfs.format(img, "TEST")
        fs.mkdir("GEM")
        fs.add_file("GEM>DESKTOP.PRG", OLD)
        p = os.path.join(self.dir, "sdfs.atr")
        img.save(p)
        return p

    def test_a_file_on_an_sdfs_disk_is_replaced(self):
        p = self.sdfs()
        before = atr.Sdfs(atr.ATRImage.load(p)).free_count()
        r = run(p, self.new, "GEM>DESKTOP.PRG")
        self.assertEqual(r.returncode, 0, r.stderr)
        fs = atr.Sdfs(atr.ATRImage.load(p))
        self.assertEqual(fs.read("GEM>DESKTOP.PRG"), NEW)
        self.assertEqual(fs.list("GEM").count("DESKTOP.PRG"), 1)
        self.assertEqual(fs.check(), [])
        # twenty sectors and a map out, two and a map in
        self.assertEqual(fs.free_count(), before + 20 - 2)

    def test_a_new_name_is_still_added(self):
        p = self.sdfs()
        r = run(p, self.new, "GEM>OTHER.PRG")
        self.assertEqual(r.returncode, 0, r.stderr)
        fs = atr.Sdfs(atr.ATRImage.load(p))
        self.assertEqual(sorted(fs.list("GEM")), ["DESKTOP.PRG", "OTHER.PRG"])
        self.assertEqual(fs.read("GEM>DESKTOP.PRG"), OLD)
        self.assertEqual(fs.check(), [])

    def test_a_file_on_a_dos_2_disk_is_replaced(self):
        img = atr.ATRImage(128, 720)
        fs = atr.Dos2.format(img)
        fs.add_file("AUTORUN.SYS", OLD)
        p = os.path.join(self.dir, "dos2.atr")
        img.save(p)
        r = run(p, self.new, "AUTORUN.SYS")
        self.assertEqual(r.returncode, 0, r.stderr)
        fs = atr.Dos2(atr.ATRImage.load(p))
        self.assertEqual(fs.read("AUTORUN.SYS"), NEW)
        self.assertEqual(fs.list().count("AUTORUN.SYS"), 1)


if __name__ == "__main__":
    unittest.main()
