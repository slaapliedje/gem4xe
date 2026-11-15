#!/usr/bin/env python3
"""bankasm.py -- a banked file's assembly, every cross-bank reference
sent through a veneer.

    python3 tools/bsp6502/bankasm.py IN.s OUT.s --tu NAME --bank SECTION=N ...

cc6502 compiles a banked file to assembly (--assembly-source), each
function in a `.section NAME,text` of its own, named for its bank by the
file's `#pragma clang section` and its BANK_TEXT cuts (docs/6502.md).
Calypsi calls a function in a bank with a plain JSR to the window, and
nothing maps the bank first, so this rewrites the file before it is
assembled.  A FUNCTION here is the first label of a text section; it is
BANKED when that section is in the --bank list.  Then:

  - Every reference to a banked function F -- JSR, JMP, .word, #.byte0,
    #.byte1 -- from anywhere but F's own bank (another bank's code, the
    file's resident code, a table in its data) is pointed at a veneer
    instead, which maps F's bank, calls F and maps the caller's back
    (src/sys6502/bank6502.s, _bcall).  So a jump table of static handlers,
    a device's table of functions and a call across a BANK_TEXT cut all
    work as written, and the C needs nothing.
  - A PUBLIC banked function F is renamed F__b, and its veneer takes the
    name F: every other file calls F and arrives through the veneer.
    References in F's own bank go straight to F__b.
  - A STATIC banked function referenced from another bank gets a public
    alias NAME__F (NAME the --tu, so two files' statics do not meet) and a
    veneer NAME__F__v.

A JMP to a shared tail in another bank -- the optimiser merges identical
function tails across functions -- is replaced by a copy of that tail.

The compiler's copy of the C source, its `;` comment lines, is dropped:
as6502 reads /* */ inside them as a comment, and a C comment spread over
two lines takes the assembly between them with it.

The veneers go at the end of the file, in section `veneer`, which the
link map keeps resident.  tools/bsp6502/bankcheck.py checks the result
from the other side: the link map, and the linked code itself.
"""
import re
import sys

SECTION = re.compile(r"^\s+\.section\s+([A-Za-z_][\w.]*)\s*(?:,\s*(\w+))?")
LABEL = re.compile(r"^([A-Za-z_][\w]*|`[^`]+`):")
PUBLIC = re.compile(r"^\s+\.public\s+(.+)$")
TOKEN = re.compile(r"(?<![\w`?])([A-Za-z_]\w*)(?![\w`])")
REFLINE = re.compile(r"^(\s*(?:[A-Za-z_]\w*:|`[^`]+`:)?\s*)(jsr|jmp|\.word|lda|ldx|ldy|"
                     r"adc|ora|and|eor|cmp|cpx|cpy|sbc|\.byte)(\s+)(.*)$")


LOCAL = re.compile(r"^(`\?L\d+`):\s*(.*)$")
TAILJMP = re.compile(r"^(\s*)jmp\s+(`\?L\d+`)\s*$")
END = re.compile(r"^\s*(rts|rti|jmp)\b")


def localise_tails(lines, banks):
    """The optimiser merges identical function tails, across functions and
    whatever their sections: `jmp ?L4340` from vdi_vsl_ends, bank 2, into
    the last two instructions of another function in bank 3.  A JMP to a
    local label in another bank is replaced by a copy of what is there, up
    to its RTS, RTI or JMP -- refused if that stretch has a label or a
    branch of its own, which a copy cannot carry."""
    where, sect = {}, None
    for i, ln in enumerate(lines):
        m = SECTION.match(ln)
        if m:
            sect = m.group(1)
        lab = LOCAL.match(ln)
        if lab:
            where[lab.group(1)] = (sect, i)
    out, sect = [], None
    for ln in lines:
        m = SECTION.match(ln)
        if m:
            sect = m.group(1)
        j = TAILJMP.match(ln)
        if j and j.group(2) in where:
            tsect, ti = where[j.group(2)]
            if tsect != sect and tsect in banks and banks.get(sect, 0) != banks[tsect]:
                body = []
                first = LOCAL.match(lines[ti]).group(2)
                k = ti + 1
                if first:
                    body.append("            " + first)
                while not (body and END.match(body[-1])):
                    if k >= len(lines) or LOCAL.match(lines[k]) or LABEL.match(lines[k]) \
                            or SECTION.match(lines[k]) or re.match(r"^\s*b[a-z]{2}\s", lines[k]):
                        raise SystemExit(f"bankasm: the shared tail {j.group(2)} in {tsect}, "
                                         f"jumped to from {sect}, is not a straight run")
                    body.append(lines[k])
                    k += 1
                out.append(f"{j.group(1)};;; {j.group(2)}'s tail, from {tsect} (bankasm)")
                out.extend(body)
                continue
        out.append(ln)
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    src, dst = argv[1], argv[2]
    tu = argv[argv.index("--tu") + 1]
    banks = {}
    i = 3
    while i < len(argv):
        if argv[i] == "--bank":
            sect, n = argv[i + 1].split("=")
            banks[sect] = int(n)
            i += 2
        else:
            i += 1
    # The C source, which cc6502 copies in as `;` comment lines, goes: as6502
    # still honours /* */ inside them, so a C comment that opens on one
    # line and closes on a later one swallows the assembly between --
    # `static WORD cur_drawn;  /* ...` over two lines lost cur_drawn's
    # label, and every use of it was "undefined symbol" (Calypsi 5.18).
    lines = [ln for ln in open(src).read().splitlines() if not ln.lstrip().startswith(";")]

    lines = localise_tails(lines, banks)

    # pass 1: which section each line is in, the functions and their banks
    sect_of_line, func_sect, publics = [], {}, set()
    cur, first = None, False
    for ln in lines:
        m = SECTION.match(ln)
        if m:
            cur = m.group(1)
            first = (m.group(2) or "") == "text" or cur in banks
        else:
            lab = LABEL.match(ln)
            if lab and first and not lab.group(1).startswith("`"):
                func_sect[lab.group(1)] = cur
                first = False
            elif ln.strip() and not ln.lstrip().startswith(";") and not ln.lstrip().startswith("."):
                first = False
            p = PUBLIC.match(ln)
            if p:
                publics |= {x.strip() for x in p.group(1).split(",")}
        sect_of_line.append(cur)

    banked = {f: s for f, s in func_sect.items() if s in banks}

    def bank(s):
        return banks.get(s, 0)          # 0: resident (or data)

    veneer_for, need_alias = {}, set()

    def via_veneer(f):
        if f in publics:
            veneer_for[f] = f
            return f
        need_alias.add(f)
        v = f"{tu}__{f}__v"
        veneer_for[f] = v
        return v

    out = []
    for idx, ln in enumerate(lines):
        here = sect_of_line[idx]
        m = REFLINE.match(ln)
        lab = LABEL.match(ln)
        p = PUBLIC.match(ln)
        if p:
            names = [x.strip() for x in p.group(1).split(",")]
            names = [n + "__b" if n in banked else n for n in names]
            out.append(f"              .public {', '.join(names)}")
            continue
        if lab and lab.group(1) in banked:
            f = lab.group(1)
            rest = ln[len(lab.group(0)):]
            if f in publics:
                ln = f"{f}__b:{rest}"
            out.append(ln)
            continue
        if m and here is not None:
            head, op, sp, operand = m.groups()

            def sub(t):
                f = t.group(1)
                if f not in banked:
                    return f
                same = bank(here) == banks[banked[f]] and bank(here) != 0
                if same:
                    return f + "__b" if f in publics else f
                return via_veneer(f)
            # comments after ';' are left alone
            code, sep, comment = operand.partition(";")
            code = TOKEN.sub(sub, code)
            ln = f"{head}{op}{sp}{code}{sep}{comment}"
        out.append(ln)

    # the aliases: a static function made reachable under a unique name
    final = []
    for ln in out:
        lab = LABEL.match(ln)
        if lab and lab.group(1) in need_alias:
            a = f"{tu}__{lab.group(1)}"
            final.append(f"              .public {a}")
            final.append(f"{a}:")
        final.append(ln)

    # every public banked function gets a veneer, called or not here:
    # other files reach it by its name
    for f in banked:
        if f in publics:
            veneer_for.setdefault(f, f)

    final.append("")
    final.append(";;; veneers (tools/bsp6502/bankasm.py)")
    final.append("              .extern _bcall")
    final.append("              .section veneer")
    for f, v in sorted(veneer_for.items()):
        target = f + "__b" if f in publics else f"{tu}__{f}"
        final.append(f"              .public {v}")
        final.append(f"{v}:          jsr     _bcall")
        final.append(f"              .word   {target}")
        final.append(f"              .byte   {banks[banked[f]]}")
    open(dst, "w").write("\n".join(final) + "\n")
    print(f"bankasm: {src}: {len(banked)} banked function(s), {len(veneer_for)} veneer(s), "
          f"{len(need_alias)} static(s) aliased")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
