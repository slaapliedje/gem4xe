#!/usr/bin/env python3
"""Find a 24-bit address truncated into sixteen bits by an explicit cast.

WHY THIS EXISTS.  A resource's ob_spec, te_ptext, te_ptmplt, ib_ptext and
the rest are LONGs holding ADDRESSES.  While every resource lived in bank
$00 a program could take the low sixteen bits of one and be right, and a
great deal of code did, in the plainest way:

    TEDINFO *ted = (TEDINFO *)(uint16_t)tree[CDISP].ob_spec.index;
    char    *text = (char *)(uint16_t)ted->te_ptext;

Since 2026-09-19 that is not safe.  rs_load puts a resource in FAR memory
for any caller that can hold a 32-bit pointer (src/aes/rsrc.c), so in a
--data-model=large program those casts throw the bank away and the write
lands at the same offset in bank $00 -- on top of the engine.

IT DOES NOT ANNOUNCE ITSELF.  The calculator accessory hit exactly this
on 2026-09-20: no refused call, no BRK, no irq_fault; the desktop simply
came up to an hourglass on an empty desk, hung inside a GEMDOS call,
because show() had been writing its display over bank $00.  Fourteen of
these were found and fixed in one afternoon and the fourteenth was found
by bisecting disk images.  Hence a check rather than another afternoon.

WHAT IT SCANS.  Application-side code only -- the trees that are compiled
as a PROGRAM and may therefore be handed a far resource.  The engine
(src/aes, src/vdi, src/sys) is --data-model=small and owns its own near
trees: the file selector's and the alert's really are in bank $00, and
their casts are correct.  objc.c reads an application's tree and already
goes through SPEC_PTR.

HOW TO SAY A CAST IS DELIBERATE.  Put `nearcast-ok:` and a reason in a
comment on the same line.  There is no allowlist in this file, so a
reason travels with the code rather than rotting here.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# The trees that are compiled as an application.
SCAN = ("src/apps", "src/desk", "src/app")

# Fields that hold an ADDRESS in a LONG.  ob_spec is the union's `index`
# on this port (src/app/gem.h), so both spellings appear.
FIELDS = ("ob_spec", "te_ptext", "te_ptmplt", "te_pvalid",
          "ib_ptext", "ib_pdata", "ib_pmask", "bi_pdata",
          "mn_tree", "fd_addr")

# A cast that keeps sixteen bits, applied anywhere on a line that also
# names one of the fields above.
NARROW = re.compile(r"\(\s*(?:uint16_t|UWORD|WORD)\s*\)")
FIELD = re.compile("|".join(re.escape(f) for f in FIELDS))
OK = re.compile(r"nearcast-ok:")


def scan_file(path):
    out = []
    with open(path, "r", errors="replace") as f:
        for n, line in enumerate(f, 1):
            s = line.split("/*")[0].split("//")[0]     # code, not comment
            if not FIELD.search(s) or not NARROW.search(s):
                continue
            if OK.search(line):
                continue
            out.append((n, line.rstrip()))
    return out


def main(argv):
    quiet = "--quiet" in argv
    bad = []
    seen = 0
    for d in SCAN:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, names in os.walk(base):
            for name in sorted(names):
                if not name.endswith((".c", ".h")):
                    continue
                path = os.path.join(dirpath, name)
                seen += 1
                for n, line in scan_file(path):
                    rel = os.path.relpath(path, ROOT)
                    bad.append(f"{rel}:{n}: {line.strip()}")

    if not quiet:
        print(f"nearcast: {seen} application-side files scanned")
    if bad:
        print("\nA 24-bit address is being truncated to sixteen bits:")
        for b in bad:
            print(f"  {b}")
        print("\nThese fields hold ADDRESSES, and a --data-model=large "
              "program's resource\nlives in FAR memory (src/aes/rsrc.c).  "
              "Cast through (uint32_t) instead;\nit is correct in both "
              "models, because a near address zero-extends.\n"
              "If a cast really is deliberate, say why with `nearcast-ok:` "
              "on the line.")
        return 1
    if not quiet:
        print("nearcast: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
