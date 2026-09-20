"""What is linked into the product, and under what licence.

docs/licence.md has the argument; this is the part a machine can check.
Two claims:

  * **no Apache-2.0 object is in any binary.**  Calypsi's C library
    carries the string and memory functions from Apache NuttX, and
    Apache 2.0 is incompatible with GPLv2 -- so src/sys/clib.c supplies
    them instead.  A `lib_*.o` coming back from the archive means
    somebody used a libc function this tree does not define, and the
    binary stopped being distributable.  That is not something to notice
    at release time.

  * **the vendor runtime has not grown.**  The compiler's own support
    code is still the vendor's.  It is distributable -- the GPL's System
    Library carve-out is written for "a compiler used to produce the
    work" -- but it is the one part of the binary without GPL source,
    and the set below is what the link needs TODAY.  A new name in it is
    something to look at, not a reason to edit this list without reading
    why.
"""
import glob
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BUILD = os.path.join(ROOT, "build")

# Håkan Thörngren's own runtime: "Permission to use with the Calypsi tool
# chain is hereby granted".  A System Library in the GPL's terms
# (docs/licence.md), and the only object code here without GPL source.
VENDOR_RUNTIME = {
    "pseudoRegisters.o", "integer.o", "controlFlow.o", "vswitch16.o",
    "memory.o", "memcpy_far.o", "memset_far.o", "spill.o", "initialize.o",
    "cstartup.o", "simplified_exit.o", "defaultExit.o",
    # Single-precision float, and in the TEST RUNNERS only -- m3, m3desk
    # and m6split, where a conformance case wants a float.  The shipped
    # GEM.COM has none: nothing in the VDI or the AES uses floating
    # point, which is worth keeping true (and this is where it would show
    # if it stopped being).
    "float32.o",
}

# What src/sys/clib.c exists to keep out.  NuttX names its files lib_*.c
# and Calypsi keeps the names, so the prefix IS the test -- but the
# assertion below is the stronger "nothing unlisted", and this is only
# here to name the offender when it fires.
NUTTX_PREFIX = "lib_"

UNIT = re.compile(r"^\s+\S+ in \((\S+\.o) \(from clib-lc-[sl]d\.a\)", re.M)


def maps():
    return sorted(glob.glob(os.path.join(BUILD, "*.map")))


def units(path):
    with open(path) as f:
        return set(UNIT.findall(f.read()))


@unittest.skipUnless(maps(), "no linker maps: build first")
class Licence(unittest.TestCase):
    def test_no_apache_2_object_is_linked(self):
        for m in maps():
            bad = sorted(u for u in units(m) if u.startswith(NUTTX_PREFIX))
            self.assertEqual(
                bad, [],
                f"{os.path.basename(m)} links Apache-2.0 NuttX object(s) "
                f"{bad} into a GPLv2 binary.  Add the function to "
                f"src/sys/clib.c rather than taking the library's -- "
                f"docs/licence.md says why.")

    def test_the_vendor_runtime_has_not_grown(self):
        for m in maps():
            extra = sorted(units(m) - VENDOR_RUNTIME)
            self.assertEqual(
                extra, [],
                f"{os.path.basename(m)} pulls {extra} from the vendor's "
                f"library, which docs/licence.md does not account for.  "
                f"Read that file before adding a name here.")

    def test_the_product_has_no_floating_point(self):
        """Not a licence claim but a budget one, and this is where the
        evidence already is: float32.o is 1.5 KB of far code the engine
        has never needed.  The runners may have it; GEM.COM may not."""
        for name in ("gem.map", "desktop.map", "calc.map", "clockacc.map",
                     "cpanelacc.map", "calcacc.map"):
            p = os.path.join(BUILD, name)
            if os.path.exists(p):
                self.assertNotIn("float32.o", units(p),
                                 f"{name} has pulled in floating point")

    def test_the_product_link_is_checked_at_all(self):
        """A skip-shaped pass is the failure mode this file could have:
        no maps, no claim.  GEM.COM's is the one that must be there."""
        self.assertTrue(os.path.exists(os.path.join(BUILD, "gem.map")),
                        "build/gem.map is missing, so the product's link "
                        "was not checked")

    def test_clib_defines_everything_the_product_calls(self):
        """The other direction: the eight names src/sys/clib.c claims."""
        with open(os.path.join(ROOT, "src", "sys", "clib.c")) as f:
            src = f.read()
        for name in ("memcpy", "memset", "strlen", "strcpy", "strcat",
                     "strcmp", "strncmp", "strchr"):
            self.assertRegex(src, r"\b" + name + r"\s*\(",
                             f"clib.c no longer defines {name}")
