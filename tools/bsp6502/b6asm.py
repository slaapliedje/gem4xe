#!/usr/bin/env python3
"""b6asm.py -- cc6502's generated assembly, read for a call made with an
argument register still holding the compiler's own scratch (docs/6502.md,
step 4e).

Calypsi cc6502 5.18 passes a function's first arguments in _Zp, _Zp+2 ...
and puts the address of a local on the C stack with

        ldx  #_Zp+k          ; where _LoadVspEA leaves the address
        lda  #offset
        jsr  _LoadVspEA
        ...
        lda  zp:_Zp+k        ; spilled to the C stack
        sta  (_Vsp),y

using an argument register as the scratch -- right when that register is
loaded with its argument afterwards, as _Zp+6 is in every ob_sst call but
one.  In src/aes/objc.c's ob_change the arguments are ob_change's own
first two parameters, forwarded in the same registers, and the compiler
took them to be there still: _Zp was the scratch, and ob_sst was called
with the last address spilled as its tree.  It read a junk object and,
whenever the junk's flags said INDIRECT, followed a junk spec into a bank
that does not exist (src/sys6502/farmem6502.c's far_bad stops there now).

And THE RUNTIME'S _Mul16to32, which returns a 16 x 16 -> 32 product with
its two low bytes swapped (Calypsi 5.18: 9 * 40 is $6801; the VDI's far
form rows and workstation records, the AES's mul_div).  bankasm.py sends
every banked call to src/sys6502/mul6502.s's b6_mul16to32; a reference
to the runtime's left in the rewritten assembly (build/b6502/*asm/*.b.s)
or in a resident object (build/b6502/res/*.o, which bankasm never sees)
is reported.

So: a call reached while an argument register (_Zp .. _Zp+7) last held a
_LoadVspEA scratch address that went to the C stack, with no store to the
register in between, is reported.  The assembly is the build's own
(--assembly-source, every banked unit: build/b6502/asm/), so `make b6asm`
builds the 6502 programs first.

    python3 tools/bsp6502/b6asm.py [FILE.s ...]   (default: build/b6502/asm)
    python3 tools/bsp6502/b6asm.py --self-test
"""
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARGREGS = 8                     # _Zp .. _Zp+7: the argument registers
HELPERS = ("_LoadVspEA", "_DecVsp", "_IncVsp")

LABEL = re.compile(r"^([A-Za-z_]\w*):")
LDX = re.compile(r"ldx\s+#_Zp(?:\+(\d+))?\s*$")
LDA = re.compile(r"lda\s+zp:_Zp(?:\+(\d+))?\s*$")
SPILL = re.compile(r"sta\s+\(_Vsp\),y\s*$")
STORE = re.compile(r"(?:sta|stx|sty)\s+zp:_Zp(?:\+(\d+))?\s*$")
JSR = re.compile(r"jsr\s+(\S+)")
END = re.compile(r"(?:rts|rti|jmp)\b")


def scan_lines(lines, name="?"):
    """[(line, function, callee, [registers])] for every bad call."""
    out = []
    func = None
    scratch = {}                # register -> 'ea' (written) or 'spilled'
    pend = None                 # the ldx #_Zp+k waiting for _LoadVspEA
    last = None                 # the register the last lda zp:_Zp+k read
    for i, ln in enumerate(lines):
        s = ln.split(";", 1)[0].strip()
        m = LABEL.match(ln)
        if m and not ln[:1].isspace():
            func, scratch, pend, last = m.group(1), {}, None, None
            continue
        m = LDX.match(s)
        if m:
            pend = int(m.group(1) or 0)
            continue
        m = JSR.match(s)
        if m and m.group(1) == "_LoadVspEA" and pend is not None:
            scratch[pend] = "ea"
            continue
        m = LDA.match(s)
        if m:
            last = int(m.group(1) or 0)
            continue
        if SPILL.match(s) and last is not None:
            for k in scratch:
                if scratch[k] == "ea" and last in (k, k + 1):
                    scratch[k] = "spilled"
            continue
        m = STORE.match(s)
        if m:
            k = int(m.group(1) or 0)
            for r in list(scratch):
                if k in (r, r + 1):
                    del scratch[r]
            continue
        m = JSR.match(s)
        if m and m.group(1) not in HELPERS:
            bad = sorted(k for k, v in scratch.items() if v == "spilled" and k < ARGREGS)
            if bad:
                out.append((i + 1, func, m.group(1), bad))
            scratch, pend = {}, None
            continue
        if END.match(s):
            scratch, pend = {}, None
    return out


# -- the self-test: ob_change's call as cc6502 5.18 wrote it, and as the
# workaround makes it --------------------------------------------------------
BAD = """\
ob_change:  ldx     #60
            ldy     #15
            jsr     _AllocStackSave
            lda     zp:_Zp
            sta     zp:_Zp+24
            lda     #-10
            jsr     _DecVsp
            ldx     #_Zp
            lda     #68
            jsr     _LoadVspEA
            ldy     #9
            lda     zp:_Zp+1
            sta     (_Vsp),y
            dey
            lda     zp:_Zp
            sta     (_Vsp),y
            ldx     #_Zp+6
            lda     #28
            jsr     _LoadVspEA
            jsr     ob_sst
            rts
"""
GOOD = BAD.replace("""            jsr     ob_sst
""", """            lda     zp:_Zp+24
            sta     zp:_Zp
            lda     zp:_Zp+25
            sta     zp:_Zp+1
            jsr     ob_sst
""")
# scratch in _Zp+6, then _Zp+6 loaded with its own argument: right
ARG6 = BAD.replace("ldx     #_Zp\n", "ldx     #_Zp+6\n").replace(
    "lda     zp:_Zp+1\n            sta     (_Vsp),y\n            dey\n            lda     zp:_Zp\n",
    "lda     zp:_Zp+7\n            sta     (_Vsp),y\n            dey\n            lda     zp:_Zp+6\n")


def self_test():
    fails = 0
    for name, text, want in (("bad", BAD, [(20, "ob_change", "ob_sst", [0])]),
                             ("reloaded", GOOD, []), ("arg6", ARG6, [])):
        got = scan_lines(text.splitlines(), name)
        ok = got == want
        print(f"  {'ok' if ok else 'FAIL'}: {name}: {got}")
        fails += not ok
    print(f"b6asm self-test: {'PASS' if not fails else 'FAIL'}")
    return 1 if fails else 0


BAD_RUNTIME = ("_Mul16to32",)


def runtime_refs(root=ROOT):
    """(file, symbol) for every reference to a runtime helper that is wrong."""
    out = []
    for f in sorted(glob.glob(os.path.join(root, "build", "b6502", "*asm", "*.b.s"))):
        text = open(f, errors="replace").read()
        out += [(f, sym) for sym in BAD_RUNTIME if re.search(r"(?<![\w`])" + sym + r"(?![\w`])", text)]
    for f in sorted(glob.glob(os.path.join(root, "build", "b6502", "res", "*.o"))):
        data = open(f, "rb").read()
        out += [(f, sym) for sym in BAD_RUNTIME if sym.encode() + b"\0" in data]
    return out


def main(argv):
    if "--self-test" in argv:
        return self_test()
    files = argv[1:] or sorted(f for f in glob.glob(os.path.join(ROOT, "build", "b6502", "asm", "*.s"))
                               if not f.endswith(".b.s"))
    if not files:
        print("b6asm: no assembly: build the 6502 programs first")
        return 1
    found = 0
    for f in files:
        for line, func, callee, regs in scan_lines(open(f, errors="replace").read().splitlines(), f):
            regs = ", ".join("_Zp" + (f"+{k}" if k else "") for k in regs)
            print(f"{os.path.relpath(f, ROOT)}:{line}: {func} calls {callee} with {regs} "
                  f"still the compiler's scratch, spilled -- not its argument")
            found += 1
    bad = runtime_refs() if len(argv) == 1 else []
    for f, sym in bad:
        print(f"{os.path.relpath(f, ROOT)}: calls the runtime's {sym}, which is wrong "
              f"(src/sys6502/mul6502.s; bankasm.py renames it in banked code)")
    st = self_test() if found == 0 else 0
    print(f"b6asm: {len(files)} files, {found} call(s) with a scratch argument, "
          f"{len(bad)} reference(s) to a runtime helper that is wrong")
    return 1 if found or bad or st else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
