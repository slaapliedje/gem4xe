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

B9, THE SECOND RULE: a scalar whose address is taken anywhere in a
function, given the value of a JOIN -- a ?:, !, && or ||, a comparison --
gets the wrong value, at every -O, -O0 included (README, B9).  The arms
leave the value in X and the store takes A:

    gt = app ? 2 : 4;   take(&gt);       ldx ##4 / ldx ##2 ... sta gt

Local, parameter, static or global alike; before, after or beside the
&; with the join inside the value too -- (c ? 2 : 4) + 1, f(c ? 2 : 4),
t |= c ? 8 : 0.  A struct field, an array element, and a variable whose
address is not taken compile right, so the rule is per function and per
variable, and it is read off the source because the generated code
cannot tell the store from a right one.  The fix is an if/else, or the
choice made into another local first.

AN INLINED FUNCTION'S RETURNS ARE A JOIN TOO (phase 138).  The panel's
Xform_do started its text cursor on object 32443 of a 41-object form:

    next = pb->xf_edit;
    if (!next)
        next = cp_firstedit(t);     /* return i; ... return 0; */
    ... form_button(t, next, nc, &next);

-O2 inlined cp_firstedit, left its answer in 1,s, and copied `next`
from 19,s, a slot nothing had written -- B9's own store, reached through
a call.  So a call counts as a join when the function is defined in the
same translation unit (a static, or an inline from a header) and has two
returns with values, or a return whose value has a join in it.

    python3 tools/ccbug/qscan.py [FILE.c ...]     (default: every src/**/*.c)
    python3 tools/ccbug/qscan.py --self-test      the shapes, found and not

Exit 1 when it finds one, or when the self-test finds the scan blind.
"""
import atexit
import glob
import json
import os
import shutil
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

# calypsi/stubs.h's nine entry points, which src/app/gemstub.c defines
FAKE_STUBS = """
#include <stdio.h>
int _Stub_open(const char *path, int oflag, ...);
int _Stub_close(int fd);
long _Stub_lseek(int fd, long offset, int whence);
int _Stub_fgetpos(int fd, fpos_t *pos);
int _Stub_fsetpos(int fd, const fpos_t *pos);
size_t _Stub_read(int fd, void *buf, size_t count);
size_t _Stub_write(int fd, const void *buf, size_t count);
int _Stub_rename(const char *oldpath, const char *newpath);
int _Stub_remove(const char *path);
void _Stub_exit(int status);
"""

# The host's <stdlib.h> brings in its struct timeval, which Calypsi's
# does not and gem.h declares for Tgettimeofday: the host's is renamed.
FAKE_STDLIB = """
#define timeval qscan_host_timeval
#define timezone qscan_host_timezone
#include_next <stdlib.h>
#undef timeval
#undef timezone
"""

# ...and its <stdio.h> a struct fpos_t, which is a number in Calypsi's
# and src/app/gemstub.c does arithmetic on
FAKE_STDIO = """
#define fpos_t qscan_host_fpos_t
#include_next <stdio.h>
#undef fpos_t
typedef long fpos_t;
"""

# The flags the Makefile gives one file and not the rest
PER_FILE = {
    "src/vdi/dev_vbxe.c": ["-DGEM4XE_DEV_IMPL", "-DGEM4XE_DEV_PREFIX=vbd_"],
    "src/vdi/dev_print.c": ["-DGEM4XE_DEV_IMPL", "-DGEM4XE_DEV_PREFIX=prd_",
                            "-DGEM4XE_DEV_PRINT"],
    "src/vdi/dev_antic.c": ["-DGEM4XE_DEV_IMPL", "-DGEM4XE_DEV_PREFIX=and_",
                            "-DGEM4XE_DEV_ANTIC"],
}

# -m32: four-byte pointers and longs, as the target's large data model
# has, so the headers' layout checks (cpx.h's CPXSLOT) hold here too
FLAGS = ["-fsyntax-only", "-m32", "-std=gnu11", "-w", "-ferror-limit=0",
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


JOIN_OPS = ("&&", "||", "==", "!=", "<", ">", "<=", ">=")


def strip(n):
    while n.get("kind") in ("ParenExpr", "ImplicitCastExpr") and n.get("inner"):
        n = n["inner"][0]
    return n


# name -> True when a call to that function is a join (b9_findings fills it
# per translation unit: defined here, and two returns with values or a
# return with a join in it)
JOINY = {}


def callee_name(n):
    """The name of the function a CallExpr calls directly, or None."""
    inner = n.get("inner") or [{}]
    d = strip(inner[0])
    if d.get("kind") != "DeclRefExpr":
        return None
    r = d.get("referencedDecl", {})
    return r.get("name") if r.get("kind") == "FunctionDecl" else None


def has_join(n):
    k = n.get("kind")
    if k == "ConditionalOperator" or k == "BinaryConditionalOperator":
        return True
    if k == "BinaryOperator" and n.get("opcode") in JOIN_OPS:
        return True
    if k == "UnaryOperator" and n.get("opcode") == "!":
        return True
    if k == "CallExpr" and JOINY.get(callee_name(n)):
        return True
    return any(has_join(c) for c in n.get("inner", []) if isinstance(c, dict))


def returns_of(fn):
    """The values of fn's return statements (not those of nested
    blocks' lambdas -- C has none)."""
    out = []

    def walk(n):
        if not isinstance(n, dict):
            return
        if n.get("kind") == "ReturnStmt" and n.get("inner"):
            out.append(n["inner"][0])
        for c in n.get("inner", []):
            walk(c)

    walk(fn)
    return out


def find_joiny(tree):
    """JOINY for this translation unit: every function with a body, to a
    fixed point, as one may return another's value."""
    rets = {}
    for n in tree.get("inner", []):
        if n.get("kind") == "FunctionDecl" and any(
                c.get("kind") == "CompoundStmt" for c in n.get("inner", [])):
            rets[n.get("name")] = returns_of(n)
    JOINY.clear()
    for name, rs in rets.items():
        if len(rs) >= 2:
            JOINY[name] = True
    changed = True
    while changed:
        changed = False
        for name, rs in rets.items():
            if not JOINY.get(name) and any(has_join(r) for r in rs):
                JOINY[name] = True
                changed = True


def var_of(n):
    """The id and name of the variable n names, or None: a scalar (not a
    record or array) VarDecl or ParmVarDecl."""
    n = strip(n)
    if n.get("kind") != "DeclRefExpr":
        return None
    d = n.get("referencedDecl", {})
    if d.get("kind") not in ("VarDecl", "ParmVarDecl"):
        return None
    t = d.get("type", {}).get("qualType", "")
    if "[" in t or t.startswith(("struct ", "union ")):
        return None
    return d.get("id"), d.get("name")


def b9_findings(tree, want_file):
    """(line, variable) for each B9 shape in `want_file`: per function,
    the variables whose address is taken, and the assignments to them of
    a value with a join in it."""
    out, last, here = [], {"file": None, "line": 0}, {"file": None, "line": 0}
    fns = []
    find_joiny(tree)

    def bare_loc(loc):
        if "file" in loc:
            last["file"] = loc["file"]
        if "line" in loc:
            last["line"] = loc["line"]

    def note(loc):
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
        line, f = here["line"], here["file"]
        note(n.get("range", {}).get("end"))
        k = n.get("kind")
        mine = f and os.path.abspath(f) == os.path.abspath(want_file)
        body = k == "FunctionDecl" and any(
            c.get("kind") == "CompoundStmt" for c in n.get("inner", []))
        if body:
            fns.append({"addr": set(), "set": []})
        if fns:
            ctx = fns[-1]
            if k == "UnaryOperator" and n.get("opcode") == "&":
                v = var_of(n["inner"][0])
                if v:
                    ctx["addr"].add(v[0])
            elif k in ("BinaryOperator", "CompoundAssignOperator") and \
                    n.get("opcode", "").endswith("=") and \
                    n.get("opcode") not in JOIN_OPS:
                v = var_of(n["inner"][0])
                if v and has_join(n["inner"][1]) and mine:
                    ctx["set"].append((line, v))
            elif k == "VarDecl" and n.get("init") and n.get("inner"):
                t = n.get("type", {}).get("qualType", "")
                if "[" not in t and not t.startswith(("struct ", "union ")) \
                        and has_join(n["inner"][0]) and mine:
                    ctx["set"].append((line, (n.get("id"), n.get("name"))))
        for c in n.get("inner", []):
            walk(c)
        if body:
            ctx = fns.pop()
            out.extend((ln, v[1]) for ln, v in ctx["set"] if v[0] in ctx["addr"])

    walk(tree)
    return out


# Every directory the Makefile hands the compiler with -I.  Without
# src/app, every application's gem.h was missing and every function in
# it was an invalid declaration clang left the body off -- so the scan
# read nothing in src/apps and said so with a zero (phase 138).  An error
# is now "not parsed", which fails the scan -- all but the one B27's own
# shape draws from today's clang (the docstring says why).
INCS = ["src", "src/sys", "build", "src/app", "src/apps", "src/vdi",
        "src/vbxe", "src/antic"]


def scan(path, inc):
    incs = [a for d in INCS for a in ("-I", os.path.join(ROOT, d))]
    own = PER_FILE.get(os.path.relpath(os.path.abspath(path), ROOT), [])
    r = subprocess.run(["clang", *FLAGS, *own, "-I", inc, *incs, path],
                       capture_output=True, text=True)
    # two errors are the far model's, not a failure to read the file: a
    # far pointer handed where a near one goes (B27's own shape), and a ?:
    # of a near and a far pointer, which a large-data program writes
    # because its plain pointers ARE far -- this clang cannot know that
    errs = [ln for ln in r.stderr.splitlines() if "error:" in ln
            and "changes address space of pointer" not in ln
            and "non-overlapping address spaces" not in ln]
    if not r.stdout.strip() or errs:
        return None, (errs or r.stderr.strip().splitlines())[:3]
    tree = json.loads(r.stdout)
    return (findings(tree, path), b9_findings(tree, path)), None


def fake_dir():
    d = tempfile.mkdtemp(prefix="qscan-")
    atexit.register(shutil.rmtree, d, True)
    os.makedirs(os.path.join(d, "calypsi"))
    with open(os.path.join(d, "calypsi", "intrinsics65816.h"), "w") as f:
        f.write(FAKE_INTRINSICS)
    with open(os.path.join(d, "calypsi", "stubs.h"), "w") as f:
        f.write(FAKE_STUBS)
    with open(os.path.join(d, "stdlib.h"), "w") as f:
        f.write(FAKE_STDLIB)
    with open(os.path.join(d, "stdio.h"), "w") as f:
        f.write(FAKE_STDIO)
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


# B9's shapes, each measured in the vendor's simulator at -O0 and -O2
# (README, B9): the BAD lines are found, the good ones are not.
SELF9 = """
extern int g, gt, tab[2];
int two(void);
int id(int x);
void take(int *p);
struct S { int a, b; };
void takes(int *p);
void bad(int app)
{
    int t, u, v, w, x;
    t = app ? 2 : 4;                      /* B9: & below */
    take(&t);
    gt = app ? two() : 4;                 /* B9: a global, & below */
    take(&gt);
    u = !app;                             /* B9 */
    if (g == 5) take(&u);
    v = (app ? 2 : 4) + 1;                /* B9 */
    take(&v);
    w = id(app > 1);                      /* B9 */
    take(&w);
    app |= g ? 8 : 0;                     /* B9: a parameter */
    take(&app);
    int y = app && g;                     /* B9: an initialiser */
    take(&y);
    x = app ? 2 : 4;                      /* fine: x's address is not taken */
    g = x;
}
static int first(int c) { if (c) return 7; return 0; }
static int one(int c) { return c + 1; }
static int pick(int c) { return c ? 2 : 4; }
void inl(int app)
{
    int n, m, k, j;
    n = first(app);                       /* B9: two returns, inlined */
    take(&n);
    k = pick(app);                        /* B9: a return with a join */
    take(&k);
    m = one(app);                         /* fine: one plain return */
    take(&m);
    j = first(app);                       /* fine: j's address is not taken */
    g = j;
}
void good(int app)
{
    int t, k;
    struct S s;
    int a[2];
    if (app) t = 2; else t = 4;           /* fine: no join in a value */
    take(&t);
    s.a = app ? 2 : 4;                    /* fine: a field */
    takes(&s.a);
    a[0] = app ? 2 : 4;                   /* fine: an element */
    take(a);
    k = app ? 2 : 4;                      /* fine: k's address is not taken */
    g = k;
}
"""
WANT9 = [11, 13, 15, 17, 19, 21, 23, 34, 36]


def self_test(inc):
    ok = True
    for name, src, want in (("B27", SELF, [12, 13, 14]), ("B9", SELF9, WANT9)):
        with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as f:
            f.write(src)
            path = f.name
        got, err = scan(path, inc)
        os.unlink(path)
        if got is None:
            lines = []
        elif name == "B27":
            lines = sorted(ln for ln, _, _ in got[0])
        else:
            lines = sorted(ln for ln, _ in got[1])
        good = lines == want
        ok = ok and good
        print(f"qscan self-test, {name}: found lines {lines}, want {want}: "
              f"{'ok' if good else 'BLIND'}" + (f" ({err})" if err else ""))
    return ok


def main(argv):
    inc = fake_dir()
    if "--self-test" in argv:
        return 0 if self_test(inc) else 1
    files = [a for a in argv if not a.startswith("-")] or sorted(
        glob.glob(os.path.join(ROOT, "src", "**", "*.c"), recursive=True))
    if not self_test(inc):
        return 1
    bad = bad9 = skipped = 0
    for path in files:
        got, err = scan(path, inc)
        if got is None:
            skipped += 1
            print(f"  {os.path.relpath(path, ROOT)}: not parsed ({err})")
            continue
        for line, a, b in got[0]:
            bad += 1
            print(f"  {os.path.relpath(path, ROOT)}:{line}: ?: of {a} and {b} -- "
                  f"cc65816 makes it NEAR (B27)")
        for line, name in got[1]:
            bad9 += 1
            print(f"  {os.path.relpath(path, ROOT)}:{line}: {name} is given a join's "
                  f"value and its address is taken -- cc65816 stores the wrong "
                  f"register (B9)")
    print(f"qscan: {len(files)} files, {skipped} not parsed, {bad} B27 shape(s), "
          f"{bad9} B9 shape(s)")
    return 1 if bad or bad9 or skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
