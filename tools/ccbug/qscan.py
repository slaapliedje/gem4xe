#!/usr/bin/env python3
"""qscan.py -- B27: a ?: whose arms are two FAR pointers that differ only
in qualifiers comes out NEAR (tools/ccbug/README.md, B27).

cc65816 gives `c ? p : q`, with p a `char __far *` and q a `const char
__far *`, the type `const char *` in BANK $00: both arms are cut to
their low sixteen bits and the bank byte is stored as zero.  Nothing is
said.  It surfaced in src/sys/doscmd.c only because one arm was a far
array linked above $FFFF, which the 16-bit relocation could not reach;
had both been in bank $00 the program would simply have read the wrong
bank.  The same arms with the same qualifiers, or arms whose types
differ by more than qualifiers (void against char), compile right.

THE RULE IS READ OFF THE ARMS, not off the type clang gives the ?:.
cc65816's front end is clang 10, and today's clang computes that type
differently from it -- for some of these shapes it keeps the address
space, for others it drops it as cc65816 does and then refuses to pass
the result to a far parameter.  So the C is read by the host's clang
with __far made an address space, and every conditional expression whose
two arms are both far pointers to the same type, but for const or
volatile, is reported -- the shape cc65816 was measured to break, and
the measurements are the self-test's cases.  It has to be a source scan:
the generated code cannot tell the bug from a near pointer widened on
purpose, which is `sta lo; stz hi` too.  The fix is a cast that makes
the arms' types agree, or an if.

    python3 tools/ccbug/qscan.py [FILE.c ...]     (default: every src/**/*.c)
    python3 tools/ccbug/qscan.py --self-test      the shapes, found and not

Exit 1 when it finds one, or when the self-test finds the scan blind.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FAR = "__attribute__((address_space(1)))"

# What the scan needs of Calypsi's own headers: names, not meaning.
FAKE_INTRINSICS = """
void __enable_interrupts(void);
void __disable_interrupts(void);
void *__memcpy_far();
"""

FLAGS = ["-fsyntax-only", "-std=gnu11", "-w", "-ferror-limit=0",
         "-D__CALYPSI__", f"-D__far={FAR}", "-D__near=",
         "-D__simple_call=", "-D__task=",
         "-Xclang", "-ast-dump=json"]


def type_of(node):
    t = node.get("type", {})
    return t.get("desugaredQualType", t.get("qualType", ""))


def arm_type(node):
    """An arm's own type: below the casts to the ?:'s composite type."""
    while node.get("kind") == "ImplicitCastExpr" and \
            node.get("castKind") in ("NoOp", "BitCast"):
        node = node["inner"][0]
    return type_of(node)


FAR_SPELLINGS = ("FAR", "__far", "__attribute__((address_space(1)))")
QUALS = ("const", "volatile")


def shape(t):
    """(far, the type's words without qualifiers or the far marker, its
    qualifiers) -- clang spells the address space by the macro that
    asked for it, so FAR, __far or the attribute."""
    words = t.replace("*", " * ").split()
    far = any(w in FAR_SPELLINGS for w in words) or "address_space(1)" in t
    base = tuple(w for w in words if w not in QUALS and w not in FAR_SPELLINGS
                 and "address_space" not in w)
    return far, base, tuple(sorted(w for w in words if w in QUALS))


def findings(tree, want_file):
    """(line, an arm's type, the other's) for each B27 shape in
    `want_file`.  Locations come as the JSON gives them: a field only
    when it changes, so the walk carries the last file and line seen."""
    out, last, here = [], {"file": None, "line": 0}, {"file": None, "line": 0}

    def bare_loc(loc):
        if "file" in loc:
            last["file"] = loc["file"]
        if "line" in loc:
            last["line"] = loc["line"]

    def note(loc):
        """Clang writes a macro's two places in turn, spelling then
        expansion, each leaving out what has not changed since the last
        place written -- so both are followed, and the expansion is
        where the code is (FAR is SPELT in a header)."""
        if not isinstance(loc, dict) or not loc:
            return
        if "spellingLoc" in loc or "expansionLoc" in loc:
            bare_loc(loc.get("spellingLoc", {}))
            bare_loc(loc.get("expansionLoc", {}))
        else:
            bare_loc(loc)
        here.update(last)

    def walk(n):
        if not isinstance(n, dict):
            return
        note(n.get("loc"))
        note(n.get("range", {}).get("begin"))
        line = here["line"]                 # where it starts ...
        note(n.get("range", {}).get("end"))  # ... and the state goes on
        if n.get("kind") == "ConditionalOperator" and len(n.get("inner", [])) == 3:
            a, b = arm_type(n["inner"][1]), arm_type(n["inner"][2])
            fa, ba, qa = shape(a)
            fb, bb, qb = shape(b)
            if (fa and fb and ba == bb and ba[-1:] == ("*",) and qa != qb
                    and here["file"]
                    and os.path.abspath(here["file"]) == os.path.abspath(want_file)):
                out.append((line, a.replace(FAR, "__far"),
                            b.replace(FAR, "__far")))
        for c in n.get("inner", []):
            walk(c)

    walk(tree)
    return out


def scan(path, inc):
    r = subprocess.run(["clang", *FLAGS, "-I", inc, "-I", os.path.join(ROOT, "src"),
                        "-I", os.path.join(ROOT, "src", "sys"),
                        "-I", os.path.join(ROOT, "build"), path],
                       capture_output=True, text=True)
    if not r.stdout.strip():
        return None, r.stderr.strip().splitlines()[:3]
    return findings(json.loads(r.stdout), path), None


def fake_dir():
    d = tempfile.mkdtemp(prefix="qscan-")
    os.makedirs(os.path.join(d, "calypsi"))
    with open(os.path.join(d, "calypsi", "intrinsics65816.h"), "w") as f:
        f.write(FAKE_INTRINSICS)
    return d


SELF = """
typedef struct { char line[8]; } S;
extern char __far *p, *p2;
extern const char __far *q;
extern const char __far m[];
extern int __far *ip;
extern const int __far *cip;
extern S __far *h;
void use(const volatile void __far *x);
void run(int c)
{
    use(c ? p : q);                       /* B27 */
    use(c ? &h->line[1] : m);             /* B27: what doscmd.c had */
    use(c ? ip : cip);                    /* B27 */
    use(c ? p : p2);                      /* fine: the same type */
    use(c ? (const char __far *)p : q);   /* fine: the cast agrees them */
    use(c ? (void __far *)p : q);         /* fine: void, not qualifiers */
}
"""


def self_test(inc):
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
        f.write(SELF)
        path = f.name
    got, err = scan(path, inc)
    os.unlink(path)
    lines = sorted(ln for ln, _, _ in got or [])
    ok = lines == [12, 13, 14]
    print(f"qscan self-test: found lines {lines}, want [12, 13, 14]: "
          f"{'ok' if ok else 'BLIND'}" + (f" ({err})" if err else ""))
    return ok


def main(argv):
    inc = fake_dir()
    if "--self-test" in argv:
        return 0 if self_test(inc) else 1
    files = [a for a in argv if not a.startswith("-")] or sorted(
        glob.glob(os.path.join(ROOT, "src", "**", "*.c"), recursive=True))
    if not self_test(inc):
        return 1
    bad = skipped = 0
    for path in files:
        got, err = scan(path, inc)
        if got is None:
            skipped += 1
            print(f"  {os.path.relpath(path, ROOT)}: not parsed ({err})")
            continue
        for line, a, b in got:
            bad += 1
            print(f"  {os.path.relpath(path, ROOT)}:{line}: ?: of {a} and {b} -- "
                  f"cc65816 makes it NEAR (B27)")
    print(f"qscan: {len(files)} files, {skipped} not parsed, {bad} B27 shape(s)")
    return 1 if bad or skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
