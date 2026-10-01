#!/usr/bin/env python3
"""A GEM resource file, built on the host, and what the AES makes of it.

A .RSC (the DRI/RCS "old" format, the one every TOS reads) is a header of
eighteen big-endian words followed by the OBJECT, TEDINFO, ICONBLK and
BITBLK arrays, the strings and image bits they point at, and three tables
of longs -- the free strings, the free images, the trees -- with every
pointer an offset from the start of the file and every object rectangle a
(pixel offset << 8 | character position) word, so that one file serves
every screen the AES may find itself on.

`Rsc` collects the pieces and lays them out at fixed file offsets; `file()`
is the file, and `expect(base, wchar, hchar, width)` is the same file as
the AES's rsrc_load leaves it in memory at `base`: words in the 65816's
order, offsets made addresses, rectangles made pixels, the TEDINFO
lengths filled in -- together with the `Obj` lists and the address map
tools/aesref.py draws the trees from.  The two come from ONE description,
so the target's fixed-up image is compared with what the description
means, not with a second loader's reading of the same bytes.

The rules are EmuTOS aes/gemrslib.c's (rs_readit, rs_fixit, fix_chpos,
fix_long, fix_tedinfo_std, fix_nptrs, fix_objects); src/aes/rsrc.c is
the other reading of them.
"""
import struct

import aesref
from aesref import (Obj, Text, Ted, Bitblk, Iconblk, Rect, G_BOX, G_IBOX,
                    G_BOXCHAR, G_CICON)

# The colour-icon extension a new-format resource carries past rsh_rssize
# (EmuTOS aes/gemrslib.c), and what rs_load brings NEAR of it: one
# CICON_NEAR record per icon -- the ICONBLK, fourteen bytes of text (the
# file's twelve and two 0s), and the far addresses of the 4-plane form and
# its selected form, 0 for none (src/aes/aes.h, src/aes/rsrc.c).
CICON_HDR = 38          # on disk: an ICONBLK and a LONG count of forms
CICON_FORM = 22         # on disk: one CICON header
CICON_TEXT = 12         # on disk
CICON_NTEXT = 14        # in the near record
CICON_BYTES = 128       # the biggest form drawn in colour: one 32x32 plane
CICON_NEAR = 56

HDR_SIZE = 36
OBJ_SIZE, TED_SIZE, BITBLK_SIZE, ICONBLK_SIZE = 24, 28, 14, 34
NIL = -1

# rsrc_gaddr / rsrc_saddr types
(R_TREE, R_OBJECT, R_TEDINFO, R_ICONBLK, R_BITBLK, R_STRING, R_IMAGEDATA,
 R_OBSPEC, R_TEPTEXT, R_TEPTMPLT, R_TEPVALID, R_IBPMASK, R_IBPDATA,
 R_IBPTEXT, R_BIPDATA, R_FRSTR, R_FRIMG) = range(17)


def ch(chars, px=0):
    """A rectangle word: `chars` character cells, then `px` pixels (-128..127
    -- the AES reads the high byte as signed past 128, so 128 itself is
    +128)."""
    assert 0 <= chars <= 255 and -128 <= px <= 128, (chars, px)
    return ((px & 0xFF) << 8) | chars


def fix_chpos(word, which, wchar, hchar, width):
    """gemrslib.c fix_chpos, on one word: which is 0 x, 1 y, 2 w, 3 h."""
    coffset = (word >> 8) & 0xFF
    cpos = word & 0xFF
    if which == 0:
        cpos *= wchar
    elif which == 1:
        cpos *= hchar
    elif which == 2:
        cpos = width if cpos == 80 else cpos * wchar
    else:
        cpos *= hchar
    return cpos + (coffset - 256 if coffset > 128 else coffset)


class _Item:
    """Anything with a file offset once the Rsc is laid out."""
    off = None


class String(_Item):
    def __init__(self, s):
        self.s = s
        self.blob = s.encode("latin-1") + b"\0"


class ImageData(_Item):
    def __init__(self, rows):
        self.blob = bytes(rows)


class RBitblk(_Item):
    def __init__(self, data, wb, hl, x, y, color):
        self.data, self.wb, self.hl, self.x, self.y, self.color = \
            data, wb, hl, x, y, color


class RIconblk(_Item):
    def __init__(self, mask, data, text, char, xchar, ychar, xicon, yicon,
                 wicon, hicon, xtext, ytext, wtext, htext):
        (self.mask, self.data, self.text, self.char, self.xchar, self.ychar,
         self.xicon, self.yicon, self.wicon, self.hicon, self.xtext,
         self.ytext, self.wtext, self.htext) = (
            mask, data, text, char, xchar, ychar, xicon, yicon, wicon, hicon,
            xtext, ytext, wtext, htext)


class RCicon(_Item):
    """A CICONBLK: an ICONBLK's worth of geometry, the mono mask and bits
    (raw rows, not image items -- they live in the extension), a text of
    up to twelve characters, and colour forms as (planes, data, mask) or
    (planes, data, mask, selected data, selected mask)."""
    def __init__(self, mask, data, text, char, xchar, ychar, xicon, yicon,
                 wicon, hicon, xtext, ytext, wtext, htext, forms):
        (self.mask, self.data, self.text, self.char, self.xchar, self.ychar,
         self.xicon, self.yicon, self.wicon, self.hicon, self.xtext,
         self.ytext, self.wtext, self.htext, self.forms) = (
            mask, data, text, char, xchar, ychar, xicon, yicon, wicon, hicon,
            xtext, ytext, wtext, htext, list(forms))

    @property
    def mono(self):                     # bytes of one plane
        return (self.wicon // 8) * self.hicon

    @property
    def size(self):                     # the whole CICONBLK on disk
        return (CICON_HDR + 2 * self.mono + CICON_TEXT
                + sum((CICON_FORM + self.mono * f[0] + self.mono)
                      + (self.mono * f[0] + self.mono if len(f) > 3 else 0)
                      for f in self.forms))


class RTed(_Item):
    def __init__(self, text, tmplt, valid, font, just, color, thickness,
                 txtlen, tmplen):
        (self.text, self.tmplt, self.valid, self.font, self.just, self.color,
         self.thickness, self.txtlen, self.tmplen) = (
            text, tmplt, valid, font, just, color, thickness, txtlen, tmplen)


class RObj(_Item):
    def __init__(self, nxt, head, tail, typ, flags, state, spec, x, y, w, h):
        (self.nxt, self.head, self.tail, self.typ, self.flags, self.state,
         self.spec, self.x, self.y, self.w, self.h) = (
            nxt, head, tail, typ, flags, state, spec, x, y, w, h)


def flags3d(objs, flat=()):
    """A dialog's 3D flags, by what each object is -- the rule EmuTOS
    applies by hand to its own dialogs: the box is a BACKGROUND; an EXIT
    button an ACTIVATOR; a selectable button or box an INDICATOR; and a
    plain TEXT or FTEXT standing on the box a BACKGROUND too, which in
    gem4xe takes the grey ground and no edge (src/aes/objc.c) -- a value
    drawn in replace mode would otherwise be a white strip on the grey.  `flat` names objects to leave as
    they are: a list's rows, which read as a list and not as buttons."""
    A = aesref
    on_root = set()
    if objs and objs[0][1] != NIL:
        c = objs[0][1]
        while c not in (NIL, 0) and c > 0:
            on_root.add(c)
            c = objs[c][0]
    out = []
    for i, o in enumerate(objs):
        o = list(o)
        typ, flags = o[3] & 0xFF, o[4]
        if flags & A.FL3DMASK or i in flat:
            pass                                  # the tree said so itself
        elif i == 0 and typ == A.G_BOX:
            flags |= A.FL3DBAK
        elif typ == A.G_BUTTON and flags & A.EXIT:
            flags |= A.FL3DACT
        elif typ in (A.G_BUTTON, A.G_BOX, A.G_BOXCHAR) and flags & A.SELECTABLE:
            flags |= A.FL3DIND
        elif typ in (A.G_TEXT, A.G_FTEXT) and i in on_root:
            flags |= A.FL3DBAK
        o[4] = flags
        out.append(tuple(o))
    return out


def overlaps3d(objs, wchar=8, hchar=8):
    """Where a dialog's 3D look draws one object over another.  A 3D
    indicator or activator grows ADJ3DSTD pixels on every side (three
    more when OUTLINED), so it must not reach any other visible object --
    a label, another button grown the same way -- nor the dialog's own
    edge.  Invisible group boxes (G_IBOX) and the objects an object sits
    inside are not counted.  [(a, b, why)], empty when it fits; positions
    in pixels for a wchar x hchar cell."""
    A = aesref

    def px(word, cell):
        return (word & 0xFF) * cell + (((word >> 8) ^ 0x80) - 0x80)

    n = len(objs)
    par = [None] * n
    for p in range(n):
        c = objs[p][1]
        while c not in (NIL, -1) and c >= 0 and c != p:
            par[c] = p
            c = objs[c][0]
    absr = [None] * n

    def ab(i):
        if absr[i] is None:
            o = objs[i]
            x, y = px(o[7], wchar), px(o[8], hchar)
            if par[i] is not None:
                px0, py0 = ab(par[i])[:2]
                x, y = x + px0, y + py0
            absr[i] = (x, y, px(o[9], wchar), px(o[10], hchar))
        return absr[i]

    def ancestors(i):
        out = set()
        while par[i] is not None:
            i = par[i]
            out.add(i)
        return out

    def grown(i):
        x, y, w, h = ab(i)
        f = objs[i][4] & A.FL3DMASK
        if f and f != A.FL3DBAK:
            g = A.ADJ3DSTD + (3 if objs[i][5] & A.OUTLINED else 0)
            return (x - g, y - g, w + 2 * g, h + 2 * g)
        return (x, y, w, h)

    bad = []
    rx, ry, rw, rh = ab(0)
    for i in range(1, n):
        f = objs[i][4] & A.FL3DMASK
        if not f or f == A.FL3DBAK:
            continue
        gx, gy, gw, gh = grown(i)
        if gx < rx or gy < ry or gx + gw > rx + rw or gy + gh > ry + rh:
            bad.append((i, 0, "past the dialog's edge"))
        up = ancestors(i)
        for s in range(1, n):
            if s == i or s in up or i in ancestors(s):
                continue
            if objs[s][3] & 0xFF == A.G_IBOX:
                continue
            sf = objs[s][4] & A.FL3DMASK
            if sf and sf != A.FL3DBAK and s < i:
                continue                    # the pair is reported once
            sx, sy, sw, sh = grown(s)
            if gx < sx + sw and sx < gx + gw and gy < sy + sh and sy < gy + gh:
                bad.append((i, s, "touches"))
    return bad


class Rsc:
    def __init__(self):
        self.strings, self.images, self.bitblks, self.iconblks = [], [], [], []
        self.teds, self.objects = [], []
        self.trees = []                 # (first object index, count)
        self.frstr, self.frimg = [], [] # String / RBitblk items
        self.cicons = []                # RCicon items, in the extension
        self.size = None                # rsh_rssize: the classic part
        self.file_len = None            # ...and the file, extension included

    # -- the pieces ----------------------------------------------------------
    def string(self, s):
        it = String(s)
        self.strings.append(it)
        return it

    def imagedata(self, rows):
        it = ImageData(rows)
        self.images.append(it)
        return it

    def bitblk(self, rows, wb, hl, x=0, y=0, color=aesref.BLACK):
        assert len(rows) == wb * hl, (len(rows), wb, hl)
        it = RBitblk(self.imagedata(rows), wb, hl, x, y, color)
        self.bitblks.append(it)
        return it

    def iconblk(self, mask, data, text, wicon, hicon, char=0, xchar=0,
                ychar=0, xicon=0, yicon=0, xtext=0, ytext=0, wtext=0, htext=0):
        assert len(mask) == len(data) == (wicon // 8) * hicon
        it = RIconblk(self.imagedata(mask), self.imagedata(data),
                      self.string(text), char, xchar, ychar, xicon, yicon,
                      wicon, hicon, xtext, ytext, wtext, htext)
        self.iconblks.append(it)
        return it

    def cicon(self, mask, data, text, wicon, hicon, forms=(), char=0,
              xchar=0, ychar=0, xicon=0, yicon=0, xtext=0, ytext=0,
              wtext=0, htext=0):
        """A colour icon.  Its index is what a G_CICON object's spec holds
        in the file; the loader makes that the address of the near record.
        `forms`: (planes, data, mask) triples, data being planes * mono
        bytes, mask one plane's worth -- or, with a SELECTED form,
        (planes, data, mask, selected data, selected mask).  Twelve
        characters of text is the most, and has no 0 after it in the
        file, as the Falcon's are written."""
        mono = (wicon // 8) * hicon
        assert len(mask) == len(data) == mono, (len(mask), len(data), mono)
        assert len(text) <= CICON_TEXT, text
        for f in forms:
            planes, d, m = f[:3]
            assert len(d) == planes * mono and len(m) == mono, (planes, len(d), len(m))
            if len(f) > 3:
                assert len(f[3]) == planes * mono and len(f[4]) == mono, (planes, len(f[3]), len(f[4]))
        it = RCicon(mask, data, text, char, xchar, ychar, xicon, yicon,
                    wicon, hicon, xtext, ytext, wtext, htext, forms)
        self.cicons.append(it)
        return len(self.cicons) - 1

    def ted(self, text, tmplt, valid, font=aesref.IBM, just=aesref.TE_LEFT,
            color=0x1180, thickness=0):
        """The file carries te_txtlen/te_tmplen as RCS wrote them; the AES
        overwrites both with strlen + 1 at load, so what goes in the file
        is deliberately wrong (0) to prove that.  RCS sizes the text
        buffer to the template's underscores; so does this.  `tmplt` and
        `valid` may be `String` items already in the file, so that several
        fields share one template the way RCS lets them."""
        if not isinstance(tmplt, String):
            tmplt = self.string(tmplt)
        if not isinstance(valid, String):
            valid = self.string(valid)
        room = max(tmplt.s.count("_"), len(text)) + 1
        t = String(text)
        t.blob = t.blob + b"\0" * (room - len(t.blob))
        self.strings.append(t)
        it = RTed(t, tmplt, valid, font, just, color, thickness, 0, 0)
        self.teds.append(it)
        return it

    def tree(self, objs, look3d=False, flat=()):
        """objs: (next, head, tail, type, flags, state, spec, x, y, w, h)
        with the rectangle words from ch() and spec an item or an int.

        look3d: this tree is a DIALOG, and gets AES 3.40's 3D flags --
        drawn only while the 3D look is on, ignored by a flat AES, so a
        resource carrying them is right on both (src/aes/objc.c)."""
        if look3d:
            objs = flags3d(objs, flat)
        first = len(self.objects)
        for o in objs:
            self.objects.append(RObj(*o))
        self.trees.append((first, len(objs)))
        return len(self.trees) - 1

    def free_string(self, s):
        it = self.string(s)
        self.frstr.append(it)
        return len(self.frstr) - 1

    def free_image(self, bb):
        self.frimg.append(bb)
        return len(self.frimg) - 1

    # -- the file --------------------------------------------------------------
    def layout(self):
        """Assign every item its file offset.  Strings first (bytes, so the
        tables after them start even), then the four arrays, then the three
        tables of longs -- and THE IMAGE BITS LAST.

        Last is not cosmetic.  A resource is loaded into the application
        pool, which is 14 KB of bank $00 for the desktop, its resource and
        everything resident beside it, and the image bits are a quarter of
        DESKTOP.RSC while being the one part of it nothing in bank $00
        needs to reach: an ICONBLK names its mask and its image in 32-bit
        fields and the VDI has taken 32-bit addresses since phase 2.  With
        the bits at the END of the file, src/aes/rsrc.c can copy them to
        far memory and hand the pool back everything above them -- without
        compacting the middle of the file, which would invalidate every
        offset already fixed up.

        The strings stay where they are.  ob_spec points at them and the
        object library reads them through a near pointer."""
        off = HDR_SIZE
        self.o_string = off
        for it in self.strings:
            it.off = off
            off += len(it.blob)
        off += off & 1
        self.o_bitblk = off
        for it in self.bitblks:
            it.off = off
            off += BITBLK_SIZE
        self.o_iconblk = off
        for it in self.iconblks:
            it.off = off
            off += ICONBLK_SIZE
        self.o_tedinfo = off
        for it in self.teds:
            it.off = off
            off += TED_SIZE
        self.o_object = off
        for it in self.objects:
            it.off = off
            off += OBJ_SIZE
        self.o_frstr = off
        off += 4 * len(self.frstr)
        self.o_frimg = off
        off += 4 * len(self.frimg)
        self.o_trindex = off
        off += 4 * len(self.trees)
        off += off & 1
        self.o_imdata = off             # last: see the note above
        for it in self.images:
            it.off = off
            off += len(it.blob)
        self.size = off
        # THE COLOUR-ICON EXTENSION, past rsh_rssize: an array of longs --
        # the true length, the table's offset, a 0 -- the table of one long
        # per icon ending in -1, then the CICONBLKs.  rs_load streams all
        # of it to far memory and never has it in the pool.
        if self.cicons:
            self.o_extarray = off
            off += 12
            self.o_citable = off
            off += 4 * (len(self.cicons) + 1)
            for it in self.cicons:
                it.off = off
                off += it.size
        self.file_len = off
        return off

    def _spec(self, o):
        return o.spec if isinstance(o.spec, int) else o.spec.off

    def header(self, e):
        vrsn = 0x0004 if self.cicons else 0     # NEW_FORMAT_RSC
        return struct.pack(e + "18H", vrsn, self.o_object, self.o_tedinfo,
                           self.o_iconblk, self.o_bitblk, self.o_frstr,
                           self.o_string, self.o_imdata, self.o_frimg,
                           self.o_trindex, len(self.objects), len(self.trees),
                           len(self.teds), len(self.iconblks), len(self.bitblks),
                           len(self.frstr), len(self.frimg), self.size)

    def file(self):
        """The file: big-endian, offsets, character rectangles."""
        self.layout()
        e = ">"
        out = bytearray(self.size)
        out[0:HDR_SIZE] = self.header(e)
        for it in self.strings + self.images:
            out[it.off:it.off + len(it.blob)] = it.blob
        for it in self.bitblks:
            out[it.off:it.off + BITBLK_SIZE] = struct.pack(
                e + "Ihhhhh", it.data.off, it.wb, it.hl, it.x, it.y, it.color)
        for it in self.iconblks:
            out[it.off:it.off + ICONBLK_SIZE] = struct.pack(
                e + "IIIhhhhhhhhhhh", it.mask.off, it.data.off, it.text.off,
                it.char, it.xchar, it.ychar, it.xicon, it.yicon, it.wicon,
                it.hicon, it.xtext, it.ytext, it.wtext, it.htext)
        for it in self.teds:
            out[it.off:it.off + TED_SIZE] = struct.pack(
                e + "IIIhhhhhhhh", it.text.off, it.tmplt.off, it.valid.off,
                it.font, 0, it.just, it.color, 0, it.thickness,
                it.txtlen, it.tmplen)
        for o in self.objects:
            out[o.off:o.off + OBJ_SIZE] = struct.pack(
                e + "hhhHHHIHHHH", o.nxt, o.head, o.tail, o.typ, o.flags,
                o.state, self._spec(o) & 0xFFFFFFFF, o.x, o.y, o.w, o.h)
        p = self.o_frstr
        for it in self.frstr:
            out[p:p + 4] = struct.pack(e + "I", it.off)
            p += 4
        p = self.o_frimg
        for it in self.frimg:
            out[p:p + 4] = struct.pack(e + "I", it.off)
            p += 4
        p = self.o_trindex
        for first, n in self.trees:
            out[p:p + 4] = struct.pack(e + "I", self.objects[first].off)
            p += 4
        if self.cicons:
            out += bytes(self.file_len - self.size)
            out[self.o_extarray:self.o_extarray + 12] = struct.pack(
                e + "III", self.file_len, self.o_citable, 0)
            p = self.o_citable
            for it in self.cicons:          # placeholders: the loader fills them
                out[p:p + 4] = struct.pack(e + "I", 0)
                p += 4
            out[p:p + 4] = struct.pack(e + "i", -1)
            for it in self.cicons:
                p = it.off
                out[p:p + ICONBLK_SIZE] = struct.pack(
                    e + "IIIhhhhhhhhhhh", 0, 0, 0, it.char, it.xchar, it.ychar,
                    it.xicon, it.yicon, it.wicon, it.hicon, it.xtext, it.ytext,
                    it.wtext, it.htext)
                p += ICONBLK_SIZE
                out[p:p + 4] = struct.pack(e + "I", len(it.forms))
                p += 4
                out[p:p + it.mono] = it.data
                p += it.mono
                out[p:p + it.mono] = it.mask
                p += it.mono
                out[p:p + CICON_TEXT] = it.text.encode("latin-1").ljust(CICON_TEXT, b"\0")
                p += CICON_TEXT
                for k, f in enumerate(it.forms):
                    planes, d, m = f[:3]
                    sel = 1 if len(f) > 3 else 0        # a pointer the loader
                    more = 1 if k + 1 < len(it.forms) else 0    # tests for 0
                    out[p:p + CICON_FORM] = struct.pack(
                        e + "hIIIII", planes, 0, 0, sel, sel, more)
                    p += CICON_FORM
                    for blob in f[1:]:          # image, mask, and the
                        out[p:p + len(blob)] = blob     # selected pair
                        p += len(blob)
                assert p == it.off + it.size, (p, it.off, it.size)
        return bytes(out)

    # -- what the AES makes of it ----------------------------------------------
    def expect(self, base, wchar, hchar, width, imbase=None, cibase=None):
        """(image, trees, mem): the file as rsrc_load leaves it at `base`,
        the trees as aesref Obj lists, and the address map for aesref.

        `imbase` is where the ICON BITMAPS ended up, when rs_load moved
        them to far memory and wound the pool back over them -- which it
        does for any resource with no BITBLKs and no free images, because
        an ICONBLK names its mask and its image in 32-bit fields
        (src/aes/rsrc.c).  Pass it and the ICONBLKs carry far addresses,
        as the target's do; leave it and they are near, which is what a
        resource whose bits stayed in the pool has.

        `cibase` is where the COLOUR-ICON EXTENSION went, for a resource
        that has one (rs_ciaddr on the target).  The near records rs_load
        makes of it are placed where the loader places them -- where the
        images were if they moved, else after the file, word-aligned --
        and `self.ci_near` is (address, bytes) so a gate can compare them.
        """
        self.layout()
        moved = imbase is not None
        if imbase is None:
            imbase = base
        else:
            imbase -= self.o_imdata        # so + it.off lands on the bytes
        if self.cicons and cibase is None:
            raise ValueError("a resource with colour icons needs cibase")
        hb = base + self.o_imdata if moved else (base + self.size + 1) & ~1
        e = "<"
        out = bytearray(self.size)
        out[0:HDR_SIZE] = self.header(e)
        mem = {}
        for it in self.strings:
            out[it.off:it.off + len(it.blob)] = it.blob
            mem[base + it.off] = Text(it.s, len(it.blob))
        for it in self.images:
            out[it.off:it.off + len(it.blob)] = it.blob
            mem[imbase + it.off] = it.blob
        for it in self.bitblks:
            # never moved: rs_load keeps the bits of a resource with
            # BITBLKs in the pool, so this is still a near address
            b = Bitblk(base + it.data.off, it.wb, it.hl, it.x, it.y, it.color)
            out[it.off:it.off + BITBLK_SIZE] = b.pack()
            mem[base + it.off] = b
        for it in self.iconblks:
            ib = Iconblk(imbase + it.mask.off, imbase + it.data.off,
                         base + it.text.off, it.char, it.xchar, it.ychar,
                         Rect(it.xicon, it.yicon, it.wicon, it.hicon),
                         Rect(it.xtext, it.ytext, it.wtext, it.htext))
            out[it.off:it.off + ICONBLK_SIZE] = ib.pack()
            mem[base + it.off] = ib
        for it in self.teds:
            t = Ted(base + it.text.off, base + it.tmplt.off, base + it.valid.off,
                    font=it.font, just=it.just, color=it.color,
                    thickness=it.thickness, txtlen=len(it.text.s) + 1,
                    tmplen=len(it.tmplt.s) + 1)
            out[it.off:it.off + TED_SIZE] = t.pack()
            mem[base + it.off] = t
        # the near records of the colour icons, as rs_cicons lays them out
        near = bytearray()
        for i, it in enumerate(self.cicons):
            a = hb + CICON_NEAR * i
            data = cibase + (it.off + CICON_HDR - self.size)
            mask = data + it.mono
            # the first 4-plane form, if the icon is small enough to be
            # drawn in colour: its image, past the form's header, and its
            # selected image after the image's mask, if it has one
            col4 = sel4 = 0
            fo = it.off + CICON_HDR + 2 * it.mono + CICON_TEXT
            for f in it.forms:
                planes = f[0]
                if planes == 4 and not col4 and it.mono <= CICON_BYTES:
                    col4 = cibase + (fo + CICON_FORM - self.size)
                    if len(f) > 3:
                        sel4 = col4 + 5 * it.mono
                fo += CICON_FORM + it.mono * planes + it.mono
                if len(f) > 3:
                    fo += it.mono * planes + it.mono
            ib = Iconblk(mask, data, a + ICONBLK_SIZE, it.char, it.xchar, it.ychar,
                         Rect(it.xicon, it.yicon, it.wicon, it.hicon),
                         Rect(it.xtext, it.ytext, it.wtext, it.htext))
            mem[a] = ib
            mem[a + ICONBLK_SIZE] = Text(it.text, CICON_NTEXT)
            mem[data] = it.data
            mem[mask] = it.mask
            near += ib.pack()
            near += it.text.encode("latin-1").ljust(CICON_NTEXT, b"\0")
            near += struct.pack("<II", col4, sel4)
        self.ci_near = (hb, bytes(near))
        objs = []
        for o in self.objects:
            spec = self._spec(o)
            if (o.typ & 0xFF) == G_CICON:
                spec = hb + CICON_NEAR * spec       # an index, made an address
            elif (o.typ & 0xFF) not in (G_BOX, G_IBOX, G_BOXCHAR):
                spec += base
            ob = Obj(o.nxt, o.head, o.tail, o.typ, o.flags, o.state, spec,
                     fix_chpos(o.x, 0, wchar, hchar, width),
                     fix_chpos(o.y, 1, wchar, hchar, width),
                     fix_chpos(o.w, 2, wchar, hchar, width),
                     fix_chpos(o.h, 3, wchar, hchar, width))
            out[o.off:o.off + OBJ_SIZE] = ob.pack()
            objs.append(ob)
        p = self.o_frstr
        for it in self.frstr:
            out[p:p + 4] = struct.pack(e + "I", base + it.off)
            p += 4
        p = self.o_frimg
        for it in self.frimg:
            out[p:p + 4] = struct.pack(e + "I", base + it.off)
            p += 4
        p = self.o_trindex
        for first, n in self.trees:
            out[p:p + 4] = struct.pack(e + "I", base + self.objects[first].off)
            p += 4
        trees = [objs[first:first + n] for first, n in self.trees]
        return bytes(out), trees, mem

    def addr(self, rtype, index, base):
        """What rsrc_gaddr(rtype, index) answers at `base` -- the donor's
        get_addr -- or None where it answers -1."""
        h = {R_OBJECT: (self.o_object, OBJ_SIZE),
             R_TEDINFO: (self.o_tedinfo, TED_SIZE),
             R_TEPTEXT: (self.o_tedinfo, TED_SIZE),
             R_ICONBLK: (self.o_iconblk, ICONBLK_SIZE),
             R_IBPMASK: (self.o_iconblk, ICONBLK_SIZE),
             R_BITBLK: (self.o_bitblk, BITBLK_SIZE),
             R_BIPDATA: (self.o_bitblk, BITBLK_SIZE),
             R_FRSTR: (self.o_frstr, 4),
             R_FRIMG: (self.o_frimg, 4)}
        if rtype == R_TREE:
            return base + self.objects[self.trees[index][0]].off
        if rtype == R_OBSPEC:
            return self.addr(R_OBJECT, index, base) + 12
        if rtype == R_TEPTMPLT:
            return self.addr(R_TEDINFO, index, base) + 4
        if rtype == R_TEPVALID:
            return self.addr(R_TEDINFO, index, base) + 8
        if rtype == R_IBPDATA:
            return self.addr(R_ICONBLK, index, base) + 4
        if rtype == R_IBPTEXT:
            return self.addr(R_ICONBLK, index, base) + 8
        if rtype == R_STRING:
            return base + self.frstr[index].off
        if rtype == R_IMAGEDATA:
            return base + self.frimg[index].off
        if rtype in h:
            off, size = h[rtype]
            return base + off + size * index
        return None

