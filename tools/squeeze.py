#!/usr/bin/env python3
"""A file squeezed as a format 6 .G4A is: "G4A" 6, its length, one G4Z
stream (tools/mkg4a.py squeeze, src/sys/g4z.s).

    python3 tools/squeeze.py IN OUT

For the floppy that boots a DOS 2, whose 720 sectors are the tightest
place the system ships (phase 152): DESKTOP.RSC goes on it squeezed, 28
sectors to 11, and the AES unpacks it as it reads the desktop's resources
into their cache (src/aes/rsrc.c, rc_fill).  A file that would not come
out smaller is written as it is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkg4a                                            # noqa: E402


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[0], "rb") as f:
        data = f.read()
    out = mkg4a.squeeze(data) or data
    with open(argv[1], "wb") as f:
        f.write(out)
    print(f"{argv[1]}: {len(data)} bytes squeezed to {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
