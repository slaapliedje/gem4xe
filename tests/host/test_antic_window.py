"""Nothing ANTIC fetches may sit in $4000-$7FFF, the PORTB bank window.

ANTIC reads memory on its own, every scan line, whatever bank PORTB has
swapped in.  A display list, a screen, a player/missile area or a
character set in the window shows whichever bank is in at the moment: a
DOS running in banked RAM (SpartaDOS X) swaps banks during disk I/O and
the display goes to pieces while it does.  gem4xe's 6502 build swaps the
same window for its own code.

Checked here, from the source:
  - the ANTIC device's display list and framebuffer (src/antic/antic.h);
  - the boot screen's character sets (src/sys/bootinfo.c);
  - that no file sets PMBASE ($D407) -- the pointer is drawn into the
    screen -- and only bootinfo.c sets CHBASE ($D409): a new one must be
    added here with its address held to the rule;
  - that no 6502 link map (tools/bsp6502/*.scm) puts memory in
    $8000-$9EFF, where the display list and screen are.

G4ROOT points the test at another tree (how it was made to fail).
"""
import glob
import os
import re
import unittest

ROOT = os.environ.get("G4ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
WINDOW = (0x4000, 0x8000)              # [lo, hi)
DISPLAY = (0x8000, 0x9F00)             # the display list and the screen
# the 6502 maps of programs that drive the ANTIC device; atari-banked.scm
# is the throwaway probe map, whose Screen holds nothing
MAPS = ("a6", "c6", "f6", "i6", "gem6502", "atari-banked")


def read(rel):
    with open(os.path.join(ROOT, rel), errors="replace") as f:
        return f.read()


def define(text, name):
    m = re.search(r"^#define\s+" + name + r"\s+\(?\s*(0x[0-9A-Fa-f]+|\d+)U?\b", text, re.M)
    if not m:
        raise AssertionError(f"#define {name} not found")
    return int(m.group(1), 0)


def overlaps(lo, hi, rng):
    return lo < rng[1] and rng[0] < hi


def memories(text):
    """[(name, lo, hi_exclusive, has_section)] for every (memory ...)."""
    out = []
    for m in re.finditer(r"\(memory\s+([\w-]+)\s+\(address\s+\(#x([0-9a-fA-F]+)\s*\.\s*#x([0-9a-fA-F]+)\)\)", text):
        rest = text[m.end():]
        nxt = re.search(r"\(memory\s", rest)
        body = rest[:nxt.start()] if nxt else rest
        out.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16) + 1, "(section" in body))
    return out


class AnticOutsideWindow(unittest.TestCase):
    def test_display_list_and_screen(self):
        h = read("src/antic/antic.h")
        dl, scr = define(h, "AN_DLIST"), define(h, "AN_SCREEN")
        size = define(h, "AN_W") // 8 * define(h, "AN_H")
        for name, lo, hi in (("display list", dl, scr), ("framebuffer", scr, scr + size)):
            self.assertFalse(overlaps(lo, hi, WINDOW),
                             f"the ANTIC {name} ${lo:04X}-${hi - 1:04X} is in the bank window")
        self.assertLessEqual(scr + size, DISPLAY[1], "the screen runs past $9EFF, into ScreenTail")

    def test_boot_fonts(self):
        b = read("src/sys/bootinfo.c")
        for name in ("GLYPHS", "TEXTSET"):
            a = define(b, name)
            self.assertFalse(overlaps(a, a + 1024, WINDOW),
                             f"bootinfo.c's {name} font ${a:04X} is in the bank window")

    def test_pmbase_and_chbase_writers(self):
        pm, ch = [], []
        for f in glob.glob(os.path.join(ROOT, "src", "**", "*.[chs]"), recursive=True):
            with open(f, errors="replace") as fh:
                t = fh.read()
            rel = os.path.relpath(f, ROOT)
            if re.search(r"(0x|\$)D407\b", t, re.I):
                pm.append(rel)
            if re.search(r"(0x|\$)D409\b", t, re.I):
                ch.append(rel)
        self.assertEqual(pm, [], "PMBASE is set: check its area is outside $4000-$7FFF, then add it here")
        self.assertEqual(sorted(ch), ["src/sys/bootinfo.c"],
                         "a new CHBASE writer: check its font is outside $4000-$7FFF, then add it here")

    def test_6502_maps_leave_the_display_alone(self):
        seen = 0
        for m in MAPS:
            text = read(f"tools/bsp6502/{m}.scm")
            for name, lo, hi, placed in memories(text):
                seen += 1
                if overlaps(lo, hi, DISPLAY):
                    self.assertFalse(placed or m != "atari-banked",
                                     f"{m}.scm's {name} ${lo:04X}-${hi - 1:04X} is over the ANTIC display")
        self.assertGreater(seen, 20, "the maps' memories were not read")


if __name__ == "__main__":
    unittest.main()
