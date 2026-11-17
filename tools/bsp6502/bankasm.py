#!/usr/bin/env python3
"""bankasm.py -- a banked file's assembly, every cross-bank reference
sent through a veneer.

    python3 tools/bsp6502/bankasm.py --index OUT.idx --bank SECTION=N ... A.s B.s ...
    python3 tools/bsp6502/bankasm.py IN.s OUT.s --tu NAME --bank SECTION=N ... [--index IDX]

cc6502 compiles a banked file to assembly (--assembly-source), each
function in a `.section NAME,text` of its own, named for its bank by the
file's `#pragma clang section` and its BANK_TEXT cuts (docs/6502.md).
Calypsi calls a function in a bank with a plain JSR to the window, and
nothing maps the bank first, so this rewrites the file before it is
assembled.  A FUNCTION here is the first label of a text section; it is
BANKED when that section is in the --bank list.

THE INDEX (--index alone) is the program's: which bank every public
banked function is in, read from all its banked files.  With it, a file
knows the banks of the functions it calls in other files, not only its
own.  Then, for every reference to a banked function F:

  - from F's own bank (JSR, JMP, or anything else): straight to F, no
    trampoline -- also across files, which is most of what the index buys;
  - a JSR or JMP from another bank k: through a veneer of this file's in
    BANK k, `TU__F__vk`.  The trampoline (src/sys6502/bank6502.s, _bcall)
    reads the veneer before it maps F's bank, so the caller's bank may
    hold it, and resident memory -- the 6502 build's scarcest -- does not;
  - an address taken (.word, #.byte0, #.byte1) -- from ANY bank, F's own
    included -- or a reference from resident code: the RESIDENT veneer,
    which maps F's bank, calls F and maps the caller's back.  A function
    pointer may be called from any bank, so it must name resident code
    (step 4c: newrect handed everyobj, in another bank, the raw address of
    mkrect, in newrect's own).  A jump table of static handlers
    and a device's table of functions work as written, and the C needs
    nothing.

A PUBLIC banked function F is renamed F__b, and its resident veneer takes
the name F: resident code and every other file's address of F arrive
through it.  Each resident veneer is a section of its own, so the linker
keeps only the ones something refers to.  A STATIC banked function
referenced from another bank gets a public alias TU__F (TU the --tu, so
two files' statics do not meet); its resident veneer is TU__F__v.

A JMP to a shared tail in another bank -- the optimiser merges identical
function tails across functions -- is replaced by a copy of that tail.

The compiler's copy of the C source, its `;` comment lines, is dropped:
as6502 reads /* */ inside them as a comment, and a C comment spread over
two lines takes the assembly between them with it.

tools/bsp6502/bankcheck.py checks the result from the other side: the
assembly (with the same index), the link map, and the linked code itself.
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


def scan(lines, banks):
    """Pass 1: which section each line is in, the file's functions and their
    sections, and its .public names."""
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
    return sect_of_line, func_sect, publics


BANK_DATA = re.compile(r"^(\s+\.section\s+)([A-Za-z_]\w*)__bank\s*,\s*(bss|data)\s*$")


def bank_data(lines, banks):
    """A variable BANK_DATA("X") put in section X__bank (src/portab.h): its
    bytes go into bank X with the code, PORTB banks being RAM -- the
    section's kind made text, so the linker places its bits in the bank's
    memory (gem6502.scm lists X__bank with X).  Zero for bss, as .space
    assembles in a text section."""
    out = []
    for ln in lines:
        m = BANK_DATA.match(ln)
        if m:
            if m.group(2) not in banks:
                raise SystemExit(f"bankasm: BANK_DATA(\"{m.group(2)}\"): no such bank section")
            ln = f"{m.group(1)}{m.group(2)}__bank,text"
        out.append(ln)
    return out


SWITCH = re.compile(r"^(\s+\.section\s+)switch\s*,\s*rodata\s*$")


def switch_in_bank(lines, banks):
    """--switch-in-bank: a switch's jump table in its function's own bank.
    cc6502 puts each in a `switch,rodata` section, which the link file
    places in resident memory; but a table is indexed by its own function
    alone -- `adc #.byte0 table`, never handed anywhere -- and its entries
    are that function's own case labels, so it can sit beside the function
    in the bank, which is mapped whenever the table is read.  The OWNER is
    the text section that names the table's label (the tables all come at
    the end of the file, after every function, so the section before one
    is nobody's); a table whose owner is in bank X goes in X__bank, as
    BANK_DATA's do (the link file lists X__bank with X), and one whose
    owner is resident, or that nothing names, stays where it was.
    src/sys/abi.c's crysbind has the AES's opcodes in two such tables."""
    owner, cur = {}, None
    for ln in lines:
        m = SECTION.match(ln)
        if m:
            cur = m.group(1) if (m.group(2) or "") == "text" else None
            continue
        if cur in banks:
            for t in re.findall(r"#\.byte[01]\s+(`[^`]+`|[A-Za-z_]\w*)", ln):
                owner.setdefault(t, cur)
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        sw = SWITCH.match(ln)
        if sw:
            lab = LABEL.match(lines[i + 1]) if i + 1 < len(lines) else None
            o = owner.get(lab.group(1)) if lab else None
            if o in banks:
                ln = f"{sw.group(1)}{o}__bank,text"
        out.append(ln)
        i += 1
    return out


def read_source(path):
    # The C source, which cc6502 copies in as `;` comment lines, goes: as6502
    # still honours /* */ inside them, so a C comment that opens on one
    # line and closes on a later one swallows the assembly between --
    # `static WORD cur_drawn;  /* ...` over two lines lost cur_drawn's
    # label, and every use of it was "undefined symbol" (Calypsi 5.18).
    return [ln for ln in open(path).read().splitlines() if not ln.lstrip().startswith(";")]


# THE RUNTIME'S HELPERS THAT ARE WRONG, and gem4xe's own in their place
# (src/sys6502/mul6502.s).  The library's _Mul16to32 returns the product
# with its two low bytes swapped (Calypsi 5.18: 9 * 40 is $6801); it
# cannot be overridden at the link, because integer.o comes in for _Mul32
# anyway and brings its own, so every call is sent to the other name here.
# tools/bsp6502/b6asm.py refuses any call to the runtime's left in a build.
RUNTIME_FIX = {"_Mul16to32": "b6_mul16to32"}
FIX_TOKEN = re.compile(r"(?<![\w`])(" + "|".join(RUNTIME_FIX) + r")(?![\w`])")


def runtime_fixes(lines):
    return [FIX_TOKEN.sub(lambda m: RUNTIME_FIX[m.group(1)], ln) for ln in lines]


def parse_banks(argv):
    banks, rest, i = {}, [], 0
    while i < len(argv):
        if argv[i] == "--bank":
            sect, n = argv[i + 1].split("=")
            banks[sect] = int(n)
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return banks, rest


def make_index(argv):
    """--index OUT.idx --bank ... A.s B.s ...: every public function in a
    bank, program-wide, as `NAME BANK` lines."""
    banks, rest = parse_banks(argv)
    out = rest[rest.index("--index") + 1]
    srcs = [a for a in rest if a.endswith(".s")]
    seen = {}
    for src in srcs:
        _, func_sect, publics = scan(read_source(src), banks)
        for f, sct in func_sect.items():
            if sct in banks and f in publics:
                if f in seen:
                    raise SystemExit(f"bankasm: {f} is defined in {seen[f][0]} and {src}")
                seen[f] = (src, banks[sct])
    with open(out, "w") as fh:
        for f in sorted(seen):
            fh.write(f"{f} {seen[f][1]}\n")
    print(f"bankasm: {out}: {len(seen)} public banked function(s) in {len(srcs)} file(s)")
    return 0


def read_index(path):
    ext = {}
    for ln in open(path):
        if ln.strip():
            name, n = ln.split()
            ext[name] = int(n)
    return ext


def main(argv):
    if "--index" in argv and "--tu" not in argv:
        return make_index(argv)
    if len(argv) < 3:
        print(__doc__)
        return 2
    src, dst = argv[1], argv[2]
    tu = argv[argv.index("--tu") + 1]
    banks, _ = parse_banks(argv[3:])
    ext = read_index(argv[argv.index("--index") + 1]) if "--index" in argv else {}
    lines = bank_data(runtime_fixes(read_source(src)), banks)
    if "--switch-in-bank" in argv:
        lines = switch_in_bank(lines, banks)
    lines = localise_tails(lines, banks)
    sect_of_line, func_sect, publics = scan(lines, banks)

    banked = {f: s for f, s in func_sect.items() if s in banks}
    for f in banked:                    # this file's own, as this file has them
        ext.pop(f, None)

    def bank(s):
        return banks.get(s, 0)          # 0: resident (or data)

    def entry(f):
        """The name a same-bank reference to f uses."""
        return f + "__b" if (f not in banked or f in publics) else f

    # RESIDENT veneers: an address taken, or resident code's reference
    veneer_for, need_alias = {}, set()

    def via_veneer(f):
        if f in publics:
            veneer_for[f] = f
            return f
        need_alias.add(f)
        v = f"{tu}__{f}__v"
        veneer_for[f] = v
        return v

    # BANK veneers: a call from bank k, in a section of bank k
    bank_veneers = {}                   # (f, k) -> (name, section)

    def bank_veneer(f, k, sect):
        if (f, k) not in bank_veneers:
            if f in banked and f not in publics:
                need_alias.add(f)
            bank_veneers[(f, k)] = (f"{tu}__{f}__v{k}", sect)
        return bank_veneers[(f, k)][0]

    out, direct, used_ext = [], 0, set()
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
                nonlocal direct
                f = t.group(1)
                if f in banked:
                    fb = banks[banked[f]]
                elif f in ext:
                    fb = ext[f]
                else:
                    return f
                hb = bank(here)
                # AN ADDRESS TAKEN -- #.byte0 F, .word F -- is the resident
                # veneer, whatever bank takes it: a function pointer is
                # called from wherever it is handed, and handed to another
                # bank's code (everyobj, in objc's banks, calling wind.c's
                # mkrect) the bank's own address names whatever that bank
                # has there.  Step 4c's crash: newrect passed mkrect, both
                # in bank wind, as $4A0F, and everyobj jumped into the
                # middle of ob_format.
                if op not in ("jsr", "jmp"):
                    return via_veneer(f) if f in banked else f
                if hb and hb == fb:
                    if f not in banked:
                        direct += 1
                        used_ext.add(entry(f))
                    return entry(f)
                if hb:
                    return bank_veneer(f, hb, here)
                # resident code: the resident veneer (another file's
                # public F is its own resident veneer)
                return via_veneer(f) if f in banked else f
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

    # every public banked function gets a resident veneer, called or not
    # here: other files and resident code reach it by its name.  Each is a
    # section of its own, so the linker keeps only those something uses.
    for f in banked:
        if f in publics:
            veneer_for.setdefault(f, f)

    def target(f):
        return entry(f) if f not in banked or f in publics else f"{tu}__{f}"

    def fbank(f):
        return banks[banked[f]] if f in banked else ext[f]

    final.append("")
    final.append(";;; veneers (tools/bsp6502/bankasm.py)")
    final.append("              .extern _bcall")
    for f, v in sorted(veneer_for.items()):
        final.append("              .section veneer")
        final.append(f"              .public {v}")
        final.append(f"{v}:          jsr     _bcall")
        final.append(f"              .word   {target(f)}")
        final.append(f"              .byte   {fbank(f)}")
    # a bank's veneers in the bank: _bcall reads the veneer before it maps
    # the target's bank, so the caller's bank may hold it
    for (f, k), (v, sect) in sorted(bank_veneers.items()):
        final.append(f"              .section {sect},text")
        final.append(f"              .public {v}")
        final.append(f"{v}:          jsr     _bcall")
        final.append(f"              .word   {target(f)}")
        final.append(f"              .byte   {fbank(f)}")
    # another file's entries, named here only now
    externs = sorted(used_ext | {target(f) for (f, _k) in bank_veneers if f not in banked})
    if externs:
        final.insert(0, f"              .extern {', '.join(externs)}")
    open(dst, "w").write("\n".join(final) + "\n")
    print(f"bankasm: {src}: {len(banked)} banked function(s), {len(veneer_for)} resident "
          f"veneer(s), {len(bank_veneers)} in banks, {direct} direct call(s) to another "
          f"file in the same bank, {len(need_alias)} static(s) aliased")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
