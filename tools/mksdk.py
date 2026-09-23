#!/usr/bin/env python3
"""The gem4xe application kit: everything needed to build a program
that runs on gem4xe, and nothing of gem4xe itself.

    tools/mksdk.py build/gem4xe-sdk [--tar build/gem4xe-sdk.tar.gz]

An application links against no part of the system -- it reaches the
VDI, the AES and GEMDOS through three call gates and is loaded,
relocated and called at run time -- so the kit is small and its
contents are exactly the files that make that possible: the header,
the bindings and the start-up as SOURCE (built by the author's own
compiler, and readable), the linker's rules, the packer, and one whole
example.

The manifest below is the kit.  tests/host/test_sdk.py builds the
example out of a copy of the kit in a directory of its own, so a file
left out of this list is a gate failure rather than a discovery
somebody else makes.
"""
import argparse
import os
import shutil
import sys
import tarfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# (where it goes in the kit, where it comes from in the tree)
MANIFEST = [
    ("README.md",           "tools/sdk/README.md"),
    ("COPYING",             "COPYING"),
    ("Makefile",            "tools/sdk/Makefile"),
    ("include/gem.h",       "src/app/gem.h"),
    ("include/portab.h",    "src/portab.h"),
    ("include/sys/stat.h",  "src/app/sys/stat.h"),      # no <sys/> in Calypsi's libc
    ("include/time.h",      "src/app/time.h"),          # a 32-bit time_t: ccbug B20
    # The names an Atari ST source includes by reflex.  Most are one door
    # pointing at gem.h; <support.h> and <dirent.h> carry real code in
    # lib/gemcompat.c.  qed wrote every one of these in its own shim
    # before they were here, which is why they are here.
    ("include/osbind.h",    "src/app/osbind.h"),
    ("include/tos.h",       "src/app/tos.h"),
    ("include/mintbind.h",  "src/app/mintbind.h"),
    ("include/gemx.h",      "src/app/gemx.h"),
    ("include/macros.h",    "src/app/macros.h"),
    ("include/strings.h",   "src/app/strings.h"),
    ("include/support.h",   "src/app/support.h"),
    ("include/dirent.h",    "src/app/dirent.h"),
    ("include/mint/cookie.h", "src/app/mint/cookie.h"),  # a jar that answers "none"
    ("lib/gemlib.c",        "src/app/gemlib.c"),
    ("lib/gemstat.c",       "src/app/gemstat.c"),       # stat() over Fsfirst
    ("lib/gemtime.c",       "src/app/gemtime.c"),       # the clock, 32-bit throughout
    ("lib/gemcompat.c",     "src/app/gemcompat.c"),     # stricmp, opendir and the rest
    ("lib/gemstub.c",       "src/app/gemstub.c"),       # the C library's board stubs
    ("lib/clib.c",          "src/sys/clib.c"),
    ("lib/gemabi.s",        "src/app/gemabi.s"),
    ("lib/crt_gemapp.s",    "src/app/crt_gemapp.s"),
    ("lib/gemapp.scm",      "src/app/gemapp.scm"),
    # A control panel extension: the contract, and the main() you do not
    # write.  Both already lived in src/app/ -- the kit's own directory --
    # and were simply never handed out, so 0.6 shipped a feature nobody
    # outside this tree could build against.
    ("include/cpx.h",       "src/app/cpx.h"),
    ("lib/cpxmain.c",       "src/app/cpxmain.c"),
    ("tools/mkg4a.py",      "tools/mkg4a.py"),
    ("tools/mkxex.py",      "tools/mkxex.py"),   # mkg4a reads ELFs with it
    # ...and getting what you built onto a disk.  The kit used to name
    # tools/mkspdisk.py, which it did not contain and which needs a
    # SpartaDOS fixture nobody outside this tree has; install.py works on
    # the .atr the release already ships.
    ("tools/install.py",    "tools/sdk/install.py"),
    ("tools/atr.py",        "tools/atr.py"),     # install.py's file systems
    # The compiler's own defects, which are ordinary C shapes and will
    # bite a third party exactly as they bit this tree.  Four of them
    # produce a silently wrong answer.
    ("doc/ccbug.md",        "tools/ccbug/README.md"),
    ("example/hello.c",     "tools/sdk/hello.c"),
    ("example/acc.c",       "tools/sdk/acc.c"),       # a desk accessory
    ("example/cpx.c",       "tools/sdk/cpx.c"),       # a panel module
]


def build(out, tar=None):
    if os.path.isdir(out):
        shutil.rmtree(out)
    for dest, src in MANIFEST:
        d = os.path.join(out, dest)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, src), d)
    if tar:
        os.makedirs(os.path.dirname(tar) or ".", exist_ok=True)
        with tarfile.open(tar, "w:gz") as t:
            t.add(out, arcname=os.path.basename(out))
    n = sum(os.path.getsize(os.path.join(out, d)) for d, _ in MANIFEST)
    return n


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", nargs="?")
    ap.add_argument("--tar")
    ap.add_argument("--sources", action="store_true",
                    help="print the tree paths MANIFEST reads, for make")
    a = ap.parse_args(argv[1:])
    # The Makefile's prerequisite list IS this table, rather than a second
    # copy of it beside it.  It was a second copy until 0.6.1 and had
    # drifted: six files were in the kit and not in the list, so editing
    # one of them did not rebuild the kit.  This tree has a memory about
    # what happens when two lists say what ships.
    if a.sources:
        print(" ".join(sorted({src for _dst, src in MANIFEST}
                              | {"tools/mksdk.py"})))
        return 0
    if not a.out:
        ap.error("an output directory, or --sources")
    n = build(a.out, a.tar)
    print(f"{a.out}: {len(MANIFEST)} files, {n} bytes"
          + (f"; {a.tar}" if a.tar else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
