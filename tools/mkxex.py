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
floppy and most of a minute of a 1050's reading, and it is code and tables.
Each far segment is packed on its own, and the packed stream is cut into
chunks, so a chunk unpacks on its own given only where it goes -- what a
match reaches back into is output the loader already wrote, in the banks
above -- and what the decoder carries from one chunk to the next is one
number, the last offset.

THE FORMAT (G4Z, phase 57): a stream of BITS interleaved with raw BYTES.
Bits are read from the top of a bit byte, and a new bit byte is taken
from the stream at the moment a bit is wanted and none is left, so the
packer writes each one where the reader will look for it.  A NUMBER n >= 1
is interlaced Elias gamma: for each bit of n below its top one, a 0 and
then that bit, and then a 1.  The elements:

    literals        gamma(n), then n raw bytes
    new-offset      gamma(hi), a raw byte lo, gamma(len - 1):
      match         offset = ((hi - 1) << 8 | lo) + 1, 1..65535, and len
                    bytes copied from (the output so far) minus it -- which
                    may overlap what it writes: that is how a run is said
    repeat match    gamma(len): len bytes at the LAST offset used

and which one comes next is a bit, by what came before:

    after a match, or at a chunk's start:   0 literals,  1 new offset
    after literals:                         0 repeat,    1 new offset

So literals never follow literals, and a repeat only follows literals --
the shape that pays, a match, a changed byte or two, the match again.
Every chunk begins with an empty bit byte and in the after-a-match state,
so the packer ends a chunk at an element and never inside one (a run of
literals too long for what is left of a chunk is split, and the rest opens
the next).  The last offset is NOT reset between chunks, or between
segments: the packer never repeats an offset a segment has not set.

Nothing marks a chunk's end: its header carries how many bytes come OUT
of it, and the loader stops when it has written that many.  The header is
five bytes, a 24-bit destination and that 16-bit count, and it sits
immediately before the payload so that a chunk is ONE .xex segment.

Compared with the byte-token format before it (a nibble pair, literals, a
two-byte offset a match), it packs gem.elf's far image to 56% where that
did 67%: 18 KB off a floppy, where the disk is most of a load.

decode() below is the loader written in Python, and the packer checks its
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


MIN_NEW = 2            # a new-offset match is two bytes at least
MAX_LEN = 4096         # a match's length, so a chunk's count stays a word
MAX_OFFSET = 0xFFFF
CHAIN = 128            # earlier places a pair of bytes occurred, tried
                       # most recent first: 32 is 0.6% bigger, 512 0.1% smaller
LONG = 48              # lengths above this are tried only at their longest


SKIP = 256             # a match this long: the positions inside it are
                       # not searched again (a run of zeros was quadratic)


def _same(data, a, b, lim):
    """How many bytes from a and from b are the same, up to lim: 32 at a
    time by slices first, which is what makes a long run cheap."""
    k = 0
    while k + 32 <= lim and data[a + k:a + k + 32] == data[b + k:b + k + 32]:
        k += 32
    while k < lim and data[a + k] == data[b + k]:
        k += 1
    return k


def _gbits(v):
    """Bits in the interlaced Elias gamma of v >= 1."""
    return 2 * v.bit_length() - 1


@functools.lru_cache(maxsize=16)
def parse(data):
    """The elements for data: ('L', n) literals or ('M', offset, length).

    AN OPTIMAL PARSE, forward, with one arrival a position: the cheapest
    way found to have written data[:i], what the last offset was on that
    way, and whether it ended in literals -- which is what says whether a
    repeat can come next.  From each position: one more literal; a repeat
    of the last offset, if literals came last; and new offsets, the most
    recent place first, each for the lengths no nearer one reached.
    Costs are the format's own, in bits, a run of literals counted as two
    bits to begin and eight a byte.  Deterministic, which matters: the
    gates recompute the chunking from the ELF and expect the same seams.
    """
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    last = [0] * (n + 1)           # 0: none yet -- never repeated
    lits = [0] * (n + 1)           # 1: literals came last
    back = [None] * (n + 1)
    cost[0] = 0
    heads = {}
    quiet = 0                      # inside a long match: not searched
    for i in range(n):
        c = cost[i]
        cl = c + 8 + (0 if lits[i] else 2)
        if cl < cost[i + 1]:
            cost[i + 1], last[i + 1], lits[i + 1], back[i + 1] = cl, last[i], 1, (i, 0, 0)
        if i < quiet:
            if i + 2 <= n:
                heads.setdefault(data[i:i + 2], []).append(i)
            continue
        lim = min(n - i, MAX_LEN)
        o = last[i]
        if lits[i] and o and o <= i:
            k = _same(data, i, i - o, lim)
            if k >= SKIP:
                quiet = max(quiet, i + k)
            for m in (range(1, k + 1) if k <= LONG else list(range(1, LONG)) + [k]):
                cm = c + 1 + _gbits(m)
                if cm < cost[i + m]:
                    cost[i + m], last[i + m], lits[i + m], back[i + m] = cm, o, 0, (i, o, m)
        if i + 2 <= n:
            key = data[i:i + 2]
            best = 1
            for p in reversed(heads.get(key, ())[-CHAIN:]):
                o = i - p
                if o > MAX_OFFSET:
                    break
                k = _same(data, p, i, lim)
                if k <= best:
                    continue
                if k >= SKIP:
                    quiet = max(quiet, i + k)
                base = c + 1 + _gbits(((o - 1) >> 8) + 1) + 8
                lo = max(best + 1, MIN_NEW)
                ms = range(lo, k + 1) if k - lo <= LONG else \
                    list(range(lo, lo + LONG)) + [k]
                for m in ms:
                    cm = base + _gbits(m - 1)
                    if cm < cost[i + m]:
                        cost[i + m], last[i + m], lits[i + m], back[i + m] = cm, o, 0, (i, o, m)
                best = k
                if k >= lim:
                    break
            heads.setdefault(key, []).append(i)
    els = []
    j = n
    while j:
        i, o, m = back[j]
        if m:
            els.append(("M", o, m))
        elif els and els[-1][0] == "L":
            els[-1] = ("L", els[-1][1] + 1)
        else:
            els.append(("L", 1))
        j = i
    els.reverse()
    return tuple(els)


class _Bits:
    """A packed stream being written: bytes, with bit bytes placed where
    the reader will take them."""

    def __init__(self):
        self.out = bytearray()
        self.at = 0
        self.used = 8                  # bits used of the current bit byte

    def bit(self, b):
        if self.used == 8:
            self.at = len(self.out)
            self.out.append(0)
            self.used = 0
        if b:
            self.out[self.at] |= 0x80 >> self.used
        self.used += 1

    def gamma(self, v):
        for k in range(v.bit_length() - 2, -1, -1):
            self.bit(0)
            self.bit((v >> k) & 1)
        self.bit(1)


def _out(e):
    return e[1] if e[0] == "L" else e[2]


def chunks(data, chunk, max_out=0xFFFF):
    """The segment packed and cut: [(bytes out, packed bytes)], each packed
    part at most `chunk` bytes and each count at most max_out."""
    q = list(parse(data))
    res = []
    w, after, lastoff, out, pos = _Bits(), 1, 0, 0, 0

    def need(e):
        if e[0] == "L":
            b, r = 1 + _gbits(e[1]), e[1]
        elif not after and e[1] == lastoff:
            b, r = 1 + _gbits(e[2]), 0
        else:
            b, r = 1 + _gbits(((e[1] - 1) >> 8) + 1) + _gbits(e[2] - 1), 1
        free = 8 - w.used
        return r + max(0, (b - free + 7) // 8)

    k = 0
    while k < len(q):
        e = q[k]
        if after and e[0] == "M" and e[2] < MIN_NEW:
            # a one-byte repeat where a chunk has just begun, and a repeat
            # cannot be said: the byte as a literal, with any that follow
            if k + 1 < len(q) and q[k + 1][0] == "L":
                q[k:k + 2] = [("L", 1 + q[k + 1][1])]
            else:
                q[k] = ("L", 1)
            continue
        if len(w.out) + need(e) > chunk or out + _out(e) > max_out:
            if e[0] == "L" and e[1] > 1:
                # the literals that fit now; the rest open the next chunk,
                # which begins where literals may come
                take = min(e[1] - 1, max_out - out, chunk - len(w.out) - 6)
                if take >= 1:
                    q[k:k + 1] = [("L", take), ("L", e[1] - take)]
                    continue
            if not w.out:
                raise SystemExit(f"a {e} too big for a {chunk}-byte chunk")
            res.append((out, bytes(w.out)))
            w, after, out = _Bits(), 1, 0
            continue
        if e[0] == "L":
            if not after:
                raise SystemExit("packer bug: literals after literals")
            w.bit(0)
            w.gamma(e[1])
            w.out += data[pos:pos + e[1]]
            after = 0
        else:
            _, o, m = e
            if not after and o == lastoff:
                w.bit(0)
                w.gamma(m)
            else:
                w.bit(1)
                w.gamma(((o - 1) >> 8) + 1)
                w.out.append((o - 1) & 0xFF)
                w.gamma(m - 1)
            after, lastoff = 1, o
        out += _out(e)
        pos += _out(e)
        k += 1
    if w.out:
        res.append((out, bytes(w.out)))
    return res


def decode(packed, count, out, last):
    """src/farload.s in Python: one chunk, `count` bytes appended to `out`
    (the output so far, which matches reach back into).  `last` is the
    offset carried in from the chunk before; the one to carry on is
    returned."""
    end = len(out) + count
    i = 0
    bits = 0x80
    after = 1

    def bit():
        nonlocal i, bits
        v = bits << 1
        if not v & 0xFF:
            v = (packed[i] << 1) | 1
            i += 1
        bits = v & 0xFF
        return v >> 8

    def gamma():
        v = 1
        while not bit():
            v = v << 1 | bit()
        return v

    while len(out) < end:
        new = bit()
        if after and not new:
            n = gamma()
            out += packed[i:i + n]
            i += n
            after = 0
            continue
        if new:
            hi = gamma()
            last = ((hi - 1) << 8 | packed[i]) + 1
            i += 1
            m = gamma() + 1
        else:
            m = gamma()
        if not 1 <= last <= len(out):
            raise ValueError(f"a match reaches {last} back at output {len(out)}")
        for _ in range(m):
            out.append(out[-last])
        after = 1
    if len(out) != end or i != len(packed):
        raise ValueError(f"chunk decoded to {len(out) - end + count} of {count} "
                         f"bytes, using {i} of {len(packed)}")
    return last


def far_chunks(vaddr, data, chunk):
    """Pack a far segment and cut it into chunks that fit the staging buffer.

    Yields (destination, the bytes the chunk unpacks to, the packed bytes).
    Every chunk is decoded again here, on top of what came before it, and
    must give back the segment's own bytes.
    """
    done, got, last = 0, bytearray(), 0
    for count, packed in chunks(data, chunk):
        last = decode(packed, count, got, last)
        if got[done:] != data[done:done + count]:
            raise SystemExit(f"packer bug: chunk at ${vaddr + done:06X} "
                             f"does not unpack to what went in")
        yield vaddr + done, bytes(got[done:]), packed
        done += count
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
