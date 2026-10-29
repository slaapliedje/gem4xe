#!/usr/bin/env python3
"""Host tests for the release floppy (tools/mkfloppy.py).

The release cannot carry gem-boot.atr, because it boots a DOS that is
not gem4xe's to give away; gem-sdx.atr is the floppy it can carry, and
what makes it so is what is NOT on it.  So the checks here are as much
about absence as presence: no boot file named in the superblock, the
blank disk's stub in the boot sectors, and otherwise exactly the card's
system -- tools/mkcf.py's SYSTEM table in \\GEM\\, the same AUTOEXEC.BAT,
and INSTALL.BAT, read back byte for byte -- on a geometry the machine's
drives and loaders read.  Its other half, gem-apps.atr, is the APPS
table on the same geometry, with an INSTALL.BAT of its own and nothing
that would boot.

Whether it BOOTS is `make test-boot`'s, under the SDX cartridge fixture.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr                                  # noqa: E402
import mkcf                                 # noqa: E402
import mkfloppy                             # noqa: E402

BUILD = os.path.join(ROOT, "build")


class TestFloppy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, _name in mkcf.SYSTEM:
            if not os.path.isfile(os.path.join(ROOT, path)):
                raise unittest.SkipTest(f"{path} is not built")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-floppy-")
        cls.out = os.path.join(cls.dir, "gem-sdx.atr")
        mkfloppy.build(cls.out)
        cls.img = atr.ATRImage.load(cls.out)
        cls.fs = atr.open_fs(cls.img)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_geometry_is_a_double_sided_double_density_floppy(self):
        """1440 sectors of 256 bytes, the first three of 128: what an
        XF551 writes and every SIO emulator and FAT loader reads."""
        self.assertEqual((self.img.sector_size, self.img.sector_count),
                         (256, 1440))
        self.assertTrue(self.img.boot_sectors_128)
        self.assertEqual(os.path.getsize(self.out), 16 + 3 * 128 + 1437 * 256)

    def test_it_is_an_sdfs_volume_called_gem4xe(self):
        self.assertIsInstance(self.fs, atr.Sdfs)
        self.assertEqual(self.fs.volname, "GEM4XE")

    def test_it_carries_only_its_own_dos(self):
        """The whole reason it can be given away: the DOS it boots is
        gem4xe's own read-only one (src/fdos.s), G4DOS.SYS, named as the
        superblock's boot file, and the boot sectors are src/fdboot.s --
        not somebody else's DOS."""
        g4 = next(e for e in self.fs.entries("") if e.filename == "G4DOS.SYS")
        self.assertEqual(self.fs.boot_file_map, g4.map)
        b1, b23, dos = mkfloppy.fdos_parts(ROOT)
        self.assertEqual(self.fs.read("G4DOS.SYS"), dos)
        self.assertEqual(self.img.read_sector(2) + self.img.read_sector(3),
                         b23 + bytes(256 - len(b23)))
        sb = self.img.read_sector(1)
        self.assertEqual(sb[48:48 + len(b1)], b1)
        self.assertEqual(sb[4] | sb[5] << 8, 0x0700)     # DOSINI
        names = {e.filename for e in self.fs.entries("")}
        self.assertFalse({n for n in names if n.endswith(".DOS")
                          or n.endswith(".SYS")} - {"G4DOS.SYS"}, names)

    def test_it_is_the_card_s_system(self):
        """Every file in tools/mkcf.py's SYSTEM table, in \\GEM\\, byte for
        byte -- and nothing else: no \\APPS\\ and no accessory, which are
        the other floppy's."""
        want = {}
        for path, name in mkcf.SYSTEM:
            with open(os.path.join(ROOT, path), "rb") as f:
                want[name] = f.read()
        for name, data in want.items():
            self.assertEqual(self.fs.read(name), data, name)
        on_disk = {f"GEM>{e.filename}" for e in self.fs.entries("GEM")}
        self.assertEqual(on_disk, set(want))
        root = {e.filename for e in self.fs.entries("")}
        self.assertEqual(root, {"GEM", "AUTOEXEC.BAT", "INSTALL.BAT",
                                "G4DOS.SYS"})

    def test_the_installer_is_mkcf_s(self):
        self.assertEqual(self.fs.read("INSTALL.BAT"),
                         mkcf.batch(mkcf.INSTALL_SYSTEM))

    def test_the_boot_file_is_the_card_s(self):
        self.assertEqual(self.fs.read("AUTOEXEC.BAT"),
                         b"".join(line.encode("ascii") + b"\x9b"
                                  for line in mkcf.BOOT))
        self.assertEqual(mkcf.BOOT, ["CD >GEM", "GEM"])

    def test_there_is_room_left_on_it(self):
        """A DESKTOP.INF, at least, and a program of somebody's own:
        the system is about 150 KB and the disk 360, so a hundred KB is
        the floor, and going under it means the system has grown past
        what a floppy is for (docs/shipping.md, section 1)."""
        free = self.fs.free_count() * (self.img.sector_size - 2)
        self.assertGreater(free, 100 * 1024, free)

    def test_the_command_line_adds_a_file(self):
        out = os.path.join(self.dir, "extra.atr")
        mkfloppy.main([out, "--add", "COPYING", "GEM>COPYING"])
        fs = atr.open_fs(atr.ATRImage.load(out))
        with open(os.path.join(ROOT, "COPYING"), "rb") as f:
            self.assertEqual(fs.read("GEM>COPYING"), f.read())


class TestAppsFloppy(unittest.TestCase):
    """gem-apps.atr: the applications and the accessory, the other half of
    the card's system partition, and not a boot disk."""

    @classmethod
    def setUpClass(cls):
        for path, _name in mkcf.APPS:
            if not os.path.isfile(os.path.join(ROOT, path)):
                raise unittest.SkipTest(f"{path} is not built")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-apps-")
        cls.out = os.path.join(cls.dir, "gem-apps.atr")
        mkfloppy.main([cls.out, "--apps"])
        cls.img = atr.ATRImage.load(cls.out)
        cls.fs = atr.open_fs(cls.img)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_geometry_is_the_system_floppy_s(self):
        self.assertEqual((self.img.sector_size, self.img.sector_count),
                         (256, 1440))
        self.assertIsInstance(self.fs, atr.Sdfs)

    def test_it_carries_no_dos_and_does_not_boot(self):
        self.assertEqual(self.fs.boot_file_map, 0)
        root = {e.filename for e in self.fs.entries("")}
        self.assertNotIn("AUTOEXEC.BAT", root)
        self.assertEqual(root, set(mkcf.DIRS) | {"INSTALL.BAT"})

    def test_it_is_the_apps_table(self):
        want = {}
        for path, name in mkcf.APPS:
            with open(os.path.join(ROOT, path), "rb") as f:
                want[name] = f.read()
        for name, data in want.items():
            self.assertEqual(self.fs.read(name), data, name)
        on_disk = set()
        for d in mkcf.DIRS:
            on_disk.update(f"{d}>{e.filename}" for e in self.fs.entries(d))
        self.assertEqual(on_disk, set(want))

    def test_the_installer_is_mkcf_s(self):
        self.assertEqual(self.fs.read("INSTALL.BAT"),
                         mkcf.batch(mkcf.INSTALL_APPS))

    def test_the_two_tables_share_no_file(self):
        """Between them they are the card's system partition, once each."""
        system = {n for _p, n in mkcf.SYSTEM}
        apps = {n for _p, n in mkcf.APPS}
        self.assertFalse(system & apps)


if __name__ == "__main__":
    unittest.main()
