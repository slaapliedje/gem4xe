#!/usr/bin/env python3
"""A control panel extension's file: its header, then its .G4A.

    mkcpx.py HEADER.cpxh MODULE.g4a OUT.cpx

The panel lists a module from the 512 bytes in front of it, as XControl
does, so nothing has to be run to be listed (docs/cpanel-plan.md, step
1).  The header is src/app/cpx.h's map, which is Atari's offsets --
little-endian here, since the AES and the panel read it as native words.

THE HEADER IS WRITTEN AS TEXT beside the module, so an icon is drawn in
an editor and reviewed in a diff:

    # comment
    id       GENL           four characters
    version  1.00           -> $0100, as XControl shows it
    flags    bootinit       any of setonly, bootinit, resident; or none
    title    General        title_txt, 17 characters at most
    text     General        i_text, under the icon, 13 at most
    icolor   0x1000         the ICONBLK's ib_char word (default)
    tcolor   0x1180         the TEDINFO's te_color word (default: Atari's)
    icon                    then 24 rows of 32, '#' set and '.' clear
    ................................

The two colour words are the GEM words XControl hands straight to its
slot's objects (its SLOTS.C), not bit-fields.
"""
import sys

MAGIC = 0x6811                  # src/app/cpx.h CPX_MAGIC
SIZE = 512
FLAGS = {"setonly": 0x0001, "bootinit": 0x0002, "resident": 0x0004}
ICON_W, ICON_H = 32, 24

# src/app/cpx.h's map
OFF_MAGIC, OFF_FLAGS, OFF_ID, OFF_VERSION = 0, 2, 4, 8
OFF_ITEXT, OFF_ICON, OFF_ICOLOR = 10, 24, 120
OFF_TITLE, OFF_TCOLOR, OFF_BUFFER = 122, 140, 142
LEN_ITEXT, LEN_TITLE, LEN_BUFFER = 14, 18, 64


class SpecError(Exception):
    pass


def parse(text, name="header"):
    """The fields of a .cpxh, as a dict; SpecError for anything wrong."""
    spec = {"flags": 0, "icolor": 0x1000, "tcolor": 0x1180}
    rows = None
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].rstrip() if rows is None else line.strip()
        if rows is not None:
            if line:
                rows.append(line)
            continue
        if not line:
            continue
        key, _, val = line.partition(" ")
        val = val.strip()
        if key == "icon":
            rows = []
        elif key == "id":
            if len(val) != 4 or not val.isascii():
                raise SpecError(f"{name}:{n}: id is four characters, not {val!r}")
            spec["id"] = val
        elif key == "version":
            major, _, minor = val.partition(".")
            if not (major.isdigit() and minor.isdigit()
                    and len(major) <= 2 and len(minor) == 2):
                raise SpecError(f"{name}:{n}: version is like 1.00, not {val!r}")
            spec["version"] = (int(major, 16) << 8) | int(minor, 16)
        elif key == "flags":
            bits = 0
            for f in val.replace(",", " ").split():
                if f != "none" and f not in FLAGS:
                    raise SpecError(f"{name}:{n}: no flag {f!r}")
                bits |= FLAGS.get(f, 0)
            spec["flags"] = bits
        elif key in ("title", "text"):
            most = (LEN_TITLE if key == "title" else LEN_ITEXT) - 1
            if not val or len(val) > most or not val.isascii():
                raise SpecError(f"{name}:{n}: {key} is 1 to {most} characters")
            spec[key] = val
        elif key in ("icolor", "tcolor"):
            spec[key] = int(val, 0) & 0xFFFF
        else:
            raise SpecError(f"{name}:{n}: no field {key!r}")
    for need in ("id", "version", "title", "text"):
        if need not in spec:
            raise SpecError(f"{name}: no {need}")
    if rows is None:
        raise SpecError(f"{name}: no icon")
    if len(rows) != ICON_H or any(len(r) != ICON_W or set(r) - set("#.")
                                  for r in rows):
        raise SpecError(f"{name}: the icon is {ICON_H} rows of {ICON_W} '#' or '.'")
    spec["icon"] = rows
    return spec


def icon_bytes(rows):
    """A row is four bytes, most significant bit the leftmost pixel --
    how the rest of the system's bitmaps are laid out (tools/rsc.py)."""
    out = bytearray()
    for r in rows:
        for x0 in range(0, ICON_W, 8):
            v = 0
            for x in range(8):
                if r[x0 + x] == "#":
                    v |= 0x80 >> x
            out.append(v)
    return bytes(out)


def header(spec):
    h = bytearray(SIZE)
    h[OFF_MAGIC:OFF_MAGIC + 2] = MAGIC.to_bytes(2, "little")
    h[OFF_FLAGS:OFF_FLAGS + 2] = spec["flags"].to_bytes(2, "little")
    # a LONG of the four characters, first in the high byte, as the ST
    # writes 'GENL'; stored as the 65816 stores a LONG
    h[OFF_ID:OFF_ID + 4] = int.from_bytes(spec["id"].encode(), "big").to_bytes(4, "little")
    h[OFF_VERSION:OFF_VERSION + 2] = spec["version"].to_bytes(2, "little")
    h[OFF_ITEXT:OFF_ITEXT + len(spec["text"])] = spec["text"].encode()
    h[OFF_ICON:OFF_ICON + 96] = icon_bytes(spec["icon"])
    h[OFF_ICOLOR:OFF_ICOLOR + 2] = spec["icolor"].to_bytes(2, "little")
    h[OFF_TITLE:OFF_TITLE + len(spec["title"])] = spec["title"].encode()
    h[OFF_TCOLOR:OFF_TCOLOR + 2] = spec["tcolor"].to_bytes(2, "little")
    return bytes(h)


def read(blob):
    """A header back out of a .cpx's first 512 bytes, for tests and gates;
    None if it is not one."""
    if len(blob) < SIZE or int.from_bytes(blob[0:2], "little") != MAGIC:
        return None
    w = lambda o: int.from_bytes(blob[o:o + 2], "little")
    z = lambda o, n: blob[o:o + n].split(b"\0")[0].decode("latin-1")
    return {
        "flags": w(OFF_FLAGS),
        "id": int.from_bytes(blob[OFF_ID:OFF_ID + 4], "little").to_bytes(4, "big").decode("latin-1"),
        "version": w(OFF_VERSION),
        "text": z(OFF_ITEXT, LEN_ITEXT),
        "icon": blob[OFF_ICON:OFF_ICON + 96],
        "icolor": w(OFF_ICOLOR),
        "title": z(OFF_TITLE, LEN_TITLE),
        "tcolor": w(OFF_TCOLOR),
        "buffer": blob[OFF_BUFFER:OFF_BUFFER + LEN_BUFFER],
    }


def main(argv):
    if len(argv) != 4:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    spec_path, g4a_path, out = argv[1:]
    try:
        spec = parse(open(spec_path).read(), spec_path)
    except SpecError as e:
        print(f"mkcpx: {e}", file=sys.stderr)
        return 1
    g4a = open(g4a_path, "rb").read()
    if g4a[:3] != b"G4A":
        print(f"mkcpx: {g4a_path} is not a .g4a", file=sys.stderr)
        return 1
    with open(out, "wb") as f:
        f.write(header(spec) + g4a)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
