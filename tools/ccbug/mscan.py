#!/usr/bin/env python3
"""Find a `jsl` the compiler reaches with an 8-BIT accumulator.

Calypsi's own assembly-interface documentation is explicit: "The 65816 is
used in native mode with 16 bit registers.  In some situations the runtime
needs to switch to 8 bit register mode ... This is done automatically and
the compiler will then switch back to 16 bits mode."  So a called function
is compiled assuming M=0, and reaching its `jsl` with M=1 means its first
16-bit immediate decodes short -- the operand's high byte is executed as
an opcode.  That is B17, and RetroWP met it as a BRK inside a callee.

THE SCAN IS DELIBERATELY CONSERVATIVE, because the alternative is a
wrong answer that reads as authoritative:

  * The accumulator is 16-bit at a function's entry label.
  * `sep #32` makes it 8-bit, `rep #32` makes it 16-bit.
  * A `##` immediate makes it 16-bit, because the assembler only takes
    that form when the accumulator is wide.  This is what caught the
    first version of this scan reporting nonsense: the compiler calls an
    outlined fragment while narrow and the fragment widens before
    returning, so the next instruction is a `##` and the call after it is
    perfectly safe.
  * ANY CALL makes it UNKNOWN afterwards, for the same reason -- the
    callee's exit width is not this scan's to guess.
  * ANY OTHER LABEL makes it UNKNOWN, because control can arrive there
    from a branch whose width this scan does not track.

Only a call to a NAMED function is ever reported.  A call to a `?Lnnnn`
fragment is the compiler talking to itself, and it knows what mode it
left.  An unknown state is never reported.  This will miss a case that
crosses a branch; it will not invent one.

    python3 tools/ccbug/mscan.py FILE.s [FILE.s ...]
    python3 tools/ccbug/mscan.py --tree        # every C source, compiled plainly
    python3 tools/ccbug/mscan.py --build       # the BUILD's own assembly: make mscan

--build runs a second check as well, joins() below: B21, an immediate
reached in a width its encoding contradicts.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
CALYPSI = os.environ.get("CALYPSI",
                         os.path.expanduser("~/dev/toolchains/calypsi-65816"))

LABEL = re.compile(r"^([A-Za-z_`?][\w`?.$]*):")
SEP = re.compile(r"^\s+sep\s+#(0x20|32)\b", re.I)
REP = re.compile(r"^\s+rep\s+#(0x20|32)\b", re.I)
CALL = re.compile(r"^\s+(jsl|jsr)\s+(.*)$", re.I)
WIDE_IMM = re.compile(r"##")        # only assembles when A is 16-bit
FUNC = re.compile(r"^([A-Za-z_][\w.$]*):")
BRANCH = re.compile(r"^\s+(bra|beq|bne|bcc|bcs|bmi|bpl|bvc|bvs|brl|jmp)\s+"
                    r"`?([\w`?.$]+)`?", re.I)
ALWAYS = ("bra", "brl", "jmp")

NARROW, WIDE, UNKNOWN = "narrow", "wide", "unknown"


def meet(a, b):
    """Two paths into one label.  Agreement is knowledge; anything else
    is not, and this scan never reports what it does not know."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a == b else UNKNOWN


def parse(path):
    """The listing as [(kind, text, label_or_target, line_no)]."""
    out = []
    with open(path, errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if line.lstrip().startswith(";") or not line.strip():
                continue
            m = LABEL.match(line)
            if m:
                out.append(("label", line, m.group(1).strip("`"), n))
                rest = line[m.end():]
                if not rest.strip():
                    continue
                line = rest          # a label with an instruction beside it
            if SEP.match(line):
                out.append(("sep", line, None, n))
            elif REP.match(line):
                out.append(("rep", line, None, n))
            elif CALL.match(line):
                out.append(("call", line, CALL.match(line).group(2).strip(), n))
            else:
                b = BRANCH.match(line)
                if b:
                    out.append(("branch", line, (b.group(1).lower(),
                                                 b.group(2).strip("`")), n))
                elif WIDE_IMM.search(line):
                    out.append(("wide", line, None, n))
                elif re.match(r"^\s+rtl\b|^\s+rts\b", line, re.I):
                    out.append(("ret", line, None, n))
    return out


def scan(path):
    """[(function, line, target)] for every call to a NAMED function that
    every path reaches with an 8-bit accumulator.

    A forward dataflow over the listing's labels, iterated to a fixed
    point.  A label's state is the MEET of its predecessors -- the
    fall-through and every branch that names it -- so a join whose paths
    all agree is known, which is the case a single pass has to give up on
    (RetroWP's linebreak.c reaches its failing call through exactly such
    a join).  Disagreement, or any unknown predecessor, stays unknown and
    is never reported.
    """
    items = parse(path)
    # entry state of each label
    state = {}
    for kind, _, lab, _ in items:
        if kind == "label":
            state[lab] = None
    for kind, _, lab, _ in items:
        if kind == "label" and FUNC.match(lab + ":") and not lab.startswith("?"):
            state[lab] = WIDE          # a function is entered 16-bit

    hits = []
    for _ in range(12):                # small listings converge at once
        changed = False
        cur, func = UNKNOWN, "?"
        hits = []
        for kind, _, arg, n in items:
            if kind == "label":
                if FUNC.match(arg + ":") and not arg.startswith("?"):
                    func = arg
                    cur = WIDE
                else:
                    new = meet(state.get(arg), cur if cur else None)
                    if new != state.get(arg):
                        state[arg] = new
                        changed = True
                    cur = state.get(arg) or UNKNOWN
            elif kind == "sep":
                cur = NARROW
            elif kind == "rep" or kind == "wide":
                cur = WIDE
            elif kind == "call":
                if cur == NARROW and not re.search(r"`\?L", arg):
                    hits.append((func, n, arg))
                cur = UNKNOWN          # the callee's exit width is its own
            elif kind == "branch":
                op, target = arg
                if target in state:
                    new = meet(state.get(target), cur)
                    if new != state.get(target):
                        state[target] = new
                        changed = True
                if op in ALWAYS:
                    cur = UNKNOWN      # nothing falls through
            elif kind == "ret":
                cur = UNKNOWN
        if not changed:
            break
    return hits


# ---- B21: a JOIN reached with two accumulator widths ----------------------
#
# The scan above asks one question -- is a named function CALLED narrow --
# and it trusts two things this one does not.  It takes any `##` as proof
# the accumulator is 16-bit, but `ldy ##0` and `ldx ##0` are wide because
# of the X flag, not M, and say nothing about the accumulator.  And it
# takes a `?L` fragment to be "the compiler talking to itself", which knows
# what mode it left.  cc65816 5.18 at -O2 broke both at once in
# src/antic/antic.c (2026-09-24): it outlined `sep #32 / ldy ##0 / rtl`,
# called it on ONE path into a join, and the join's `adc ##33` -- 69 21 00
# -- ran as `adc #$21` followed by BRK.  test-m24 caught it as a program
# that never started drawing.
#
# So this check tracks the SET of widths that can reach each instruction,
# follows a fragment to see what width it returns in, and flags any
# accumulator immediate whose encoding one of those widths contradicts.
# `##` on lda/adc/... is two operand bytes and only right when A is 16-bit;
# `#` is one and only right when it is 8-bit.

M_IMM = re.compile(r"^\s+(lda|adc|sbc|cmp|and|ora|eor|bit)\s+(##?)", re.I)
SEPREP = re.compile(r"^\s+(sep|rep)\s+#(\S+)", re.I)
INSN = re.compile(r"^\s+([a-z]{3})\b", re.I)
JSL = re.compile(r"^\s+jsl\s+(?:long:)?`?([\w?.$]+)`?", re.I)
BR = re.compile(r"^\s+(bra|beq|bne|bcc|bcs|bmi|bpl|bvc|bvs|brl|jmp)\s+"
                r"(?:\.kbank\s+|long:)?`?([\w?.$]+)`?", re.I)
W, N = "16", "8"


def _lines(path):
    """[(label or None, instruction text or None, line number)]."""
    out = []
    with open(path, errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith(";"):
                continue
            m = LABEL.match(line)
            lab = m.group(1).strip("`") if m else None
            rest = line[m.end():] if m else line
            if lab:
                out.append((lab, None, n))
            if rest.strip() and INSN.match(rest):
                out.append((None, rest, n))
    return out


def _mbits(operand):
    """Does a sep/rep operand touch M (bit 5)?"""
    try:
        v = int(operand.replace("0x", ""), 16) if operand.startswith("0x") \
            else int(operand)
    except ValueError:
        return False
    return bool(v & 0x20)


def joins(path):
    """[(function, line, text, widths)] for every accumulator immediate
    that some path reaches in a width its encoding contradicts."""
    items = _lines(path)
    at = {}
    for i, (lab, _, _) in enumerate(items):
        if lab is not None:
            at[lab] = i

    def frag_exit(start, width):
        """What width a `jsl`ed fragment returns in, given the width it
        was entered in; None if it is not straight-line to an rtl."""
        i = start
        while i < len(items):
            lab, text, _ = items[i]
            if text:
                op = INSN.match(text).group(1).lower()
                sr = SEPREP.match(text)
                if sr and _mbits(sr.group(2)):
                    width = N if sr.group(1).lower() == "sep" else W
                elif op == "plp":
                    return None
                elif op in ("rtl", "rts"):
                    return width
                elif BR.match(text) or op == "jsl":
                    return None
            i += 1
        return None

    inw = [set() for _ in items]
    todo = []
    func_of = {}
    for i, (lab, _, _) in enumerate(items):
        if lab and not lab.startswith("?"):
            inw[i] = {W}                   # a function is entered 16-bit
            todo.append(i)
    cur_func = "?"
    for i, (lab, _, _) in enumerate(items):
        if lab and not lab.startswith("?"):
            cur_func = lab
        func_of[i] = cur_func

    def push(j, ws):
        if j < len(items) and not ws <= inw[j]:
            inw[j] |= ws
            todo.append(j)

    while todo:
        i = todo.pop()
        ws = set(inw[i])
        lab, text, _ = items[i]
        if text is None:
            push(i + 1, ws)
            continue
        op = INSN.match(text).group(1).lower()
        sr = SEPREP.match(text)
        if sr and _mbits(sr.group(2)):
            ws = {N} if sr.group(1).lower() == "sep" else {W}
        elif op == "plp":
            ws = set()                     # unknown: say nothing after it
        elif op == "jsl":
            m = JSL.match(text)
            tgt = m.group(1) if m else ""
            if tgt.startswith("?") and tgt in at:
                out = set()
                for w in ws:
                    e = frag_exit(at[tgt], w)
                    if e is None:
                        out = set()
                        break
                    out.add(e)
                ws = out
            else:
                ws = {W}                   # a named function returns 16-bit
        mi = M_IMM.match(text)
        if mi:
            ws = {W} if len(mi.group(2)) == 2 else {N}
        b = BR.match(text)
        if b:
            tgt = b.group(2)
            if tgt in at:
                push(at[tgt], ws)
            if b.group(1).lower() in ("bra", "brl", "jmp"):
                continue
        if op in ("rtl", "rts", "rti"):
            continue
        push(i + 1, ws)

    hits = []
    for i, (lab, text, n) in enumerate(items):
        if not text:
            continue
        mi = M_IMM.match(text)
        if not mi:
            continue
        enc = W if len(mi.group(2)) == 2 else N
        wrong = inw[i] - {enc}
        if wrong:
            hits.append((func_of[i], n, text.strip(), sorted(inw[i])))
    return hits


def tree_sources():
    """The C the tree compiles, with the flags it compiles them with."""
    out = []
    for base, _, names in os.walk(os.path.join(ROOT, "src")):
        for name in sorted(names):
            if name.endswith(".c"):
                out.append(os.path.join(base, name))
    return out


def build_scan():
    """Both checks over the assembly the BUILD produced (make mscan, which
    rebuilds with CC_ASM=1): every object tools/ccdep.sh compiled, with
    its own flags and defines.  That matters here -- the VDI is compiled
    three times from one source with different prefixes, and --tree, which
    compiles each file once and plainly, never sees the ANTIC instance."""
    b = os.path.join(ROOT, "build")
    files = []
    for base, _, names in os.walk(b):
        for n in sorted(names):
            if n.endswith(".s"):
                stem = os.path.join(base, n[:-2])
                if os.path.exists(stem + ".o") and os.path.exists(stem + ".d"):
                    files.append(os.path.join(base, n))
    if not files:
        sys.exit("mscan --build: no assembly beside the objects -- run "
                 "`make mscan`, which rebuilds with CC_ASM=1")
    calls = widths = 0
    for f in files:
        rel = os.path.relpath(f, ROOT)
        for func, n, tgt in scan(f):
            print(f"{rel}:{n}: {func} calls {tgt} with an 8-bit accumulator")
            calls += 1
        for func, n, text, ws in joins(f):
            print(f"{rel}:{n}: {func}: `{text}` is reached with the "
                  f"accumulator {' and '.join(w + '-bit' for w in ws)} wide")
            widths += 1
    print(f"mscan: {len(files)} object(s) of the build scanned; {calls} "
          f"call(s) reached narrow, {widths} immediate(s) reached in the "
          f"wrong width")
    return 1 if calls or widths else 0


def main(argv):
    if "--build" in argv:
        return build_scan()
    if "--tree" not in argv:
        files = [a for a in argv if a.endswith(".s")]
        if not files:
            sys.exit(__doc__)
        total = 0
        for f in files:
            for func, n, tgt in scan(f):
                print(f"{f}:{n}: {func} calls {tgt} with an 8-bit accumulator")
                total += 1
        print(f"{total} call(s) reached narrow")
        return 1 if total else 0

    cc = os.path.join(CALYPSI, "bin", "cc65816")
    if not os.path.exists(cc):
        sys.exit("Calypsi not installed")
    out = os.path.join(ROOT, "build", "mscan")
    os.makedirs(out, exist_ok=True)
    total, skipped = 0, 0
    for src in tree_sources():
        stem = os.path.basename(src)[:-2]
        asm = os.path.join(out, stem + ".s")
        r = subprocess.run(
            [cc, "--code-model=large", "--data-model=small", "-O2",
             "-I", os.path.join(ROOT, "src"),
             "-I", os.path.join(ROOT, "src", "app"),
             "-I", os.path.join(ROOT, "build"),
             "--assembly-source", asm, "-c",
             "-o", os.path.join(out, stem + ".o"), src],
            capture_output=True, text=True)
        if r.returncode:
            skipped += 1           # a source this flag set cannot build alone
            continue
        for func, n, tgt in scan(asm):
            print(f"{os.path.relpath(src, ROOT)}: {func} calls {tgt} "
                  f"with an 8-bit accumulator ({os.path.relpath(asm, ROOT)}:{n})")
            total += 1
    print(f"mscan: {total} call(s) reached narrow; "
          f"{skipped} source(s) could not be compiled alone and were skipped")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
