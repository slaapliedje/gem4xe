#!/usr/bin/env python3
"""farscan.py -- the 6502 build's far pointers, read by the host's clang
(docs/6502.md, step 4b).

On the 65C816 a FAR pointer is a 24-bit pointer and `p->field` reads
where it points.  On the 6502 there is no such pointer: what is beyond
64 KB is a PORTB bank in the $4000-$7FFF window, reached only through the
far_* helpers (src/sys6502/farmem6502.c), and src/portab.h defines FAR
away.  So `(TEDINFO FAR *)addr` compiles there, cuts the address to its
low 16 bits, and reads near memory -- silently: cc6502 warns of none of
it, an explicit cast least of all.  An object tree is worse: on the 6502
OBTREE is the 24-bit address as a number (src/aes/aes.h), so `tree + n`
compiles too, adding bytes where the 65C816 adds objects.

This reads every file the 6502 build compiles with the host's clang, the
6502's code paths chosen (__CALYPSI_TARGET_6502__, cc6502's headers, a
16-bit target), and two things changed for the scan only (src/portab.h,
src/aes/aes.h, under GEM4XE_FARSCAN):

  - FAR is clang's `noderef`: dereferencing a FAR pointer -- `p->f`,
    `p[i]`, `*p` -- is an error, and so is casting the attribute away.
    What is far on the 65C816 only for placement, and near on the 6502 --
    a device's table, a constant table, a block of the bank-$00 pool --
    is declared FAR_816 instead, on purpose, and is not reported;
  - OBTREE is a pointer to an incomplete struct: arithmetic on a tree,
    `tree->f`, and a tree taken as a number without a cast are errors.
    The OB_ macros and an explicit cast get by.

and -Wint-conversion and -Wincompatible-pointer-types are errors: a near
pointer handed where a far address or a tree goes.

NOT SEEN: an explicit cast of a FAR pointer to a plain one, `(T *)p`,
drops noderef without a word.  The self-test says so every run.

    python3 tools/bsp6502/farscan.py [FILE.c ...]   (default: the 6502 build's files)
    python3 tools/bsp6502/farscan.py --self-test     the shapes, found and not

Exit 1 when it finds one, when a file cannot be read, or when the
self-test finds the scan blind.  It needs a clang that knows the msp430
target (16-bit int and pointers, as the 6502 has) and cc6502's headers.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))

# the files the 6502 build compiles, and what the Makefile gives one of them
FILES = ["src/vdi/vdi.c", "src/vdi/dev_antic.c", "src/antic/antic.c", "src/vdi/font.c",
         "src/vdi/pointer.c", "src/vdi/fillpat.c", "src/vdi/sintbl.c", "src/sys/farmem.c",
         "src/sys6502/*.c", "src/v6_*.c", "src/f6_*.c", "src/aes/*.c"]
PER_FILE = {
    "src/vdi/dev_antic.c": ["-DGEM4XE_DEV_IMPL", "-DGEM4XE_DEV_PREFIX=and_",
                            "-DGEM4XE_DEV_ANTIC"],
    "src/sys6502/farmem6502.c": ["-DB6_CODE_BANKS=1"],
}
INCS = ["src", "src/vdi", "src/aes", "build", "src/sys", "src/antic"]
FLAGS = ["--target=msp430", "-fsyntax-only", "-std=gnu11", "-Wno-everything",
         "-Wnoderef", "-Werror=noderef", "-Werror=int-conversion",
         "-Werror=incompatible-pointer-types", "-ferror-limit=0",
         "-nostdinc", "-D__NATURAL_INT_SIZE__=8", "-D__CALYPSI__",
         "-D__CALYPSI_TARGET_6502__", "-DGEM4XE_FARSCAN", "-DGEM4XE_BANKED"]


def scan(path, root=ROOT):
    rel = os.path.relpath(os.path.abspath(path), root)
    incs = [a for d in INCS for a in ("-I", os.path.join(root, d))]
    r = subprocess.run(["clang", *FLAGS, "-isystem", os.path.join(CAL, "include"),
                        *PER_FILE.get(rel, []), *incs, path],
                       capture_output=True, text=True)
    errs = [ln for ln in r.stderr.splitlines() if ": error:" in ln or "fatal error" in ln]
    if r.returncode and not errs:
        errs = r.stderr.strip().splitlines()[:3] or [f"clang exit {r.returncode}"]
    return errs


# the self-test: each shape a line of a function in a scratch copy of
# the real headers' rules
# NOT SEEN, and said so: an explicit cast to a plain pointer drops
# noderef without a word -- `*(const char *)farptr` -- so a cast of a FAR
# pointer is still the reader's to check (grep for `FAR *)` casts).
BLIND = ["an explicit cast of a FAR pointer to a plain one: (T *)farptr"]

FIXTURE = r"""
#include "portab.h"
#include "aes/aes.h"
typedef struct { WORD a; WORD b; } PAIR;
static const uint8_t FAR_816 table[4] = { 1, 2, 3, 4 };
WORD shape_far_deref(uint32_t at) { PAIR FAR *p = (PAIR FAR *)at; return p->b; }
WORD shape_far_index(const char FAR *s) { return s[1]; }
OBTREE shape_tree_plus(OBTREE t) { return t + 1; }
WORD shape_tree_arrow(OBTREE t) { return t->ob_x; }
uint32_t shape_tree_number(OBTREE t) { uint32_t a = t; return a; }
OBTREE shape_near_tree(OBJECT *o) { OBTREE t = o; return t; }
WORD fine_far816(WORD i) { return table[i & 3]; }
WORD fine_ob_get(OBTREE t) { return OB_GET(t, 2, ob_x); }
OBTREE fine_ob_ptr(OBTREE t) { return OB_PTR(t, 1); }
uint32_t fine_cast(OBTREE t) { return (uint32_t)(uintptr_t)t; }
OBTREE fine_near(OBJECT *o) { return OB_NEAR(o); }
"""


def self_test():
    d = tempfile.mkdtemp(prefix="farscan-")
    try:
        path = os.path.join(d, "fixture.c")
        with open(path, "w") as f:
            f.write(FIXTURE)
        errs = scan(path)
        lines = FIXTURE.splitlines()
        hit = {}
        for e in errs:
            try:
                n = int(e.split(":")[1])
            except (IndexError, ValueError):
                print(f"farscan: self-test: unreadable: {e}")
                return 1
            name = lines[n - 1].split("(")[0].split()[-1]
            hit.setdefault(name, []).append(e)
        bad = 0
        for ln in lines:
            if "(" not in ln or not ln.split("(")[0].split():
                continue
            name = ln.split("(")[0].split()[-1]
            if name.startswith("shape_") and name not in hit:
                print(f"farscan: self-test: BLIND to {name}")
                bad += 1
            if name.startswith("fine_") and name in hit:
                print(f"farscan: self-test: reports {name}, which is right: {hit[name][0]}")
                bad += 1
        shapes = sum(1 for ln in lines if ln.split("(")[0].split()[-1:] and
                     ln.split("(")[0].split()[-1].startswith("shape_"))
        print(f"farscan: self-test: {shapes - bad if bad <= shapes else 0} of {shapes} "
              f"shapes found, {'clean' if not bad else str(bad) + ' problem(s)'}")
        for b in BLIND:
            print(f"farscan: self-test: not seen, by design: {b}")
        return 1 if bad else 0
    finally:
        shutil.rmtree(d, True)


def main(argv):
    if shutil.which("clang") is None:
        print("farscan: no clang on PATH")
        return 1
    if "--self-test" in argv:
        return self_test()
    files = argv[1:] or sorted({p for g in FILES for p in glob.glob(os.path.join(ROOT, g))})
    found = 0
    for p in files:
        errs = scan(p)
        for e in errs:
            print(e.replace(os.path.abspath(ROOT) + "/", ""))
        found += len(errs)
    print(f"farscan: {len(files)} file(s), {found} far access(es) the 6502 cannot make")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
