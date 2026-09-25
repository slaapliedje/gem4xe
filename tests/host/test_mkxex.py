"""The .xex packer, and in particular the far-code staging it emits.

What is being tested is a CONTRACT BETWEEN TWO FILES: tools/mkxex.py packs the
far image and cuts it into chunks, and src/farload.s unpacks them on the
target.  The model below is the second half of that contract written in
Python -- it loads a .xex the way DOS does and unpacks the way farload does,
written from farload.s rather than borrowed from mkxex.py's own checker -- so
a format mistake shows up here, in a second, instead of as a machine that
boots to nothing.

It is a model, not the article: it proves the FORMAT is right, not that the
65816 code is.  tests/emu/m6_farcode.py is what proves the code runs.
"""
import os
import random
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mkxex  # noqa: E402

RUNAD, INITAD = 0x02E0, 0x02E2


def load_xex(blob):
    """Load a .xex the way an Atari DOS loader does.

    Returns (memory, runad).  `memory` is a dict of 24-bit address -> byte, so
    that a write the loader could not have made -- anything outside bank $00 --
    would be visible rather than silently wrapped.

    INITAD is honoured after EVERY segment once it has been set, which is the
    more aggressive of the two readings DOSes take; the packer has to be
    correct under it.
    """
    assert blob[:2] == b"\xff\xff", "missing $FFFF magic"
    mem, initad, runad = {}, None, None
    i = 2
    while i < len(blob):
        start, end = struct.unpack_from("<HH", blob, i)
        i += 4
        if start == 0xFFFF:                      # an optional repeated magic
            continue
        if end < start:
            raise AssertionError(f"segment ${start:04X}-${end:04X} runs backwards")
        n = end - start + 1
        body = blob[i:i + n]
        assert len(body) == n, "segment runs off the end of the file"
        i += n
        for k, b in enumerate(body):
            mem[start + k] = b
        if start <= INITAD <= end:
            initad = mem[INITAD] | (mem[INITAD + 1] << 8)
        if start <= RUNAD <= end:
            runad = mem[RUNAD] | (mem[RUNAD + 1] << 8)
        if initad:
            farload_copy(mem)
    return mem, runad


def farload_copy(mem, hdr=None):
    """src/farload.s, in Python: unpack one staged chunk, then consume it."""
    hdr = SYMS["_fl_hdr"] if hdr is None else hdr
    src = SYMS["_fl_buf"]
    cnt = mem.get(hdr + 3, 0) | (mem.get(hdr + 4, 0) << 8)
    if not cnt:
        return
    dst = mem[hdr] | (mem[hdr + 1] << 8) | (mem[hdr + 2] << 16)
    # The loader runs its unpacker in the bank above the image, which it is
    # told before the first chunk (src/farload.s, fl_fastbank): it must be
    # there, and above everything this chunk writes.
    fast = mem.get(SYMS["fl_fastbank"])
    assert fast is not None, "a chunk arrived before fl_fastbank was set"
    assert fast > (dst + cnt - 1) >> 16, (
        f"the unpacker's bank ${fast:02X} is not above a chunk ending at "
        f"${dst + cnt - 1:06X}")

    def nxt():
        nonlocal src
        b = mem[src]
        src += 1
        return b

    def length(nib):
        n = nib
        if nib == 15:
            while True:
                b = nxt()
                n += b
                if b != 255:
                    break
        return n

    def run(mat, n):
        nonlocal dst, cnt
        for _ in range(n):
            mem[dst] = mem[mat]
            dst += 1
            mat += 1
            cnt -= 1
        return mat

    while cnt:
        tok = nxt()
        n = length(tok >> 4)
        src = run(src, n)                      # the literals, from the buffer
        if not cnt:
            break
        off = nxt() | (nxt() << 8)
        if off == 0:
            continue                           # no match: only literals
        n = length(tok & 15) + 4
        run(dst - off, n)
        assert src <= SYMS["_fl_end"], "read past the staging buffer"
    mem[hdr + 3] = mem[hdr + 4] = 0


SYMS = {"_fl_hdr": 0x8000, "_fl_buf": 0x8005, "_fl_end": 0x8005 + 0x1A00,
        "_fl_copy": 0x9A05, "fl_fastbank": 0x3F4C}


def rand(n, seed):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


class Tokens(unittest.TestCase):
    """pack() and unpack() are inverses, over every shape of the format."""

    def round_trip(self, data):
        packed = mkxex.join(mkxex.pack(data))
        self.assertEqual(mkxex.unpack(packed, len(data)), data)
        return packed

    def test_nothing(self):
        self.assertEqual(mkxex.pack(b""), [])

    def test_too_short_to_match(self):
        self.round_trip(b"abc")
        self.round_trip(b"abcabc")            # a 3-byte repeat is not a match

    def test_a_run_is_a_match_at_offset_one(self):
        packed = self.round_trip(b"\x00" * 1000)
        self.assertLess(len(packed), 12)

    def test_literal_extension_bytes(self):
        for n in (14, 15, 16, 269, 270, 271, 600):
            with self.subTest(n=n):
                self.round_trip(rand(n, n))

    def test_match_extension_bytes(self):
        for n in (18, 19, 20, 273, 274, 275, 1023, 1024, 1025, 5000):
            with self.subTest(n=n):
                data = rand(64, 7)
                data += data[:4] * (n // 4 + 1)  # a long run of one period
                self.round_trip(data[:64 + n])

    def test_incompressible_data_is_flushed_with_the_no_match_word(self):
        data = rand(3000, 3)
        tokens = mkxex.pack(data)
        self.assertGreater(len(tokens), 1, "MAX_LITERALS should have split it")
        for tok in tokens:
            self.assertTrue(mkxex.literal_only(tok))
            self.assertLessEqual(mkxex.token_out(tok), mkxex.MAX_LITERALS)
        self.round_trip(data)

    def test_offset_is_bounded_by_a_word(self):
        chunk = rand(200, 9)
        data = chunk + rand(0x10000, 10) + chunk   # the repeat is too far back
        packed = self.round_trip(data)
        for tok in mkxex.pack(data):
            L, i = mkxex.literals(tok)
            if i + 2 <= len(tok):
                self.assertLessEqual(tok[i] | (tok[i + 1] << 8), 0xFFFF)
        self.assertGreater(len(packed), 0x10000 + 200)

    def test_unpack_refuses_a_reach_before_the_start(self):
        with self.assertRaises(ValueError):
            mkxex.unpack(b"\x00\x05\x00", 4)  # offset 5 with nothing written

    def test_unpack_refuses_a_count_that_does_not_end_on_a_token(self):
        packed = mkxex.join(mkxex.pack(b"abcdefgh"))
        with self.assertRaises(ValueError):
            mkxex.unpack(packed, 5)


class FarChunks(unittest.TestCase):
    """far_chunks must cut at token boundaries and cover the segment."""

    def tile(self, base, data, chunk):
        out = {}
        for dst, plain, packed in mkxex.far_chunks(base, data, chunk):
            self.assertLessEqual(len(packed), chunk)
            self.assertLessEqual(len(plain), 0xFFFF)
            self.assertEqual(mkxex.unpack(packed, len(plain),
                                          data[:dst - base]), plain)
            for k, b in enumerate(plain):
                self.assertNotIn(dst + k, out, "chunks must not overlap")
                out[dst + k] = b
        self.assertEqual(bytes(out[base + i] for i in range(len(data))), data)
        self.assertEqual(len(out), len(data), "no byte written outside the segment")
        return out

    def test_code_like_data(self):
        data = bytes((i * 7 + 3) & 0xFF for i in range(0x1F00 * 2))
        self.tile(0x010000, data, 0x1A00)

    def test_incompressible_data_fills_chunks_with_literals(self):
        data = rand(20000, 20)
        chunks = list(mkxex.far_chunks(0x010000, data, 0x1A00))
        self.assertGreaterEqual(len(chunks), 3)
        for dst, plain, packed in chunks[:-1]:
            self.assertGreater(len(packed), 0x1A00 - mkxex.MAX_LITERALS - 8,
                               "an incompressible chunk should be nearly full")
        self.tile(0x010000, data, 0x1A00)

    def test_the_output_count_is_kept_under_a_word(self):
        # A megabyte of zeros packs to next to nothing, but no chunk may
        # claim to unpack to more than 65535 bytes.
        data = b"\x00" * 200000
        chunks = list(mkxex.far_chunks(0x010000, data, 0x1A00))
        self.assertGreaterEqual(len(chunks), 4)
        self.tile(0x010000, data, 0x1A00)

    def test_a_chunk_never_ends_with_a_dangling_no_match_word(self):
        data = rand(3000, 30) + b"\x00" * 3000 + rand(3000, 31)
        for dst, plain, packed in mkxex.far_chunks(0x010000, data, 1100):
            # unpack() requires every byte to be consumed, which a trailing
            # no-match word after the last literal would not be.
            mkxex.unpack(packed, len(plain), data[:dst - 0x010000])

    def test_small_segment_is_one_chunk(self):
        chunks = list(mkxex.far_chunks(0x030000, b"gem4xe" * 10, 0x1A00))
        self.assertEqual(len(chunks), 1)

    def test_a_token_too_big_for_the_buffer_is_refused(self):
        with self.assertRaises(SystemExit):
            list(mkxex.far_chunks(0x010000, rand(2000, 40), 500))


class Staging(unittest.TestCase):
    """A packed far image must reload byte-for-byte through the unpacker."""

    def pack_and_load(self, far):
        near = [(0x3000, b"\xea" * 16)]
        blob, _, _ = mkxex.build_xex(near + far, 0x3000, SYMS)
        return load_xex(blob)

    def test_round_trip(self):
        img = bytes((i * 31 + 17) & 0xFF for i in range(13767))
        mem, runad = self.pack_and_load([(0x010000, img)])
        self.assertEqual(runad, 0x3000)
        got = bytes(mem.get(0x010000 + i, 0xFF) for i in range(len(img)))
        self.assertEqual(got, img)

    def test_matches_reach_into_earlier_chunks(self):
        # The second copy of the block is a match back across a chunk seam.
        block = rand(0x1800, 50)
        img = block + rand(0x1800, 51) + block
        mem, _ = self.pack_and_load([(0x010000, img)])
        self.assertEqual(bytes(mem[0x010000 + i] for i in range(len(img))), img)

    def test_two_far_segments(self):
        a = bytes(range(256)) * 4
        b = bytes((0xFF - i) & 0xFF for i in range(3000))
        mem, _ = self.pack_and_load([(0x010000, a), (0x018000, b)])
        self.assertEqual(bytes(mem[0x010000 + i] for i in range(len(a))), a)
        self.assertEqual(bytes(mem[0x018000 + i] for i in range(len(b))), b)

    def test_count_field_is_consumed(self):
        # Otherwise the INITAD call DOS makes after the run-vector segment
        # would unpack the last chunk a second time, over live memory.
        mem, _ = self.pack_and_load([(0x010000, b"\x5a" * 1024)])
        self.assertEqual(mem[SYMS["_fl_hdr"] + 3], 0)
        self.assertEqual(mem[SYMS["_fl_hdr"] + 4], 0)

    def test_the_unpacker_goes_above_the_image(self):
        # Two banks of image: the fast unpacker must go in the third.
        mem, _ = self.pack_and_load([(0x010000, rand(0x9000, 7)),
                                     (0x020000, rand(0x3000, 8))])
        self.assertEqual(mem[SYMS["fl_fastbank"]], 0x03)

    def test_refuses_segments_out_of_order(self):
        # The loader takes the last chunk's end as the image's top.
        with self.assertRaises(SystemExit) as e:
            mkxex.stage_far([(0x020000, b"\x01" * 64), (0x010000, b"\x02" * 64)],
                            SYMS)
        self.assertIn("address order", str(e.exception))

    def test_refuses_a_straddling_segment(self):
        with self.assertRaises(SystemExit):
            mkxex.build_xex([(0xFF00, b"\x00" * 0x400)], 0x3000, SYMS)

    def test_refuses_far_code_without_the_loader(self):
        with self.assertRaises(SystemExit) as e:
            mkxex.build_xex([(0x010000, b"\x00" * 256)], 0x3000, {})
        self.assertIn("farload", str(e.exception))

    def test_refuses_a_header_apart_from_its_buffer(self):
        syms = dict(SYMS, _fl_buf=SYMS["_fl_hdr"] + 4)
        with self.assertRaises(SystemExit) as e:
            mkxex.build_xex([(0x010000, b"\x00" * 256)], 0x3000, syms)
        self.assertIn("header", str(e.exception))


class RealBinary(unittest.TestCase):
    """The build products themselves, if they have been built."""

    def reassemble(self, name):
        elf = os.path.join(ROOT, "build", name)
        if not os.path.exists(elf):
            self.skipTest(f"build/{name} not built")
        segs, syms = mkxex.read_elf(elf)
        far = [(a, d) for a, d in segs if a > 0xFFFF]
        self.assertTrue(far, f"{name} should have far code; is --code-model=large set?")
        blob, _, _ = mkxex.build_xex(segs, syms["_atari_entry"], syms)
        global SYMS
        keep, SYMS = SYMS, syms
        try:
            mem, runad = load_xex(blob)
        finally:
            SYMS = keep
        self.assertEqual(runad, syms["_atari_entry"])
        for base, data in far:
            got = bytes(mem.get(base + i, 0xFF) for i in range(len(data)))
            self.assertEqual(got, data, f"far image at ${base:06X} did not reassemble")
        return len(blob), sum(len(d) for _, d in far)

    def test_m3_far_image_reassembles(self):
        self.reassemble("m3.elf")

    def test_gem_far_image_reassembles_and_shrinks(self):
        size, far = self.reassemble("gem.elf")
        self.assertLess(size, far * 3 // 4, "the far image should pack to under 75%")


if __name__ == "__main__":
    unittest.main()
