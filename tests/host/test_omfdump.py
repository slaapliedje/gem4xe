"""tools/omfdump.py against an OMF segment this file builds byte by byte.

The tool exists to answer one question -- how much relocation information
an ORCA load file carries, and at what widths (docs/sdx-reloc.md) -- and
its answer is a set of COUNTS.  A census that silently miscounts is worse
than no census, and the records it has to get right are the compressed
ones: a SUPER record is a run-length list over 256-byte pages, so one
record can stand for hundreds of relocations and a reader that reports
"1 SUPER record" has said nothing at all.

So the fixture is built here with KNOWN numbers of each kind, and the
test requires those numbers back.  It needs no Apple II, no disk image
and no Golden Gate.
"""
import io
import struct
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import omfdump                                  # noqa: E402


def segment(body, segname=b"TEST", lablen=0, numlen=4, version=2):
    """One OMF v2 segment header wrapped round `body`."""
    name_at = 44                                # DISPNAME: after LOADNAME
    loadname = b" " * 10
    sname = bytes([len(segname)]) + segname if not lablen else segname.ljust(lablen)
    data_at = name_at + len(loadname) + len(sname)
    head = bytearray(data_at)
    head[13] = lablen
    head[14] = numlen
    head[15] = version
    struct.pack_into("<I", head, 16, 0x10000)   # BANKSIZE
    struct.pack_into("<H", head, 20, 0x0000)    # KIND: code
    struct.pack_into("<H", head, 34, 1)         # SEGNUM
    struct.pack_into("<H", head, 40, name_at)   # DISPNAME
    struct.pack_into("<H", head, 42, data_at)   # DISPDATA
    head[name_at:name_at + 10] = loadname
    head[name_at + 10:] = sname
    seg = bytes(head) + body
    struct.pack_into("<I", seg := bytearray(seg), 0, len(seg))   # BYTECNT
    struct.pack_into("<I", seg, 8, 0x100)                        # LENGTH
    return bytes(seg)


def super_record(kind, pages):
    """A SUPER record.  `pages` is a list: an int skips that many pages,
    a list of offsets patches them in the current page."""
    body = bytearray([kind])
    for p in pages:
        if isinstance(p, int):
            body.append(0x80 | (p - 1))
        else:
            body.append(len(p) - 1)
            body.extend(p)
    return bytes([omfdump.SUPER]) + struct.pack("<I", len(body)) + bytes(body)


class TestOmfDump(unittest.TestCase):
    def census(self, blob):
        path = Path(self.tmp) / "fixture.omf"
        path.write_bytes(blob)
        buf = io.StringIO()
        with redirect_stdout(buf):
            got = omfdump.dump(str(path), verbose=False)
        self.printed = buf.getvalue()
        return got

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def test_header_is_read(self):
        blob = segment(bytes([omfdump.END]), segname=b"here")
        self.census(blob)
        self.assertIn("'here'", self.printed)
        self.assertIn("OMF v2", self.printed)

    def test_lconst_is_skipped_not_scanned(self):
        """An LCONST holds the segment's IMAGE.  Every byte of it that
        happens to equal $F5 is a cRELOC opcode to a reader that forgot to
        skip the payload -- which is the whole failure mode this guards."""
        image = bytes([omfdump.cRELOC]) * 64
        body = (bytes([omfdump.LCONST]) + struct.pack("<I", len(image)) + image
                + bytes([omfdump.END]))
        got = self.census(segment(body))
        self.assertEqual(got.get("LCONST"), 1)
        self.assertNotIn("cRELOC", got)

    def test_creloc_counted_by_width(self):
        body = bytearray()
        for nbytes, count in ((2, 5), (3, 2), (1, 1)):
            for i in range(count):
                body += bytes([omfdump.cRELOC, nbytes, 0])
                body += struct.pack("<HH", i, i)
        body.append(omfdump.END)
        got = self.census(segment(bytes(body)))
        self.assertEqual(got["cRELOC"], 8)
        self.assertEqual(got["  cRELOC 2-byte"], 5)
        self.assertEqual(got["  cRELOC 3-byte"], 2)
        self.assertEqual(got["  cRELOC 1-byte"], 1)

    def test_super_patches_are_counted_individually(self):
        """THE POINT OF THE TOOL.  Three pages: four patches, a skipped
        page, then three more -- seven relocations in ONE record."""
        body = super_record(0, [[1, 2, 3, 4], 1, [10, 20, 30]])
        body += super_record(1, [[7, 8]])
        body += bytes([omfdump.END])
        got = self.census(segment(body))
        self.assertEqual(got["SUPER"], 2)
        self.assertEqual(got["  SUPER RELOC2"], 7)
        self.assertEqual(got["  SUPER RELOC3"], 2)

    def test_reloc_and_interseg(self):
        body = bytearray()
        body += bytes([omfdump.RELOC, 3, 0]) + struct.pack("<II", 0x10, 0x20)
        body += bytes([omfdump.INTERSEG, 3, 0]) + struct.pack("<IHHI", 0x30, 1, 2, 0)
        body.append(omfdump.END)
        got = self.census(segment(bytes(body)))
        self.assertEqual(got["  RELOC 3-byte"], 1)
        self.assertEqual(got["  INTERSEG 3-byte"], 1)

    def test_expression_records_are_walked(self):
        """An object file's relocations are unresolved EXPRs, and an
        expression is a postfix list ending in $00.  Getting its operand
        widths wrong walks off the end of the segment -- which is exactly
        what happened to the first version of this reader."""
        expr = (bytes([0x83, 4]) + b"~arr"          # label reference
                + bytes([0x81]) + struct.pack("<I", 3)   # constant, NUMLEN
                + bytes([0x01])                     # add
                + bytes([0x00]))                    # end
        body = bytes([omfdump.EXPR, 2]) + expr
        body += bytes([omfdump.LEXPR, 3]) + expr
        body += bytes([omfdump.END])
        got = self.census(segment(body))
        self.assertEqual(got["EXPR"], 1)
        self.assertEqual(got["LEXPR"], 1)

    def test_two_segments_both_reported(self):
        one = segment(bytes([omfdump.END]), segname=b"one")
        two = segment(bytes([omfdump.END]), segname=b"two")
        self.census(one + two)
        self.assertIn("2 segment(s)", self.printed)


if __name__ == "__main__":
    unittest.main()
