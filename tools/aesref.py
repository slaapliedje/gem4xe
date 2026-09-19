#!/usr/bin/env python3
"""Host reference for the AES object library.

Mirrors src/aes/graf.c and src/aes/objc.c -- which in turn mirror EmuTOS's
gemgraf.c / gemgsxif.c / gemoblib.c / gemobed.c -- drawing through the same
tools/vdiref.py VDI the target draws through its own.  The AES gets no
private path to the screen on either side, which is what keeps the pixel
comparison meaningful; and because the reference issues the same VDI calls
in the same order, the attribute cache (gl_mode, gl_tcolor ...) and the
cursor nesting are checked too, not just the final picture.

The tree lives in host memory as `Obj`s, and everything an ob_spec points
at -- strings, TEDINFOs, BITBLKs, image bits, INDIRECT longs -- lives in a
`Layout`, which assigns the same addresses the harness pokes into the
target's scratch area.  `Text` is mutable so objc_edit can write back
through te_ptext, exactly as the target does.
"""
import contextlib
import struct

import gemdata
import vdiref
from vdiref import (V_PLINE, V_GTEXT, VSL_TYPE, VSL_WIDTH, VSL_COLOR,
                    VST_COLOR, VSF_INTERIOR, VSF_STYLE, VSF_COLOR, VSWR_MODE,
                    VQ_EXTND, VRO_CPYFM, VRT_CPYFM, VR_RECFL, VS_CLIP,
                    V_SHOW_C, V_HIDE_C, VSL_UDSTY, VST_HEIGHT,
                    VQ_MOUSE, V_STRING, VQ_KEY_S, VSC_FORM,
                    VEX_TIMV, VEX_BUTV, VEX_MOTV,
                    MD_REPLACE, MD_TRANS, MD_XOR,
                    FIS_HOLLOW, FIS_SOLID, FIS_PATTERN)

# graf_mouse's forms and commands (EmuTOS include/aesdefs.h)
ARROW, TEXT_CRSR, HOURGLASS, POINT_HAND = 0, 1, 2, 3
FLAT_HAND, THIN_CROSS, THICK_CROSS, OUTLN_CROSS = 4, 5, 6, 7
USER_DEF = 255
M_OFF, M_ON, M_SAVE, M_RESTORE, M_PREVIOUS = 256, 257, 258, 259, 260

# ob_type
G_BOX, G_TEXT, G_BOXTEXT, G_IMAGE = 20, 21, 22, 23
G_USERDEF, G_IBOX, G_BUTTON, G_BOXCHAR = 24, 25, 26, 27
G_STRING, G_FTEXT, G_FBOXTEXT, G_ICON, G_TITLE = 28, 29, 30, 31, 32
G_CICON = 33            # a colour icon: drawn as the ICONBLK its CICONBLK starts with
# ob_flags
NONE, SELECTABLE, DEFAULT, EXIT, EDITABLE = 0, 1, 2, 4, 8
RBUTTON, LASTOB, TOUCHEXIT, HIDETREE, INDIRECT = 0x10, 0x20, 0x40, 0x80, 0x100
# ob_state
NORMAL, SELECTED, CROSSED, CHECKED = 0, 1, 2, 4
DISABLED, OUTLINED, SHADOWED = 8, 0x10, 0x20
WHITEBAK = 0x40

NIL, ROOT, MAX_DEPTH, MAX_LEN = -1, 0, 8, 81
WHITE, BLACK, LWHITE, LBLACK = 0, 1, 8, 9
IP_HOLLOW, IP_4PATT, IP_SOLID = 0, 4, 7
IBM, SMALL = 3, 5
TE_LEFT, TE_RIGHT, TE_CNTR = 0, 1, 2
EDSTART, EDINIT, EDCHAR, EDEND = 0, 1, 2, 3
ESCAPE, BACKSPACE, TAB, RETURN = 0x011B, 0x0E08, 0x0F09, 0x1C0D
DELETE, UNDO, ENTER = 0x537F, 0x6100, 0x720D
ARROW_UP, ARROW_DOWN, ARROW_LEFT, ARROW_RIGHT = 0x4800, 0x5000, 0x4B00, 0x4D00

# evnt_multi flags
MU_KEYBD, MU_BUTTON, MU_M1, MU_M2, MU_MESAG, MU_TIMER = 1, 2, 4, 8, 16, 32
# form_dial
FMD_START, FMD_GROW, FMD_SHRINK, FMD_FINISH = 0, 1, 2, 3
# find_obj directions
FORWARD, BACKWARD, DEFLT = 0, 1, 2
# -- the window manager (wind.c) ------------------------------------------
NUM_WIN, NUM_ORECT, NUM_MSGS, NUM_ELEM = 8, 80, 16, 19
AP_MSGWORDS, AP_MSGBYTES = 8, 16      # src/aes/aes.h: a message
NUM_ACCS = 6                    # the Desk box's slots (src/aes/proc.h)
DESKWH = 0
VF_INUSE, VF_BROKEN, VF_ISOPEN = 1, 2, 4
WS_FULL, WS_CURR, WS_PREV, WS_WORK, WS_TRUE = 0, 1, 2, 3, 4
WC_BORDER, WC_WORK = 0, 1
END_UPDATE, BEG_UPDATE, END_MCTRL, BEG_MCTRL = 0, 1, 2, 3
# the active window's tree, W_TREE-relative
(W_BOX, W_TITLE, W_CLOSER, W_NAME, W_FULLER, W_INFO, W_DATA, W_WORK,
 W_SIZER, W_VBAR, W_UPARROW, W_DNARROW, W_VSLIDE, W_VELEV, W_HBAR,
 W_LFARROW, W_RTARROW, W_HSLIDE, W_HELEV) = range(NUM_ELEM)
# window kinds
NAME, CLOSER, FULLER, MOVER, INFO, SIZER = 1, 2, 4, 8, 0x10, 0x20
UPARROW, DNARROW, VSLIDE, LFARROW, RTARROW, HSLIDE = (0x40, 0x80, 0x100,
                                                      0x200, 0x400, 0x800)
# wind_get/wind_set fields
(WF_KIND, WF_NAME, WF_INFO, WF_WXYWH, WF_CXYWH, WF_PXYWH, WF_FXYWH,
 WF_HSLIDE, WF_VSLIDE, WF_TOP, WF_FIRSTXYWH, WF_NEXTXYWH, WF_RESVD,
 WF_NEWDESK, WF_HSLSIZ, WF_VSLSIZ, WF_SCREEN, WF_TATTRB, WF_SIZTOP,
 WF_OWNER) = range(1, 21)
WF_BOTTOM = 25
# messages
(WM_REDRAW, WM_TOPPED, WM_CLOSED, WM_FULLED, WM_ARROWED, WM_HSLID,
 WM_VSLID, WM_SIZED, WM_MOVED, WM_NEWTOP, WM_UNTOPPED, WM_ONTOP) = range(20, 32)
MN_SELECTED = 10
AC_OPEN, AC_CLOSE = 40, 41
# the menu tree's fixed objects (menu.c), and mn_do's states
THESCREEN, THEBAR, THEACTIVE, THEDESK = 0, 1, 2, 3
MENU_THICKNESS = 1
# sub-menus (src/aes/menu.c): the ROM's mark, and gem4xe's gap
SMI_BASE, NUM_SMI, SM_ARROW, SM_ARROWOFF = 128, 8, 0x03, 2
SM_GAP = 2 * MENU_THICKNESS
SUBMENU = 0x0800                # ob_flags: this item carries a menu
ME_INQUIRE, ME_ATTACH, ME_REMOVE = 0, 1, 2
MIS_INQUIRE, MIS_SET = 0, 1
START_STATE, INTITLE_STATE, INITEM_STATE, OUTSIDE_STATE = 1, 2, 3, 4
SUBMENU_STATE = 5
# WM_ARROWED's actions
(WA_UPPAGE, WA_DNPAGE, WA_UPLINE, WA_DNLINE, WA_LFPAGE, WA_RTPAGE,
 WA_LFLINE, WA_RTLINE) = range(8)
TGADGETS = NAME | CLOSER | FULLER | MOVER
VGADGETS = UPARROW | DNARROW | VSLIDE
HGADGETS = LFARROW | RTARROW | HSLIDE
MAX_COORDINATE = 10000      # the far edge of a drag's constraint
DROP_SHADOW_SIZE = 2
S_ONLY = 3                  # the vro_cpyfm mode bb_screen moves a window with
TOPPED_COLOR, UNTOPPED_COLOR, DESK_SPEC = 0x11A1, 0x1100, 0x00001143
# W_ACTIVE's object types and specs, in W_BOX.. order
GL_WATYPE = (G_IBOX, G_BOX, G_BOXCHAR, G_BOXTEXT, G_BOXCHAR, G_BOXTEXT,
             G_IBOX, G_IBOX, G_BOXCHAR, G_BOX, G_BOXCHAR, G_BOXCHAR, G_BOX,
             G_BOX, G_BOX, G_BOXCHAR, G_BOXCHAR, G_BOX, G_BOX)
GL_WASPEC = (0x00011101, 0x00011101, 0x05011101, None, 0x07011101, None,
             0x00001101, 0x00001101, 0x06011101, 0x00011101, 0x01011101,
             0x02011101, 0x00011111, 0x00011101, 0x00011101, 0x04011101,
             0x03011101, 0x00011111, 0x00011101)
# The reference's addresses for the AES's own TEDINFOs and their empty
# string: above 16 bits, where no Layout can put anything.
WM_ANAME, WM_AINFO, WM_EMPTY = 0x10000, 0x10001, 0x10002

OBJ_SIZE, TED_SIZE, BITBLK_SIZE = 24, 28, 14
INTIN_SIZE = 128            # the VDI's intin[]; expand_string clamps to it


def cdiv(a, b):
    """C integer division: truncates toward zero, unlike Python's floor."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _rng(spec):
    """Expand 'a..z' ranges into a set of byte values (see instr() below)."""
    out, i = set(), 0
    while i < len(spec):
        if i + 3 < len(spec) and spec[i + 1:i + 3] == '..':
            for c in range(ord(spec[i]), ord(spec[i + 3]) + 1):
                out.add(c)
            i += 4
        else:
            out.add(ord(spec[i]))
            i += 1
    return out


# The gemobed.c validation tables, byte for byte.
VALIDATE_N = "0..9A..Z \x80\x8e\x8f\x90\x92\x99\x9a\x9e\xa5\xb5\xb6\xb7\xb8\xc2..\xdc"
VALIDATE_A = VALIDATE_N[4:]
VALIDATE_n = "0..9a..zA..Z \x80..\xff"
VALIDATE_a = VALIDATE_n[4:]
VALIDATE_F = ":?*a..zA..Z0..9_\x80..\xff"
VALIDATE_f = VALIDATE_F[3:]
VALIDATE_P = ".?*a..zA..Z0..9_\\:\x80..\xff"
VALIDATE_p = VALIDATE_P[3:]


class Obj:
    def __init__(self, nxt, head, tail, typ, flags, state, spec, x, y, w, h):
        (self.ob_next, self.ob_head, self.ob_tail, self.ob_type, self.ob_flags,
         self.ob_state, self.ob_spec, self.ob_x, self.ob_y,
         self.ob_width, self.ob_height) = (nxt, head, tail, typ, flags, state,
                                           spec, x, y, w, h)

    def pack(self):
        return struct.pack("<hhhHHHIhhhh", self.ob_next, self.ob_head,
                           self.ob_tail, self.ob_type, self.ob_flags,
                           self.ob_state, self.ob_spec & 0xFFFFFFFF,
                           self.ob_x, self.ob_y, self.ob_width, self.ob_height)


class Text:
    """A NUL-terminated byte string in a buffer of `size` bytes (latin-1)."""

    def __init__(self, s, size=None):
        self.s = s
        self.size = size if size is not None else len(s) + 1
        assert len(s) < self.size, (s, size)

    def pack(self):
        b = self.s.encode("latin-1")
        return b + b"\0" * (self.size - len(b))


class Ted:
    def __init__(self, ptext, ptmplt, pvalid, font=IBM, just=TE_LEFT,
                 color=0x1180, thickness=0, txtlen=0, tmplen=0):
        self.ptext, self.ptmplt, self.pvalid = ptext, ptmplt, pvalid
        self.font, self.fontid, self.just, self.color = font, 0, just, color
        self.fontsize, self.thickness = 0, thickness
        self.txtlen, self.tmplen = txtlen, tmplen

    def pack(self):
        return struct.pack("<IIIhhhhhhhh", self.ptext, self.ptmplt, self.pvalid,
                           self.font, self.fontid, self.just, self.color,
                           self.fontsize, self.thickness, self.txtlen,
                           self.tmplen)


class Bitblk:
    def __init__(self, pdata, wb, hl, x=0, y=0, color=BLACK):
        self.pdata, self.wb, self.hl, self.x, self.y, self.color = \
            pdata, wb, hl, x, y, color

    def pack(self):
        return struct.pack("<Ihhhhh", self.pdata, self.wb, self.hl,
                           self.x, self.y, self.color)


class Iconblk:
    """ICONBLK, 34 bytes as in a .RSC: a mask, an image, a label, the
    char-and-colours word, and three rectangles relative to the object."""
    def __init__(self, pmask, pdata, ptext, char, xchar, ychar,
                 icon, text):
        self.pmask, self.pdata, self.ptext, self.char = pmask, pdata, ptext, char
        self.xchar, self.ychar = xchar, ychar
        self.icon, self.text = icon, text

    def pack(self):
        return struct.pack("<IIIhhhhhhhhhhh", self.pmask, self.pdata, self.ptext,
                           self.char, self.xchar, self.ychar,
                           self.icon.x, self.icon.y, self.icon.w, self.icon.h,
                           self.text.x, self.text.y, self.text.w, self.text.h)


class Layout:
    """Lays a tree and its ob_spec targets out at fixed addresses.

    The objects go first, at `base`; everything they point at follows,
    word aligned, in the order it is added.  `mem` maps address -> the
    Python object at it, which is what the AES model dereferences.
    """

    def __init__(self, base, max_objs=8):
        self.base = base
        self.mem = {}
        self.items = []
        self.next = base + OBJ_SIZE * max_objs
        self.max_objs = max_objs

    def _put(self, thing, blob):
        addr = self.next
        self.mem[addr] = thing
        self.items.append((addr, len(blob)))
        self.next += len(blob) + (len(blob) & 1)
        return addr

    def blob_of(self, thing):
        """The bytes an item occupies NOW -- a Text edited by objc_edit
        packs differently from when it was laid out."""
        if isinstance(thing, bytes):
            return thing
        if isinstance(thing, int):
            return struct.pack("<I", thing & 0xFFFFFFFF)
        return thing.pack()

    def text(self, s, size=None):
        t = Text(s, size)
        return self._put(t, t.pack())

    def ted(self, text, tmpl, valid, just=TE_LEFT, color=0x1180, thickness=0,
            font=IBM, txtlen=None):
        """A TEDINFO whose te_ptext buffer holds txtlen bytes (default: one
        per '_' in the template plus the NUL, as RCS would size it)."""
        if txtlen is None:
            txtlen = max(tmpl.count('_'), len(text)) + 1
        t = Ted(self.text(text, txtlen), self.text(tmpl), self.text(valid),
                font=font, just=just, color=color, thickness=thickness,
                txtlen=txtlen, tmplen=len(tmpl) + 1)
        return self._put(t, t.pack())

    def bitblk(self, rows, wb, hl, x=0, y=0, color=BLACK):
        """`rows` is the raw 1-plane image: hl rows of wb bytes, MSB first."""
        assert len(rows) == wb * hl, (len(rows), wb, hl)
        pdata = self._put(bytes(rows), bytes(rows))
        b = Bitblk(pdata, wb, hl, x, y, color)
        return self._put(b, b.pack())

    def iconblk(self, mask, data, label, char=0, xchar=0, ychar=0,
                icon=None, text=None, wb=4, hl=32):
        """An ICONBLK and the three things it points at.  `mask` and
        `data` are raw 1-plane images of hl rows of wb bytes."""
        assert len(mask) == wb * hl and len(data) == wb * hl
        pmask = self._put(bytes(mask), bytes(mask))
        pdata = self._put(bytes(data), bytes(data))
        ptext = self.text(label)
        icon = icon or Rect(0, 0, wb * 8, hl)
        text = text or Rect(0, hl, wb * 8, 8)
        ib = Iconblk(pmask, pdata, ptext, char, xchar, ychar, icon, text)
        return self._put(ib, ib.pack())

    def indirect(self, spec):
        return self._put(spec, struct.pack("<I", spec & 0xFFFFFFFF))

    def pack(self, objs):
        assert len(objs) <= self.max_objs
        blob = bytearray(self.next - self.base)
        tree = pack_tree(objs)
        blob[0:len(tree)] = tree
        for addr, size in self.items:
            b = self.blob_of(self.mem[addr])
            assert len(b) == size, (addr, len(b), size)
            o = addr - self.base
            blob[o:o + size] = b
        return bytes(blob)

    def addr_of(self, thing):
        for a, t in self.mem.items():
            if t is thing:
                return a
        raise KeyError(thing)


def pack_tree(objs):
    return b"".join(o.pack() for o in objs)


def crack(color):
    """gr_crack: border 15-12, text 11-8, mode bit 7, pattern 6-4, inside 3-0."""
    return ((color >> 12) & 0xF, (color >> 8) & 0xF,
            MD_REPLACE if (color & 0x80) else MD_TRANS,
            (color >> 4) & 7, color & 0xF)


class Rect:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x=0, y=0, w=0, h=0):
        self.x, self.y, self.w, self.h = x, y, w, h

    def copy(self):
        return Rect(self.x, self.y, self.w, self.h)

    def tuple(self):
        return (self.x, self.y, self.w, self.h)


class MOBLK:
    """A mouse rectangle for MU_M1/MU_M2: m_out says whether to wait for
    the pointer to leave it rather than enter it."""
    def __init__(self, m_out, x, y, w, h):
        self.m_out = m_out
        self.m_gr = Rect(x, y, w, h)


class PlanExhausted(Exception):
    """An event wait needed input and the op's plan had none left."""


def inside(x, y, pt):
    return pt.x <= x < pt.x + pt.w and pt.y <= y < pt.y + pt.h


def downorup(new, buparm):
    """The button-state test every waiter is phrased in: bit 24 flag
    (0 = wait to enter the state, 1 = to leave it), bits 15..8 the mask,
    bits 7..0 the state."""
    flag = (buparm >> 24) & 0xFF
    mask = (buparm >> 8) & 0xFF
    val = buparm & 0xFF
    return ((mask & (val ^ new)) == 0) != bool(flag)


def combine_cms(clicks, mask, state):
    return ((clicks & 0xFFFF) << 16) | ((mask & 0xFF) << 8) | (state & 0xFF)


def word(x):
    """A 16-bit two's-complement word, as the target's WORD arithmetic
    leaves it."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


# The dotted XOR line styles, phased by position (gemgraf.c).
HZTLTBL = (0x5555, 0xAAAA)
VERTTBL = (0x5555, 0xAAAA, 0xAAAA, 0x5555)
# Double-click rates in ms, index 0..4, the slowest first (gemevlib.c).
GL_DCRATES = (450, 330, 275, 220, 165)


# -- rectangles (graf.c) ----------------------------------------------------
def rc_intersect(p1, p2):
    """p2 = p1 & p2, written even when they do not meet; TRUE if they do."""
    tx = max(p2.x, p1.x)
    ty = max(p2.y, p1.y)
    tw = min(p2.x + p2.w, p1.x + p1.w)
    th = min(p2.y + p2.h, p1.y + p1.h)
    p2.x, p2.y, p2.w, p2.h = tx, ty, tw - tx, th - ty
    return tw > tx and th > ty


def rc_union(p1, p2):
    """p2 = the bounding box of p1 and p2."""
    tx = min(p1.x, p2.x)
    ty = min(p1.y, p2.y)
    tw = max(p1.x + p1.w, p2.x + p2.w)
    th = max(p1.y + p1.h, p2.y + p2.h)
    p2.x, p2.y, p2.w, p2.h = tx, ty, tw - tx, th - ty


def rc_equal(p1, p2):
    return p1.tuple() == p2.tuple()


def rc_constrain(pc, pt):
    """Move pt to lie inside pc (it keeps its size)."""
    if pt.x < pc.x:
        pt.x = pc.x
    if pt.y < pc.y:
        pt.y = pc.y
    if pt.x + pt.w > pc.x + pc.w:
        pt.x = word(pc.x + pc.w - pt.w)
    if pt.y + pt.h > pc.y + pc.h:
        pt.y = word(pc.y + pc.h - pt.h)


def mul_div(m1, m2, d1):
    return word(cdiv(m1 * m2, d1))


def mul_div_round(m1, m2, d1):
    """m1 * m2 / d1 rounded, with the donor's WORD truncation of the
    doubled quotient before the rounding step."""
    r = word(cdiv(m1 * m2 * 2, d1))
    return word((r - 1) >> 1 if r < 0 else (r + 1) >> 1)


class Window:
    """One of gl_win[]: the flags, kind, strings (addresses), slider
    settings, the full/work/previous rectangles, and the rectangle list
    in link order, with w_rnext the WF_NEXTXYWH cursor into it."""

    def __init__(self):
        self.w_flags = 0
        self.w_kind = 0
        # Who created it, for WF_OWNER.  This model runs ONE application,
        # so the answer is always its pid -- an accessory can own a
        # window on the target and nothing in the tree creates one.
        self.w_owner = 0
        self.w_pname = self.w_pinfo = WM_EMPTY
        self.w_hslide = self.w_vslide = 0
        self.w_hslsiz = self.w_vslsiz = -1
        self.w_full = Rect()
        self.w_work = Rect()
        self.w_prev = Rect()
        self.w_rlist = []
        self.w_rnext = 0


class OrectExhausted(Exception):
    """The rectangle pool ran out: the target would silently drop the
    piece (see wind.c mkpiece), so a case that gets here is a bad case."""


# -- fsel.c's string helpers (util/optimize.c, util/miscutil.c) -----------
def fs_fmt_str(name):
    """'SAMPLE.PRG' -> 'SAMPLE  PRG', 'TEST' -> 'TEST'."""
    if "." in name:
        stem, ext = name.split(".", 1)
        return stem[:8].ljust(8) + ext[:3]
    return name[:8]


def fs_unfmt_str(fmt):
    """The reverse: 'SAMPLE  PRG' -> 'SAMPLE.PRG'."""
    stem = fmt[:8].replace(" ", "")
    return stem + ("." + fmt[8:] if fmt[8:] else "")


def fs_wildcmp(pattern, name):
    """The name against the pattern, name and extension in turn."""
    pi = ni = 0
    for _ in range(2):
        while ni < len(name) and name[ni] != ".":
            p = pattern[pi] if pi < len(pattern) else ""
            if p == "*":
                ni += 1
                continue
            if p == "?" or p == name[ni]:
                pi += 1
                ni += 1
                continue
            return False
        while pi < len(pattern) and pattern[pi] in "*?":
            pi += 1
        if pi < len(pattern) and pattern[pi] == ".":
            pi += 1
        if ni < len(name) and name[ni] == ".":
            ni += 1
    return (pattern[pi] if pi < len(pattern) else "") == \
        (name[ni] if ni < len(name) else "")


def fs_drive_number(path):
    """0..7 for A..H at the front of the path, else -1."""
    if len(path) >= 2 and path[1] == ":":
        c = path[0].upper()
        if "A" <= c < chr(ord("A") + 8):
            return ord(c) - ord("A")
    return -1


def fs_back(path, pend=None):
    """-> (path, pos): back from `pend` to the last separator, or the
    colon of X: (a separator put in after it), or the start."""
    p = len(path) if pend is None else pend
    while p != 0:
        c = path[p] if p < len(path) else ""
        if c == "\\":
            break
        if c == ":" and p == 1:
            path = path[:2] + "\\" + path[2:]
            p = 2
            break
        p -= 1
    return path, p


def fs_pspec(path, pend=None):
    """-> (path, pos): the file part, after the last separator."""
    path, p = fs_back(path, pend)
    if p < len(path) and path[p] == "\\":
        p += 1
    return path, p


# The selector's flag on a name (fsel.c FS_FILE / FS_FOLDER): a listing
# entry is "NAME.EXT" for a file or FOLDER + "NAME" for a subdirectory.
FS_FILE, FS_FOLDER = " ", "\x07"


def fs_cioname(gem, dirsep=""):
    """The DOS seam's dos_cioname (src/sys/dos.c), which sh_cioname is:
    X:\\DIR\\NAME.EXT -> Dn:NAME.EXT on a flat DOS (the last component),
    Dn:>DIR>NAME.EXT on one with directories (`dirsep` its separator),
    uppercased, at most CIO_NAME_MAX (63) characters."""
    out = ""
    name = gem
    if len(gem) >= 3 and gem[1] == ":" and gem[2] == "\\":
        d = gem[0].lower()
        if "a" <= d <= "h":
            out = "D" + str(ord(d) - ord("a") + 1) + ":"
        name = gem[3:]
        out += dirsep
    if not dirsep:
        name = name.split("\\")[-1]
    return (out + name.upper().replace("\\", dirsep))[:63]


def fs_flagged(entry):
    """A listing entry -> (flag, name): a plain string is a file's."""
    if entry[:1] in (FS_FILE, FS_FOLDER):
        return entry[0], entry[1:]
    return FS_FILE, entry


def fs_entry(line):
    """A DOS 2 directory line -> NAME.EXT, FOLDER + NAME for a
    subdirectory, or None for a line that is not an entry (fsel.c's
    fs_entry): the deleted entry's dashes, the FREE SECTORS line, noise.
    The subdirectory marks are the DOS seam's (src/sys/dos.h): SpartaDOS
    X puts ':' in the second flag column and the directory's own
    extension after the name; SpartaDOS 3.2 puts "DIR" in inverse video
    (the high bits set) where the extension would be.  A DOS 2 line has
    neither."""
    ok = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_@")
    if len(line) < 17 or line[13] != " ":
        return None
    mark_ext = line[10:13] == "".join(chr(ord(c) | 0x80) for c in "DIR")
    folder = mark_ext or line[1] == ":"
    if not folder and line[1] != " ":
        return None
    name, ext = line[2:10].rstrip(), "" if mark_ext else line[10:13].rstrip()
    if not name or not "A" <= name[0] <= "Z":
        return None
    if any(c not in ok for c in name) or any(c not in ok for c in ext):
        return None
    return (FS_FOLDER if folder else "") + name + ("." + ext if ext else "")


class AES:
    """The object library over a vdiref.VDI.

    `tree` is a list of Obj; `mem` maps the addresses ob_spec/te_ptext/...
    hold to Text / Ted / Bitblk / bytes / int (INDIRECT).  Call gsx_start()
    at the point the script runs op 1000 -- after V_OPNWK/V_CLRWK -- so the
    attribute cache starts from the same VDI state on both sides.
    """

    def __init__(self, vdi, tree, mem):
        self.v = vdi
        self.tree = tree
        self.mem = mem
        self.intin = []
        self.gl_clip = Rect()
        # Edit state, static in objc.c
        self.g_rawstr = self.g_tmpstr = self.g_valstr = self.g_fmtstr = ""
        self.edblk = None
        # The input plan the event waits consume (see run()).
        self.plan = []
        # The screen at each ("shot",) step of a plan, in order: what the
        # harness screenshots inside an op, where a drop-down is showing.
        self.shots = []
        # GEMDOS's drive: the current one and the map Dsetdrv reports,
        # what the harness read from the DOS seam (src/sys/gemdos.c)
        self.dos_drive, self.dos_drvmap = 0, 1
        # ... and what its file calls see: where the far heap's first
        # Malloc lands (the gate derives it from the shell's brk), the
        # DTA's address and what the last search put in it, the
        # directories by their search path ("A:\\" -> [(name, attr, time,
        # date, size)] as gemdos.c gd_next lists the disk), and the
        # search Fsnext goes on with
        self.dos_brk = 0
        self.dos_dta = 0
        # whether the DOS the gate booted has a command processor a
        # program may hand a line to (Psystem, src/sys/dos.c): a
        # SpartaDOS X of 4.4 or later, which the gate says; a DOS 2 and
        # a SpartaDOS 3 have not
        self.psystem = False
        self.dos_dta_data = None
        self.dos_dirs = {}
        self.dos_searches = {}
        self.dos_files = {}             # by handle, while they are open
        # what a fresh directory's own entry says its length is: the gate
        # sets it from the filesystem it built the disk with (SDFS writes
        # the header entry, so 23), because a folder's size counts in the
        # window's information line and so in G
        self.dos_newdir = 0
        # shel_write's request, kept for the shell loop, and the shell
        # buffer shel_put/shel_get keep between programs (src/aes/shel.c
        # sh_init clears it)
        self.sh_doex = self.sh_isgr = 0
        self.sh_buf = bytearray(SIZE_SHELBUF)
        # What the last level-triggered button quick-out found (ev_wait):
        # the button's level and the screen, and how many turns in a row
        # the caller has taken on one held press.
        self.last_level = None
        self.held_turns = 0
        self.nbchange = 0
        # wind.c: the desktop tree form_dial(FMD_FINISH) redraws through,
        # until wm_init() builds the window manager's state
        self.gl_newdesk = None
        self.gl_newroot = 0
        self.ml_ocnt = 0
        self.ml_ctrl = Rect()
        # event.c: the message queue (mq_put), oldest first
        self.gl_queue = []
        self.ct_init()
        # fsel.c: the drives the selector can list ("D1:" -> [NAME.EXT]
        # as CIO's directory read yields them through fs_entry, or None
        # for a drive that does not answer), the drive buttons that are
        # live, and where the target's pool starts, which is where the
        # selector's tree is laid out (run(..., dirs=, pool=)).
        self.dirs = {}
        self.dos_dirsep = ""
        self.gl_drvbits = 0x00FF
        self.pool_mark = None
        # the strings the harness staged for the selector's buffers, by
        # address (run(..., buffers=)); fs_input leaves its results here
        self.fs_strings = {}
        self.fs_path_addr = self.rec_addr = 0

    # -- gemgsxif.c ---------------------------------------------------------
    def vcall(self, op, pts=(), ints=(), form=None):
        """A VDI call on the AES's own workstation -- gsx_call's
        contrl[6] = gl_handle -- so that an application's attributes and
        clip, on the virtual workstation it opened, and the AES's never
        disturb each other."""
        return self.v.call(op, pts, ints, form, handle=self.gl_handle)

    def gsx_start(self):
        v = self.v
        self.gl_mode = self.gl_tcolor = self.gl_lcolor = -1
        self.gl_fis = self.gl_patt = -1
        self.gl_moff = 0
        self.gl_mform = self.gl_pmform = self.gr_saved = None
        # the workstation vdi_init opened: the AES draws on the device
        # itself, an application on a virtual one
        self.gl_handle = vdiref.VDI_PHYS_HANDLE
        self.vcall(VQ_EXTND, (), (0,))
        self.gl_width = v.intout[0] + 1
        self.gl_height = v.intout[1] + 1
        wpixel, hpixel = v.intout[3], v.intout[4]
        self.vcall(VQ_EXTND, (), (1,))
        self.gl_nplanes = v.intout[4]
        self.vcall(VST_HEIGHT, (0, 0), ())
        (self.gl_wptschar, self.gl_hptschar,
         self.gl_wchar, self.gl_hchar) = v.ptsout[0:4]
        self.gl_hbox = self.gl_hchar + 3
        self.gl_wbox = cdiv(self.gl_hbox * hpixel, wpixel)
        if self.gl_wbox < self.gl_wchar + 4:
            self.gl_wbox = self.gl_wchar + 4
        self.vcall(VSL_TYPE, (), (7,))
        self.vcall(VSL_WIDTH, (1, 0), ())
        self.vcall(VSL_UDSTY, (), (0xFFFF,))
        w, h = self.gl_width, self.gl_height
        self.gl_rscreen = Rect(0, 0, w, h)
        self.gl_rfull = Rect(0, self.gl_hbox, w, h - self.gl_hbox)
        self.gl_rcenter = Rect((w - self.gl_wbox) // 2,
                               (h - 2 * self.gl_hbox) // 2,
                               self.gl_wbox, self.gl_hbox)
        self.gl_rmenu = Rect(0, 0, w, self.gl_hbox)
        self.gsx_sclip(Rect(0, 0, w + 1, h + 1))

    def gsx_moff(self):
        if not self.gl_moff:
            self.vcall(V_HIDE_C)
        self.gl_moff += 1

    def gsx_mon(self):
        self.gl_moff -= 1
        if not self.gl_moff:
            self.vcall(V_SHOW_C, (), (1,))

    def gsx_mforce(self):
        """The pointer shown whatever the hide count, which is returned
        for gsx_munforce to put back (the menu's ct_mouse)."""
        old = self.gl_moff
        if old:
            self.vcall(V_SHOW_C, (), (0,))
            self.gl_moff = 0
        return old

    def gsx_munforce(self, old):
        if old:
            self.gsx_moff()
            self.gl_moff = old

    def ratinit(self):
        """The pointer on whatever the count, unconditionally: what the
        shell does before each program (src/aes/shel.c sh_main)."""
        self.vcall(V_SHOW_C, (), (0,))
        self.gl_moff = 0

    def gsx_attr(self, text, mode, color):
        if mode != self.gl_mode:
            self.vcall(VSWR_MODE, (), (mode,))
            self.gl_mode = mode
        if text:
            if color != self.gl_tcolor:
                self.vcall(VST_COLOR, (), (color,))
                self.gl_tcolor = color
        elif color != self.gl_lcolor:
            self.vcall(VSL_COLOR, (), (color,))
            self.gl_lcolor = color

    def gsx_fcolor(self, color):
        self.vcall(VSF_COLOR, (), (color,))

    def gsx_sclip(self, pt):
        self.gl_clip = pt.copy()
        if pt.w and pt.h:
            self.vcall(VS_CLIP, (pt.x, pt.y, pt.x + pt.w - 1,
                                  pt.y + pt.h - 1), (1,))
        else:
            self.vcall(VS_CLIP, (0, 0, 0, 0), (0,))

    def gsx_gclip(self):
        return self.gl_clip.copy()

    def gsx_chkclip(self, pt):
        c = self.gl_clip
        if c.w and c.h:
            if pt.y + pt.h < c.y or pt.x + pt.w < c.x:
                return False
            if c.y + c.h <= pt.y or c.x + c.w <= pt.x:
                return False
        return True

    def gsx_box(self, pt):
        x, y = pt.x, pt.y
        x2, y2 = x + pt.w - 1, y + pt.h - 1
        self.vcall(V_PLINE, (x, y, x2, y, x2, y2, x, y2, x, y), ())

    def gsx_cline(self, x1, y1, x2, y2):
        self.gsx_moff()
        self.vcall(V_PLINE, (x1, y1, x2, y2), ())
        self.gsx_mon()

    # -- the XOR rubber lines (gemgraf.c) ---------------------------------
    def gsx_xline(self, pts):
        """A polyline of dotted XOR segments, each phased by the parity
        of its own position so two draws cancel over any stipple."""
        v = self.v
        for i in range(0, len(pts) - 2, 2):
            x1, y1, x2, y2 = pts[i:i + 4]
            if x1 == x2:
                st = VERTTBL[(x1 & 1) | ((y1 & 1) << 1)]
            else:
                yl = y1 if x1 < x2 else y2
                st = HZTLTBL[yl & 1]
            self.vcall(VSL_UDSTY, (), (st,))
            self.vcall(V_PLINE, (x1, y1, x2, y2), ())
        self.vcall(VSL_UDSTY, (), (0xFFFF,))

    def gsx_xbox(self, pt):
        x, y = pt.x, pt.y
        x2, y2 = x + pt.w - 1, y + pt.h - 1
        self.gsx_xline((x, y, x2, y, x2, y2, x, y2, x, y))

    def gsx_xcbox(self, pt):
        """Just the corners, each arm two box cells long."""
        wa, ha = 2 * self.gl_wbox, 2 * self.gl_hbox
        x1, y1 = pt.x, pt.y
        x2, y2 = pt.x + pt.w - 1, pt.y + pt.h - 1
        self.gsx_xline((x1, y1 + ha, x1, y1, x1 + wa, y1))
        self.gsx_xline((x2 + 1 - wa, y1, x2, y1, x2, y1 + ha))
        self.gsx_xline((x2, y2 + 1 - ha, x2, y2, x2 + 1 - wa, y2))
        self.gsx_xline((x1 + wa, y2, x1, y2, x1, y2 + 1 - ha))

    # -- input through the VDI --------------------------------------------
    def gsx_mouse(self):
        """(buttons, x, y) from vq_mouse."""
        v = self.v
        self.vcall(VQ_MOUSE)
        return v.intout[0], v.ptsout[0], v.ptsout[1]

    def gsx_kstate(self):
        self.vcall(VQ_KEY_S)
        return self.v.intout[0]

    def gsx_getkey(self):
        """One key from the VDI's queue, or None (v_string, one key per
        call on this driver)."""
        v = self.v
        self.vcall(V_STRING, (0, 0), (1, 0))
        if v.contrl4 == 0:
            return None
        return v.intout[0]

    def gsx_tblt(self, font, x, y, nc):
        y += self.gl_hptschar
        self.vcall(V_GTEXT, (x, y), self.intin[:nc])

    def gsx_tcalc(self, font, text, w, h):
        n = self.expand_string(text)
        w = min(w, n * self.gl_wchar)
        h = min(h, self.gl_hchar)
        n = min(n, cdiv(w, self.gl_wchar)) if cdiv(h, self.gl_hchar) else 0
        return w, h, n

    def gsx_blt(self, form, sx, sy, dx, dy, w, h, rule, fg, bg):
        """form is the raw 1-plane bits at fd_addr; fd_wdwidth = (w/8)/2."""
        self.gsx_moff()
        pts = (sx, sy, sx + w - 1, sy + h - 1, dx, dy, dx + w - 1, dy + h - 1)
        wdwidth = cdiv(cdiv(w, 8), 2)
        if fg == -1:
            raise NotImplementedError("vro_cpyfm from a memory form")
        self.vcall(VRT_CPYFM, pts, (rule, fg, bg), (form, wdwidth))
        self.gsx_mon()

    # -- gemgraf.c ----------------------------------------------------------
    @staticmethod
    def gr_inside(pt, th):
        pt.x += th
        pt.y += th
        pt.w -= 2 * th
        pt.h -= 2 * th

    def gr_box(self, x, y, w, h, th):
        t = Rect(x, y, w, h)
        if th != 0:
            if th < 0:
                th -= 1
            self.gsx_moff()
            while True:
                th += -1 if th > 0 else 1
                n = t.copy()
                self.gr_inside(n, th)
                self.gsx_box(n)
                if th == 0:
                    break
            self.gsx_mon()

    def bb_fill(self, mode, fis, patt, x, y, w, h):
        self.gsx_attr(True, mode, self.gl_tcolor)
        if fis != self.gl_fis:
            self.vcall(VSF_INTERIOR, (), (fis,))
            self.gl_fis = fis
        if patt != self.gl_patt:
            self.vcall(VSF_STYLE, (), (patt,))
            self.gl_patt = patt
        self.vcall(VR_RECFL, (x, y, x + w - 1, y + h - 1), ())

    def gr_rect(self, icol, ipat, pt):
        fis = FIS_PATTERN
        if ipat == IP_HOLLOW:
            fis = FIS_HOLLOW
        elif ipat == IP_SOLID:
            fis = FIS_SOLID
        self.gsx_fcolor(icol)
        self.bb_fill(MD_REPLACE, fis, ipat, pt.x, pt.y, pt.w, pt.h)

    def expand_string(self, text):
        """Stage `text` into intin[] as byte values; returns its length."""
        codes = [ord(c) & 0xFF for c in text][:INTIN_SIZE - 1]
        self.intin = codes
        return len(codes)

    def gr_just(self, just, font, text, w, h, pt):
        pt.w, pt.h = w, h
        pt.w, pt.h, n = self.gsx_tcalc(font, text, pt.w, pt.h)
        h -= pt.h
        if h > 0:
            pt.y += cdiv(h + 1, 2)
        w -= pt.w
        if w > 0:
            if just == TE_RIGHT:
                pt.x += w
            elif just == TE_CNTR:
                pt.x += cdiv(w + 1, 2)
        return n

    def gr_gtext(self, just, font, text, pt):
        t = pt.copy()
        n = self.gr_just(just, font, text, t.w, t.h, t)
        if n > 0:
            self.gsx_tblt(font, t.x, t.y, n)

    # -- gemobjop.c / gemoblib.c ------------------------------------------
    def ob_getspec(self, obj):
        o = self.tree[obj]
        spec = o.ob_spec
        if o.ob_flags & INDIRECT:
            spec = self.mem[spec]
        return spec & 0xFFFFFFFF

    def ob_sst(self, obj):
        """Returns (state, type, flags, spec, th, ch)."""
        o = self.tree[obj]
        spec = self.ob_getspec(obj)
        typ = o.ob_type & 0xFF
        th, ch = 0, 0
        if typ == G_TITLE:
            th = 1
        elif typ in (G_TEXT, G_BOXTEXT, G_FTEXT, G_FBOXTEXT):
            th = self.mem[spec].thickness
        elif typ in (G_BOX, G_BOXCHAR, G_IBOX):
            th = (spec >> 16) & 0xFF
            if th >= 0x80:
                th -= 0x100
            ch = (spec >> 24) & 0xFF
        elif typ == G_BUTTON:
            th = -1
            if o.ob_flags & EXIT:
                th -= 1
            if o.ob_flags & DEFAULT:
                th -= 1
        return o.ob_state, typ, o.ob_flags, spec, th, ch

    def ob_get_par(self, obj):
        if obj == ROOT:
            return NIL
        pobj = self.tree[obj].ob_next
        while self.tree[pobj].ob_tail != obj:
            obj = pobj
            pobj = self.tree[obj].ob_next
        return pobj

    @staticmethod
    def _ob_get_prev(tree, parent, obj):
        pobj = tree[parent].ob_head
        if pobj == obj:
            return NIL
        while True:
            nobj = tree[pobj].ob_next
            if nobj == obj:
                return pobj
            if nobj == parent:
                return NIL
            pobj = nobj

    def ob_offset(self, obj):
        x = y = 0
        while True:
            o = self.tree[obj]
            x += o.ob_x
            y += o.ob_y
            obj = self.ob_get_par(obj)
            if obj == NIL:
                break
        return x, y

    def ob_actxywh(self, obj):
        x, y = self.ob_offset(obj)
        o = self.tree[obj]
        return Rect(x, y, o.ob_width, o.ob_height)

    def ob_relxywh(self, obj):
        o = self.tree[obj]
        return Rect(o.ob_x, o.ob_y, o.ob_width, o.ob_height)

    def ob_format(self, just, raw, tmpl):
        """Returns (raw, fmt): raw is emptied when it begins with '@'."""
        if raw[:1] == '@':
            raw = ''
        out = [''] * len(tmpl)
        if just == TE_RIGHT:
            ti, ri, step = len(tmpl) - 1, len(raw) - 1, -1
        else:
            ti, ri, step = 0, 0, 1
        while 0 <= ti < len(tmpl):
            c = tmpl[ti]
            if c != '_':
                out[ti] = c
            elif 0 <= ri < len(raw):
                out[ti] = raw[ri]
                ri += step
            else:
                out[ti] = '_'
            ti += step
        return raw, ''.join(out)

    def just_draw(self, obj, sx, sy):
        state, typ, flags, spec, th, ch = self.ob_sst(obj)
        o = self.tree[obj]
        if (flags & HIDETREE) or spec == 0xFFFFFFFF:
            return
        t = Rect(sx, sy, o.ob_width, o.ob_height)
        # Trivial reject against the clip
        c = t.copy()
        if state & OUTLINED:
            self.gr_inside(c, -3)
        else:
            self.gr_inside(c, 3 * th if th < 0 else -3 * th)
        if not self.gsx_chkclip(c):
            return
        bcol, tcol, ipat, icol, tmode = BLACK, BLACK, IP_HOLLOW, WHITE, MD_REPLACE
        tmpth = 0
        ted = None
        if typ != G_STRING:
            tmpth = th if th > 0 else 0
            if typ in (G_TEXT, G_BOXTEXT, G_FTEXT, G_FBOXTEXT):
                ted = self.mem[spec]
                bcol, tcol, tmode, ipat, icol = crack(ted.color)
            elif typ in (G_BOX, G_BOXCHAR, G_IBOX):
                bcol, tcol, tmode, ipat, icol = crack(spec & 0xFFFF)
            if typ in (G_BOX, G_BOXCHAR, G_IBOX, G_BUTTON, G_BOXTEXT,
                       G_FBOXTEXT):
                if th != 0:
                    self.gsx_attr(False, MD_REPLACE, bcol)
                    self.gr_box(t.x, t.y, t.w, t.h, th)
                if typ != G_IBOX:
                    self.gr_inside(t, tmpth)
                    self.gr_rect(icol, ipat, t)
                    self.gr_inside(t, -tmpth)
        self.gsx_attr(True, tmode, tcol)
        # Text objects
        if typ in (G_FTEXT, G_FBOXTEXT):
            raw = self.mem[ted.ptext].s
            tmpl = self.mem[ted.ptmplt].s
            raw, fmt = self.ob_format(ted.just, raw, tmpl)   # a copy: te_ptext is untouched
            self._gtext(ted.just, ted.font, fmt, t, tmpth)
        elif typ == G_BOXCHAR:
            text = chr(ch) if ch else ''
            self._gtext(TE_CNTR, IBM, text, t, tmpth)
        elif typ in (G_TEXT, G_BOXTEXT):
            self._gtext(ted.just, ted.font, self.mem[ted.ptext].s, t, tmpth)
        elif typ == G_IMAGE:
            bi = self.mem[spec]
            self.gsx_blt(self.mem[bi.pdata], bi.x, bi.y, t.x, t.y,
                         bi.wb * 8, bi.hl, MD_TRANS, bi.color, WHITE)
        elif typ in (G_ICON, G_CICON):
            # the donor's gr_gicon (gemgraf.c): the mask under the image,
            # both transparent, then the character and the label.  A
            # G_CICON draws its mono form: its spec is the ICONBLK a
            # CICONBLK begins with (src/aes/rsrc.c, rs_cicons)
            ib = self.mem[spec]
            fg, bg, ch = (ib.char >> 12) & 15, (ib.char >> 8) & 15, ib.char & 0xFF
            if state & SELECTED:
                fg, bg = bg, fg
            pi = Rect(ib.icon.x + t.x, ib.icon.y + t.y, ib.icon.w, ib.icon.h)
            pl = Rect(ib.text.x + t.x, ib.text.y + t.y, ib.text.w, ib.text.h)
            label = self.mem[ib.ptext].s
            if not ((state & WHITEBAK) and bg == WHITE):
                self.gsx_blt(self.mem[ib.pmask], 0, 0, pi.x, pi.y, pi.w, pi.h,
                             MD_TRANS, bg, fg)
                if label:
                    self.gr_rect(bg, IP_SOLID, pl)
            self.gsx_blt(self.mem[ib.pdata], 0, 0, pi.x, pi.y, pi.w, pi.h,
                         MD_TRANS, fg, bg)
            self.gsx_attr(True, MD_TRANS, fg)
            if ch:
                self.intin = [ch]
                self.gsx_tblt(SMALL, pi.x + ib.xchar, pi.y + ib.ychar, 1)
            if label:
                self.gr_gtext(TE_CNTR, SMALL, label, pl)
            state &= ~SELECTED      # spent: no XOR at the end (gr_gicon)
        elif typ in (G_STRING, G_TITLE, G_BUTTON):
            n = self.expand_string(self.mem[spec].s)
            if n:
                self.gsx_attr(True, MD_TRANS, BLACK)
                y = t.y + cdiv(t.h - self.gl_hchar, 2)
                x = t.x
                if typ == G_BUTTON:
                    x += cdiv(t.w - n * self.gl_wchar, 2)
                self.gsx_tblt(IBM, x, y, n)
        # Outline
        if state & OUTLINED:
            self.gsx_attr(False, MD_REPLACE, BLACK)
            self.gr_box(t.x - 3, t.y - 3, t.w + 6, t.h + 6, 1)
            self.gsx_attr(False, MD_REPLACE, WHITE)
            self.gr_box(t.x - 2, t.y - 2, t.w + 4, t.h + 4, 2)
        if th > 0:
            self.gr_inside(t, th)
        else:
            th = -th
        if (state & SHADOWED) and th:
            self.gsx_fcolor(bcol)
            self.bb_fill(MD_REPLACE, FIS_SOLID, 0, t.x, t.y + t.h + th,
                         t.w + th, 2 * th)
            self.bb_fill(MD_REPLACE, FIS_SOLID, 0, t.x + t.w + th, t.y,
                         2 * th, t.h + 3 * th)
        if state & CHECKED:
            self.gsx_attr(True, MD_TRANS, BLACK)
            self.intin = [8]
            self.gsx_tblt(IBM, t.x + 2, t.y, 1)
        if state & CROSSED:
            self.gsx_attr(False, MD_TRANS, WHITE)
            self.gsx_cline(t.x, t.y, t.x + t.w - 1, t.y + t.h - 1)
            self.gsx_cline(t.x, t.y + t.h - 1, t.x + t.w - 1, t.y)
        if state & DISABLED:
            self.gsx_fcolor(WHITE)
            self.bb_fill(MD_TRANS, FIS_PATTERN, IP_4PATT, t.x, t.y, t.w, t.h)
        if state & SELECTED:
            self.bb_fill(MD_XOR, FIS_SOLID, IP_SOLID, t.x, t.y, t.w, t.h)

    def _gtext(self, just, font, text, t, tmpth):
        c = t.copy()
        self.gr_inside(c, tmpth)
        self.gr_gtext(just, font, text, c)

    def everyobj(self, this, last, routine, sx, sy, maxdep):
        tree = self.tree
        x = [0] * (MAX_DEPTH + 2)
        y = [0] * (MAX_DEPTH + 2)
        x[0], y[0] = sx, sy
        depth = 1
        while True:
            if this == last:
                return
            x[depth] = x[depth - 1] + tree[this].ob_x
            y[depth] = y[depth - 1] + tree[this].ob_y
            routine(this, x[depth], y[depth])
            head = tree[this].ob_head
            if (head != NIL and not (tree[this].ob_flags & HIDETREE)
                    and depth <= maxdep):
                depth += 1
                this = head
                continue
            while True:
                tmp = tree[this].ob_next
                if tmp == last or this == ROOT:
                    return
                if tree[tmp].ob_tail != this:
                    this = tmp
                    break
                depth -= 1
                this = tmp

    def ob_draw(self, obj, depth):
        last = NIL if obj == ROOT else self.tree[obj].ob_next
        pobj = self.ob_get_par(obj)
        sx, sy = self.ob_offset(pobj) if pobj != NIL else (0, 0)
        self.gsx_moff()
        self.everyobj(obj, last, self.just_draw, sx, sy, depth)
        self.gsx_mon()

    def ob_find(self, currobj, depth, mx, my):
        tree = self.tree
        lastfound = NIL
        dosibs = False
        parent = self.ob_get_par(currobj)
        ox, oy = self.ob_offset(parent) if parent != NIL else (0, 0)
        while currobj != NIL and depth >= 0:
            o = tree[currobj]
            t = Rect(o.ob_x + ox, o.ob_y + oy, o.ob_width, o.ob_height)
            if (not (o.ob_flags & HIDETREE) and
                    t.x <= mx < t.x + t.w and t.y <= my < t.y + t.h):
                lastfound = currobj
                if o.ob_tail != NIL and depth:
                    depth -= 1
                    parent = currobj
                    ox, oy = t.x, t.y
                    currobj = o.ob_tail
                    dosibs = True
                    continue
                break
            if dosibs and lastfound != NIL:
                currobj = self._ob_get_prev(tree, parent, currobj)
            else:
                currobj = NIL
        return lastfound

    def ob_center(self):
        root = self.tree[ROOT]
        wd, hd = root.ob_width, root.ob_height
        xd = cdiv(self.gl_width - wd, 2)
        yd = self.gl_hbox + cdiv(self.gl_height - self.gl_hbox - hd, 2)
        root.ob_x, root.ob_y = xd, yd
        if root.ob_state & OUTLINED:
            xd = max(xd - 3, 0)
            yd = max(yd - 3, 0)
            wd += 6
            hd += 6
        if root.ob_state & SHADOWED:
            th = self.ob_sst(ROOT)[4]
            th = -th if th < 0 else th
            wd += 2 * th
            hd += 2 * th
        return xd, yd, wd, hd

    # -- gemobed.c ----------------------------------------------------------
    @staticmethod
    def find_pos(s, pos):
        i = 0
        while pos > 0 and i < len(s):
            if s[i] == '_':
                pos -= 1
            i += 1
        while i < len(s) and s[i] != '_':
            i += 1
        return i

    @staticmethod
    def scan_to_end(s, start, idx, chr_):
        i = start
        while i < len(s) and s[i] != chr_:
            if s[i] == '_':
                idx += 1
            i += 1
        return idx

    @staticmethod
    def instr(ch, spec):
        return ch in _rng(spec)

    @staticmethod
    def check(ch, valchar):
        """Returns (ok, ch) -- the char may be upcased."""
        def up(c):
            return c - 32 if ord('a') <= c <= ord('z') else c
        tbl = {'9': ("0..9", False), 'A': (VALIDATE_A, True),
               'N': (VALIDATE_N, True), 'a': (VALIDATE_a, False),
               'n': (VALIDATE_n, False), 'F': (VALIDATE_F, True),
               'f': (VALIDATE_f, True), 'P': (VALIDATE_P, True),
               'p': (VALIDATE_p, True)}
        if valchar == 'X':
            return True, ch
        if valchar == 'x':
            return True, up(ch)
        if valchar in tbl:
            spec, upcase = tbl[valchar]
            if upcase:
                ch = up(ch)
            return AES.instr(ch, spec), ch
        return False, ch

    def pxl_rect(self, obj, ch_pos):
        o = self.ob_actxywh(obj)
        self.gr_just(self.edblk.just, self.edblk.font,
                     self.mem[self.edblk.ptmplt].s, o.w, o.h, o)
        return Rect(o.x + ch_pos * self.gl_wchar, o.y,
                    self.gl_wchar, self.gl_hchar)

    def curfld(self, obj, cur_pos, dist):
        t = self.pxl_rect(obj, cur_pos)
        if dist:
            t.w += (dist - 1) * self.gl_wchar
        else:
            self.gsx_attr(False, MD_XOR, BLACK)
            t.y -= 3
            t.h += 6
        oc = self.gsx_gclip()
        self.gsx_sclip(t)
        if dist:
            self.ob_draw(obj, 0)
        else:
            self.gsx_cline(t.x, t.y, t.x, t.y + t.h - 1)
        self.gsx_sclip(oc)

    def ob_stfn(self, idx):
        return (self.find_pos(self.g_tmpstr, idx),
                self.find_pos(self.g_tmpstr, len(self.g_rawstr)))

    def ob_delit(self, idx):
        if idx < len(self.g_rawstr):
            self.g_rawstr = self.g_rawstr[:idx] + self.g_rawstr[idx + 1:]
            return 0
        return 1

    @staticmethod
    def ins_char(s, pos, ch, tot_len):
        n = len(s)
        s = s[:pos] + ch + s[pos:]
        return s[:n + 1] if n + 1 < tot_len else s[:tot_len - 1]

    def ob_edit(self, obj, in_char, idx, kind):
        """Returns (idx, ret) -- the out-idx and the function result."""
        if kind == EDSTART or obj <= 0:
            return idx, 1
        spec = self.ob_getspec(obj)
        self.edblk = ed = self.mem[spec]
        ptext = self.mem[ed.ptext]
        self.g_tmpstr = self.mem[ed.ptmplt].s
        self.g_rawstr = ptext.s
        # The validation string is extended to the template's length by
        # repeating its LAST character (gemobed.c), so "9" governs everywhere.
        vs = self.mem[ed.pvalid].s
        while vs and len(vs) < ed.tmplen and len(vs) < MAX_LEN - 1:
            vs += vs[-1]
        self.g_valstr = vs
        self.g_rawstr, self.g_fmtstr = self.ob_format(ed.just, self.g_rawstr,
                                                     self.g_tmpstr)
        txtlen = ed.txtlen
        if kind == EDINIT:
            idx = len(self.g_rawstr)
        elif kind == EDCHAR:
            no_redraw = True
            start, finish = self.ob_stfn(idx)
            cur_pos = start
            self.curfld(obj, cur_pos, 0)
            if in_char == BACKSPACE:
                if idx > 0:
                    idx -= 1
                    no_redraw = bool(self.ob_delit(idx))
            elif in_char == ESCAPE:
                idx = 0
                self.g_rawstr = ''
                no_redraw = False
            elif in_char == DELETE:
                if idx <= txtlen - 2:
                    no_redraw = bool(self.ob_delit(idx))
            elif in_char == ARROW_LEFT:
                if idx > 0:
                    idx -= 1
            elif in_char == ARROW_RIGHT:
                if idx < len(self.g_rawstr):
                    idx += 1
            else:
                tmp_back = False
                if idx > txtlen - 2:
                    cur_pos -= 1
                    start = cur_pos
                    tmp_back = True
                    idx -= 1
                bin_ = in_char & 0xFF
                if bin_:
                    vc = self.g_valstr[idx] if idx < len(self.g_valstr) else '\0'
                    ok, bin_ = self.check(bin_, vc)
                    if ok:
                        self.g_rawstr = self.ins_char(self.g_rawstr, idx,
                                                      chr(bin_), txtlen)
                        idx += 1
                        no_redraw = False
                    else:
                        if tmp_back:
                            idx += 1
                            cur_pos += 1
                        pos = self.scan_to_end(self.g_tmpstr, cur_pos, idx,
                                               chr(bin_))
                        if pos < txtlen - 2:
                            r = self.g_rawstr
                            r = r[:idx] + ' ' * (pos - idx)
                            self.g_rawstr = r[:pos]
                            idx = pos
                            no_redraw = False
            ptext.s = self.g_rawstr
            if not no_redraw:
                self.g_rawstr, self.g_fmtstr = self.ob_format(
                    ed.just, self.g_rawstr, self.g_tmpstr)
                new_start, new_finish = self.ob_stfn(idx)
                start = min(start, new_start)
                dist = max(finish, new_finish) - start
                if dist:
                    self.curfld(obj, start, dist)
        cur_pos = self.find_pos(self.g_tmpstr, idx)
        self.curfld(obj, cur_pos, 0)
        return idx, 1

    # -- the public entry points the runner ops map onto ------------------
    def draw(self, start, depth, clip):
        """objc_draw: op 1042, ptsin clip (x,y,w,h), intin (start, depth)."""
        self.gsx_sclip(Rect(*clip))
        self.ob_draw(start, depth)

    def find(self, start, depth, mx, my):
        """objc_find: op 1043."""
        return self.ob_find(start, depth, mx, my)

    def offset(self, obj):
        """objc_offset: op 1044."""
        return self.ob_offset(obj)

    def edit(self, obj, kchar, idx, kind):
        """objc_edit: op 1046 -> (idx, ret)."""
        self.gsx_sclip(self.gl_rfull)
        return self.ob_edit(obj, kchar, idx, kind)

    def change(self, obj, clip, newstate, redraw):
        """objc_change: op 1047."""
        self.gsx_sclip(Rect(*clip))
        self.ob_change(obj, newstate, redraw)

    def ob_change(self, obj, newstate, redraw):
        state, typ, flags, spec, th, ch = self.ob_sst(obj)
        if state == newstate or spec == 0xFFFFFFFF:
            return
        o = self.tree[obj]
        o.ob_state = newstate
        if not redraw:
            return
        x, y = self.ob_offset(obj)
        self.gsx_moff()
        th = th if th > 0 else 0
        if typ not in (G_ICON, G_CICON, G_USERDEF) and ((newstate ^ state) & SELECTED):
            self.bb_fill(MD_XOR, FIS_SOLID, IP_SOLID, x + th, y + th,
                         o.ob_width - 2 * th, o.ob_height - 2 * th)
            redraw = False
        if redraw:
            self.just_draw(obj, x, y)
        self.gsx_mon()

    def center(self):
        """form_center: op 1054 -> (x, y, w, h)."""
        return self.ob_center()

    # -- event.c: the mouse, buttons, keyboard and timer ------------------
    # Mirrors src/aes/event.c state for state.  The waits pull input from
    # self.plan through _step(), one frame at a time, the way the harness
    # feeds the target.

    def ev_init(self):
        v = self.v
        self.mtrans = 0
        self.mclick = self.pr_mclick = 0
        self.gl_bdely = self.gl_bpend = self.gl_bclick = 0
        self.bw_active = self.bw_done = False
        self.bw_parm = self.bw_want = self.bw_clicks = 0
        self.gl_ticks = 0
        self.gl_queue = []
        self.ct_init()
        self.vcall(VEX_TIMV)
        v.vec_timv = self.ev_timv
        self.gl_ticktime = max(v.intout[0], 1)
        self.vcall(VEX_BUTV)
        v.vec_butv = self.ev_butv
        self.vcall(VEX_MOTV)
        v.vec_motv = self.ev_motv
        b, x, y = self.gsx_mouse()
        self.xrat = self.pr_xrat = x
        self.yrat = self.pr_yrat = y
        self.button = self.pr_button = b
        self.gl_btrue = self.gl_bdesired = b
        self.kstate = self.gsx_kstate()
        self.ev_dclick(3, True)

    def ev_dclick(self, rate, setit):
        if setit:
            rate = max(0, min(rate, 4))
            self.gl_dcindex = rate
            self.gl_dclick = GL_DCRATES[rate] // self.gl_ticktime
        return self.gl_dcindex

    def in_mrect(self, pmo):
        return pmo.m_out != inside(self.xrat, self.yrat, pmo.m_gr)

    def bchange(self, new, clicks):
        if (not self.gl_ctmown and new == 1 and self.button == 0
                and not self.ct_inside):
            self.ct_owns = self.ct_chkown(self.xrat, self.yrat) < 0
            if self.ct_owns:
                self.ct_click = True
                self.ct_x, self.ct_y = self.xrat, self.yrat
        self.mtrans += 1
        self.nbchange += 1
        self.pr_button = self.button
        self.pr_mclick = self.mclick
        self.pr_xrat = self.xrat
        self.pr_yrat = self.yrat
        self.button = new
        self.mclick = clicks
        if self.bw_active and self.ct_mine() and downorup(new, self.bw_parm):
            if self.bw_want > 1:
                self.gl_bpend -= 1
            self.bw_clicks = min(clicks, self.bw_want)
            self.bw_done = True
            self.bw_active = False

    def b_click(self, state):
        if state == self.gl_btrue:
            return
        if self.gl_bdely:
            if state == self.gl_bdesired:
                self.gl_bclick += 1
                self.gl_bdely += 3
        else:
            if self.gl_bpend and state:
                self.gl_bclick = 1
                self.gl_bdesired = state
                self.gl_bdely = self.gl_dclick
            else:
                self.bchange(state, 1)
        self.gl_btrue = state

    def b_delay(self, amnt):
        if not self.gl_bdely:
            return
        self.gl_bdely = max(self.gl_bdely - amnt, 0)
        if self.gl_bdely == 0:
            self.bchange(self.gl_bdesired, self.gl_bclick)
            if self.gl_bdesired != self.gl_btrue:
                self.bchange(self.gl_btrue, 1)

    def mchange(self, x, y):
        dx, dy = self.xrat - x, self.yrat - y
        if self.gl_bdely and (dx > 2 or dx < -2 or dy > 2 or dy < -2):
            self.b_delay(self.gl_bdely)
        self.xrat, self.yrat = x, y

    # the VDI vectors
    def ev_motv(self):
        b, x, y = self.gsx_mouse()
        if x != self.xrat or y != self.yrat:
            self.mchange(x, y)

    def ev_butv(self):
        b, x, y = self.gsx_mouse()
        self.b_click(b)

    def ev_timv(self):
        self.gl_ticks += 1
        self.b_delay(1)

    # -- ownership (geminput.c; event.c's ct_* here) -----------------------
    # ctrl is the application's rectangle; a press outside it goes to the
    # control manager, which keeps the mouse until the button is up, and
    # the application's waits see none of the input meanwhile.  The
    # control manager is a call made from the poll that saw the press,
    # its own waits nested inside the application's.
    def ct_init(self):
        self.ctrl = Rect()
        self.ct_owns = self.ct_inside = self.ct_click = False
        self.ct_x = self.ct_y = 0
        self.gl_ctmown = False
        self.ct_tmpmoff = 0
        self.ct_arrow_stop()
        # menu.c: the bar showing, and the rectangle that wakes the menu
        self.gl_mntree = None
        self.gl_ctwait = MOBLK(False, 0, 0, 0, 0)
        # The accessories' names, by slot, and where the first of them
        # lands in the tree.  Registrations outlive every application --
        # the donor registers once at AES start-up and never clears them
        # -- so this is set up HERE, in ct_init, and not in mn_init.
        self.gl_acctitle = [None] * NUM_ACCS
        self.gl_accreg = 0
        self.gl_dafirst = 0

    def ct_mine(self):
        return self.ct_inside or not self.ct_owns

    def ct_chkown(self, mx, my):
        if inside(mx, my, self.ctrl):
            return 1
        if inside(mx, my, self.gl_rmenu):
            return -1
        if self.wm_find(mx, my):
            return -1
        return 0

    def set_ctrl(self, pt):
        self.ctrl = pt.copy()

    def get_ctrl(self):
        return self.ctrl.copy()

    def ct_release(self):
        self.ct_owns = False
        self.ct_arrow_stop()
        if self.bw_active and downorup(self.button, self.bw_parm):
            if self.bw_want > 1:
                self.gl_bpend -= 1
            self.bw_clicks = 1
            self.bw_done = True
            self.bw_active = False

    def ct_chgown(self, pr):
        self.ctrl = pr.copy()
        if not self.gl_ctmown and self.button == 0:
            self.ct_release()

    def ct_run(self, menu=False):
        saved = (self.bw_active, self.bw_want, self.bw_done, self.bw_clicks,
                 self.bw_parm)
        self.bw_active = False
        self.ct_inside = True
        self.mtrans = 0
        self.wm_update(BEG_UPDATE)
        try:
            if menu:
                self.hctl_rect()
            else:
                self.hctl_button(self.ct_x, self.ct_y)
        finally:
            self.wm_update(END_UPDATE)
            self.ct_inside = False
            (self.bw_active, self.bw_want, self.bw_done, self.bw_clicks,
             self.bw_parm) = saved

    def ct_poll(self):
        if self.ct_inside:
            return
        if self.ct_click:
            self.ct_click = False
            self.ct_run()
        # The pointer in the active bar with the buttons up runs the menu
        # (the donor's mchange tail); the mouse is held until the button
        # that ended it is up -- event.c's deviation from the donor, which
        # re-dispatches a button still down as a press.
        if (not self.ct_owns and not self.gl_ctmown and self.button == 0
                and self.gl_mntree is not None
                and self.in_mrect(self.gl_ctwait)):
            self.ct_owns = True
            self.ct_run(menu=True)
        if not self.ct_owns:
            return
        if self.button:
            while self.gsx_getkey() is not None:
                pass
            self.ct_arrow_repeat()
            return
        self.ct_release()

    def ev_poll(self):
        """A wait's entry poll: the state brought up to date without a
        plan step or a tick, then the control manager's turn."""
        self.v.input_poll()
        self.ct_poll()

    def ev_fq(self):
        while self.gsx_getkey() is not None:
            pass

    def ev_rets(self, rets):
        if self.mtrans > 1:
            rets[0:3] = [self.pr_xrat, self.pr_yrat, self.pr_button]
        else:
            rets[0:3] = [self.xrat, self.yrat, self.button]
        self.kstate = self.gsx_kstate()
        rets[3] = self.kstate
        self.mtrans = 0

    def bw_register(self, buparm):
        self.bw_parm = buparm
        self.bw_want = (buparm >> 16) & 0xFF
        self.bw_done = False
        self.bw_active = True
        if self.bw_want > 1:
            self.gl_bpend += 1

    def bw_cancel(self):
        if self.bw_active:
            self.bw_active = False
            if self.bw_want > 1 and self.gl_bpend:
                self.gl_bpend -= 1

    def _step(self, check):
        """Apply the next plan step, poll once, and say whether `check`
        came true.

        The harness pokes the target's pointer or presses a key while the
        emulator is paused at a frame boundary, then runs frames; so the
        target's first poll of a frame sees the new input and the tick
        together, and its wait loop tests after every poll.  One step here
        is the same: the previous frame's key is up, the input is applied,
        one poll with the tick, the control manager's turn, then the test.
        A `frames` step is that many polls, one per call, so that a wait
        the control manager nests inside this one takes its polls from
        the same place; what it leaves of the step is the outer wait's to
        go on with, as the harness goes on running the step's frames.
        Frames left when the op completes are lost on both sides (the
        target does not poll between ops, and sees at most one tick when
        it next does): run() drops them."""
        if not self.plan:
            raise PlanExhausted()
        step = self.plan[0]
        v = self.v
        kind = step[0]
        v.key_mods = 0
        if kind == "frames":
            n = step[1]
            if n <= 1:
                self.plan.pop(0)
            else:
                self.plan[0] = ("frames", n - 1, True)
            if n <= 0:
                return False
            v.input_poll(tick=True)
            self.ct_poll()
            return check()
        self.plan.pop(0)
        if kind == "shot":
            # the screen as it stands, between frames: no input, no tick
            self.shots.append(v.to_rgb())
            return check()
        if kind == "probe":
            # the harness reads the target between frames; nothing here
            return check()
        if kind == "move":
            v.ptr_x, v.ptr_y = step[1], step[2]
        elif kind == "button":
            v.buttons = step[1]
        elif kind == "key":
            # ("key", altirra_name, gem_code[, shift, ctrl])
            v.keys.append(step[2])
            shift = len(step) > 3 and step[3]
            ctrl = len(step) > 4 and step[4]
            v.key_mods = (2 if shift else 0) | (4 if ctrl else 0)
        else:
            raise ValueError(f"unknown plan step {step!r}")
        v.input_poll(tick=True)
        self.ct_poll()
        return check()

    def ev_wait(self, flags, pmo1, pmo2, tmcount, buparm, rets, mebuff=None):
        """Wait for any of `flags`; returns what happened.  rets[4] gets
        the key, rets[5] the click count, mebuff the message a MU_MESAG
        delivered.  No ev_rets: ev_block's callers need mtrans as the wait
        left it."""
        self.ev_poll()

        def level():
            return self.button, self.nbchange, self.xrat, self.yrat

        def quick():
            """Anything already there?  -> (what, satisfied by the button's
            level rather than a stored edge)"""
            what = 0
            by_level = False
            mine = self.ct_mine()
            if mine and flags & MU_KEYBD:
                k = self.gsx_getkey()
                if k is not None:
                    rets[4] = k
                    what |= MU_KEYBD
            if mine and flags & MU_BUTTON:
                if self.mtrans > 1 and downorup(self.pr_button, buparm):
                    what |= MU_BUTTON
                    rets[5] = self.pr_mclick
                elif downorup(self.button, buparm):
                    what |= MU_BUTTON
                    rets[5] = self.mclick
                    by_level = True
            if mine and (flags & MU_M1) and self.in_mrect(pmo1):
                what |= MU_M1
            if mine and (flags & MU_M2) and self.in_mrect(pmo2):
                what |= MU_M2
            if (flags & MU_TIMER) and tmcount == 0:
                what |= MU_TIMER
            if flags & MU_MESAG:
                m = self.mq_get()
                if m is not None:
                    mebuff[:] = m
                    what |= MU_MESAG
            return what, by_level

        what, by_level = quick()
        if what == MU_BUTTON and by_level and self.last_level is not None \
                and self.last_level[0] == level():
            # The caller has come straight back with the button still held
            # and nothing else changed, and the target returns again at
            # once, thousands of times a frame, until the input changes.
            # What the caller did with the last return is on the screen:
            # if it drew something -- the file selector scrolling a line
            # for every return while an arrow is held -- the next return
            # is a new turn, and the target takes them until the caller
            # runs out of changes (the list's end) long before the frame
            # does.  Once a turn changes nothing -- form_do over a disabled
            # object, outside the dialog where GEM rings its bell, a
            # scroll at its stop -- every return after it is that one over
            # again, so walk the plan to the change instead.
            if self.v.screen_key() != self.last_level[1]:
                self.held_turns += 1
                if self.held_turns > 4096:
                    raise ValueError("a held button whose turns never settle: "
                                     "how many the target takes is unknowable")
            else:
                found = [(0, False)]

                def changed():
                    found[0] = quick()
                    return (found[0][0] != MU_BUTTON
                            or level() != self.last_level[0])

                while not self._step(changed):
                    pass
                what, by_level = found[0]
        if what:
            if (what & MU_BUTTON) and by_level:
                self.last_level = (level(), self.v.screen_key())
            else:
                self.last_level = None
                self.held_turns = 0
            return what
        self.last_level = None
        self.held_turns = 0

        if flags & MU_BUTTON:
            self.bw_register(buparm)
        twant = t0 = 0
        if flags & MU_TIMER:
            twant = 1 if tmcount < self.gl_ticktime else tmcount // self.gl_ticktime
            t0 = self.gl_ticks
        which = [0]

        def check():
            w = 0
            mine = self.ct_mine()
            if mine and flags & MU_KEYBD:
                k = self.gsx_getkey()
                if k is not None:
                    rets[4] = k
                    w |= MU_KEYBD
            if mine and (flags & MU_BUTTON) and self.bw_done:
                rets[5] = self.bw_clicks
                w |= MU_BUTTON
            if mine and (flags & MU_M1) and self.in_mrect(pmo1):
                w |= MU_M1
            if mine and (flags & MU_M2) and self.in_mrect(pmo2):
                w |= MU_M2
            if (flags & MU_TIMER) and self.gl_ticks - t0 >= twant:
                w |= MU_TIMER
            if flags & MU_MESAG:
                m = self.mq_get()
                if m is not None:
                    mebuff[:] = m
                    w |= MU_MESAG
            which[0] = w
            return w != 0

        while not self._step(check):
            pass
        self.bw_cancel()
        return which[0]

    def ev_multi(self, flags, pmo1, pmo2, tmcount, buparm, rets, mebuff=None):
        what = self.ev_wait(flags, pmo1, pmo2, tmcount, buparm, rets, mebuff)
        self.ev_rets(rets)
        return what

    def ev_wait_ticks(self, ticks):
        """Sleep for `ticks` ticks, none meaning one (adelay)."""
        t0 = self.gl_ticks
        ticks = max(ticks, 1)
        self.ev_poll()
        while self.gl_ticks - t0 < ticks:
            self._step(lambda: self.gl_ticks - t0 >= ticks)

    def ev_block(self, code, lvalue):
        if code == MU_KEYBD:
            self.ev_poll()
            got = []

            def check():
                k = self.gsx_getkey() if self.ct_mine() else None
                if k is not None:
                    got.append(k)
                return bool(got)
            while not check() and not self._step(check):
                pass
            return got[0]
        if code == MU_BUTTON:
            self.ev_poll()
            if self.ct_mine() and downorup(self.button, lvalue):
                return 1
            self.bw_register(lvalue)
            while not self.bw_done:
                self._step(lambda: self.bw_done)
            return self.bw_clicks
        if code in (MU_M1, MU_M2):
            self.ev_wait(code, lvalue, lvalue, 0, 0, [0] * 6)
            return 0
        if code == MU_TIMER:
            self.ev_wait_ticks(lvalue)
            return 0
        return 0

    def ev_keybd(self):
        return self.ev_block(MU_KEYBD, 0)

    def ev_button(self, clicks, mask, state, rets):
        ret = self.ev_block(MU_BUTTON, combine_cms(clicks, mask, state))
        self.ev_rets(rets)
        return ret

    def ev_mouse(self, pmo, rets):
        self.ev_block(MU_M1, pmo)
        self.ev_rets(rets)
        rets[2] = self.button
        return 1

    def ev_timer(self, count):
        ticks = 0 if count < self.gl_ticktime else count // self.gl_ticktime
        self.ev_wait_ticks(ticks)
        return 1

    # -- grlib.c: the XOR rubber boxes and graf_watchbox ------------------
    def gr_stilldn(self, out, x, y, w, h):
        rets = [0] * 6
        mo = MOBLK(out, x, y, w, h)
        which = self.ev_multi(MU_KEYBD | MU_BUTTON | MU_M1, mo, None,
                              0, 0x0001FF00, rets)
        return not (which & MU_BUTTON)

    def gr_setup(self, color):
        self.gsx_sclip(self.gl_rscreen)
        self.gsx_attr(False, MD_XOR, color)

    def gr_scale(self, xdist, ydist):
        """-> (cnt, xstep, ystep)"""
        self.gr_setup(BLACK)
        dist = word(cdiv(xdist + ydist, 2))
        i = 0
        while dist:
            dist = cdiv(dist, 2)
            i += 1
        if i:
            xs = max(cdiv(xdist, i), 1)
            ys = max(cdiv(ydist, i), 1)
        else:
            xs = ys = 1
        return i, xs, ys

    def gr_stepcalc(self, orgw, orgh, pt):
        """-> (cx, cy, cnt, xstep, ystep)"""
        cx = cdiv(pt.w, 2) - cdiv(orgw, 2)
        cy = cdiv(pt.h, 2) - cdiv(orgh, 2)
        cnt, xs, ys = self.gr_scale(cx, cy)
        return cx + pt.x, cy + pt.y, cnt, xs, ys

    def gr_xor(self, clipped, cnt, cx, cy, cw, ch, xstep, ystep, dowdht):
        while True:
            t = Rect(cx, cy, cw, ch)
            if clipped:
                self.gsx_xcbox(t)
            else:
                self.gsx_xbox(t)
            cx -= xstep
            cy -= ystep
            if dowdht:
                cw += 2 * xstep
                ch += 2 * ystep
            if cnt == 0:
                break
            cnt -= 1

    def gr_2box(self, flag1, cnt, pt, xstep, ystep, flag2):
        self.gsx_moff()
        for _ in range(2):
            self.gr_xor(flag1, cnt, pt.x, pt.y, pt.w, pt.h, xstep, ystep,
                        flag2)
        self.gsx_mon()

    def gr_movebox(self, w, h, srcx, srcy, dstx, dsty):
        t = Rect(srcx, srcy, w, h)
        signx = -1 if srcx < dstx else 1
        signy = -1 if srcy < dsty else 1
        cnt, xs, ys = self.gr_scale(signx * (srcx - dstx),
                                    signy * (srcy - dsty))
        self.gr_2box(False, cnt, t, signx * xs, signy * ys, False)

    def gr_growbox(self, po, pt):
        o = po.copy()
        cx, cy, cnt, xs, ys = self.gr_stepcalc(o.w, o.h, pt)
        self.gr_movebox(o.w, o.h, o.x, o.y, cx, cy)
        o.x, o.y = cx, cy
        self.gr_2box(True, cnt, o, xs, ys, True)

    def gr_shrinkbox(self, po, pt):
        cx, cy, cnt, xs, ys = self.gr_stepcalc(po.w, po.h, pt)
        self.gr_2box(True, cnt, pt, -xs, -ys, True)
        self.gr_movebox(po.w, po.h, cx, cy, po.x, po.y)

    def gr_watchbox(self, obj, instate, outstate):
        self.gsx_sclip(self.gl_rscreen)
        t = self.ob_actxywh(obj)
        out = False
        while True:
            state = outstate if out else instate
            self.ob_change(obj, state & 0xFFFF, True)
            out = not out
            if not self.gr_stilldn(out, t.x, t.y, t.w, t.h):
                break
        return int(out)

    # -- the pointer's shape (gsx_mfset, gr_mouse) ---------------------
    def gsx_mfset(self, form):
        """vsc_form with 37 words: hot spot, planes, the mask's colour and
        the data's, sixteen mask words, sixteen data.  The previous form is
        kept for graf_mouse(M_PREVIOUS).  Under a hide and a show, as the
        donor does it: vsc_form defines the form, and a pointer on the
        screen keeps its old picture until it is drawn again."""
        form = list(form)
        assert len(form) == gemdata.MFORM_WORDS, len(form)
        self.gsx_moff()
        if self.gl_mform is not None:
            self.gl_pmform = self.gl_mform
        self.gl_mform = form
        self.vcall(VSC_FORM, (), tuple(form))
        self.gsx_mon()

    def gr_mouse(self, mode, form=None):
        """graf_mouse: a shape, or a command about the pointer.  The
        donor's gr_mouse (gemgrlib.c) with its M_SAVE/M_RESTORE/M_PREVIOUS
        extension; a mode that is neither is the arrow, as it fails safe
        there."""
        if mode == M_OFF:
            self.gsx_moff()
            return
        if mode == M_ON:
            self.gsx_mon()
            return
        if mode == M_SAVE:
            self.gr_saved = list(self.gl_mform) if self.gl_mform else None
            return
        if mode == M_RESTORE:
            form = self.gr_saved
        elif mode == M_PREVIOUS:
            form = self.gl_pmform
        elif mode != USER_DEF:
            if mode < ARROW or mode > OUTLN_CROSS:
                mode = ARROW
            form = gemdata.mform_words(gemdata.MFORM_NAMES[mode])
        if form:
            self.gsx_mfset(form)

    def gr_mkstate(self):
        """-> (mx, my, mstat, kstat)"""
        self.v.input_poll()
        self.kstate = self.gsx_kstate()
        return self.xrat, self.yrat, self.button, self.kstate

    # the drag and rubber boxes the control manager works with
    def gr_clamp(self, xo, yo, wmin, hmin):
        return (max(self.xrat - xo + 1, wmin), max(self.yrat - yo + 1, hmin))

    def gr_draw(self, have2box, po, poff):
        self.gsx_xbox(po)
        if have2box:
            self.gsx_xbox(Rect(po.x + poff.x, po.y + poff.y,
                               po.w + poff.w, po.h + poff.h))

    def gr_wait(self, po, poff):
        have2box = not rc_equal(self.gl_rzero, poff)
        self.gsx_moff()
        self.gr_draw(have2box, po, poff)
        self.gsx_mon()
        down = self.gr_stilldn(True, self.xrat, self.yrat, 1, 1)
        self.gsx_moff()
        self.gr_draw(have2box, po, poff)
        self.gsx_mon()
        return down

    def gr_rubwind(self, xo, yo, wmin, hmin, poff):
        """-> (w, h)"""
        self.wm_update(BEG_UPDATE)
        self.gr_setup(BLACK)
        o = Rect(xo, yo, 0, 0)
        while True:
            o.w, o.h = self.gr_clamp(o.x, o.y, wmin, hmin)
            if not self.gr_wait(o, poff):
                break
        self.wm_update(END_UPDATE)
        return o.w, o.h

    def gr_rubbox(self, xo, yo, wmin, hmin):
        return self.gr_rubwind(xo, yo, wmin, hmin, self.gl_rzero)

    def gr_dragbox(self, w, h, sx, sy, pc):
        """-> (x, y)"""
        self.wm_update(BEG_UPDATE)
        self.gr_setup(BLACK)
        offx, offy = self.gr_clamp(sx + 1, sy + 1, 0, 0)
        o = Rect(sx, sy, w, h)
        while True:
            o.x = self.xrat - offx
            o.y = self.yrat - offy
            rc_constrain(pc, o)
            if not self.gr_wait(o, self.gl_rzero):
                break
        self.wm_update(END_UPDATE)
        return o.x, o.y

    def gr_slidebox(self, parent, obj, isvert):
        c = self.ob_actxywh(parent)
        t = self.ob_relxywh(obj)
        t.x, t.y = self.gr_dragbox(t.w, t.h, t.x + c.x, t.y + c.y, c)
        divnd = t.y - c.y if isvert else t.x - c.x
        divis = c.h - t.h if isvert else c.w - t.w
        return mul_div_round(divnd, 1000, divis) if divis else 0

    # -- the window manager (wind.c) ----------------------------------------
    # The rectangle pool is counted, not modelled: gl_rul is how many are
    # free, and running out is an error rather than a dropped piece.
    def get_orect(self):
        if self.gl_rul == 0:
            raise OrectExhausted(f"more than {NUM_ORECT} rectangles")
        self.gl_rul -= 1

    def free_orects(self, n):
        self.gl_rul += n

    def mkpiece(self, tlrb, new, old):
        """The piece of old on the tlrb side of new."""
        self.get_orect()
        x, w = old.x, old.w
        y = max(old.y, new.y)
        oy2, ny2 = old.y + old.h, new.y + new.h
        h = min(oy2, ny2) - y
        if tlrb == 0:                   # TOP
            y = old.y
            h = new.y - old.y
        elif tlrb == 1:                 # LEFT
            w = new.x - old.x
        elif tlrb == 2:                 # RIGHT
            x = new.x + new.w
            w = old.x + old.w - x
        else:                           # BOTTOM
            y = ny2
            h = oy2 - ny2
        return Rect(x, y, w, h)

    def brkrct(self, new, r):
        """The pieces of r not under new, in TOP LEFT RIGHT BOTTOM order,
        r itself going back to the pool; None if they do not overlap."""
        if not (new.x < r.x + r.w and new.x + new.w > r.x and
                new.y < r.y + r.h and new.y + new.h > r.y):
            return None
        have = (new.y > r.y, new.x > r.x,
                new.x + new.w < r.x + r.w, new.y + new.h < r.y + r.h)
        pieces = [self.mkpiece(i, new, r) for i in range(4) if have[i]]
        self.free_orects(1)
        return pieces

    def mkrect(self, wh):
        """Break every rectangle of window wh's list around gl_mkrect."""
        pwin = self.gl_win[wh]
        rl = pwin.w_rlist
        i = 0
        while i < len(rl):
            pieces = self.brkrct(self.gl_mkrect, rl[i])
            if pieces is None:
                i += 1
            else:
                rl[i:i + 1] = pieces
                pwin.w_flags |= VF_BROKEN
                i += len(pieces)

    def newrect(self, wh):
        """Rebuild window wh's list: its whole true rectangle, after every
        window below it has been broken around that rectangle."""
        pwin = self.gl_win[wh]
        self.free_orects(len(pwin.w_rlist))
        pwin.w_rlist = []
        pwin.w_flags &= ~VF_BROKEN
        self.gl_mkrect = self.w_getsize(WS_TRUE, wh)
        if not (self.gl_mkrect.w and self.gl_mkrect.h):
            return
        self.w_everyobj(ROOT, wh, lambda obj, x, y: self.mkrect(obj))
        self.get_orect()
        pwin.w_rlist = [self.gl_mkrect.copy()]

    def w_everyobj(self, this, last, routine):
        saved, self.tree = self.tree, self.W_TREE
        try:
            self.everyobj(this, last, routine, 0, 0, MAX_DEPTH)
        finally:
            self.tree = saved

    # -- the window tree and the frame
    @staticmethod
    def w_nilit(olist):
        for o in olist:
            o.ob_next = o.ob_head = o.ob_tail = NIL

    def w_setup(self, wh, kind):
        pwin = self.gl_win[wh]
        pwin.w_flags = VF_INUSE
        pwin.w_kind = kind & 0xFFFF
        pwin.w_owner = 0                # the one application: see Window
        pwin.w_pname = pwin.w_pinfo = WM_EMPTY
        pwin.w_hslide = pwin.w_vslide = 0
        pwin.w_hslsiz = pwin.w_vslsiz = -1

    def w_getsize(self, which, wh):
        pwin = self.gl_win[wh]
        if which in (WS_CURR, WS_TRUE):
            o = self.W_TREE[wh]
            pt = Rect(o.ob_x, o.ob_y, o.ob_width, o.ob_height)
            if which == WS_TRUE and pt.w and pt.h:
                pt.w += DROP_SHADOW_SIZE
                pt.h += DROP_SHADOW_SIZE
            return pt
        if which == WS_PREV:
            return pwin.w_prev.copy()
        if which == WS_WORK:
            return pwin.w_work.copy()
        return pwin.w_full.copy()

    def w_setsize(self, which, wh, pt):
        pwin = self.gl_win[wh]
        if which in (WS_CURR, WS_TRUE):
            o = self.W_TREE[wh]
            o.ob_x, o.ob_y, o.ob_width, o.ob_height = pt.tuple()
        elif which == WS_PREV:
            pwin.w_prev = pt.copy()
        elif which == WS_WORK:
            pwin.w_work = pt.copy()
        else:
            pwin.w_full = pt.copy()

    def w_adjust(self, parent, obj, x, y, w, h):
        o = self.W_ACTIVE[obj]
        o.ob_x, o.ob_y, o.ob_width, o.ob_height = x, y, w, h
        o.ob_head = o.ob_tail = NIL
        self.ob_add(self.W_ACTIVE, parent, obj)

    # objc.c's tree surgery, on whichever tree is handed in
    @staticmethod
    def ob_add(tree, parent, child):
        if parent == NIL or child == NIL:
            return
        tree[child].ob_next = parent
        ptail = tree[parent].ob_tail
        if ptail == NIL:
            tree[parent].ob_head = child
        else:
            tree[ptail].ob_next = child
        tree[parent].ob_tail = child

    @staticmethod
    def _ob_get_par_in(tree, obj):
        if obj == ROOT:
            return NIL
        pobj = tree[obj].ob_next
        if pobj != NIL:
            while tree[pobj].ob_tail != obj:
                obj = pobj
                pobj = tree[obj].ob_next
        return pobj

    @classmethod
    def ob_delete(cls, tree, obj):
        if obj == ROOT:
            return False
        nextsib = tree[obj].ob_next
        parent = cls._ob_get_par_in(tree, obj)
        if tree[parent].ob_head == obj:
            if tree[parent].ob_tail == obj:
                nextsib = NIL
                tree[parent].ob_tail = NIL
            tree[parent].ob_head = nextsib
        else:
            prev = cls._ob_get_prev(tree, parent, obj)
            if prev == NIL:
                return False
            tree[prev].ob_next = nextsib
            if tree[parent].ob_tail == obj:
                tree[parent].ob_tail = prev
        return True

    @classmethod
    def ob_order(cls, tree, mov_obj, new_pos):
        if mov_obj == ROOT:
            return False
        parent = cls._ob_get_par_in(tree, mov_obj)
        cls.ob_delete(tree, mov_obj)
        chg_obj = tree[parent].ob_head
        if chg_obj == NIL:
            cls.ob_add(tree, parent, mov_obj)
            return True
        if new_pos == 0:
            tree[mov_obj].ob_next = chg_obj
            tree[parent].ob_head = mov_obj
        else:
            if new_pos == NIL:
                chg_obj = tree[parent].ob_tail
            else:
                for _ in range(1, new_pos):
                    chg_obj = tree[chg_obj].ob_next
            tree[mov_obj].ob_next = tree[chg_obj].ob_next
            tree[chg_obj].ob_next = mov_obj
        if tree[mov_obj].ob_next == parent:
            tree[parent].ob_tail = mov_obj
        return True

    def do_walk(self, wh, tree, obj, depth, pc):
        """Draw obj of tree once per rectangle of window wh's list that
        meets pc (clipped to the screen below the menu bar)."""
        if wh == NIL:
            return
        if pc is not None:
            rc_intersect(self.gl_rfull, pc)
        else:
            pc = self.gl_rfull.copy()
        saved, self.tree = self.tree, tree
        try:
            for r in self.gl_win[wh].w_rlist:
                t = r.copy()
                if rc_intersect(pc, t):
                    self.gsx_sclip(t)
                    self.ob_draw(obj, depth)
        finally:
            self.tree = saved

    def w_top(self):
        return self.gl_wtop if self.gl_wtop != NIL else DESKWH

    def w_above(self, wh):
        """The window directly above wh in the order list, DESKWH for
        none.  ob_head is the bottom and ob_next steps UPWARDS; the last
        child of a right-threaded tree points back at ROOT."""
        up = self.W_TREE[wh].ob_next
        return DESKWH if up in (ROOT, NIL) else up

    def w_below(self, wh):
        """...and the one directly below it, DESKWH for none."""
        i = self.W_TREE[ROOT].ob_head
        if i in (NIL, wh):
            return DESKWH
        while i not in (NIL, ROOT) and self.W_TREE[i].ob_next != wh:
            i = self.W_TREE[i].ob_next
        return DESKWH if i in (NIL, ROOT) else i

    def w_setactive(self):
        self.ct_chgown(self.w_getsize(WS_WORK, self.w_top()))

    def w_drawdesk(self, pc):
        if self.gl_newdesk is not None:
            tree, depth, root = self.gl_newdesk, MAX_DEPTH, self.gl_newroot
        else:
            tree, depth, root = self.W_TREE, 0, ROOT
        self.do_walk(DESKWH, tree, root, depth, pc.copy())

    def w_bldvbar(self, kind, istop, pw, x, y, w, h):
        self.w_adjust(W_DATA, W_VBAR, x, y, self.gl_wbox, h)
        x = y = 0
        if not istop:
            return
        if kind & UPARROW:
            self.w_adjust(W_VBAR, W_UPARROW, x, y, self.gl_wbox, self.gl_hbox)
            y += self.gl_hbox - 1
            h -= self.gl_hbox - 1
        if kind & DNARROW:
            w -= self.gl_wbox - 1
            h -= self.gl_hbox - 1
            self.w_adjust(W_VBAR, W_DNARROW, x, y + h - 1, self.gl_wbox,
                          self.gl_hbox)
        if kind & VSLIDE:
            self.w_adjust(W_VBAR, W_VSLIDE, x, y, self.gl_wbox, h)
            if pw.w_vslsiz == -1:
                size = self.gl_hbox
            else:
                size = max(mul_div_round(h, pw.w_vslsiz, 1000), self.gl_hbox)
            posn = mul_div_round(word(h - size), pw.w_vslide, 1000)
            self.w_adjust(W_VSLIDE, W_VELEV, 0, posn, self.gl_wbox, size)

    def w_bldhbar(self, kind, istop, pw, x, y, w, h):
        self.w_adjust(W_DATA, W_HBAR, x, y, w, self.gl_hbox)
        x = y = 0
        if not istop:
            return
        if kind & LFARROW:
            self.w_adjust(W_HBAR, W_LFARROW, x, y, self.gl_wbox, self.gl_hbox)
            x += self.gl_wbox - 1
            w -= self.gl_wbox - 1
        if kind & RTARROW:
            w -= self.gl_wbox - 1
            h -= self.gl_hbox - 1
            self.w_adjust(W_HBAR, W_RTARROW, x + w - 1, y, self.gl_wbox,
                          self.gl_hbox)
        if kind & HSLIDE:
            self.w_adjust(W_HBAR, W_HSLIDE, x, y, w, self.gl_hbox)
            if pw.w_hslsiz == -1:
                size = self.gl_wbox
            else:
                size = max(mul_div_round(w, pw.w_hslsiz, 1000), self.gl_wbox)
            posn = mul_div_round(word(w - size), pw.w_hslide, 1000)
            self.w_adjust(W_HSLIDE, W_HELEV, posn, 0, size, self.gl_hbox)

    def w_bldactive(self, wh):
        """Lay W_ACTIVE out for window wh."""
        if wh == NIL:
            return
        pw = self.gl_win[wh]
        istop = self.gl_wtop == wh
        kind = pw.w_kind
        W = self.W_ACTIVE
        self.w_nilit(W)
        self.gl_aname.ptext = pw.w_pname
        self.gl_ainfo.ptext = pw.w_pinfo
        self.gl_aname.just = TE_CNTR

        t = self.w_getsize(WS_CURR, wh)
        (W[W_BOX].ob_x, W[W_BOX].ob_y,
         W[W_BOX].ob_width, W[W_BOX].ob_height) = t.tuple()
        t.x = t.y = 0

        if kind & (NAME | CLOSER | FULLER):
            self.w_adjust(W_BOX, W_TITLE, t.x, t.y, t.w, self.gl_hbox)
            tempw = t.w
            if (kind & CLOSER) and istop:
                self.w_adjust(W_TITLE, W_CLOSER, t.x, t.y, self.gl_wbox,
                              self.gl_hbox)
                t.x += self.gl_wbox
                tempw -= self.gl_wbox
            if (kind & FULLER) and istop:
                tempw -= self.gl_wbox
                self.w_adjust(W_TITLE, W_FULLER, t.x + tempw, t.y,
                              self.gl_wbox, self.gl_hbox)
            if kind & NAME:
                self.w_adjust(W_TITLE, W_NAME, t.x, t.y, tempw, self.gl_hbox)
                W[W_NAME].ob_state = NORMAL if istop else DISABLED
                self.gl_aname.color = TOPPED_COLOR if istop else UNTOPPED_COLOR
            t.x = 0
            t.y += self.gl_hbox - 1
            t.h -= self.gl_hbox - 1

        if kind & INFO:
            self.w_adjust(W_BOX, W_INFO, t.x, t.y, t.w, self.gl_hbox)
            t.y += self.gl_hbox - 1
            t.h -= self.gl_hbox - 1

        self.w_adjust(W_BOX, W_DATA, t.x, t.y, t.w, t.h)
        havevbar = kind & (UPARROW | DNARROW | VSLIDE | SIZER)
        havehbar = kind & (LFARROW | RTARROW | HSLIDE | SIZER)
        sizer_x, sizer_y = -1, 0
        if havevbar and havehbar:
            sizer_x = t.w - self.gl_wbox
            sizer_y = t.h - self.gl_hbox
        t.x = t.y = 1
        t.w -= 2
        t.h -= 2
        if havevbar:
            t.w -= self.gl_wbox - 1
        if havehbar:
            t.h -= self.gl_hbox - 1
        self.w_adjust(W_DATA, W_WORK, t.x, t.y, t.w, t.h)

        if havevbar:
            t.x += t.w
            self.w_bldvbar(kind, istop, pw, t.x, 0, t.w + 2, t.h + 2)
        if havehbar:
            t.y += t.h
            self.w_bldhbar(kind, istop, pw, 0, t.y, t.w + 2, t.h + 2)
        if sizer_x >= 0:
            self.w_adjust(W_DATA, W_SIZER, sizer_x, sizer_y, self.gl_wbox,
                          self.gl_hbox)
            W[W_SIZER].ob_spec &= 0x00FFFFFF
            if istop and (kind & SIZER):
                W[W_SIZER].ob_spec |= 0x06000000

    def w_cpwalk(self, wh, obj, depth, usetrue):
        if usetrue:
            c = self.w_getsize(WS_TRUE, wh)
        else:
            c = self.gsx_gclip()
            c.w += DROP_SHADOW_SIZE
            c.h += DROP_SHADOW_SIZE
        self.w_bldactive(wh)
        self.do_walk(wh, self.W_ACTIVE, obj, depth, c)

    # -- redraw messages
    @staticmethod
    def w_union(rlist):
        if not rlist:
            return None
        pt = rlist[0].copy()
        for r in rlist[1:]:
            rc_union(r, pt)
        return pt

    def w_redraw(self, wh, pt):
        t = pt.copy()
        d = self.w_getsize(WS_WORK, wh)
        if not rc_intersect(t, d):
            return
        d = self.w_union(self.gl_win[wh].w_rlist)
        if d is not None and rc_intersect(d, t):
            self.ap_sendmsg(WM_REDRAW, wh, t.x, t.y, t.w, t.h)

    # -- moving and changing
    def w_mvfix(self, ps, pd):
        tmpsx = ps.x
        rc_intersect(self.gl_rfull, ps)
        if tmpsx == -1:
            pd.x += 1
            pd.w -= 1
            return True
        return False

    def bb_screen(self, sx, sy, dx, dy, w, h):
        self.gsx_moff()
        self.vcall(VRO_CPYFM, (sx, sy, sx + w - 1, sy + h - 1,
                                dx, dy, dx + w - 1, dy + h - 1), (S_ONLY,))
        self.gsx_mon()

    def bb_save_restore(self, pr, saveit):
        """graf.c: the rectangle widened to whole bytes -- an even x, an
        even width -- copied between the screen and the VDI's save form
        at the same place, so the blit is one pure copy.  The clip comes
        off for the duration: a clip that cut the rectangle back to an odd
        one would change what is copied, and on the target it would cost
        the blitter (docs/phase12.md)."""
        x = pr.x & ~1
        w = (pr.w + (pr.x & 1) + 1) & ~1
        save = self.v.dev.save_form()
        forms = (None, save) if saveit else (save, None)
        clip = self.gsx_gclip()
        self.gsx_sclip(self.gl_rzero)
        self.gsx_moff()
        self.vcall(VRO_CPYFM, (x, pr.y, x + w - 1, pr.y + pr.h - 1,
                                x, pr.y, x + w - 1, pr.y + pr.h - 1),
                    (S_ONLY,), forms)
        self.gsx_mon()
        self.gsx_sclip(clip)

    def bb_save(self, pr):
        self.bb_save_restore(pr, True)

    def bb_restore(self, pr):
        self.bb_save_restore(pr, False)

    def w_move(self, wh):
        """Move the top window wh from its previous to its current
        rectangle: (moved, where w_update stops, the rectangle to update)."""
        s = self.w_getsize(WS_PREV, wh)
        s.w += DROP_SHADOW_SIZE
        s.h += DROP_SHADOW_SIZE
        d = self.w_getsize(WS_TRUE, wh)
        if ((s.x + s.w > self.gl_width and d.x < s.x) or
                (s.y + s.h > self.gl_height and d.y < s.y)):
            rc_union(s, d)
            stop = DESKWH
        else:
            stop = wh
        sminus1 = self.w_mvfix(s, d)
        dminus1 = self.w_mvfix(d, s)
        if stop == wh:
            self.gsx_sclip(self.gl_rfull)
            self.bb_screen(s.x, s.y, d.x, d.y, s.w, s.h)
            if sminus1 != dminus1:
                if dminus1:
                    s.x -= 1
                if sminus1:
                    d.x -= 1
                    d.w = 1
                    self.gsx_sclip(d)
                    self.w_cpwalk(self.gl_wtop, 0, 0, False)
            pc = s
        else:
            pc = d
        return stop == wh, stop, pc.copy()

    def w_update(self, bottom, pt, top, moved):
        """Redraw every window from bottom to top within pt, frame and
        WM_REDRAW, skipping one that was blitted into place."""
        W = self.W_TREE
        rc_intersect(self.gl_rfull, pt)
        self.gsx_moff()
        if bottom == DESKWH:
            bottom = W[ROOT].ob_head
        if bottom != NIL:
            if top == DESKWH:
                top = W[ROOT].ob_tail
            while True:
                if not (moved and top == self.gl_wtop):
                    self.gsx_sclip(pt)
                    self.w_cpwalk(top, 0, MAX_DEPTH, False)
                    self.w_redraw(top, pt)
                i = bottom
                done = i == top
                while i != top:
                    ni = W[i].ob_next
                    if ni == top:
                        top = i
                    else:
                        i = ni
                if done:
                    break
        self.gsx_mon()

    def draw_change(self, wh, pt):
        pwin = self.gl_win[wh]
        W = self.W_TREE
        wasclr = not (pwin.w_flags & VF_BROKEN)
        c = self.w_getsize(WS_CURR, wh)
        self.w_setsize(WS_PREV, wh, c)
        self.w_setsize(WS_CURR, wh, pt)
        pwin.w_work = Rect(*self.wm_calc(WC_WORK, pwin.w_kind, pt.x, pt.y,
                                         pt.w, pt.h))
        if not (pwin.w_flags & VF_ISOPEN):
            return

        self.w_everyobj(ROOT, NIL, lambda obj, x, y: self.newrect(obj))
        oldtop = self.gl_wtop
        self.gl_wtop = W[ROOT].ob_tail
        self.w_setactive()

        start, stop, moved = wh, DESKWH, False
        if not rc_equal(self.gl_rzero, pt) and pt.x == c.x and pt.y == c.y:
            if pt.w == c.w and pt.h == c.h:
                # same place, same size: a change of top, or nothing
                if wh != W[ROOT].ob_tail or wh == oldtop:
                    return
                if oldtop != NIL:
                    self.w_cpwalk(oldtop, 0, MAX_DEPTH, True)
                    clrold = not (self.gl_win[oldtop].w_flags & VF_BROKEN)
                else:
                    clrold = True
                if clrold and wasclr:
                    self.w_cpwalk(self.gl_wtop, 0, MAX_DEPTH, True)
                    return
            else:
                # same place, new size
                if pt.w <= c.w and pt.h <= c.h:
                    stop = wh
                    self.w_cpwalk(self.gl_wtop, 0, MAX_DEPTH, True)
                    moved = True
                if pt.w < c.w or pt.h < c.h:
                    start = DESKWH
                c.w = max(pt.w, c.w) + DROP_SHADOW_SIZE
                c.h = max(pt.h, c.h) + DROP_SHADOW_SIZE
        else:
            # a move, an open (from nothing) or a close (to nothing)
            if (not (c.w and c.h) or
                    (pt.x <= c.x and pt.y <= c.y and
                     pt.x + pt.w >= c.x + c.w and pt.y + pt.h >= c.y + c.h)):
                c = pt.copy()
            else:
                if pt.w == c.w and pt.h == c.h and self.gl_wtop == wh:
                    moved, stop, c = self.w_move(wh)
                    start = DESKWH
                if not (pt.w and pt.h):
                    start = DESKWH
                if start != DESKWH:
                    rc_union(pt, c)
                    if not rc_equal(pt, c):
                        start = DESKWH

        # a new top: its frame is redrawn with the rest
        if oldtop != W[ROOT].ob_tail and self.gl_wtop != NIL:
            t = self.w_getsize(WS_CURR, self.gl_wtop)
            rc_union(t, c)
            if oldtop != NIL and oldtop != wh:
                pprev = self.w_getsize(WS_PREV, self.gl_wtop)
                if rc_equal(pprev, self.gl_rzero):
                    self.w_cpwalk(oldtop, 0, MAX_DEPTH, True)

        c.w += DROP_SHADOW_SIZE
        c.h += DROP_SHADOW_SIZE
        if start == DESKWH:
            self.w_drawdesk(c)
        self.w_update(start, c, stop, moved)

    @staticmethod
    def w_snap(pt):
        """x down to even, width up to even: the blitter has no shifter.
        The width is not widened to keep the right edge, so an odd move
        of a snapped window stays a move (a blit) and not a resize."""
        pt.x &= ~1
        if pt.w & 1:
            pt.w += 1

    # -- the API
    def wm_init(self):
        self.gl_rul = NUM_ORECT
        self.W_TREE = [Obj(NIL, NIL, NIL, G_IBOX, 0, 0, 0, 0, 0, 0, 0)
                       for _ in range(NUM_WIN)]
        self.W_TREE[ROOT].ob_type = G_BOX
        self.W_TREE[ROOT].ob_spec = DESK_SPEC
        self.gl_win = [Window() for _ in range(NUM_WIN)]
        self.W_ACTIVE = [Obj(NIL, NIL, NIL, GL_WATYPE[i], 0, 0,
                             GL_WASPEC[i] or 0, 0, 0, 0, 0)
                         for i in range(NUM_ELEM)]
        self.W_ACTIVE[ROOT].ob_state = SHADOWED

        # the desktop owns the whole screen below the menu bar
        self.get_orect()
        self.gl_win[DESKWH].w_rlist = [self.gl_rfull.copy()]
        self.w_setup(DESKWH, 0)
        self.w_setsize(WS_CURR, DESKWH, self.gl_rscreen)
        self.w_setsize(WS_PREV, DESKWH, self.gl_rscreen)
        self.w_setsize(WS_FULL, DESKWH, self.gl_rfull)
        self.w_setsize(WS_WORK, DESKWH, self.gl_rfull)

        self.gl_wtop = NIL
        self.gl_newdesk = None
        self.gl_newroot = ROOT
        self.gl_rzero = Rect()
        self.gl_mkrect = Rect()
        self.wm_ucount = 0

        # gl_asamp, twice, the name centred
        self.gl_aname = Ted(WM_EMPTY, 0, 0, font=IBM, just=TE_CNTR,
                            color=UNTOPPED_COLOR, thickness=1,
                            txtlen=80, tmplen=80)
        self.gl_ainfo = Ted(WM_EMPTY, 0, 0, font=IBM, just=TE_LEFT,
                            color=UNTOPPED_COLOR, thickness=1,
                            txtlen=80, tmplen=80)
        self.mem[WM_ANAME] = self.gl_aname
        self.mem[WM_AINFO] = self.gl_ainfo
        self.mem[WM_EMPTY] = Text("")
        self.W_ACTIVE[W_NAME].ob_spec = WM_ANAME
        self.W_ACTIVE[W_INFO].ob_spec = WM_AINFO

    def wm_create(self, kind, pt):
        for i in range(NUM_WIN):
            if not (self.gl_win[i].w_flags & VF_INUSE):
                self.w_setup(i, kind)
                self.w_setsize(WS_CURR, i, self.gl_rzero)
                self.w_setsize(WS_PREV, i, self.gl_rzero)
                self.w_setsize(WS_FULL, i, pt)
                return i
        return -1

    def get_pwin(self, wh):
        if wh < 0 or wh >= NUM_WIN:
            return None
        pwin = self.gl_win[wh]
        return pwin if pwin.w_flags & VF_INUSE else None

    def wm_open(self, wh, pt):
        pwin = self.get_pwin(wh)
        if pwin is None or (pwin.w_flags & VF_ISOPEN):
            return 0
        t = pt.copy()
        self.w_snap(t)
        self.wm_update(BEG_UPDATE)
        pwin.w_flags |= VF_ISOPEN
        self.ob_add(self.W_TREE, ROOT, wh)
        self.draw_change(wh, t)
        self.w_setsize(WS_PREV, wh, t)
        self.wm_update(END_UPDATE)
        return 1

    def wm_close(self, wh):
        pwin = self.get_pwin(wh)
        if pwin is None or not (pwin.w_flags & VF_ISOPEN):
            return 0
        self.wm_update(BEG_UPDATE)
        self.ob_delete(self.W_TREE, wh)
        self.draw_change(wh, self.gl_rzero.copy())
        pwin.w_flags &= ~VF_ISOPEN
        self.wm_update(END_UPDATE)
        return 1

    def wm_delete(self, wh):
        pwin = self.get_pwin(wh)
        if pwin is None:
            return 0
        if pwin.w_flags & VF_ISOPEN:
            self.wm_close(wh)
        self.newrect(wh)
        self.w_setsize(WS_CURR, wh, self.gl_rscreen)
        self.w_setsize(WS_PREV, wh, self.gl_rscreen)
        self.w_setsize(WS_FULL, wh, self.gl_rfull)
        self.w_setsize(WS_WORK, wh, self.gl_rfull)
        pwin.w_flags = 0
        return 1

    @staticmethod
    def w_owns(pwin, i, pt):
        """The next rectangle of pwin's list from index i that meets pt,
        leaving the cursor after it; (x, y, 0, 0) when there is none, x and
        y as the last failed intersection left them."""
        pout = Rect()
        rl = pwin.w_rlist
        while i < len(rl):
            pout = rl[i].copy()
            i += 1
            pwin.w_rnext = i
            if rc_intersect(pt, pout):
                return pout
        pout.w = pout.h = 0
        return pout

    def wm_get(self, wh, field):
        """(the return value, the four output words)."""
        out = [0, 0, 0, 0]
        pwin = self.get_pwin(wh)
        if pwin is None and field not in (WF_TOP, WF_SCREEN, WF_BOTTOM):
            return 0, out
        sizes = {WF_WXYWH: WS_WORK, WF_CXYWH: WS_CURR,
                 WF_PXYWH: WS_PREV, WF_FXYWH: WS_FULL}
        if field in sizes:
            out[:] = self.w_getsize(sizes[field], wh).tuple()
        elif field == WF_HSLIDE:
            out[0] = pwin.w_hslide
        elif field == WF_VSLIDE:
            out[0] = pwin.w_vslide
        elif field == WF_HSLSIZ:
            out[0] = pwin.w_hslsiz
        elif field == WF_VSLSIZ:
            out[0] = pwin.w_vslsiz
        elif field == WF_TOP:
            out[0] = self.w_top()
        elif field in (WF_FIRSTXYWH, WF_NEXTXYWH):
            t = self.w_getsize(WS_WORK, wh)
            i = 0 if field == WF_FIRSTXYWH else pwin.w_rnext
            out[:] = self.w_owns(pwin, i, t).tuple()
        elif field == WF_SCREEN:
            pass
        elif field == WF_OWNER:
            # Compendium p.455: the owner's AES id, the open status, the
            # handle of the window directly ABOVE it and the one directly
            # BELOW it.  The root's children are the windows with the
            # BOTTOM first, so ob_next steps upwards; a right-threaded
            # tree's last child points back at ROOT, which means "nothing
            # above" and answers the desk's own handle.
            out[:] = [pwin.w_owner, 1 if pwin.w_flags & VF_ISOPEN else 0,
                      self.w_above(wh), self.w_below(wh)]
        elif field == WF_BOTTOM:
            # p.456: the bottom window, the desk NOT counted -- and the
            # desk itself when there is no window at all.
            head = self.W_TREE[ROOT].ob_head
            out[0] = head if head != NIL else DESKWH
        else:
            return 0, out
        return 1, out

    def wm_mktop(self, wh):
        self.ob_order(self.W_TREE, wh, NIL)
        p = self.w_getsize(WS_PREV, wh)
        t = self.w_getsize(WS_CURR, wh)
        self.draw_change(wh, t)
        self.w_setsize(WS_PREV, wh, p)

    def wm_set(self, wh, field, pinwds):
        pwin = self.get_pwin(wh)
        if pwin is None:
            return 0
        pinwds = list(pinwds) + [0] * 4
        self.wm_update(BEG_UPDATE)
        which, do_cpwalk, ret = -1, False, 1
        if field in (WF_HSLSIZ, WF_VSLSIZ, WF_HSLIDE, WF_VSLIDE):
            if not (field in (WF_HSLSIZ, WF_VSLSIZ) and pinwds[0] == -1):
                pinwds[0] = min(max(pinwds[0], 1), 1000)
        if field == WF_NAME:
            # all 24 bits, high word first: a --data-model=large program's
            # title is far, and the AES re-reads it at every redraw, so
            # the address is kept whole and brought down at DRAW time
            # (w_ptext, src/aes/wind.c) rather than bounced in the shim
            pwin.w_pname = ((pinwds[0] & 0xFFFF) << 16) | (pinwds[1] & 0xFFFF)
            self.gl_aname.ptext = pwin.w_pname
            if pwin.w_flags & VF_ISOPEN:
                which, do_cpwalk = W_NAME, True
        elif field == WF_INFO:
            pwin.w_pinfo = ((pinwds[0] & 0xFFFF) << 16) | (pinwds[1] & 0xFFFF)
            self.gl_ainfo.ptext = pwin.w_pinfo
            if pwin.w_flags & VF_ISOPEN:
                which, do_cpwalk = W_INFO, True
        elif field == WF_CXYWH:
            t = Rect(*pinwds[0:4])
            self.w_snap(t)
            self.draw_change(wh, t)
        elif field == WF_TOP:
            if wh != self.gl_wtop:
                self.wm_mktop(wh)
        elif field == WF_NEWDESK:
            addr = pinwds[1] & 0xFFFF
            self.gl_newdesk = self.trees[addr] if addr else None
            self.gl_newroot = pinwds[2]
        elif field == WF_HSLSIZ:
            if pwin.w_hslsiz != pinwds[0]:
                pwin.w_hslsiz = pinwds[0]
                which = W_HSLIDE
        elif field == WF_VSLSIZ:
            if pwin.w_vslsiz != pinwds[0]:
                pwin.w_vslsiz = pinwds[0]
                which = W_VSLIDE
        elif field == WF_HSLIDE:
            if pwin.w_hslide != pinwds[0]:
                pwin.w_hslide = pinwds[0]
                which = W_HSLIDE
        elif field == WF_VSLIDE:
            if pwin.w_vslide != pinwds[0]:
                pwin.w_vslide = pinwds[0]
                which = W_VSLIDE
        else:
            ret = 0
        if wh == self.gl_wtop and which in (W_HSLIDE, W_VSLIDE):
            do_cpwalk = True
        if do_cpwalk:
            self.w_cpwalk(wh, which, MAX_DEPTH, True)
        self.wm_update(END_UPDATE)
        return ret

    def wm_find(self, x, y):
        saved, self.tree = self.tree, self.W_TREE
        try:
            return self.ob_find(ROOT, 2, x, y)
        finally:
            self.tree = saved

    def wm_new(self):
        """wind_new (109): the windows, the two locks and the pointer's
        hide count put back.  The locks FIRST, or a close would draw
        nothing.  The menu bar is deliberately left alone -- src/aes/
        wind.c says why that differs from the Falcon ROM."""
        while self.ml_ocnt > 0:
            self.wm_update(END_MCTRL)
        while self.wm_ucount > 0:
            self.wm_update(END_UPDATE)
        for wh in range(1, NUM_WIN):
            if self.gl_win[wh].w_flags & VF_ISOPEN:
                self.wm_close(wh)
            if self.gl_win[wh].w_flags & VF_INUSE:
                self.wm_delete(wh)
        if self.gl_moff:
            self.gl_moff = 0
            self.vcall(V_SHOW_C, (), (0,))

    def wm_update(self, beg):
        if beg < 2:
            if beg:
                self.wm_ucount += 1
            elif self.wm_ucount:
                self.wm_ucount -= 1
        else:
            self.fm_own(beg - 2)

    def wm_calc(self, wtype, kind, x, y, w, h):
        tb = bb = lb = rb = 1
        if kind & (NAME | CLOSER | FULLER):
            tb += self.gl_hbox - 1
        if kind & INFO:
            tb += self.gl_hbox - 1
        if kind & (UPARROW | DNARROW | VSLIDE | SIZER):
            rb += self.gl_wbox - 1
        if kind & (LFARROW | RTARROW | HSLIDE | SIZER):
            bb += self.gl_hbox - 1
        if wtype == WC_BORDER:
            lb, tb, rb, bb = -lb, -tb, -rb, -bb
        return word(x + lb), word(y + tb), word(w - lb - rb), word(h - tb - bb)

    # -- the message queue (event.c)
    def mq_put(self, msg):
        """Post a message: a WM_REDRAW joins an earlier one for the same
        window, a WM_ARROWED replaces an earlier one, a full queue drops."""
        msg = list(msg[:8])
        if msg[0] in (WM_REDRAW, WM_ARROWED):
            for om in self.gl_queue:
                if om[0] != msg[0]:
                    continue
                if msg[0] == WM_REDRAW:
                    if om[3] != msg[3]:
                        continue
                    r = Rect(*om[4:8])
                    rc_union(Rect(*msg[4:8]), r)
                    om[4:8] = r.tuple()
                    return
                om[:] = msg
                return
        if len(self.gl_queue) >= NUM_MSGS:
            return
        self.gl_queue.append(msg)

    def mq_get(self):
        """The oldest message, or None."""
        if not self.gl_queue:
            return None
        return self.gl_queue.pop(0)

    def ap_read(self, ap_id, length):
        """appl_read: (answer, the eight words the caller's buffer ends
        up holding).  Your own pipe only, and ONE message -- this pipe is
        messages and not bytes, and src/aes/appl.c says what keeping it
        that way cost."""
        if ap_id != 0 or length != AP_MSGBYTES:
            return 0, [0] * AP_MSGWORDS
        return 1, list(self.ev_mesag())

    def ap_sendmsg(self, type_, w3, w4, w5, w6, w7):
        self.mq_put([type_, 0, 0, w3, w4, w5, w6, w7])

    def ev_mesag(self):
        """evnt_mesag: the oldest message; with none pending the target
        polls forever, so the plan runs out."""
        m = self.mq_get()
        if m is None:
            # the target's first poll of an empty queue: no plan step, no
            # tick, but the control manager's turn -- a held arrow refills
            # the queue here
            self.ev_poll()
            m = self.mq_get()
        while m is None:
            self._step(lambda: False)
            m = self.mq_get()
        return m

    # -- ctrl.c: the control manager (gemctrl.c) ----------------------------
    # What a press on a window's frame does: the gadget's work, then one
    # message.  The arrows repeat from ct_arrow_repeat while the button
    # stays down, once the double-click time has passed.
    GL_WA = [WA_UPLINE, WA_DNLINE, WA_UPPAGE, WA_DNPAGE, 0,
             WA_LFLINE, WA_RTLINE, WA_LFPAGE, WA_RTPAGE]

    def ct_msgup(self, message, wh, m1, m2, m3, m4):
        if message:
            self.ap_sendmsg(message, wh, m1, m2, m3, m4)

    def handle_arrow_msg(self, wh, gadget):
        self.wm_update(END_UPDATE)
        self.ct_action = self.GL_WA[gadget - W_UPARROW]
        self.ap_sendmsg(WM_ARROWED, wh, self.ct_action, 0, 0, 0)
        self.ct_held = True
        self.ct_wh = wh
        self.ct_tick = self.gl_ticks
        self.wm_update(BEG_UPDATE)

    def ct_arrow_repeat(self):
        if not self.ct_held:
            return
        if not (self.button & 1):
            self.ct_held = False
            return
        if self.gl_ticks - self.ct_tick < self.gl_dclick:
            return
        self.ap_sendmsg(WM_ARROWED, self.ct_wh, self.ct_action, 0, 0, 0)

    def ct_arrow_stop(self):
        self.ct_held = False
        self.ct_wh = self.ct_action = 0
        self.ct_tick = 0

    def hctl_window(self, wh, mx, my):
        pwin = self.gl_win[wh]
        if wh != self.gl_wtop:
            self.ct_msgup(WM_TOPPED, wh, 0, 0, 0, 0)
            return
        message = 0
        need_normal = False
        self.w_bldactive(wh)
        saved, self.tree = self.tree, self.W_ACTIVE
        try:
            gadget = cpt = self.ob_find(W_BOX, MAX_DEPTH, mx, my)
            t = self.w_getsize(WS_CURR, wh)
            x, y, w, h = t.x, t.y, t.w, t.h
            kind = pwin.w_kind
            if cpt in (W_CLOSER, W_FULLER):
                if self.gr_watchbox(gadget, SELECTED, NORMAL):
                    message = WM_CLOSED if cpt == W_CLOSER else WM_FULLED
                    need_normal = True
            elif cpt == W_NAME:
                if kind & MOVER:
                    f = Rect(0, self.gl_hbox,
                             self.gl_rscreen.w + w - self.gl_wbox - 6,
                             MAX_COORDINATE)
                    x, y = self.gr_dragbox(w, h, x, y, f)
                    message = WM_MOVED
            elif cpt == W_SIZER:
                if kind & SIZER:
                    t = self.w_getsize(WS_WORK, wh)
                    t.x -= x
                    t.y -= y
                    t.w -= w
                    t.h -= h
                    wm, hm = self.gl_wchar, self.gl_hchar
                    if kind & (TGADGETS | HGADGETS):
                        wm = self.gl_wbox * 4
                    if kind & VGADGETS:
                        hm = self.gl_hbox * 6
                    w, h = self.gr_rubwind(x, y, wm, hm, t)
                    message = WM_SIZED
            elif cpt in (W_HSLIDE, W_VSLIDE, W_UPARROW, W_DNARROW,
                         W_LFARROW, W_RTARROW):
                if cpt in (W_HSLIDE, W_VSLIDE):
                    elev_x, elev_y = self.ob_offset(cpt + 1)
                    if cpt == W_HSLIDE:
                        if not (mx < elev_x):
                            cpt += 1
                    else:
                        if not (my < elev_y):
                            cpt += 1
                self.handle_arrow_msg(wh, cpt)
                return
            elif cpt in (W_HELEV, W_VELEV):
                message = WM_HSLID if cpt == W_HELEV else WM_VSLID
                x = self.gr_slidebox(cpt - 1, cpt, cpt == W_VELEV)
            if need_normal:
                self.ob_change(gadget, NORMAL, True)
        finally:
            self.tree = saved
        self.ct_msgup(message, wh, x, y, w, h)

    def hctl_button(self, mx, my):
        wh = self.wm_find(mx, my)
        if wh > 0:
            self.hctl_window(wh, mx, my)

    def hctl_rect(self):
        """What was chosen from the bar, and who hears about it.  An item
        in the Desk drop-down at or below gl_dafirst is an ACCESSORY's and
        gets AC_OPEN with the menu id in msg[4]; everything else is the
        application's MN_SELECTED with the item there.  AC_OPEN's msg[3]
        is the Desk TITLE's object index, which is where two pages of the
        Compendium have it wrong and both sources have it right.

        The model has one process, so there is nobody else to send an
        AC_OPEN to -- what it records is that one was sent, and with which
        words, which is what a gate comparing returned values can check."""
        if self.gl_mntree is None:
            return
        got = self.mn_do()
        if not got:
            return
        title, item = got
        if title == THEDESK and self.gl_accreg and item >= self.gl_dafirst:
            self.do_chg(title, SELECTED, False, True, True)
            self.ct_msgup(AC_OPEN, title, item - self.gl_dafirst, 0, 0, 0)
            return
        # WORDS 5, 6 AND 7: the tree the item came from, high word
        # first, then the box it is a child of.  With sub-menus the item
        # may not be in the menu bar's tree, and then the number alone
        # names nothing (MULTITOS GEMCTRL.C splits the pointer this way).
        self.ct_msgup(MN_SELECTED, title, item,
                      (self.mn_tree >> 16) & 0xFFFF, self.mn_tree & 0xFFFF,
                      self.mn_menu)

    def ct_mouse(self, grabit):
        """The control manager takes the mouse for the menu: the pointer
        forced on, and the application's hide count put back after."""
        if grabit:
            self.gl_ctmown = True
            self.ct_tmpmoff = self.gsx_mforce()
        else:
            self.gsx_munforce(self.ct_tmpmoff)
            self.gl_ctmown = False

    # -- form.c: form_do, form_dial -----------------------------------------
    def fm_own(self, beg_ownit):
        if beg_ownit:
            if self.ml_ocnt == 0:
                self.ml_ctrl = self.get_ctrl()
                self.ct_chgown(self.gl_rscreen)
            self.ml_ocnt += 1
        else:
            self.ml_ocnt -= 1
            if self.ml_ocnt == 0:
                self.ct_chgown(self.ml_ctrl)

    def ob_fs(self, obj):
        o = self.tree[obj]
        return o.ob_state, o.ob_flags

    def find_obj(self, start_obj, which):
        obj, flag, inc = 0, EDITABLE, 1
        if which == BACKWARD:
            inc = -1
            obj = start_obj + inc
        elif which == FORWARD:
            obj = start_obj + inc
        elif which == DEFLT:
            flag = DEFAULT
        while obj >= 0:
            state, theflag = self.ob_fs(obj)
            if not (theflag & HIDETREE) and not (state & DISABLED):
                if theflag & flag:
                    return obj
            if theflag & LASTOB:
                obj = -1
            else:
                obj += inc
        return start_obj

    def fm_inifld(self, start_fld):
        if start_fld == 0:
            start_fld = self.find_obj(0, FORWARD)
        return start_fld

    def fm_keybd(self, obj, ch):
        """-> (cont, ch, new_obj); new_obj is None when untouched, as
        the C leaves *pnew_obj alone."""
        direction = -1
        new_obj = None
        if ch in (RETURN, ENTER):
            obj = 0
            direction = DEFLT
        elif ch == ARROW_UP:
            direction = BACKWARD
        elif ch in (TAB, ARROW_DOWN):
            direction = FORWARD
        if direction != -1:
            ch = 0
            new_obj = self.find_obj(obj, direction)
            if direction == DEFLT and new_obj != 0:
                st = self.tree[new_obj].ob_state
                self.ob_change(new_obj, (st | SELECTED) & 0xFFFF, True)
                return 0, ch, new_obj
        return 1, ch, new_obj

    def fm_button(self, new_obj, clks):
        """-> (cont, new_obj | orword)"""
        cont = True
        orword = 0
        state, flags = self.ob_fs(new_obj)
        if flags & TOUCHEXIT:
            if clks == 2:
                orword = 0x8000
            cont = False
        if (flags & SELECTABLE) and not (state & DISABLED):
            if flags & RBUTTON:
                parent = self.ob_get_par(new_obj)
                tobj = self.tree[parent].ob_head
                while tobj != parent:
                    tstate, tflags = self.ob_fs(tobj)
                    if (tflags & RBUTTON) and ((tstate & SELECTED)
                                               or tobj == new_obj):
                        if tobj == new_obj:
                            tstate |= SELECTED
                            state = tstate
                        else:
                            tstate &= ~SELECTED
                        self.ob_change(tobj, tstate & 0xFFFF, True)
                    tobj = self.tree[tobj].ob_next
            else:
                if self.gr_watchbox(new_obj, state ^ SELECTED, state):
                    state ^= SELECTED
            if cont and (flags & (SELECTABLE | EDITABLE)):
                self.ev_button(1, 0x0001, 0x0000, [0] * 6)
        if (state & SELECTED) and (flags & EXIT):
            cont = False
        if cont and not (flags & EDITABLE):
            new_obj = 0
        return int(cont), word(new_obj | orword)

    def fm_do(self, start_fld):
        self.fm_own(True)
        self.ev_fq()
        self.gsx_sclip(self.gl_rfull)
        next_obj = self.fm_inifld(start_fld)
        edit_obj = 0
        idx = 0
        cont = True
        while cont:
            if next_obj != 0 and edit_obj != next_obj:
                edit_obj = next_obj
                next_obj = 0
                idx, _ = self.ob_edit(edit_obj, 0, idx, EDINIT)
            rets = [0] * 6
            which = self.ev_multi(MU_KEYBD | MU_BUTTON, None, None, 0,
                                  0x0002FF01, rets)
            if which & MU_KEYBD:
                cont, ch, nxt = self.fm_keybd(edit_obj, rets[4])
                if nxt is not None:
                    next_obj = nxt
                if ch:
                    idx, _ = self.ob_edit(edit_obj, ch, idx, EDCHAR)
            if which & MU_BUTTON:
                next_obj = self.ob_find(ROOT, MAX_DEPTH, rets[0], rets[1])
                if next_obj == NIL:
                    next_obj = 0        # GEM rings the bell here
                else:
                    cont, next_obj = self.fm_button(next_obj, rets[5])
            if not cont or (next_obj != 0 and next_obj != edit_obj):
                idx, _ = self.ob_edit(edit_obj, 0, idx, EDEND)
        self.fm_own(False)
        return next_obj

    def fm_dial(self, fmd_type, pi, pt):
        self.gsx_sclip(self.gl_rscreen)
        if fmd_type == FMD_GROW:
            self.gr_growbox(pi, pt)
        elif fmd_type == FMD_SHRINK:
            self.gr_shrinkbox(pi, pt)
        elif fmd_type == FMD_FINISH:
            # the desktop under the dialog, then WM_REDRAW to every window
            # the dialog covered (w_update clips its rectangle in place)
            self.w_drawdesk(pt)
            self.w_update(DESKWH, pt.copy(), DESKWH, False)
        return 1

    def form_keybd(self, obj, ch, nxt):
        """-> (cont, ch, next_obj), with the runner's own defaults for
        the outputs the C leaves untouched."""
        self.gsx_sclip(self.gl_rfull)
        cont, ch, new = self.fm_keybd(obj, ch)
        return cont, ch, nxt if new is None else new

    def form_button(self, obj, clks):
        self.gsx_sclip(self.gl_rfull)
        return self.fm_button(obj, clks)

    # -- fsel.c: the file selector (gemfslib.c) ---------------------------
    # The tree is the one tools/fselrsc.py describes, fixed up at the pool
    # mark the way rs_fixit leaves it (tools/rsc.py expect()), so every
    # address in it is the target's; the work area follows it as fsel.c
    # lays it out.  The names are plain strings here where the target has
    # far slots, and the directory read is a lookup in self.dirs where the
    # target has CIO -- and the frames the target spends reading are frames
    # the plan's settles cover, since this side reads in no time.
    # -- form_alert (src/aes/alert.c, EmuTOS aes/gemfmalt.c) -----------
    AL_MAX_LINENUM, AL_MAX_LINELEN = 5, 40
    AL_MAX_BUTNUM, AL_MAX_BUTLEN = 3, 20
    AL_NUM_OBJS, AL_MSGOFF, AL_BUTOFF = 10, 2, 7

    def _al_strbrk(self, tree, start, maxnum, maxlen, alert, texts):
        """The donor's fm_strbrk: break at | and ], a doubled one being a
        literal.  Returns (rest, count, longest)."""
        def endsub(c):
            return c in ("|", "]", "")
        i, longest = 0, 0
        if alert[:1] == "[":
            alert = alert[1:]
        for i in range(maxnum):
            out = []
            while len(out) < maxlen:
                c = alert[:1]
                if endsub(c):
                    if c and alert[1:2] == c:
                        alert = alert[1:]       # || or ]]: a literal one
                    else:
                        break
                out.append(alert[:1])
                alert = alert[1:]
            texts[start + i].s = "".join(out)
            longest = max(longest, len(out))
            while not endsub(alert[:1]):        # a substring that was too long
                alert = alert[1:]
            if alert[:1] in ("]", ""):
                break
            alert = alert[1:]
        while alert[:1] not in ("]", ""):
            alert = alert[1:]
        return alert[1:], min(i + 1, maxnum), longest

    lang = None          # what LANG.RSC says, when a gate hands it over

    # form_error's map from a DOS error to a string of LANG.RSC
    # (src/aes/alert.c's fm_error, the donor's gemfmlib.c).
    FM_ERRSTR = {2: "ERRFILE", 3: "ERRFILE", 18: "ERRFILE", 4: "ERRDOCS",
                 5: "ERREXIST", 15: "ERRDRIVE", 8: "ERRMEM", 10: "ERRMEM",
                 11: "ERRMEM"}

    def fm_error(self, n, strings=None):
        """form_error: the alert for a DOS error number.  The texts are
        the system's, not the application's, so they come from what
        tools/langrsc.py describes -- or from `strings`/`self.lang`, when
        a gate is proving that a LANG.RSC on the disk is the one being
        read.  The number is written over the two characters after the
        '#', which is what the target does."""
        if n > 63:
            return False
        texts = dict(strings) if strings else self.lang
        if texts is None:
            import langrsc
            texts = dict(langrsc.STRINGS)
        name = self.FM_ERRSTR.get(n, "ERRTOS")
        s = texts[name]
        if name == "ERRTOS":
            h = s.find("#")
            if h >= 0 and len(s) >= h + 3:
                s = s[:h + 1] + "%02d" % n + s[h + 3:]
        return self.fm_alert(1, s) != 1

    def fm_alert(self, defbut, alstr):
        """form_alert: the string parsed into a ten-object tree, built in
        character cells, drawn, and the button pressed returned (1..3).
        The tree and its strings are the pool's, as the target's are."""
        assert self.pool_mark is not None, "run(..., pool=) names the pool"
        base = self.pool_mark
        wc, hc = self.gl_wchar, self.gl_hchar
        tree = [Obj(NIL, NIL, NIL, G_STRING, NONE, NORMAL, 0, 0, 0, 0, 0)
                for _ in range(self.AL_NUM_OBJS)]
        # the string buffers, where the pool puts them: after the objects
        addr = base + OBJ_SIZE * self.AL_NUM_OBJS
        texts = {}
        for i in range(self.AL_MAX_LINENUM):
            texts[self.AL_MSGOFF + i] = Text("", self.AL_MAX_LINELEN + 1)
        for i in range(self.AL_MAX_BUTNUM):
            texts[self.AL_BUTOFF + i] = Text("", self.AL_MAX_BUTLEN + 1)
        for obj, t in sorted(texts.items()):
            self.mem[addr] = t
            tree[obj].ob_spec = addr
            addr += t.size + (t.size & 1)
        tree[ROOT].ob_type = G_BOX
        tree[ROOT].ob_flags = NONE          # LASTOB goes on the last button
        tree[ROOT].ob_spec = 0x00011100     # the donor's DIALERT root
        tree[ROOT].ob_state = OUTLINED
        tree[1].ob_type = G_IMAGE
        for i in range(self.AL_MAX_BUTNUM):
            tree[self.AL_BUTOFF + i].ob_type = G_BUTTON

        # parse: [icon][line|line][button|button]
        icnum = ord(alstr[1]) - ord("0")
        rest, nummsg, mlenmsg = self._al_strbrk(
            tree, self.AL_MSGOFF, self.AL_MAX_LINENUM, self.AL_MAX_LINELEN,
            alstr[3:], texts)
        _, numbut, mlenbut = self._al_strbrk(
            tree, self.AL_BUTOFF, self.AL_MAX_BUTNUM, self.AL_MAX_BUTLEN,
            rest, texts)
        mlenbut += 1                    # half a character each side

        # build, in character cells (the donor's fm_build)
        al = Rect(0, 0, 1, 1)
        ms = Rect(1, 1, mlenmsg, 1)
        bt = Rect(1, 2 + nummsg, mlenbut, 1)
        ic = Rect(0, 0, 0, 0)
        if icnum:
            hicon = (gemdata.ICON_HL + hc - 1) // hc
            ic = Rect(1, 1, 4, hicon)
            al.w += ic.w + 1
            ms.x = ic.x + ic.w + 1
        allbut = numbut * mlenbut + 2 * (numbut - 1)
        if mlenmsg + al.w > allbut + 1:
            al.w += mlenmsg + 1
            bt.x = (al.w - allbut) // 2
        else:
            al.w = allbut + 2
            bt.x = 1
        bt.y = max(ic.y + ic.h, nummsg + 1) + 1
        al.h = max(bt.y + bt.h, ic.y + ic.h) + 1

        def setxywh(obj, r):
            o = tree[obj]
            o.ob_x, o.ob_y, o.ob_width, o.ob_height = r.x, r.y, r.w, r.h

        setxywh(ROOT, al)
        for o in tree:
            o.ob_next = o.ob_head = o.ob_tail = NIL
        with self.on_tree(tree):
            if icnum:
                setxywh(1, ic)
                self.ob_add(tree, ROOT, 1)
            for i in range(nummsg):
                setxywh(self.AL_MSGOFF + i, ms)
                ms.y += 1
                self.ob_add(tree, ROOT, self.AL_MSGOFF + i)
            for i in range(numbut):
                o = tree[self.AL_BUTOFF + i]
                o.ob_flags = SELECTABLE | EXIT
                o.ob_state = NORMAL
                setxywh(self.AL_BUTOFF + i, bt)
                bt.x += mlenbut + 2
                self.ob_add(tree, ROOT, self.AL_BUTOFF + i)
            tree[self.AL_BUTOFF + numbut - 1].ob_flags |= LASTOB

            # character cells to pixels, as rs_obfix does
            for o in tree:
                o.ob_x *= wc
                o.ob_y *= hc
                o.ob_width = (self.gl_width if o.ob_width == 80
                              else o.ob_width * wc)
                o.ob_height *= hc

            if 1 <= defbut <= numbut:
                tree[self.AL_BUTOFF + defbut - 1].ob_flags |= DEFAULT

            if icnum:
                icnum = icnum if 1 <= icnum <= 3 else 3
                name = gemdata.ICON_NAMES[icnum - 1]
                bits = gemdata.icon_bytes(name)
                self.mem[addr] = bits
                self.mem[addr + 1] = Bitblk(addr, gemdata.ICON_WB,
                                            gemdata.ICON_HL, 0, 0, BLACK)
                tree[1].ob_spec = addr + 1
                tree[1].ob_width = tree[1].ob_height = gemdata.ICON_HL

            self.gr_mouse(ARROW)
            d = Rect(*self.ob_center())
            # where the buttons landed, on the screen, for a harness that
            # wants to click one: the model says where the AES puts them
            root = tree[ROOT]
            self.alert_buttons = [
                Rect(root.ob_x + tree[self.AL_BUTOFF + i].ob_x,
                     root.ob_y + tree[self.AL_BUTOFF + i].ob_y,
                     tree[self.AL_BUTOFF + i].ob_width,
                     tree[self.AL_BUTOFF + i].ob_height)
                for i in range(numbut)]
            rc_intersect(self.gl_rscreen, d)

            self.wm_update(BEG_UPDATE)
            t = self.gsx_gclip()
            self.bb_save(d)
            self.gsx_sclip(d)
            self.ob_draw(ROOT, MAX_DEPTH)
            i = self.fm_do(0)
            self.gsx_sclip(d)
            self.bb_restore(d)
            self.gsx_sclip(t)
            self.wm_update(END_UPDATE)
        return i - self.AL_BUTOFF + 1

    def fs_input(self, path, sel, label=None):
        """-> (ret, button, path, sel), the buffers as the target leaves
        them.  `path` and `sel` are str; `label` None for fsel_input."""
        import fselrsc
        from fselrsc import (FSTITLE, FSDIRECT, FSSELECT, FS1STDRV, FCLSBOX,
                             FTITLE, SCRLBAR, FUPAROW, FDNAROW, FSVSLID,
                             FSVELEV, FILEBOX, F1NAME, F9NAME, FSOK, FSCANCEL,
                             NM_DRIVES, NM_NAMES)
        assert self.pool_mark is not None, "run(..., pool=) names the pool"
        R = fselrsc.build()
        base = self.pool_mark
        image, trees, mem = R.expect(base, self.gl_wchar, self.gl_hchar,
                                     self.gl_width)
        tree = trees[0]
        self.mem.update(mem)
        work = base + len(image)                 # g_fslist, then the paths
        LEN_FSPATH = fselrsc.LEN_DIRECT + 9
        locstr = Text("", LEN_FSPATH)
        locold = Text("", LEN_FSPATH)
        mask = Text("", LEN_FSPATH)
        self.mem[work + 128] = locstr
        self.mem[work + 128 + LEN_FSPATH] = locold
        self.mem[work + 128 + 2 * LEN_FSPATH] = mask
        if label is not None:
            self.mem[base - 2] = Text(label)     # the caller's, somewhere
        ted = lambda obj: self.mem[tree[obj].ob_spec]           # noqa: E731
        text = lambda obj: self.mem[ted(obj).ptext]              # noqa: E731

        def inf_sset(obj, s):
            text(obj).s = s[:ted(obj).txtlen - 1]

        def inf_what(ok):
            for field in range(2):
                if tree[ok + field].ob_state & SELECTED:
                    tree[ok + field].ob_state = NORMAL
                    return 1 if field == 0 else 0
            return -1

        def path_changed(p):
            n = ted(FSDIRECT).txtlen - 1
            return p[:n] != text(FSDIRECT).s[:n]

        def get_drive(p):
            d = fs_drive_number(p)
            return d if d >= 0 else 0

        def drive_path(drive):
            locstr.s = chr(ord("A") + drive) + ":\\" + mask.s

        def set_mask():
            p, pend = fs_pspec(locstr.s)
            if pend == len(p):
                p += "*.*"
            locstr.s = p[:LEN_FSPATH - 1]
            mask.s = locstr.s[pend:][:LEN_FSPATH - 1]

        def select_drive(drive, redraw):
            if not 0 <= drive < NM_DRIVES:
                return
            old = -1
            for i in range(NM_DRIVES):
                o = tree[FS1STDRV + i]
                if o.ob_state & SELECTED:
                    o.ob_state &= ~SELECTED
                    old = i
            tree[FS1STDRV + drive].ob_state |= SELECTED
            if redraw and drive != old:
                if old >= 0:
                    self.ob_draw(FS1STDRV + old, MAX_DEPTH)
                self.ob_draw(FS1STDRV + drive, MAX_DEPTH)

        names = []

        def fs_active(ppath, pspec):
            # the directory's CIO name is the key: "D1:" on DOS 2,
            # "D1:>" or "D1:>SUB>" on a SpartaDOS; a folder is listed
            # whatever the mask, and sorts first, its flag being lower
            allpath, pend = fs_pspec(ppath)
            allpath = allpath[:pend] + "*.*"
            key = fs_cioname(allpath, self.dos_dirsep)[:-3]
            listing = self.dirs.get(key)
            if listing is None:
                return False, []
            found = []
            for e in listing:
                flag, n = fs_flagged(e)
                if flag == FS_FOLDER or fs_wildcmp(pspec, n):
                    found.append(flag + n)
            return True, sorted(found[:64])

        def fs_1scroll(curr, count, touchob):
            newcurr = curr - 1 if touchob == FUPAROW else curr + 1
            if newcurr < 0:
                newcurr += 1
            if count - newcurr < NM_NAMES:
                newcurr -= 1
            return newcurr if count > NM_NAMES else curr

        def fs_format(currtop, count):
            cnt = min(count - currtop, NM_NAMES)
            for i in range(NM_NAMES):
                name = (names[currtop + i][0] + fs_fmt_str(names[currtop + i][1:])
                        if i < cnt else " ")
                inf_sset(F1NAME + i, name)
                tree[F1NAME + i].ob_type = G_FBOXTEXT
                tree[F1NAME + i].ob_state = NORMAL
            y = 0
            th = h = tree[FSVSLID].ob_height
            if count > NM_NAMES:
                h = max(mul_div_round(NM_NAMES, h, count), self.gl_hbox)
                y = mul_div_round(currtop, th - h, count - NM_NAMES)
            tree[FSVELEV].ob_y, tree[FSVELEV].ob_height = y, h

        def fs_sel(sel, state):
            if sel:
                self.ob_change(F1NAME + sel - 1, state, True)

        def fs_nscroll(sel, curr, count, touchob, n):
            newcurr = curr
            for _ in range(n):
                newcurr = fs_1scroll(newcurr, count, touchob)
            diffcurr = newcurr - curr
            if diffcurr:
                curr = newcurr
                fs_sel(sel, NORMAL)
                sel = 0
                fs_format(curr, count)
                r1 = self.gsx_gclip()
                r0 = self.ob_actxywh(F1NAME)
                neg = diffcurr < 0
                diffcurr = abs(diffcurr)
                if diffcurr < NM_NAMES:
                    sy = r0.y + r0.h * diffcurr
                    dy = r0.y
                    if neg:
                        sy, dy = r0.y, sy
                    self.bb_screen(r0.x, sy, r0.x, dy, r0.w,
                                   r0.h * (NM_NAMES - diffcurr))
                    if not neg:
                        r0.y += r0.h * (NM_NAMES - diffcurr)
                else:
                    diffcurr = NM_NAMES
                r0.h *= diffcurr
                for i, r in enumerate((r0, r1)):
                    self.gsx_sclip(r)
                    self.ob_draw(FSVSLID if i else FILEBOX, MAX_DEPTH)
            return sel, curr

        def fs_newdir():
            self.ob_draw(FSDIRECT, MAX_DEPTH)
            ok, found = fs_active(locstr.s, mask.s)
            if not ok:
                return False, 0
            names[:] = found
            fs_format(0, len(names))
            ted(FTITLE).ptext = work + 128 + 2 * LEN_FSPATH
            for obj in (FTITLE, FILEBOX, SCRLBAR):
                self.ob_draw(obj, MAX_DEPTH)
            return True, len(names)

        with self.on_tree(tree):
            if not path:
                path = "A:\\*.*"
            # fs_start's widths, on this copy
            rfs = Rect(*self.ob_center())
            diff = tree[SCRLBAR].ob_width - self.gl_wbox
            tree[FTITLE].ob_width -= diff
            for obj in (SCRLBAR, FUPAROW, FDNAROW, FSVSLID, FSVELEV):
                tree[obj].ob_width = self.gl_wbox
            locstr.s = path[:LEN_FSPATH - 1]
            locold.s = locstr.s
            set_mask()
            ted(FTITLE).ptext = work + 128 + 2 * LEN_FSPATH
            inf_sset(FSDIRECT, locstr.s)
            selname = fs_fmt_str(sel)
            inf_sset(FSSELECT, selname)
            selname = " " + selname
            if label is not None:
                tree[FSTITLE].ob_spec = base - 2
            tree[FSTITLE].ob_x = ((tree[ROOT].ob_width
                                   - len(self.mem[tree[FSTITLE].ob_spec].s)
                                   * self.gl_wchar) // 2)
            for drive in range(NM_DRIVES):
                if self.gl_drvbits & (1 << drive):
                    tree[FS1STDRV + drive].ob_state &= ~DISABLED
                else:
                    tree[FS1STDRV + drive].ob_state |= DISABLED
            select_drive(get_drive(locstr.s), False)
            self.gsx_sclip(rfs)
            self.fm_dial(FMD_START, self.gl_rcenter, rfs)
            self.ob_draw(ROOT, 2)

            curr = count = sel = 0
            newsel = newdrive = False
            cont = newlist = True
            error = 0
            while cont:
                touchob = 0 if newlist else self.fm_do(FSSELECT)
                _, mx, my = self.gsx_mouse()
                if newlist:
                    fs_sel(sel, NORMAL)
                    inf_sset(FSDIRECT, locstr.s)
                    p, pend = fs_pspec(locstr.s)
                    locstr.s = p[:pend] + mask.s
                    curr = sel = 0
                    newlist = False
                    ok, count = fs_newdir()
                    error = 0 if ok else error + 1
                    if error == 1:
                        newlist = True
                        if locstr.s != locold.s:
                            locstr.s = locold.s
                        else:
                            drive_path(0)
                        select_drive(get_drive(locstr.s), True)
                    locold.s = locstr.s
                value = 0
                dclkret = (touchob & 0x8000) != 0
                touchob &= 0x7FFF
                if touchob == FSOK and path_changed(locstr.s):
                    self.ob_change(FSOK, NORMAL, True)
                elif touchob in (FSOK, FSCANCEL):
                    cont = False
                elif touchob in (FUPAROW, FDNAROW):
                    value = 1
                elif touchob in (FSVSLID, FSVELEV):
                    pt = self.ob_actxywh(FSVELEV)
                    if touchob == FSVSLID and not inside(mx, my, pt):
                        touchob = FUPAROW if my <= pt.y else FDNAROW
                        value = NM_NAMES
                    else:
                        self.fm_own(True)
                        value = self.gr_slidebox(FSVSLID, FSVELEV, True)
                        self.fm_own(False)
                        value = curr - mul_div_round(value, count - NM_NAMES, 1000)
                        if value >= 0:
                            touchob = FUPAROW
                        else:
                            touchob = FDNAROW
                            value = -value
                elif F1NAME <= touchob <= F9NAME:
                    fnum = touchob - F1NAME + 1
                    if fnum <= count:
                        if sel and sel != fnum:
                            fs_sel(sel, NORMAL)
                        if sel != fnum:
                            sel = fnum
                            fs_sel(sel, SELECTED)
                        selname = text(touchob).s
                        if selname[0] == " ":
                            newsel = True
                            if dclkret:
                                cont = False
                        else:
                            p, pend = fs_pspec(locstr.s)
                            locstr.s = (p[:pend] + fs_unfmt_str(selname[1:])
                                        + "\\" + mask.s)
                            newlist = True
                elif touchob == FCLSBOX:
                    p, pos = fs_back(locstr.s)
                    if pos != 0 and p[pos - 1] != ":":
                        _, pend = fs_pspec(p, pos - 1)
                        locstr.s = p[:pend] + mask.s
                        newlist = True
                else:
                    drive = touchob - FS1STDRV
                    if (0 <= drive < NM_DRIVES and drive != get_drive(locstr.s)
                            and not path_changed(locstr.s)
                            and not tree[touchob].ob_state & DISABLED):
                        drive_path(drive)
                        newdrive = True

                if touchob == FSCANCEL:
                    break
                if not newlist and not newdrive and path_changed(locstr.s):
                    if get_drive(text(FSDIRECT).s) != get_drive(locstr.s):
                        newdrive = True
                    else:
                        newlist = True
                    locstr.s = text(FSDIRECT).s
                if newdrive:
                    select_drive(touchob - FS1STDRV, True)
                    newdrive = False
                    newlist = True
                if newlist:
                    inf_sset(FSDIRECT, locstr.s)
                    set_mask()
                    if not error:
                        selname = selname[:1]
                        newsel = True
                if newsel:
                    text(FSSELECT).s = selname[1:]
                    self.ob_draw(FSSELECT, MAX_DEPTH)
                    if not cont:
                        self.ob_change(FSOK, SELECTED, True)
                    newsel = False
                if value:
                    sel, curr = fs_nscroll(sel, curr, count, touchob, value)

            path = locstr.s
            sel = fs_unfmt_str(text(FSSELECT).s)
            self.fm_dial(FMD_FINISH, self.gl_rcenter, rfs)
            button = inf_what(FSOK)
        return 1, button, path, sel

    # -- menu.c: the menu library (gemmnlib.c) ----------------------------
    # The bar's objects sit at fixed indices; a title's drop-down is the
    # sibling as many along the drop-down box's chain as the title is
    # along the active bar's.  These work on self.tree, as the object
    # library does; mn_do runs on the bar that menu_bar showed, whichever
    # tree the application's wait was called with.
    @contextlib.contextmanager
    def on_tree(self, tree):
        saved, self.tree = self.tree, tree
        try:
            yield
        finally:
            self.tree = saved

    def mn_init(self):
        self.gl_mntree = None
        self.gl_ctwait.m_out = False
        self.gl_ctwait.m_gr = self.gl_rmenu.copy()
        if not hasattr(self, "gl_smi"):
            self.gl_smi = [{"tree": 0, "menu": 0, "start": 0, "count": 0}
                           for _ in range(NUM_SMI)]

    def menu_sub(self, ititle):
        tree = self.tree
        themenus = tree[THESCREEN].ob_tail
        imenu = tree[themenus].ob_head
        for _ in range(ititle - THEACTIVE - 1):
            imenu = tree[imenu].ob_next
        return imenu

    def menu_fixup(self):
        """The Desk drop-down's chain rebuilt for the accessories that
        have registered a name: the application's item, then -- if there
        are any -- the separator and one item per name, in slot order.
        The chain is destroyed and rebuilt BY INDEX over the RCS's own
        dabox+1..dabox+8, which is why the resource must carry exactly
        eight children whether they are used or not.  The height is
        recomputed and the width is not: a title too long for the box the
        resource drew is clipped, and the resource is where its width was
        decided."""
        tree = self.gl_mntree
        if tree is None:
            return
        themenus = tree[THESCREEN].ob_tail
        dabox = tree[themenus].ob_head
        tree[dabox].ob_head = tree[dabox].ob_tail = NIL
        self.gl_dafirst = dabox + 3
        cnt = (2 + self.gl_accreg) if self.gl_accreg else 1
        slot, height = 0, 0
        for i in range(1, cnt + 1):
            ob = dabox + i
            self.ob_add(tree, dabox, ob)
            if i > 2:                       # the names, after the separator
                while slot < NUM_ACCS and self.gl_acctitle[slot] is None:
                    slot += 1
                if slot >= NUM_ACCS:
                    break
                tree[ob].ob_spec = self.gl_acctitle[slot]
                slot += 1
            height += self.gl_hchar
        tree[dabox].ob_height = height

    def rect_change(self, pmo, iob, x):
        pmo.m_gr = self.ob_actxywh(iob)
        pmo.m_out = x

    def do_chg(self, iitem, chgvalue, dochg, dodraw, chkdisabled):
        """A state bit set or cleared, redrawn with the clip off if
        dodraw; False, and nothing done, for a disabled object when
        chkdisabled."""
        curr = self.tree[iitem].ob_state
        if chkdisabled and (curr & DISABLED):
            return False
        if dochg:
            curr |= chgvalue
        else:
            curr &= ~chgvalue
        if dodraw:
            self.gsx_sclip(self.gl_rzero)
        self.ob_change(iitem, curr, dodraw)
        return True

    @staticmethod
    def item_changed(last_item, cur_item):
        return last_item != NIL and last_item != cur_item

    def menu_select(self, last_item, cur_item, setit):
        if self.item_changed(last_item, cur_item):
            return self.do_chg(last_item, SELECTED, setit, True, True)
        return False

    def menu_sr(self, saveit, imenu):
        """What is under a drop-down saved or put back, one pixel of
        frame included left, right and below -- unclipped, as the donor
        has it; the VDI clips the copy to the screen."""
        self.gsx_sclip(self.gl_rzero)
        t = self.ob_actxywh(imenu)
        t.x -= MENU_THICKNESS
        t.w += 2 * MENU_THICKNESS
        t.h += 2 * MENU_THICKNESS
        if saveit:
            self.bb_save(t)
        else:
            self.bb_restore(t)

    def popup_place(self, imenu, istart, x, y):
        """The box on the screen.  x and y name where the START ITEM
        goes, so the item's own offset comes off first; the parent's
        origin comes off too, because both donors clamp ob_x/ob_y
        against the screen as if the box hung off the root.  Then it is
        clamped both ways -- the ROM clamps neither, its submenu path
        clamps both, and a popup off an edge is unusable (src/aes/menu.c
        has the argument)."""
        t = self.tree
        w, h = t[imenu].ob_width, t[imenu].ob_height
        ox, oy = self.ob_offset(imenu)
        ox -= t[imenu].ob_x
        oy -= t[imenu].ob_y
        bx = x
        by = y - t[istart].ob_y
        while bx + w + MENU_THICKNESS > self.gl_width:
            bx -= self.gl_wchar
        while bx < MENU_THICKNESS:
            bx += self.gl_wchar
        while by > self.gl_height - h:
            by -= self.gl_hchar
        while by < self.gl_rfull.y:
            by += self.gl_hchar
        t[imenu].ob_x = bx - ox
        t[imenu].ob_y = by - oy

    def popup_track(self, imenu, istart):
        """The item under the pointer when a press comes, or NIL."""
        t = self.tree
        cur = NIL
        if not (t[istart].ob_state & DISABLED):
            cur = istart
        if cur != NIL:
            self.do_chg(cur, SELECTED, True, False, True)
        self.gsx_sclip(self.gl_rzero)
        self.ob_draw(imenu, MAX_DEPTH)
        m = MOBLK(False, 0, 0, 0, 0)
        rets = [0] * 6
        while True:
            self.rect_change(m, cur if cur != NIL else imenu, cur != NIL)
            which = self.ev_multi(MU_BUTTON | MU_M1, m, None, 0,
                                  0x0001FF01, rets)
            last = cur
            cur = self.ob_find(imenu, 1, rets[0], rets[1])
            if cur == imenu:
                cur = NIL
            self.menu_select(last, cur, False)
            self.menu_select(cur, last, True)
            if which & MU_BUTTON:
                break
        if cur != NIL:
            self.do_chg(cur, SELECTED, False, False, False)
        return cur

    def mn_popup(self, tree, imenu, istart, scroll, x, y):
        """menu_popup: (answer, the out block as the runner reports it).
        On FALSE only the keystate is written -- both donors agree, and
        the runner seeds the other four so that is visible."""
        out = [-2, -3, -4, -1, 0]       # menu, item, scroll, keystate, tree
        # seeded as the runner seeds them: words the call cannot produce
        if not tree or imenu <= 0:
            out[3] = 0
            return 0, out
        with self.on_tree(tree):
            if istart < 0:
                istart = self.tree[imenu].ob_head
            if istart <= 0:
                out[3] = 0
                return 0, out
            self.wm_update(BEG_MCTRL)
            self.ev_button(1, 0x00FF, 0x0000, [0] * 6)
            self.popup_place(imenu, istart, x, y)
            self.menu_sr(True, imenu)
            chosen = self.popup_track(imenu, istart)
            self.menu_sr(False, imenu)
            out[3] = self.kstate
            if chosen != NIL:
                out[0], out[1], out[2], out[4] = imenu, chosen, scroll, 1
            self.ev_button(1, 0x00FF, 0x0000, [0] * 6)
            self.wm_update(END_MCTRL)
        return (1 if chosen != NIL else 0), out

    # ---- sub-menus: menu_attach and menu_istart -----------------------
    # The mark is the ROM's: a right-arrow character two bytes from the
    # end of the item's own string, the SUBMENU flag, and the slot number
    # in ob_type's HIGH byte from 128 up.  src/aes/menu.c has the
    # reasoning and the limits; this follows it line for line.

    def tree_addr(self, tree):
        """Where a tree is staged: MN_SELECTED's words 5 and 6."""
        for a, t in self.trees.items():
            if t is tree:
                return a
        return 0

    def smi_at(self, n):
        if n < SMI_BASE or n >= SMI_BASE + NUM_SMI:
            return None
        s = self.gl_smi[n - SMI_BASE]
        return s if s["tree"] else None

    def smi_of(self, tree, item):
        if not (tree[item].ob_flags & SUBMENU):
            return None
        return self.smi_at((tree[item].ob_type >> 8) & 0xFF)

    def smi_find(self, addr, imenu):
        for s in self.gl_smi:
            if s["tree"] == addr and s["menu"] == imenu:
                return s
        return None

    def sm_mark(self, tree, item, ch):
        """The arrow into the item's own string, where the ROM puts it:
        two bytes from the end.  The target writes one byte through the
        address in ob_spec; here the staged Text is edited, which is the
        same string seen from the host side."""
        p = tree[item].ob_spec
        if tree[item].ob_flags & INDIRECT:
            p = self.mem[p]
        t = self.mem.get(p)
        if t is None or not isinstance(t, Text) or len(t.s) < SM_ARROWOFF:
            return False
        n = len(t.s)
        t.s = t.s[:n - SM_ARROWOFF] + chr(ch) + t.s[n - SM_ARROWOFF + 1:]
        return True

    def sm_detach(self, tree, item):
        s = self.smi_of(tree, item)
        self.sm_mark(tree, item, 0x20)
        tree[item].ob_type &= 0x00FF
        tree[item].ob_flags &= ~SUBMENU
        if s:
            s["count"] -= 1
            if s["count"] <= 0:
                s["tree"] = 0

    def mn_attach(self, flag, tree, item, md):
        """md is [treeaddr, menu, start, scroll]; answers (ok, md)."""
        md = list(md)
        if not tree or item <= 0:
            return 0, md
        if (tree[item].ob_type & 0x00FF) != G_STRING:
            return 0, md
        if flag == ME_INQUIRE:
            s = self.smi_of(tree, item)
            if not s:
                return 0, md
            return 1, [s["tree"], s["menu"], s["start"], 0]
        if flag not in (ME_ATTACH, ME_REMOVE):
            return 0, md
        if tree[item].ob_flags & SUBMENU:
            self.sm_detach(tree, item)
        if flag == ME_REMOVE:
            return 1, md
        if not md[0] or md[1] <= 0:
            return 0, md
        s = self.smi_find(md[0], md[1])
        if not s:
            s = next((x for x in self.gl_smi if not x["tree"]), None)
            if not s:
                return 0, md
            s["tree"], s["menu"], s["count"] = md[0], md[1], 0
        if not self.sm_mark(tree, item, SM_ARROW):
            if s["count"] <= 0:
                s["tree"] = 0
            return 0, md
        st = self.trees[s["tree"]]
        start = max(st[s["menu"]].ob_head, min(md[2], st[s["menu"]].ob_tail))
        s["start"] = start
        md[2] = start
        s["count"] += 1
        tree[item].ob_type = (tree[item].ob_type & 0x00FF) | \
                             ((SMI_BASE + self.gl_smi.index(s)) << 8)
        tree[item].ob_flags |= SUBMENU
        return 1, md

    def mn_istart(self, flag, addr, imenu, item):
        if not addr or imenu <= 0:
            return 0
        s = self.smi_find(addr, imenu)
        if not s:
            return 0
        if flag == MIS_INQUIRE:
            return s["start"]
        if flag != MIS_SET:
            return 0
        t = self.trees[addr]
        item = max(t[imenu].ob_head, min(item, t[imenu].ob_tail))
        s["start"] = item
        return item

    def sm_show(self, tree, item):
        """Open the submenu beside the item: (addr, box) or (0, 0)."""
        s = self.smi_of(tree, item)
        if not s:
            return 0, 0
        st = self.trees[s["tree"]]
        with self.on_tree(tree):
            r = self.ob_actxywh(item)
        with self.on_tree(st):
            w, h = st[s["menu"]].ob_width, st[s["menu"]].ob_height
            ox, oy = self.ob_offset(s["menu"])
            ox -= st[s["menu"]].ob_x
            oy -= st[s["menu"]].ob_y
            bx = r.x + r.w + SM_GAP
            if bx + w + MENU_THICKNESS > self.gl_width:
                bx = r.x - w - SM_GAP
            if bx < MENU_THICKNESS:
                return 0, 0
            by = r.y - st[s["start"]].ob_y
            while by > self.gl_height - h:
                by -= self.gl_hchar
            while by < self.gl_rfull.y:
                by += self.gl_hchar
            st[s["menu"]].ob_x = bx - ox
            st[s["menu"]].ob_y = by - oy
            self.menu_sr(True, s["menu"])
            self.gsx_sclip(self.gl_rzero)
            self.ob_draw(s["menu"], MAX_DEPTH)
        return s["tree"], s["menu"]

    def sm_hide(self, tree, item):
        s = self.smi_of(tree, item)
        if s:
            with self.on_tree(self.trees[s["tree"]]):
                self.menu_sr(False, s["menu"])

    def sm_opens(self, tree, item):
        if item == NIL or (tree[item].ob_state & DISABLED):
            return False
        return self.smi_of(tree, item) is not None

    def menu_down(self, ititle):
        imenu = self.menu_sub(ititle)
        if self.do_chg(ititle, SELECTED, True, True, True):
            self.menu_sr(True, imenu)
            self.ob_draw(imenu, MAX_DEPTH)
        return imenu

    def mn_do(self):
        """The drop-downs run from the pointer's arrival in the bar until
        a button transition off a title ends them, or the pointer leaves
        with nothing down: (title, item) when an enabled item was chosen,
        else None.  The button is left as the transition left it."""
        with self.on_tree(self.gl_mntree):
            return self._mn_do()

    def _mn_do(self):
        tree = self.tree
        menu_state = START_STATE
        done = False
        buparm = 0x00010101                     # a press
        cur_title = cur_menu = cur_item = NIL
        cur_sub = smparent = NIL
        smtree, smroot = 0, 0
        p1mor, p2mor = MOBLK(False, 0, 0, 0, 0), MOBLK(False, 0, 0, 0, 0)
        rets = [0] * 6
        self.ct_mouse(True)
        while not done:
            p1tree = tree
            mnu_flags = MU_BUTTON | MU_M1
            if menu_state == START_STATE:
                # into the titles, or out of the bar
                mnu_flags |= MU_M2
                self.rect_change(p2mor, THEBAR, True)
                main_rect, leave_flag = THEACTIVE, False
            elif menu_state == OUTSIDE_STATE:
                # into the titles, into the drop-down, or -- with one
                # showing -- into the submenu: three rectangles
                mnu_flags |= MU_M2
                self.rect_change(p2mor, cur_menu, False)
                main_rect, leave_flag = THEACTIVE, False
            elif menu_state == INITEM_STATE:
                # off the item; the button the other way
                main_rect = cur_item
                buparm = 0x00010100 if (self.button & 1) else 0x00010101
                leave_flag = True
            elif menu_state == SUBMENU_STATE:
                p1tree = self.trees[smtree]
                main_rect = cur_sub
                buparm = 0x00010100 if (self.button & 1) else 0x00010101
                leave_flag = True
            else:                               # INTITLE_STATE
                main_rect, leave_flag = cur_title, True
            with self.on_tree(p1tree):
                self.rect_change(p1mor, main_rect, leave_flag)

            # two rectangles and not three: src/aes/menu.c says why
            ev_which = self.ev_multi(mnu_flags, p1mor, p2mor, 0, buparm, rets)

            # A button in the bar off the titles is nothing; on a title it
            # flips the transition waited for; anywhere else it ends the menu.
            if ev_which & MU_BUTTON:
                if menu_state == START_STATE:
                    continue
                if menu_state != INTITLE_STATE:
                    break
                buparm ^= 0x00000001

            last_title, last_item, last_sub = cur_title, cur_item, cur_sub
            cur_title = self.ob_find(THEACTIVE, 1, rets[0], rets[1])
            if cur_title != NIL and cur_title != THEACTIVE:
                menu_state = INTITLE_STATE
                cur_item = NIL
                cur_sub = NIL
            else:
                cur_title = last_title
                if cur_menu == NIL:             # no menu ever shown
                    cur_title = NIL
                if cur_title == NIL:
                    done = True
                else:
                    # the submenu is asked first, and cur_item is left
                    # alone while the pointer is in it
                    if smtree:
                        with self.on_tree(self.trees[smtree]):
                            cur_sub = self.ob_find(smroot, 1, rets[0], rets[1])
                        if cur_sub == smroot:
                            cur_sub = NIL
                    else:
                        cur_sub = NIL
                    if cur_sub != NIL:
                        menu_state = SUBMENU_STATE
                    else:
                        cur_item = self.ob_find(cur_menu, 1, rets[0], rets[1])
                        if cur_item != NIL:
                            menu_state = INITEM_STATE
                        elif tree[cur_title].ob_state & DISABLED:
                            cur_title = NIL
                            done = True
                        else:
                            menu_state = OUTSIDE_STATE

            # inside out: the submenu's highlight, the submenu, the item,
            # then the title and its menu
            if smtree:
                with self.on_tree(self.trees[smtree]):
                    self.menu_select(last_sub, cur_sub, False)
            if smtree and cur_item != smparent:
                self.sm_hide(tree, smparent)
                smtree, smparent = 0, NIL
                cur_sub = last_sub = NIL
            self.menu_select(last_item, cur_item, False)
            if self.menu_select(last_title, cur_title, False):
                self.menu_sr(False, cur_menu)
            if self.menu_select(cur_title, last_title, True):
                cur_menu = self.menu_down(cur_title)
            self.menu_select(cur_item, last_item, True)
            if not smtree and self.sm_opens(tree, cur_item):
                smtree, smroot = self.sm_show(tree, cur_item)
                if smtree:
                    smparent = cur_item
            if smtree:
                with self.on_tree(self.trees[smtree]):
                    self.menu_select(cur_sub, last_sub, True)

        got = None
        self.mn_tree, self.mn_menu = self.tree_addr(tree), cur_menu
        if cur_title != NIL:
            if smtree:
                self.sm_hide(tree, smparent)
                if cur_sub != NIL:
                    with self.on_tree(self.trees[smtree]):
                        self.do_chg(cur_sub, SELECTED, False, False, False)
            self.menu_sr(False, cur_menu)
            ok = False
            if smtree and cur_sub != NIL:
                with self.on_tree(self.trees[smtree]):
                    ok = self.do_chg(cur_sub, SELECTED, False, False, True)
                if ok:
                    got = (cur_title, cur_sub)
                    self.mn_tree, self.mn_menu = smtree, smroot
            if not ok and not smtree and cur_item != NIL \
                    and self.do_chg(cur_item, SELECTED, False, False, True):
                got = (cur_title, cur_item)
                ok = True
            if not ok:
                self.do_chg(cur_title, SELECTED, False, True, True)
        self.ct_mouse(False)
        return got

    def mn_bar(self, showit):
        """menu_bar on self.tree: shown -- fixed up, the bar stretched to
        the right edge, drawn with the clip off, the line under it black
        -- or forgotten."""
        tree = self.tree
        if showit:
            self.gl_mntree = tree
            self.menu_fixup()
            tree[THEBAR].ob_width = self.gl_width - tree[THEBAR].ob_x
            self.gl_ctwait.m_gr = self.ob_actxywh(THEACTIVE)
            self.gsx_sclip(self.gl_rzero)
            self.ob_draw(THEBAR, MAX_DEPTH)
            self.gsx_attr(False, MD_REPLACE, BLACK)
            self.gsx_cline(0, self.gl_hbox - 1, self.gl_width - 1,
                           self.gl_hbox - 1)
        else:
            self.gl_mntree = None
            self.gl_ctwait.m_gr = self.gl_rmenu.copy()

    def mn_text(self, item, addr):
        """menu_text: the string at addr copied over the item's, whose
        buffer the caller made long enough."""
        self.mem[self.tree[item].ob_spec].s = self.mem[addr].s

    def mn_register(self, pid, addr):
        """A name in the Desk menu, and the menu id an AC_OPEN will carry.
        The ADDRESS is kept, not the string: the AES puts it straight into
        an object's ob_spec, which is the donor's own behaviour and the
        reason an accessory's title has to outlive the accessory's
        start-up.  The id is the SLOT, found by looking for a free one, so
        that six ids stay six ids however they were handed out."""
        if pid < 0 or self.gl_accreg >= NUM_ACCS:
            return -1
        for slot in range(NUM_ACCS):
            if self.gl_acctitle[slot] is None:
                break
        else:
            return -1
        self.gl_acctitle[slot] = addr
        self.gl_accreg += 1
        self.menu_fixup()
        return slot

    # -- the runner's AES ops (src/m3_vdi.c: 1000 + AES function number) --
    def op(self, op, pts=(), ints=()):
        """Execute one script record and return the result record the
        target writes for it (vdiref.record): (contrl[2], contrl[4],
        intout[0..14], ptsout[0..2]) with only the declared words
        non-zero."""
        pts, ints = list(pts), list(ints)
        c2 = c4 = 0
        io, po = [0] * vdiref.RESULT_INTOUT, [0, 0, 0]
        n = op - 1000
        if n == 0:
            self.gsx_start()
            self.ev_init()
            self.wm_init()
            self.mn_init()
        elif n == 10:
            # appl_init: the ap_id, which is 0 -- one process (abi.c)
            io[0] = 0
            c4 = 1
        elif n == 11:
            # appl_read: id, len -- the runner has no buffer a script
            # could name, so the message comes back in int_out[1..]
            io[0], words = self.ap_read(ints[0], ints[1])
            io[1:1 + AP_MSGWORDS] = words
            c4 = 1 + AP_MSGWORDS
        elif n == 12:
            # appl_write: id, len, then the eight-word message.  The
            # length is read: one message, or a refusal.
            if ints[1] != AP_MSGBYTES:
                io[0] = 0
            else:
                self.mq_put(ints[2:2 + AP_MSGWORDS])
                io[0] = 1
            c4 = 1
        elif n == 19:
            io[0] = 1                   # appl_exit
            c4 = 1
        elif n == 20:
            io[0] = self.ev_keybd()
            c4 = 1
        elif n == 21:
            rets = [0] * 6
            io[0] = self.ev_button(ints[0], ints[1] & 0xFFFF,
                                   ints[2] & 0xFFFF, rets)
            io[1:5] = rets[0:4]
            c4 = 5
        elif n == 22:
            rets = [0] * 6
            io[0] = self.ev_mouse(MOBLK(*ints[0:5]), rets)
            io[1:5] = rets[0:4]
            c4 = 5
        elif n == 23:
            io[0:8] = self.ev_mesag()
            c4 = 8
        elif n == 24:
            io[0] = self.ev_timer((ints[0] & 0xFFFF) | ((ints[1] & 0xFFFF) << 16))
            c4 = 1
        elif n == 25:
            # GEM int_in order: flags clicks mask state MOBLK1[5] MOBLK2[5] lo hi
            rets, msg = [0] * 6, [0] * 8
            ms = (ints[14] & 0xFFFF) | ((ints[15] & 0xFFFF) << 16)
            io[0] = self.ev_multi(ints[0], MOBLK(*ints[4:9]), MOBLK(*ints[9:14]),
                                  ms, combine_cms(ints[1], ints[2], ints[3]),
                                  rets, msg)
            io[1:7] = rets[0:6]
            io[7:15] = msg          # the message, if one was delivered
            c4 = 15
        elif n == 26:
            io[0] = self.ev_dclick(ints[0], ints[1])
            c4 = 1
        elif n == 30:
            self.mn_bar(ints[0])
            io[0] = 1
            c4 = 1
        elif n == 31:
            io[0] = int(self.do_chg(ints[0], CHECKED, ints[1], False, False))
            c4 = 1
        elif n == 32:
            io[0] = int(self.do_chg(ints[0] & 0x7FFF, DISABLED, not ints[1],
                                    (ints[0] & 0x8000) != 0, False))
            c4 = 1
        elif n == 33:
            io[0] = int(self.do_chg(ints[0], SELECTED, not ints[1], True, True))
            c4 = 1
        elif n == 34:
            self.mn_text(ints[0], ints[1])
            io[0] = 1
            c4 = 1
        elif n == 35:
            io[0] = self.mn_register(ints[0], ints[1])
            c4 = 1
        elif n == 37:
            # menu_attach: flag, item; the tree, and the MENU block
            md = [ints[2], ints[3], ints[4], ints[5]]
            io[0], md = self.mn_attach(ints[0], self.tree, ints[1], md)
            io[1:5] = md
            c4 = 5
        elif n == 38:
            # menu_istart: flag, imenu, item -- the tree by address
            io[0] = self.mn_istart(ints[0], self.tree_addr(self.tree),
                                   ints[1], ints[2])
            c4 = 1
        elif n == 36:
            # menu_popup: the MENU block spelled out -- box, start,
            # scroll, then x and y -- with the tree in the tree slot as
            # every other menu op has it.  The whole out block comes
            # back, so what the call must NOT touch is visible too.
            io[0], out = self.mn_popup(self.tree, ints[0], ints[1],
                                       ints[2], ints[3], ints[4])
            io[1:6] = out
            c4 = 6
        elif n == 40:
            # objc_add and objc_delete: the tree surgery objc.c already did
            # for the window manager, now an application's to call as well.
            self.ob_add(self.tree, ints[0], ints[1])
            io[0] = 1
            c4 = 1
        elif n == 41:
            io[0] = 1 if self.ob_delete(self.tree, ints[0]) else 0
            c4 = 1
        elif n == 42:
            self.draw(ints[0], ints[1], pts[0:4])
        elif n == 43:
            io[0] = self.find(ints[0], ints[1], pts[0], pts[1])
            c4 = 1
        elif n == 44:
            io[0], io[1] = self.offset(ints[0])
            c4 = 2
        elif n == 45:
            # objc_order
            self.ob_order(self.tree, ints[0], ints[1])
            io[0] = 1
            c4 = 1
        elif n == 46:
            io[0], io[1] = self.edit(ints[0], ints[1], ints[2], ints[3])
            c4 = 2
        elif n == 47:
            self.change(ints[0], pts[0:4], ints[1] & 0xFFFF, ints[2])
        elif n == 50:
            io[0] = self.fm_do(ints[0])
            c4 = 1
        elif n == 51:
            io[0] = self.fm_dial(ints[0], Rect(*ints[1:5]), Rect(*ints[5:9]))
            c4 = 1
        elif n == 52:
            # form_alert: the default button, the string at the record's
            # address slot (self.fs_strings, what the harness staged)
            io[0] = self.fm_alert(ints[0], self.fs_strings[self.rec_addr])
            c4 = 1
        elif n == 53:
            # form_error: the number; the text is the system's own
            io[0] = 1 if self.fm_error(ints[0]) else 0
            c4 = 1
        elif n == 54:
            io[0], io[1], io[2], po[0] = self.center()
            c4, c2 = 3, 1
        elif n == 55:
            io[0], io[1], io[2] = self.form_keybd(ints[0], ints[1], ints[2])
            c4 = 3
        elif n == 56:
            io[0], io[1] = self.form_button(ints[0], ints[1])
            c4 = 2
        elif n in (73, 74):
            pi, pt = Rect(*ints[0:4]), Rect(*ints[4:8])
            if n == 73:
                self.gr_growbox(pi, pt)
            else:
                self.gr_shrinkbox(pi, pt)
            io[0] = 1
            c4 = 1
        elif n == 109:
            # wind_new: the return is reserved, so it is the plain TRUE
            self.wm_new()
            io[0] = 1
            c4 = 1
        elif n == 72:
            # graf_mbox / graf_movebox: a ghost box walked from one place
            # to another.  It draws and undraws in XOR, so what it leaves
            # on the screen is what was there -- which is the whole of
            # what a gate can check about it, and worth checking.
            self.gr_movebox(*ints[0:6])
            io[0] = 1
            c4 = 1
        elif n == 75:
            io[0] = self.gr_watchbox(ints[0], ints[1], ints[2])
            c4 = 1
        elif n == 76:
            # graf_slidebox: 0..1000 of the way along the parent, which is
            # a measurement and not a status
            io[0] = self.gr_slidebox(ints[0], ints[1], ints[2])
            c4 = 1
        elif n == 70:
            io[0] = 1
            io[1:3] = self.gr_rubbox(*ints[0:4])
            c4 = 3
        elif n == 71:
            io[0] = 1
            io[1:3] = self.gr_dragbox(ints[0], ints[1], ints[2], ints[3],
                                      Rect(*ints[4:8]))
            c4 = 3
        elif n == 77:
            # graf_handle: the AES's workstation handle and its character
            # and box cell sizes
            io[0] = self.gl_handle
            io[1:5] = (self.gl_wchar, self.gl_hchar, self.gl_wbox, self.gl_hbox)
            c4 = 5
        elif n == 78:
            # graf_mouse: the mode, then USER_DEF's 37 words after it.
            # GEM passes a pointer; a script record carries the words, so
            # neither side has a buffer to stage for this one.
            form = ints[1:1 + gemdata.MFORM_WORDS]
            self.gr_mouse(ints[0], form if len(form) == gemdata.MFORM_WORDS else None)
            io[0] = 1
            c4 = 1
        elif n == 79:
            io[0] = 1
            io[1:5] = self.gr_mkstate()
            c4 = 5
        elif n in (90, 91):
            # fsel_input / fsel_exinput: the path is the record's fourth
            # slot, the selection and label are looked up in self.mem as
            # the strings the harness staged (run(..., strings=))
            path = self.fs_strings[self.fs_path_addr]
            sel = self.fs_strings[ints[0]]
            label = self.fs_strings[ints[1]] if n == 91 else None
            io[0], io[1], path, sel = self.fs_input(path, sel, label)
            self.fs_strings[self.fs_path_addr] = path
            self.fs_strings[ints[0]] = sel
            c4 = 2
        elif n == 100:
            io[0] = self.wm_create(ints[0], Rect(*ints[1:5]))
            c4 = 1
        elif n == 101:
            io[0] = self.wm_open(ints[0], Rect(*ints[1:5]))
            c4 = 1
        elif n == 102:
            io[0] = self.wm_close(ints[0])
            c4 = 1
        elif n == 103:
            io[0] = self.wm_delete(ints[0])
            c4 = 1
        elif n == 104:
            io[0], io[1:5] = self.wm_get(ints[0], ints[1])
            c4 = 5
        elif n == 105:
            io[0] = self.wm_set(ints[0], ints[1], ints[2:])
            c4 = 1
        elif n == 106:
            io[0] = self.wm_find(ints[0], ints[1])
            c4 = 1
        elif n == 107:
            self.wm_update(ints[0])
            io[0] = 1
            c4 = 1
        elif n == 108:
            io[0] = 1
            io[1:5] = self.wm_calc(ints[0], ints[1] & 0xFFFF, *ints[2:6])
            c4 = 5
        elif n == 110:
            # rsrc_load: the file is the harness's to stage where the
            # target's rsrc_load puts it (tools/rsc.py Rsc.expect), and
            # the trees in it are in self.trees by address
            io[0] = 1
            c4 = 1
        elif n == 111:
            io[0] = 1                   # rsrc_free
            c4 = 1
        elif n == 112:
            # rsrc_gaddr: where the thing is in the file is the file's
            # business (tools/rsc.py Rsc.addr); a record that uses the
            # address names it in its fourth slot
            io[0] = 1
            c4 = 1
        elif n == 121:
            # shel_write: the request is the shell loop's, remembered
            self.sh_doex, self.sh_isgr = ints[0], ints[1]
            io[0] = 1
            c4 = 1
        elif n in (122, 123):
            # shel_get / shel_put: the caller's buffer is the record's
            # address slot, a CharArray in self.mem; the copy is clamped
            # to the shell buffer as sh_get/sh_put clamp it
            buf = self.mem[self.rec_addr]
            k = min(ints[0], SIZE_SHELBUF)
            if n == 122:
                buf.raw[:k] = self.sh_buf[:k]
            else:
                self.sh_buf[:k] = buf.raw[:k]
            io[0] = 1
            c4 = 1
        elif op >= GEMDOS_OP:
            # GEMDOS through the same entry as the AES (src/sys/abi.c
            # gem_entry counts it too), so a script that mirrors a
            # program's calls keeps the target's gem_calls as its index.
            # The drive calls only, from the DOS seam the harness read.
            fn = op - GEMDOS_OP
            c4 = 1
            if fn == 0x19:              # Dgetdrv
                io[0] = self.dos_drive
            elif fn == 0x0E:            # Dsetdrv: the map of drives
                self.dos_drive = ints[0]
                io[0] = self.dos_drvmap
            else:
                ret = self.gemdos(fn, ints)
                io[0], io[1] = ret & 0xFFFF, (ret >> 16) & 0xFFFF
                c4 = 2
        else:
            raise ValueError(f"unknown AES op {op}")
        return vdiref.record(c2, c4, io, po)

    # -- open files -------------------------------------------------------
    # A handle is its IOCB plus GD_HANDLE_BASE (src/sys/gemdos.c), and an
    # IOCB is the lowest free one from 1 (src/sys/cio.c, free_iocb).  A
    # search holds one only while it is still reading the directory --
    # every listing the gates use fits one read, so none is held here.
    GD_HANDLE_BASE = 6
    CIO_IOCBS = 8

    def dos_open(self, parent, name, size, writing):
        for iocb in range(1, self.CIO_IOCBS):
            h = iocb + self.GD_HANDLE_BASE
            if h not in self.dos_files:
                self.dos_files[h] = {"parent": parent, "name": name,
                                     "size": size, "at": 0, "w": writing}
                return h
        return GD_ENHNDL & 0xFFFFFFFF

    def dos_close(self, h):
        if h not in self.dos_files:
            return GD_EIHNDL & 0xFFFFFFFF
        del self.dos_files[h]
        return 0

    def dos_setsize(self, f):
        """A write grows the directory entry, which is what the gate
        reads back off the image afterwards."""
        entries = self.dos_dirs.get(f["parent"], [])
        for i, e in enumerate(entries):
            if e[0] == f["name"]:
                entries[i] = (e[0], e[1], e[2], e[3], f["size"])
                return

    def gemdos(self, fn, ints):
        """The file calls of src/sys/gemdos.c the desktop makes, on the
        listing the harness read off the disk (dos_dirs) and the far heap
        the gate placed (dos_brk).  `ints` are the trap frame's words
        from offset 6, a LONG low word first (src/app/gemlib.c); the
        LONG result."""
        def long_(i):
            return ints[i] | (ints[i + 1] << 16)

        if fn == 0x1A:                  # Fsetdta
            self.dos_dta = long_(0)
            return 0
        if fn == 0x3B:                  # Dsetpath: the root, or a
            # directory the listing knows (gemdos.c gd_setpath opens
            # X:\DIR\*.* to be sure of it)
            path = self.mem[long_(0)].s
            if len(path) > 3:
                if path[-1] != "\\":
                    path += "\\"
                if path not in self.dos_dirs:
                    return GD_EPTHNF & 0xFFFFFFFF
            return 0
        if fn == 0x2F:                  # Fgetdta
            return self.dos_dta
        if fn == 0x48:                  # Malloc: far_alloc, or the room
            n = long_(0)
            if n & 0x80000000:
                # the room left: the far probe's last bank less brk, which
                # nothing here mirrors
                raise ValueError("Malloc(-1): the room is the target's to know")
            if n == 0:
                return 0
            # Each block carries a LONG in front of it, its size, so that
            # the last one can be given back (src/sys/gemdos.c, MB_HDR):
            # the address is four past the heap's cursor, and the cursor
            # moves by the block and the header together, rounded.
            ret = self.dos_brk + 4
            self.dos_brk += (n + 4 + 3) & ~3
            return ret
        if fn == 0x39:                  # Dcreate: a folder in a listed
            # directory, empty, and listed itself from now on
            path = self.mem[long_(0)].s
            k = path.rfind("\\") + 1
            parent, name = path[:k], path[k:]
            if parent not in self.dos_dirs:
                return GD_EPTHNF & 0xFFFFFFFF
            if any(e[0] == name for e in self.dos_dirs[parent]):
                return GD_EACCDN & 0xFFFFFFFF
            self.dos_dirs[parent].append((name, FA_SUBDIR, 0, 0, self.dos_newdir))
            self.dos_dirs[path + "\\"] = []
            return 0
        if fn == 0x3A:                  # Ddelete: an empty folder
            path = self.mem[long_(0)].s
            k = path.rfind("\\") + 1
            parent, name = path[:k], path[k:]
            if parent not in self.dos_dirs or path + "\\" not in self.dos_dirs:
                return GD_EPTHNF & 0xFFFFFFFF
            if self.dos_dirs[path + "\\"]:
                return GD_EACCDN & 0xFFFFFFFF
            self.dos_dirs[parent] = [e for e in self.dos_dirs[parent]
                                     if e[0] != name]
            del self.dos_dirs[path + "\\"]
            return 0
        if fn == 0x41:                  # Fdelete
            path = self.mem[long_(0)].s
            k = path.rfind("\\") + 1
            parent, name = path[:k], path[k:]
            entries = self.dos_dirs.get(parent)
            if entries is None:
                return GD_EPTHNF & 0xFFFFFFFF
            if not any(e[0] == name and not e[1] & FA_SUBDIR for e in entries):
                return GD_EFILNF & 0xFFFFFFFF
            self.dos_dirs[parent] = [e for e in entries if e[0] != name]
            return 0
        if fn == 0x43:                  # Fattrib: the DOS's lock, and
            # nothing else -- src/sys/gemdos.c gd_fattrib refuses a read
            # outright, because reading an attribute back is what a
            # search answers
            if not ints[2]:
                return GD_EINVFN & 0xFFFFFFFF
            path, attr = self.mem[long_(0)].s, ints[3]
            k = path.rfind("\\") + 1
            parent, name = path[:k], path[k:]
            entries = self.dos_dirs.get(parent)
            if entries is None:
                return GD_EPTHNF & 0xFFFFFFFF
            out, found = [], False
            for e in entries:
                if e[0] == name and not e[1] & FA_SUBDIR:
                    found = True
                    e = (e[0], (e[1] & ~FA_RDONLY) | (attr & FA_RDONLY),
                         e[2], e[3], e[4])
                out.append(e)
            if not found:
                return GD_EFILNF & 0xFFFFFFFF
            self.dos_dirs[parent] = out
            return 0
        if fn == 0x56:                  # Frename: within one directory,
            # which is all the DOS's own rename does (gd_rename builds
            # CIO's "path,newname" out of the destination's last
            # component).  A name already taken is refused, as XIO 32 is
            # refused; what a DOS does with a LOCKED file is not modelled
            # here, so nothing may rename one until it is
            old, new = self.mem[long_(1)].s, self.mem[long_(3)].s
            k = old.rfind("\\") + 1
            parent, oldname = old[:k], old[k:]
            newname = new[new.rfind("\\") + 1:]
            entries = self.dos_dirs.get(parent)
            if entries is None:
                return GD_EPTHNF & 0xFFFFFFFF
            hit = [e for e in entries if e[0] == oldname]
            if not hit:
                return GD_EFILNF & 0xFFFFFFFF
            if any(e[0] == newname for e in entries):
                return GD_EACCDN & 0xFFFFFFFF
            e = hit[0]
            self.dos_dirs[parent] = [x if x[0] != oldname
                                     else (newname,) + tuple(e[1:])
                                     for x in entries]
            if e[1] & FA_SUBDIR:        # its listing travels with it
                was, now = parent + oldname + "\\", parent + newname + "\\"
                for key in [k2 for k2 in self.dos_dirs if k2.startswith(was)]:
                    self.dos_dirs[now + key[len(was):]] = self.dos_dirs.pop(key)
            return 0
        if fn == 0x3D or fn == 0x3C:    # Fopen / Fcreate
            path = self.mem[long_(0)].s
            k = path.rfind("\\") + 1
            parent, name = path[:k], path[k:]
            entries = self.dos_dirs.get(parent)
            if entries is None:
                return GD_EPTHNF & 0xFFFFFFFF
            hit = [e for e in entries if e[0] == name and not e[1] & FA_SUBDIR]
            if fn == 0x3D:                      # open what is there
                if not hit:
                    return GD_EFILNF & 0xFFFFFFFF
                size = hit[0][4]
            else:                               # create, or empty what is
                self.dos_dirs[parent] = [e for e in entries if e[0] != name]
                self.dos_dirs[parent].append((name, 0, 0, self.dos_newdir, 0))
                size = 0
            h = self.dos_open(parent, name, size, fn == 0x3C)
            return h
        if fn == 0x3E:                  # Fclose
            return self.dos_close(ints[0])
        if fn == 0x3F or fn == 0x40:    # Fread / Fwrite
            h, count = ints[0], ints[1] | (ints[2] << 16)
            f = self.dos_files.get(h)
            if f is None:
                return GD_EIHNDL & 0xFFFFFFFF
            if fn == 0x3F:
                n = min(count, f["size"] - f["at"])
                if n < 0:
                    n = 0
                f["at"] += n
                return n
            f["at"] += count
            if f["at"] > f["size"]:
                f["size"] = f["at"]
            self.dos_setsize(f)
            return count
        if fn == 0x4E:                  # Fsfirst
            spec = self.mem[long_(0)].s
            k = spec.rfind("\\") + 1
            path, pattern = spec[:k], spec[k:]
            if path not in self.dos_dirs:
                raise ValueError(f"Fsfirst {spec!r}: no listing for {path!r}")
            # the search belongs to the DTA that started it, as
            # src/sys/gemdos.c's slots do (SL_OWNER) and the ST's DTA
            # does: a walk that nests one search inside another gives
            # each level a DTA, and neither disturbs the other
            self.dos_searches[self.dos_dta] = (list(self.dos_dirs[path]),
                                               pattern, ints[2])
            return self.gemdos(0x4F, ())
        if fn == 0x4F:                  # Fsnext
            search = self.dos_searches.get(self.dos_dta)
            if search is None:
                return GD_ENMFIL & 0xFFFFFFFF
            entries, pattern, want = search
            while entries:
                name, attr, time, date, size = entries.pop(0)
                if attr & FA_SUBDIR and not want & FA_SUBDIR:
                    continue
                if attr & FA_HIDDEN and not want & FA_HIDDEN:
                    continue
                if not fs_wildcmp(pattern, name):
                    continue
                self.dos_dta_data = (name, attr, time, date, size)
                return 0
            del self.dos_searches[self.dos_dta]
            return GD_ENMFIL & 0xFFFFFFFF
        if fn == GD_PSYSTEM:            # the probe: a null line asks
            return 0 if self.psystem else GD_EINVFN & 0xFFFFFFFF
        raise ValueError(f"unknown GEMDOS function {fn:#x}")


AES_OP = 1000
GSX_START, OBJC_DRAW, OBJC_FIND, OBJC_OFFSET = 1000, 1042, 1043, 1044
OBJC_ADD, OBJC_DELETE = 1040, 1041
OBJC_EDIT, OBJC_CHANGE, FORM_CENTER = 1046, 1047, 1054
EVNT_KEYBD, EVNT_BUTTON, EVNT_MOUSE, EVNT_TIMER = 1020, 1021, 1022, 1024
EVNT_MULTI, EVNT_DCLICK = 1025, 1026
FORM_DO, FORM_DIAL, FORM_KEYBD, FORM_BUTTON = 1050, 1051, 1055, 1056
FORM_ALERT, FORM_ERROR = 1052, 1053
GRAF_RUBBOX, GRAF_DRAGBOX = 1070, 1071
WIND_NEW = 1109
GRAF_MBOX = 1072
GRAF_GROWBOX, GRAF_SHRINKBOX, GRAF_WATCHBOX = 1073, 1074, 1075
GRAF_SLIDEBOX = 1076
GRAF_MOUSE = 1078
GRAF_MKSTATE = 1079
APPL_INIT, APPL_WRITE, APPL_EXIT, EVNT_MESAG = 1010, 1012, 1019, 1023
APPL_READ = 1011
GRAF_HANDLE = 1077
FSEL_INPUT, FSEL_EXINPUT = 1090, 1091
(MENU_BAR, MENU_ICHECK, MENU_IENABLE, MENU_TNORMAL, MENU_TEXT,
 MENU_REGISTER, MENU_POPUP, MENU_ATTACH, MENU_ISTART) = range(1030, 1039)
(WIND_CREATE, WIND_OPEN, WIND_CLOSE, WIND_DELETE, WIND_GET, WIND_SET,
 WIND_FIND, WIND_UPDATE, WIND_CALC) = range(1100, 1109)
RSRC_LOAD, RSRC_FREE, RSRC_GADDR = 1110, 1111, 1112
SHEL_WRITE, SHEL_GET, SHEL_PUT = 1121, 1122, 1123
SIZE_SHELBUF = 4192                     # src/app/gem.h
# GEMDOS, as a script sees it: the function number over this base
# (src/app/gemlib.c has the numbers)
GEMDOS_OP = 2000
DSETDRV, DGETDRV, DSETPATH = GEMDOS_OP + 0x0E, GEMDOS_OP + 0x19, GEMDOS_OP + 0x3B
FSETDTA, FGETDTA, MALLOC = GEMDOS_OP + 0x1A, GEMDOS_OP + 0x2F, GEMDOS_OP + 0x48
FSFIRST, FSNEXT = GEMDOS_OP + 0x4E, GEMDOS_OP + 0x4F
DCREATE, DDELETE, FDELETE = GEMDOS_OP + 0x39, GEMDOS_OP + 0x3A, GEMDOS_OP + 0x41
FATTRIB, FRENAME = GEMDOS_OP + 0x43, GEMDOS_OP + 0x56
FCREATE, FOPEN, FCLOSE = GEMDOS_OP + 0x3C, GEMDOS_OP + 0x3D, GEMDOS_OP + 0x3E
FREAD, FWRITE = GEMDOS_OP + 0x3F, GEMDOS_OP + 0x40
PSYSTEM = GEMDOS_OP + 0x1F0         # gem4xe's own (src/sys/gemdos.h)
# src/sys/gemdos.h: the attributes and the error the searches answer
FA_RDONLY, FA_HIDDEN, FA_SYSTEM, FA_VOLUME, FA_SUBDIR, FA_ARCHIVE = (
    0x01, 0x02, 0x04, 0x08, 0x10, 0x20)
GD_EINVFN = -32
GD_PSYSTEM = 0x1F0                  # gem4xe's own (src/sys/gemdos.h)
GD_EPTHNF, GD_EACCDN, GD_EFILNF, GD_ENMFIL = -34, -36, -33, -49
GD_ENHNDL, GD_EIHNDL = -35, -37


def run(script, tree, mem, plan=None, pointer=(0, 0), trees=None,
        dirs=None, pool=None, buffers=None, dirsep="", lang=None, dev=None,
        home=0):
    """Run a mixed VDI/AES script against fresh models; returns
    (vdi, aes, results) with one result record per script record, the
    way vdiref.VDI.run() does for a pure VDI script.

    `plan` maps a script record's index to the input steps the harness
    will apply while the target is inside that op -- ("frames", n),
    ("move", x, y), ("button", state), ("key", name, code[, shift, ctrl]),
    ("shot", ...) for a screenshot between frames, kept in AES.shots --
    and the event waits here consume the same steps (AES._step).  A
    plan starts with a ("frames", n) settle: the harness sees the op's
    index the moment the one before it completes, and a step applied then
    could land in the op's entry poll (the quick checks) or its loop (the
    button FIFO), which count clicks differently.  The settle puts the
    target in the loop before the first real step, and the model walks the
    same frames.  An op that returns with steps unused, or with a click
    still counting in the double-click delay, would leave the two sides in
    states the harness cannot tell apart, so both are errors in the plan.
    `pointer` is where the target's pointer starts, read back by the
    harness.  A record may name a tree by address in its fourth slot,
    resolved through `trees`; so is the tree a WF_NEWDESK names.  A
    FSEL_INPUT record names the path buffer there instead, and `buffers`
    maps that address and the ones in its intin to the strings staged in
    them; `dirs` is what the drives list and `pool` where the target's
    application pool starts (AES.fs_input).
    """
    v = vdiref.VDI(dev)
    v.ptr_x, v.ptr_y = pointer
    a = AES(v, tree, mem)
    a.trees = dict(trees or {})
    a.home = tree               # the tree a record that names none means
    # ...and WHERE it is, which MN_SELECTED's words 5 and 6 report now
    # that an item may come from a tree that is not the menu bar's.
    if home:
        a.trees[home] = tree
    a.home_addr = home
    a.dirs = dirs or {}
    a.dos_dirsep = dirsep       # the DOS seam's: "" on DOS 2, ">" on a SpartaDOS
    a.pool_mark = pool
    a.fs_strings = dict(buffers or {})
    a.lang = dict(lang) if lang else None    # what LANG.RSC says, if not English
    return v, a, resume(v, a, script, plan)


def resume(v, a, script, plan=None, base=0):
    """Run script on models that already have a history -- the target's
    state carries from one script to the next unless a script starts it
    over with GSX_START, and a session longer than the runner's buffers
    hold is fed to it in pieces.  Plan keys index the script from base.
    Returns the result records."""
    plan = {k - base: v_ for k, v_ in (plan or {}).items()}
    trees, tree = a.trees, a.home
    results = []
    for i, rec in enumerate(script):
        op = rec[0]
        pts = rec[1] if len(rec) > 1 else ()
        ints = rec[2] if len(rec) > 2 else ()
        steps = list(plan.pop(i, ()))
        if op >= AES_OP:
            # the record's fourth slot is an address: a tree's, or -- for
            # the calls whose argument is a string the harness staged --
            # the string's (run(..., buffers=))
            a.rec_addr = rec[3] if len(rec) > 3 else 0
            if op in (FSEL_INPUT, FSEL_EXINPUT):
                a.fs_path_addr = rec[3]
                a.tree = tree
            elif op in (FORM_ALERT, SHEL_GET, SHEL_PUT) or op >= GEMDOS_OP:
                a.tree = tree
            else:
                a.tree = trees[rec[3]] if len(rec) > 3 else tree
            if steps and (steps[0][0] != "frames" or steps[0][1] < 1):
                raise ValueError(f"record {i} (op {op}): a plan starts with "
                                 f"a (\"frames\", n) settle, not {steps[0]}")
            a.plan = steps
            try:
                results.append(a.op(op, pts, ints))
            except PlanExhausted:
                raise PlanExhausted(f"record {i} (op {op}) needs more input "
                                    f"than its plan gives") from None
            if (len(a.plan) == 1 and a.plan[0][0] == "frames"
                    and len(a.plan[0]) > 2):
                # the rest of a frames step the op completed inside: the
                # harness stops running them when it sees the op complete
                a.plan = []
            if a.plan:
                raise ValueError(f"record {i} (op {op}) returned with "
                                 f"{len(a.plan)} plan step(s) unused")
            if a.gl_bdely:
                raise ValueError(f"record {i} (op {op}) returned with a "
                                 f"click still in the double-click delay")
        else:
            if steps:
                raise ValueError(f"record {i} (op {op}) is a VDI call: "
                                 f"it cannot take a plan")
            v.call(op, pts, ints, rec[3] if len(rec) > 3 else None)
            results.append(v.result())
    if plan:
        raise ValueError(f"plan for records that do not exist: "
                         f"{sorted(k + base for k in plan)}")
    return results


def encode(script, tree_base, mfdb_addr=0):
    """Serialise a script for src/m3_vdi.c: AES records carry the tree's
    address in the contrl[7] slot -- tree_base, or the record's own fourth
    slot when it names another tree.  A VDI raster record's form (its
    fourth slot) is at mfdb_addr on the target, as vdiref.encode plants
    it."""
    out = []
    for rec in script:
        op = rec[0]
        pts = list(rec[1]) if len(rec) > 1 else []
        ints = list(rec[2]) if len(rec) > 2 else []
        c7 = c8 = 0
        if op >= AES_OP:
            c7 = (rec[3] if len(rec) > 3 else tree_base) & 0xFFFF
        elif len(rec) > 3 and rec[3] is not None:
            c7, c8 = mfdb_addr & 0xFFFF, (mfdb_addr >> 16) & 0xFFFF
        # the eighth header word is contrl[5], the sub-opcode: no AES call
        # has one, but the runner reads it for v_gdp (tools/vdiref.py)
        out += [op, len(pts) // 2, len(ints), c7, c8, 0, 0, 0] + pts + ints
    out.append(0)
    return out
