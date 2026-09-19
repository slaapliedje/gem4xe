#!/usr/bin/env python3
"""The kit's clock (src/app/gemtime.c), against Python's calendar.

WHY THE KIT HAS A CLOCK AT ALL.  Calypsi's <time.h> says
`typedef int64_t time_t`, and on this compiler a 64-bit division is a
loaded gun: _Div64 is eight bytes that end in `clc` and fall through into
whatever the linker placed after them (tools/ccbug, B20).  Asking the C
library to format a date is enough to fire it -- its localtime() divides
a time_t -- and that is how qed died on an Atari while saving a file.
So include/time.h makes time_t a 32-bit long and lib/gemtime.c does the
calendar in 32-bit arithmetic.

A calendar written a second time is only worth having if it agrees with
everybody else's, so this compiles gemtime.c WITH THE REAL COMPILER, runs
it under Calypsi's own simulator, and compares every field against
Python's datetime.  Two things are checked that a field comparison would
not reach:

  * mktime(gmtime(t)) == t for every case, which catches a calendar that
    is self-consistently wrong;
  * the linked program contains NO _Div64, which is the whole point of
    the exercise and the only direct test that B20 has been designed out
    rather than merely avoided today.
"""
import datetime
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CALYPSI = os.environ.get("CALYPSI", os.path.expanduser("~/dev/toolchains/calypsi-65816"))
GEMTIME_C = os.path.join(ROOT, "src", "app", "gemtime.c")
TIME_SIM_C = os.path.join(ROOT, "tests", "host", "time_sim.c")

UTC = datetime.timezone.utc
# The stamp time_sim.c formats: it must match the RTC stub there.
STAMP = 1789828220


def expect(ts):
    d = datetime.datetime.fromtimestamp(ts, UTC)
    # Python's weekday() is Monday=0; C's tm_wday is Sunday=0.
    wday = (d.weekday() + 1) % 7
    yday = d.timetuple().tm_yday - 1
    return (d.year, d.month, d.day, d.hour, d.minute, d.second, wday, yday)


class TestGemTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        scm = os.path.join(CALYPSI, "example", "minimal", "linker.scm")
        out = os.path.join(ROOT, "build", "gemtime")
        os.makedirs(out, exist_ok=True)
        objs = []
        # gemtime.c AT THE LEVEL THE PRODUCT USES.  test_the_makefile_still
        # _pins_O0 below is what keeps the two in step; building it here at
        # -O2 regardless would test something nothing ships.
        for src, opt in ((GEMTIME_C, "-O0"), (TIME_SIM_C, "-O2")):
            obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
            subprocess.run([cc, "-g", "--code-model=large", "--data-model=small",
                            opt, "-I", os.path.join(ROOT, "src"),
                            "-I", os.path.join(ROOT, "src", "app"),
                            "-o", obj, src], check=True)
            objs.append(obj)
        cls.elf = os.path.join(out, "gemtime.elf")
        cls.map = os.path.join(out, "gemtime.map")
        subprocess.run([ld, "-g", scm] + objs + ["-o", cls.elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified", "--list-file", cls.map],
                       check=True)
        names = ["tsim_ran", "tsim_out", "tsim_back", "tsim_us", "tsim_de",
                 "tsim_iso", "tsim_hms", "tsim_mix", "tsim_trunc",
                 "tsim_truncbuf", "tsim_time_gtod", "tsim_time_rtc"]
        script = "run\n" + "".join(f"print {n}\n" for n in names) + "quit\n"
        p = subprocess.run([db, "--nh", "--nx", "--exit-breakpoint", cls.elf],
                           input=script, capture_output=True, text=True,
                           timeout=180)
        cls.txt = p.stdout + p.stderr
        # db65816 prints an array as a MULTI-LINE block, `{ [0] = v, ... }`,
        # so a per-line regex reads the first element and calls it the
        # answer.  Slice between the `$n = ` markers instead.
        marks = list(re.finditer(r"\$\d+ = ", cls.txt))
        cls.vals = [cls.txt[m.end():(marks[i + 1].start()
                                     if i + 1 < len(marks) else len(cls.txt))]
                    for i, m in enumerate(marks)]
        if len(cls.vals) < len(names):
            raise AssertionError(f"the simulator said too little:\n{cls.txt[-2000:]}")
        cls.by = dict(zip(names, cls.vals))

    @staticmethod
    def _ints(s):
        return [int(v) for v in re.findall(r"=\s*(-?\d+)", s)] or \
               [int(v) for v in re.findall(r"(-?\d+)", s)]

    @staticmethod
    def _str(s):
        m = re.search(r'"((?:[^"\\]|\\.)*)"', s)
        if m:
            return m.group(1)
        # the debugger may print a char array element by element
        chars = [int(v) for v in re.findall(r"=\s*(-?\d+)", s)]
        out = ""
        for c in chars:
            if c == 0:
                break
            out += chr(c & 0xFF)
        return out

    def test_it_ran(self):
        self.assertEqual(self._ints(self.by["tsim_ran"])[0], 1,
                         "the simulated program did not reach the end")

    def test_every_field_matches_python(self):
        import importlib.util
        spec = re.findall(r"=\s*(-?\d+)", self.by["tsim_out"])
        got = [int(v) for v in spec]
        with open(TIME_SIM_C) as f:
            src = f.read()
        block = re.search(r"const long tsim_in\[NCASES\] = \{(.*?)\};", src, re.S)
        stamps = [int(v) for v in re.findall(r"(-?\d+)L", block.group(1))]
        self.assertEqual(len(stamps) * 8, len(got),
                         f"{len(stamps)} stamps but {len(got)} fields back")
        for i, ts in enumerate(stamps):
            with self.subTest(stamp=ts):
                self.assertEqual(tuple(got[i * 8:i * 8 + 8]), expect(ts),
                                 f"gmtime_r({ts}) disagrees with Python "
                                 f"(year, mon, mday, hour, min, sec, wday, yday)")

    def test_mktime_is_the_inverse(self):
        with open(TIME_SIM_C) as f:
            src = f.read()
        block = re.search(r"const long tsim_in\[NCASES\] = \{(.*?)\};", src, re.S)
        stamps = [int(v) for v in re.findall(r"(-?\d+)L", block.group(1))]
        back = [int(v) for v in re.findall(r"=\s*(-?\d+)", self.by["tsim_back"])]
        self.assertEqual(len(back), len(stamps))
        for ts, b in zip(stamps, back):
            self.assertEqual(b, ts, f"mktime(gmtime({ts})) came back {b}")

    def test_the_formats_qed_asks_for(self):
        """The four src/global.c asks for, against Python's strftime --
        not against constants typed here.  The first draft of this test
        DID type them, got the stamp an hour field wrong, and accused the
        code of what the test had done."""
        d = datetime.datetime.fromtimestamp(STAMP, UTC)
        for key, fmt in (("tsim_us", "%m/%d/%Y"), ("tsim_de", "%d.%m.%Y"),
                         ("tsim_iso", "%Y-%m-%d"), ("tsim_hms", "%H:%M:%S")):
            with self.subTest(fmt=fmt):
                self.assertEqual(self._str(self.by[key])[:len(d.strftime(fmt))],
                                 d.strftime(fmt))

    def test_the_rest_of_the_conversions(self):
        """%a %b %e %I%p j=%j %% and then %q, which is NOT one of ours and
        must come through as written rather than vanishing."""
        d = datetime.datetime.fromtimestamp(STAMP, UTC)
        want = d.strftime("%a %b ") + f"{d.day:2d} " + d.strftime("%I%p") \
             + " j=" + d.strftime("%j") + " % %q"
        self.assertEqual(self._str(self.by["tsim_mix"]), want)

    def test_a_buffer_too_small_answers_zero(self):
        self.assertEqual(self._ints(self.by["tsim_trunc"])[0], 0,
                         "strftime into a 4-byte buffer must answer 0")
        self.assertEqual(self._ints(self.by["tsim_truncbuf"])[0], 0,
                         "...and leave the buffer terminated, not half-written")

    def test_time_takes_the_rtc_when_there_is_no_mint_clock(self):
        gtod = self._ints(self.by["tsim_time_gtod"])[0]
        rtc = self._ints(self.by["tsim_time_rtc"])[0]
        self.assertEqual(gtod, 1000000000,
                         "time() did not take Tgettimeofday's answer")
        self.assertEqual(rtc, STAMP,
                         "time() did not fall back to Tgetdate/Tgettime "
                         "(2026-09-19 14:30:20) when the clock refused")

    def test_the_makefile_still_pins_O0(self):
        """gemtime.c is built at -O0 because -O1 and above miscompile
        civil_from_days (the file says which shapes).  This test builds it
        at -O0 too, so it would go on passing if somebody raised the
        Makefile -- hence this, which reads the Makefile and requires the
        two to agree."""
        with open(os.path.join(ROOT, "Makefile"), errors="ignore") as f:
            mk = f.read()
        for target in ("build/app/gemtime.o", "build/appld/gemtime.o"):
            i = mk.find(target + ":")
            self.assertGreater(i, 0, f"{target} has no rule of its own any more")
            recipe = mk[i:mk.find("\n\n", i)]
            self.assertIn("-O0", recipe,
                          f"{target} is no longer built at -O0; if the compiler "
                          f"was fixed, raise it HERE and in this test together")

    def test_no_div64_is_linked(self):
        """THE POINT.  A 64-bit division anywhere in this calendar would
        call _Div64, which falls through into whatever follows it
        (tools/ccbug B20).  The kit's whole reason for having a <time.h>
        is that no program keeping to it can reach that."""
        with open(self.map, errors="ignore") as f:
            text = f.read()
        self.assertNotIn("_Div64", text,
                         "gemtime.c links _Div64: a 64-bit division got in")


if __name__ == "__main__":
    unittest.main()
