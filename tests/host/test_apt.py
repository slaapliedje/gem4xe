"""The APT partition table, and SDFS inside a partition.

A card image is not something a gate can boot yet (docs/shipping.md,
section 3: SpartaDOS X needs an IDE driver this project has no fixture
for), so what can be checked is that what we write is what the readers
expect.  The rules below are Altirra's `ATDecodePartitionTable`
(src/ATIO/source/partitiontable.cpp), which reads real APT disks, and
its own APT writer in blockdevdiskadapter.cpp: the protective MBR's type
byte and LBA, the 'APT' signature, the entry count, the sixteen-byte
entries, and the sector-size code that says a partition's sectors are
512 bytes and one to a block.

The SDFS half is Altirra's `ATDiskFSSDX2::InitNew` (diskfssdx2.cpp),
where a 512-byte volume differs from a floppy's: one boot sector rather
than three, a size byte of 1, and a boot header that loads at $0440.
"""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import apt                                   # noqa: E402
from atr import Sdfs, ATRError               # noqa: E402

MB = 1 << 20


def card(mb=16, sizes=(8 * MB // apt.BLOCK, 0)):
    img = apt.Image(mb * MB // apt.BLOCK)
    parts = apt.layout(img, list(sizes))
    apt.write_table(img, parts)
    return img, parts


class Table(unittest.TestCase):
    def test_protective_mbr(self):
        img, _ = card()
        mbr = img.read_block(0)
        self.assertEqual(mbr[0x1FE:0x200], b"\x55\xAA")
        self.assertEqual(mbr[0x1BE], 0x80)                  # bootable
        self.assertEqual(mbr[0x1C2], apt.MBR_TYPE_APT)      # $7F: foreign
        self.assertEqual(struct.unpack_from("<I", mbr, 0x1C6)[0], apt.APT_LBA)
        self.assertEqual(struct.unpack_from("<I", mbr, 0x1CA)[0],
                         img.blocks - apt.APT_LBA)

    def test_an_atari_booting_it_as_a_floppy_is_told(self):
        """The MBR's first 128 bytes, which an APT reader never reads, are
        an Atari boot record: ONE sector to $3000, never the 256 to $0000
        that two zero bytes meant -- which crashed the machine at the end
        of a long load -- and the message says what the image is."""
        img, _ = card()
        mbr = img.read_block(0)
        self.assertEqual(mbr[1], 1)                         # one sector
        self.assertEqual(mbr[2] | mbr[3] << 8, 0x3000)      # to $3000
        self.assertIn(apt.CARD_IMAGE_SAYS[0].encode("ascii"), mbr[:128])
        self.assertEqual(mbr[128:0x1BE], bytes(0x1BE - 128))  # nothing else

    def test_header(self):
        img, parts = card()
        tab = img.read_block(apt.APT_LBA)
        self.assertEqual(tab[1:4], b"APT")
        self.assertEqual(tab[5], 1 + len(parts))            # the header counts
        self.assertTrue(0 < tab[5] <= 32)                   # the parser's range
        self.assertLess(tab[6], 32)                         # next header index
        self.assertLess(tab[7], 32)                         # previous
        self.assertEqual(struct.unpack_from("<I", tab, 8)[0], 0)    # no next sector
        self.assertEqual(struct.unpack_from("<I", tab, 12)[0], 0)   # none before

    def test_entries(self):
        img, parts = card()
        tab = img.read_block(apt.APT_LBA)
        for i, p in enumerate(parts, start=1):
            e = tab[i * 16:(i + 1) * 16]
            with self.subTest(entry=i):
                self.assertEqual(e[0] & 0x03, apt.SIZE_512)
                self.assertFalse(e[0] & 0x80)               # not a reserved entry
                self.assertEqual(e[1], apt.TYPE_DOS)
                self.assertEqual(struct.unpack_from("<I", e, 2)[0], p.start)
                self.assertEqual(struct.unpack_from("<I", e, 6)[0], p.sector_count)
                pid = struct.unpack_from("<H", e, 10)[0]
                self.assertEqual(pid, i)
                self.assertNotIn(pid, (0x0000, 0xFFFF))     # reserved ids
                self.assertTrue(e[12] & apt.FLAG_AUTOMOUNT)
                self.assertFalse(e[12] & apt.FLAG_READONLY)

    def test_partitions_fit_and_do_not_overlap(self):
        img, parts = card()
        at = apt.HEADER_BLOCKS
        for p in parts:
            self.assertEqual(p.start, at)
            self.assertGreater(p.sector_count, 0)
            at += p.sector_count
        self.assertLessEqual(at, img.blocks)

    def test_read_back(self):
        img, parts = card()
        again = apt.read_table(img)
        self.assertEqual([(p.start, p.sector_count) for p in again],
                         [(p.start, p.sector_count) for p in parts])

    def test_fifteen_mapping_slots(self):
        img = apt.Image(64 * 1024)
        parts = apt.layout(img, [1024] * 15)
        apt.write_table(img, parts)                 # fifteen is allowed
        self.assertEqual(len(apt.read_table(img)), 15)
        with self.assertRaises(ATRError):
            apt.write_table(img, apt.layout(apt.Image(64 * 1024), [512] * 16))

    def test_a_partition_must_fit(self):
        img = apt.Image(1024)
        with self.assertRaises(ATRError):
            apt.Partition(img, 8, 2000)
        with self.assertRaises(ATRError):
            apt.layout(img, [2000])


class Volume(unittest.TestCase):
    """SDFS on a partition: 512-byte sectors, one to a block."""

    def setUp(self):
        self.img, self.parts = card()
        self.fs = Sdfs.format(self.parts[0], "GEM4XE")

    def test_superblock_is_a_512_byte_volume(self):
        sb = self.parts[0].read_sector(1)
        self.assertEqual(sb[1], 1)                  # one boot sector
        self.assertEqual(sb[31], 1)                 # the 512 code, not the size
        self.assertEqual(struct.unpack_from("<H", sb, 33)[0], 512)
        self.assertEqual(struct.unpack_from("<H", sb, 35)[0], (512 - 4) // 2)
        self.assertEqual(sb[2:6], bytes([0x00, 0x04, 0xE0, 0x07]))   # $0440, $07E0
        self.assertEqual(sb[6:9], bytes([0x4C, 0x40, 0x04]))         # JMP $0440
        self.assertEqual(sb[7], 0x40)               # what open_fs() looks for
        self.assertEqual(self.fs.volname, "GEM4XE")

    def test_files_and_directories(self):
        fs = self.fs
        free = fs.free_count()
        fs.mkdir("GEM")
        blob = bytes(range(256)) * 400              # 102,400 bytes
        fs.add_file("GEM>BIG.COM", blob)
        fs.add_file("AUTOEXEC.BAT", b"CD >GEM\x9bGEM\x9b")
        self.assertEqual(fs.read("GEM>BIG.COM"), blob)
        self.assertEqual(fs.list(), ["GEM", "AUTOEXEC.BAT"])
        self.assertEqual(fs.list("GEM"), ["BIG.COM"])
        self.assertLess(fs.free_count(), free)
        # 102,400 bytes is 200 sectors of 512, and the file's own map pages
        self.assertLessEqual(free - fs.free_count(), 200 + 8)

    def test_the_second_partition_is_its_own_volume(self):
        other = Sdfs.format(self.parts[1], "DOCS")
        self.fs.add_file("ONLY.TXT", b"x")
        self.assertEqual(other.volname, "DOCS")
        self.assertEqual(other.list(), [])
        self.assertEqual(Sdfs(self.parts[0]).list(), ["ONLY.TXT"])

    def test_it_survives_a_save_and_load(self):
        self.fs.add_file("HELLO.TXT", b"hello\x9b")
        path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "gem4xe-test-card.img")
        try:
            self.img.save(path)
            back = apt.Image.load(path)
            fs = Sdfs(apt.read_table(back)[0])
            self.assertEqual(fs.volname, "GEM4XE")
            self.assertEqual(fs.read("HELLO.TXT"), b"hello\x9b")
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
