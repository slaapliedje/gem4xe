#!/usr/bin/env python3
"""APT: the partition table SpartaDOS X reads on a hard disk or a CF card.

A floppy is one file system and nothing else.  A hard disk is a table of
partitions, and on this platform the table is Konrad Kokoszkiewicz's
**APT** -- what SpartaDOS X mounts as D1:, D2:, ... and what an SDX
FDISK writes.  This module lays one out, and reads one back, so a card
image can be built the way tools/mkspdisk.py builds a floppy.

The layout is Altirra's, read rather than remembered: its parser is
`ATDecodePartitionTable` (src/ATIO/source/partitiontable.cpp), which
reads real APT disks, and its writer is the header
`ATBlockDeviceDiskAdapter::ReadHeaderSector`
(src/Altirra/source/blockdevdiskadapter.cpp), which SDX mounts.

    LBA 0    a protective MBR.  One partition entry, type $7F ("unknown /
             foreign"), pointing at the APT table's own LBA -- so a PC
             that sees the card does not think it is empty and offer to
             format it.
    LBA 1    the APT table: sixteen-byte entries.  The first is the
             header ('APT' in bytes 1-3, the entry count in byte 5, the
             next and previous table sectors in 8-15); the rest describe
             partitions.  Entries 1..15 are the "mapping slots", which
             are the ones a DOS mounts as D1:..D15:.
    LBA 2-7  spare, so that a table that grows does not move the data.
    LBA 8+   the partitions themselves.

A card that also has to be a FAT volume -- an SD card in a SubCart or an
AVGCART, whose own file browser reads the first FAT partition in the
MBR and whose SIDE 2 emulation hands the whole card to the U1MB's PBI
BIOS -- keeps the same table, moved: the MBR's first entry is the FAT
partition, its second the type-$7F entry pointing at the table, and
the table and the APT partitions follow the FAT partition.  Which is
the layout an SDX FDISK leaves on such a card, and the one the PBI
BIOS reads back the same way -- through the $7F entry, wherever it
points (`write_table(..., apt_lba=, fat=)`, `layout(..., at=)`).

An entry says where a partition starts and how long it is IN BLOCKS of
512 bytes, and how the DOS's own sectors sit inside those blocks (byte
0, bits 0-1: 1 = 128, 2 = 256, 3 = 512, and bits 2-3 a packing mode).
This writes 512-byte sectors, one to a block, which is the simple case
-- and what SDFS wants on anything bigger than a floppy (tools/atr.py,
Sdfs.format).
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atr import Sdfs, ATRError, message_boot  # noqa: E402

BLOCK = 512
HEADER_BLOCKS = 8               # LBA 0-7: the MBR, the table, and room to grow
APT_LBA = 1
# What a card image says when it is mounted as a floppy and booted (the
# screen editor shows 38 columns).
CARD_IMAGE_SAYS = ["gem4xe: a card image, not a floppy.",
                   "Boot gem-sdx.atr instead."]
MBR_TYPE_APT = 0x7F             # the type byte a protective MBR gives the table
MBR_TYPE_FAT32 = 0x0C           # FAT32 with LBA addressing: the SD-card case
SIG = b"APT"

# byte 0 of a partition entry: the sector size, and how sectors pack into
# blocks.  512-byte sectors are one to a block and have no packing.
SIZE_512 = 0x03
TYPE_DOS = 0x00                 # byte 1: a DOS partition (SDFS lives here)
FLAG_AUTOMOUNT = 0x40           # byte 12
FLAG_READONLY = 0x80


class Image:
    """A raw hard disk or CF card image: `blocks` blocks of 512 bytes and
    no header of any kind, which is what the emulator's `harddisk` device
    and a real card reader both expect."""

    def __init__(self, blocks):
        if blocks < HEADER_BLOCKS + 1:
            raise ATRError(f"an image of {blocks} blocks has no room for a table")
        self.blocks = blocks
        self.data = bytearray(blocks * BLOCK)

    @classmethod
    def load(cls, path):
        blob = open(path, "rb").read()
        if len(blob) % BLOCK:
            raise ATRError(f"{path}: {len(blob)} bytes is not a whole number of blocks")
        img = cls(len(blob) // BLOCK)
        img.data[:] = blob
        return img

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.data)

    def read_block(self, n):
        if not 0 <= n < self.blocks:
            raise ATRError(f"block {n} outside 0..{self.blocks - 1}")
        return bytes(self.data[n * BLOCK:(n + 1) * BLOCK])

    def write_block(self, n, payload):
        if len(payload) > BLOCK:
            raise ATRError(f"block {n}: {len(payload)} > {BLOCK}")
        if not 0 <= n < self.blocks:
            raise ATRError(f"block {n} outside 0..{self.blocks - 1}")
        self.data[n * BLOCK:(n + 1) * BLOCK] = bytes(payload) + bytes(BLOCK - len(payload))

    def __repr__(self):
        return f"Image({self.blocks} x {BLOCK} = {self.blocks * BLOCK // (1 << 20)} MB)"


class Partition:
    """One partition of an Image, as a sector-addressed medium -- the
    interface tools/atr.py's file systems want (sector_size, sector_count,
    read_sector, write_sector, sector_len), so that Sdfs can format and
    fill a partition exactly as it fills a floppy.  Sectors are 512 bytes
    and one to a block, numbered from 1."""

    sector_size = BLOCK

    def __init__(self, img, start, count, name=""):
        if start < 1 or start + count > img.blocks:
            raise ATRError(f"partition {start}+{count} does not fit in {img!r}")
        self.img, self.start, self.sector_count, self.name = img, start, count, name

    def read_sector(self, n):
        return self.img.read_block(self._block(n))

    def write_sector(self, n, payload):
        self.img.write_block(self._block(n), payload)

    def sector_len(self, n):
        self._block(n)                  # for the range check
        return BLOCK

    def _block(self, n):
        if not 1 <= n <= self.sector_count:
            raise ATRError(f"sector {n} outside 1..{self.sector_count}")
        return self.start + n - 1

    def __repr__(self):
        mb = self.sector_count * BLOCK / (1 << 20)
        return (f"Partition({self.name or '?'}: block {self.start}, "
                f"{self.sector_count} x {BLOCK}, {mb:.1f} MB)")


def layout(img, sizes, at=HEADER_BLOCKS):
    """Partitions of `sizes` blocks each, laid end to end after the
    header -- or from `at`, for a table that does not sit at LBA 1.  A
    size of 0 takes what is left."""
    parts = []
    for i, n in enumerate(sizes):
        if not n:
            n = img.blocks - at
        parts.append(Partition(img, at, n, f"D{i + 1}"))
        at += n
    if at > img.blocks:
        raise ATRError(f"{at} blocks of partitions in an image of {img.blocks}")
    return parts


def write_table(img, parts, boot_drive=0, apt_lba=APT_LBA, fat=None):
    """The protective MBR and the APT table, for partitions already laid
    out.  Every partition is a mapping slot, so the DOS mounts them in
    order as D1:, D2:, and so on.  `fat` = (start, count) puts a FAT32
    partition in the MBR's first entry and the table's entry second --
    the SD-card layout in the header -- and `apt_lba` is then where the
    table sits, after the FAT partition."""
    if len(parts) > 15:
        raise ATRError(f"{len(parts)} partitions: entries 1-15 are the mapping slots")
    if apt_lba < 1 or apt_lba >= img.blocks:
        raise ATRError(f"a table at block {apt_lba} is outside {img!r}")
    mbr = bytearray(BLOCK)
    # The MBR's first 446 bytes are boot code for a PC and nothing to an
    # Atari's APT reader.  Its first 128 are an ATARI boot record here, for
    # the person who mounts the card image as a floppy -- which the OS then
    # read as 256 sectors to load at $0000, over zero page, and crashed at
    # the end of a long load (reported from AltirraSDL, 2026-10-29).  Now it
    # says what it is and waits.
    rec = message_boot(CARD_IMAGE_SAYS)
    mbr[:len(rec)] = rec
    off = 0x1BE
    if fat:
        start, count = fat
        if start < 1 or start + count > apt_lba:
            raise ATRError(f"a FAT partition {start}+{count} does not end before the table at {apt_lba}")
        mbr[off + 4] = MBR_TYPE_FAT32
        mbr[off + 8:off + 12] = struct.pack("<I", start)
        mbr[off + 12:off + 16] = struct.pack("<I", count)
        off += 16
    mbr[off] = 0x80                                     # the entry is bootable
    mbr[off + 4] = MBR_TYPE_APT
    mbr[off + 8:off + 12] = struct.pack("<I", apt_lba)
    mbr[off + 12:off + 16] = struct.pack("<I", img.blocks - apt_lba)
    mbr[0x1FE:0x200] = b"\x55\xAA"
    img.write_block(0, mbr)

    tab = bytearray(BLOCK)
    tab[0] = 0x00                       # rev 0, no metadata, fifteen slots
    tab[1:4] = SIG
    tab[4] = boot_drive
    tab[5] = 1 + len(parts)             # the header is an entry as well
    # bytes 6-15 stay zero: one table sector, no next and no previous
    for i, p in enumerate(parts, start=1):
        e = bytearray(16)
        e[0] = SIZE_512
        e[1] = TYPE_DOS
        e[2:6] = struct.pack("<I", p.start)
        e[6:10] = struct.pack("<I", p.sector_count)
        e[10:12] = struct.pack("<H", i)         # partition id; 0 and $FFFF are reserved
        e[12] = FLAG_AUTOMOUNT
        tab[i * 16:(i + 1) * 16] = e
    img.write_block(apt_lba, tab)


def read_fat(img):
    """The (start, count) of the MBR's FAT partition, or None: what an
    SD card's own browser will see, and what has to end before the table."""
    mbr = img.read_block(0)
    if mbr[0x1FE:0x200] != b"\x55\xAA":
        return None
    for off in range(0x1BE, 0x1FE, 16):
        if mbr[off + 4] in (MBR_TYPE_FAT32, 0x0B, 0x06, 0x0E):
            return struct.unpack_from("<II", mbr, off + 8)
    return None


def read_table(img):
    """The partitions an APT table describes, the way Altirra's
    ATDecodePartitionTable finds them: through the protective MBR if
    there is one, then the entries of the table sector.  Only the shape
    this module writes is understood -- one table sector, 512-byte
    sectors -- which is enough to check what was written and to tell a
    gate which drive is which."""
    mbr = img.read_block(0)
    lba = APT_LBA
    if mbr[0x1FE:0x200] == b"\x55\xAA":
        for off in range(0x1BE, 0x1FE, 16):
            if mbr[off + 4] == MBR_TYPE_APT:
                lba = struct.unpack_from("<I", mbr, off + 8)[0]
                break
        else:
            raise ATRError("the MBR has no APT partition")
    tab = img.read_block(lba)
    if tab[1:4] != SIG:
        raise ATRError(f"no APT signature at block {lba}")
    if struct.unpack_from("<I", tab, 8)[0] or struct.unpack_from("<I", tab, 12)[0]:
        raise ATRError("a table of more than one sector: not written here")
    out = []
    for i in range(1, tab[5]):
        e = tab[i * 16:(i + 1) * 16]
        if not e[0] & 0x03 or e[0] & 0x80:
            continue
        if (e[0] & 0x03) != SIZE_512:
            raise ATRError(f"entry {i} is not a 512-byte partition")
        start, count = struct.unpack_from("<I", e, 2)[0], struct.unpack_from("<I", e, 6)[0]
        out.append(Partition(img, start, count, f"D{i}"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="inspect an APT-partitioned image")
    ap.add_argument("image")
    ap.add_argument("path", nargs="?", default="", help="a directory to list, e.g. GEM")
    ap.add_argument("--drive", type=int, default=1, help="which partition (D1: by default)")
    a = ap.parse_args(argv)
    img = Image.load(a.image)
    parts = read_table(img)
    print(f"{a.image}: {img!r}, {len(parts)} partition(s)")
    fat = read_fat(img)
    if fat:
        print(f"  FAT partition: block {fat[0]}, {fat[1]} x {BLOCK}, {fat[1] * BLOCK / (1 << 20):.1f} MB")
    for p in parts:
        print(f"  {p!r}")
    p = parts[a.drive - 1]
    fs = Sdfs(p)
    print(f"D{a.drive}: volume {fs.volname!r}, {fs.free_count()} sectors free")
    for name in fs.list(a.path.upper()):
        print(f"    {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
