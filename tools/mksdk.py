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
    ("tools/mkg4a.py",      "tools/mkg4a.py"),
    ("tools/mkxex.py",      "tools/mkxex.py"),   # mkg4a reads ELFs with it
    ("example/hello.c",     "tools/sdk/hello.c"),
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
    ap.add_argument("out")
    ap.add_argument("--tar")
    a = ap.parse_args(argv[1:])
    n = build(a.out, a.tar)
    print(f"{a.out}: {len(MANIFEST)} files, {n} bytes"
          + (f"; {a.tar}" if a.tar else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
