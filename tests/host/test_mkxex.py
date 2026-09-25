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
    LOADER["last"] = 0
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


LOADER = {"last": 0}        # what src/farload.s keeps between chunks


def farload_copy(mem, hdr=None):
    """src/farload.s, in Python, written from the G4Z description at the top
    of tools/mkxex.py and not from its decode(): unpack one staged chunk,
    then consume it.  The last offset is kept between chunks, as the loader
    keeps it, in the bank that stays put."""
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

    held = []                  # bits of the current bit byte, top first

    def byte():
        nonlocal src
        b = mem[src]
        src += 1
        return b

    def bit():
        if not held:
            b = byte()
            held.extend((b >> (7 - k)) & 1 for k in range(8))
        return held.pop(0)

    def number():
        n = 1
        while bit() == 0:
            n = n * 2 + bit()
        return n

    def copy(frm, n):
        nonlocal dst, cnt
        for _ in range(n):
            mem[dst] = mem[frm]
            dst += 1
            frm += 1
            cnt -= 1
        assert cnt >= 0, "a chunk wrote past its count"

    after_match = True         # how a chunk begins
    while cnt:
        choice = bit()
        if after_match and choice == 0:            # literals
            n = number()
            copy(src, n)
            src += n
            after_match = False
            continue
        if choice == 1:                            # a new offset
            hi = number()
            lo = byte()
            LOADER["last"] = (hi - 1) * 256 + lo + 1
            n = number() + 1
        else:                                      # a repeat
            assert LOADER["last"], "a repeat before any offset"
            n = number()
        copy(dst - LOADER["last"], n)
        after_match = True
    assert src <= SYMS["_fl_end"], "read past the staging buffer"
    mem[hdr + 3] = mem[hdr + 4] = 0


SYMS = {"_fl_hdr": 0x8000, "_fl_buf": 0x8005, "_fl_end": 0x8005 + 0x1A00,
        "_fl_copy": 0x9A05, "fl_fastbank": 0x3F4C}


def rand(n, seed):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


def tile(test, base, data, chunk):
    """far_chunks() over data: every chunk within its limits and decoded
    again here, and together exactly the segment."""
    out, got, last = {}, bytearray(), 0
    for dst, plain, packed in mkxex.far_chunks(base, data, chunk):
        test.assertLessEqual(len(packed), chunk)
        test.assertLessEqual(len(plain), 0xFFFF)
        test.assertEqual(dst, base + len(got), "chunks in address order, no gaps")
        last = mkxex.decode(packed, len(plain), got, last)
        for k, b in enumerate(plain):
            out[dst + k] = b
    test.assertEqual(bytes(got), data)
    test.assertEqual(len(out), len(data), "no byte written outside the segment")
    return out


class G4Z(unittest.TestCase):
    """The format: every shape of it through the packer and decode()."""

    def round_trip(self, data, chunk=0x1A00):
        tile(self, 0x010000, data, chunk)
        return sum(len(p) for _, p in mkxex.chunks(data, chunk))

    def test_nothing(self):
        self.assertEqual(mkxex.chunks(b"", 0x1A00), [])

    def test_short(self):
        for data in (b"a", b"ab", b"abc", b"abab", b"abcabc"):
            with self.subTest(data=data):
                self.round_trip(data)

    def test_a_run_is_a_match_at_offset_one(self):
        self.assertLess(self.round_trip(b"\x00" * 1000), 12)

    def test_a_repeat_after_literals(self):
        # a block, a changed byte, the block again: the shape repeats serve
        block = rand(40, 1)
        data = block + b"\x55" + block[:20] + b"\xAA" + block[21:] * 3
        self.round_trip(data)

    def test_long_literal_runs_and_numbers_of_every_width(self):
        for n in (1, 2, 3, 127, 128, 255, 256, 257, 4095, 4096, 9000):
            with self.subTest(n=n):
                self.round_trip(rand(n, n))

    def test_long_matches(self):
        for n in (2, 3, 255, 256, 4095, 4096, 4097, 20000):
            with self.subTest(n=n):
                data = rand(64, 7)
                data += data[:5] * (n // 5 + 1)
                self.round_trip(data[:64 + n])

    def test_offsets_of_every_width(self):
        for gap in (1, 255, 256, 257, 65534, 65535):
            with self.subTest(gap=gap):
                block = rand(16, gap)
                self.round_trip(block + rand(max(gap - 16, 0), gap + 1) + block)

    def test_an_offset_past_a_word_is_not_used(self):
        block = rand(200, 9)
        data = block + rand(0x10000, 10) + block
        self.assertGreater(self.round_trip(data), 0x10000 + 200)

    def test_decode_refuses_a_reach_before_the_start(self):
        w = mkxex._Bits()
        w.bit(1)
        w.gamma(1)
        w.out.append(4)            # offset 5, with nothing written
        w.gamma(1)
        with self.assertRaises(ValueError):
            mkxex.decode(bytes(w.out), 2, bytearray(), 0)

    def test_decode_refuses_a_count_that_does_not_end_the_chunk(self):
        (count, packed), = mkxex.chunks(b"abcdefgh" * 3, 0x1A00)
        with self.assertRaises(ValueError):
            mkxex.decode(packed, count - 3, bytearray(), 0)

    def test_small_chunks_everywhere(self):
        # every cut: chunks a few bytes long, a literal run split across
        # them, a repeat that falls at a chunk's start
        r = random.Random(5)
        for trial in range(60):
            n = r.randint(1, 1500)
            alpha = r.choice((1, 2, 3, 12, 256))
            data = bytes(r.randrange(alpha) for _ in range(n))
            for chunk in (16, 40, 300):
                with self.subTest(trial=trial, chunk=chunk):
                    tile(self, 0x010000, data, chunk)

    def test_the_output_count_is_kept_under_a_word(self):
        data = b"\x00" * 200000
        chunks = list(mkxex.far_chunks(0x010000, data, 0x1A00))
        self.assertGreaterEqual(len(chunks), 4)
        tile(self, 0x010000, data, 0x1A00)
        # ...and it is still a run: skipping the search inside long matches
        # once made this 97,752 bytes of mostly literals
        self.assertLess(sum(len(p) for _, _, p in chunks), 400)

    def test_incompressible_data_fills_its_chunks(self):
        data = rand(20000, 20)
        chunks = list(mkxex.far_chunks(0x010000, data, 0x1A00))
        self.assertGreaterEqual(len(chunks), 3)
        for dst, plain, packed in chunks[:-1]:
            self.assertGreater(len(packed), 0x1A00 - 16,
                               "an incompressible chunk should be nearly full")

    def test_a_chunk_too_small_for_anything_is_refused(self):
        with self.assertRaises(SystemExit):
            list(mkxex.far_chunks(0x010000, rand(200, 40), 4))

    def test_the_real_far_image_packs_to_well_under_two_thirds(self):
        elf = os.path.join(ROOT, "build", "gem.elf")
        if not os.path.exists(elf):
            self.skipTest("build/gem.elf not built")
        segs, _ = mkxex.read_elf(elf)
        far = [d for a, d in segs if a > 0xFFFF]
        plain = sum(map(len, far))
        packed = sum(len(p) for d in far for _, p in mkxex.chunks(d, 0x1A00))
        self.assertLess(packed / plain, 0.60,
                        f"{packed} of {plain}: the byte-token format did 0.67")


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
