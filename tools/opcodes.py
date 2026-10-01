#!/usr/bin/env python3
"""Which AES and VDI OPCODES the engine serves, by enumeration.

tools/surface.py answers a different question -- which NAMES the kit
declares, against the ones gemlib declares -- and the two can disagree in
both directions, which is the reason this file exists.  It found three
such disagreements on its first run, all of them in wind_get's fields:
WF_SCREEN and WF_OWNER were SERVED and not declared, so a port had to
#define them itself (qed did), and WF_BOTTOM was DECLARED and not served.
All three are settled now -- the three are declared and wind_get answers
them -- which is what the audit is for.

A name in a header is a promise; an opcode in a dispatcher is the thing
that keeps it.  This reads the dispatchers.

WHAT IT DOES NOT MEASURE: the FIELDS an opcode takes.  wind_get is one
opcode and twenty-odd questions, and serving the opcode says nothing
about which of them are answered.  Those are checked where they are
implemented -- tests/host/test_wind_order.py for the window order.

    python3 tools/opcodes.py            # what is missing
    python3 tools/opcodes.py --all      # every opcode, served or not

The AES names are EmuTOS's include/aesdefs.h, which is the Caldera-GPL
AES's own opcode table; the VDI names come out of gem4xe's own jump
tables, where each handler is `vdi_<name>` and an unserved slot is
`v_nop`.  Neither list is typed here, so neither can drift.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EMUTOS = os.path.expanduser("~/dev/emutos")
ABI_C = os.path.join(ROOT, "src", "sys", "abi.c")
VDI_C = os.path.join(ROOT, "src", "vdi", "vdi.c")

# The opcodes an AES serves at all.  Below 10 is the VDI's business.
AES_LO, AES_HI = 10, 137


def aes_names():
    """opcode -> name, from EmuTOS's AES opcode table.

    ONLY the opcode block, which is why this looks for its heading and
    stops at the next one.  aesdefs.h goes on to define field, message
    and size constants in the same 10..137 range -- I_SIZE is 16,
    WF_COLOR is 18, WM_SIZED is 27 -- and a reader that takes every
    #define in range reports those as missing AES calls.  The first
    version of this file did exactly that and claimed five opcodes that
    do not exist."""
    path = os.path.join(EMUTOS, "include", "aesdefs.h")
    if not os.path.exists(path):
        return {}
    out, inblock = {}, False
    with open(path, errors="ignore") as f:
        for line in f:
            if "AES opcodes" in line:
                inblock = True
                continue
            if inblock and re.match(r"\s*/\*", line) and "Manager" not in line \
                    and "function" not in line:
                break                       # the next section's heading
            if not inblock:
                continue
            m = re.match(r"#define\s+([A-Z_0-9]+)\s+(\d+)\b", line)
            if m and AES_LO <= int(m.group(2)) <= AES_HI:
                out.setdefault(int(m.group(2)), m.group(1).lower())
    return out


def aes_served():
    """The opcodes crysbind() has a case for."""
    with open(ABI_C, errors="ignore") as f:
        src = f.read()
    i = src.index("static WORD crysbind(")
    j = src.index("static void aes_entry(", i)
    body = src[i:j]
    return {int(n) for n in re.findall(r"^\s*case (\d+):", body, re.M)}


def vdi_table(name):
    """opcode -> (handler, note), out of one of gem4xe's jump tables.

    Paired by the table's OWN comment -- `handler, /* 12 */` -- rather
    than by counting commas, for two reasons.  The comment carries the
    opcode number, so a miscount cannot silently shift every name by one;
    and each comment TRAILS its handler's comma, so a reader that takes
    the comment out of the same comma-separated piece as the handler gets
    the previous entry's number.  The first version did that and named
    every v_nop slot "(slot N)" because it had found the wrong comment.
    """
    with open(VDI_C, errors="ignore") as f:
        src = f.read()
    i = src.index(f"{name}[] = {{")
    body = src[i:src.index("};", i)]
    out = {}
    # The comma is OPTIONAL: the last entry of a table has none, and
    # requiring it dropped one slot from each table -- silently, which is
    # the failure this whole file exists to stop.  contiguous() below
    # makes any such loss loud instead.
    for m in re.finditer(r"(\w+)\s*,?\s*/\*\s*(\d+)\s*([^*]*?)\s*\*/", body):
        handler, op, note = m.group(1), int(m.group(2)), m.group(3).strip()
        # A `(nop)` marker, or a note saying the opcode does not exist, is
        # the TABLE stating that the slot is settled rather than unwritten.
        # Keeping that apart from a bare v_nop is the difference between
        # "five decisions" and "five things to go and do" -- this tool
        # reported the former as the latter once, and it sent somebody
        # looking to close them before a release.
        settled = note.endswith("(nop)") or "does not exist" in note
        out[op] = (handler, re.sub(r"\s*\(nop\)$", "", note), settled)
    return out


def contiguous(names, lo, hi, what):
    """Every opcode in lo..hi must have been found, or the parse lost
    entries and every count after it is wrong."""
    gaps = [n for n in range(lo, hi + 1) if n not in names]
    if gaps:
        raise AssertionError(
            f"{what}: the parse found no entry for {gaps} -- the table was "
            f"read wrongly, so no number in this report can be trusted")


def report(kind, served, names, show_all):
    have = sorted(n for n in names if n in served)
    miss = sorted(n for n in names if n not in served)
    print(f"\n{kind}: {len(have)} of {len(names)} opcodes served")
    rows = names.items() if show_all else [(n, names[n]) for n in miss]
    for n, nm in sorted(rows):
        mark = "ok  " if n in served else "MISS"
        print(f"    {mark} {n:4d}  {nm}")
    # SERVED AND UNNAMED.  The AES names come from EmuTOS, whose AES is
    # 1.40's, so an opcode gem4xe serves from a LATER AES has no row
    # above and would otherwise be counted by neither side -- appl_getinfo
    # (130) was served for a whole commit while this said "65 of 79"
    # before and after.  An audit that exists to stop a silent gap must
    # not have one of its own.
    extra = sorted(n for n in served if n not in names)
    if extra:
        print(f"    -- and {len(extra)} served that {kind}'s name table does "
              f"not carry: {', '.join(str(n) for n in extra)}")
    return miss


# Served here and absent from EmuTOS's include/aesdefs.h, so the audit
# reports them as "served that AES's name table does not carry".  They
# still belong in a reference a person reads.
EXTRA_AES = {130: "appl_getinfo"}


# ---- below the opcodes: the questions one opcode answers ---------------
# wind_get and wind_set are one opcode each and twenty-odd fields;
# appl_getinfo is one opcode and fifteen subjects; objc_sysvar a dozen
# settings; and GEMDOS is a trap, not an AES opcode at all.  Each is read
# out of the C function that answers it -- its `case` labels -- and set
# against a list this tree does not keep: EmuTOS's, or the kit's gem.h.

AES_H = os.path.join(ROOT, "src", "aes", "aes.h")
APPL_C = os.path.join(ROOT, "src", "aes", "appl.c")
WIND_C = os.path.join(ROOT, "src", "aes", "wind.c")
OBJC_C = os.path.join(ROOT, "src", "aes", "objc.c")
GEMDOS_C = os.path.join(ROOT, "src", "sys", "gemdos.c")
GEMDOS_H = os.path.join(ROOT, "src", "sys", "gemdos.h")
KIT_H = os.path.join(ROOT, "src", "app", "gem.h")


def read(path):
    with open(path, errors="ignore") as f:
        return f.read()


def c_body(src, head):
    """The function whose definition starts with `head`, to its closing
    brace, braces counted."""
    i = src.index(head)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError(head)


def defines(*paths, prefix):
    """NAME -> number for every `#define PREFIXxxx n` in the files."""
    out = {}
    for p in paths:
        for m in re.finditer(rf"#define\s+({prefix}\w*)\s+(-?(?:0x[0-9A-Fa-f]+|\d+))L?\b",
                             read(p)):
            out.setdefault(m.group(1), int(m.group(2), 0))
    return out


def case_numbers(body, names):
    """The numbers a body's `case` labels stand for."""
    out = set()
    for lab in re.findall(r"\bcase\s+([A-Za-z_0-9]+)\s*:", body):
        if lab in names:
            out.add(names[lab])
        elif re.fullmatch(r"\d+|0x[0-9A-Fa-f]+", lab):
            out.add(int(lab, 0))
    return out


def wind_fields():
    """(number -> name, served by wind_get, served by wind_set)."""
    mine = defines(AES_H, prefix="WF_")
    names = {}
    for nm, n in defines(KIT_H, prefix="WF_").items():
        names.setdefault(n, nm)
    for nm, n in defines(os.path.join(EMUTOS, "include", "aesdefs.h"),
                         prefix="WF_").items():
        names.setdefault(n, nm)
    src = read(WIND_C)
    get = case_numbers(c_body(src, "WORD wm_get("), mine)
    put = case_numbers(c_body(src, "WORD wm_set("), mine)
    for n in get | put:
        names.setdefault(n, f"(field {n})")
    return names, get, put


def getinfo_subjects():
    """(number -> name, answered)."""
    names = {n: nm for nm, n in defines(APPL_C, prefix="AI_").items() if n >= 0}
    body = c_body(read(APPL_C), "WORD ap_getinfo(")
    return names, case_numbers(body, {v: k for k, v in names.items()} and
                               {nm: n for n, nm in names.items()})


def sysvar_settings():
    """(number -> name, settable, answered): objc_sysvar's two switches,
    the SET one first."""
    names = {}
    for nm, n in defines(KIT_H, prefix="").items():
        if nm in ("LK3DIND", "LK3DACT", "INDBUTCOL", "ACTBUTCOL", "BACKGRCOL",
                  "AD3DVALUE") or nm.startswith("G4_"):
            names[n] = nm
    lookup = {nm: n for n, nm in names.items()}
    body = c_body(read(OBJC_C), "WORD ob_sysvar(")
    k = body.index("switch (which)")
    k2 = body.index("switch (which)", k + 1)
    return names, case_numbers(body[k:k2], lookup), case_numbers(body[k2:], lookup)


# GEMDOS calls EmuTOS serves outside bdosmain.c's table, which has NI in
# their slots: Super switches the CPU's mode, so it is answered in the trap
# handler itself (bdos/rwa.S).  Read from the table alone, every TOS's
# oldest call looked like one EmuTOS lacks.
EMUTOS_ELSEWHERE = {0x20: "xsuper"}


def gemdos_functions():
    """(number -> name, served, EmuTOS's): served is gemdos.c's case
    labels, in gd_nopath and gemdos_call; EmuTOS's is every number its
    bdos/bdosmain.c function table has an implementation for."""
    gd = defines(GEMDOS_H, GEMDOS_C, prefix="GD_")
    src = read(GEMDOS_C)
    served = (case_numbers(c_body(src, "static LONG gd_nopath("), gd)
              | case_numbers(c_body(src, "void gemdos_call("), gd))
    names = {}
    for nm, n in gd.items():
        if n in served:
            names.setdefault(n, nm[3:].capitalize())
    emu = {}
    path = os.path.join(EMUTOS, "bdos", "bdosmain.c")
    if os.path.exists(path):
        for m in re.finditer(r"\{\s*F\((\w+)\)[^}]*\}\s*,?\s*/\*\s*0x([0-9A-Fa-f]+)", read(path)):
            emu.setdefault(int(m.group(2), 16), m.group(1))
    # ...and the ones EmuTOS dispatches before its table is reached
    emu.update(EMUTOS_ELSEWHERE)
    for n, en in emu.items():
        names.setdefault(n, en.lstrip("x").capitalize() + " (EmuTOS's name)")
    return names, served, set(emu)


def markdown(path, an, aserved, vnames, vserved, vsettled):
    """The same audit as a table, for the kit to carry.

    A developer's question is not "how many are served" but "will
    menu_popup work" -- and include/gem.h is 1,255 lines of declarations
    that cannot answer it, because DECLARED is not SERVED.  This is
    generated from the dispatchers, so it cannot drift from them.
    """
    out = ["# What gem4xe serves",
           "",
           "Generated by `tools/opcodes.py --md` from the AES's and the",
           "VDI's own dispatch tables -- not from a header, and not from a",
           "list somebody keeps by hand. **Declared is not served**, which",
           "is the distinction this exists for.",
           "",
           f"**AES: {len(aserved & set(an))} of {len(an)} opcodes.**",
           f"**VDI: {len(vserved)} of {len(vnames)}.**",
           "",
           "## AES", "", "| opcode | name | |", "|---|---|---|"]
    # ...including the ones EmuTOS's name table does not carry.  130 is
    # appl_getinfo, which is the call a porter is most likely to ask
    # about, and it was missing from this table for exactly that reason.
    names = dict(an)
    for n in aserved - set(an):
        names[n] = EXTRA_AES.get(n, f"(opcode {n})")
    for n in sorted(names):
        out.append(f"| {n} | `{names[n]}` | "
                   f"{'served' if n in aserved else '**not served**'} |")
    out += ["", "## VDI", "", "| opcode | name | |", "|---|---|---|"]
    for n in sorted(vnames):
        if n in vsettled:
            mark = "**dispatches to v_nop on purpose** -- `src/vdi/vdi.c` says why"
        elif n in vserved:
            mark = "served"
        else:
            mark = "**not served**"
        out.append(f"| {n} | `{vnames[n]}` | {mark} |")
    out += ["",
            "A `v_nop` here is a DECISION, not a gap: DRI's own shipping",
            "driver nopped ten opcodes.  A call to one returns cleanly and",
            "draws nothing, which is what an application expects of it.",
            ""]

    def yes(b):
        return "yes" if b else "--"

    names, get, put = wind_fields()
    out += ["## wind_get and wind_set fields", "",
            f"**{len(get)} answered by wind_get, {len(put)} taken by "
            f"wind_set**, out of the fields EmuTOS's `aesdefs.h` and the kit's "
            f"`gem.h` name.  From the `case` labels of `wm_get` and `wm_set` "
            f"(`src/aes/wind.c`).  A field a call does not take makes it "
            f"return 0, which is failure.", "",
            "| field | name | wind_get | wind_set |", "|---|---|---|---|"]
    for n in sorted(names):
        out.append(f"| {n} | `{names[n]}` | {yes(n in get)} | {yes(n in put)} |")

    names, ans = getinfo_subjects()
    out += ["", "## appl_getinfo subjects", "",
            f"**{len(ans)} subjects answered.**  From `ap_getinfo`'s `case` "
            f"labels (`src/aes/appl.c`); a subject it does not know answers "
            f"FALSE, as an AES should.  64 and up are gem4xe's own.", "",
            "| subject | name | |", "|---|---|---|"]
    for n in sorted(names):
        out.append(f"| {n} | `{names[n]}` | {'answered' if n in ans else 'FALSE'} |")

    names, sets, asks = sysvar_settings()
    out += ["", "## objc_sysvar settings", "",
            "From `ob_sysvar`'s two switches (`src/aes/objc.c`).  100 and up "
            "are gem4xe's own.", "",
            "| which | name | inquire | set |", "|---|---|---|---|"]
    for n in sorted(names):
        out.append(f"| {n} | `{names[n]}` | {yes(n in asks)} | {yes(n in sets)} |")

    names, served, emu = gemdos_functions()
    gone = sorted(emu - served)
    own = sorted(served - emu)
    out += ["", "## GEMDOS functions", "",
            f"**{len(served & emu)} of the {len(emu)} EmuTOS implements, and "
            f"{len(own)} more.**  From the `case` labels of `gd_nopath` and "
            f"`gemdos_call` (`src/sys/gemdos.c`), against the function table "
            f"in EmuTOS's `bdos/bdosmain.c`.  There is no BIOS or XBIOS: a "
            f"program reaches the machine through the VDI, the AES and "
            f"GEMDOS only (`src/sys/abi.c`).", "",
            "| function | name | |", "|---|---|---|"]
    for n in sorted(names):
        if n in served:
            mark = "served" if n in emu else "served -- **not in EmuTOS**"
        else:
            mark = "**not served**"
        out.append(f"| 0x{n:02X} | `{names[n]}` | {mark} |")
    out.append("")
    with open(path, "w") as f:
        f.write("\n".join(out))
    return len(out)


def main(argv):
    show_all = "--all" in argv
    md = None
    if "--md" in argv:
        i = argv.index("--md")
        md = argv[i + 1] if i + 1 < len(argv) else None
        if not md:
            print("--md wants a path")
            return 2
    an = aes_names()
    if not an:
        print(f"EmuTOS not found at {EMUTOS} -- the AES names come from its "
              f"include/aesdefs.h")
        return 2
    aserved = aes_served()
    amiss = report("AES", aserved, an, show_all)

    # The VDI: a slot is served unless its handler is v_nop -- and a
    # v_nop the table MARKS `(nop)` is a decision, not a gap.
    vnames, vserved, vsettled = {}, set(), {}
    for tbl in ("jmptb1", "jmptb2"):
        for op, (handler, note, settled) in vdi_table(tbl).items():
            if handler == "v_nop":
                vnames[op] = note or f"(slot {op})"
                if settled:
                    vsettled[op] = note or f"(slot {op})"
                    vserved.add(op)        # dispatched, deliberately empty
            else:
                vnames[op] = handler[4:] if handler.startswith("vdi_") else handler
                vserved.add(op)
    contiguous(vnames, 1, 39, "jmptb1")
    contiguous(vnames, 100, 131, "jmptb2")
    vmiss = report("VDI", vserved, vnames, show_all)

    if vsettled:
        print(f"\n{len(vsettled)} VDI opcode(s) dispatch to v_nop ON PURPOSE "
              f"(src/vdi/vdi.c says why each one):")
        for op in sorted(vsettled):
            print(f"    nop  {op:4d}  {vsettled[op]}")

    if md:
        markdown(md, an, aserved, vnames, vserved, vsettled)
        print(f"\n{md}: written")

    print(f"\n{len(amiss)} AES and {len(vmiss)} VDI opcodes are not served.")
    print("tools/surface.py answers the other half: which NAMES the kit "
          "declares against gemlib's.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
