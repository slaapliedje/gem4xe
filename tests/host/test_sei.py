"""No SEI in native mode: irq_sei is the one way interrupts go off.

Windows Altirra's 65C816 (to 4.50-test21 at least) lets the one IRQ
through that arrives as an SEI, SEP #$04 or PLP sets I, and in native
mode never clears the flag that let it: the IRQ is taken again at the
handler's first fetch, and every fetch after, until the stack has
wrapped through bank $00.  With timer 1 at 4 kHz gem4xe hit it within a
minute on AtariAge after 0.9.2 (docs/phase82.md).  src/sys/sei.s's
irq_sei sets I with a COP instead, which an emulator gets right.

So every SEI and SEP that sets I in gem4xe's own sources is listed here,
with the reason it is safe -- emulation mode, where Altirra clears the
flag on the way into the handler, or I already set -- and a new one
fails this test until it is looked at.  C cannot write one at all:
__disable_interrupts() is the compiler's SEI, and cpu_sei() is irq_sei.
PLP is not listed: gem4xe's restore I to what the caller had, which is
a set I only when it was already set.
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (file, label the SEI follows) -> why it is safe
ALLOWED = {
    ("src/crt_atari.s", "ae_go"): "emulation mode, before the XCE",
    ("src/crt_atari.s", "_sys_exit"): "I is already set: irq_remove ran",
    ("src/farload.s", "fl_probe_dst"): "emulation mode, before the XCE",
    ("src/sys/cio.s", "cio_back"): "emulation mode, after the OS call",
}

SEI = re.compile(r"^\s*(?:[A-Za-z_.$0-9]+:)?\s*(sei|sep\s+#(0x)?([0-9a-fA-F]+))\b",
                 re.IGNORECASE)
LABEL = re.compile(r"^([A-Za-z_.][A-Za-z_.$0-9]*):")


def sources(exts):
    for top in ("src", os.path.join("tools", "sdk")):
        for d, _, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith(exts):
                    yield os.path.relpath(os.path.join(d, f), ROOT)


def sei_sites(path, text):
    label, found = None, []
    for n, line in enumerate(text.splitlines(), 1):
        code = line.split(";", 1)[0]
        m = LABEL.match(code)
        if m and not m.group(1)[0].isdigit():
            label = m.group(1)
        m = SEI.match(code)
        if not m:
            continue
        if m.group(1).lower().startswith("sep"):
            if not int(m.group(3), 16 if m.group(2) else 10) & 0x04:
                continue
        found.append((path, label, n))
    return found


class NoNativeSei(unittest.TestCase):
    def test_every_sei_is_accounted_for(self):
        seen = set()
        for path in sources((".s",)):
            with open(os.path.join(ROOT, path), errors="ignore") as f:
                for p, label, n in sei_sites(path, f.read()):
                    self.assertIn((p, label), ALLOWED,
                                  f"{p}:{n}: an SEI after {label}: in native "
                                  "mode use `jsl irq_sei` (src/sys/sei.s)")
                    seen.add((p, label))
        self.assertEqual(seen, set(ALLOWED),
                         "an allowed SEI is gone: take it off the list")

    def test_c_has_no_sei(self):
        for path in sources((".c", ".h")):
            with open(os.path.join(ROOT, path), errors="ignore") as f:
                text = f.read()
            if path == os.path.join("src", "portab.h"):
                self.assertIn("#define cpu_sei()    irq_sei()", text)
                continue
            self.assertNotIn("__disable_interrupts", text,
                             f"{path}: the compiler's SEI; use cpu_sei()")

    def test_the_scan_sees_one(self):
        # a check that passes by saying nothing is not believed until it
        # has been made to speak
        text = "foo:\n  lda #1\n  sei\nbar: sep #0x34\n  sep #0x30\n"
        self.assertEqual(sei_sites("x.s", text), [("x.s", "foo", 3), ("x.s", "bar", 4)])


if __name__ == "__main__":
    unittest.main()
