#!/usr/bin/env python3
"""A .car cartridge image: gem4xe on a flash cartridge.

    python3 tools/mkcar.py build/cart.elf build/gem4xe.car

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
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkxex                                            # noqa: E402

CART_TYPE_MAXFLASH_1M = 42
BANK = 8192
BANKS = 128
WINDOW = 0xA000                 # where a bank appears
BOOT_BANK = BANKS - 1           # 127: what RESET maps
ERASED = 0xFF


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


def image(boot, payload=()):
    """The whole ROM: payload from bank 0 up, boot in bank 127."""
    if len(payload) > BOOT_BANK:
        raise SystemExit(f"{len(payload)} payload banks, and only "
                         f"{BOOT_BANK} below the boot bank")
    rom = bytearray([ERASED]) * (BANK * BANKS)
    for i, b in enumerate(payload):
        rom[i * BANK:(i + 1) * BANK] = b.ljust(BANK, bytes([ERASED]))
    rom[BOOT_BANK * BANK:] = boot
    return bytes(rom)


def car(rom, cart_type=CART_TYPE_MAXFLASH_1M):
    return (b"CART" + struct.pack(">II", cart_type, sum(rom) & 0xFFFFFFFF)
            + b"\0\0\0\0" + rom)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[1:]))
    ap.add_argument("elf", help="the bootstrap, linked at $A000 (src/cart.scm)")
    ap.add_argument("out", help="where to write the .car")
    a = ap.parse_args(argv[1:])

    boot = bank_from_elf(a.elf)
    rom = image(boot)
    with open(a.out, "wb") as f:
        f.write(car(rom))
    used = sum(1 for i in range(BANKS)
               if rom[i * BANK:(i + 1) * BANK] != bytes([ERASED]) * BANK)
    print(f"{a.out}: AtariMax 1 Mbit (type {CART_TYPE_MAXFLASH_1M}), "
          f"{BANKS} banks of {BANK}, {used} used, boot in bank {BOOT_BANK}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
