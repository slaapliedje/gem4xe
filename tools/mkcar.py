#!/usr/bin/env python3
"""A .car cartridge image: gem4xe on a flash cartridge.

    python3 tools/mkcar.py build/cart.elf build/gem4xe-sys.car \
        --dev build/cartd.elf --system

WHY A CARTRIDGE.  The release's own disk answers BOOT ERROR on its own --
it carries no DOS by design and wants SpartaDOS X in the machine -- so
"download one file and look at it" does not work today.  A cartridge
needs no DOS (docs/cartridge.md says why read-only makes that true), and
a flash cartridge is one file.

THE FORMAT is sixteen bytes and then the ROM:

    0   'CART'
    4   the type, big-endian: 42 is AtariMax 1 Mbit
    8   the checksum, big-endian: the sum of every ROM byte, as a 32-bit
        quantity that is allowed to wrap
    12  four zero bytes
    16  the ROM itself

Altirra checks the checksum unless it is zero, so it is written properly
rather than left out.

THE LAYOUT.  128 banks of 8 KB, mapped one at a time at $A000-$BFFF.
**Bank 127 is the one the machine comes up on** (Altirra,
kATCartridgeMode_MaxFlash_1024K: InitBank(127, -1, 127)), so the
bootstrap goes there and the payload goes below it.  Getting that
backwards produces a cartridge that is perfectly valid and does nothing,
which is why it is stated here rather than remembered.

Unused banks are filled with $FF, which is what an erased flash part
reads as -- so the image matches what the hardware would hold, and a
bank that was never written is obvious in a dump.

WHAT GOES ON IT.  `--system` is the product: every file the release's
loose `system/` folder carries, taken from tools/mkdist.py's own table
rather than listed again here -- see system(), and the four times this
project has shipped a second list that drifted.  `--file` adds one by
hand, which is what the gate's fixtures use, and `--test-banks` fills
the payload with a pattern instead, for the staging check.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkxex                                            # noqa: E402
import mkdist                                           # noqa: E402

BUILD = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))

CART_TYPE_MAXFLASH_1M = 42
BANK = 8192
BANKS = 128
WINDOW = 0xA000                 # where a bank appears
BOOT_BANK = BANKS - 1           # 127: what RESET maps
ERASED = 0xFF

# Where the D: handler rides in the boot bank, and how much of it the
# bootstrap copies down.  A FIXED offset rather than one the packer
# chooses, so src/cart.s can name it as a constant: the bootstrap is
# linked into $A000-$AFFF (src/cart.scm) and this is the page after it.
DEV_AT = 0x1000                 # within the bank, so $B000 in the window
DEV_ROOM = 0x0800               # 2 KB, which the packer checks it into
DEV_ORG = 0x0700                # where it is linked and copied to
# ...behind a four-byte header, 'C' 'D' and the length, so the bootstrap
# can tell a cartridge that HAS a handler from one that does not.  Erased
# flash reads as $FF and the first image without one had the bootstrap
# copy 2 KB of it to $0700 and CALL it -- which survived by luck.
DEV_MAGIC = b"CD"
DEV_HDR = 4

ENT_SIZE = 16                   # src/cartd.s says what the fields are
MAX_FILES = 24
# DOS 2's drive bitmap, which src/sys/gemdos.c's Drvmap returns verbatim.
# The handler owns the byte (src/cartd.s, cd_drvbyt) because on a machine
# with no DOS nothing else does, and the desktop would otherwise draw an
# icon per bit of whatever instruction was linked there.  Checked here
# rather than trusted: it is right only if the linker put `devhead` first.
DRVBYT = 0x070A


def bank_from_elf(path):
    """The 8 KB the linker placed at $A000-$BFFF, as one bank.

    The ELF carries only the bytes that were used, so the gaps are
    filled -- including the run up to the six-byte header at $BFFA,
    which is at the very top and would otherwise leave the bank short.
    """
    img = bytearray([ERASED]) * BANK
    wrote = 0
    segs, _syms = mkxex.read_elf(path)
    for addr, data in segs:
        if not (WINDOW <= addr and addr + len(data) <= WINDOW + BANK):
            raise SystemExit(
                f"{path}: a segment at ${addr:04X}+{len(data)} is outside the "
                f"cartridge window ${WINDOW:04X}-${WINDOW + BANK - 1:04X}")
        img[addr - WINDOW:addr - WINDOW + len(data)] = data
        wrote += len(data)
    if not wrote:
        raise SystemExit(f"{path}: nothing in the cartridge window")
    # The six the OS reads.  A cartridge whose $BFFC is not 0 is not a
    # cartridge as far as the machine is concerned, and the failure is a
    # machine that boots straight past it -- silence, not an error.
    if img[BANK - 4] != 0:
        raise SystemExit(f"{path}: $BFFC is ${img[BANK - 4]:02X}, not 0 -- "
                         f"the OS will not see a cartridge here")
    return bytes(img)


def test_pattern(bank):
    """One payload bank of something no accident produces.

    Step two moves banks out of the cartridge and into far memory, and
    the only question is whether every byte arrived where it was aimed.
    A constant would not notice two banks staged in the wrong order, and
    a counter would not notice a bank staged twice, so each byte depends
    on BOTH its offset and its bank.
    """
    return bytes(((i * 7 + bank * 61 + 0x5A) & 0xFF) for i in range(BANK))


def entry(name, bank, page, length):
    """One sixteen-byte directory entry, in src/cartd.s's shape.

    The name is split at the dot and each half space-padded, which is
    the form the handler compares in -- it normalises a spec into this
    shape once rather than teaching the compare loop about dots.
    """
    base, _, ext = name.upper().partition(".")
    if len(base) > 8 or len(ext) > 3:
        raise SystemExit(f"{name}: a D1: name is eight and three")
    if length >= 1 << 24:
        raise SystemExit(f"{name}: {length} bytes is past a three-byte length")
    return (base.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")
            + bytes([bank, page,
                     length & 0xFF, (length >> 8) & 0xFF, length >> 16]))


def lay_out(files):
    """(payload banks, directory entries) for `files`, page aligned.

    PAGE ALIGNED because the entry carries a PAGE and not an offset:
    one byte instead of two, at a cost of under 256 bytes a file.  A
    file runs on across bank boundaries from there, which is what the
    handler's read loop walks.
    """
    rom, dirent = bytearray(), []
    for name, data in files:
        while len(rom) % 256:
            rom.append(ERASED)
        bank, page = divmod(len(rom), BANK)
        dirent.append(entry(name, bank, page // 256, len(data)))
        rom += data
    if len(dirent) > MAX_FILES:
        raise SystemExit(f"{len(dirent)} files, and src/cartd.s has room "
                         f"for {MAX_FILES}")
    banks = [bytes(rom[i:i + BANK]) for i in range(0, len(rom), BANK)]
    return banks, dirent


def device(elf, dirent):
    """The D: handler, with its directory filled in.

    The handler is linked at $0700 and travels as bytes; the two places
    the packer has to reach are public symbols, so this patches what the
    linker placed rather than knowing where it put it.
    """
    segs, syms = mkxex.read_elf(elf)
    for k in ("cd_dir", "cd_dirlen", "cd_end", "cd_drvbyt"):
        if k not in syms:
            raise SystemExit(f"{elf}: no {k} -- is it still .public?")
    lo = min(a for a, _d in segs)
    if lo != DEV_ORG:
        raise SystemExit(f"{elf}: linked at ${lo:04X}, not ${DEV_ORG:04X}")
    if syms["cd_drvbyt"] != DRVBYT:
        raise SystemExit(
            f"{elf}: cd_drvbyt is at ${syms['cd_drvbyt']:04X}, not DOS 2's "
            f"DRVBYT at ${DRVBYT:04X} -- the desktop reads that address for "
            f"its list of drives, so `devhead` has to be the first section "
            f"in src/cartd.scm")
    blob = bytearray([0]) * (max(a + len(d) for a, d in segs) - lo)
    for a, d in segs:
        blob[a - lo:a - lo + len(d)] = d
    blob[syms["cd_dirlen"] - lo] = len(dirent)
    at = syms["cd_dir"] - lo
    for i, e in enumerate(dirent):
        blob[at + i * ENT_SIZE:at + (i + 1) * ENT_SIZE] = e
    if len(blob) + DEV_HDR > DEV_ROOM:
        raise SystemExit(f"{elf}: {len(blob)} bytes, and there is "
                         f"{DEV_ROOM - DEV_HDR} for it")
    return bytes(blob)


def image(boot, payload=(), dev=b""):
    """The whole ROM: payload from bank 0 up, boot and the handler in 127."""
    if len(payload) > BOOT_BANK:
        raise SystemExit(f"{len(payload)} payload banks, and only "
                         f"{BOOT_BANK} below the boot bank")
    rom = bytearray([ERASED]) * (BANK * BANKS)
    for i, b in enumerate(payload):
        rom[i * BANK:(i + 1) * BANK] = b.ljust(BANK, bytes([ERASED]))
    rom[BOOT_BANK * BANK:] = boot
    if dev:
        at = BOOT_BANK * BANK + DEV_AT
        hdr = DEV_MAGIC + bytes([len(dev) & 0xFF, len(dev) >> 8])
        rom[at:at + DEV_HDR + len(dev)] = hdr + dev
    return bytes(rom)


def car(rom, cart_type=CART_TYPE_MAXFLASH_1M):
    return (b"CART" + struct.pack(">II", cart_type, sum(rom) & 0xFFFFFFFF)
            + b"\0\0\0\0" + rom)


def system():
    """What the release's loose `system/` folder holds, as (NAME, path).

    NOT A LIST OF ITS OWN, and that is the point.  This project has had
    the same bug four times -- a second list of what ships, drifting out
    of step with the first, and every gate booting a DISK so that a wrong
    FOLDER was invisible to all of them.  The control panel was missing
    from the release for two versions that way.  So the cartridge carries
    mkdist.SYSTEM, which is the flat list a directory-less D1: wants
    anyway, and a file added there is on the cartridge with nothing else
    touched.
    """
    return [(name, os.path.join(BUILD, src)) for src, name in mkdist.SYSTEM]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[1:]))
    if "--sources" in argv:             # what the Makefile depends on
        print(" ".join(p for _n, p in system()))
        return 0
    ap.add_argument("elf", help="the bootstrap, linked at $A000 (src/cart.scm)")
    ap.add_argument("out", help="where to write the .car")
    ap.add_argument("--test-banks", type=int, default=0, metavar="N",
                    help="fill N payload banks with test_pattern(), which is "
                         "what test-m37 stages and checks")
    ap.add_argument("--dev", metavar="CARTD.ELF",
                    help="the read-only D: handler, linked at $0700")
    ap.add_argument("--file", nargs=2, action="append", default=[],
                    metavar=("NAME", "PATH"),
                    help="a file to put on D1:, as NAME.EXT")
    ap.add_argument("--system", action="store_true",
                    help="put the whole of tools/mkdist.py's SYSTEM on D1: -- "
                         "GEM.COM and everything the release's system/ folder "
                         "holds, so the cartridge boots into the desktop")
    ap.add_argument("--sources", action="store_true",
                    help="print what --system would read, for a Makefile, and "
                         "stop")
    a = ap.parse_args(argv[1:])

    boot = bank_from_elf(a.elf)

    if a.test_banks and (a.file or a.system):
        raise SystemExit("--test-banks fills the payload with a pattern and "
                         "--file/--system fill it with files; pick one")
    dev, files = b"", []
    if a.test_banks:
        banks = [test_pattern(i) for i in range(a.test_banks)]
    else:
        for name, path in (system() if a.system else []) + a.file:
            with open(path, "rb") as f:
                files.append((name, f.read()))
        banks, dirent = lay_out(files)
        if a.dev:
            dev = device(a.dev, dirent)
        elif files:
            raise SystemExit("--file wants --dev: without the handler there "
                             "is nothing to read the files with")
    rom = image(boot, banks, dev)
    with open(a.out, "wb") as f:
        f.write(car(rom))
    used = sum(1 for i in range(BANKS)
               if rom[i * BANK:(i + 1) * BANK] != bytes([ERASED]) * BANK)
    print(f"{a.out}: AtariMax 1 Mbit (type {CART_TYPE_MAXFLASH_1M}), "
          f"{BANKS} banks of {BANK}, {used} used, boot in bank {BOOT_BANK}"
          + (f", D1: with {len(files)} file(s)" if dev else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
