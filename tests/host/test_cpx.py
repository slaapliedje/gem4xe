"""The CPX contract is written twice.  This is the third.

A control panel extension's table is described in two places that cannot
include each other: the AES is --data-model=small and knows the layout as
CPXE_INFO / CPXE_HDR / CPXE_SIZE (src/aes/shel.c), while an application
is --data-model=large and knows it as `struct CPXSLOT` (src/app/cpx.h).
The subject number appl_getinfo answers on is likewise AI_CPX in the AES
and AES_CPX in the kit.

Two files agreeing is not the same as being right, and this tree has a
memory about exactly that: a gate that diffs a model against a target
passes when both are wrong the same way.  So the numbers are stated a
THIRD time here, from the header's own documented map, and all three
must agree.

The map is the comment in src/app/cpx.h, which is Atari's field for
field.  It is read out of the comment rather than out of the struct on
purpose: sizeof on this compiler answers two different numbers for a
struct with a trailing array (B7, tools/ccbug), so the struct is not
allowed to be the authority for a FILE FORMAT.
"""
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import cpanelrsc                                    # noqa: E402
CPX_H = os.path.join(ROOT, "src", "app", "cpx.h")
GEM_H = os.path.join(ROOT, "src", "app", "gem.h")
SHEL_C = os.path.join(ROOT, "src", "aes", "shel.c")
APPL_C = os.path.join(ROOT, "src", "aes", "appl.c")

# Atari's header, stated here from the format and nowhere else.
HDR_SIZE = 512
HDR_FIELDS = [                      # (offset, bytes, name)
    (0, 2, "magic"), (2, 2, "flags"), (4, 4, "cpx_id"), (8, 2, "cpx_version"),
    (10, 14, "i_text"), (24, 96, "icon"), (120, 2, "i_info"),
    (122, 18, "title_txt"), (140, 2, "t_info"), (142, 64, "buffer"),
    (206, 306, "reserved"),
]
SUBJECT = 64                        # appl_getinfo's, gem4xe's own
SLOT_INFO = 4                       # a 32-bit CPXINFO address...
SLOT_FILE = 16                      # ...the file name, PADDED to 16 (B7)
SLOT_HDR = SLOT_INFO + SLOT_FILE    # ...then the header
SLOT_SIZE = SLOT_HDR + HDR_SIZE
HDR_BUF, HDR_BUFLEN = 142, 64       # the settings inside it


def text(path):
    with open(path, "r", errors="replace") as f:
        return f.read()


def define(src, name):
    m = re.search(rf"^#define\s+{name}\s+(\S+)", src, re.M)
    return None if not m else int(m.group(1), 0)


class CpxContract(unittest.TestCase):
    def test_the_header_map_adds_up(self):
        """Every field abuts the next and the last ends at 512.  A gap
        or an overlap here is a file format nobody can read."""
        at = 0
        for off, size, name in HDR_FIELDS:
            self.assertEqual(off, at, f"{name} starts at {off}, not {at}")
            at += size
        self.assertEqual(at, HDR_SIZE, f"the header is {at} bytes, not 512")

    def test_cpx_h_documents_that_map(self):
        """The comment in cpx.h is what a porter reads, so it is what
        has to be right -- and it is checked against the list above
        rather than against the struct beside it."""
        src = text(CPX_H)
        for off, _size, name in HDR_FIELDS:
            self.assertTrue(
                re.search(rf"^\s*\*\s*{off}\s+\S+\s+{re.escape(name)}\b",
                          src, re.M),
                f"src/app/cpx.h's map has no line for {name} at {off}")

    def test_the_header_size_agrees(self):
        self.assertEqual(define(text(CPX_H), "CPX_HDR_SIZE"), HDR_SIZE)
        self.assertEqual(define(text(SHEL_C), "CPX_HDR_SZ"), HDR_SIZE,
                         "the AES's copy of the header size has drifted")

    def test_the_slot_layout_agrees(self):
        """src/aes/shel.c lays the table out by hand; src/app/cpx.h lays
        it out as a struct.  Neither can include the other."""
        shel = text(SHEL_C)
        self.assertEqual(define(shel, "CPXE_INFO"), 0)
        self.assertEqual(define(shel, "CPXE_FILE"), SLOT_INFO,
                         "the file name does not follow the CPXINFO")
        self.assertEqual(define(shel, "CPXE_HDR"), SLOT_HDR,
                         "the header does not follow the file name")
        self.assertEqual(define(shel, "CPXH_BUF"), HDR_BUF,
                         "the AES's idea of where the settings are has "
                         "drifted from Atari's map")
        self.assertEqual(define(shel, "CPXH_BUFLEN"), HDR_BUFLEN)
        m = re.search(r"^#define\s+CPXE_SIZE\s+\(CPXE_HDR \+ CPX_HDR_SZ\)",
                      shel, re.M)
        self.assertTrue(m, "CPXE_SIZE is no longer CPXE_HDR + CPX_HDR_SZ")
        self.assertEqual(SLOT_HDR + HDR_SIZE, SLOT_SIZE)

    def test_the_subject_number_agrees(self):
        """AI_CPX in the AES, AES_CPX in the kit: one number, two files,
        and a program that asks the wrong one gets a truthful FALSE from
        an AES that does not know it -- which is the failure this would
        otherwise hide behind."""
        self.assertEqual(define(text(APPL_C), "AI_CPX"), SUBJECT)
        self.assertEqual(define(text(GEM_H), "AES_CPX"), SUBJECT)

    def test_the_subject_does_not_collide_with_atari(self):
        """Atari's subjects run 0..14.  A private one has to sit clear of
        where theirs could grow, or a future AES answers a different
        question to the same number."""
        gem = text(GEM_H)
        atari = [define(gem, n) for n in
                 ("AES_LARGEFONT", "AES_SMALLFONT", "AES_SYSTEM",
                  "AES_LANGUAGE", "AES_PROCESS", "AES_PCGEM", "AES_INQUIRE",
                  "AES_WDIALOG", "AES_MOUSE", "AES_MENU", "AES_SHELL",
                  "AES_WINDOW", "AES_MESSAGE", "AES_OBJECT", "AES_FORM")]
        self.assertNotIn(None, atari, "an Atari subject has been renamed")
        self.assertGreater(SUBJECT, max(atari) + 16,
                           f"subject {SUBJECT} is too close to Atari's "
                           f"highest ({max(atari)})")

    def test_every_vtable_entry_takes_one_address(self):
        """THE RULE THE COMPILER IMPOSES.  Calypsi's saveds switches to
        the callee's direct page before the body reads its arguments,
        which the caller left in ITS direct page -- so only the first
        argument survives, and not even that if it is a pointer.  Every
        entry therefore takes exactly one uint32_t.

        Checked on the HEADER, because that is the contract a porter
        writes against; a module with the wrong signature compiles and
        then reads garbage."""
        src = text(CPX_H)
        body = src[src.index("} XCPB;"):src.index("} CPXINFO;")]
        for m in re.finditer(r"\(\*(\w+)\)\(([^)]*)\)", body):
            name, args = m.group(1), m.group(2).strip()
            self.assertEqual(args, "uint32_t pb",
                             f"CPXINFO's {name} takes {args!r}; every entry "
                             f"must take one uint32_t (see the header)")

    def test_every_xcpb_callback_takes_one_address(self):
        """...and the same in the other direction: an XCPB callback runs
        in the PANEL and is called BY a module, which is the same
        cross-link call and the same rule."""
        src = text(CPX_H)
        body = src[src.index("typedef struct {"):src.index("} XCPB;")]
        found = 0
        for m in re.finditer(r"\(\*(\w+)\)\(([^)]*)\)", body):
            name, args = m.group(1), m.group(2).strip()
            self.assertEqual(args, "uint32_t xcpb",
                             f"XCPB's {name} takes {args!r}, not one address")
            found += 1
        self.assertGreater(found, 0, "no XCPB callbacks found to check")

    def test_every_vtable_entry_is_saveds(self):
        """A CPXINFO entry is called by the PANEL, across a link boundary,
        so each one has to establish its own direct page and data bank.
        The gate module is the worked example a porter copies, so if it
        stopped being saveds the example would teach the bug."""
        mod = text(os.path.join(ROOT, "src", "m35_cpx.c"))
        for fn in ("m35_cpx_call", "m35_cpx_draw", "m35_cpx_close",
                   "m35_cpx_key", "m35_cpx_button", "m35_cpx_timer"):
            self.assertTrue(
                re.search(rf"SAVEDS\s+\w[\w ]*\*?\s*{fn}\b", mod),
                f"{fn} is in a CPXINFO and is not SAVEDS")


class XGenAlert(unittest.TestCase):
    """The canned alerts, whose numbers are Atari's and whose words are
    the panel's.

    The Compendium's table for (*xcpb->XGen_Alert)() is stated here --
    a fourth place, on purpose -- because it is an ABI a ported module
    compiles against: a module that says XAL_FILE_ERR on an ST and gets
    the memory alert here is worse than one that gets nothing.
    """

    # Atari's, from the Compendium: SAVE_DEFAULTS 0, MEM_ERR 1,
    # FILE_ERR 2, FILE_NOT_FOUND 3.  Four, and no others.
    ATARI = [("XAL_SAVE_DEFAULTS", 0), ("XAL_MEM_ERR", 1),
             ("XAL_FILE_ERR", 2), ("XAL_FILE_NOT_FOUND", 3)]

    def setUp(self):
        self.h = text(CPX_H)

    def test_the_numbers_are_ataris(self):
        for name, want in self.ATARI:
            self.assertEqual(define(self.h, name), want,
                             f"{name} must be {want}: a module ported from "
                             f"an ST names the alert by number")

    def test_the_kit_and_the_resource_count_the_same_four(self):
        """src/apps/cpanel.c has the compile-time version of this and the
        build fails without it; this says so on a machine with no tool
        chain, and names the two so a reader can find them."""
        self.assertEqual(define(self.h, "XAL_NALERT"), len(self.ATARI))
        self.assertEqual(cpanelrsc.N_XALERT, len(self.ATARI),
                         "CPANEL.RSC carries a different number of alert "
                         "strings than cpx.h says there are")

    def test_each_number_has_a_string(self):
        """Indexed straight into the free strings from CPXAL0, so a gap
        would draw whatever string happened to be at that index."""
        have = {i for i, _name, _text in cpanelrsc.XALERTS}
        self.assertEqual(have, {n for _name, n in self.ATARI})
        self.assertEqual(cpanelrsc.CPXAL0, 0,
                         "the first alert is not the resource's first free "
                         "string, so cpanel.c's CPXAL0 + id is wrong")

    def test_each_string_is_an_alert_form_alert_can_parse(self):
        """[icon][text][buttons] -- the grammar fm_alert parses.  A
        translation that loses a bracket loses the alert entirely."""
        for _i, name, s in cpanelrsc.XALERTS:
            self.assertRegex(s, r"^\[[0-3]\]\[.+\]\[.+\]$", name)

    def test_only_alert_zero_asks_a_question(self):
        """The Compendium: XGen_Alert "returns TRUE if 'OK' was selected
        or FALSE if 'Cancel' was selected.  Alerts 1-3 always returns
        TRUE."  A one-button alert is what makes that true here rather
        than a special case in the panel -- form_alert can only answer 1
        when there is one button."""
        for i, name, s in cpanelrsc.XALERTS:
            buttons = s[s.rindex("][") + 2:-1].split("|")
            if i == 0:
                self.assertEqual(len(buttons), 2,
                                 f"{name} is the one alert that asks, so it "
                                 f"needs a second button to say no with")
            else:
                self.assertEqual(len(buttons), 1,
                                 f"{name} has {len(buttons)} buttons, so it "
                                 f"can answer something other than TRUE, "
                                 f"which the Compendium says it never does")

    def test_the_panel_publishes_it(self):
        """It was 0 for the whole of 0.6's development, which cpx.h
        allows and a module must cope with -- so nothing was refused and
        no gate went red while the callback did not exist."""
        panel = text(os.path.join(ROOT, "src", "apps", "cpanel.c"))
        self.assertRegex(
            panel, r"XGen_Alert\s*=\s*cp_gen_alert",
            "the panel does not hand out XGen_Alert, so every module that "
            "asks for an alert silently gets none")
        self.assertRegex(
            panel, r"SAVEDS\s+void\s+cp_gen_alert",
            "cp_gen_alert is called by a module across a link boundary "
            "and is not SAVEDS")

    def test_no_alert_text_is_in_the_c(self):
        """The point of a canned alert is that the panel owns the words,
        which is also the only way a translator reaches them."""
        for _i, _name, s in cpanelrsc.XALERTS:
            body = s[s.index("][") + 2:s.rindex("][")]
            for path in (CPX_H, os.path.join(ROOT, "src", "apps", "cpanel.c"),
                         os.path.join(ROOT, "src", "m35_cpx.c")):
                self.assertNotIn(body, text(path),
                                 f"{os.path.basename(path)} carries an "
                                 f"alert's words; they belong in CPANEL.RSC")


if __name__ == "__main__":
    unittest.main()
