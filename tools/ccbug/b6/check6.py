#!/usr/bin/env python3
"""Build tools/ccbug/b6's cc6502 bugs with one or more Calypsi 6502
installs and run them in db6502, printing each bug beside the shape that
avoids it; then compile the three files that crash the compiler.

    python3 tools/ccbug/b6/check6.py [--calypsi DIR ...] [-O N ...]

The bugs are informational.  The exit status counts the workaround
shapes (the "fix:" lines) that came out wrong, because those are what
gem4xe's 6502 code relies on.
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRASHES = {
    "c8_member_addr.c": ("6502", "C8 (unsigned)&s.b"),
    "c9_inline_addr.c": ("6502", "C9 inlined return take(&local)"),
    "c10_bit255.c":     ("6502", "C10 if ((x, -1) < 0), --core 6502"),
}


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, **kw)


def one(cal, opt, d):
    b = lambda t: os.path.join(cal, "bin", t)
    objs = []
    for src in ("bugs6.c", "other.c", "fwd.c"):
        o = os.path.join(d, src[:-2] + ".o")
        r = run([b("cc6502"), "--core", "6502", f"-O{opt}", "-o", o,
                 os.path.join(HERE, src)])
        if r.returncode:
            sys.exit(f"{src} did not compile:\n{r.stdout}")
        objs.append(o)
    elf = os.path.join(d, "b6.elf")
    r = run([b("ln6502"), "--debug", "--semi-hosted", os.path.join(HERE, "linker.scm")]
            + objs + ["-o", elf, os.path.join(cal, "lib", "clib-6502.a")])
    if r.returncode:
        sys.exit(f"link failed:\n{r.stdout}")
    r = run([b("db6502"), "--nh", "--nx", "--core", "6502",
             "--terminate-on-program-exit", elf, "-e", "run"],
            stdin=subprocess.DEVNULL, timeout=300)
    if "END" not in r.stdout:
        sys.exit(f"the program did not finish:\n{r.stdout[-500:]}")
    return [ln for ln in r.stdout.splitlines() if ln.startswith("C")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calypsi", action="append")
    ap.add_argument("-O", action="append")
    a = ap.parse_args()
    cals = a.calypsi or [os.path.expanduser("~/dev/toolchains/calypsi-6502")]
    opts = a.O or ["0", "2"]
    bad_fix = 0
    for cal in cals:
        ver = run([os.path.join(cal, "bin", "cc6502"), "--version"]).stdout.splitlines()[0]
        for opt in opts:
            print(f"\n== {ver}, -O{opt}")
            with tempfile.TemporaryDirectory() as d:
                for ln in one(cal, opt, d):
                    print("  " + ln)
                    if " fix:" in ln and ln.endswith("WRONG"):
                        bad_fix += 1
        with tempfile.TemporaryDirectory() as d:
            for src, (core, note) in CRASHES.items():
                for opt in opts:
                    r = run([os.path.join(cal, "bin", "cc6502"), "--core", core,
                             f"-O{opt}", "-o", os.path.join(d, "x.o"),
                             os.path.join(HERE, src)])
                    ice = "internal error" in r.stdout
                    print(f"  {note:40s} -O{opt}  "
                          + ("internal error" if ice else
                             "compiles" if r.returncode == 0 else "error"))
    print(f"\ncheck6: {bad_fix} workaround shape(s) wrong")
    return bad_fix


if __name__ == "__main__":
    sys.exit(main())
