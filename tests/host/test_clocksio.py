#!/usr/bin/env python3
"""The SIO clock asked once an hour (src/sys/clock.c, sio_clock).

An APETime clock on the serial bus -- a FujiNet's -- was asked at every
read, and the Control Panel's header reads every second: one click a
second from the OS's noisy I/O on a 600XL.  sio_clock now keeps the bus's
answer with the timer's second and counts on from it, going back to the
bus once an hour, or counting on from the last answer if nobody replies.

No emulator here has an APETime device, so tests/host/clock_sim.c builds
clock.c WITH THE REAL COMPILER, stands in for the bus and the timer, and
runs under Calypsi's simulator; every read is checked here against
Python's datetime, with the number of bus transactions it took.
"""
import datetime
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CALYPSI = os.environ.get("CALYPSI", os.path.expanduser("~/dev/toolchains/calypsi-65816"))
SIM_C = os.path.join(ROOT, "tests", "host", "clock_sim.c")
T = datetime.datetime
H = datetime.timedelta(hours=1)
S = datetime.timedelta(seconds=1)

# per read in clock_sim.c's main: the time it should give and how many
# times the bus has been asked by then (None: no time at all)
first = T(2026, 12, 31, 23, 59, 30)
second = T(2027, 1, 1, 1, 0, 5)
WANT = [
    (first, 1),                         # asked
    (first + 29 * S, 1),                # counted
    (T(2027, 1, 1, 0, 0, 0), 1),        # counted across the year
    (first + 3599 * S, 1),              # the hour not up
    (second, 2),                        # asked again: the bus's, not the count
    (second + H, 3),                    # asked, nobody: counted on
    (second + H + S, 3),                # not asked again within the hour
    (T(2028, 2, 28, 23, 59, 59), 4),
    (T(2028, 2, 29, 0, 0, 0), 4),       # a leap year
    (T(2027, 2, 28, 23, 59, 59), 5),
    (T(2027, 3, 1, 0, 0, 0), 5),        # not one
    (T(2027, 6, 5, 12, 0, 0), 6),       # the timer stopped: asked...
    (T(2027, 6, 5, 12, 0, 0), 7),       # ...at every read
    (None, 8),                          # nobody on the bus: no time
]


class TestClockSio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = os.path.join(CALYPSI, "bin", "cc65816")
        if not os.path.exists(cc):
            raise unittest.SkipTest("Calypsi not installed")
        ld, db = (os.path.join(CALYPSI, "bin", t) for t in ("ln65816", "db65816"))
        out = os.path.join(ROOT, "build", "clocksio")
        os.makedirs(out, exist_ok=True)
        # Calypsi's minimal script, and a home for clock.c's far tables
        # (FAR_816: section cfar), which it has none for
        with open(os.path.join(CALYPSI, "example", "minimal", "linker.scm")) as f:
            text = f.read().replace("(section farcode idata cdata switch)",
                                    "(section farcode idata cdata switch cfar)")
        scm = os.path.join(out, "linker.scm")
        with open(scm, "w") as f:
            f.write(text)
        obj = os.path.join(out, "clock_sim.o")
        # clock.c at the product's -O2, small data as the system is built
        subprocess.run([cc, "-g", "--code-model=large", "--data-model=small", "-O2",
                        "-I", os.path.join(ROOT, "src"), "-I", os.path.join(ROOT, "src", "sys"),
                        "-o", obj, SIM_C], check=True)
        elf = os.path.join(out, "clock_sim.elf")
        subprocess.run([ld, "-g", scm, obj, "-o", elf, "clib-lc-sd.a",
                        "--rtattr", "exit=simplified",
                        "--list-file", os.path.join(out, "clock_sim.map")], check=True)
        names = ["tsim_ran", "tsim_n", "tsim_out"]
        script = "run\n" + "".join(f"print {n}\n" for n in names) + "quit\n"
        p = subprocess.run([db, "--nh", "--nx", "--exit-breakpoint", elf],
                           input=script, capture_output=True, text=True, timeout=180)
        txt = p.stdout + p.stderr
        marks = list(re.finditer(r"\$\d+ = ", txt))
        vals = [txt[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(txt))]
                for i, m in enumerate(marks)]
        if len(vals) < len(names):
            raise AssertionError(f"the simulator said too little:\n{txt[-2000:]}")
        cls.by = dict(zip(names, vals))

    @staticmethod
    def _ints(s):
        return [int(v) for v in re.findall(r"=\s*(-?\d+)", s)] or \
               [int(v) for v in re.findall(r"(-?\d+)", s)]

    def test_it_ran(self):
        self.assertEqual(self._ints(self.by["tsim_ran"])[0], 1)
        self.assertEqual(self._ints(self.by["tsim_n"])[0], len(WANT))

    def test_every_read(self):
        out = self._ints(self.by["tsim_out"])
        for i, (when, asked) in enumerate(WANT):
            s, mi, h, d, mo, y, got_asked, ok = out[i * 8:i * 8 + 8]
            with self.subTest(read=i + 1):
                self.assertEqual(got_asked, asked, f"read {i + 1}: the bus asked "
                                 f"{got_asked} times by now, want {asked}")
                if when is None:
                    self.assertEqual(ok, 0, f"read {i + 1}: a time with nobody on the bus")
                    continue
                self.assertEqual(ok, 1, f"read {i + 1}: no time")
                self.assertEqual((y, mo, d, h, mi, s),
                                 (when.year, when.month, when.day, when.hour,
                                  when.minute, when.second), f"read {i + 1}")


if __name__ == "__main__":
    unittest.main()
