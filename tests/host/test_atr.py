"""The DOS 2 filesystem, and in particular double density.

Single and double density are the same filesystem with a different sector
size, and almost everything about them is shared -- which is exactly why
the differences are worth a test: the last three bytes of a sector mean
slightly different things, and getting either wrong makes a disk that
looks right in a directory listing and reads back rubbish.

  * the data is `sector size - 3` bytes, so 125 in single density and 253
    in double;
  * the sector link is the same three bytes in both -- the directory
    entry's number in the top six bits of the first, the next sector in
    the remaining ten;
  * but the byte count is a WHOLE byte in double density, because 253
    does not fit in seven bits, where a single-density disk leaves the
    top bit alone (DOS 1 used it to mean "last sector").

The rules are Altirra's ATDiskFSDOS2 (src/ATIO/source/diskfsdos2.cpp:
InitNew, GetSectorDataBytes, GetNextSector, WriteFile), which reads and
writes real disks; the numbers below -- 707 free on a fresh disk of
either density -- are what a real DOS reports for one.

tests/emu/product_boot.py is what proves a disk built this way boots.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from atr import ATRImage, Dos2, ATRError, enhance  # noqa: E402

SD, DD = 128, 256


def blank(sector_size, sectors=720):
    img = ATRImage(sector_size, sectors)
    return img, Dos2.format(img)


class Format(unittest.TestCase):
    def test_free_sectors(self):
        """A fresh disk has 707 free in either density: 720 less the boot
        sectors, the VTOC, the eight directory sectors and 720 itself."""
        for size in (SD, DD):
            with self.subTest(sector_size=size):
                img, fs = blank(size)
                self.assertEqual(fs.free_count(), 707)
                vtoc = img.read_sector(Dos2.VTOC)
                self.assertEqual(vtoc[0], 0x02)
                self.assertEqual(vtoc[1] | (vtoc[2] << 8), 707)
                self.assertEqual(vtoc[3] | (vtoc[4] << 8), 707)
                self.assertEqual(fs.list(), [])

    def test_data_bytes(self):
        for size, want in ((SD, 125), (DD, 253)):
            _, fs = blank(size)
            self.assertEqual(fs.data_bytes, want)

    def test_mydos_keeps_720(self):
        """MyDOS does not reserve sector 720, which is the one extra free
        sector its floppies report -- and how Altirra tells the two
        apart."""
        img, fs = blank(DD)
        self.assertFalse(fs.mydos)
        img2 = ATRImage(DD, 720)
        fs2 = Dos2.format(img2, mydos=True)
        self.assertEqual(fs2.free_count(), 708)
        self.assertTrue(Dos2(img2).mydos)

    def test_no_extended_volumes(self):
        with self.assertRaises(ATRError):
            Dos2.format(ATRImage(DD, 2048))


class RoundTrip(unittest.TestCase):
    def sizes(self, fs):
        n = fs.data_bytes
        return [1, n - 1, n, n + 1, 2 * n, 3 * n + 7, 40000]

    def test_write_read_delete(self):
        for size in (SD, DD):
            img, fs = blank(size)
            free = fs.free_count()
            for i, n in enumerate(self.sizes(fs)):
                with self.subTest(sector_size=size, bytes=n):
                    blob = bytes((i + j) & 0xFF for j in range(n))
                    ent = fs.add_file(f"F{i}.DAT", blob)
                    self.assertEqual(fs.read(f"F{i}.DAT"), blob)
                    want = max(1, (n + fs.data_bytes - 1) // fs.data_bytes)
                    self.assertEqual(ent.count, want)
                    free -= want
                    self.assertEqual(fs.free_count(), free)
            for i, _ in enumerate(self.sizes(fs)):
                fs.delete(f"F{i}.DAT")
            self.assertEqual(fs.free_count(), 707)
            self.assertEqual(fs.list(), [])

    def test_a_full_disk_is_refused(self):
        img, fs = blank(DD)
        with self.assertRaises(ATRError):
            fs.add_file("TOOBIG.DAT", b"x" * (708 * fs.data_bytes))


class SectorLinks(unittest.TestCase):
    """The three bytes at the end of every sector, read back by hand."""

    def link(self, img, sector):
        raw = img.read_sector(sector)
        n = len(raw)
        return raw[n - 3] >> 2, ((raw[n - 3] & 3) << 8) | raw[n - 2], raw[n - 1]

    def test_chain(self):
        for size in (SD, DD):
            with self.subTest(sector_size=size):
                img, fs = blank(size)
                n = fs.data_bytes
                ent = fs.add_file("CHAIN.DAT", b"a" * (2 * n + 5))
                self.assertEqual(ent.count, 3)
                fileno, nxt, used = self.link(img, ent.start)
                self.assertEqual(fileno, ent.index)
                self.assertEqual(used, n)          # a full sector
                self.assertNotEqual(nxt, 0)
                fileno, nxt2, used = self.link(img, nxt)
                self.assertEqual((fileno, used), (ent.index, n))
                fileno, last, used = self.link(img, nxt2)
                self.assertEqual((fileno, last, used), (ent.index, 0, 5))

    def test_double_density_count_uses_the_whole_byte(self):
        """253 has bit 7 set.  A reader that masked it off -- which is
        right in single density -- would lose 128 bytes of every full
        sector, and the file would come back short and wrong."""
        img, fs = blank(DD)
        blob = bytes(range(256)) * 4        # 1024 bytes: four full sectors and a bit
        ent = fs.add_file("FULL.DAT", blob)
        raw = img.read_sector(ent.start)
        self.assertEqual(raw[len(raw) - 1], 253)
        self.assertTrue(raw[len(raw) - 1] & 0x80)
        self.assertEqual(fs.read("FULL.DAT"), blob)

    def test_single_density_count_fits_in_seven_bits(self):
        img, fs = blank(SD)
        ent = fs.add_file("FULL.DAT", b"z" * 300)
        raw = img.read_sector(ent.start)
        self.assertEqual(raw[127], 125)
        self.assertFalse(raw[127] & 0x80)


class Enhanced(unittest.TestCase):
    def test_enhance_wants_single_density(self):
        img, _ = blank(DD)
        with self.assertRaises(ATRError):
            enhance(img)

    def test_enhance_of_a_blank_disk(self):
        img, fs = blank(SD)
        big = enhance(img)
        fs2 = Dos2(big)
        self.assertTrue(fs2.dos25)
        self.assertEqual(big.sector_count, Dos2.ED_SECTORS)
        # DOS 2.5's own number for a fresh enhanced disk
        self.assertEqual(fs2.free_count(), 1010)


class MyDOSExtendedLinks(unittest.TestCase):
    """A MyDOS volume over 1023 sectors -- the 1440-sector MyDOS 4.50
    fixture is one -- chains a file by EXTENDED links: the next sector's
    whole number, high byte first, and no directory number in the link;
    the file carries $04 in its flag.  The volume says so with a VTOC code
    above 2.  Altirra's ATDiskFSDOS2 (WriteFile's extFile, GetNextSector)
    is the rule, and the disk below is laid out by hand from it, not by
    Dos2, so the writer is not marking its own homework.

    Read as DOS 2 links, A's link to sector 1030 ($0406) is "file 1,
    sector 6" -- B's first sector.  That is the shape of what --sweep did
    to the MyDOS fixture: it followed other files' chains into DUP.SYS's
    sectors, freed them, and wrote AUTORUN.SYS over them, so Quit stalled
    reloading a DUP.SYS that was no longer there (docs/phase106.md)."""

    A_SECS = [4, 1030, 5]
    B_SECS = [6, 7]

    def volume(self):
        img = ATRImage(DD, 1440)
        bits = bytearray(b"\xff" * 181)
        used = [0, 1, 2, 3, 360] + list(range(361, 369)) + self.A_SECS + self.B_SECS
        for sec in used:
            bits[sec // 8] &= ~(0x80 >> (sec % 8)) & 0xFF
        vtoc = bytearray(256)
        vtoc[0] = 3                         # MyDOS, extended links
        vtoc[1], vtoc[2] = 1428 & 0xFF, 1428 >> 8
        free = sum(bin(b).count("1") for b in bits)
        vtoc[3], vtoc[4] = free & 0xFF, free >> 8
        vtoc[10:10 + 181] = bits
        img.write_sector(360, vtoc)
        self.data = {}
        d = bytearray(256)
        for k, (name, secs) in enumerate((("A       BIN", self.A_SECS),
                                          ("B       BIN", self.B_SECS))):
            body = bytes((k * 7 + i) & 0xFF for i in range(253 * len(secs) - 9))
            self.data[name[:1] + ".BIN"] = body
            d[k * 16:k * 16 + 5] = bytes([0x46, len(secs), 0, secs[0] & 0xFF, secs[0] >> 8])
            d[k * 16 + 5:k * 16 + 16] = name.encode()
            for i, sec in enumerate(secs):
                chunk = body[i * 253:(i + 1) * 253]
                nxt = secs[i + 1] if i + 1 < len(secs) else 0
                raw = bytearray(256)
                raw[:len(chunk)] = chunk
                raw[253], raw[254], raw[255] = nxt >> 8, nxt & 0xFF, len(chunk)
                img.write_sector(sec, raw)
        img.write_sector(361, d)
        return img

    def test_read(self):
        fs = Dos2(self.volume())
        self.assertTrue(fs.mydos)
        for name, body in self.data.items():
            self.assertEqual(fs.read(name), body, name)

    def test_delete_frees_its_own_sectors_only(self):
        img = self.volume()
        fs = Dos2(img)
        fs.delete("A.BIN")
        _, bits = fs._bitmap()
        for sec in self.A_SECS:
            self.assertTrue(fs._bit(bits, sec), f"sector {sec} of A not freed")
        for sec in self.B_SECS:
            self.assertFalse(fs._bit(bits, sec), f"B's sector {sec} freed with A")
        self.assertEqual(Dos2(img).read("B.BIN"), self.data["B.BIN"])

    def test_a_new_file_is_written_the_volume_s_way(self):
        img = self.volume()
        fs = Dos2(img)
        body = bytes(range(256)) * 3
        fs.add_file("C.BIN", body, above=1100)
        e = fs.find("C.BIN")
        self.assertEqual(e.flag & 0x04, 0x04)
        first = img.read_sector(e.start)
        nxt = (first[253] << 8) | first[254]
        self.assertGreater(nxt, 1023)       # the high byte is the number's
        self.assertEqual(Dos2(img).read("C.BIN"), body)

    def test_the_fixture_s_dos_survives_a_sweep(self):
        """The MyDOS 4.50 fixture itself, swept as build/gem-mydos.atr is,
        keeps DOS.SYS and DUP.SYS byte for byte."""
        try:
            import tomllib
            with open(os.path.join(ROOT, "fixtures.toml"), "rb") as f:
                src = tomllib.load(f)["dos"]["mydos"]
        except (OSError, KeyError):
            self.skipTest("no MyDOS fixture: [dos].mydos in fixtures.toml")
        if not os.path.exists(src):
            self.skipTest(f"{src} is not here")
        img = ATRImage.load(src)
        fs = Dos2(img)
        keep = {n: fs.read(n) for n in ("DOS.SYS", "DUP.SYS")}
        for e in fs.entries():
            if e.in_use and e.filename not in keep:
                fs.delete(e.filename)
        fs.compact()
        fs.add_file("AUTORUN.SYS", bytes(418 * 253))
        fs = Dos2(img)
        for n, body in keep.items():
            self.assertEqual(fs.read(n), body, f"{n} changed by the sweep")


if __name__ == "__main__":
    unittest.main()
