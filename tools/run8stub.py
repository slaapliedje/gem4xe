#!/usr/bin/env python3
"""The stub that runs a plain Atari program after GEM on DOS 2 and MyDOS
(src/run8.s, docs/run8-plan.md step 2), as a C array GEM.COM carries.

    python3 tools/run8stub.py build/run8.elf build/run8_stub.h

GEM copies it to $0400 as its last act and fills in its header: the
DOS's own DOSVEC, the program's name and GEM's.  Two parts, joined here:
what has to outlive the program or the cartridge, $0400-$057F, and what
runs once before either, $0580-$05FF.  The offsets of those
are fixed by src/run8.s's first lines, and this checks the link against
them -- a header that moved would have GEM write a name over the code.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkxex                                      # noqa: E402

AT = 0x0400
GO = 0x0580                         # BASIC's line buffer: what runs once
ROOM = GO - AT                      # what outlives a program or a cartridge
GO_ROOM = 0x0600 - GO
FIELDS = (("r8_dos", 3), ("r8_prog", 5), ("r8_gem", 53))
PROG_LEN, GEM_LEN = 48, 20


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__.strip().split("\n\n")[1])
    segs, syms = mkxex.read_elf(argv[1])
    code = dict(segs)
    if set(code) != {AT, GO}:
        raise SystemExit(f"{argv[1]}: segments at {sorted(hex(a) for a in code)}, "
                         f"not ${AT:04X} and ${GO:04X}")
    if syms.get("r8_go") != GO:
        raise SystemExit(f"{argv[1]}: r8_go at {syms.get('r8_go')!r}, not ${GO:04X}")
    if len(code[AT]) > ROOM or len(code[GO]) > GO_ROOM:
        raise SystemExit(f"{argv[1]}: {len(code[AT])} and {len(code[GO])} bytes, more "
                         f"than the {ROOM} and {GO_ROOM} there is room for")
    # one image from $0400, the gap to $0580 zero
    data = code[AT] + bytes(GO - AT - len(code[AT])) + code[GO]
    for name, off in FIELDS:
        if syms.get(name) != AT + off:
            raise SystemExit(f"{argv[1]}: {name} at {syms.get(name)!r}, not "
                             f"${AT + off:04X} -- src/run8.s's header moved")
    if syms["r8_gem"] - syms["r8_prog"] != PROG_LEN:
        raise SystemExit(f"{argv[1]}: the program's name is not {PROG_LEN} bytes")
    if syms["r8_gem"] + GEM_LEN > syms["r8_end"]:
        raise SystemExit(f"{argv[1]}: GEM's name runs past the stub's end")
    rows = [", ".join(f"0x{b:02X}" for b in data[i:i + 12])
            for i in range(0, len(data), 12)]
    with open(argv[2], "w") as f:
        f.write(f"/* {argv[2]} -- written by tools/run8stub.py from {argv[1]}:\n"
                f" * src/run8.s, which GEM copies to ${AT:04X} to run a plain Atari\n"
                f" * program on DOS 2 or MyDOS and then itself again. */\n")
        f.write(f"#define R8_AT       0x{AT:04X}\n")
        f.write(f"#define R8_LEN      {len(data)}\n")
        for name, off in FIELDS:
            f.write(f"#define {name.upper():<11} {off}\n")
        f.write(f"#define R8_PROGLEN  {PROG_LEN}\n")
        f.write(f"#define R8_GEMLEN   {GEM_LEN}\n")
        f.write("static const uint8_t FAR r8_stub[R8_LEN] = {\n    ")
        f.write(",\n    ".join(rows))
        f.write("\n};\n")
    print(f"{argv[2]}: {len(code[AT])} bytes at ${AT:04X} ({ROOM - len(code[AT])} spare), "
          f"{len(code[GO])} at ${GO:04X} ({GO_ROOM - len(code[GO])} spare)")


if __name__ == "__main__":
    main(sys.argv)
