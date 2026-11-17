#!/usr/bin/env python3
"""b6scan.py -- cc6502's byte conversions, read by the host's clang
(docs/6502.md; the measurements are tools/bsp6502/b6cast.py's).

Calypsi cc6502 5.18 gets a value narrowed to a byte and then widened
again wrong, at every -O, and says nothing.  Two faults, both measured
in the vendor's simulator (python3 tools/bsp6502/b6cast.py: -O0, -O1 and
-O2, every byte value in the first sweeps, nine around bit 7 since):

  A, THE HIGH BYTE IS $FF.  A COMPUTED value of SIGNED type -- int, a
     promoted byte or signed char, long -- narrowed to uint8_t and widened
     comes out sign-extended: `ora #127; bmi; lda #0` where a zero
     belongs.  (uint8_t)(k + 1) is -111 for k = $90.  + - & | ^ ~,
     unary -, << all do it, `& 0xFF` too: (uint8_t)(w & 0xFF) is the
     common shape.  (char) too: plain char is unsigned on cc6502.  An
     UNSIGNED int operand is right ((uint8_t)(k + 1u), (uint8_t)(u + 1)
     with u unsigned), and so are a plain load, a call's result, a ?:, a
     comma, and * / % (library calls).  So is a value that cannot have
     bit 7 set: masked below $80, or a truth value (== < && ! ...).  >> is right but on a signed char.  A
     cast to SIGNED char is right: sign extension is what it wants.

  B, BITS 8-15 SURVIVE.  A 32-bit value, signed or unsigned, narrowed to
     a byte -- unsigned or signed char -- and widened keeps its low
     SIXTEEN bits: (uint8_t)l with l = $12345690 is $5690.  A load does
     it, `& 0xFF`, ?:, / and >>; signed arithmetic gets fault A instead.
     Right: an unsigned value shifted right 24 or more or masked below
     $FF, which leave nothing in bits 8-15, and unsigned + - * | ^ ~ <<
     (reported anyway -- the self-test's over_ lines say why).

ONLY THE HIGH BYTE IS WRONG; the low one always holds the right value.
So the scan follows a widened byte to where it is USED, and reports it
only where the high byte can matter -- a comparison, an index, a return
or argument or variable that is wider than a byte, a switch, / and %.
Carried back into a byte by + - * & | ^ ~ << it is right (measured),
masked below $FF it is right, shifted right or tested for truth it is
right.  `& 0xFF` is NOT a rescue: cc6502 takes it for a no-op on a byte
and drops it, and the scan carries straight through one.

The fix is a byte that has been STORED: `uint8_t t = k + 1;` (or a cast
into it) then t; a byte global or parameter, or a byte returned from a
function in another file, is right too.

The routes into a widened byte, each one measured:
  - an explicit cast, or a chain of them, widened by anything: a return,
    an argument, an int variable, arithmetic, a comparison, a switch, an
    array index, the arm of a ?: -- REPORTED;
  - a function in the same file returning a byte its return narrowed,
    called where the result is widened: -O2 inlines it and the stored
    byte is gone -- REPORTED (right at -O0; the build is -O2);
  - a byte assignment's value used, `(t = k + 1)`, ++ and += on a byte,
    and a byte parameter of a function -O2 inlines -- measured RIGHT,
    and not followed.
The flags below hold those.  The self-test holds the scan to its
fixture; `b6cast.py` holds the scan to the compiler, by running both on
the same 92 shapes and failing on any disagreement.

    python3 tools/bsp6502/b6scan.py [--root DIR] [FILE.c ...]
                                       (default: the 6502 build's files)
    python3 tools/bsp6502/b6scan.py --self-test

Exit 1 when it finds one, when a file cannot be parsed, or when the
self-test finds the scan blind or noisy.  It needs a clang that knows
the msp430 target (16-bit int and pointers, 32-bit long, as cc6502 has)
and cc6502's headers; plain char is unsigned on cc6502, and so here.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))

# The files the 6502 build compiles, and what the Makefile gives one of
# them: farscan.py's list, which is the build's.
FILES = ["src/vdi/vdi.c", "src/vdi/dev_antic.c", "src/antic/antic.c", "src/vdi/font.c",
         "src/vdi/pointer.c", "src/vdi/fillpat.c", "src/vdi/sintbl.c", "src/sys/farmem.c",
         "src/sys6502/*.c", "src/v6_*.c", "src/f6_*.c", "src/a6_*.c", "src/c6_*.c", "src/i6_*.c",
         "src/aes/*.c", "src/sys/abi.c", "src/sys/cio.c", "src/p6_prog.c", "src/app/gemlib.c",
         "src/sys/gemdos.c", "src/sys/dos.c", "src/sys/con.c", "src/sys/clock.c"]   # 5b-4
PER_FILE = {
    "src/vdi/dev_antic.c": ["-DGEM4XE_DEV_IMPL", "-DGEM4XE_DEV_PREFIX=and_",
                            "-DGEM4XE_DEV_ANTIC"],
    "src/sys6502/farmem6502.c": ["-DB6_CODE_BANKS=1"],
    # a program built with the kit (docs/6502.md, step 5): its headers
    "src/p6_prog.c": ["-Isrc/app"],
    "src/app/gemlib.c": ["-Isrc/app"],
}
INCS = ["src", "src/vdi", "src/aes", "build", "src/sys", "src/antic"]
FLAGS = ["--target=msp430", "-fsyntax-only", "-std=gnu11", "-w", "-funsigned-char",
         "-ferror-limit=0", "-nostdinc", "-D__NATURAL_INT_SIZE__=8", "-D__CALYPSI__",
         "-D__CALYPSI_TARGET_6502__", "-DGEM4XE_BANKED", "-Xclang", "-ast-dump=json"]

# What b6cast.py measured of the routes other than a cast.  True: the
# route is broken and the scan follows it.  Change one only with a
# measurement; the self-test holds the scan to these.
ASSIGN_BROKEN = False
INLINE_RET_BROKEN = True
INLINE_PAR_BROKEN = False

# ---------------------------------------------------------------- types

INT_BITS = {"char": 8, "signed char": 8, "unsigned char": 8,
            "short": 16, "unsigned short": 16, "int": 16, "unsigned int": 16,
            "long": 32, "unsigned long": 32, "long long": 64, "unsigned long long": 64}
SIGNED = {"signed char", "short", "int", "long", "long long"}
NORMAL = {"short int": "short", "unsigned short int": "unsigned short",
          "long int": "long", "unsigned long int": "unsigned long", "unsigned": "unsigned int",
          "long long int": "long long", "unsigned long long int": "unsigned long long",
          "signed": "int", "signed int": "int", "short unsigned int": "unsigned short",
          "long unsigned int": "unsigned long"}


def ctype(node):
    t = node.get("type", {})
    s = t.get("desugaredQualType", t.get("qualType", ""))
    words = [w for w in s.split() if w not in ("const", "volatile")]
    s = " ".join(words)
    s = NORMAL.get(s, s)
    if s.startswith("enum "):
        return 16, True
    if s in INT_BITS:
        return INT_BITS[s], s in SIGNED
    return None


def is_ubyte(node):
    t = ctype(node)
    return t is not None and t[0] == 8 and not t[1]


def is_byte(node):
    t = ctype(node)
    return t is not None and t[0] == 8


def strip_parens(n):
    while n.get("kind") == "ParenExpr" and n.get("inner"):
        n = n["inner"][0]
    return n


LOADS = ("DeclRefExpr", "MemberExpr", "ArraySubscriptExpr", "IntegerLiteral",
         "CharacterLiteral", "CallExpr", "UnaryExprOrTypeTraitExpr", "StmtExpr")
FINE_OPS = ("*", "/", "%", ",")    # library calls, and a comma's value is its right


def plain(n):
    """A value cc6502 narrows right when it is 16 bits or less: a load,
    a literal, a call's result, a deref, a ?: or comma of such, and
    integral promotions of them."""
    n = strip_parens(n)
    k = n.get("kind")
    if k == "ImplicitCastExpr" or k == "CStyleCastExpr":
        return plain(n["inner"][0]) if n.get("inner") else True
    if k in LOADS:
        return True
    if k == "UnaryOperator" and n.get("opcode") == "*":
        return True
    if k == "ConditionalOperator":
        return True           # measured: (U8)(c ? k + 1 : 0) is right
    if k == "BinaryOperator" and n.get("opcode") == ",":
        return True           # measured: (U8)(c, k + 1) is right
    return False


def narrowing_fault(x, to_signed=False):
    """The fault a value `x`, narrowed to a byte and widened, meets: 'A',
    'B' or None.  A signed char destination meets only B."""
    t = ctype(x)
    if t is None:
        return None
    bits, signed = t
    xs = strip_parens(x)
    op = xs.get("opcode") if xs.get("kind") == "BinaryOperator" else None
    kids = xs.get("inner", [])
    if bits >= 32:
        # no bits 8-15 to survive, measured: an unsigned value shifted
        # right 24 or more, or masked below $FF (not BY $FF: dropped)
        if not signed and op == ">>" and (const_value(kids[1]) or 0) >= 24:
            return None
        if not signed and op == "&" and any(0 <= (const_value(k) if const_value(k)
                                                  is not None else -1) < 0xFF for k in kids):
            return None
        return "B"            # the rest: see the self-test's over_ lines
    if to_signed or not signed or plain(x):
        return None
    if op in FINE_OPS:
        return None
    # bit 7 never set, measured: a truth value is 0 or 1
    if op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||") or (
            xs.get("kind") == "UnaryOperator" and xs.get("opcode") == "!"):
        return None
    # bit 7 never set, measured: masked below $80
    if op == "&" and any(0 <= (const_value(k) if const_value(k) is not None else -1) < 0x80
                         for k in kids):
        return None
    # a right shift is right unless what is shifted was a signed char
    if op == ">>" and not (is_byte(unpromoted(kids[0])) and not is_ubyte(unpromoted(kids[0]))):
        return None
    return "A"


def unpromoted(n):
    """n below its integral promotion: what the program wrote."""
    n = strip_parens(n)
    while n.get("kind") == "ImplicitCastExpr" and n.get("castKind") in (
            "IntegralCast", "LValueToRValue") and n.get("inner"):
        n = strip_parens(n["inner"][0])
    return n


def source_fault(n, ctx):
    """Follow a byte-typed expression `n` down to where it was narrowed;
    the fault, and the line, if it is one of the measured shapes."""
    n = strip_parens(n)
    k = n.get("kind")
    if k in ("ImplicitCastExpr", "CStyleCastExpr") and n.get("inner"):
        x = n["inner"][0]
        if is_byte(n) and (ctype(x) or (0, 0))[0] > 8:
            f = narrowing_fault(x, to_signed=not is_ubyte(n))
            return (f, "cast" if k == "CStyleCastExpr" else "conversion") if f else None
        if is_ubyte(x) or ctype(x) and ctype(x)[0] == 8:
            return source_fault(x, ctx)
        return None
    if k == "BinaryOperator" and n.get("opcode") == "=" and ASSIGN_BROKEN:
        return source_fault(n["inner"][1], ctx)
    if k == "CallExpr" and INLINE_RET_BROKEN:
        name = callee(n)
        if name in ctx["byteret"]:
            return (ctx["byteret"][name], f"return of {name}(), inlined")
    if k == "ConditionalOperator":
        return source_fault(n["inner"][1], ctx) or source_fault(n["inner"][2], ctx)
    return None


TRANSPARENT = ("+", "-", "*", "&", "|", "^", "<<")   # the low byte goes through


def const_value(n):
    n = strip_parens(n)
    while n.get("kind") in ("ImplicitCastExpr", "CStyleCastExpr") and n.get("inner"):
        n = strip_parens(n["inner"][0])
    if n.get("kind") in ("IntegerLiteral", "CharacterLiteral"):
        try:
            return int(n.get("value"), 0) if isinstance(n.get("value"), str) else int(n["value"])
        except (TypeError, ValueError, KeyError):
            return None
    return None


def where_used(path):
    """Follow a widened byte, path[-1], up through its ancestors path[:-1]
    to the use that decides: None when only its low byte can reach it
    (narrowed again, masked below $FF, shifted right, tested for truth,
    discarded), or a word for where the high byte does."""
    cur = path[-1]
    for par in reversed(path[:-1]):
        k = par.get("kind")
        kids = par.get("inner", [])
        first = kids and kids[0] is cur
        if k == "ParenExpr":
            pass
        elif k in ("ImplicitCastExpr", "CStyleCastExpr"):
            ck = par.get("castKind")
            t = ctype(par)
            if ck == "IntegralToBoolean":
                return None
            if t is None:
                return "a conversion"
            if t[0] == 8:
                return None                       # narrowed: the low byte only
        elif k == "BinaryOperator":
            op = par.get("opcode")
            if op == "&":
                other = kids[1] if first else kids[0]
                c = const_value(other)
                if c is not None and 0 <= c < 0xFF:
                    return None                   # masked below $FF
            if op in TRANSPARENT:
                if op == "<<" and not first:
                    return "a shift count"
            elif op == ">>":
                return None if first else "a shift count"
            elif op in ("&&", "||"):
                return None
            elif op == ",":
                if first:
                    return None
            elif op in ("==", "!=", "<", ">", "<=", ">="):
                return "a comparison"
            elif op in ("/", "%"):
                return "a division"
            elif op == "=":
                return "an assignment wider than a byte"
            else:
                return f"`{op}`"
        elif k == "CompoundAssignOperator":
            return "an assignment wider than a byte"
        elif k == "UnaryOperator":
            op = par.get("opcode")
            if op == "!":
                return None
            if op not in ("~", "-", "+"):
                return f"`{op}`"
        elif k == "ConditionalOperator":
            if first:
                return None                       # its truth
        elif k in ("IfStmt", "WhileStmt", "DoStmt", "ForStmt"):
            return None if cur is not None and k != "ForStmt" else "a loop"
        elif k == "ReturnStmt":
            return "a return wider than a byte"
        elif k == "CallExpr":
            return "an argument wider than a byte"
        elif k == "ArraySubscriptExpr":
            return "an index"
        elif k == "VarDecl":
            return "a variable wider than a byte"
        elif k == "SwitchStmt":
            return "a switch"
        elif k in ("CompoundStmt", "NullStmt"):
            return None                           # a value discarded
        else:
            return f"a {k}"
        cur = par
    return "its use"


def callee(n):
    d = strip_parens(n["inner"][0]) if n.get("inner") else {}
    while d.get("kind") == "ImplicitCastExpr" and d.get("inner"):
        d = d["inner"][0]
    r = d.get("referencedDecl", {}) if d.get("kind") == "DeclRefExpr" else {}
    return r.get("name") if r.get("kind") == "FunctionDecl" else None


def returns_of(fn):
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "ReturnStmt" and n.get("inner"):
                out.append(n["inner"][0])
            for c in n.get("inner", []):
                walk(c)
    walk(fn)
    return out


def has_body(fn):
    return any(c.get("kind") == "CompoundStmt" for c in fn.get("inner", []))


def ret_type_ubyte(fn):
    q = fn.get("type", {}).get("qualType", "")
    r = q.split("(")[0].strip()
    return {"type": {"qualType": r}}


def scan_tree(tree, want_file):
    """(line, fault, how) for each shape in want_file."""
    ctx = {"byteret": {}, "bytepar": {}}
    # functions with bodies here: a byte return a narrowing feeds, and
    # byte parameters, both of which -O2 can inline into a widened use
    for fn in tree.get("inner", []):
        if fn.get("kind") != "FunctionDecl" or not has_body(fn):
            continue
        rt = ret_type_ubyte(fn)
        # the return type's desugared spelling is not in the JSON; a
        # return value's own implicit cast says what it is converted to
        for r in returns_of(fn):
            r = strip_parens(r)
            if r.get("kind") == "ImplicitCastExpr" and is_byte(r) and r.get("inner") \
                    and (ctype(r["inner"][0]) or (0, 0))[0] > 8:
                f = narrowing_fault(r["inner"][0], to_signed=not is_ubyte(r))
                if f:
                    ctx["byteret"][fn.get("name")] = f
        pars = [c for c in fn.get("inner", []) if c.get("kind") == "ParmVarDecl"]
        ctx["bytepar"][fn.get("name")] = [is_ubyte(p) for p in pars]
        del rt

    out = []
    last = {"file": None, "line": 0}
    here = {"file": None, "line": 0}

    def bare(loc):
        if "file" in loc:
            last["file"] = loc["file"]
        if "line" in loc:
            last["line"] = loc["line"]

    def note(loc):
        if not isinstance(loc, dict) or not loc:
            return
        if "spellingLoc" in loc or "expansionLoc" in loc:
            bare(loc.get("spellingLoc", {}))
            bare(loc.get("expansionLoc", {}))
        else:
            bare(loc)
        here.update(last)

    def mine():
        return here["file"] and os.path.abspath(here["file"]) == os.path.abspath(want_file)

    path = []

    def walk(n):
        if not isinstance(n, dict):
            return
        note(n.get("loc"))
        note(n.get("range", {}).get("begin"))
        line, is_mine = here["line"], mine()
        note(n.get("range", {}).get("end"))
        k = n.get("kind")
        path.append(n)
        if is_mine and k in ("ImplicitCastExpr", "CStyleCastExpr") and n.get("inner"):
            x = n["inner"][0]
            t = ctype(n)
            if t and t[0] > 8 and is_byte(x):           # a byte, widened
                f = source_fault(x, ctx)
                use = f and where_used(path)
                if use:
                    out.append((line, f[0], f"{f[1]}, then {use}"))
        if is_mine and k == "ArraySubscriptExpr" and len(n.get("inner", [])) == 2:
            for idx in n["inner"]:
                if is_byte(idx):                         # an index is widened too
                    f = source_fault(idx, ctx)
                    if f:
                        out.append((line, f[0], f[1] + ", then an index"))
        if is_mine and k == "CallExpr" and INLINE_PAR_BROKEN:
            name = callee(n)
            flags = ctx["bytepar"].get(name)
            if flags:
                for a, isb in zip(n.get("inner", [])[1:], flags):
                    if isb:
                        f = source_fault(a, ctx)
                        if f:
                            out.append((line, f[0], f"{f[1]} into {name}()'s byte parameter, inlined"))
        for c in n.get("inner", []):
            walk(c)
        path.pop()

    walk(tree)
    # one report per line and fault
    seen, uniq = set(), []
    for o in out:
        if (o[0], o[1]) not in seen:
            seen.add((o[0], o[1]))
            uniq.append(o)
    return uniq


def scan(path, root=ROOT, extra=()):
    rel = os.path.relpath(os.path.abspath(path), root)
    incs = [a for d in INCS for a in ("-I", os.path.join(root, d))]
    r = subprocess.run(["clang", *FLAGS, "-isystem", os.path.join(CAL, "include"),
                        *PER_FILE.get(rel, []), *extra, *incs, path],
                       capture_output=True, text=True)
    errs = [ln for ln in r.stderr.splitlines() if "error:" in ln]
    if r.returncode or errs or not r.stdout.strip():
        return None, (errs or r.stderr.strip().splitlines() or [f"clang exit {r.returncode}"])[:3]
    return scan_tree(json.loads(r.stdout), path), None


WHAT = {"A": "sign-extended: the high byte is $FF when bit 7 is set",
        "B": "a 32-bit value: bits 8-15 survive"}

# ------------------------------------------------------------ self-test

# Every line named shape_ is a shape the simulator got wrong, and must be
# reported; every fine_ one it got right, and must not be; a route_ one
# is reported exactly when its flag above says the route is broken.  An over_ one
# it got right too, and is reported ON PURPOSE: which 32-bit operations
# escape fault B depends on what the optimiser makes of them (unsigned
# & 0xF1 is right, & 0xFF is not), and a shift's on its operand's type
# (a byte's << and an int's >> are right, an int's << and a signed
# char's >> are not), and two widened bytes compared
# can come out right by luck of the optimiser -- a stored
# byte costs nothing, so the rule is kept simple and these are held to
# being reported.  b6cast.py
# runs the same expressions; the names match its table.
FIXTURE = r"""
#include <stdint.h>
typedef uint8_t U8;
extern U8 gb, gb2, gb3; extern signed char gs; extern int gi, gk; extern unsigned gun;
extern long gl; extern unsigned long gul; extern int gt[256]; extern char *gp;
extern int sink(int); extern U8 xr(void); extern int xp(U8);
struct S { U8 b; int i; }; extern struct S gst;
static U8 ir(void) { return gb + 1; }
static U8 irv(void) { U8 t = gb + 1; return t; }
static int ip(U8 x) { return x; }
int shape_add(void) { return (U8)(gb + 1); }
int shape_uchar(void) { return (unsigned char)(gb + 1); }
int shape_int_and(void) { return (U8)(gi & 0xFF); }
int shape_xor(void) { return (U8)(gb ^ 1); }
int shape_not(void) { return (U8)~gb; }
int shape_neg(void) { return (U8)-gb; }
int shape_shl(void) { return (U8)(gi << 1); }
int shape_schar(void) { return (U8)(gs | 1); }
int shape_char(void) { return (U8)(*gp + 1); }
int shape_compare(void) { return (U8)(gb + 1) > 0x7F; }
int shape_arg(void) { return sink((U8)(gb + 1)); }
int shape_into_int(void) { int v = (U8)(gb + 1); return v; }
int shape_member(void) { gst.i = (U8)(gb + 1); return gst.i; }
int shape_double(void) { return (U8)(U8)(gb + 1); }
int shape_outer_mask(void) { return (U8)(gb + 1) & 0xFF; }
int shape_switch(void) { switch ((U8)(gb + 1)) { case 0x81: return 1; } return 0; }
long shape_to_long(void) { return (U8)(gb + 1); }
int shape_long_load(void) { return (U8)gl; }
int shape_ulong_load(void) { return (U8)gul; }
int shape_ulong_shr(void) { return (U8)(gul >> 8); }
int shape_long_mask(void) { return (U8)(gl & 0xFF); }
int shape_long_add(void) { return (U8)(gl + 1); }
int shape_index(void) { return gt[(U8)(gb + 1)]; }
int shape_plain_char(void) { return (char)(gb + 1); }
int shape_in_arm(void) { return gk ? (U8)(gb + 1) : 0; }
int shape_schar_long(void) { return (signed char)gl; }
int route_inl_ret(void) { return ir(); }                     /* INLINE_RET */
int route_assign(void) { U8 t; return (t = gb + 1); }        /* ASSIGN */
int route_inl_par(void) { return ip(gb + 1); }               /* INLINE_PAR */
int fine_stored(void) { U8 t = (U8)(gb + 1); return t; }
int fine_implicit(void) { U8 t = gb + 1; return t; }
int fine_mask(void) { return (gb + 1) & 0xFF; }
int fine_unsigned(void) { return (U8)(gb + 1u); }
int fine_unsigned_var(void) { return (U8)(gun + 1); }
int fine_int_load(void) { return (U8)gi; }
int fine_member_load(void) { return (U8)gst.i; }
int fine_schar_load(void) { return (U8)gs; }
int fine_call(void) { return (U8)sink(gb); }
int fine_mul(void) { return (U8)(gb * 3); }
int fine_div(void) { return (U8)(gi / 3); }
int fine_cond(void) { return (U8)(gk ? gi : 0); }
int fine_byte_glob(void) { gb2 = gb + 1; return gb2; }
int fine_ext_ret(void) { return xr(); }
int fine_ext_par(void) { return xp(gb + 1); }
int fine_inl_stored(void) { return irv(); }
int fine_hi_byte(void) { return (U8)((unsigned)gi >> 8); }
int fine_long_stored(void) { U8 t = (U8)gl; return t; }
int fine_index_stored(void) { U8 t = gb + 1; return gt[t]; }
int fine_back_cond(void) { U8 v = gk ? (U8)(gb | 1) : (U8)(gb & (U8)~gk); return v; }
int fine_back_or(void) { U8 t = (U8)(gb + 1) | (U8)~gk; return t; }
int fine_back_mul(void) { U8 t = (U8)(gb + 1) * 3; return t; }
int fine_back_shl(void) { U8 t = ((U8)(gb + 1)) << 1; return t; }
int fine_back_neg(void) { U8 t = -(U8)(gb + 1); return t; }
int fine_back_sum(void) { U8 t = (U8)(gb + 1) + (U8)(gb + 2); return t; }
int fine_back_param(void) { return xp((U8)(gb + 1) | 1); }
int fine_back_long(void) { U8 t = (U8)gl + 1; return t; }
int fine_shr(void) { U8 t = (U8)((U8)(gb + 1) >> 1); return t; }
int fine_mask_15(void) { return gt[(U8)(gb + 1) & 15]; }
int fine_mask_7f(void) { return (U8)(gb + 1) & 0x7F; }
int fine_mask_long(void) { return gt[(U8)(gul >> 8) & 15]; }
int fine_truth_not(void) { return !(U8)(gb + 1); }
int fine_truth_if(void) { if ((U8)(gb + 1)) return 1; return 0; }
int fine_truth_long(void) { return !(U8)gl; }
int fine_around_cond(void) { return (U8)(gk ? gb + 1 : 0); }
int fine_comma(void) { return (U8)(gk, gb + 1); }
int fine_schar_add(void) { return (signed char)(gb + 1); }
int fine_incr(void) { U8 t = gb; return ++t; }
int fine_compound(void) { U8 t = gb; return (t += 1); }
int over_ulong_add(void) { return (U8)(gul + 1); }
int over_u8_shl(void) { return (U8)(gb << 1); }
int fine_int_shr(void) { return (U8)(gi >> 1); }
int shape_schar_shr(void) { return (U8)(gs >> 1); }
int fine_byte_shr4(void) { return (U8)(gb >> 4); }
int fine_cmp_narrow(void) { return (U8)(gb == 0x80) == (U8)(gk == 0x40); }
int fine_not_narrow(void) { return (U8)!gb == 1; }
int fine_and_narrow(void) { return (U8)(gb && gk) > 0; }
int fine_byte_and0f(void) { return (U8)(gb & 0x0F); }
int fine_int_and7f(void) { return (U8)(gi & 0x7F); }
int fine_own_sub(void) { return (U8)((U8)(gul >> 24) & 0x0F) == 9; }
int fine_ulong_shr24(void) { return (U8)(gul >> 24) == 0x89; }
int fine_ulong_and0f(void) { return (U8)(gul & 0x0F); }
int shape_long_shr24(void) { return (U8)(gl >> 24); }
int shape_is_near(void) { return (U8)(gul >> 16) == 0; }
int over_both_sides(void) { return (U8)(gb + 1) == (U8)(gb3 + 1); }
int fine_shifted_out(void) { return (unsigned)(U8)(gb + 1) >> 8; }
"""

ROUTE = {"INLINE_RET": "INLINE_RET_BROKEN", "ASSIGN": "ASSIGN_BROKEN",
         "INLINE_PAR": "INLINE_PAR_BROKEN"}


def self_test():
    d = tempfile.mkdtemp(prefix="b6scan-")
    try:
        path = os.path.join(d, "fixture.c")
        with open(path, "w") as f:
            f.write(FIXTURE)
        got, err = scan(path, root=d)
        if got is None:
            print(f"b6scan: self-test: fixture not parsed: {err}")
            return 1
        lines = FIXTURE.splitlines()
        hit = {}
        for ln, fault, how in got:
            name = lines[ln - 1].split("(")[0].split()[-1]
            hit.setdefault(name, []).append((fault, how))
        bad = shapes = 0
        for ln in lines:
            head = ln.split("(")[0].split()
            if not head:
                continue
            name = head[-1]
            route = next((r for r in ROUTE if f"/* {r} */" in ln), None)
            want = name.startswith(("shape_", "over_"))
            if name.startswith("route_"):
                want = bool(globals()[ROUTE[route]])   # as measured
            shapes += want
            if want and name not in hit:
                print(f"b6scan: self-test: BLIND to {name}")
                bad += 1
            if not want and name.startswith(("fine_", "route_")) and name in hit:
                print(f"b6scan: self-test: reports {name}, which is right: {hit[name][0]}")
                bad += 1
        print(f"b6scan: self-test: {shapes} lines to report, {len(hit)} reported, "
              f"{'clean' if not bad else str(bad) + ' problem(s)'}")
        return 1 if bad else 0
    finally:
        shutil.rmtree(d, True)


def main(argv):
    if shutil.which("clang") is None:
        print("b6scan: no clang on PATH")
        return 1
    if "--self-test" in argv:
        return self_test()
    root = ROOT
    args = argv[1:]
    if "--root" in args:
        i = args.index("--root")
        root = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    files = args or sorted({p for g in FILES for p in glob.glob(os.path.join(root, g))})
    if self_test():
        return 1
    found = skipped = 0
    for p in files:
        got, err = scan(p, root=root)
        rel = os.path.relpath(os.path.abspath(p), root)
        if got is None:
            skipped += 1
            print(f"  {rel}: not parsed: {err}")
            continue
        for ln, fault, how in got:
            found += 1
            print(f"  {rel}:{ln}: {how}: {WHAT[fault]} ({fault})")
    print(f"b6scan: {len(files)} file(s), {skipped} not parsed, {found} byte(s) cc6502 widens wrong")
    return 1 if found or skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
