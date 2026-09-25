#!/usr/bin/env python3
"""ELF -> Atari executable (.xex) packer for Calypsi output.

Calypsi's linker always emits ELF+DWARF and has no .xex output format, so this
walks the ELF program headers and writes the Atari segmented binary format:

    $FFFF                       file magic (once, at the start)
    <start> <end> <data...>     one per loadable segment, little-endian, end
                                is INCLUSIVE
    $02E2 $02E3 <addr>          INITAD -- DOS calls here after loading a segment
    $02E0 $02E1 <addr>          RUNAD  -- DOS jumps here when the load completes

Only PT_LOAD segments with a non-zero file size are emitted: a segment with
p_filesz == 0 and p_memsz > 0 is .bss, which occupies RAM but carries no bytes.
Calypsi's cstartup zeroes what needs zeroing through its data_init_table.

FAR SEGMENTS

A .xex segment header is two 16-bit addresses, so an Atari DOS loader cannot
place anything above $FFFF -- but gem4xe links its code into the banks above
it, one linker memory per bank from $01 up (src/gem4xe.scm), so a far
segment per bank the image reached.  Those segments therefore travel as
CHUNKS: each is aimed at the staging buffer that src/farload.s reserves in
bank $00, followed by a two-byte segment that writes INITAD, which makes DOS
call the loader.  The loader unpacks the chunk to its real home and returns,
and by the time DOS reaches the run vector the far image is assembled.

Writing INITAD after every chunk rather than once at the start is REQUIRED,
and the reason was measured rather than assumed (2026-09-18, after a reader on
AtariAge corrected an earlier account of it here).  The DOS calls INITAD after
every segment -- AND POINTS IT AT AN RTS ONCE IT HAS.  So it fires only for the
segment that just set it, and a loader that wrote INITAD once would unpack its
first chunk and silently skip every chunk after it.

Measured on DOS II+/D 6.4 with a seven-segment probe: INITAD set once, two
plain segments after it, the vector's routine counting its own calls.  It ran
ONCE, and afterwards $02E2 read $1507, where the byte is $60.  This file used
to say "DOSes disagree about whether INITAD fires after every segment or only
after one that writes to it" -- they do not disagree; one mechanism looks like
both.  The loader still zeroes its own count field, which is now belt and
braces rather than the reason.

THE CHUNKS ARE PACKED.  The far image is two thirds of a double-density
floppy and most of a minute of a 1050's reading, and it is code and tables,
which an LZ77 makes a third smaller.  Each far segment is packed on its own
as one stream of TOKENS, and the stream is cut into chunks at token
boundaries, so a chunk unpacks on its own given only where it goes -- what
a match reaches back into is output the loader already wrote, in the banks
above, and the segment before this one is never referenced.  A token is:

    byte       LLLL MMMM   L literal bytes follow; a match of M+4 bytes after
    bytes      if L == 15: added to L, one after another, until one is not 255
    L bytes    the literals
    word       the match's offset, little-endian, 1..65535: it copies from
               (the output so far) minus this, which may overlap what it
               writes -- that is how a run is encoded.  Or 0: NO match, the
               token was only its literals (M is 0 and nothing follows) --
               how a long stretch of incompressible bytes is carried, a
               thousand literals at a time, so that no token outgrows the
               staging buffer
    bytes      if M == 15: added to M as above

The last token of a chunk may stop after its literals, without even the
offset word.  Nothing marks that: the chunk's header carries how many bytes
come OUT of it, the loader stops when it has written that many, and the
packer cuts only at token boundaries, so the count runs out exactly where a
token ends.  The header is five bytes, a 24-bit destination and that 16-bit
count, and it sits immediately before the payload so that a chunk is ONE
.xex segment.

unpack() below is the loader written in Python, and the packer checks its
own output through it before writing a byte of the .xex: a format mistake
fails the build here, not a boot there.  tests/host/test_mkxex.py loads the
.xex the way a DOS does and requires the image back byte for byte.

The staging layout is not repeated here: _fl_hdr, _fl_buf and _fl_end come out
of the ELF symbol table, so src/farload.s and src/gem4xe.scm remain the only
places that decide where the buffer is and how big it is.

Usage: mkxex.py in.elf out.xex [--entry SYMBOL] [--syms out.sym]

--syms writes "NAME ADDR" lines for every symbol, so a test harness can find
buffers by name instead of hard-coding addresses that drift on every rebuild.
"""
import functools
import struct
import sys

PT_LOAD = 1


def read_elf(path):
    """Return (list of (vaddr, bytes), {symbol: value}) from a 32-bit LE ELF."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"\x7fELF":
        raise SystemExit(f"{path}: not an ELF file")
    if d[4] != 1 or d[5] != 1:
        raise SystemExit(f"{path}: expected a 32-bit little-endian ELF")

    e_shoff, = struct.unpack_from("<I", d, 0x20)
    e_phoff, = struct.unpack_from("<I", d, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x2A)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", d, 0x2E)

    segs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_offset, p_vaddr, _pa, p_filesz, p_memsz = struct.unpack_from("<6I", d, o)
        if p_type == PT_LOAD and p_filesz > 0:
            segs.append((p_vaddr, d[p_offset:p_offset + p_filesz]))

    syms = {}
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        sh_type, = struct.unpack_from("<I", d, o + 4)
        if sh_type != 2:                                  # SHT_SYMTAB
            continue
        sh_offset, sh_size, sh_link, _info, _align, sh_entsize = struct.unpack_from(
            "<6I", d, o + 16)
        stro = e_shoff + sh_link * e_shentsize
        str_off, str_size = struct.unpack_from("<II", d, stro + 16)
        strtab = d[str_off:str_off + str_size]
        for j in range(sh_size // sh_entsize):
            so = sh_offset + j * sh_entsize
            st_name, st_value = struct.unpack_from("<II", d, so)
            end = strtab.find(b"\0", st_name)
            name = strtab[st_name:end].decode("ascii", "replace")
            if name:
                syms.setdefault(name, st_value)
    return segs, syms


RUNAD, INITAD = 0x02E0, 0x02E2


def seg(addr, data):
    """One .xex segment: start, INCLUSIVE end, bytes."""
    return struct.pack("<HH", addr, addr + len(data) - 1) + data


MIN_MATCH = 4          # a match shorter than this costs more than its literals
MAX_OFFSET = 0xFFFF    # the offset is a word
MAX_LITERALS = 1024    # per token, so that no token outgrows a chunk
MAX_MATCH = 1024       # ...and no chunk's output outgrows its 16-bit count
HASH = 4               # bytes a candidate match is found by
CHAIN = 64             # earlier places of those bytes tried, most recent first


def _ext(n):
    """Bytes a nibble-coded count of n (after its bias) takes past the nibble."""
    return 0 if n < 15 else 1 + (n - 15) // 255


@functools.lru_cache(maxsize=16)
def pack(data):
    """LZ77 the bytes into a list of tokens, each the bytes of one token.

    AN OPTIMAL PARSE, not a greedy one.  The longest earlier match at every
    position is found first (a hash of the next four bytes, the most recent
    CHAIN places it occurred); then, working back from the end, each
    position's cheapest way on is chosen -- a literal, or a match of any
    length it could take -- by what it costs in the file.  A greedy parse
    with one byte of lookahead took the longest match wherever it stood,
    and that is not the same thing: 0.9 KB of the far image, and on the
    DOS 2 floppy that was the difference between fitting and not
    (docs/phase56.md).  Deterministic, which matters: the gates recompute
    the chunking from the ELF and expect the same seams.

    Costs are counted a literal at a byte, and a match at a token byte, an
    offset word and its length's extension bytes -- the literal run's own
    extension bytes, one per 255, are left out of the choice.
    """
    n = len(data)
    heads = {}
    blen = [0] * n
    boff = [0] * n
    for i in range(n):
        if i + HASH > n:
            continue
        key = data[i:i + HASH]
        chain = heads.get(key)
        if chain is None:
            heads[key] = [i]
            continue
        lim = min(n - i, MAX_MATCH)
        best, off = 0, 0
        for p in reversed(chain[-CHAIN:]):
            if i - p > MAX_OFFSET:
                break
            k = HASH
            while k < lim and data[p + k] == data[i + k]:
                k += 1
            if k > best:
                best, off = k, i - p
                if k >= lim:
                    break
        blen[i], boff[i] = best, off
        chain.append(i)

    cost = [0] * (n + 1)
    take = [0] * (n + 1)                       # 0: a literal; else a match length
    for i in range(n - 1, -1, -1):
        c, t = cost[i + 1] + 1, 0
        m_max = blen[i]
        if m_max >= MIN_MATCH:
            # every length up to 40, and the longest: the extension bytes
            # make nothing between worth more than one of those
            lens = range(MIN_MATCH, m_max + 1) if m_max <= 40 else \
                list(range(MIN_MATCH, 40)) + [m_max]
            for m in lens:
                cm = cost[i + m] + 3 + _ext(m - MIN_MATCH)
                if cm < c:
                    c, t = cm, m
        cost[i], take[i] = c, t

    tokens = []

    def token(lits, mlen, off):
        L, M = len(lits), mlen - MIN_MATCH if mlen else 0
        out = bytearray([(min(L, 15) << 4) | min(M, 15)])
        if L >= 15:
            r = L - 15
            while r >= 255:
                out.append(255)
                r -= 255
            out.append(r)
        out += lits
        out += struct.pack("<H", off)          # 0: no match follows
        if mlen:
            if M >= 15:
                r = M - 15
                while r >= 255:
                    out.append(255)
                    r -= 255
                out.append(r)
        tokens.append(bytes(out))

    i = 0
    lits = bytearray()
    while i < n:
        if len(lits) >= MAX_LITERALS:
            token(lits, 0, 0)
            lits = bytearray()
        m = take[i]
        if m:
            token(lits, m, boff[i])
            lits = bytearray()
            i += m
        else:
            lits.append(data[i])
            i += 1
    if lits:
        token(lits, 0, 0)
    return tokens


def literals(tok):
    """A token's literal count, and where in it the offset word starts."""
    i = 1
    L = tok[0] >> 4
    if L == 15:
        while True:
            L += tok[i]
            i += 1
            if tok[i - 1] != 255:
                break
    return L, i + L


def literal_only(tok):
    """True if the token carries no match: it ends in the no-match word."""
    L, i = literals(tok)
    return i + 2 == len(tok) and tok[i] | tok[i + 1] == 0


def join(tokens):
    """The tokens as one chunk's payload.

    A chunk's last token stops after its literals if it has no match, so the
    no-match word that marks that mid-chunk is left off the end.
    """
    if tokens and literal_only(tokens[-1]):
        tokens = tokens[:-1] + [tokens[-1][:-2]]
    return b"".join(tokens)


def token_out(tok):
    """How many bytes a token writes: its literals plus its match."""
    L, i = literals(tok)
    if i >= len(tok) or tok[i] | tok[i + 1] == 0:
        return L
    i += 2
    M = (tok[0] & 15) + MIN_MATCH
    if (tok[0] & 15) == 15:
        while True:
            M += tok[i]
            i += 1
            if tok[i - 1] != 255:
                break
    return L + M


def unpack(packed, count, before=b""):
    """src/farload.s in Python: `count` bytes out of `packed`.

    `before` is the output the loader has already written ahead of this
    chunk's destination, which is what a match may reach back into.
    """
    out = bytearray(before)
    end = len(out) + count
    i = 0
    while len(out) < end:
        tok = packed[i]
        i += 1
        L = tok >> 4
        if L == 15:
            while True:
                L += packed[i]
                i += 1
                if packed[i - 1] != 255:
                    break
        out += packed[i:i + L]
        i += L
        if len(out) >= end:
            break
        off = packed[i] | (packed[i + 1] << 8)
        i += 2
        if off == 0:
            if tok & 15:
                raise ValueError(f"no-match token with a match length at {i - 2}")
            continue
        M = (tok & 15) + MIN_MATCH
        if (tok & 15) == 15:
            while True:
                M += packed[i]
                i += 1
                if packed[i - 1] != 255:
                    break
        if not 1 <= off <= len(out):
            raise ValueError(f"match reaches {off} bytes back at output {len(out)}")
        for _ in range(M):
            out.append(out[-off])
    if len(out) != end or i != len(packed):
        raise ValueError(f"chunk unpacked to {len(out) - len(before)} bytes of "
                         f"{count}, using {i} of {len(packed)}")
    return bytes(out[len(before):])


def far_chunks(vaddr, data, chunk):
    """Pack a far segment and cut it into chunks that fit the staging buffer.

    Yields (destination, the bytes the chunk unpacks to, the packed bytes).
    Cuts are at token boundaries only, and a chunk's output is kept under
    what its 16-bit count can say.  Every chunk is unpacked again here, on
    top of what came before it, and must give back the segment's own bytes.
    """
    tokens = pack(data)
    done = 0
    piece, out = [], 0

    def cut():
        packed = join(piece)
        got = unpack(packed, out, data[:done])
        if got != data[done:done + out]:
            raise SystemExit(f"packer bug: chunk at ${vaddr + done:06X} "
                             f"does not unpack to what went in")
        return vaddr + done, got, packed

    for tok in tokens:
        t_out = token_out(tok)
        if piece and (sum(map(len, piece)) + len(tok) > chunk
                      or out + t_out > 0xFFFF):
            yield cut()
            done += out
            piece, out = [], 0
        if len(tok) > chunk:
            raise SystemExit(f"a {len(tok)}-byte token cannot fit a "
                             f"{chunk}-byte staging buffer")
        piece.append(tok)
        out += t_out
    if piece:
        yield cut()
        done += out
    if done != len(data):
        raise SystemExit(f"packer bug: {done} of {len(data)} bytes chunked")


def build_xex(segs, entry, syms):
    near, far = [], []
    for vaddr, data in sorted(segs):
        end = vaddr + len(data) - 1
        if end <= 0xFFFF:
            near.append((vaddr, data))
        elif vaddr > 0xFFFF:
            far.append((vaddr, data))
        else:
            raise SystemExit(
                f"segment ${vaddr:06X}-${end:06X} straddles the bank $00 boundary")

    out = bytearray(b"\xff\xff")
    for vaddr, data in near:
        out += seg(vaddr, data)
    if far:
        staged, _ = stage_far(far, syms)
        out += staged
    out += seg(RUNAD, struct.pack("<H", entry))
    return bytes(out), near, far


def stage_far(far, syms):
    """Chunk the far image into staging-buffer segments plus INITAD triggers."""
    need = ("_fl_hdr", "_fl_buf", "_fl_end", "_fl_copy")
    missing = [n for n in need if n not in syms]
    if missing:
        raise SystemExit(
            f"far segments need src/farload.s linked in; missing {', '.join(missing)}")
    hdr, buf, scr, loader = (syms[n] for n in need)
    chunk = scr - buf
    if chunk <= 0:
        raise SystemExit(f"staging buffer is {chunk} bytes")
    if buf != hdr + HDR:
        raise SystemExit(
            f"_fl_buf (${buf:04X}) must follow the {HDR}-byte header at _fl_hdr "
            f"(${hdr:04X}) immediately, so that a chunk is one .xex segment")

    out = bytearray()
    # Zero the count while INITAD is still unset, so that the first trigger
    # cannot act on whatever the staging buffer happened to contain.
    out += seg(hdr, b"\x00" * HDR)
    # Where the loader runs its unpacker: the bank above the far image, in
    # the accelerator's fast RAM, because bank $00 is all on the slow bus
    # until the program switches it (src/farload.s, fl_fastbank).
    if "fl_fastbank" not in syms:
        raise SystemExit("far segments need src/farload.s's fl_fastbank")
    top = max(vaddr + len(data) - 1 for vaddr, data in far) >> 16
    out += seg(syms["fl_fastbank"], bytes([top + 1]))
    stats = []
    last = 0
    for vaddr, data in far:
        # IN ADDRESS ORDER: the loader takes the end of the last chunk as
        # the top of the image (src/farload.s, ff_done), not a maximum.
        if vaddr < last:
            raise SystemExit(f"far segment ${vaddr:06X} is below one already "
                             f"staged; the loader needs them in address order")
        last = vaddr + len(data)
        n = 0
        for dst, plain, packed in far_chunks(vaddr, data, chunk):
            out += seg(hdr, struct.pack("<HBH", dst & 0xFFFF, dst >> 16, len(plain))
                       + packed)
            out += seg(INITAD, struct.pack("<H", loader))
            n += 1
        stats.append(n)
    return bytes(out), stats


HDR = 5    # the chunk header: a 24-bit destination and a 16-bit output count


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__.strip().splitlines()[-1])
    src, dst = argv[0], argv[1]
    want = "__program_start"
    if "--entry" in argv:
        want = argv[argv.index("--entry") + 1]

    segs, syms = read_elf(src)
    if want not in syms:
        raise SystemExit(f"{src}: entry symbol {want!r} not found")
    if syms[want] > 0xFFFF:
        raise SystemExit(
            f"{src}: entry symbol {want!r} is at ${syms[want]:06X}; DOS's run "
            f"vector is 16-bit, so the entry point has to be in bank $00")
    entry = syms[want]

    xex, near, far = build_xex(segs, entry, syms)
    open(dst, "wb").write(xex)

    if "--syms" in argv:
        path = argv[argv.index("--syms") + 1]
        with open(path, "w") as f:
            for name in sorted(syms):
                f.write(f"{name} {syms[name]:06X}\n")
        print(f"    {path}: {len(syms)} symbols")

    nearb = sum(len(d) for _, d in near)
    farb = sum(len(d) for _, d in far)
    print(f"{dst}: {len(xex)} bytes, run ${entry:04X} ({want})")
    for vaddr, data in near:
        print(f"    ${vaddr:04X}-${vaddr + len(data) - 1:04X}  {len(data):5d} bytes  bank $00")
    for vaddr, data in far:
        print(f"  ${vaddr:06X}-${vaddr + len(data) - 1:06X}  {len(data):5d} bytes  "
              f"staged through ${syms['_fl_buf']:04X}")
    if far:
        chunk = syms["_fl_end"] - syms["_fl_buf"]
        staged, chunks = stage_far(far, syms)
        packed = len(staged) - sum(chunks) * (4 + HDR + 6) - (4 + HDR) - 5
        print(f"    {nearb} bytes in bank $00, {farb} far packed to {packed} "
              f"({100 * packed // farb}%) in {sum(chunks)} chunk(s) of up to {chunk}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
