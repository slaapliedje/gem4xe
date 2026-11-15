#!/usr/bin/env python3
"""elfsym.py -- a Calypsi object's global symbols, listed or renamed.

    python3 tools/bsp6502/elfsym.py list OBJ [--section NAME]
    python3 tools/bsp6502/elfsym.py rename OBJ OUT --suffix __b [--section NAME]

Calypsi's objects are ELF32 with a machine number objcopy does not know,
so `objcopy --redefine-sym` refuses them.  The edit is a small one: the
symbol table points into a string table by offset, so a renamed symbol
gets its new name appended to a copy of that string table, placed at the
end of the file, and its st_name moved there.  Relocations refer to
symbols by index, which nothing here changes.

`list` prints the defined GLOBAL symbols, with --section only those in a
section of that name (a bank's code).  `rename` gives each of those the
suffix: F becomes F__b, and the veneer that keeps the name F switches the
bank and calls it (tools/bsp6502/veneers.py).
"""
import struct
import sys


class Elf:
    def __init__(self, data):
        self.d = bytearray(data)
        if self.d[:4] != b"\x7fELF" or self.d[4] != 1 or self.d[5] != 1:
            raise ValueError("not a little-endian ELF32 file")
        (self.shoff,) = struct.unpack_from("<I", self.d, 0x20)
        self.shentsize, self.shnum, self.shstrndx = struct.unpack_from("<HHH", self.d, 0x2E)
        self.sh = [self._shdr(i) for i in range(self.shnum)]
        names = self.sh[self.shstrndx]
        for s in self.sh:
            s["name_s"] = self._str(names, s["name"])

    def _shdr(self, i):
        o = self.shoff + i * self.shentsize
        f = struct.unpack_from("<10I", self.d, o)
        keys = ("name", "type", "flags", "addr", "offset", "size", "link", "info",
                "addralign", "entsize")
        s = dict(zip(keys, f))
        s["at"] = o
        return s

    def _str(self, sec, off):
        b = self.d[sec["offset"] + off: sec["offset"] + sec["size"]]
        return bytes(b[:b.index(0)]).decode("latin-1")

    def symtab(self):
        st = next(s for s in self.sh if s["type"] == 2)
        return st, self.sh[st["link"]]

    def symbols(self):
        st, strs = self.symtab()
        out = []
        for i in range(st["size"] // 16):
            o = st["offset"] + i * 16
            name, value, size, info, other, shndx = struct.unpack_from("<IIIBBH", self.d, o)
            out.append({"i": i, "at": o, "name": self._str(strs, name), "bind": info >> 4,
                        "shndx": shndx,
                        "section": self.sh[shndx]["name_s"] if 0 < shndx < self.shnum else None})
        return out

    def globals(self, section=None):
        return [s for s in self.symbols() if s["bind"] == 1 and s["shndx"] != 0
                and (section is None or s["section"] == section)]

    def rename(self, names, suffix):
        st, strs = self.symtab()
        table = bytearray(self.d[strs["offset"]: strs["offset"] + strs["size"]])
        done = []
        for s in self.symbols():
            if s["name"] in names and s["bind"] == 1 and s["shndx"] != 0:
                struct.pack_into("<I", self.d, s["at"], len(table))
                table += (s["name"] + suffix).encode("latin-1") + b"\0"
                done.append(s["name"])
        new_off = len(self.d)
        self.d += table
        struct.pack_into("<I", self.d, strs["at"] + 16, new_off)
        struct.pack_into("<I", self.d, strs["at"] + 20, len(table))
        return done


def main(argv):
    if len(argv) < 3 or argv[1] not in ("list", "rename"):
        print(__doc__)
        return 2
    sect = argv[argv.index("--section") + 1] if "--section" in argv else None
    e = Elf(open(argv[2], "rb").read())
    syms = e.globals(sect)
    if argv[1] == "list":
        for s in syms:
            print(s["name"], s["section"])
        return 0
    out = argv[3]
    suffix = argv[argv.index("--suffix") + 1] if "--suffix" in argv else "__b"
    e.rename({s["name"] for s in syms}, suffix)
    open(out, "wb").write(e.d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
