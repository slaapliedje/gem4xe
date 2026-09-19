#!/usr/bin/env python3
"""Which AES and VDI OPCODES the engine serves, by enumeration.

tools/surface.py answers a different question -- which NAMES the kit
declares, against the ones gemlib declares -- and the two can disagree in
both directions, which is the reason this file exists:

  * WF_SCREEN and WF_OWNER are SERVED by the window manager and not
    declared in gem.h, so a port has to #define them itself (qed did);
  * WF_BOTTOM is DECLARED in gem.h and not served.

A name in a header is a promise; an opcode in a dispatcher is the thing
that keeps it.  This reads the dispatchers.

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
        out[op] = (handler, re.sub(r"\s*\(nop\)$", "", note))
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
    return miss


def main(argv):
    show_all = "--all" in argv
    an = aes_names()
    if not an:
        print(f"EmuTOS not found at {EMUTOS} -- the AES names come from its "
              f"include/aesdefs.h")
        return 2
    aserved = aes_served()
    amiss = report("AES", aserved, an, show_all)

    # The VDI: a slot is served unless its handler is v_nop.
    vnames, vserved = {}, set()
    for tbl in ("jmptb1", "jmptb2"):
        for op, (handler, note) in vdi_table(tbl).items():
            if handler == "v_nop":
                vnames[op] = note or f"(slot {op})"
            else:
                vnames[op] = handler[4:] if handler.startswith("vdi_") else handler
                vserved.add(op)
    contiguous(vnames, 1, 39, "jmptb1")
    contiguous(vnames, 100, 131, "jmptb2")
    vmiss = report("VDI", vserved, vnames, show_all)

    print(f"\n{len(amiss)} AES and {len(vmiss)} VDI opcodes are not served.")
    print("tools/surface.py answers the other half: which NAMES the kit "
          "declares against gemlib's.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
