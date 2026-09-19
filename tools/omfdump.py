#!/usr/bin/env python3
"""omfdump.py -- read Apple IIgs OMF and report what RELOCATIONS it carries.

WHY THIS IS IN A GEM PORT'S TREE.  docs/sdx-reloc.md asks whether gem4xe
could ship as a SpartaDOS X relocatable binary and answers "not with
Calypsi", because Calypsi's linker emits no relocations at all -- which is
why tools/mkg4a.py has to link the program three times and diff the bytes
that moved.  The same note names the counter-example: ORCA/C and the ORCA
linker produce OMF, a format with real relocation records, and an
OMF -> $FFFD/$FFF9 converter is therefore a CONCEIVABLE tool where a
Calypsi one is not.  This is the measurement behind that sentence: point
it at an ORCA object or executable and it says, by count and by width,
exactly what relocation information exists to convert.

It is a reader, not a converter.  What a converter would need -- a
two-byte target for a 16-bit fixup, a three-byte one for a 24-bit fixup,
and the promise that an address is never materialised as two separate
immediates (SDX Programming Guide 2.4) -- is precisely what the census
below reports.

The format is OMF 2.1 (Apple IIgs GS/OS Reference, Appendix F).  Only the
record kinds an ORCA toolchain emits are decoded; anything else is
reported by opcode so that an unknown record is loud rather than silent.

    python3 tools/omfdump.py FILE [FILE ...]
    python3 tools/omfdump.py --verbose FILE      # every relocation
"""
import struct
import sys

# Body opcodes (GS/OS Reference F-3).  A value of $01..$DF is a CONST of
# that many bytes rather than an opcode.
END, ALIGN, ORG, RELOC, INTERSEG, USING, STRONG = 0x00, 0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5
GLOBAL, GEQU, MEM, EXPR, ZEXPR, BEXPR, RELEXPR = 0xE6, 0xE7, 0xE8, 0xEB, 0xEC, 0xED, 0xEE
LOCAL, EQU, DS, LCONST, LEXPR, ENTRY = 0xEF, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4
cRELOC, cINTERSEG, SUPER = 0xF5, 0xF6, 0xF7

OPNAME = {END: "END", ALIGN: "ALIGN", ORG: "ORG", RELOC: "RELOC",
          INTERSEG: "INTERSEG", USING: "USING", STRONG: "STRONG",
          GLOBAL: "GLOBAL", GEQU: "GEQU", MEM: "MEM", EXPR: "EXPR",
          ZEXPR: "ZEXPR", BEXPR: "BEXPR", RELEXPR: "RELEXPR",
          LOCAL: "LOCAL", EQU: "EQU", DS: "DS", LCONST: "LCONST",
          LEXPR: "LEXPR", ENTRY: "ENTRY", cRELOC: "cRELOC",
          cINTERSEG: "cINTERSEG", SUPER: "SUPER"}

# SUPER record types (F-27): the compressed forms a linker emits for
# whole classes of fixup at once.
SUPER_KIND = {0: "SUPER RELOC2", 1: "SUPER RELOC3",
              2: "SUPER REFTO2 (interseg)", 3: "SUPER REFTO3 (interseg)"}
for _i in range(4, 14):
    SUPER_KIND[_i] = f"SUPER INTERSEG{_i - 3}"
SUPER_KIND[14] = "SUPER RELOC16"

SEG_KIND = {0x00: "code", 0x01: "data", 0x02: "jump table", 0x04: "pathname",
            0x08: "library dictionary", 0x10: "initialisation",
            0x11: "direct page/stack", 0x12: "dynamic"}


class Seg:
    pass


def read_header(b, at):
    """One OMF segment header.  Returns (Seg, offset of the body)."""
    s = Seg()
    (s.bytecnt, s.resspc, s.length) = struct.unpack_from("<III", b, at)
    s.lablen = b[at + 13]
    s.numlen = b[at + 14]
    s.version = b[at + 15]
    s.banksize = struct.unpack_from("<I", b, at + 16)[0]
    if s.version >= 2:
        s.kind = struct.unpack_from("<H", b, at + 20)[0]
        s.org = struct.unpack_from("<I", b, at + 24)[0]
        s.align = struct.unpack_from("<I", b, at + 28)[0]
        s.numsex = b[at + 32]
        s.segnum = struct.unpack_from("<H", b, at + 34)[0]
        s.entry = struct.unpack_from("<I", b, at + 36)[0]
        s.dispname = struct.unpack_from("<H", b, at + 40)[0]
        s.dispdata = struct.unpack_from("<H", b, at + 42)[0]
    else:                                   # v0/v1: KIND is a byte at 12
        s.kind = b[at + 12]
        s.org = struct.unpack_from("<I", b, at + 20)[0]
        s.align = struct.unpack_from("<I", b, at + 24)[0]
        s.numsex = b[at + 28]
        s.segnum = b[at + 29] if s.version == 1 else 0
        s.entry = struct.unpack_from("<I", b, at + 30)[0]
        s.dispname = struct.unpack_from("<H", b, at + 34)[0]
        s.dispdata = struct.unpack_from("<H", b, at + 36)[0]
    nm = at + s.dispname
    s.loadname = b[nm:nm + 10].rstrip(b" ").decode("latin-1")
    ln = s.lablen or 0
    if ln:
        s.segname = b[nm + 10:nm + 10 + ln].rstrip(b" ").decode("latin-1")
    else:                                   # variable-length: a length byte
        n = b[nm + 10]
        s.segname = b[nm + 11:nm + 11 + n].decode("latin-1")
    return s, at + s.dispdata


def label(b, at, lablen):
    """A label: fixed LABLEN bytes, or a length byte then the text."""
    if lablen:
        return b[at:at + lablen].rstrip(b" ").decode("latin-1"), at + lablen
    n = b[at]
    return b[at + 1:at + 1 + n].decode("latin-1"), at + 1 + n


def skip_expr(b, at, numlen):
    """An expression is postfix and ends with a $00 operator (GS/OS
    Reference F-16).  $01..$12 are the operators and carry no operand;
    $80 is the location counter; $81 is a constant of NUMLEN bytes;
    $82..$86 name a label; $87 is a relative offset of NUMLEN bytes."""
    while True:
        op = b[at]; at += 1
        if op == 0x00:
            return at
        if 0x01 <= op <= 0x12 or op == 0x80:
            continue
        if op == 0x81 or op == 0x87:
            at += numlen
        elif 0x82 <= op <= 0x86:
            _, at = label(b, at, 0)
        else:
            raise ValueError(f"unknown expression operator ${op:02X} at {at - 1}")


def dump(path, verbose=False):
    with open(path, "rb") as f:
        b = f.read()
    at, segs, total = 0, 0, {}
    print(f"{path}: {len(b)} bytes")
    while at < len(b):
        try:
            s, body = read_header(b, at)
        except (struct.error, IndexError):
            print(f"  (stopped: truncated header at {at})")
            break
        if s.bytecnt == 0 or at + s.bytecnt > len(b) + 16:
            print(f"  (stopped: implausible BYTECNT {s.bytecnt} at {at})")
            break
        segs += 1
        kind = SEG_KIND.get(s.kind & 0x1F, f"kind ${s.kind:04X}")
        print(f"  segment {s.segnum}: {s.segname!r} ({kind}) "
              f"OMF v{s.version}, length ${s.length:X}, "
              f"banksize ${s.banksize:X}, numlen {s.numlen}")
        counts, relocs = {}, []
        p = body
        end = at + s.bytecnt
        while p < end:
            op = b[p]; p += 1
            if op == END:
                break
            if 0x01 <= op <= 0xDF:                      # CONST
                counts["CONST"] = counts.get("CONST", 0) + 1
                p += op
                continue
            name = OPNAME.get(op, f"${op:02X}")
            counts[name] = counts.get(name, 0) + 1
            if op == LCONST:
                n = struct.unpack_from("<I", b, p)[0]; p += 4 + n
            elif op == DS:
                p += s.numlen
            elif op == ORG or op == ALIGN:
                p += s.numlen
            elif op == RELOC:
                nb, shift = b[p], b[p + 1]
                off = struct.unpack_from("<I", b, p + 2)[0]
                sub = struct.unpack_from("<i", b, p + 6)[0]
                relocs.append(("RELOC", nb, shift, off, sub))
                counts[f"  RELOC {nb}-byte"] = counts.get(f"  RELOC {nb}-byte", 0) + 1
                p += 2 + 2 * s.numlen
            elif op == cRELOC:
                nb, shift = b[p], b[p + 1]
                off = struct.unpack_from("<H", b, p + 2)[0]
                sub = struct.unpack_from("<H", b, p + 4)[0]
                relocs.append(("cRELOC", nb, shift, off, sub))
                counts[f"  cRELOC {nb}-byte"] = counts.get(f"  cRELOC {nb}-byte", 0) + 1
                p += 6
            elif op == INTERSEG:
                nb, shift = b[p], b[p + 1]
                off = struct.unpack_from("<I", b, p + 2)[0]
                relocs.append(("INTERSEG", nb, shift, off, 0))
                counts[f"  INTERSEG {nb}-byte"] = counts.get(f"  INTERSEG {nb}-byte", 0) + 1
                p += 2 + s.numlen + 2 + 2 + s.numlen
            elif op == cINTERSEG:
                nb, shift = b[p], b[p + 1]
                off = struct.unpack_from("<H", b, p + 2)[0]
                relocs.append(("cINTERSEG", nb, shift, off, 0))
                counts[f"  cINTERSEG {nb}-byte"] = counts.get(f"  cINTERSEG {nb}-byte", 0) + 1
                p += 7
            elif op == SUPER:
                n = struct.unpack_from("<I", b, p)[0]
                kindb = b[p + 4]
                # A SUPER record is a run-length list over 256-byte pages:
                # a byte with bit 7 set skips (N & $7F) + 1 pages, one with
                # it clear is followed by N + 1 one-byte offsets within the
                # current page (GS/OS Reference F-27).  Counting them is
                # the point of this tool -- these are where a linked ORCA
                # program keeps the BULK of its relocations, and a census
                # that stopped at "1 SUPER record" would say nothing.
                patches, q, page = 0, p + 5, 0
                while q < p + 4 + n:
                    c = b[q]; q += 1
                    if c & 0x80:
                        page += (c & 0x7F) + 1
                    else:
                        patches += c + 1
                        q += c + 1
                        page += 1
                kn = SUPER_KIND.get(kindb, f"SUPER type {kindb}")
                counts[f"  {kn}"] = counts.get(f"  {kn}", 0) + patches
                p += 4 + n
            elif op in (GLOBAL, GEQU, EQU, LOCAL, ENTRY):
                _, p = label(b, p, s.lablen)
                if op in (GLOBAL, LOCAL):
                    p += 3                   # length, type, private
                elif op in (GEQU, EQU):
                    p += 3
                    p = skip_expr(b, p, s.numlen)
                else:
                    p += s.numlen
            elif op in (EXPR, ZEXPR, BEXPR, LEXPR, RELEXPR):
                if op == RELEXPR:
                    p += 1 + s.numlen
                else:
                    p += 1
                p = skip_expr(b, p, s.numlen)
            elif op == USING or op == STRONG:
                _, p = label(b, p, s.lablen)
            elif op == MEM:
                p += 2 * s.numlen
            else:
                print(f"    ! unhandled opcode {name} at {p - 1}; stopping segment")
                break
        for k in sorted(counts):
            print(f"      {k:28s} {counts[k]}")
            total[k] = total.get(k, 0) + counts[k]
        if verbose:
            for kind_, nb, shift, off, sub in relocs:
                print(f"        {kind_:10s} {nb} byte(s) shift {shift:4d} "
                      f"at ${off:06X} <- ${sub & 0xFFFFFFFF:06X}")
        at += s.bytecnt
    print(f"  {segs} segment(s)")
    return total


def main(argv):
    verbose = "--verbose" in argv or "-v" in argv
    files = [a for a in argv if not a.startswith("-")]
    if not files:
        print(__doc__.strip().splitlines()[-3].strip())
        return 2
    grand = {}
    for f in files:
        for k, v in dump(f, verbose).items():
            grand[k] = grand.get(k, 0) + v
        print()
    if len(files) > 1:
        print("total:")
        for k in sorted(grand):
            print(f"  {k:30s} {grand[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
