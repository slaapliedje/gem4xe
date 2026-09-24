#!/usr/bin/env python3
"""Host tests for the distribution (tools/mkdist.py).

The artefact is what a tester is handed, and its README is the only
thing standing between them and a machine that boots as a 6502 and
refuses.  Two halves of that page are generated -- what the desktop's
menu offers and what it offers disabled, and what is really on each
disk image -- so what is checked here is that the generation is honest:
every menu item lands in exactly one of the two lists, the files the
page names are the files on the images, and nothing is left unfilled.

The disks themselves are checked by `make test-boot`, which boots them.

THE PROSE HALF IS CHECKED TOO, NOW.  The generated halves stayed true for
phases on end while the hand-written "what is not there yet" bullets
rotted: the page was still promising a machine with one VDI driver and no
`DESKTOP.INF` after both had been built.  So the claims that name a thing
in the tree are tied to the tree -- if the printer device exists the page
may not say there is none, and if the ANTIC driver is in the product the
page may not say VBXE is required.  A claim nothing checks is a claim
that will be wrong eventually.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import atr                                  # noqa: E402
import deskrsc                              # noqa: E402
import mkcar                                # noqa: E402
import mkdist                               # noqa: E402

BUILD = os.path.join(ROOT, "build")


def built(name):
    return os.path.isfile(os.path.join(BUILD, name))


class TestDistribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for src, _ in mkdist.SYSTEM:
            if not built(src):
                raise unittest.SkipTest(f"build/{src} is not built")
        cls.dir = tempfile.mkdtemp(prefix="gem4xe-dist-")
        cls.out = os.path.join(cls.dir, "gem4xe-test")
        cls.made, cls.missing = mkdist.build(cls.out)
        with open(os.path.join(cls.out, "README.md")) as f:
            cls.page = f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    # -- the prose half, against the tree ----------------------------
    def src(self, *parts):
        with open(os.path.join(ROOT, *parts)) as f:
            return f.read()

    def test_the_page_does_not_deny_a_device_the_product_has(self):
        """src/vdi/vdidev.h's table is the list of devices; the page may
        not say there is one driver when there are three."""
        mk = self.src("Makefile")
        for obj, name, denial in (
                ("build/dev_print.o", "printer",
                 "there is one VDI driver"),
                ("build/dev_antic.o", "ANTIC", "VBXE** | required")):
            if obj in mk:
                self.assertNotIn(
                    denial, self.page,
                    f"the {name} device is linked into GEM.COM and the "
                    f"page still says {denial!r}")

    def test_the_page_says_the_printer_is_there_and_undriven(self):
        """Both halves of it: the device exists, and nothing clicks it.
        When a Print item appears in the desktop's resource this fails,
        which is the point -- the page will need rewriting that day."""
        if "build/dev_print.o" not in self.src("Makefile"):
            self.skipTest("no printer device in this tree")
        self.assertRegex(self.page, r"PRINTER=|PRINTTO=",
                         "the page does not mention the printer's config keys")
        rsc = self.src("tools", "deskrsc.py")
        has_print = re.search(r'"[^"]*\bPrint\b', rsc)
        self.assertFalse(
            has_print and "nothing prints yet" in self.page,
            "the desktop's resource has a Print item now, so the page's "
            "'nothing prints yet' is stale")

    def test_the_page_does_not_deny_a_desktop_inf(self):
        """src/desk/ writes one (test-m19 reads it back), so the page may
        not say nothing is written."""
        if "INF_REV_LEVEL" not in self.src("src", "desk", "desk.h"):
            self.skipTest("no DESKTOP.INF in this tree")
        self.assertNotIn(
            "nothing is written to a `DESKTOP.INF` yet", self.page,
            "the desktop writes a DESKTOP.INF and the page denies it")

    def test_the_page_warns_about_the_emulator_s_cpu_bugs(self):
        """tools/altirra/ carries a patch for two 65C816 core faults that
        hit the PRODUCT, not just the gates.  A page that hands out an
        Altirra command line has to say so."""
        patch = os.path.join(ROOT, "tools", "altirra",
                             "altirra-65c816-native-mode.patch")
        if not os.path.exists(patch):
            self.skipTest("the CPU patch is gone: upstream took it?")
        self.assertIn("AltirraSDL", self.page)
        self.assertRegex(
            self.page, r"pull request #88|tools/altirra",
            "the page gives an Altirra command line and never mentions "
            "that its 65C816 core needs the patch in tools/altirra/")

    def test_the_source_travels_with_the_binaries(self):
        """GPL section 3 wants the source alongside or a written offer,
        and there is no repository to point at, so it goes in the box.
        It must also be the RIGHT source, which is why mkdist refuses a
        dirty tree -- see test_a_dirty_tree_is_refused."""
        tarball = os.path.join(self.out, "src", "gem4xe-src.tar.gz")
        self.assertTrue(os.path.isfile(tarball),
                        "the distribution carries no source tarball")
        import tarfile
        with tarfile.open(tarball) as t:
            names = t.getnames()
        self.assertGreater(len(names), 100,
                           f"the source tarball holds only {len(names)} entries")
        for want in ("src/vdi/vdi.c", "src/aes/event.c", "COPYING",
                     "docs/licence.md", "Makefile"):
            self.assertTrue(any(n.endswith("/" + want) for n in names),
                            f"the source tarball is missing {want}")

    def test_the_version_is_written_down_for_a_bug_report(self):
        """Both numbers: the release, which is what the About box shows,
        and the date and commit, which identify the build."""
        import deskrsc
        with open(os.path.join(self.out, "VERSION")) as f:
            v = f.read().strip()
        self.assertRegex(v, r"^\S+ \(\d{4}-\d{2}-\d{2}-")
        self.assertTrue(v.startswith(deskrsc.VERSION + " "),
                        f"the dist says {v!r}, which does not start with "
                        f"the VERSION file's {deskrsc.VERSION!r}")
        self.assertIn(v.split(" (")[1].rstrip(")"), self.page,
                      "VERSION and the page's stamp disagree")

    def test_the_about_box_shows_the_same_version(self):
        """ONE place: tools/deskrsc.py reads the VERSION file, so the
        resource the desktop loads and the number in the dist cannot
        drift.  tools/deskref.py's model reads the same list, which is
        what keeps the pixel gates honest across a version bump."""
        import deskrsc
        with open(os.path.join(ROOT, "VERSION")) as f:
            want = f.read().strip()
        self.assertEqual(deskrsc.VERSION, want)
        line = [t for t, x, y in deskrsc.ABOUT if t.startswith("version ")]
        self.assertEqual(line, ["version " + want],
                         f"the About box's version line is {line}")
        # ...and it is centred, since its length moves with the version
        self.assertEqual(deskrsc.VERSION_X,
                         (deskrsc.ABOUT_W - len(line[0])) // 2)

    def test_a_dirty_tree_is_refused(self):
        """The check itself, by reading mkdist rather than by dirtying
        the tree: a release whose source does not match its binaries is
        worse than no release."""
        with open(os.path.join(ROOT, "tools", "mkdist.py")) as f:
            src = f.read()
        self.assertIn('endswith("-dirty")', src,
                      "mkdist no longer refuses to package a dirty tree")

    def test_the_page_has_nothing_left_unfilled(self):
        """A template placeholder that survives into the artefact is a
        hole in the page nobody would notice until a tester read it."""
        self.assertNotRegex(self.page, r"\{[a-z_]+\}")

    def test_the_system_files_are_there_and_are_this_tree_s(self):
        for src, name in mkdist.SYSTEM:
            with open(os.path.join(BUILD, src), "rb") as f:
                want = f.read()
            with open(os.path.join(self.out, "system", name), "rb") as f:
                self.assertEqual(f.read(), want, name)
            self.assertIn(f"`{name}`", self.page)

    def test_every_disk_this_tree_built_is_in_it(self):
        for src, dest, _kind, _prose in mkdist.DISKS:
            if not built(src):
                continue
            p = os.path.join(self.out, dest)
            self.assertTrue(os.path.isfile(p), dest)
            self.assertEqual(os.path.getsize(p),
                             os.path.getsize(os.path.join(BUILD, src)))
            self.assertIn(f"`{dest}`", self.page)

    def test_the_page_lists_the_files_that_are_really_on_the_images(self):
        """Read back independently of the tool that wrote the page."""
        for src, dest, kind, _prose in mkdist.DISKS:
            if kind is None or not built(src):
                continue
            path = os.path.join(self.out, dest)
            if kind == "car":
                # Not an ATR at all: a packed cartridge ROM, whose
                # directory is read the way the machine reads it -- the
                # handler at a fixed offset in the boot bank, and
                # cd_dir's place inside it from the linker.
                _t, ok, _used, names = mkcar.read_car(
                    path, os.path.join(mkdist.BUILD, "cartd.elf"))
                self.assertTrue(ok, f"{dest}: the checksum in the header is "
                                    f"not the sum of the ROM")
            elif kind == "dos2":
                names = [e.filename
                         for e in atr.Dos2(atr.ATRImage.load(path)).entries()
                         if e.in_use]
            else:
                names = [e.filename
                         for e in atr.Sdfs(atr.ATRImage.load(path)).entries("")]
            # by its heading: another disk's prose may name this one first
            section = self.page.split(f"### `{dest}`")[1].split("###")[0]
            for n in names:
                self.assertIn(f"`{n}", section, f"{dest} holds {n} and the "
                              f"page does not say so")

    def test_every_menu_item_is_in_exactly_one_of_the_two_lists(self):
        """The half of the page that says what works, and the half that
        says what does not, are generated from the same menu; an item in
        neither would be a quiet omission."""
        items = mkdist.menu_items()
        works = self.page.split("## What works")[1].split("## What is not")[0]
        notyet = self.page.split("## What is not there yet")[1]
        self.assertTrue(items)
        for _idx, label, enabled in items:
            here, there = (works, notyet) if enabled else (notyet, works)
            self.assertIn(f"**{label}**", here, label)
            self.assertNotIn(f"**{label}**", there, label)

    def test_the_disabled_list_is_the_resource_s_own(self):
        items = {idx for idx, _l, enabled in mkdist.menu_items()
                 if not enabled}
        self.assertEqual(items, set(deskrsc.NOT_YET))

    def test_the_kit_travels_with_it(self):
        tgz = os.path.join(self.out, "sdk", "gem4xe-sdk.tar.gz")
        self.assertTrue(os.path.isfile(tgz))
        self.assertGreater(os.path.getsize(tgz), 8192)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "COPYING")))

    def test_a_disk_this_tree_cannot_build_is_said_to_be_missing(self):
        """The fixtures are not always here, and the artefact must say
        which disks it does not have rather than quietly omit them."""
        out = os.path.join(self.dir, "gem4xe-missing")
        disks = mkdist.DISKS
        try:
            mkdist.DISKS = disks + [("no-such.atr", "disks/no-such.atr",
                                     None, "not built here")]
            mkdist.build(out)
        finally:
            mkdist.DISKS = disks
        with open(os.path.join(out, "README.md")) as f:
            page = f.read()
        self.assertIn("is not in this build", page)
        self.assertFalse(os.path.exists(os.path.join(out, "disks",
                                                     "no-such.atr")))

    def test_the_release_leaves_the_third_party_dos_at_home(self):
        """`make release` is the public download: the floppies boot a DOS
        that is not gem4xe's to give away (fixtures.toml.example), so
        they stay out and the page says so -- and the install-by-hand
        recipe that replaces them is read from the card's own layout."""
        import mkcf
        out = os.path.join(self.dir, "gem4xe-public")
        mkdist.build(out, public=True)
        with open(os.path.join(out, "README.md")) as f:
            page = f.read()
        for src, dest, _kind, _prose in mkdist.DISKS:
            p = os.path.join(out, dest)
            if src in mkdist.THIRD_PARTY_DOS:
                self.assertFalse(os.path.exists(p), f"{dest} is in the release")
                self.assertIn(f"`{dest}`", page, f"the page does not say "
                              f"{dest} was left out")
            elif built(src):
                self.assertTrue(os.path.isfile(p), dest)
        self.assertIn("not gem4xe's to give away", page)
        self.assertNotIn("--disk disks/gem-boot.atr", page)
        self.assertNotIn("not for redistribution", page)
        self.assertNotRegex(page, r"\{[a-z_]+\}")
        for _path, name in mkcf.SYSTEM + mkcf.APPS:
            d, n = name.split(">")
            self.assertRegex(page, rf"`{n}`[^;]*into\s+`\\{d}\\`",
                             f"the recipe does not put {n} in \\{d}\\")
        # ...and the tester's build still has what the tree built
        self.assertIn("--disk disks/gem-boot.atr", self.page)
        self.assertNotIn("not gem4xe's to give away", self.page)

    def test_the_release_carries_the_floppy_that_has_no_dos(self):
        """gem-sdx.atr (tools/mkfloppy.py) is the one floppy the release
        can carry, and the page has to say what boots it -- SpartaDOS X,
        from a cartridge it does not include -- and where that comes
        from, without pretending the download is self-sufficient."""
        if not built("gem-sdx.atr"):
            self.skipTest("build/gem-sdx.atr is not built")
        out = os.path.join(self.dir, "gem4xe-public-floppy")
        mkdist.build(out, public=True)
        with open(os.path.join(out, "README.md")) as f:
            page = f.read()
        p = os.path.join(out, "disks", "gem-sdx.atr")
        self.assertTrue(os.path.isfile(p))
        fs = atr.open_fs(atr.ATRImage.load(p))
        self.assertEqual(fs.boot_file_map, 0, "the release floppy names a DOS")
        self.assertIn("--cart SDX.car --disk disks/gem-sdx.atr", page)
        self.assertIn("https://sdx.atari8.info/", page)
        self.assertIn("does not include", page)
        section = page.split("### `disks/gem-sdx.atr`")[1].split("###")[0]
        self.assertIn("no DOS", section)
        self.assertIn("`GEM\\` (", section)
        self.assertIn("`INSTALL.BAT`", section)
        self.assertNotIn("`APPS\\` (", section)
        # ...and its other half, the applications, which carries no DOS
        # either and so travels with it
        if built("gem-apps.atr"):
            self.assertTrue(os.path.isfile(os.path.join(out, "disks",
                                                        "gem-apps.atr")))
            apps = page.split("### `disks/gem-apps.atr`")[1].split("###")[0]
            self.assertIn("`APPS\\` (", apps)
            self.assertIn("`INSTALL.BAT`", apps)

    def test_the_zip_is_the_tarball_s_tree(self):
        """The same files, the same bytes, the same top-level name:
        a Windows user and a Linux user unpack the same thing."""
        import tarfile
        import zipfile
        out = os.path.join(self.dir, "gem4xe-both")
        tgz, zp = out + ".tar.gz", out + ".zip"
        mkdist.build(out, tar=tgz, zip_path=zp)
        with tarfile.open(tgz) as t:
            tar_files = {m.name: t.extractfile(m).read()
                         for m in t.getmembers() if m.isfile()}
        with zipfile.ZipFile(zp) as z:
            zip_files = {i.filename: z.read(i) for i in z.infolist()
                         if not i.is_dir()}
        self.assertEqual(set(tar_files), set(zip_files))
        for name, data in tar_files.items():
            self.assertEqual(zip_files[name], data, name)
        self.assertTrue(all(n.startswith("gem4xe-both/") for n in zip_files))
        self.assertIn("gem4xe-both/README.md", zip_files)
        self.assertIn("gem4xe-both/system/GEM.COM", zip_files)


if __name__ == "__main__":
    unittest.main()
