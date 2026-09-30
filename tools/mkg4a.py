#!/usr/bin/env python3
"""ELF x3 -> gem4xe loadable application (.g4a).

A gem4xe application is linked at placeholder addresses (src/app/gemapp.scm)
and put wherever there is room at load time: its near region -- direct
page, stack, data -- somewhere page-aligned in gem4xe's bank-$00 pool, its
far region -- the code -- in some bank of the far heap.  Neither the
compiler nor the linker emits relocations for that, so this tool DERIVES
them: the same objects are linked three times, once at the placeholders,
once with the near region moved up a page and once with the far region
moved up a bank, and the bytes that changed are the fixups.

    near up a page:  every byte that changed is the HIGH byte of a near
                     address (a page moves it by exactly 1);
    far up a bank:   every byte that changed is the BANK byte of a far
                     address (a bank moves it by exactly 1).

Any byte that changed by other than +1, or changed under both shifts, is
address arithmetic the loader could not relocate -- a shifted or divided
address, a bank in a low byte -- and the tool refuses rather than emit a
program that would work at the placeholders and nowhere else.  Nothing
else about the layout is assumed: the shifts, the region bases and the
entry point are read from the ELFs.

    G4A file, little-endian:
      0  'G4A' v                    magic, format version (3 or 4)
      4  u16 near_base              where the near region was linked
      6  u16 near_size              its whole extent, a page multiple
      8  u16 far_off                the far region's offset in its bank
     10  u32 far_size
     14  u8  far_bank               the bank it was linked in
     15  u8  far_banks              banks the far region spans -- the image
                                    AND the far variables, which carry no
                                    bytes and so are nowhere in the file
     16  u16 entry_lo, u8 entry_bank, u8 0
     20  u16 x4: fixup counts -- near part: high-byte, bank; far part: high-byte, bank
     28  u32 0
     32  near bytes, far bytes, then the four fixup lists

    VERSION 3 and VERSION 4 differ in one thing: how wide a FAR fixup
    offset is.  v3 writes it as a u16, which caps the far image at 64 KB;
    v4 writes it as three bytes and has no such cap.  The near lists are
    u16 in both, and stay that way -- the near region is a page-aligned
    slice of gem4xe's bank-$00 pool and cannot be bigger than the bank.

    A file is written v3 whenever the far image fits in 64 KB, which is
    every program in this tree but one.  GACS's GEM shell is the exception
    and the reason the wide format exists: 102,862 bytes of farcode and
    another 11 KB of constants, which is not close to a bank and cannot be
    made to fit one.  The loader reads both (src/sys/app.c).

    Versions 1 and 2 were the same pair, with the same layout, for programs
    that called gem4xe through COP #$73, #$C8 and #$01.  Those signatures
    were given up -- $01 is Rapidus OS's own and $80-$FF are reserved by
    WDC (src/sys/abi.h) -- and the number moved with them, so that the
    loader refuses an old program by name (APP_E_OLDSDK) and an old loader
    refuses a new one, instead of either starting a program whose calls
    go nowhere.

    The far IMAGE may now span banks.  It used to be refused here, on the
    ground that the program counter wraps inside a bank so code may not
    cross one -- which is true, and is not this tool's business: no single
    FUNCTION crosses a bank because each is its own linker fragment placed
    inside one memory, and src/app/gemapp.scm gives every code bank a pair
    of memories either side of the $D5 page for exactly that reason.  The
    packer was enforcing an invariant it does not own, and the cost was
    that no application could be larger than a bank.

Usage: mkg4a.py base.elf near-shifted.elf far-shifted.elf out.g4a
                [--syms out.sym] [--c-array out.c NAME]
"""
import re
import struct
import sys

from mkxex import read_elf

MAGIC_V3 = b"G4A\x03"      # far fixups u16
MAGIC_V4 = b"G4A\x04"      # far fixups three bytes
MAGIC_V5 = b"G4A\x05"      # packed: code and far variables placed apart
HDR_V5 = 48
PACK_LIMIT = 0xD500         # a packed program's code stays under the $D5 page
# What formats 3 and 4 promise the loader: the call gates' COP signatures
# (src/sys/abi.h, src/app/gemabi.s).
GATES = {"vdi_call": 0x56, "aes_call": 0x41, "dos_call": 0x44}


def read_elf_all(path):
    """Every PT_LOAD, bytes or not: (vaddr, filebytes, memsz), plus symbols."""
    with open(path, "rb") as f:
        d = f.read()
    e_phoff, = struct.unpack_from("<I", d, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x2A)
    segs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_offset, p_vaddr, _pa, p_filesz, p_memsz = struct.unpack_from("<6I", d, o)
        if p_type == 1 and p_memsz > 0:
            segs.append((p_vaddr, d[p_offset:p_offset + p_filesz], p_memsz))
    _, syms = read_elf(path)
    return segs, syms


def extents(segs, syms):
    """(near_base, near_end, far_base, far_end) of a link: the near region
    starts at the direct page, which the linker script puts first, and runs
    to the end of its last memory -- a memory's whole size is what the ELF
    records, and the bss within it must be zeroed; the far region is code
    and ends with its last byte."""
    near = [s for s in segs if s[0] < 0x10000]
    # A far memory nothing was placed in still gets a PT_LOAD with no file
    # bytes (the second half of the bank, above the $D5 hole, in an
    # application smaller than the first); it carries nothing and must not
    # stretch the far region to it.
    far = [s for s in segs if s[0] >= 0x10000 and len(s[1])]
    if not near or not far:
        raise SystemExit("expected both a near and a far region")
    dp = syms["_DirectPageStart"]
    if dp & 0xFF:
        raise SystemExit(f"_DirectPageStart ${dp:04X} is not page aligned")
    near_end = max(a + m for a, _, m in near)
    far_base = min(a for a, _, _ in far)
    far_end = max(a + len(d) for a, d, _ in far)
    if min(a for a, _, _ in near) < dp:
        raise SystemExit("a near segment lies below the direct page")
    return dp, near_end, far_base, far_end


def far_span(mapfile, far_base):
    """How far the far region REACHES, from the linker's own list file.

    This is not the same as how far the IMAGE reaches, and the difference
    is a --data-model=large program's variables: `far` and `zfar`
    (src/app/gemapp.scm) carry no bytes, so they are nowhere in the image
    -- but the loader allocates whole banks from the count in the header,
    and a count taken from the image alone would leave them outside what
    it was given.  That is memory the far heap goes on to hand somebody
    else, written to by a program that believes it owns it, with nothing
    failing at the time.

    It has to come from the map because the ELF cannot say: the linker
    emits a PT_LOAD for every memory it was GIVEN, used or not, all with
    the memory's full size, so an empty AppFarBss looks exactly like a
    full one.  The map lists the sections it actually placed.
    """
    end = far_base
    try:
        f = open(mapfile)
    except OSError:
        return end
    with f:
        for ln in f:
            m = re.match(r"^(far|zfar|ifar|farcode|switch|cfar|libcode|code)\s+"
                         r"([0-9a-f]{6})-([0-9a-f]{6})\s", ln)
            if m and int(m.group(2), 16) >= far_base:
                end = max(end, int(m.group(3), 16) + 1)
    return end


def image(segs, base, end):
    """The bytes of [base, end): what the file carries, zero elsewhere, and
    a mask of which bytes the file carried."""
    buf = bytearray(end - base)
    mask = bytearray(end - base)
    for a, data, memsz in segs:
        if base <= a < end:
            o = a - base
            buf[o:o + len(data)] = data
            for i in range(len(data)):
                mask[o + i] = 1
    return bytes(buf), bytes(mask)


def diff(base_img, base_mask, moved_img, moved_mask, what):
    """Offsets of the bytes that moved by exactly +1; refuses anything else."""
    if base_mask != moved_mask:
        raise SystemExit(f"{what}: the shifted link laid its bytes out differently")
    out = []
    for i, (a, b) in enumerate(zip(base_img, moved_img)):
        if a != b:
            if ((a + 1) & 0xFF) != b:
                raise SystemExit(f"{what}: byte {i} changed from ${a:02X} to "
                                 f"${b:02X}, not by +1: address arithmetic "
                                 f"the loader cannot relocate")
            out.append(i)
    return out


def vars_span(mapfile, vbase):
    """[vbase, end) of the far VARIABLES, from the linker's list file: they
    carry no bytes, so only the map says how far they reach."""
    end = vbase
    try:
        f = open(mapfile)
    except OSError:
        return end
    with f:
        for ln in f:
            m = re.match(r"^(far|zfar\d*)\s+([0-9a-f]{6})-([0-9a-f]{6})\s", ln)
            if m and int(m.group(2), 16) >= vbase:
                end = max(end, int(m.group(3), 16) + 1)
    return end


def packable(pack, base_elf, b_syms, near_img, near_mask, far_img, far_mask,
             nb, near_size, fb, fe, far_size, far_banks,
             near_hi, far_hi, near_bank, far_bank):
    """The fixup lists of a PACKED program (.G4A format 5), or a SystemExit
    saying why it cannot be one.

    Three more links (the Makefile's g4a): the code down a bank, the code
    up a page, the far variables up a page, the rest left where it was in
    each.  The bytes that move under the first are references to the CODE
    by bank; the bank shift of the two together (the far link) moved those
    and the references to the VARIABLES, so the variables' bank list is the
    difference.  The two page links give each region's page list.  A
    program packs when its code is one extent under the $D5 page and its
    variables fit one bank: then the loader can put each at any page of any
    bank, and several small programs share one."""
    cd_elf, cp_elf, vp_elf = pack
    c_segs, c_syms = read_elf_all(cd_elf)
    p_segs, p_syms = read_elf_all(cp_elf)
    v_segs, v_syms = read_elf_all(vp_elf)
    if fe - fb > PACK_LIMIT or (fb & 0xFFFF):
        raise SystemExit(f"the code is {fe - fb} bytes, over the ${PACK_LIMIT:04X} "
                         f"a packed program may have below the $D5 page")
    vbase = (fb & ~0xFFFF) + 0x10000        # one code bank: the variables next
    vend = vars_span(base_elf[:-4] + ".map", vbase)
    if far_banks > 2 or vend - vbase > 0x10000:
        raise SystemExit("the far variables do not fit one bank")
    for segs, what, code_at in ((c_segs, "code-down", fb - 0x10000),
                                (p_segs, "code-page", fb + 0x100),
                                (v_segs, "vars-page", fb)):
        cb = min(a for a, d, _ in segs if a >= 0x10000 and len(d))
        if cb != code_at:
            raise SystemExit(f"the {what} link put the code at ${cb:06X}, "
                             f"not ${code_at:06X}")
    cn, cnm = image(c_segs, nb, nb + near_size)
    cf, cfm = image(c_segs, fb - 0x10000, fe - 0x10000)
    pn, pnm = image(p_segs, nb, nb + near_size)
    pf, pfm = image(p_segs, fb + 0x100, fe + 0x100)
    vn, vnm = image(v_segs, nb, nb + near_size)
    vf, vfm = image(v_segs, fb, fe)
    # base = code-down + 1 bank: diff from the moved link TO the base
    near_cbank = diff(cn, cnm, near_img, near_mask, "near part, code bank")
    far_cbank = diff(cf, cfm, far_img, far_mask, "far part, code bank")
    near_cpage = diff(near_img, near_mask, pn, pnm, "near part, code page")
    far_cpage = diff(far_img, far_mask, pf, pfm, "far part, code page")
    near_vpage = diff(near_img, near_mask, vn, vnm, "near part, vars page")
    far_vpage = diff(far_img, far_mask, vf, vfm, "far part, vars page")
    if not set(near_cbank) <= set(near_bank) or not set(far_cbank) <= set(far_bank):
        raise SystemExit("a code bank fixup the whole-region shift did not see")
    near_vbank = sorted(set(near_bank) - set(near_cbank))
    far_vbank = sorted(set(far_bank) - set(far_cbank))
    if vend == vbase and (near_vbank or far_vbank or near_vpage or far_vpage):
        raise SystemExit("references to far variables, and none are placed")
    lists = [near_hi, near_cbank, near_cpage, near_vbank, near_vpage,
             far_hi, far_cbank, far_cpage, far_vbank, far_vpage]
    for part in (lists[:5], lists[5:]):
        seen = set()
        for lst in part:
            if seen & set(lst):
                raise SystemExit("a byte moved under two shifts")
            seen |= set(lst)
    return dict(lists=lists, vbase=vbase, vsize=vend - vbase)


# FORMAT 5's LISTS.  Seven per part, the near part's then the code's:
#   0 near page      a near address's high byte       + the near page delta
#   1 code long      a 24-bit code address: its middle byte at the offset
#                    + the code page delta, its bank byte after it + bank
#   2 code page      a 16-bit code address's high byte
#   3 code bank      a bank byte on its own
#   4 vars long, 5 vars page, 6 vars bank    the same for the variables
# A 24-bit address has a page fixup and a bank fixup side by side, and
# most of a program's are that; one entry for the pair instead of one in
# each list is what keeps a packed file no bigger than format 3 was (a
# DOS 2 floppy has no sectors to spare, docs/phase57.md).  Each list is a
# u16 count and then its offsets, rising, as deltas: a byte 1..255, or 0
# and the u16 offset itself.
V5_LISTS = 7


def v5_split(page, bank):
    """(long, page only, bank only) from a region's page and bank lists."""
    bank = set(bank)
    longs = [o for o in page if o + 1 in bank]
    ls = set(longs)
    return (longs, [o for o in page if o not in ls],
            sorted(bank - {o + 1 for o in longs}))


def v5_encode(offsets):
    out = bytearray(struct.pack("<H", len(offsets)))
    prev = 0
    for o in sorted(offsets):
        d = o - prev
        if 1 <= d <= 255:
            out.append(d)
        else:
            out += b"\0" + struct.pack("<H", o)
        prev = o
    return bytes(out)


def read_v5(blob):
    """A format 5 file, read the way src/sys/app.c app_load_v5 reads it:
    the header's fields, the near and code images, and the fourteen lists
    of offsets.  tests/host/test_pack.py and test_g4a.py use this, so the
    reading is written once on the host."""
    assert blob[:4] == MAGIC_V5, blob[:4]
    (link_near, near_size, code_off, code_size, code_link, vars_link, entry,
     vars_off, _z, vars_size) = struct.unpack("<HHHIBBIHHI", blob[4:28])
    at = HDR_V5
    near = blob[at:at + near_size]
    at += near_size
    code = blob[at:at + code_size]
    at += code_size
    lists = []
    for _ in range(2 * V5_LISTS):
        n, = struct.unpack("<H", blob[at:at + 2])
        at += 2
        lst, prev = [], 0
        for _ in range(n):
            d = blob[at]
            at += 1
            if d:
                prev += d
            else:
                prev, = struct.unpack("<H", blob[at:at + 2])
                at += 2
            lst.append(prev)
        lists.append(lst)
    if at != len(blob):
        raise SystemExit(f"{len(blob) - at} bytes past the lists")
    return dict(link_near=link_near, near_size=near_size, code_off=code_off,
                code_size=code_size, code_link=code_link, vars_link=vars_link,
                entry=entry, vars_off=vars_off, vars_size=vars_size,
                near=near, code=code, lists=lists)


def apply_v5(f, near_at, code_at, vars_at):
    """The near part and the code as app_load_v5 leaves them for those
    three places: (near, code), patched."""
    near, code = bytearray(f["near"]), bytearray(f["code"])
    dn = ((near_at - f["link_near"]) >> 8) & 0xFF
    dcb = ((code_at >> 16) - f["code_link"]) & 0xFF
    dcp = (((code_at & 0xFFFF) - f["code_off"]) >> 8) & 0xFF
    dvb = ((vars_at >> 16) - f["vars_link"]) & 0xFF
    dvp = (((vars_at & 0xFFFF) - f["vars_off"]) >> 8) & 0xFF
    adds = [(dn, None), (dcp, dcb), (dcp, None), (dcb, None),
            (dvp, dvb), (dvp, None), (dvb, None)]
    for l, lst in enumerate(f["lists"]):
        part = near if l < V5_LISTS else code
        first, second = adds[l % V5_LISTS]
        for o in lst:
            part[o] = (part[o] + first) & 0xFF
            if second is not None:
                part[o + 1] = (part[o + 1] + second) & 0xFF
    return bytes(near), bytes(code)


def write_v5(out, packed, nb, near_size, fb, far_size, entry,
             near_img, far_img, b_syms, syms_out, c_out, c_name):
    """Format 5 (src/sys/app.c reads it):

      0  'G4A' 5
      4  u16 near_base, u16 near_size
      8  u16 code_off, u32 code_size       the image: code, constants, ifar
     14  u8  code_bank, u8 vars_bank       where each was linked
     16  u32 entry
     20  u16 vars_off, u16 0, u32 vars_size   no bytes: the crt makes them
     28  20 bytes of 0
     48  near bytes, code bytes, then the fourteen lists (V5_LISTS above)
    """
    (n_np, n_cb, n_cp, n_vb, n_vp, f_np, f_cb, f_cp, f_vb, f_vp) = packed["lists"]
    lists = []
    for np_, cp, cb, vp, vb in ((n_np, n_cp, n_cb, n_vp, n_vb),
                                (f_np, f_cp, f_cb, f_vp, f_vb)):
        lists += [np_, *v5_split(cp, cb), *v5_split(vp, vb)]
    vb, vs = packed["vbase"], packed["vsize"]
    hdr = MAGIC_V5 + struct.pack("<HHHIBBIHHI", nb, near_size, fb & 0xFFFF,
                                 far_size, fb >> 16, vb >> 16, entry,
                                 vb & 0xFFFF, 0, vs)
    hdr += bytes(20)
    assert len(hdr) == HDR_V5, len(hdr)
    body = near_img + far_img + b"".join(v5_encode(l) for l in lists)
    blob = hdr + body
    # read it back and patch it for where it was linked: nothing may move
    f = read_v5(blob)
    if apply_v5(f, nb, fb, vb) != (near_img, far_img):
        raise SystemExit("format 5 does not read back as it was written")
    with open(out, "wb") as fh:
        fh.write(blob)
    if syms_out:
        with open(syms_out, "w") as fh:
            for name, val in sorted(b_syms.items(), key=lambda kv: kv[1]):
                fh.write(f"{name} {val:06X}\n")
    if c_out:
        with open(c_out, "w") as fh:
            fh.write(f"/* Generated by tools/mkg4a.py from {out} -- do not edit. */\n")
            fh.write("#include <stdint.h>\n")
            fh.write("#include \"portab.h\"\n")
            fh.write(f"const uint32_t {c_name}_len = {len(blob)}UL;\n")
            fh.write(f"const uint8_t FAR {c_name}[{len(blob)}] = {{\n")
            for o in range(0, len(blob), 16):
                fh.write("    " + ",".join(f"{b}" for b in blob[o:o + 16]) + ",\n")
            fh.write("};\n")
    print(f"{out}: PACKED, near ${nb:04X}+{near_size}, code ${fb:06X}+{far_size}, "
          f"far variables ${vb:06X}+{vs}, fixups "
          + "/".join(str(len(l)) for l in lists) + f", {len(blob)} bytes")
    return 0


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    base_elf, near_elf, far_elf, out = argv[:4]
    syms_out = c_out = c_name = None
    pack = None
    i = 4
    while i < len(argv):
        if argv[i] == "--syms":
            syms_out = argv[i + 1]
            i += 2
        elif argv[i] == "--pack":
            pack = argv[i + 1:i + 4]
            i += 4
        elif argv[i] == "--c-array":
            c_out, c_name = argv[i + 1], argv[i + 2]
            i += 3
        else:
            raise SystemExit(f"unknown option {argv[i]}")

    b_segs, b_syms = read_elf_all(base_elf)
    n_segs, n_syms = read_elf_all(near_elf)
    f_segs, f_syms = read_elf_all(far_elf)
    nb, ne, fb, fe = extents(b_segs, b_syms)
    nn, nne, nf, nfe = extents(n_segs, n_syms)
    fn, fne, ff, ffe = extents(f_segs, f_syms)
    fspan = far_span(base_elf[:-4] + ".map", fb)
    far_banks = ((max(fspan, fe) - 1) >> 16) - (fb >> 16) + 1

    # The shifts are whatever the links say they are; each must move one
    # region by a whole page / bank and leave the other alone.
    near_shift, far_shift = nn - nb, ff - fb
    if near_shift != 0x100 or nf != fb or (nne - nn) != (ne - nb) or (nfe - nf) != (fe - fb):
        raise SystemExit(f"the near-shifted link should move the near region "
                         f"up exactly one page: near ${nb:04X}->${nn:04X}, "
                         f"far ${fb:06X}->${nf:06X}")
    if far_shift != 0x10000 or fn != nb or (fne - fn) != (ne - nb) or (ffe - ff) != (fe - fb):
        raise SystemExit(f"the far-shifted link should move the far region "
                         f"up exactly one bank: near ${nb:04X}->${fn:04X}, "
                         f"far ${fb:06X}->${ff:06X}")

    near_size = (ne - nb + 0xFF) & ~0xFF
    far_size = fe - fb
    near_img, near_mask = image(b_segs, nb, nb + near_size)
    far_img, far_mask = image(b_segs, fb, fe)
    n_near_img, n_near_mask = image(n_segs, nn, nn + near_size)
    n_far_img, n_far_mask = image(n_segs, nf, nf + far_size)
    f_near_img, f_near_mask = image(f_segs, fn, fn + near_size)
    f_far_img, f_far_mask = image(f_segs, ff, ff + far_size)

    near_hi = diff(near_img, near_mask, n_near_img, n_near_mask, "near part, page shift")
    far_hi = diff(far_img, far_mask, n_far_img, n_far_mask, "far part, page shift")
    near_bank = diff(near_img, near_mask, f_near_img, f_near_mask, "near part, bank shift")
    far_bank = diff(far_img, far_mask, f_far_img, f_far_mask, "far part, bank shift")
    both = (set(near_hi) & set(near_bank)) | (set(far_hi) & set(far_bank))
    if both:
        raise SystemExit(f"bytes moved under both shifts: {sorted(both)[:8]}")

    entry = b_syms["__program_start"]
    if not (fb <= entry < fe):
        raise SystemExit(f"entry ${entry:06X} is not in the far region")

    # The call gates the program was linked with must be the ones the format
    # number stamped below promises (src/sys/abi.h).  Objects built from an
    # older kit's gemabi.s would otherwise leave here as a format 3 or 4 file
    # whose every call is refused on the Atari, with nothing on the host to
    # say so.  A program that links no gate is not asked.
    for name, sig in GATES.items():
        a = b_syms.get(name)
        if a is None or not fb <= a < fe - 1:
            continue
        got = far_img[a - fb:a - fb + 2]
        if got != bytes((0x02, sig)):
            raise SystemExit(f"{name} is {got.hex(' ')}, not COP #${sig:02X}: "
                             f"the program was linked with an older kit's "
                             f"gemabi.s -- rebuild its objects with this kit")

    # PACKED, when it can be: format 5 (phase 80).  The rest is v3 or v4.
    packed = None
    if pack:
        try:
            packed = packable(pack, base_elf, b_syms, near_img, near_mask,
                              far_img, far_mask, nb, near_size, fb, fe, far_size,
                              far_banks, near_hi, far_hi, near_bank, far_bank)
        except SystemExit as why:
            print(f"{out}: not packed -- {why}")
    if packed:
        return write_v5(out, packed, nb, near_size, fb, far_size, entry,
                        near_img, far_img, b_syms, syms_out, c_out, c_name)

    # v3 unless the far image needs more room than its offsets have. Every
    # program in this tree but GACS's shell is v3.
    wide = far_size > 0x10000
    for name, lst in (("near", near_hi + near_bank), ("far", far_hi + far_bank)):
        if len(lst) > 0xFFFF:
            raise SystemExit(f"{len(lst)} {name} fixups: the header counts "
                             f"them in a u16")
    hdr = (MAGIC_V4 if wide else MAGIC_V3) + struct.pack(
                              "<HHHIBBHBBHHHHI",
                              nb, near_size, fb & 0xFFFF, far_size, fb >> 16,
                              far_banks,
                              entry & 0xFFFF, entry >> 16, 0,
                              len(near_hi), len(near_bank), len(far_hi), len(far_bank), 0)
    assert len(hdr) == 32, len(hdr)
    body = near_img + far_img
    for lst in (near_hi, near_bank):
        body += b"".join(struct.pack("<H", o) for o in lst)
    for lst in (far_hi, far_bank):
        if wide:
            body += b"".join(struct.pack("<I", o)[:3] for o in lst)
        else:
            body += b"".join(struct.pack("<H", o) for o in lst)
    blob = hdr + body
    with open(out, "wb") as f:
        f.write(blob)

    if syms_out:
        with open(syms_out, "w") as f:
            for name, val in sorted(b_syms.items(), key=lambda kv: kv[1]):
                f.write(f"{name} {val:06X}\n")
    if c_out:
        with open(c_out, "w") as f:
            f.write(f"/* Generated by tools/mkg4a.py from {out} -- do not edit. */\n")
            f.write("#include <stdint.h>\n")
            f.write("#include \"portab.h\"\n")
            f.write(f"const uint32_t {c_name}_len = {len(blob)}UL;\n")
            f.write(f"const uint8_t FAR {c_name}[{len(blob)}] = {{\n")
            for o in range(0, len(blob), 16):
                f.write("    " + ",".join(f"{b}" for b in blob[o:o + 16]) + ",\n")
            f.write("};\n")

    print(f"{out}: near ${nb:04X}+{near_size} ({len(near_hi)} page, "
          f"{len(near_bank)} bank fixups), far ${fb:06X}+{far_size} "
          f"({len(far_hi)} page, {len(far_bank)} bank fixups), "
          f"entry ${entry:06X}, {len(blob)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
