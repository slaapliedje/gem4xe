#!/usr/bin/env python3
"""Re-derive every claim made to Calypsi about `.scatterTo28` (issue #89).

A report sent upstream is worth exactly what its weakest sentence is
worth, so nothing here is quoted from a previous run: this assembles and
links the files beside it, reads the values out of the LINKED IMAGE, and
prints each claim with the evidence next to it.  Run it before saying any
of this to anybody.

    python3 tools/ccbug/scatter/validate.py [--calypsi DIR]

Exit status is the number of claims that did not hold.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BANK_BASE = 0x10000          # where atari.scm puts the flat store
BANK_SIZE = 0x4000           # the Atari's window, and so a bank
WINDOW = 0x4000              # ...and the address it appears at

results = []


def claim(text, ok, evidence=""):
    results.append((text, bool(ok), evidence))
    print(f"  {'ok  ' if ok else 'FAIL'}  {text}")
    if evidence:
        for line in str(evidence).splitlines():
            print(f"            {line}")


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, **kw)


def assemble_ok(asm, src_line, extern="far_a"):
    """True if a single line assembles, with the tool's first message.

    THE INDENTATION MATTERS and cost this file its first answer: a
    directive written in column 0 is read as a LABEL, so every form came
    back 'illegal symbol syntax' and looked like a rejection of the
    operator.  Everything is indented here for that reason."""
    with tempfile.TemporaryDirectory() as d:
        s = os.path.join(d, "v.s")
        with open(s, "w") as f:
            f.write('              .rtmodel version, "1"\n'
                    '              .rtmodel core, "*"\n'
                    f'              .extern {extern}\n'
                    '              .section code, root\n'
                    f'              {src_line}\n')
        r = run([asm, "-o", os.path.join(d, "v.o"), s])
        msg = r.stdout.strip().splitlines()
        first = re.sub(r"^v\.s:\d+: ", "", msg[0]) if msg else ""
        return (not msg), first


def load_image(elf):
    """Address -> bytes, out of the ELF's PT_LOAD headers."""
    out = run(["llvm-readelf", "-l", elf]).stdout
    segs = []
    for line in out.splitlines():
        m = re.match(r"\s*LOAD\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)"
                     r"\s+0x([0-9a-f]+)", line)
        if m:
            off, va, _pa, fsz = (int(m.group(i), 16) for i in range(1, 5))
            segs.append((va, off, fsz))
    with open(elf, "rb") as f:
        data = f.read()

    def at(va, n):
        for base, off, fsz in segs:
            if base <= va < base + fsz:
                return data[off + (va - base): off + (va - base) + n]
        raise KeyError(f"${va:04X} is in no PT_LOAD")
    return at


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--calypsi",
                    default=os.path.expanduser("~/dev/toolchains/calypsi-6502"))
    ap.add_argument("--calypsi816",
                    default=os.path.expanduser("~/dev/toolchains/calypsi-65816"))
    a = ap.parse_args(argv)
    asm = os.path.join(a.calypsi, "bin", "as6502")
    ld = os.path.join(a.calypsi, "bin", "ln6502")
    asm816 = os.path.join(a.calypsi816, "bin", "as65816")
    if not os.path.exists(asm):
        print("Calypsi 6502 not installed")
        return 77

    print("\n-- the toolchain the numbers came from -------------------------")
    # TWO toolchains are involved and they are NOT at the same version:
    # the scatter work is 6502, and the closing "not on the 65816" claim
    # is 65816.  A report that names one version and makes claims from
    # both invites the obvious and fair reply, "try the current one".
    va = run([asm, "--version"]).stdout.strip()
    vl = run([ld, "--version"]).stdout.strip()
    claim("as6502 and ln6502 agree on a version",
          va.split()[-1] == vl.split()[-1], f"{va}\n{vl}")
    v6502 = va.split()[-1]
    # 5.18 is the newest 6502 RELEASE (checked against the upstream
    # release list on 2026-09-19; every public release through 5.18
    # carries all four architectures, and there is no 5.18.1 or 5.18.2
    # release at all).  The 5.18.1/5.18.2 packages on this machine are
    # 65816 only.  This file can only check the first half offline.
    claim("the 6502 tools are 5.18", v6502 == "5.18", f"6502 = {v6502}")
    if os.path.exists(asm816):
        v816 = run([asm816, "--version"]).stdout.strip()
        claim("the 65816 assembler, used only for the last section, is 5.18.2",
              v816.split()[-1] == "5.18.2", v816)

    work = tempfile.mkdtemp(prefix="scatter-")
    try:
        for f in ("atari.scm", "table.s", "bank_a.s", "bank_b.s", "bank_c.s"):
            shutil.copy(os.path.join(HERE, f), work)

        print("\n-- the map is the machine, not a convenience -------------------")
        scm = open(os.path.join(work, "atari.scm")).read()
        claim("the slot is the Atari's one window, $4000-$7fff",
              "(address (#x4000 . #x7fff))" in scm)
        claim("it scatters, and may generate instances",
              "(scatter-to RAM-banks)" in scm and ":generate-instances" in scm)
        claim(f"the flat store starts at ${BANK_BASE:X}",
              f"(address (#x{BANK_BASE:x} . #x1fffff))" in scm)

        print("\n-- assemble and link -------------------------------------------")
        objs = []
        for n in ("bank_a", "bank_b", "bank_c", "table"):
            o = os.path.join(work, n + ".o")
            r = run([asm, "-o", o, os.path.join(work, n + ".s")])
            if r.stdout.strip():
                claim(f"{n}.s assembles", False, r.stdout.strip())
                return sum(1 for _, ok, _ in results if not ok)
            objs.append(o)
        elf = os.path.join(work, "scat.elf")
        mapf = os.path.join(work, "scat.map")
        r = run([ld, os.path.join(work, "atari.scm")] + objs +
                ["-o", elf, "--list-file", mapf])
        claim("the link succeeds", os.path.exists(elf), r.stdout.strip()[:200])
        listing = open(mapf, errors="ignore").read()

        print("\n-- what the linker did -----------------------------------------")
        scat = sorted(set(int(x, 16) for x in
                          re.findall(r"\(scatter to ([0-9a-f]+) in bankedRAM\)",
                                     listing)))
        claim("three instances were generated", len(scat) == 3,
              " ".join(f"${v:06X}" for v in scat))
        claim("and they are one bank apart",
              scat == [BANK_BASE, BANK_BASE + BANK_SIZE, BANK_BASE + 2 * BANK_SIZE],
              " ".join(f"${v:06X}" for v in scat))
        sizes = set(re.findall(r"placed at address 4000-([0-9a-f]+) of size "
                               r"([0-9a-f]+) \(scatter to", listing))
        claim("each instance holds ONE routine, too big to share",
              all(int(s, 16) > BANK_SIZE // 2 for _, s in sizes),
              "; ".join(f"size ${s.upper()} ({int(s, 16)} bytes)" for _, s in sizes))

        print("\n-- the values, read out of the LINKED IMAGE --------------------")
        syms = dict((m.group(2), int(m.group(1), 16)) for m in
                    re.finditer(r"(\w+) = (runtime_addr|storage_addr)\b", listing))
        syms = {}
        for m in re.finditer(r"(runtime_addr|storage_addr) = ([0-9a-f]+)", listing):
            syms[m.group(1)] = int(m.group(2), 16)
        claim("the resident table is in the map",
              "runtime_addr" in syms and "storage_addr" in syms,
              " ".join(f"{k}=${v:04X}" for k, v in sorted(syms.items())))
        at = load_image(elf)
        rt = at(syms["runtime_addr"], 6)
        st = at(syms["storage_addr"], 12)
        runtime = [int.from_bytes(rt[i:i + 2], "little") for i in (0, 2, 4)]
        storage = [int.from_bytes(st[i:i + 4], "little") for i in (0, 4, 8)]
        names = ("far_a", "far_b", "far_c")
        claim("every routine RUNS at the window base",
              all(v == WINDOW for v in runtime),
              " ".join(f"{n}=${v:04X}" for n, v in zip(names, runtime)))
        claim("the map agrees that they all run there",
              all(re.search(rf"{n} = {WINDOW:04x}\b", listing) for n in names))
        claim(".scatterTo28 gives a DIFFERENT storage address for each",
              len(set(storage)) == 3,
              " ".join(f"{n}=${v:06X}" for n, v in zip(names, storage)))
        claim("each storage address is one of the instances",
              all(v in scat for v in storage))
        banks = [(v - BANK_BASE) // BANK_SIZE for v in storage]
        claim("so (storage - base) / 16K is a bank index, and they are distinct",
              sorted(banks) == [0, 1, 2],
              " ".join(f"{n}->bank {b}" for n, b in zip(names, banks)))
        claim("the storage address is NOT the runtime address",
              all(s != r for s, r in zip(storage, runtime)),
              "which is the whole point of the operator")

        print("\n-- is it deterministic? ----------------------------------------")
        elf2 = os.path.join(work, "scat2.elf")
        run([ld, os.path.join(work, "atari.scm")] + objs + ["-o", elf2])
        at2 = load_image(elf2)
        claim("a second link assigns the same banks",
              bytes(at2(syms["storage_addr"], 12)) == bytes(st),
              "(so the table above is not one lucky ordering)")

        print("\n-- the syntax, which is the half that does NOT work ------------")
        good = [".byte .byte0 far_a", ".byte .byte1 far_a", ".byte .byte2 far_a",
                ".byte .byte3 far_a", ".word .word0 far_a", ".word .word2 far_a",
                "lda #.byte2 far_a", "lda #.byte0 far_a"]
        for line in good:
            ok, msg = assemble_ok(asm, line)
            claim(f"accepted on an ordinary symbol:  {line}", ok, msg)
        ok, msg = assemble_ok(asm, ".long .scatterTo28 far_a")
        claim("accepted:  .long .scatterTo28 far_a", ok, msg)

        bad = [".byte .scatterTo28 far_a",
               ".word .scatterTo28 far_a",
               ".byte .byte0 .scatterTo28 far_a",
               ".byte .byte2 .scatterTo28 far_a",
               ".byte .byte3 .scatterTo28 far_a",
               ".byte .byte2 (.scatterTo28 far_a)",
               ".byte (.byte2 .scatterTo28 far_a)",
               ".word .word0 .scatterTo28 far_a",
               ".word .word2 .scatterTo28 far_a",
               ".long .word0 .scatterTo28 far_a",
               ".long .byte2 .scatterTo28 far_a",
               "lda #.byte2 .scatterTo28 far_a"]
        for line in bad:
            ok, msg = assemble_ok(asm, line)
            claim(f"REFUSED:  {line}", not ok, msg)

        print("\n-- in an INSTRUCTION OPERAND it assembles, and then ------------")
        print("   the linker fails.  This is the half the first draft of the")
        print("   report got wrong: it quoted a harness that had lost its")
        print("   indentation, so every form read as a parse error.")
        operand = ["lda #.byte0 (.scatterTo28 far_a)",
                   "lda #.byte1 (.scatterTo28 far_a)",
                   "lda #.byte2 (.scatterTo28 far_a)",
                   "lda #.byte3 (.scatterTo28 far_a)",
                   "lda #.scatterTo28 far_a"]
        for line in operand:
            ok, msg = assemble_ok(asm, line)
            claim(f"ASSEMBLES:  {line}", ok, msg)
            with tempfile.TemporaryDirectory() as d:
                ps = os.path.join(d, "p.s")
                with open(ps, "w") as f:
                    f.write('              .rtmodel version, "1"\n'
                            '              .rtmodel core, "*"\n'
                            '              .extern far_a\n'
                            '              .section code, root\n'
                            f'              {line}\n')
                po = os.path.join(d, "p.o")
                run([asm, "-o", po, ps])
                lr = run([ld, os.path.join(work, "atari.scm")] + objs[:3] +
                         [po, "-o", os.path.join(d, "p.elf")])
                out = lr.stdout.strip().splitlines()
                claim(f"  ...and the LINKER then fails:  {line}",
                      any("internal error" in l for l in out),
                      out[0] if out else "(it linked -- the bug is gone)")
        # the control: the same shape on an ordinary symbol must link
        with tempfile.TemporaryDirectory() as d:
            ps = os.path.join(d, "p.s")
            with open(ps, "w") as f:
                f.write('              .rtmodel version, "1"\n'
                        '              .rtmodel core, "*"\n'
                        '              .extern far_a\n'
                        '              .section code, root\n'
                        '              lda #.byte2 far_a\n')
            po = os.path.join(d, "p.o")
            run([asm, "-o", po, ps])
            lr = run([ld, os.path.join(work, "atari.scm")] + objs[:3] +
                     [po, "-o", os.path.join(d, "p.elf")])
            claim("CONTROL: lda #.byte2 far_a (no scatterTo28) links cleanly",
                  not lr.stdout.strip(), lr.stdout.strip()[:120] or "(links)")

        print("\n-- the byte operators mean what the report says they mean ------")
        # Load-bearing: the report argues .byte2 is the wrong granularity
        # for a 16 KB bank because it is bits 16-23.  Check, do not assume.
        with tempfile.TemporaryDirectory() as d:
            bs = os.path.join(d, "b.s")
            with open(bs, "w") as f:
                f.write('              .rtmodel version, "1"\n'
                        '              .rtmodel core, "*"\n'
                        '              .public probe\n'
                        '              .section code, root\n'
                        'probe:        .byte .byte0 0x123456, .byte1 0x123456,'
                        ' .byte2 0x123456, .byte3 0x123456\n')
            bo, be, bm = (os.path.join(d, x) for x in ("b.o", "b.elf", "b.map"))
            run([asm, "-o", bo, bs])
            run([ld, os.path.join(work, "atari.scm"), bo, "-o", be,
                 "--list-file", bm])
            pm = re.search(r"probe = ([0-9a-f]+)",
                           open(bm, errors="ignore").read())
            got = bytes(load_image(be)(int(pm.group(1), 16), 4))
            claim(".byte0/1/2/3 of $123456 are 56 34 12 00 (so .byte2 is bits 16-23)",
                  got == bytes((0x56, 0x34, 0x12, 0x00)), got.hex(" "))

        print("\n-- can the value be adjusted at all? ---------------------------")
        for line, why in ((".long (.scatterTo28 far_a)", "parenthesised"),
                          (".long .scatterTo28 (far_a)", "operand in parens"),
                          (".long .scatterTo28 far_a + 1", "plus a constant"),
                          (".long (.scatterTo28 far_a) - 0x10000", "minus the base"),
                          (".long (.scatterTo28 far_a) >> 14", "shifted to a bank")):
            ok, msg = assemble_ok(asm, line)
            claim(f"{'accepted' if ok else 'REFUSED '}:  {line}  ({why})",
                  True, msg or "(assembles)")

        print("\n-- and the 65816, which gem4xe actually uses -------------------")
        if os.path.exists(asm816):
            # The control has to be a form as65816 really takes, or a
            # rejection below proves nothing.  `.long .word0 far_a` is NOT
            # it -- that is refused there on its own account -- so use a
            # plain .long and an ordinary byte operator.
            ok16a, _ = assemble_ok(asm816, ".long far_a")
            ok16b, _ = assemble_ok(asm816, ".byte .byte2 far_a")
            claim("as65816 takes .long, and .byte2 on an ordinary symbol",
                  ok16a and ok16b,
                  "so a rejection below is about the operator, not the syntax")
            ok16s, msg16s = assemble_ok(asm816, ".long .scatterTo28 far_a")
            claim("as65816 REFUSES .scatterTo28", not ok16s, msg16s)
            guide = os.path.join(a.calypsi816, "doc", "pdf",
                                 "Calypsi65816Guide.pdf")
            if os.path.exists(guide):
                txt = run(["pdftotext", guide, "-"]).stdout
                claim("the 65816 guide never mentions it",
                      "scatterTo28" not in txt,
                      f"{txt.lower().count('scatterto28')} mentions")
        else:
            claim("as65816 present", False, "not installed; skipped")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    bad_n = sum(1 for _, ok, _ in results if not ok)
    print(f"\nscatter-validate: {len(results) - bad_n}/{len(results)} claims hold")
    return bad_n


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
