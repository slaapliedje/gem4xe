#!/usr/bin/env python3
"""b6cast.py -- cc6502's byte conversions, measured in the vendor's
simulator (the evidence tools/bsp6502/b6scan.py's rules rest on).

Each shape is a function of globals the driver sets, so nothing folds;
each runs for nine byte values around the sign boundary (and the first
sweep of the matrix ran every value, 0-255, with the same result).  The
6502 prints what it got; the HOST computes what C says it should be, on
a 16-bit-int, 32-bit-long target -- a reference computed on the 6502 is
compiled by the compiler under test, and one of the first ones was.

    python3 tools/bsp6502/b6cast.py [-O 0|1|2 ...] [--core 6502]

Then it runs b6scan.py on the very file the simulator ran, and prints
each shape's two verdicts: what the 6502 got, and whether the scan
reports it.  It exits 1 on any disagreement -- a wrong shape the scan is
quiet on, or a right one it reports, but for the over_ shapes it reports
on purpose.  When cc6502 is fixed, the shapes come out right and this
says so: that is the cue to retire the scan.  The build goes to a
scratch directory and is removed.  About 12 seconds per -O.

Measured 2026-11-15, cc6502 5.18, --core 6502, -O0 and -O2 alike (every
-O1 shape agrees too), except the inlined byte return, which is
right at -O0 and wrong at -O1 and -O2:

  fault A, sign-extended:  (U8)(signed computed) widened, for + - & | ^
                           ~ unary- <<, `& 0xFF` included, and >> on a
                           signed char.  Right: * / % (library calls),
                           an int's >>, a byte's << and >>, loads, calls,
                           ?: and comma, any UNSIGNED int operand, and a
                           value masked below $80.
  fault B, 16 bits kept:   (U8)(32-bit) widened, signed or unsigned:
                           load, & 0xFF, ?:, /, >>.  Unsigned + - * | ^
                           ~ << come out right, and so do >> 24 or more
                           and a mask below $FF; signed ones get fault A.
  right, always:           a byte stored first -- a local, a global, a
                           parameter -- and a byte function's return
                           from another file.
  right, where it goes:    the widened value carried back into a byte by
                           + - * & | ^ ~ <<, or masked below $FF, or
                           shifted right, or tested for truth.  The low
                           byte is always right; only the high one is not.
                           `& 0xFF` does NOT rescue it: cc6502 takes the
                           mask for a no-op on a byte and drops it.
"""
import os
import shutil
import subprocess
import sys
import tempfile

CAL = os.environ.get("CALYPSI6502", os.path.expanduser("~/dev/toolchains/calypsi-6502"))
VALUES = [0x00, 0x01, 0x40, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF]


def sb(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def w16(x):
    return x & 0xFFFF


# inputs, for byte value v: gb = v, gs = (signed char)v, gi = 0x7E00 + v,
# gun = 0xCD00 + v, gl = 0x12345600 + v, gul = 0x89ABCD00 + v, gk = 0x40,
# gneg = 0x8000 + (v << 7), gt[i] = i, *gp = v
GI = lambda v: 0x7E00 + v
GL = lambda v: 0x12345600 + v
GUL = lambda v: 0x89ABCD00 + v


def cdiv(x, y):
    q = abs(x) // abs(y)
    return q if (x < 0) == (y < 0) else -q


# (name, C body, the host's answer, what b6scan.py says: 'A', 'B', None,
#  or a route flag's name)
SHAPES = [
    # fault A: signed computed values
    ("add",        "return (U8)(gb + 1);",            lambda v: (v + 1) & 0xFF, "A"),
    ("uchar",      "return (unsigned char)(gb + 1);", lambda v: (v + 1) & 0xFF, "A"),
    ("sub",        "return (U8)(gb - 3);",            lambda v: (v - 3) & 0xFF, "A"),
    ("and",        "return (U8)(gb & 0xF1);",         lambda v: v & 0xF1, "A"),
    ("or",         "return (U8)(gb | 1);",            lambda v: v | 1, "A"),
    ("xor",        "return (U8)(gb ^ 1);",            lambda v: v ^ 1, "A"),
    ("not",        "return (U8)~gb;",                 lambda v: ~v & 0xFF, "A"),
    ("neg",        "return (U8)-gb;",                 lambda v: -v & 0xFF, "A"),
    ("addv",       "return (U8)(gb + gk);",           lambda v: (v + 0x40) & 0xFF, "A"),
    ("int_add",    "return (U8)(gi + 1);",            lambda v: (v + 1) & 0xFF, "A"),
    ("int_and",    "return (U8)(gi & 0xFF);",         lambda v: v, "A"),
    ("int_shl",    "return (U8)(gi << 1);",           lambda v: (v << 1) & 0xFF, "A"),
    ("schar_or",   "return (U8)(gs | 1);",            lambda v: v | 1, "A"),
    ("schar_shr",  "return (U8)(gs >> 1);",           lambda v: (sb(v) >> 1) & 0xFF, "A"),
    ("char_add",   "return (U8)(*gp + 1);",           lambda v: (v + 1) & 0xFF, "A"),
    ("long_add",   "return (U8)(gl + 1);",            lambda v: (v + 1) & 0xFF, "A"),
    ("compare",    "return (U8)(gb + 1) > 0x7F;",     lambda v: int(((v + 1) & 0xFF) > 0x7F), "A"),
    ("arg",        "return sink((U8)(gb + 1));",      lambda v: (v + 1) & 0xFF, "A"),
    ("into_int",   "int x = (U8)(gb + 1); return x;", lambda v: (v + 1) & 0xFF, "A"),
    ("double",     "return (U8)(U8)(gb + 1);",        lambda v: (v + 1) & 0xFF, "A"),
    ("outer_mask", "return (U8)(gb + 1) & 0xFF;",     lambda v: (v + 1) & 0xFF, "A"),
    ("switch",     "switch ((U8)(gb + 1)) { case 0x81: return 1; } return 0;",
                                                      lambda v: int(v == 0x80), "A"),
    ("index",      "return gt[(U8)(gb + 1)];",        lambda v: (v + 1) & 0xFF, "A"),
    ("plain_char", "return (char)(gb + 1);",          lambda v: (v + 1) & 0xFF, "A"),
    ("in_arm",     "return gk ? (U8)(gb + 1) : 0;",   lambda v: (v + 1) & 0xFF, "A"),
    # fault B: 32-bit values
    ("long_load",  "return (U8)gl;",                  lambda v: v, "B"),
    ("long_mask",  "return (U8)(gl & 0xFF);",         lambda v: v, "B"),
    ("ulong_load", "return (U8)gul;",                 lambda v: v, "B"),
    ("ulong_shr",  "return (U8)(gul >> 8);",          lambda v: 0xCD, "B"),
    ("ulong_div",  "return (U8)(gul / 3);",           lambda v: (GUL(v) // 3) & 0xFF, "B"),
    ("ulong_cond", "return (U8)(gk ? gul : 0);",      lambda v: v, "B"),
    ("schar_long", "return (signed char)gl;",         lambda v: sb(v), "B"),
    # routes other than a cast
    ("inl_ret",    "return ir();",                    lambda v: (v + 1) & 0xFF, "INLINE_RET_BROKEN"),
    ("assign",     "U8 t; return (t = gb + 1);",      lambda v: (v + 1) & 0xFF, "ASSIGN_BROKEN"),
    ("inl_par",    "return ip(gb + 1);",              lambda v: (v + 1) & 0xFF, "INLINE_PAR_BROKEN"),
    # right
    ("stored",     "U8 t = (U8)(gb + 1); return t;",  lambda v: (v + 1) & 0xFF, None),
    ("implicit",   "U8 t = gb + 1; return t;",        lambda v: (v + 1) & 0xFF, None),
    ("mask",       "return (gb + 1) & 0xFF;",         lambda v: (v + 1) & 0xFF, None),
    ("unsigned",   "return (U8)(gb + 1u);",           lambda v: (v + 1) & 0xFF, None),
    ("uns_var",    "return (U8)(gun + 1);",           lambda v: (v + 1) & 0xFF, None),
    ("int_load",   "return (U8)gi;",                  lambda v: v, None),
    ("schar_load", "return (U8)gs;",                  lambda v: v, None),
    ("call",       "return (U8)sink(gi);",            lambda v: v, None),
    ("mul",        "return (U8)(gb * 3);",            lambda v: (v * 3) & 0xFF, None),
    ("div",        "return (U8)(gi / 3);",            lambda v: cdiv(GI(v), 3) & 0xFF, None),
    ("cond",       "return (U8)(gk ? gi : 0);",       lambda v: v, None),
    ("glob",       "gb2 = gb + 1; return gb2;",       lambda v: (v + 1) & 0xFF, None),
    ("ext_ret",    "return xr();",                    lambda v: (v + 1) & 0xFF, None),
    ("ext_par",    "return xp(gb + 1);",              lambda v: (v + 1) & 0xFF, None),
    ("inl_stored", "return irv();",                   lambda v: (v + 1) & 0xFF, None),
    ("hi_byte",    "return (U8)((unsigned)gi >> 8);", lambda v: 0x7E, None),
    ("long_stored", "U8 t = (U8)gl; return t;",       lambda v: v, None),
    ("idx_stored", "U8 t = gb + 1; return gt[t];",    lambda v: (v + 1) & 0xFF, None),
    ("around_cond", "return (U8)(gk ? gb + 1 : 0);",  lambda v: (v + 1) & 0xFF, None),
    ("comma",      "return (U8)(gk, gb + 1);",        lambda v: (v + 1) & 0xFF, None),
    ("schar_add",  "return (signed char)(gb + 1);",   lambda v: sb(v + 1), None),
    ("incr",       "U8 t = gb; return ++t;",          lambda v: (v + 1) & 0xFF, None),
    ("compound",   "U8 t = gb; return (t += 1);",     lambda v: (v + 1) & 0xFF, None),
    # widened, then narrowed again: the low byte is always right, so a
    # value that only + - * & | ^ ~ << carry back into a byte is right
    ("back_cond",  "U8 v = gk ? (U8)(gb | 1) : (U8)(gb & (U8)~gk); return v;",
                                                      lambda v: v | 1, None),
    ("back_or",    "U8 t = (U8)(gb + 1) | (U8)~gk; return t;",
                                                      lambda v: ((v + 1) | 0xBF) & 0xFF, None),
    ("back_mul",   "U8 t = (U8)(gb + 1) * 3; return t;", lambda v: ((v + 1) * 3) & 0xFF, None),
    ("back_shl",   "U8 t = ((U8)(gb + 1)) << 1; return t;", lambda v: ((v + 1) << 1) & 0xFF, None),
    ("back_neg",   "U8 t = -(U8)(gb + 1); return t;", lambda v: -(v + 1) & 0xFF, None),
    ("back_sum",   "U8 t = (U8)(gb + 1) + (U8)(gb + 2); return t;",
                                                      lambda v: (2 * v + 3) & 0xFF, None),
    ("back_param", "return xp((U8)(gb + 1) | 1);",    lambda v: ((v + 1) | 1) & 0xFF, None),
    ("back_long",  "U8 t = (U8)gl + 1; return t;",    lambda v: (v + 1) & 0xFF, None),
    ("shr",        "U8 t = (U8)((U8)(gb + 1) >> 1); return t;",
                                                      lambda v: ((v + 1) & 0xFF) >> 1, None),
    # masked below bit 7: the high byte is cleared, and with it the fault
    ("mask_15",    "return gt[(U8)(gb + 1) & 15];",   lambda v: (v + 1) & 15, None),
    ("mask_7f",    "return (U8)(gb + 1) & 0x7F;",     lambda v: (v + 1) & 0x7F, None),
    ("mask_long",  "return gt[(U8)(gul >> 8) & 15];", lambda v: 0xD, None),
    # a widened byte shifted right, and a byte's truth, are right too
    ("truth_not",  "return !(U8)(gb + 1);",           lambda v: int(v == 0xFF), None),
    ("truth_if",   "if ((U8)(gb + 1)) return 1; return 0;", lambda v: int(v != 0xFF), None),
    ("truth_long", "return !(U8)gl;",                 lambda v: int(v == 0), None),
    # value ranges: bit 7 can never be set, or bits 8-15 never survive
    ("byte_shr4",  "return (U8)(gb >> 4);",           lambda v: v >> 4, None),
    ("byte_and0f", "return (U8)(gb & 0x0F);",         lambda v: v & 15, None),
    ("schar_and0f", "return (U8)(gs & 0x0F);",        lambda v: v & 15, None),
    ("int_and7f",  "return (U8)(gi & 0x7F);",         lambda v: v & 0x7F, None),
    ("own_sub",    "return (U8)((U8)(gul >> 24) & 0x0F) == 9;", lambda v: 1, None),
    ("ulong_shr24", "return (U8)(gul >> 24);",        lambda v: 0x89, None),
    ("ulong_shr24c", "return (U8)(gul >> 24) == 0x89;", lambda v: 1, None),
    ("long_shr24n", "return (U8)(gln >> 24);",        lambda v: 0x89, "B"),
    ("ulong_and0f", "return (U8)(gul & 0x0F);",       lambda v: v & 15, None),
    ("is_near",    "return (U8)(gtop >> 16) == 0;",   lambda v: 1, "B"),
    ("drive",      "return (char)('1' + gb7 - 'A');", lambda v: (0x31 + (v & 0x3F) - 0x41) & 0xFF, "A"),
    # right, and reported on purpose (b6scan.py's over_ lines)
    ("ulong_add",  "return (U8)(gul + 1);",           lambda v: (v + 1) & 0xFF, "over"),
    ("u8_shl",     "return (U8)(gb << 1);",           lambda v: (v << 1) & 0xFF, "over"),
    ("int_shr",    "return (U8)(gi >> 1);",           lambda v: (GI(v) >> 1) & 0xFF, None),
    ("both_sides", "return (U8)(gb + 1) == (U8)(gb3 + 1);", lambda v: 1, "over"),
    ("shifted_out", "return (unsigned)(U8)(gb + 1) >> 8;", lambda v: 0, None),
]

# routes that only the optimiser breaks: right at -O0, as measured
OPTIMISER_ONLY = ("INLINE_RET_BROKEN",)

PRE = """#include <stdint.h>
typedef uint8_t U8;
extern U8 gb, gb2, gb3; extern signed char gs; extern int gi, gk, gt[256];
extern unsigned gun; extern long gl; extern unsigned long gul; extern char *gp;
extern int sink(int); extern U8 xr(void); extern int xp(U8);
extern long gln; extern unsigned long gtop; extern U8 gb7;
static U8 ir(void) { return gb + 1; }
static U8 irv(void) { U8 t = gb + 1; return t; }
static int ip(U8 x) { return x; }
"""

DRIVER = """#include <stdio.h>
#include <stdint.h>
uint8_t gb, gb2, gb3; signed char gs; int gi, gk = 0x40, gt[256]; unsigned gun;
long gl; unsigned long gul; char gc[2]; char *gp = gc;
long gln; unsigned long gtop; uint8_t gb7;
int sink(int v) { return v; }
uint8_t xr(void) { return gb + 1; }
int xp(uint8_t x) { return x; }
static const unsigned values[] = { %s };
int main(void)
{
    unsigned i, v;
    for (i = 0; i < 256; i++) gt[i] = (int)i;
    for (i = 0; i < sizeof values / sizeof values[0]; i++) {
        v = values[i];
        gb = (uint8_t)v; gb3 = (uint8_t)v; gs = (signed char)v; gi = (int)(0x7E00u + v);
        gun = 0xCD00u + v; gl = (long)(0x12345600UL + v); gul = 0x89ABCD00UL + v;
        gc[0] = (char)v; gln = (long)(0x89ABCD00UL + v); gtop = 0x01000000UL + v;
        gb7 = (uint8_t)(v & 0x3F);
        printf("V%%x", v);
        %s
        printf("\\n");
    }
    printf("END\\n");
    return 0;
}
"""

LINKER = """(define memories
  '((memory flash (address (#x8000 . #xffff))
            (section code idata cdata switch data_init_table (reset #xfffc)))
    (memory zeropage (address (#x00 . #xff))
            (section registers zzpage zpage))
    (memory RAM (address (#x0100 . #x7fff))
            (section (stack (#x100 . #x1ff))
                     cstack data zdata))
    (block cstack (size #x800))
    (block stack (size #x100))
    ))
"""


def run(d, opt, core):
    with open(os.path.join(d, "shapes.c"), "w") as f:
        f.write(PRE + "".join(f"int b6_{n}(void) {{ {b} }}\n" for n, b, _, _ in SHAPES))
    calls = " ".join(f"{{ extern int b6_{n}(void); printf(\" %x\", b6_{n}()); }}"
                     for n, _, _, _ in SHAPES)
    with open(os.path.join(d, "main.c"), "w") as f:
        f.write(DRIVER % (", ".join(hex(v) for v in VALUES), calls))
    with open(os.path.join(d, "linker.scm"), "w") as f:
        f.write(LINKER)
    cc = os.path.join(CAL, "bin", "cc6502")
    for src in ("main", "shapes"):
        subprocess.run([cc, "--core", core, f"-O{opt}", "-o",
                        os.path.join(d, src + ".o"), os.path.join(d, src + ".c")], check=True)
    elf = os.path.join(d, "t.elf")
    subprocess.run([os.path.join(CAL, "bin", "ln6502"), "--debug", "--semi-hosted",
                    os.path.join(d, "linker.scm"), os.path.join(d, "main.o"),
                    os.path.join(d, "shapes.o"), "-o", elf,
                    os.path.join(CAL, "lib", f"clib-{core}.a")], check=True)
    r = subprocess.run([os.path.join(CAL, "bin", "db6502"), "--nh", "--nx", "--core", core,
                        "--terminate-on-program-exit", elf, "-e", "run"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800)
    rows = [ln.split() for ln in r.stdout.splitlines() if ln.startswith("V")]
    if "END" not in r.stdout or len(rows) != len(VALUES):
        raise RuntimeError(f"the simulator stopped early: {r.stdout[-300:]!r} {r.stderr[-300:]!r}")
    return rows


def verdicts(rows):
    out = {}
    for i, (n, _, ref, _) in enumerate(SHAPES):
        bad = []
        for r in rows:
            v, got = int(r[0][1:], 16), int(r[i + 1], 16)
            if got != w16(ref(v)):
                bad.append((v, got, w16(ref(v))))
        out[n] = bad
    return out


def main(argv):
    opts, core = [], "6502"
    a = argv[1:]
    while a:
        x = a.pop(0)
        if x == "-O":
            opts.append(a.pop(0))
        elif x == "--core":
            core = a.pop(0)
    opts = opts or ["0", "1", "2"]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import b6scan
    disagree = 0
    for opt in opts:
        d = tempfile.mkdtemp(prefix="b6cast-")
        try:
            v = verdicts(run(d, opt, core))
            # the scan, on the very file the simulator ran
            got, err = b6scan.scan(os.path.join(d, "shapes.c"), root=d)
            if got is None:
                print(f"b6cast: the scan could not read the shapes: {err}")
                return 1
            src = open(os.path.join(d, "shapes.c")).read().splitlines()
        finally:
            shutil.rmtree(d, True)
        reported = {}
        for ln, fault, how in got:
            head = src[ln - 1].split("(")[0].split()
            if head and head[-1].startswith("b6_"):
                reported.setdefault(head[-1][3:], fault)
        print(f"b6cast: -O{opt} --core {core}    (what the simulator got, what b6scan.py says)")
        for n, _, _, says in SHAPES:
            bad = v[n]
            said = reported.get(n)
            if says in OPTIMISER_ONLY and opt == "0":
                ok = not bad                       # nothing is inlined at -O0
            elif says == "over":
                ok = not bad and said is not None  # right, and reported on purpose
            else:
                ok = bool(bad) == (said is not None)
            disagree += not ok
            tag = "wrong" if bad else "right"
            eg = f"  v={bad[0][0]:#04x} got {bad[0][1]:#06x} want {bad[0][2]:#x}" if bad else ""
            word = f"reports {said}" if said else "quiet"
            print(f"  {'  ' if ok else '!!'} {n:12s} {tag:5s} {word:10s}{eg}")
        print()
    print(f"b6cast: {len(SHAPES)} shapes at -O{',-O'.join(opts)}: "
          + ("b6scan.py reports exactly the wrong ones, and the over_ ones" if not disagree else
             f"{disagree} disagreement(s) between the compiler and b6scan.py (!!)"))
    return 1 if disagree else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
