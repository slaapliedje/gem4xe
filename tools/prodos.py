#!/usr/bin/env python3
"""prodos.py -- read and write files on a ProDOS volume image (.po/.hdv).

Just enough ProDOS for the Spectre GS gates: list a directory, read a file,
and put a file (replacing one of the same name) with its file type and aux
type.  The image is a plain run of 512-byte blocks in ProDOS order, which is
what MAME's apple2gs takes as a hard disk (.hdv) and what a .po is.

    prodos.py ls  IMAGE [/SYSTEM]
    prodos.py get IMAGE /SYSTEM/START OUT
    prodos.py put IMAGE /SYSTEM/START IN --type 0xB3 [--aux 0xDB07]

Storage types handled: 1 seedling, 2 sapling, 3 tree (data), 5 extended
(data + resource fork) for reading and freeing; files are written as
seedling, sapling or tree as their size needs.  Paths are case-blind and
'/'-separated, starting below the volume.  Reference: Beneath Apple ProDOS
and the ProDOS 8 Technical Reference, chapter B (file organization).
"""
import argparse
import struct
import sys

BLK = 512


class Volume:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.img = bytearray(f.read())
        hdr = self.block(2)
        if hdr[4] >> 4 != 0xF:
            raise SystemExit(f"{path}: block 2 is not a volume directory")
        self.total = struct.unpack_from("<H", hdr, 0x29)[0]
        self.bitmap = struct.unpack_from("<H", hdr, 0x27)[0]

    def block(self, n):
        return self.img[n * BLK:(n + 1) * BLK]

    def write_block(self, n, data):
        assert len(data) <= BLK
        self.img[n * BLK:(n + 1) * BLK] = bytes(data).ljust(BLK, b"\0")

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.img)

    # -- the free-block bitmap: a 1 bit is a FREE block ------------------
    def _bit(self, n):
        byte = self.bitmap * BLK + n // 8
        return byte, 0x80 >> (n % 8)

    def is_free(self, n):
        byte, m = self._bit(n)
        return bool(self.img[byte] & m)

    def set_free(self, n, free):
        byte, m = self._bit(n)
        if free:
            self.img[byte] |= m
        else:
            self.img[byte] &= ~m & 0xFF

    def alloc(self):
        for n in range(self.total):
            if self.is_free(n):
                self.set_free(n, False)
                self.write_block(n, b"")
                return n
        raise SystemExit("volume full")

    # -- directories -----------------------------------------------------
    def entries(self, key):
        """Yield (block, offset, entry bytes) for each live entry of the
        directory whose key block is `key`."""
        hdr = self.block(key)           # only the key block's header says
        elen, per = hdr[0x23], hdr[0x24]    # how long an entry is
        b = key
        first = True
        while b:
            blk = self.block(b)
            nxt = struct.unpack_from("<H", blk, 2)[0]
            for i in range(per):
                off = 4 + i * elen
                if first and i == 0:
                    continue            # the directory header
                e = blk[off:off + elen]
                if len(e) == elen and e[0] >> 4:
                    yield b, off, e
            first = False
            b = nxt

    @staticmethod
    def name(e):
        return e[1:1 + (e[0] & 0x0F)].decode("ascii")

    def lookup(self, path):
        """(dir key block, entry block, offset, entry) or None for the
        last component; the directory must exist."""
        parts = [p for p in path.strip("/").split("/") if p]
        key = 2
        for i, p in enumerate(parts):
            hit = None
            for b, off, e in self.entries(key):
                if self.name(e).upper() == p.upper():
                    hit = (b, off, e)
                    break
            if i == len(parts) - 1:
                return key, hit
            if not hit or hit[2][0] >> 4 != 0xD:
                raise SystemExit(f"no directory {p} in {path}")
            key = struct.unpack_from("<H", hit[2], 0x11)[0]
        return 2, None

    # -- fork data -------------------------------------------------------
    def fork_blocks(self, storage, key):
        """Every block a fork occupies, index blocks included, and the data
        blocks in order (0 = a sparse hole)."""
        if storage == 1:
            return [key], [key]
        if storage == 2:
            idx = self.block(key)
            data = [idx[i] | idx[256 + i] << 8 for i in range(256)]
            return [key] + [d for d in data if d], data
        if storage == 3:
            mi = self.block(key)
            used, data = [key], []
            for j in range(128):
                s = mi[j] | mi[256 + j] << 8
                if not s:
                    data += [0] * 256
                    continue
                u, d = self.fork_blocks(2, s)
                used += u
                data += d
            return used, data
        raise SystemExit(f"storage type {storage} not handled")

    def read_fork(self, storage, key, eof):
        _, data = self.fork_blocks(storage, key)
        out = bytearray()
        for d in data:
            if len(out) >= eof:
                break
            out += self.block(d) if d else bytes(BLK)
        return bytes(out[:eof])

    def file_blocks(self, e):
        st = e[0] >> 4
        key = struct.unpack_from("<H", e, 0x11)[0]
        if st != 5:
            return self.fork_blocks(st, key)[0]
        ext = self.block(key)
        used = [key]
        for base in (0, 256):          # data fork, then resource fork
            s, k = ext[base], struct.unpack_from("<H", ext, base + 1)[0]
            if s:
                used += self.fork_blocks(s, k)[0]
        return used

    def read_file(self, e):
        st = e[0] >> 4
        key = struct.unpack_from("<H", e, 0x11)[0]
        if st == 5:
            ext = self.block(key)
            s, k = ext[0], struct.unpack_from("<H", ext, 1)[0]
            eof = ext[5] | ext[6] << 8 | ext[7] << 16
            return self.read_fork(s, k, eof)
        eof = e[0x15] | e[0x16] << 8 | e[0x17] << 16
        return self.read_fork(st, key, eof)

    def write_fork(self, data):
        """Write `data`; return (storage type, key block, blocks used)."""
        chunks = [data[i:i + BLK] for i in range(0, max(len(data), 1), BLK)]
        blocks = []
        for c in chunks:
            n = self.alloc()
            self.write_block(n, c)
            blocks.append(n)
        if len(blocks) == 1:
            return 1, blocks[0], 1

        def index(bl):
            n = self.alloc()
            idx = bytearray(BLK)
            for i, d in enumerate(bl):
                idx[i], idx[256 + i] = d & 0xFF, d >> 8
            self.write_block(n, idx)
            return n

        if len(blocks) <= 256:
            return 2, index(blocks), len(blocks) + 1
        subs = [index(blocks[i:i + 256]) for i in range(0, len(blocks), 256)]
        if len(subs) > 128:
            raise SystemExit("file too large for ProDOS")
        return 3, index(subs), len(blocks) + len(subs) + 1


def cmd_ls(v, path):
    key = 2
    if path.strip("/"):
        _, hit = v.lookup(path)
        if not hit or hit[2][0] >> 4 != 0xD:
            raise SystemExit(f"{path}: not a directory")
        key = struct.unpack_from("<H", hit[2], 0x11)[0]
    for _, _, e in v.entries(key):
        st = e[0] >> 4
        eof = e[0x15] | e[0x16] << 8 | e[0x17] << 16
        aux = struct.unpack_from("<H", e, 0x1F)[0]
        print(f"{v.name(e):16} type ${e[0x10]:02X} aux ${aux:04X} "
              f"storage {st:X} eof {eof}")


def cmd_put(v, path, data, ftype, aux):
    dkey, hit = v.lookup(path)
    if hit is None:
        raise SystemExit(f"{path}: not found (put only replaces, for now)")
    b, off, e = hit
    for n in v.file_blocks(e):
        v.set_free(n, True)
    st, key, used = v.write_fork(data)
    e = bytearray(e)
    e[0] = st << 4 | (e[0] & 0x0F)
    e[0x10] = ftype
    struct.pack_into("<H", e, 0x11, key)
    struct.pack_into("<H", e, 0x13, used)
    e[0x15:0x18] = len(data).to_bytes(3, "little")
    struct.pack_into("<H", e, 0x1F, aux)
    blk = bytearray(v.block(b))
    blk[off:off + len(e)] = e
    v.write_block(b, blk)
    v.save()
    print(f"{path}: {len(data)} bytes, type ${ftype:02X}, "
          f"storage {st}, {used} block(s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("op", choices=["ls", "get", "put"])
    ap.add_argument("image")
    ap.add_argument("path", nargs="?", default="/")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--type", type=lambda s: int(s, 0), default=0xB3)
    ap.add_argument("--aux", type=lambda s: int(s, 0), default=0)
    a = ap.parse_args()
    v = Volume(a.image)
    if a.op == "ls":
        cmd_ls(v, a.path)
    elif a.op == "get":
        _, hit = v.lookup(a.path)
        if not hit:
            raise SystemExit(f"{a.path}: not found")
        with open(a.file, "wb") as f:
            f.write(v.read_file(hit[2]))
    else:
        with open(a.file, "rb") as f:
            cmd_put(v, a.path, f.read(), a.type, a.aux)


if __name__ == "__main__":
    sys.exit(main())
