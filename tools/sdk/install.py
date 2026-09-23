#!/usr/bin/env python3
"""Put what you built onto a gem4xe disk image.

    python3 tools/install.py gem4xe-0.6.1-apps.atr mine.g4a APPS>MINE.PRG
    python3 tools/install.py gem4xe-0.6.1.atr acc.g4a GEM>MINE.ACC
    python3 tools/install.py gem4xe-0.6.1.atr cpx.g4a GEM>MINE.CPX mine.rsc GEM>MINE.RSC
    python3 tools/install.py gem4xe-0.6.1-apps.atr --ls

WHY THIS EXISTS.  The kit used to say "in the gem4xe source tree, run
tools/mkspdisk.py" -- a tool the kit did not contain, needing a
SpartaDOS fixture disk nobody outside that tree has, to build a disk you
already have.  This works on the image the release ships, which is the
one you were going to boot anyway.

The image is modified IN PLACE unless you give --out, and a name that is
already there is replaced.  Keep a copy of the original: there is no
undo, and a full disk is a failed write rather than a smaller file.

WHERE THINGS GO, and it is not filing -- it decides whether the system
looks at them at all:

    GEM>NAME.PRG      a program, beside the system
    APPS>NAME.PRG     a program, in the applications folder
    GEM>NAME.ACC      a desk accessory.  \\GEM\\ ONLY: the AES scans its
                      own directory for *.ACC at start-up and nowhere
                      else, so an accessory in \\APPS\\ is never loaded
    GEM>NAME.CPX      a control panel extension, same rule
    GEM>AUTO>NAME.PRG run once at start-up, before the accessories
    GEM>NAME.RSC      a resource, beside whatever loads it: rsrc_load
                      takes a bare name and resolves it against the
                      system's directory

The EXTENSION is the role and the CONTAINER is always a .g4a -- one
build, installed under the name that says what it is.  The desktop reads
.PRG, .APP, .TOS, .TTP and .G4A as programs; anything else is a document
and double-clicking it offers Show, Print or Cancel.

A `>` is SpartaDOS's path separator and what these images use.  A plain
NAME with no `>` goes in the root.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atr import ATRImage, open_fs, ATRError          # noqa: E402


def parents(path):
    """'GEM>AUTO>X.PRG' -> ['GEM', 'GEM>AUTO'] -- the directories it needs."""
    parts = path.split(">")[:-1]
    return [">".join(parts[:i + 1]) for i in range(len(parts))]


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(__doc__.splitlines()[1:]))
    ap.add_argument("image", help="a gem4xe .atr, as the release ships")
    ap.add_argument("pairs", nargs="*", metavar="FILE NAME",
                    help="a local file and the name to store it under")
    ap.add_argument("--out", help="write here instead of in place")
    ap.add_argument("--ls", action="store_true",
                    help="list what is on the image and stop")
    a = ap.parse_args(argv[1:])

    try:
        img = ATRImage.load(a.image)
        fs = open_fs(img)
    except (OSError, ATRError) as e:
        print(f"{a.image}: {e}", file=sys.stderr)
        return 1

    if a.ls:
        # One level on a DOS 2 disk (it has no folders); the whole tree on
        # a SpartaDOS one, which is what the release ships.
        def walk(path=""):
            try:
                ents = fs.entries(path)
            except TypeError:                   # Dos2.entries takes no path
                for n in fs.list():
                    print(f"  {n}")
                return
            for e in ents:
                if not getattr(e, "in_use", True):
                    continue
                full = f"{path}>{e.filename}" if path else e.filename
                mark = ">" if e.is_dir else ""
                print(f"  {full}{mark}")
                if e.is_dir:
                    walk(full)
        walk()
        return 0

    if len(a.pairs) % 2:
        ap.error("every FILE needs a NAME after it")
    if not a.pairs:
        ap.error("nothing to install -- give a FILE and a NAME, or --ls")

    made = set()
    for src, name in zip(a.pairs[0::2], a.pairs[1::2]):
        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"{src}: {e}", file=sys.stderr)
            return 1
        # The directories first, and only the ones that are not there --
        # mkdir on an existing one is an error on these file systems.
        for d in parents(name):
            if d not in made:
                made.add(d)
                try:
                    fs.mkdir(d)
                except Exception:
                    pass                # already there, which is fine
        try:
            fs.add_file(name, data)
        except Exception as e:
            print(f"{name}: {e}", file=sys.stderr)
            print("  (a full disk looks like this; the apps floppy has "
                  "the most room)", file=sys.stderr)
            return 1
        print(f"  {name} <- {src} ({len(data)} bytes)")

    out = a.out or a.image
    img.save(out)
    print(f"{out}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
