#!/usr/bin/env python3
"""Host tests for the pointing-device layer.

The VDI conformance suite tests everything ABOVE the seam in
src/vdi/pointer.h -- it only ever sees an absolute position.  This tests what
is below it, which the emulator's bridge cannot drive directly: the two
transition tables (Gray-code quadrature, the CX80's direction-and-pulse) and
the guarantee that neither has drifted from the reference; the per-device
choice of PORTA lines, walked through the target's own C in the compiler's
simulator against Altirra's device models (tests/host/quad_sim.c); and the
XEM1 decode, likewise.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdiref  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools", "ccbug"))
import check as ccbug  # noqa: E402  (the simulator driver)

POINTER_C = os.path.join(ROOT, "src", "vdi", "pointer.c")
IRQ_STUB_C = os.path.join(ROOT, "tests", "host", "irq_stub.c")
# pointer.c clamps to the screen, and the screen is whatever `vdev`
# points at now (docs/phase34.md), so a build of it needs a device
DEV_STUB_C = os.path.join(ROOT, "tests", "host", "dev_stub.c")
QUAD_SIM_C = os.path.join(ROOT, "tests", "host", "quad_sim.c")
XEM1_SIM_C = os.path.join(ROOT, "tests", "host", "xem1_sim.c")
TABLET_SIM_C = os.path.join(ROOT, "tests", "host", "tablet_sim.c")
GRAY = (0, 1, 3, 2)          # the quadrature phase order, one full cycle
CALYPSI = os.environ.get("CALYPSI", os.path.expanduser("~/dev/toolchains/calypsi-65816"))


def c_table(name="qdec"):
    with open(POINTER_C) as f:
        src = f.read()
    m = re.search(r"static const signed char " + name + r"\[16\]\s*=\s*\{(.*?)\};", src, re.S)
    if not m:
        raise AssertionError(f"{name}[] not found in pointer.c")
    vals = [int(v) for v in re.findall(r"[-+]?\d+", m.group(1))]
    assert len(vals) == 16, f"{name} has {len(vals)} entries"
    return vals


def simulate(program, sources, names):
    """Compile pointer.c and `sources` for the compiler's simulator, run
    them, and return the named globals.  Skips if Calypsi is not here."""
    cc = os.path.join(CALYPSI, "bin", "cc65816")
    if not os.path.exists(cc):
        raise unittest.SkipTest("Calypsi not installed")
    ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
    scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
    out = os.path.join(ROOT, "build", program)
    os.makedirs(out, exist_ok=True)
    objs = []
    for src in (POINTER_C, IRQ_STUB_C, DEV_STUB_C) + tuple(sources):
        obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
        subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                        "-O2", "-I", os.path.join(ROOT, "src"), "-o", obj, src],
                       check=True)
        objs.append(obj)
    elf = os.path.join(out, program + ".elf")
    subprocess.run([ld, "-g", scm] + objs + ["-o", elf, "clib-lc-sd.a",
                    "--rtattr", "exit=simplified"], check=True)
    return ccbug.simulate(db, elf, names)


class TestQuadrature(unittest.TestCase):
    def test_c_and_reference_tables_agree(self):
        """The driver's table and the reference's must be identical."""
        c = c_table()
        ref = [vdiref.decode_quad(p, n) for p in range(4) for n in range(4)]
        self.assertEqual(c, ref)

    def test_full_cycle_forward_is_four_counts(self):
        total = sum(vdiref.decode_quad(GRAY[i], GRAY[(i + 1) % 4])
                    for i in range(4))
        self.assertEqual(total, 4)

    def test_reverse_cycle_is_minus_four(self):
        total = sum(vdiref.decode_quad(GRAY[(i + 1) % 4], GRAY[i])
                    for i in range(4))
        self.assertEqual(total, -4)

    def test_motion_then_reverse_returns_to_origin(self):
        """Any walk and its reverse must net to zero -- no drift."""
        walk = [0, 1, 3, 2, 0, 2, 3, 1, 0, 1, 1, 3, 3, 2]
        fwd = sum(vdiref.decode_quad(walk[i], walk[i + 1])
                  for i in range(len(walk) - 1))
        rev = sum(vdiref.decode_quad(walk[i + 1], walk[i])
                  for i in range(len(walk) - 1))
        self.assertEqual(fwd + rev, 0)

    def test_no_movement_reads_zero(self):
        for p in range(4):
            self.assertEqual(vdiref.decode_quad(p, p), 0)

    def test_two_step_jump_drops_motion(self):
        """A missed sample is ambiguous: report 0 rather than guess a
        direction.  Inventing motion the wrong way is worse than losing it."""
        for p, n in ((0, 3), (3, 0), (1, 2), (2, 1)):
            self.assertEqual(vdiref.decode_quad(p, n), 0)


class TestTrakBall(unittest.TestCase):
    """The CX80's direction-and-pulse lines: not quadrature, and the sign
    comes from the sample that carries the edge."""

    def test_c_and_reference_tables_agree(self):
        c = c_table("tbdec")
        ref = [vdiref.decode_tb(p, n) for p in range(4) for n in range(4)]
        self.assertEqual(c, ref)

    def test_pulse_with_direction_high_is_plus(self):
        self.assertEqual(vdiref.decode_tb(0b10, 0b11), +1)
        self.assertEqual(vdiref.decode_tb(0b11, 0b10), +1)

    def test_pulse_with_direction_low_is_minus(self):
        self.assertEqual(vdiref.decode_tb(0b00, 0b01), -1)
        self.assertEqual(vdiref.decode_tb(0b01, 0b00), -1)

    def test_direction_change_alone_is_nothing(self):
        for p in range(4):
            self.assertEqual(vdiref.decode_tb(p, p), 0)
            self.assertEqual(vdiref.decode_tb(p, p ^ 2), 0)

    def test_sign_is_the_edge_samples_direction(self):
        """Altirra's model flips the direction bit in the same update as
        the pulse, so a reversal's first count must already go the new way."""
        self.assertEqual(vdiref.decode_tb(0b10, 0b01), -1)
        self.assertEqual(vdiref.decode_tb(0b00, 0b11), +1)


class TestDeviceWalks(unittest.TestCase):
    """Altirra's ST mouse, Amiga mouse and CX80 models walked through the
    target's pointer layer in the compiler's simulator, seven steps each
    way on each axis (tests/host/quad_sim.c).  The signs are the emulator's
    -- no hardware has confirmed them -- but a wrong pin pairing shows up
    here as an axis that reads zero or the other axis moving."""
    STEPS = 7

    @classmethod
    def setUpClass(cls):
        names = [f"r_{d}[{i}]" for d in ("st", "amiga", "tb") for i in range(16)]
        names.append("r_handler_agrees")
        cls.got = simulate("quad", [QUAD_SIM_C], names)

    def walks(self, dev, port=2):
        """The sim walks every device twice: port 2 into [0..7], port 1
        into [8..15].  Port 2 is the standard and the default."""
        g, base = self.got, 0 if port == 2 else 8
        return [(g[f"r_{dev}[{base + 2 * w}]"], g[f"r_{dev}[{base + 2 * w + 1}]"])
                for w in range(4)]

    def check_device(self, dev):
        n = self.STEPS
        want = [(n, 0), (-n, 0), (0, n), (0, -n)]
        self.assertEqual(self.walks(dev, 2), want, f"{dev} on port 2")
        self.assertEqual(self.walks(dev, 1), want,
                         f"{dev} on port 1, the escape for a machine wired "
                         f"the other way")

    def test_st_mouse(self):
        self.check_device("st")

    def test_amiga_mouse(self):
        self.check_device("amiga")

    def test_cx80_trak_ball(self):
        self.check_device("tb")

    def test_handler_arithmetic_matches_polled_path(self):
        """The timer handler indexes the same tables as (prev << 2) | pair;
        its C copy in quad_sim.c must count what ptr_poll() counted."""
        self.assertEqual(self.got["r_handler_agrees"], 1)


class TestTabletScaling(unittest.TestCase):
    """POKEY's pot counter tops out near 228 against a 640x240 screen."""
    POT_MAX = 228

    def scale(self, pot, span):
        return (pot * (span - 1)) // self.POT_MAX

    def test_endpoints_reach_the_corners(self):
        self.assertEqual(self.scale(0, 640), 0)
        self.assertEqual(self.scale(self.POT_MAX, 640), 639)
        self.assertEqual(self.scale(0, 240), 0)
        self.assertEqual(self.scale(self.POT_MAX, 240), 239)

    def test_horizontal_granularity_is_coarse(self):
        """~2.8 screen pixels per step across: fine for hitting a menu item,
        too coarse to draw with.  Recorded so it is a known property rather
        than a surprise."""
        step = self.scale(1, 640) - self.scale(0, 640)
        self.assertEqual(step, 2)
        self.assertGreaterEqual(639 / self.POT_MAX, 2.7)

    def test_vertical_is_about_one_to_one(self):
        self.assertLessEqual(abs(239 / self.POT_MAX - 1.0), 0.1)


class AltirraTablet:
    """Altirra's ATTabletController (inputcontroller.cpp), forward: where
    the stylus is -> what the port reads.  inputmanager.cpp builds the
    CX77 ("Tablet") with (stylus-up 228, invertY) and the KoalaPad with
    (0, no invert).  A position is -1..+1 across the pad, left to right
    and top to bottom, as the controller's raw position -0x10000..0x10000
    is; the pot is (pos * 114 + 0x728000) >> 16, so 0..228."""
    def __init__(self, cx77):
        self.up, self.invert = (228, True) if cx77 else (0, False)

    def pots(self, u, v, lifted=False):
        if lifted:
            return self.up, self.up
        def pot(f):
            pos = max(-0x10000, min(0x10000, int(round(f * 0x10000))))
            return (pos * 114 + 0x728000) >> 16
        return pot(u), pot(-v if self.invert else v)

    @staticmethod
    def lines(stylus=False, left=False, right=False):
        """SetPortOutput: a pressed button's bit pulls its line low --
        stylus button bit 0 (the up line), left bit 2, right bit 3."""
        bits = (1 if stylus else 0) | (4 if left else 0) | (8 if right else 0)
        return ~bits & 15


def tablet_expect(cx77, px, py):
    """What the pointer should do for a reading: None while the stylus is
    up (the pointer stays), else the screen position -- 0..228 spread over
    the VBXE's 640 x 240, top-left at the pad's top-left."""
    up = 228 if cx77 else 0
    px, py = min(px, 228), min(py, 228)
    if px == up and py == up:
        return None
    if cx77:
        py = 228 - py
    return (px * 639) // 228, (py * 239) // 228


class TestTablets(unittest.TestCase):
    """The CX77 and the KoalaPad, held to Altirra's model of them.  Until
    phase 108 gem4xe had one tablet with the KoalaPad's y and no stylus-up
    value, read port 1 whatever MOUSEPORT said, and took the buttons from
    both triggers."""

    def test_the_model_places_the_corners(self):
        for cx77 in (True, False):
            t = AltirraTablet(cx77)
            self.assertEqual(tablet_expect(cx77, *t.pots(1, 1)), (639, 239))
            self.assertEqual(tablet_expect(cx77, *t.pots(-1, 1)), (0, 239))
            self.assertEqual(tablet_expect(cx77, *t.pots(-0.99, -0.99)), (2, 1))
            self.assertEqual(tablet_expect(cx77, *t.pots(0.99, -0.99)), (636, 1))

    def test_one_corner_reads_as_lifted(self):
        """The stylus-up reading is also one corner's: the CX77's top
        right (228, 228 with its y inverted), the KoalaPad's top left
        (0, 0).  Nothing can tell them apart, so the pointer stays where
        it was -- a pixel short of that corner, never thrown to it."""
        self.assertIsNone(tablet_expect(True, *AltirraTablet(True).pots(1, -1)))
        self.assertIsNone(tablet_expect(False, *AltirraTablet(False).pots(-1, -1)))

    def test_lifting_the_stylus_is_not_a_place(self):
        for cx77 in (True, False):
            t = AltirraTablet(cx77)
            self.assertIsNone(tablet_expect(cx77, *t.pots(0, 0, lifted=True)))

    def test_down_the_pad_is_down_the_screen(self):
        for cx77 in (True, False):
            t = AltirraTablet(cx77)
            ys = [tablet_expect(cx77, *t.pots(0, v / 8))[1] for v in range(-7, 8)]
            self.assertEqual(ys, sorted(ys), f"cx77={cx77}")
            self.assertLess(ys[0], ys[-1])

    def test_target_decode_matches_the_model(self):
        got = simulate("tablet", [TABLET_SIM_C], ["r_cx77", "r_koala", "r_buttons"])

        def one(h, cx77, px, py):
            e = tablet_expect(cx77, px, py)
            x, y = e if e else (-1, -1)
            h = (h * 31 + (1 if e else 2)) & 0xFFFFFFFF
            h = (h * 31 + (x & 0xFFFF)) & 0xFFFFFFFF
            return (h * 31 + (y & 0xFFFF)) & 0xFFFFFFFF

        def walk(cx77):
            h = 0
            for v in range(256):
                for e in (0, 1, 114, 227, 228, 255):
                    h = one(h, cx77, v, e)
                    h = one(h, cx77, e, v)
            return h
        b = 0
        for n in range(16):
            left = (n & 1) == 0 or (n & 4) == 0
            right = (n & 8) == 0
            b = (b * 7 + (1 if left else 0) + (2 if right else 0)) & 0xFFFFFFFF
        self.assertEqual(got["r_cx77"] & 0xFFFFFFFF, walk(True), "CX77")
        self.assertEqual(got["r_koala"] & 0xFFFFFFFF, walk(False), "KoalaPad")
        self.assertEqual(got["r_buttons"] & 0xFFFFFFFF, b, "buttons")

    def test_the_buttons_are_the_direction_lines(self):
        L = AltirraTablet.lines
        def want(n):
            return (1 if (n & 1) == 0 or (n & 4) == 0 else 0) | (2 if (n & 8) == 0 else 0)
        self.assertEqual(want(L()), 0)
        self.assertEqual(want(L(stylus=True)), 1)
        self.assertEqual(want(L(left=True)), 1)
        self.assertEqual(want(L(right=True)), 2)
        self.assertEqual(want(L(stylus=True, right=True)), 3)


class TestXem1(unittest.TestCase):
    """mouSTer's XEM1 mode: the decode in tools/vdiref.py follows the
    adapter's sample driver instruction by instruction; these pin what that
    arithmetic means, and the last one runs the target's C over every pair
    of readings in the compiler's simulator and compares."""

    def test_readings_are_64_to_191(self):
        self.assertEqual([p for p in range(256) if vdiref.xem1_valid(p)],
                         list(range(64, 192)))
        self.assertFalse(vdiref.xem1_valid(228))     # an empty port

    def test_no_change_is_no_movement(self):
        for p in range(64, 192):
            self.assertEqual(vdiref.decode_xem1(p, p), (0, p))

    def test_low_bit_is_noise_and_accumulates(self):
        """One count halves to nothing and does not move the reference, so
        a second count a frame later delivers the pixel."""
        d, ref = vdiref.decode_xem1(128, 129)
        self.assertEqual((d, ref), (0, 128))
        self.assertEqual(vdiref.decode_xem1(ref, 130), (1, 130))
        self.assertEqual(vdiref.decode_xem1(128, 127), (0, 128))
        self.assertEqual(vdiref.decode_xem1(128, 126), (-1, 126))

    def test_halves_toward_zero(self):
        self.assertEqual(vdiref.decode_xem1(128, 131)[0], 1)
        self.assertEqual(vdiref.decode_xem1(128, 125)[0], -1)
        self.assertEqual(vdiref.decode_xem1(128, 191)[0], 31)
        self.assertEqual(vdiref.decode_xem1(128, 64)[0], -32)

    def test_counter_wraps_at_seven_bits(self):
        """191 -> 64 is one step forward, not 127 back."""
        self.assertEqual(vdiref.decode_xem1(190, 65), (1, 65))    # +3
        self.assertEqual(vdiref.decode_xem1(65, 190), (-1, 190))  # -3
        self.assertEqual(vdiref.decode_xem1(191, 64), (0, 191))   # +1: noise

    def test_target_decode_matches_reference(self):
        got = simulate("xem1", [XEM1_SIM_C], ["r_hash", "r_valid", "r_wrap", "r_neg"])

        h = v = 0
        for p in range(256):
            v = (v * 3 + (1 if vdiref.xem1_valid(p) else 0)) & 0xFFFFFFFF
        for ref in range(64, 192):
            for now in range(64, 192):
                h = (h * 31 + (vdiref.decode_xem1(ref, now)[0] & 0xFF)) & 0xFFFFFFFF
        self.assertEqual(got["r_wrap"], 1)
        self.assertEqual(got["r_neg"], -1)
        self.assertEqual(got["r_valid"] & 0xFFFFFFFF, v)
        self.assertEqual(got["r_hash"] & 0xFFFFFFFF, h)


if __name__ == "__main__":
    unittest.main(verbosity=2)
