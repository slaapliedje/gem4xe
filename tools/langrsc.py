#!/usr/bin/env python3
"""LANG.RSC -- everything the SYSTEM says, in one file a translator ships.

    python3 tools/langrsc.py build/lang.rsc build/lang_rsc.c build/lang_rsc.h

Three outputs from one description, because the three must not disagree:

    lang.rsc      the file.  GEM.COM reads it at start-up and keeps it in
                  far memory; replacing it is how gem4xe is translated
                  (docs/shipping.md, section 5).
    lang_rsc.c    the same bytes as a `FAR` array: the English the
                  system falls back on when the file is not there, so a
                  disk without LANG.RSC still speaks.
    lang_rsc.h    the indices, so src/ and this file cannot disagree
                  about which string is which.

It is a real .RSC -- tools/rsc.py writes it, an RCS could open it -- with
free strings and nothing else.  No trees: the file selector's tree stays
in the far image (tools/fselrsc.py) because the selector copies its whole
resource into the application pool each time it opens, and 1 KB of alert
text would be 1 KB less for the application's own resource every time
(docs/phase11.md has that budget).  Widening a translated selector is
therefore still to do, and section 5 says so.

THE TEXTS are the donor's, from EmuTOS's gem_rsc.c by way of
src/aes/alert.c and src/aes/shel.c, where they were C literals until this
file existed.  Two rules for whoever translates them:

  * `|` breaks a line, `[n][text][buttons]` is form_alert's grammar, and
    the first `[n]` chooses the icon (0 none, 1 note, 2 question, 3 stop).
  * ST_ERRTOS carries the error number in the two digits after its `#`.
    fm_error writes them there by searching for the `#`, not by counting
    characters, so a translation may move the phrase but must keep one
    `#` followed by two digits.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsc                                              # noqa: E402

# The name on the disk, which src/aes/aes.h calls LANG_FILE.
FILENAME = "LANG.RSC"

# (name, text).  The order is the index order: appending is safe, and
# reordering is not -- build/lang_rsc.h is what the C uses.
STRINGS = [
    # form_error's five, by the DOS error it is given (src/aes/alert.c)
    ("ERRFILE", "[2][This application cannot|find the folder or file|"
                "you just tried to access.][  OK  ]"),
    ("ERRDOCS", "[1][This application does not|have room to open another|"
                "document.  To make room,|close any document that|"
                "you do not need.][  OK  ]"),
    ("ERREXIST", "[1][An item with this name|already exists in the|"
                 "directory, or this item|is set to Read Only status.][  OK  ]"),
    ("ERRDRIVE", "[1][The drive you specified|does not exist.][Cancel]"),
    ("ERRMEM", "[1][There is not enough memory|in your computer for the|"
               "application you just tried|to run.][  OK  ]"),
    ("ERRTOS", "[3][TOS error #00.][Cancel]"),
    # the shell, when it cannot run what it was asked for (src/aes/shel.c)
    ("APPNOTFOUND", "[1][This application|cannot be found.][ OK ]"),
    ("APPNOTLOAD", "[1][This application|cannot be loaded.][ OK ]"),
    ("APPOLDSDK", "[1][This application was built|for an older gem4xe.|"
                  "Rebuild it with the|current SDK.][ OK ]"),
    # the boot screen (src/sys/bootinfo.c): the labels down its left
    # column, and the few values that are words rather than the machine's
    # own names and numbers.  A label is cut at BOOT_LABEL columns there,
    # so a translation keeps them short.
    ("BOOT_VERSION", "Version"),
    ("BOOT_CPU", "Processor"),
    ("BOOT_MEMORY", "Memory"),
    ("BOOT_DOS", "DOS"),
    ("BOOT_CONFIG", "Settings"),
    ("BOOT_LANG", "Language"),
    ("BOOT_VIDEO", "Screen"),
    ("BOOT_CLOCK", "Clock"),
    ("BOOT_POINTER", "Pointer"),
    ("BOOT_PRINTER", "Printer"),
    ("BOOT_BUILTIN", "built in"),
    ("BOOT_DEFAULTS", "defaults"),
    ("BOOT_NONE", "none"),
    ("BOOT_PTR_ST", "ST mouse"),
    ("BOOT_PTR_AMIGA", "Amiga mouse"),
    ("BOOT_PTR_CX80", "CX80 trak-ball"),
    ("BOOT_PTR_TABLET", "touch tablet"),
    ("BOOT_PTR_XEM1", "mouSTer (XEM1)"),
    ("BOOT_BANKS", "banks"),
    ("BOOT_HOLD", "Hold SHIFT to pause this screen"),
    # the vectors line (src/sys/irq.h: how irq_install() reached them, or
    # why not), and the refusal that follows a "why not" on the way out
    ("BOOT_IRQ", "Vectors"),
    ("BOOT_IRQ_COPIED", "OS copied"),
    ("BOOT_IRQ_RAM", "OS in RAM"),
    ("BOOT_IRQ_NOCOPY", "copy failed"),
    ("BOOT_IRQ_NOVEC", "not kept"),
    ("EXIT_NOCOPY", "gem4xe: no RAM under the OS ROM"),
    ("EXIT_NOVEC", "gem4xe: the vectors did not take"),
    ("EXIT_NOIRQ", "gem4xe: no interrupt vectors installed"),
    ("EXIT_NOVBXE", "gem4xe: VIDEO=VBXE, but no VBXE found"),
    # the desktop never started (src/gem.c, exit_desk): which reason, the
    # memory it found when that was the reason, and -- on a cartridge,
    # where leaving is a cold start that would wipe the screen -- a wait
    ("EXIT_NOFAR", "gem4xe: the desktop needs more memory"),
    ("EXIT_FARKB", "KB of memory above bank $00"),
    ("EXIT_NOFILE", "gem4xe: DESKTOP.PRG is not on the disk"),
    ("EXIT_NODESK", "gem4xe: the desktop could not be loaded"),
    ("EXIT_ANYKEY", "Press a key to start again"),
]

# The longest string the system will ever copy into its near buffer, and
# the reason src/sys/lang.h can size that buffer without asking anyone.
MAXLEN = max(len(s) for _, s in STRINGS)
# The boot screen's labels, and the columns a label gets before it is cut
# (src/sys/bootinfo.c draws them; the other BOOT_ strings are values).
BOOT_LABELS = tuple("BOOT_" + n for n in
                    "VERSION CPU IRQ MEMORY DOS CONFIG LANG VIDEO CLOCK POINTER PRINTER".split())
BOOT_LABEL = 9
assert all(len(s) <= BOOT_LABEL for n, s in STRINGS if n in BOOT_LABELS), \
    "a boot-screen label is wider than its column"


def build(strings=None):
    r = rsc.Rsc()
    for _, s in (strings or STRINGS):
        r.free_string(s)
    return r


def c_source(data, path):
    lines = [f"/* {os.path.basename(path)}: LANG.RSC as the system falls back "
             f"on it, {len(data)} bytes.  Generated -- do not edit. */",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"const uint8_t FAR lang_rsc[{len(data)}] = {{"]
    for i in range(0, len(data), 12):
        lines.append("    " + ", ".join(f"0x{b:02X}" for b in data[i:i + 12]) + ",")
    lines.append("};")
    return "\n".join(lines) + "\n"


def c_header(data, path):
    lines = [f"/* {os.path.basename(path)}: what the system says, by index.  "
             "Generated -- do not edit. */",
             "#ifndef GEM4XE_LANG_RSC_H", "#define GEM4XE_LANG_RSC_H",
             "#include <stdint.h>", "#include \"portab.h\"",
             f"#define LANG_RSC_SIZE {len(data)}",
             f"#define LANG_NSTRING  {len(STRINGS)}",
             f"#define LANG_MAXLEN   {MAXLEN}",
             f"#define LANG_BOOT_LABEL {BOOT_LABEL}",
             "extern const uint8_t FAR lang_rsc[LANG_RSC_SIZE];"]
    lines += [f"#define LS_{name:<12s} {i}" for i, (name, _) in enumerate(STRINGS)]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    data = build().file()
    with open(argv[1], "wb") as f:
        f.write(data)
    for path, text in ((argv[2], c_source(data, argv[2])),
                       (argv[3], c_header(data, argv[3]))):
        with open(path, "w") as f:
            f.write(text)
    print(f"{argv[1]}: {len(data)} bytes, {len(STRINGS)} strings, "
          f"longest {MAXLEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
