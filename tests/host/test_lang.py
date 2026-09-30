#!/usr/bin/env python3
"""LANG.RSC: what the system says, and the rules a translation must keep.

The file is built here rather than read out of build/, so these run on a
machine with no tool chain -- and so that what is checked is the
description in tools/langrsc.py, which is what src/ and the model both
work from.
"""
import os
import struct
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import aesref                                       # noqa: E402
import langrsc                                      # noqa: E402

HDR = "!HHHHHHHHHHhhhhhhhH"                         # the .RSC header, big-endian
HDR_SIZE = struct.calcsize(HDR)
FIELDS = ("vrsn object tedinfo iconblk bitblk frstr string imdata frimg "
          "trindex nobs ntree nted nib nbb nstring nimages rssize").split()


def header(data):
    return dict(zip(FIELDS, struct.unpack_from(HDR, data, 0)))


def strings_of(data):
    """Every free string, read the way src/aes/lang.c reads them: the
    offset table at rsh_frstr, four big-endian bytes an entry."""
    h = header(data)
    out = []
    for i in range(h["nstring"]):
        off = struct.unpack_from("!I", data, h["frstr"] + 4 * i)[0]
        end = data.index(b"\0", off)
        out.append(data[off:end].decode("latin1"))
    return out


class Resource(unittest.TestCase):
    def setUp(self):
        self.data = langrsc.build().file()

    def test_header_is_a_strings_only_resource(self):
        h = header(self.data)
        self.assertEqual(h["rssize"], len(self.data))
        self.assertEqual(h["nstring"], len(langrsc.STRINGS))
        self.assertEqual(h["vrsn"] & 4, 0)          # not the colour format
        self.assertEqual((h["ntree"], h["nobs"], h["nted"]), (0, 0, 0))

    def test_strings_are_the_description_in_order(self):
        self.assertEqual(strings_of(self.data), [s for _, s in langrsc.STRINGS])

    def test_maxlen_covers_the_longest(self):
        """src/sys buffers a string by LANG_MAXLEN, so it had better be
        the longest one there is."""
        self.assertEqual(langrsc.MAXLEN, max(len(s) for _, s in langrsc.STRINGS))

    def test_header_names_every_string_by_its_index(self):
        h = langrsc.c_header(self.data, "lang_rsc.h")
        for i, (name, _) in enumerate(langrsc.STRINGS):
            self.assertIn(f"#define LS_{name:<12s} {i}", h)
        self.assertIn(f"#define LANG_NSTRING  {len(langrsc.STRINGS)}", h)
        self.assertIn(f"#define LANG_MAXLEN   {langrsc.MAXLEN}", h)

    def test_the_fallback_array_is_the_file(self):
        """build/lang_rsc.c is the same bytes: a disk without LANG.RSC
        gets exactly what a disk with it gets."""
        c = langrsc.c_source(self.data, "lang_rsc.c")
        body = c[c.index("{") + 1:c.rindex("}")]
        got = bytes(int(t, 16) for t in body.replace("\n", "").split(",") if t.strip())
        self.assertEqual(got, self.data)

    def test_every_text_is_an_alert_or_a_label_or_a_line(self):
        """An alert is [icon][text][buttons], which is the grammar
        fm_alert parses -- a translation that loses a bracket loses the
        alert.  The boot screen's labels (BOOT_*) are plain text, cut at
        BOOT_LABEL columns, so one wider than that is a label that would
        never be read whole.  An EXIT_ line is printed on E: on the way
        back to DOS, one line of a 40-column screen with an EOL put after
        it, so it has no EOL of its own and fits the line."""
        for name, s in langrsc.STRINGS:
            if name.startswith("BOOT_"):
                self.assertNotIn("[", s, name)
                if name in langrsc.BOOT_LABELS:
                    self.assertLessEqual(len(s), langrsc.BOOT_LABEL, name)
            elif name.startswith("EXIT_"):
                self.assertNotIn("\x9b", s, name)
                # EXIT_FARKB has the kilobytes put in front of it, up to
                # five digits and a space (src/gem.c, exit_desk)
                self.assertLessEqual(len(s) + (6 if name == "EXIT_FARKB" else 0),
                                     40, name)
            else:
                self.assertRegex(s, r"^\[[0-3]\]\[.+\]\[.+\]$", name)

    def test_the_error_number_has_somewhere_to_go(self):
        """fm_error writes the number over the two characters after the
        '#', so ERRTOS must have one '#' and at least two after it."""
        s = dict(langrsc.STRINGS)["ERRTOS"]
        self.assertEqual(s.count("#"), 1)
        self.assertGreaterEqual(len(s) - s.index("#"), 3)


def german(name, text):
    """The English with a longer phrase in front of it, and ERRTOS with
    its number moved to the end -- a translation is a third longer than
    English as a rule, and it puts the words where it likes.  A boot
    label is cut to its column; a boot value just grows."""
    if name in langrsc.BOOT_LABELS:
        return ("Prozessor" if name == "BOOT_CPU" else text + "e")[:langrsc.BOOT_LABEL]
    if name.startswith("BOOT_"):
        return text + " (deutsch)"
    if name.startswith("EXIT_"):
        return ("gem4xe: " + text[len("gem4xe: "):] + " (de)")[:40]
    return ("[1][Diese Anwendung meldet einen Fehler|"
            + ("in der Ausfuehrung|Fehler Nummer #00" if name == "ERRTOS"
               else text[text.index("][") + 2:text.rindex("][")])
            + "][ Abbrechen ]")


class Translated(unittest.TestCase):
    """A translation is a different file with the same indices: longer
    strings, the phrases moved, the grammar kept."""

    STRINGS = [(name, german(name, text)) for name, text in langrsc.STRINGS]

    def setUp(self):
        self.data = langrsc.build(self.STRINGS).file()

    def test_it_reads_back(self):
        self.assertEqual(strings_of(self.data), [s for _, s in self.STRINGS])
        self.assertEqual(header(self.data)["nstring"], len(langrsc.STRINGS))

    def test_it_is_longer_than_the_english(self):
        """Which is the case the near buffer has to survive: the target
        refuses a resource with fewer strings than it asks for, not a
        bigger one, and far_strget truncates rather than overruns."""
        self.assertGreater(len(self.data), len(langrsc.build().file()))

    def test_it_keeps_the_rules_a_translation_must_keep(self):
        """The two a translator has to respect, on a translation that
        moves everything else: form_alert's grammar, and one '#' with
        room for two digits after it in ERRTOS."""
        for name, s in self.STRINGS:
            if name.startswith("EXIT_"):
                self.assertLessEqual(len(s), 40, name)
            elif not name.startswith("BOOT_"):
                self.assertRegex(s, r"^\[[0-3]\]\[.+\]\[.+\]$", name)
        s = dict(self.STRINGS)["ERRTOS"]
        self.assertEqual(s.count("#"), 1)
        self.assertGreaterEqual(len(s) - s.index("#"), 3)
        self.assertGreater(s.index("#"), dict(langrsc.STRINGS)["ERRTOS"].index("#"))


class Model(unittest.TestCase):
    """tools/aesref.py picks the same string for an error as src does."""

    WANT = {2: "ERRFILE", 3: "ERRFILE", 18: "ERRFILE", 4: "ERRDOCS",
            5: "ERREXIST", 15: "ERRDRIVE", 8: "ERRMEM", 10: "ERRMEM",
            11: "ERRMEM", 0: "ERRTOS", 63: "ERRTOS"}

    def test_the_map_is_the_targets(self):
        for n, name in self.WANT.items():
            self.assertEqual(aesref.AES.FM_ERRSTR.get(n, "ERRTOS"), name, n)

    def test_every_name_the_map_uses_exists(self):
        names = {name for name, _ in langrsc.STRINGS}
        for name in set(aesref.AES.FM_ERRSTR.values()) | {"ERRTOS"}:
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
