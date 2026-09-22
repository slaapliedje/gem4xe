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
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
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
SLOT_FILE = 14                      # ...the module's file name, for CPX_Save
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


if __name__ == "__main__":
    unittest.main()
