#!/usr/bin/env python3
"""The GEM Desktop, run against the AES model.

src/desk/desktop.c is a program, not a script: what it asks the AES
next depends on what the AES answered last -- the character cell from
graf_handle sizes the icons, the desk from wind_get places them, the
rectangle list drives the redraw, the drive map from Dsetdrv says how
many disks there are, the directory Fsfirst/Fsnext list fills the
window, and evnt_multi's answer chooses the branch.  So the gate
(tests/emu/m17_desktop.py) cannot hand the model a script the way the
earlier gates do; it hands the model the desktop, transcribed here call
for call from desktop.c, deskobj.c and deskwin.c, and the desktop asks
the model as it goes.  What comes out is the same thing the gates always
had: the list of records the desktop made (Desktop.script), the input
each wait was given (Desktop.plan, keyed the way m7_form.drive wants
it), and the model's screen at every ("shot",) step (AES.shots) -- to be
compared with the target, which runs the real DESKTOP.PRG under sh_main.

The addresses are the target's, derived the way src/sys/app.c and
src/aes/rsrc.c derive them from the application pool: the near region
at the first page boundary at or above the pool mark, the desktop's
globals G where the link put them relative to that, the resource at
the first even address after the near region.  The desktop's G4A header
gives the link addresses; build/desktop.sym gives G.  Nothing here is a
number read off a probe.

The screen tree is built as deskobj.c builds it, object by object; the
windows' WNODEs as deskwin.c fills them, a FNODE per directory entry
from the model's GEMDOS (aesref.AES.gemdos, over the listing the gate
read off the disk); and Desktop.globes() packs G as the target lays it
out (desk.h), so the gate can read G back from the target and compare
every byte.  The strings the program writes in place -- a window's
search spec, title and info line, an icon's label -- are CharArrays
registered at their G addresses, so the model's Fsfirst, wind_set and
icon drawer read what the target's would.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aesref                               # noqa: E402
import vdiref                               # noqa: E402
import deskrsc                              # noqa: E402
from aesref import (Obj, Text, Iconblk, Rect,  # noqa: E402
                    G_BOX, G_IBOX, G_ICON, G_STRING, NONE, NORMAL, SELECTED, WHITEBAK,
                    NIL, ROOT, MAX_DEPTH, ARROW, HOURGLASS, M_OFF, M_ON,
                    DISABLED, EDITABLE, FA_RDONLY, FRENAME, FATTRIB,
                    BEG_UPDATE, END_UPDATE, MU_KEYBD, MU_BUTTON, MU_MESAG,
                    MU_TIMER, FMD_START, FMD_FINISH,
                    NAME, CLOSER, FULLER, MOVER, INFO, SIZER, UPARROW,
                    DNARROW, VSLIDE, LFARROW, RTARROW, HSLIDE,
                    WF_NAME, WF_INFO, WF_WXYWH, WF_CXYWH, WF_PXYWH, WF_FXYWH,
                    WF_VSLIDE, WF_TOP, WF_FIRSTXYWH, WF_NEXTXYWH, WF_NEWDESK,
                    WF_HSLSIZ, WF_VSLSIZ, WF_HSLIDE, WC_WORK,
                    WM_REDRAW, WM_TOPPED, WM_CLOSED, WM_FULLED, WM_ARROWED,
                    WM_VSLID, WM_HSLID, WM_SIZED, WM_MOVED, WM_NEWTOP,
                    WA_UPPAGE, WA_DNPAGE, WA_UPLINE, WA_DNLINE,
                    WA_LFPAGE, WA_RTPAGE, WA_LFLINE, WA_RTLINE, MN_SELECTED,
                    APPL_INIT, APPL_EXIT, EVNT_MULTI, MENU_BAR,
                    MENU_ICHECK, MENU_IENABLE, MENU_TNORMAL,
                    OBJC_DRAW, OBJC_FIND,
                    OBJC_OFFSET, FORM_DO, FORM_DIAL, FORM_CENTER, FORM_ALERT,
                    GRAF_HANDLE, GRAF_GROWBOX, GRAF_SHRINKBOX,
                    WIND_CREATE, WIND_OPEN, WIND_CLOSE, WIND_DELETE, WIND_CALC,
                    WIND_GET, WIND_SET, WIND_FIND, WIND_UPDATE,
                    RSRC_LOAD, RSRC_FREE, RSRC_GADDR, SHEL_WRITE,
                    SHEL_GET, SHEL_PUT, SIZE_SHELBUF,
                    DSETDRV, DGETDRV, DSETPATH, FSETDTA, MALLOC, FSFIRST,
                    FSNEXT, DCREATE, DDELETE, FDELETE, FA_SUBDIR,
                    GRAF_MKSTATE, GRAF_DRAGBOX, GRAF_RUBBOX,
                    FOPEN, FCREATE, FCLOSE, FREAD, FWRITE, GD_EACCDN,
                    PSYSTEM)
from rsc import R_TREE, R_ICONBLK, R_STRING, ICONBLK_SIZE  # noqa: E402
from deskrsc import (ADMENU, ADDINFO, ADMKDBOX, ADDELDIA, ADFINFO,  # noqa: E402
                     DESKMENU, FILEMENU, ABOUITEM,
                     OPTNMENU, OPENITEM, SHOWITEM, NFOLITEM, DELTITEM,
                     CLOSITEM, CLSWITEM, QUITITEM, READITEM, SAVEITEM,
                     DEVERSN, DEOK,
                     MKNAME, MKOK, CDTITLE, CDFILES, CDFOLDS, CDOK,
                     FITITLE, FINAME, FISIZE, FIDATE, FIFILES, FIFOLDS,
                     FIRDWR, FIRONLY, FIOK,
                     STDISK, STTRASH, STNOMEM, STNOWIND, STDEFDIR,
                     STDELFIL, STDELDIR, STFOFAIL, STFO8DEE, STDEEPPA,
                     STCPYFIL, STDISKFU, STNOTHIN, STSAMEPL,
                     STDELTTL, STCPYTTL, STMOVTTL,
                     STFIINFO, STFOINFO, STRENAME, STSVINF, STRDINF,
                     STFLINE, STFMARK, VIEWMENU, ICONITEM, TEXTITEM,
                     NAMEITEM, TYPEITEM, SIZEITEM, DATEITEM, NSRTITEM, FITITEM,
                     IB_HARD, IB_FLOPPY, IB_TRASH,
                     IB_FOLDER, IB_APPL, IB_DOCU, NOT_YET, CMDITEM)

# the two AES calls aesref numbers only in its dispatcher
OBJC_ORDER = 1045
GRAF_MOUSE = 1078
E_OK = 0

# -- desk.h ----------------------------------------------------------------
DESKWH, DROOT, NUM_WNODES = 0, 1, 4
WOBS_START = DROOT + 1 + NUM_WNODES
NUM_ITEMS = 16
NUM_SOBS = WOBS_START + NUM_ITEMS
MAX_DRIVES = 8
MAX_ICONTEXT_WIDTH = 12
LABEL_LEN = MAX_ICONTEXT_WIDTH + 1
DESK_SPEC = 0x00001143
WINDOW_SPEC = 0x00001100
# The "#Q" line's pairs: one per screen, the colour one first, each a
# desk byte and a window byte.  desk.h N_SCREENS / PATCOL_MASK.
N_SCREENS = 2
SCR_COLOUR = 0
SCR_MONO = 1
PATCOL_MASK = 0x00FF
MIN_WINT, MIN_HINT = 4, 2
WINDOW_STYLE = (NAME | CLOSER | FULLER | MOVER | INFO | SIZER | UPARROW
                | DNARROW | VSLIDE | LFARROW | RTARROW | HSLIDE)
LEN_ZPATH, LEN_ZFNAME, LEN_ZINFO = 48, 14, 36
LEN_WNAME = LEN_ZPATH + 2
NUM_FNODES = 64
MAX_DELLEVEL = 4
DISPATTR = FA_SUBDIR
F_SELECTED = 0x0001
SHW_EXEC, SHW_SHUTDOWN = 1, 4               # gem.h
CPDATA_LEN, INF_REV_LEVEL, SH_TAILLEN = 128, 2, 128
INF_NAME = "DESKTOP.INF"                    # desk.h
AES_VERSION = 0x0140                        # abi.c: global[0]
LEN_FNODE = 48                          # a text line's places, and the
V_ICON, V_TEXT = 0, 1                   # width its highlight covers
S_NAME, S_TYPE, S_SIZE, S_DATE, S_NSRT = 0, 1, 2, 3, 4
INF_E1_VIEWTEXT = 0x80
INF_E1_SORTMASK = 0x60
INF_E5_NOSORT = 0x80
INF_E5_NOSIZE = 0x10
SCREENINFO_SIZE = LEN_FNODE             # the union: ICONBLK + label is 47
OBJ_SIZE = aesref.OBJ_SIZE
RESULT_INTOUT = vdiref.RESULT_INTOUT
# the structs deskwin.c keeps, sized as cc65816 lays them out (no padding)
DTA_SIZE, FNODE_SIZE = 44, 30
PNODE_SIZE = 2 + 4 + LEN_ZPATH + 4
WNODE_SIZE = 16 + PNODE_SIZE + LEN_WNAME + LEN_ZINFO
# where a WNODE's in-place strings are
WN_SPEC, WN_NAME, WN_INFO = 16 + 6, 16 + PNODE_SIZE, 16 + PNODE_SIZE + LEN_WNAME
WSAVE_SIZE = 6 * 2 + LEN_ZPATH
CSAVE_SIZE = NUM_WNODES * WSAVE_SIZE

# -- deskwin.c -------------------------------------------------------------
# desk.h: what an operation is doing, and the buffer a copy goes through
OP_COUNT, OP_DELETE, OP_COPY, OP_MOVE = 0, 1, 2, 3
COPY_BUF = 1024
# graf_mkstate's key state: SHIFT is the modifier this machine can be
# asked about while the button is down (src/app/gem.h)
MODE_RSHIFT, MODE_LSHIFT = 0x01, 0x02

ARENA_SIZE = (DTA_SIZE + NUM_WNODES * NUM_FNODES * FNODE_SIZE + CSAVE_SIZE
              + SIZE_SHELBUF + MAX_DELLEVEL * DTA_SIZE + COPY_BUF)
WIN_XCELL, WIN_WCELL, WIN_HCELL = 2, 38, 12
# where the model keeps a string the desktop passes from its stack (the
# target's address is the compiler's; the gate compares G, not records)
STACK_STRING = 0x00FFFE00
STACK_STRING2 = 0x00FFFE80              # ...and the destination's
WIN_YCELL = (6, 8, 10, 13)

# GLOBES, field by field in the order desk.h declares them; sizes as
# cc65816 lays them out (WORD 2, a near pointer 2, a far pointer 4,
# GRECT 8, no padding).
# A PLAIN POINTER IS TWO BYTES OR FOUR, and which it is follows the
# desktop's data model rather than being restated here: under
# --data-model=large every `OBJECT *` and `const char *` in desk.h's G is
# a 32-bit address.  Its `FAR *` fields (g_dta, g_opdta, g_cnxsave,
# g_shelbuf, g_copybuf) are four in BOTH models and are not listed here.
# Measured rather than assumed: G is 2054 bytes small and 2070 large, and
# the eight fields below are exactly that difference.
def _desk_large():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "build", "desktop.map"),
                  "r", errors="replace") as f:
            return "clib-lc-ld.a" in f.read(4096)
    except OSError:
        return False


PTR = 4 if _desk_large() else 2

GLOBES = [("a_menu", PTR), ("a_info", PTR), ("a_mkdir", PTR),
          ("a_delete", PTR),
          ("a_finfo", PTR), ("a_iblist", PTR), ("g_handle", 2),
          ("g_wchar", 2), ("g_hchar", 2), ("g_wbox", 2), ("g_hbox", 2),
          ("g_desk", 8), ("g_wicon", 2), ("g_hicon", 2),
          ("g_iview", 2), ("g_isort", 2), ("g_ifit", 2),
          ("g_iwext", 2), ("g_ihext", 2), ("g_iwint", 2),
          ("g_ihint", 2), ("g_fline", PTR), ("g_fmark", PTR),
          ("g_icw", 2),
          ("g_ich", 2), ("g_icols", 2), ("g_screenfree", 2), ("g_rmsg", 16),
          ("g_wcnt", 2), ("g_nfiles", 4), ("g_ndirs", 4), ("g_opsize", 4),
          ("g_dta", 4), ("g_opdta", 4), ("g_cnxsave", 4), ("g_shelbuf", 4),
          ("g_copybuf", 4),
          ("g_wlist", NUM_WNODES * WNODE_SIZE),
          ("g_patcol", N_SCREENS * 2 * 2),
          ("g_screen", NUM_SOBS * OBJ_SIZE),
          ("g_screeninfo", NUM_ITEMS * SCREENINFO_SIZE)]
GLOBES_SIZE = sum(n for _, n in GLOBES)


def g_offset(name):
    off = 0
    for field, size in GLOBES:
        if field == name:
            return off
        off += size
    raise KeyError(name)


def w(x):
    """A WORD as the target stores it."""
    return (x & 0xFFFF).to_bytes(2, "little")


def dw(x):
    """A LONG."""
    return (x & 0xFFFFFFFF).to_bytes(4, "little")


def p(x):
    """A plain pointer, as wide as the desktop's data model makes it."""
    return dw(x) if PTR == 4 else w(x)


def signed(x):
    """A WORD the model returned through a result record, as the
    program's WORD sees it."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def mul_div(m1, m2, d1):
    return (m1 * m2) // d1                  # never negative here


def rc_intersect(p1, p2):
    """p2 becomes the part of it inside p1; True if any is."""
    tw = min(p2.x + p2.w, p1.x + p1.w)
    th = min(p2.y + p2.h, p1.y + p1.h)
    tx = max(p2.x, p1.x)
    ty = max(p2.y, p1.y)
    p2.x, p2.y, p2.w, p2.h = tx, ty, tw - tx, th - ty
    return tw > tx and th > ty


def far_strcmp(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    ca = ord(a[i]) if i < len(a) else 0
    cb = ord(b[i]) if i < len(b) else 0
    return ca - cb


class CharArray:
    """A char[size] the program writes into in place with put_str: the
    bytes past the NUL stay what they were, as the target's do, and the
    model reads the string through .s the way it reads a Text."""

    def __init__(self, size):
        self.size = size
        self.raw = bytearray(size)

    @property
    def s(self):
        n = self.raw.find(0)
        return bytes(self.raw if n < 0 else self.raw[:n]).decode("latin-1")

    def put(self, s, at=0):
        """The chars and a NUL from `at`; returns where the NUL went."""
        b = s.encode("latin-1")
        assert at + len(b) < self.size, (s, at, self.size)
        self.raw[at:at + len(b)] = b
        self.raw[at + len(b)] = 0
        return at + len(b)

    def pack(self):
        return bytes(self.raw)


class Fnode:
    """A directory entry in a window's listing (far memory: not in G)."""
    __slots__ = ("obid", "flags", "seq", "attr", "time", "date", "size",
                 "name")

    def __init__(self, attr, time, date, size, name):
        self.obid = self.flags = self.seq = 0
        self.attr, self.time, self.date, self.size, self.name = (
            attr, time, date, size, name)


class Pnode:
    def __init__(self, spec_addr):
        self.count, self.size = 0, 0
        self.spec_addr = spec_addr
        self.spec = CharArray(LEN_ZPATH)
        self.flist = 0
        self.fnodes = []

    def pack(self):
        return (w(self.count) + dw(self.size) + self.spec.pack()
                + dw(self.flist))


class Wnode:
    def __init__(self, addr):
        self.addr = addr
        self.id = self.root = 0
        self.cvrow = self.cvcol = 0
        self.pncol = self.pnrow = self.vnrow = self.vncol = 0
        self.path = Pnode(addr + WN_SPEC)
        self.name = CharArray(LEN_WNAME)
        self.info = CharArray(LEN_ZINFO)

    def pack(self):
        return (b"".join(w(x) for x in (self.id, self.root,
                                        self.cvrow, self.cvcol,
                                        self.pncol, self.pnrow,
                                        self.vnrow, self.vncol))
                + self.path.pack() + self.name.pack() + self.info.pack())


class Wsave:
    """A window's place between programs: a slot of CSAVE (far memory,
    in the arena after the FNODEs)."""
    __slots__ = ("x", "y", "w", "h", "hsl", "vsl", "path")

    def __init__(self):
        self.x = self.y = self.w = self.h = self.hsl = self.vsl = 0
        self.path = ""


class NeedsInput(Exception):
    """The desktop is in a wait the gate gave no input for."""


class Desktop:
    """desktop.c against the model.  `inputs` is a list of step producers,
    one per wait that blocks for input (evnt_multi with MU_BUTTON with
    nothing queued, form_do, form_alert) in the order the desktop enters
    them; each is called with the Desktop just before the wait and
    returns the plan steps for it -- so it can ask the model where things
    are at that moment."""

    def __init__(self, v, a, mark, link_near, near_size, g_link, drvmap, inputs,
                 imbase=None, far_base=None, link_bank=2, rsc_far=None,
                 dos_brk=None):
        self.v, self.a = v, a
        self.near = (mark + 0xFF) & ~0xFF
        if far_base is None:
            # SMALL DATA: app_load's pool_alloc(near_size, 0x100) holds the
            # globals, and rs_load's pool_alloc(size, 2) follows it
            # (src/sys/app.c, src/aes/rsrc.c).
            self.G = self.near + (g_link - link_near)
            self.rsc_base = (self.near + near_size + 1) & ~1
        else:
            # LARGE DATA: the globals are in far bss, which app_load placed
            # with the rest of the far image (src/sys/app.c, app_far), and
            # rs_load put the resource far as well rather than in the pool
            # -- which is the whole point, the pool being 14 KB of bank $00
            # against 14.9 MB out here.
            self.G = (far_base + (((g_link >> 16) - link_bank) << 16)
                      + (g_link & 0xFFFF))
            self.rsc_base = rsc_far
        # where rs_load put the resource's icon bitmaps: far, when it moved
        # them, which is what lets the pool have them back (src/aes/rsrc.c)
        self.imbase = imbase
        self.g_screen_addr = self.G + g_offset("g_screen")
        self.g_screeninfo_addr = self.G + g_offset("g_screeninfo")
        a.dos_drvmap = drvmap
        self.inputs = list(inputs)
        self.script, self.plan, self.waits = [], {}, []
        # G as the program keeps it
        self.a_menu = self.a_info = self.a_iblist = 0
        self.handle = self.wchar = self.hchar = self.wbox = self.hbox = 0
        self.desk = Rect()
        self.wicon = self.hicon = self.icw = self.ich = 0
        self.iview = V_ICON
        self.isort = S_NAME
        self.ifit = 1                   # desktop.c: the donor's win_start
        self.icols = 0
        self.iwext = self.ihext = self.iwint = self.ihint = 0
        self.fline = self.fmark = 0
        self.screenfree = 0
        self.rmsg = [0] * 8
        self.wcnt, self.dta, self.opdta = 0, 0, 0
        self.nfiles = self.ndirs = self.opsize = 0
        self.a_mkdir = self.a_delete = self.a_finfo = 0
        # the backgrounds, a pair per screen: app_start seeds the
        # defaults and a "#Q" line overwrites them
        self.patcol = [[0, 0] for _ in range(N_SCREENS)]
        self.cnxsave = self.shelbuf = self.copybuf = 0
        self.wsave = [Wsave() for _ in range(NUM_WNODES)]
        # the desktop's copy of the shell buffer, a far CharArray the
        # model's shel_get/shel_put copy into and out of
        self.shelbuf_data = CharArray(SIZE_SHELBUF)
        wlist = self.G + g_offset("g_wlist")
        self.wlist = [Wnode(wlist + i * WNODE_SIZE) for i in range(NUM_WNODES)]
        for pw in self.wlist:
            a.mem[pw.path.spec_addr] = pw.path.spec
            a.mem[pw.addr + WN_NAME] = pw.name
            a.mem[pw.addr + WN_INFO] = pw.info
        self.screen = [Obj(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) for _ in range(NUM_SOBS)]
        # SCREENINFO per item: the ICONBLK (None until the slot is first
        # used; it keeps its last one after) and the label, in place
        self.info = [None] * NUM_ITEMS
        self.labels = [CharArray(LABEL_LEN) for _ in range(NUM_ITEMS)]
        self.lines = [CharArray(LEN_FNODE) for _ in range(NUM_ITEMS)]
        self.istext = [False] * NUM_ITEMS       # which half of the union
        for i, label in enumerate(self.labels):
            a.mem[self.info_addr(WOBS_START + i) + ICONBLK_SIZE] = label
        self.rsc = None

    # -- the ABI -----------------------------------------------------------
    def call(self, op, ints=(), pts=(), tree=None, steps=None):
        """One call: the record goes on the script, its input on the plan,
        the model answers now.  Returns (intout, ptsout)."""
        rec = (op, tuple(pts), tuple(ints))
        if tree is not None:
            rec += (tree,)
        i = len(self.script)
        self.script.append(rec)
        if steps:
            self.plan[i] = list(steps)
        res = aesref.resume(self.v, self.a, [rec],
                            {0: list(steps)} if steps else None)[0]
        return list(res[2:2 + RESULT_INTOUT]), list(res[2 + RESULT_INTOUT:])

    def take_input(self, what):
        """The next producer's steps for the call about to be made."""
        if not self.inputs:
            raise NeedsInput(f"call {len(self.script)}: {what} with no input left")
        self.waits.append(len(self.script))
        return self.inputs.pop(0)(self)

    def wait(self, flags, clicks, mask, state, ms, blocking):
        """evnt_multi as desktop.c calls it: no mouse rectangles, the
        message into G.g_rmsg.  A blocking wait needs input only when
        nothing is queued for the program -- with a message waiting it
        returns at once, on the target as here.  Returns (which, mx, my,
        button, kstate, kret, bret)."""
        steps = None
        if blocking and not self.a.gl_queue:
            steps = self.take_input(f"evnt_multi {flags:#x}")
        io, _ = self.call(EVNT_MULTI,
                          (flags, clicks, mask, state) + (0,) * 10
                          + (ms & 0xFFFF, ms >> 16), steps=steps)
        if io[0] & MU_MESAG:
            self.rmsg = list(io[7:15])
        return io[0:7]

    def form_alert(self, defbut, text):
        """form_alert: the string is the record's address slot, the way
        the harness stages one (aesref.run(..., buffers=))."""
        self.a.fs_strings[text] = text
        io, _ = self.call(FORM_ALERT, (defbut,), tree=text,
                          steps=self.take_input("form_alert"))
        return io[0]

    # -- GEMDOS (src/app/gemlib.c: a LONG is two words, low first) ---------
    def gemdos(self, fn, ints=()):
        io, _ = self.call(fn, ints)
        ret = io[0] | (io[1] << 16)
        return ret - (1 << 32) if ret & 0x80000000 else ret

    def gemdos_long(self, fn, n, *rest):
        return self.gemdos(fn, (n & 0xFFFF, (n >> 16) & 0xFFFF) + rest)

    # -- dialogs -------------------------------------------------------------
    def start_dialog(self, tree):
        io, po = self.call(FORM_CENTER, tree=tree)
        self.dlg = Rect(io[0], io[1], io[2], po[0])
        d = self.dlg
        self.call(FORM_DIAL, (FMD_START, 0, 0, 0, 0, d.x, d.y, d.w, d.h))
        self.call(OBJC_DRAW, (ROOT, MAX_DEPTH), (d.x, d.y, d.w, d.h), tree=tree)

    def end_dialog(self):
        d = self.dlg
        self.call(FORM_DIAL, (FMD_FINISH, 0, 0, 0, 0, d.x, d.y, d.w, d.h))

    def fun_alert(self, defbut, stnum):
        """deskfun.c fun_alert: the text is a free string of the
        resource, fetched by index -- so it can be translated -- and
        rsrc_gaddr answers the bank-$00 address form_alert wants."""
        addr = self.rsrc_gaddr(R_STRING, stnum)
        return self.form_alert(defbut, self.a.mem[addr].s)

    def busy(self, on):
        self.call(WIND_UPDATE, (BEG_UPDATE,))
        self.call(GRAF_MOUSE, (HOURGLASS if on else ARROW,))
        self.call(WIND_UPDATE, (END_UPDATE,))

    # -- the resource (rsrc.c on the target, tools/rsc.py here) -------------
    def rsrc_load(self):
        self.call(RSRC_LOAD)
        a = self.a
        r = deskrsc.build()
        image, trees, mem = r.expect(self.rsc_base, self.wchar, self.hchar,
                                     a.gl_width, imbase=self.imbase)
        self.rsc, self.rsc_image = r, image
        for t, objs in enumerate(trees):
            a.trees[r.addr(R_TREE, t, self.rsc_base)] = objs
        a.mem.update(mem)
        return 1

    def wind_str(self, wh, field, addr):
        """WF_NAME / WF_INFO: the address in two words, HIGH FIRST, as the
        ST passes it and as src/aes/wind.c takes it.  Both words carry
        something once G is in far memory (src/desk/deskwin.c)."""
        self.wind_set(wh, field, addr >> 16, addr & 0xFFFF)

    def rsrc_gaddr(self, rtype, index):
        self.call(RSRC_GADDR, (rtype, index))
        return self.rsc.addr(rtype, index, self.rsc_base)

    def set_version(self):
        """AES_VERSION over the resource's "0.00", as global[0] has it."""
        spec = self.a.trees[self.a_info][DEVERSN].ob_spec
        old = self.a.mem[spec]
        g = AES_VERSION
        s = list(old.s)
        s[0] = "0123456789ABCDEF"[(g >> 8) & 15]
        s[2] = "0123456789ABCDEF"[(g >> 4) & 15]
        s[3] = "0123456789ABCDEF"[g & 15]
        self.a.mem[spec] = Text("".join(s), old.size)

    # -- the window manager, as deskwin.c wraps it -------------------------
    def wind_get_rect(self, wh, field):
        io, _ = self.call(WIND_GET, (wh, field))
        return Rect(*io[1:5])

    def wind_set_rect(self, wh, field, r):
        self.call(WIND_SET, (wh, field, r.x, r.y, r.w, r.h))

    def wind_set(self, wh, field, a=0, b=0, c=0, d=0):
        self.call(WIND_SET, (wh, field, a, b, c, d))

    # -- the screen tree (deskobj.c) ---------------------------------------
    def r_set(self, obj, x, y, w_, h):
        o = self.screen[obj]
        o.ob_x, o.ob_y, o.ob_width, o.ob_height = x, y, w_, h

    def obj_add(self, parent, obj):
        pp = self.screen[parent]
        last = pp.ob_tail
        self.screen[obj].ob_next = parent
        if last == NIL:
            pp.ob_head = obj
        else:
            self.screen[last].ob_next = obj
        pp.ob_tail = obj

    def obj_init(self):
        for i in range(WOBS_START):
            o = self.screen[i]
            o.ob_head = o.ob_next = o.ob_tail = NIL
        for i in range(WOBS_START, NUM_SOBS - 1):
            self.screen[i].ob_next = i + 1
        self.screen[NUM_SOBS - 1].ob_next = NIL
        self.screenfree = WOBS_START
        self.screen[ROOT] = Obj(NIL, NIL, NIL, G_IBOX, NONE, NORMAL, 0, 0, 0, 0, 0)
        self.r_set(ROOT, 0, 0, self.desk.x + self.desk.w, self.desk.y + self.desk.h)
        for i in range(NUM_WNODES + 1):
            self.screen[DROOT + i] = Obj(NIL, NIL, NIL, G_BOX, NONE, NORMAL,
                                         WINDOW_SPEC, 0, 0, 0, 0)
            self.obj_add(ROOT, DROOT + i)
        self.a.trees[self.g_screen_addr] = self.screen

    def obj_walloc(self, x, y, w_, h):
        for i in range(DROOT + 1, WOBS_START):
            o = self.screen[i]
            if not (o.ob_width and o.ob_height):
                self.r_set(i, x, y, w_, h)
                return i
        return 0

    def obj_wfree(self, obj, x, y, w_, h):
        win = self.screen[obj]
        self.r_set(obj, x, y, w_, h)
        if win.ob_head >= WOBS_START:
            oldfree = self.screenfree
            self.screenfree = win.ob_head
            i = win.ob_head
            while True:
                item = self.screen[i]
                if item.ob_next < WOBS_START:
                    item.ob_next = oldfree
                    break
                i = item.ob_next
        win.ob_head = win.ob_tail = NIL

    def obj_ialloc(self, wparent, x, y, w_, h):
        objnum = self.screenfree
        if objnum < WOBS_START:
            return 0
        o = self.screen[objnum]
        self.screenfree = o.ob_next
        o.ob_next = o.ob_head = o.ob_tail = NIL
        self.obj_add(wparent, objnum)
        self.r_set(objnum, x, y, w_, h)
        return objnum

    def info_addr(self, obj):
        return self.g_screeninfo_addr + (obj - WOBS_START) * SCREENINFO_SIZE

    def obj_info(self, obj):
        return self.info[obj - WOBS_START]

    def obj_clear(self, obid):
        """The item's store emptied before it is written (deskobj.c
        obj_clear): the union's two halves are different lengths and a
        slot is reused in both views, so what is past the text has to be
        nothing rather than what the last item left."""
        k = obid - WOBS_START
        self.labels[k].raw[:] = bytes(LABEL_LEN)
        self.lines[k].raw[:] = bytes(LEN_FNODE)

    def obj_icon(self, wparent, x, y, which, label, letter):
        obid = self.obj_ialloc(wparent, x, y, self.wicon, self.hicon)
        if not obid:
            return 0
        self.obj_clear(obid)
        self.istext[obid - WOBS_START] = False
        o = self.screen[obid]
        o.ob_state, o.ob_flags, o.ob_type = NORMAL, NONE, G_ICON
        src = self.a.mem[self.a_iblist + which * ICONBLK_SIZE]
        addr = self.info_addr(obid)
        ib = Iconblk(src.pmask, src.pdata, src.ptext, src.char, src.xchar,
                     src.ychar, Rect(src.icon.x, src.icon.y, src.icon.w, src.icon.h),
                     Rect(src.text.x, src.text.y, src.text.w, src.text.h))
        o.ob_spec = addr
        ib.icon.x = (self.wicon - ib.icon.w) // 2
        ib.text.y = ib.icon.h
        ib.text.w = MAX_ICONTEXT_WIDTH * self.wchar
        ib.text.h = self.hchar + 2
        ib.char = (ib.char & 0xFF00) | letter
        self.labels[obid - WOBS_START].put(label[:LABEL_LEN - 1])
        ib.ptext = addr + ICONBLK_SIZE
        self.info[obid - WOBS_START] = ib
        self.a.mem[addr] = ib
        return obid

    def obj_text(self, wparent, x, y, w_, h):
        """An item object for the text view: a G_STRING over the line,
        which the caller fills in place (deskobj.c obj_text)."""
        obid = self.obj_ialloc(wparent, x, y, w_, h)
        if not obid:
            return 0
        self.obj_clear(obid)
        self.istext[obid - WOBS_START] = True
        o = self.screen[obid]
        o.ob_state, o.ob_flags, o.ob_type = NORMAL, NONE, G_STRING
        o.ob_spec = self.info_addr(obid)
        self.info[obid - WOBS_START] = None
        self.a.mem[o.ob_spec] = self.lines[obid - WOBS_START]
        return obid

    # -- the desk (desktop.c) ------------------------------------------------
    def snap_icon(self, gx, gy):
        columns = self.desk.w // self.icw
        rows = self.desk.h // self.ich
        cx = min(gx, columns - 1)
        cy = min(gy, rows - 1)
        spare = self.desk.w - columns * self.icw
        px = cx * self.icw + spare // columns
        spare = self.desk.h - rows * self.ich
        py = cy * self.ich + spare // rows + self.desk.y
        return px, py

    def desk_icon(self, gx, gy, which, label, letter):
        x, y = self.snap_icon(gx, gy)
        return self.obj_icon(DROOT, x, y, which, label, letter)

    def desk_build(self):
        a = self.a
        ib0 = a.mem[self.a_iblist]
        self.wicon = MAX_ICONTEXT_WIDTH * self.wchar + 2 * ib0.text.x
        self.hicon = ib0.icon.h + self.hchar + 2
        xcnt = self.desk.w // (self.wicon + MIN_WINT)
        self.icw = self.desk.w // xcnt
        ycnt = self.desk.h // (self.hicon + MIN_HINT)
        self.ich = self.desk.h // ycnt
        self.obj_wfree(DROOT, 0, 0, self.desk.x + self.desk.w,
                       self.desk.y + self.desk.h)
        self.screen[DROOT].ob_spec = DESK_SPEC
        disk = a.mem[self.rsrc_gaddr(R_STRING, STDISK)].s
        trash = a.mem[self.rsrc_gaddr(R_STRING, STTRASH)].s
        io, _ = self.call(DGETDRV)
        io, _ = self.call(DSETDRV, (io[0],))
        drvmap = io[0] & 0xFFFF
        n = 0
        for drive in range(MAX_DRIVES):
            if not drvmap & (1 << drive):
                continue
            gx, gy = n % xcnt, n // xcnt
            label = disk[:LABEL_LEN - 3] + " " + chr(ord("A") + drive)
            self.desk_icon(gx, gy, IB_HARD if drive > 1 else IB_FLOPPY,
                           label, ord("A") + drive)
            n += 1
        gx, gy = 0, ycnt - 1
        if n and (n - 1) // xcnt >= gy:
            gx = xcnt - 1
        self.desk_icon(gx, gy, IB_TRASH, trash, 0)

    def sel_item(self, root):
        i = self.screen[root].ob_head
        while i >= WOBS_START:
            if self.screen[i].ob_state & SELECTED:
                return i
            i = self.screen[i].ob_next
        return 0

    # -- the windows (deskwin.c) -------------------------------------------
    def win_start(self):
        self.wcnt = 0
        arena = self.gemdos_long(MALLOC, ARENA_SIZE)
        if arena <= 0:
            return False
        self.dta = arena
        self.gemdos_long(FSETDTA, arena)
        for i, pw in enumerate(self.wlist):
            pw.id = 0
            pw.root = DROOT + 1 + i
            pw.path.flist = arena + DTA_SIZE + i * NUM_FNODES * FNODE_SIZE
        self.cnxsave = arena + DTA_SIZE + NUM_WNODES * NUM_FNODES * FNODE_SIZE
        self.shelbuf = self.cnxsave + CSAVE_SIZE
        self.opdta = self.shelbuf + SIZE_SHELBUF
        self.copybuf = self.opdta + MAX_DELLEVEL * DTA_SIZE
        self.a.mem[self.shelbuf] = self.shelbuf_data
        for ws in self.wsave:
            ws.x = ws.y = ws.w = ws.h = ws.hsl = ws.vsl = 0
            ws.path = ""
        return True

    def win_find(self, wh):
        for pw in self.wlist:
            if pw.id == wh:
                return pw
        return None

    def win_ontop(self):
        wob = self.screen[ROOT].ob_tail
        o = self.screen[wob]
        if o.ob_width and o.ob_height:
            return self.wlist[wob - (DROOT + 1)]
        return None

    def win_top(self, pw):
        self.call(OBJC_ORDER, (pw.root, NIL), tree=self.g_screen_addr)

    def win_free(self, pw):
        if pw.id != -1:
            self.call(WIND_DELETE, (pw.id,))
        self.wcnt -= 1
        pw.id = 0
        self.call(OBJC_ORDER, (pw.root, 1), tree=self.g_screen_addr)
        self.obj_wfree(pw.root, 0, 0, 0, 0)

    def win_alloc(self):
        if self.wcnt == NUM_WNODES:
            return None
        ws = self.wsave[self.wcnt]
        r = Rect(ws.x, ws.y, ws.w, ws.h)
        wob = self.obj_walloc(r.x, r.y, r.w, r.h)
        if not wob:
            return None
        self.wcnt += 1
        pw = self.wlist[wob - (DROOT + 1)]
        pw.root = wob
        pw.cvrow = pw.cvcol = 0
        pw.pncol = (r.w - self.wchar) // (self.wicon + MIN_WINT)
        pw.pnrow = (r.h - self.hchar) // (self.hicon + MIN_HINT)
        pw.vnrow = pw.vncol = 0
        d = self.desk
        io, _ = self.call(WIND_CREATE, (WINDOW_STYLE, d.x, d.y, d.w, d.h))
        pw.id = signed(io[0])
        if pw.id != -1:
            return pw
        self.win_free(pw)
        return None

    # -- the listing ---------------------------------------------------------
    @staticmethod
    def win_fnode(pw, obj):
        for pf in pw.path.fnodes[:pw.path.count]:
            if pf.obid == obj:
                return pf
        return None

    def pn_fcomp(self, a, b):
        """The field the current order compares (deskwin.c pn_fcomp):
        date and size run the other way round, and every order falls
        back to the name."""
        chk = 0
        if self.isort == S_DATE:
            chk = b.date - a.date or b.time - a.time
        elif self.isort == S_SIZE:
            chk = b.size - a.size
        elif self.isort == S_TYPE:
            def ext(n):
                k = n.find(".")
                return n[k:] if k >= 0 else ""
            chk = far_strcmp(ext(a.name), ext(b.name))
        elif self.isort == S_NSRT:
            chk = a.seq - b.seq
        if chk:
            return -1 if chk < 0 else 1
        return far_strcmp(a.name, b.name)

    def pn_comp(self, a, b):
        if self.isort != S_NSRT and (a.attr ^ b.attr) & FA_SUBDIR:
            return -1 if a.attr & FA_SUBDIR else 1
        return self.pn_fcomp(a, b)

    @staticmethod
    def pn_open(pn, spec):
        if len(spec) >= LEN_ZPATH:
            return False
        pn.spec.put(spec)
        pn.count = pn.size = 0
        pn.fnodes = []
        return True

    def pn_active(self, pn):
        pn.size = pn.count = 0                  # read again after a delete
        pn.fnodes = []
        ret = self.gemdos(FSFIRST, (pn.spec_addr & 0xFFFF, pn.spec_addr >> 16,
                                    DISPATTR))
        count = 0
        while ret == E_OK and count < NUM_FNODES:
            name, attr, time, date, size = self.a.dos_dta_data
            if name[:1] != ".":
                fn = Fnode(attr & 0xFF, time, date, size, name[:LEN_ZFNAME - 1])
                fn.seq = count              # where the directory had it
                i = count                   # insertion: slide the ones after it up
                while i > 0 and self.pn_comp(fn, pn.fnodes[i - 1]) < 0:
                    i -= 1
                pn.fnodes.insert(i, fn)
                count += 1
                pn.size += fn.size
            ret = self.gemdos(FSNEXT)
        pn.count = count

    @staticmethod
    def win_sname(pw):
        d = pw.name.put(" ")
        d = pw.name.put(pw.path.spec.s, d)
        pw.name.put(" ", d)

    def win_sinfo(self, pw):
        pw.info.put(f" {pw.path.size} bytes used in {pw.path.count} items.")
        self.wind_str(pw.id, WF_INFO, pw.addr + WN_INFO)

    @staticmethod
    def win_which(pf):
        if pf.attr & FA_SUBDIR:
            return IB_FOLDER
        k = pf.name.find(".")
        if k >= 0 and pf.name[k:] in (".G4A", ".PRG"):   # .PRG: the same, by an Atari name
            return IB_APPL
        return IB_DOCU

    def win_view(self):
        """What an item of the current view fills, and the space in front
        of it (deskwin.c win_view).  The text line's left margin is EVEN
        here, where the donor makes it odd for the ST's fast text: at
        4bpp an odd x is the slow path, not the fast one."""
        if self.iview == V_TEXT:
            self.iwext, self.ihext = LEN_FNODE * self.wchar, self.hchar
            self.iwint, self.ihint = 2 * self.wchar, 2
        else:
            self.iwext, self.ihext = self.wicon, self.hicon
            self.iwint, self.ihint = MIN_WINT, MIN_HINT
        # ...and the grid a window that does NOT size to fit is laid on:
        # the columns the widest window this screen can show would hold
        d = self.desk
        io, _ = self.call(WIND_CALC, (WC_WORK, WINDOW_STYLE, d.x, d.y, d.w, d.h))
        self.icols = max(1, io[3] // (self.iwext + self.iwint))

    def win_line(self, k, pf):
        """One line of the text view into item slot k, from the template
        the resource carries (deskwin.c win_line): each run of a
        placeholder letter takes one field, in the template's order and
        width."""
        def num(n, value, pad):
            d = str(value)[-n:] if value else "0"
            return d.rjust(n, pad)[-n:]

        t = self.a.mem[self.fline].s
        mark = self.a.mem[self.fmark].s
        out, i = "", 0
        while i < len(t) and len(out) < LEN_FNODE - 1:
            c = t[i]
            n = 1
            while i + n < len(t) and t[i + n] == c:
                n += 1
            n = min(n, LEN_FNODE - 1 - len(out))
            if c == "f":
                out += mark[0 if pf.attr & FA_SUBDIR else
                            1 if pf.attr & FA_RDONLY else 2] * n
            elif c in "ne":
                name = pf.name
                k2 = name.find(".")
                part = (name[:k2] if k2 >= 0 else name) if c == "n" else (
                    name[k2 + 1:] if k2 >= 0 else "")
                out += part[:n].ljust(n)
            elif c == "s":
                out += " " * n if pf.attr & FA_SUBDIR else num(n, pf.size, " ")
            elif c == "d":
                out += num(n, pf.date & 0x1F, "0")
            elif c == "m":
                out += num(n, (pf.date >> 5) & 0x0F, "0")
            elif c == "y":
                out += num(n, ((pf.date >> 9) + 80) % 100, "0")
            elif c == "H":
                out += num(n, (pf.time >> 11) & 0x1F, "0")
            elif c == "M":
                out += num(n, (pf.time >> 5) & 0x3F, "0")
            else:
                out += c * n
            i += n
        self.lines[k].put(out)

    def win_bldview(self, pw, r):
        iwspc, ihspc = self.iwext + self.iwint, self.ihext + self.ihint
        pn = pw.path
        self.obj_wfree(pw.root, r.x, r.y, r.w, r.h)
        wfit = max(r.w // iwspc, 1)
        hfit = max(r.h // ihspc, 1)
        for pf in pn.fnodes[:pn.count]:
            pf.obid = 0
        # the grid the LISTING is laid on: the window's columns with size
        # to fit, the screen's without (deskwin.c win_bldview)
        if self.ifit:
            pw.vncol = wfit
            pw.vnrow = (pn.count + wfit - 1) // wfit
        else:
            pw.vncol = min(pn.count, self.icols)
            pw.vnrow = (pn.count + self.icols - 1) // self.icols
        pw.vncol = max(pw.vncol, 1)
        pw.vnrow = max(pw.vnrow, 1)
        pw.pncol = wfit
        pw.pnrow = min(hfit, pw.vnrow)
        while pw.vncol - pw.cvcol < min(wfit, pw.vncol):
            pw.cvcol -= 1
        while pw.vnrow - pw.cvrow < pw.pnrow:
            pw.cvrow -= 1
        hfit = min(pw.vnrow - pw.cvrow, pw.pnrow + 1)     # a row may show in part
        row = 0
        while row < hfit:
            for col in range(pw.pncol):
                vcol = pw.cvcol + col
                if vcol >= pw.vncol:
                    break
                i = (pw.cvrow + row) * pw.vncol + vcol
                if i >= pn.count:
                    break
                pf = pn.fnodes[i]
                if self.iview == V_TEXT:
                    obid = self.obj_text(pw.root, col * iwspc + self.iwint,
                                         row * ihspc + self.ihint,
                                         self.iwext, self.ihext)
                    if obid:
                        self.win_line(obid - WOBS_START, pf)
                else:
                    obid = self.obj_icon(pw.root, col * iwspc + self.iwint,
                                         row * ihspc + self.ihint,
                                         self.win_which(pf), pf.name, 0)
                if not obid:
                    row = hfit                  # no items left: stop
                    break
                pf.obid = obid
                o = self.screen[obid]
                o.ob_state = WHITEBAK | (SELECTED if pf.flags & F_SELECTED else 0)
                o.ob_flags = NONE
            row += 1
        self.wind_set(pw.id, WF_HSLSIZ,
                      mul_div(pw.pncol, 1000, pw.vncol)
                      if pw.vncol > pw.pncol else 1000)
        self.wind_set(pw.id, WF_HSLIDE,
                      mul_div(pw.cvcol, 1000, pw.vncol - pw.pncol)
                      if pw.vncol > pw.pncol else 0)
        self.wind_set(pw.id, WF_VSLSIZ, mul_div(pw.pnrow, 1000, pw.vnrow))
        self.wind_set(pw.id, WF_VSLIDE,
                      mul_div(pw.cvrow, 1000, pw.vnrow - pw.pnrow)
                      if pw.vnrow > pw.pnrow else 0)

    def desk_verify(self, wh):
        pw = self.win_find(wh)
        if pw:
            self.win_bldview(pw, self.wind_get_rect(wh, WF_WXYWH))

    def do_wredraw(self, wh, pc):
        root = DROOT
        if wh != DESKWH:
            pw = self.win_find(wh)
            if pw is None:
                return
            root = pw.root
        self.call(GRAF_MOUSE, (M_OFF,))
        t = self.wind_get_rect(wh, WF_FIRSTXYWH)
        while t.w and t.h:
            if rc_intersect(pc, t):
                self.call(OBJC_DRAW, (root, MAX_DEPTH), t.tuple(),
                          tree=self.g_screen_addr)
            t = self.wind_get_rect(wh, WF_NEXTXYWH)
        self.call(GRAF_MOUSE, (M_ON,))

    def win_scroll(self, pw, newcv):
        newcv = max(min(newcv, pw.vnrow - pw.pnrow), 0)
        if newcv == pw.cvrow:
            return
        pw.cvrow = newcv
        t = self.wind_get_rect(pw.id, WF_WXYWH)
        self.win_bldview(pw, t)
        self.do_wredraw(pw.id, t)

    def win_hscroll(self, pw, newcv):
        newcv = max(min(newcv, pw.vncol - pw.pncol), 0)
        if newcv == pw.cvcol:
            return
        pw.cvcol = newcv
        t = self.wind_get_rect(pw.id, WF_WXYWH)
        self.win_bldview(pw, t)
        self.do_wredraw(pw.id, t)

    def win_arrow(self, pw, arrow):
        if arrow == WA_UPPAGE:
            self.win_scroll(pw, pw.cvrow - pw.pnrow)
        elif arrow == WA_DNPAGE:
            self.win_scroll(pw, pw.cvrow + pw.pnrow)
        elif arrow == WA_UPLINE:
            self.win_scroll(pw, pw.cvrow - 1)
        elif arrow == WA_DNLINE:
            self.win_scroll(pw, pw.cvrow + 1)
        elif arrow == WA_LFPAGE:
            self.win_hscroll(pw, pw.cvcol - pw.pncol)
        elif arrow == WA_RTPAGE:
            self.win_hscroll(pw, pw.cvcol + pw.pncol)
        elif arrow == WA_LFLINE:
            self.win_hscroll(pw, pw.cvcol - 1)
        elif arrow == WA_RTLINE:
            self.win_hscroll(pw, pw.cvcol + 1)

    def win_slide(self, pw, permille):
        self.win_scroll(pw, mul_div(permille, pw.vnrow - pw.pnrow, 1000))

    def win_hslide(self, pw, permille):
        self.win_hscroll(pw, mul_div(permille, pw.vncol - pw.pncol, 1000))

    # -- selection -----------------------------------------------------------
    def act_chg(self, wh, root, obj, set_, dodraw):
        pob = self.screen[obj]
        state = pob.ob_state & 0xFFFF
        state = (state | SELECTED) if set_ else (state & ~SELECTED)
        if state == pob.ob_state & 0xFFFF:
            return
        pob.ob_state = state
        if root != DROOT:
            pf = self.win_fnode(self.wlist[root - (DROOT + 1)], obj)
            if pf:
                pf.flags = (pf.flags | F_SELECTED) if set_ else (pf.flags & ~F_SELECTED)
        if dodraw:
            io, _ = self.call(OBJC_OFFSET, (obj,), tree=self.g_screen_addr)
            self.do_wredraw(wh, Rect(io[0], io[1], pob.ob_width, pob.ob_height))

    def act_bsclick(self, wh, root, obj, kstate):
        """What a CLICK does to the selection (deskwin.c act_bsclick):
        SHIFT toggles one item, a plain click makes one the selection,
        and a click on nothing clears it."""
        if kstate & (MODE_LSHIFT | MODE_RSHIFT):
            if obj:
                self.act_chg(wh, root, obj,
                             not (self.screen[obj].ob_state & SELECTED), True)
            return
        if not obj or not (self.screen[obj].ob_state & SELECTED):
            self.act_select(wh, root, obj)

    def act_allselect(self, wh, root, box):
        """Everything of a window's whose cell the rectangle touches,
        selected; what it does not touch, deselected -- what a rubber
        band leaves (deskwin.c act_allselect)."""
        i = self.screen[root].ob_head
        while i >= WOBS_START:
            io, _ = self.call(OBJC_OFFSET, (i,), tree=self.g_screen_addr)
            t = Rect(signed(io[0]), signed(io[1]),
                     self.screen[i].ob_width, self.screen[i].ob_height)
            self.act_chg(wh, root, i, bool(rc_intersect(box, t)), True)
            i = self.screen[i].ob_next

    def act_count(self, root):
        """How many of a window's items are selected, and the first of
        them (deskwin.c act_count)."""
        n, first = 0, 0
        i = self.screen[root].ob_head
        while i >= WOBS_START:
            if self.screen[i].ob_state & SELECTED:
                if not n:
                    first = i
                n += 1
            i = self.screen[i].ob_next
        return n, first

    def act_select(self, wh, root, obj):
        i = self.screen[root].ob_head
        while i >= WOBS_START:
            nxt = self.screen[i].ob_next
            self.act_chg(wh, root, i, i == obj, True)
            i = nxt

    def obj_parent(self, obj):
        while obj >= WOBS_START:
            obj = self.screen[obj].ob_next
        return obj

    def obj_wh(self, parent):
        return DESKWH if parent == DROOT else self.wlist[parent - (DROOT + 1)].id

    # -- opening -------------------------------------------------------------
    def do_xyfix(self, t):
        t.x = signed((t.x + 8) & 0xFFF0)
        if t.y < self.desk.y:
            t.y = self.desk.y

    def do_wopen(self, new_win, wh, curr, pt):
        t = pt.copy()
        self.do_xyfix(t)
        if curr > 0:
            croot = self.obj_parent(curr)
            io, _ = self.call(OBJC_OFFSET, (curr,), tree=self.g_screen_addr)
            o = self.screen[curr]
            self.call(GRAF_GROWBOX, (io[0], io[1], o.ob_width, o.ob_height,
                                     t.x, t.y, t.w, t.h))
            self.act_chg(self.obj_wh(croot), croot, curr, False, new_win)
        if new_win:
            self.call(WIND_OPEN, (wh, t.x, t.y, t.w, t.h))

    def do_wfull(self, wh):
        curr = self.wind_get_rect(wh, WF_CXYWH)
        prev = self.wind_get_rect(wh, WF_PXYWH)
        full = self.wind_get_rect(wh, WF_FXYWH)
        if curr.tuple() == full.tuple():
            self.wind_set_rect(wh, WF_CXYWH, prev)
            self.call(GRAF_SHRINKBOX, prev.tuple() + full.tuple())
        else:
            self.call(GRAF_GROWBOX, curr.tuple() + full.tuple())
            self.wind_set_rect(wh, WF_CXYWH, full)

    def do_diropen(self, pw, new_win, curr, path, pt, redraw):
        self.busy(True)
        if not self.pn_open(pw.path, path):
            self.busy(False)
            return False
        self.pn_active(pw.path)
        self.win_sname(pw)
        self.win_sinfo(pw)
        self.wind_str(pw.id, WF_NAME, pw.addr + WN_NAME)
        self.do_wopen(new_win, pw.id, curr, pt)
        if new_win:
            self.win_top(pw)
        self.desk_verify(pw.id)
        if redraw and not new_win:
            self.do_wredraw(pw.id, self.wind_get_rect(pw.id, WF_WXYWH))
        self.busy(False)
        return True

    def pn_sort(self, pn):
        """The listing put into the current order where it stands, by the
        same insertion sort pn_active runs as it reads (deskwin.c
        pn_sort)."""
        for i in range(1, pn.count):
            fn = pn.fnodes[i]
            j = i
            while j > 0 and self.pn_comp(fn, pn.fnodes[j - 1]) < 0:
                j -= 1
            if j != i:
                pn.fnodes.insert(j, pn.fnodes.pop(i))

    def win_srtall(self):
        for pw in self.wlist:
            if pw.id:
                self.pn_sort(pw.path)

    def win_bdall(self):
        for pw in self.wlist:
            if pw.id:
                self.desk_verify(pw.id)

    def win_shwall(self):
        for pw in self.wlist:
            if pw.id:
                self.do_wredraw(pw.id, self.wind_get_rect(pw.id, WF_WXYWH))

    def win_rebld(self, pw):
        """deskwin.c win_rebld: the listing read again after the disk
        changed under it, the same place and the same view."""
        self.busy(True)
        self.call(FSETDTA, (self.dta & 0xFFFF, self.dta >> 16))
        self.pn_active(pw.path)
        self.win_sname(pw)
        self.win_sinfo(pw)
        self.wind_str(pw.id, WF_NAME, pw.addr + WN_NAME)
        self.desk_verify(pw.id)
        self.do_wredraw(pw.id, self.wind_get_rect(pw.id, WF_WXYWH))
        self.busy(False)

    def do_dopen(self, curr):
        pw = self.win_alloc()
        if pw is None:
            self.fun_alert(1, STNOWIND)
            self.act_chg(DESKWH, DROOT, curr, False, True)
            return False
        path = chr(self.obj_info(curr).char & 0xFF) + ":\\*.*"
        o = self.screen[pw.root]
        box = Rect(o.ob_x, o.ob_y, o.ob_width, o.ob_height)
        if not self.do_diropen(pw, True, curr, path, box, True):
            self.win_free(pw)
            self.act_chg(DESKWH, DROOT, curr, False, True)
            return False
        return True

    def do_fopen(self, pw, curr, name):
        t = self.wind_get_rect(pw.id, WF_WXYWH)
        path = pw.path.spec.s[:-3]                  # "A:\SUB\*.*" less the "*.*"
        if len(path) + len(name) > LEN_ZPATH - 5:
            return False
        path += name + "\\*.*"
        return self.do_diropen(pw, False, curr, path, t, True)

    def do_aopen(self, pw, curr, name):
        """The donor's do_aopen + pro_run + pro_exec: the program's
        directory made the default, then shel_write(SHW_EXEC) with the
        full path and an empty tail; the icon deselected either way.
        The path strings are the desktop's stack, so the records carry
        no address for them."""
        app_path = pw.path.spec.s[:-3]              # "A:\SUB\*.*" less the "*.*"
        if len(app_path) + len(name) >= LEN_ZPATH:
            return False
        self.busy(True)
        self.call(DSETDRV, (ord(app_path[0]) - ord("A"),))
        self.a.mem[STACK_STRING] = Text(app_path)
        if self.gemdos_long(DSETPATH, STACK_STRING) < 0:
            self.busy(False)
            self.fun_alert(1, STDEFDIR)
            return False
        self.busy(False)
        app_path += name
        self.busy(True)
        io, _ = self.call(SHEL_WRITE, (SHW_EXEC, 1, 1))
        ret = io[0]
        if not ret:
            self.busy(False)
        self.do_wopen(False, pw.id, curr, self.desk)
        return ret

    def do_open(self, wh, obj):
        """True only when a program ran (the donor's do_open): the
        desktop is done then."""
        if wh == DESKWH:
            if self.obj_info(obj).char & 0xFF:
                self.do_dopen(obj)
            return False                            # else the trash
        pw = self.win_find(wh)
        if pw is None:
            return False
        pf = self.win_fnode(pw, obj)
        if pf is None:
            return False
        if pf.attr & FA_SUBDIR:
            self.do_fopen(pw, obj, pf.name)
            return False
        if self.win_which(pf) == IB_APPL:
            return self.do_aopen(pw, obj, pf.name)
        return False

    def win_close(self, pw, close_window):
        spec = pw.path.spec.s
        if not close_window:
            last = spec.rfind("\\")                 # the '\' before the "*.*"
            i = max(last, 0)
            while i > 0 and spec[i - 1] != "\\":
                i -= 1
            if i > 0:                               # "A:\SUB\*.*" -> "A:\*.*"
                path = spec[:i] + "*.*"
                t = self.wind_get_rect(pw.id, WF_WXYWH)
                self.do_diropen(pw, False, 0, path, t, True)
                return
        self.call(WIND_CLOSE, (pw.id,))
        self.win_free(pw)

    # -- the windows between programs ----------------------------------------
    @staticmethod
    def scan_2(text, i):
        """The donor's scan_2 over text from i: past the spaces, two hex
        digits (0xFF is -1) or nothing at a CR.  Returns (value, i)."""
        def hex_dig(c):
            n = ord(c)
            if n >= ord("A"):
                n += 9
            return n & 0x0F

        while text[i] == " ":
            i += 1
        v = 0
        if text[i] != "\r":
            v = hex_dig(text[i]) << 4
            v |= hex_dig(text[i + 1])
            i += 2
            if v == 0xFF:
                v = -1
        return v, i

    def inf_write(self):
        """The INF text from the slots into the shell buffer copy; its
        length with the NUL, from the buffer's start."""
        def hex2(v):
            return f" {v & 0xFF:02X}"

        text = f"#R{hex2(INF_REV_LEVEL)}\r\n"
        text += ("#E"
                 + hex2((INF_E1_VIEWTEXT if self.iview == V_TEXT else 0)
                        | ((0 if self.isort == S_NSRT else self.isort) << 5))
                 + hex2(0) + hex2(0) + hex2(0)
                 + hex2((INF_E5_NOSORT if self.isort == S_NSRT else 0)
                        | (0 if self.ifit else INF_E5_NOSIZE))
                 + "\r\n")
        text += ("#Q" + "".join(hex2(v) for pc in self.patcol for v in pc)
                 + "\r\n")
        for ws in self.wsave:
            text += ("#W" + hex2(ws.hsl) + hex2(ws.vsl)
                     + hex2(ws.x // self.wchar) + hex2(ws.y // self.hchar)
                     + hex2(ws.w // self.wchar) + hex2(ws.h // self.hchar)
                     + hex2(0) + " " + ws.path + "@\r\n")
        end = self.shelbuf_data.put(text, CPDATA_LEN)
        return end + 1

    def build_inf(self):
        for i, ws in enumerate(self.wsave):
            ws.x, ws.y = WIN_XCELL * self.wchar, WIN_YCELL[i] * self.hchar
            ws.w, ws.h = WIN_WCELL * self.wchar, WIN_HCELL * self.hchar
            ws.hsl = ws.vsl = 0
            ws.path = ""
        self.inf_write()

    def inf_name(self):
        """The file the layout lives in, on the drive the desktop was
        started from (deskwin.c inf_name)."""
        io, _ = self.call(DGETDRV)
        return f"{chr(ord('A') + io[0])}:\\{INF_NAME}"

    def inf_load(self):
        """The file into the shell buffer copy, FALSE when there is
        none (deskwin.c inf_load)."""
        self.a.mem[STACK_STRING] = Text(self.inf_name())
        fd = self.gemdos_long(FOPEN, STACK_STRING, 0)
        if fd < 0:
            return False
        room = SIZE_SHELBUF - CPDATA_LEN - 1
        buf = self.shelbuf + CPDATA_LEN
        got = self.gemdos(FREAD, (fd, room & 0xFFFF, room >> 16,
                                  buf & 0xFFFF, buf >> 16))
        self.gemdos(FCLOSE, (fd,))
        if got < 0:
            got = 0
        # The model's GEMDOS keeps a file's LENGTH, not its bytes, so
        # what a read gives back is what this desktop last wrote --
        # which it still has, in the buffer it wrote from.
        raw = self.shelbuf_data.raw
        raw[CPDATA_LEN + got] = 0
        return raw[CPDATA_LEN] == ord("#")

    def inf_store(self, n):
        """...and the buffer out to it; `n` is inf_write's length, so
        neither the NUL nor the bytes in front of the text go."""
        self.a.mem[STACK_STRING] = Text(self.inf_name())
        fd = self.gemdos_long(FCREATE, STACK_STRING, 0)
        if fd < 0:
            return False
        length = n - CPDATA_LEN - 1
        buf = self.shelbuf + CPDATA_LEN
        put = self.gemdos(FWRITE, (fd, length & 0xFFFF, length >> 16,
                                   buf & 0xFFFF, buf >> 16))
        self.gemdos(FCLOSE, (fd,))
        return put == length

    def inf_parse(self):
        """The slots from the "#W" lines of whatever is in the buffer."""
        raw = self.shelbuf_data.raw
        n = raw.find(0, CPDATA_LEN)
        text = bytes(raw[CPDATA_LEN:n]).decode("latin-1")
        i, wincnt = 0, 0
        while i < len(text):
            c = text[i]
            i += 1
            if c != "#":
                continue
            if text[i] == "R":
                _, i = self.scan_2(text, i + 1)
            elif text[i] == "E":
                e1, i = self.scan_2(text, i + 1)
                _, i = self.scan_2(text, i)     # the donor's date and clock
                _, i = self.scan_2(text, i)     # formats, and its video
                _, i = self.scan_2(text, i)     # words: the resource's here
                e5, i = self.scan_2(text, i)
                self.desk_view(V_TEXT if e1 & INF_E1_VIEWTEXT else V_ICON)
                self.desk_sort(S_NSRT if e5 & INF_E5_NOSORT
                               else (e1 & INF_E1_SORTMASK) >> 5)
                self.desk_fit(not (e5 & INF_E5_NOSIZE))
            elif text[i] == "Q":
                i += 1
                for pc in self.patcol:
                    pc[0], i = self.scan_2(text, i)
                    pc[1], i = self.scan_2(text, i)
                self.desk_patcol_apply()
            elif text[i] == "W":
                i += 1
                if wincnt < NUM_WNODES:
                    ws = self.wsave[wincnt]
                    ws.hsl, i = self.scan_2(text, i)
                    ws.vsl, i = self.scan_2(text, i)
                    v, i = self.scan_2(text, i)
                    ws.x = v * self.wchar
                    v, i = self.scan_2(text, i)
                    ws.y = v * self.hchar
                    v, i = self.scan_2(text, i)
                    ws.w = v * self.wchar
                    v, i = self.scan_2(text, i)
                    ws.h = v * self.hchar
                    i += 4                          # " 00 ", then the path
                    k = text.find("@", i)
                    ws.path = text[i:min(k, i + LEN_ZPATH - 1)]
                    i = k if k - i < LEN_ZPATH - 1 else i + LEN_ZPATH - 1
                    wincnt += 1


    def desk_screen(self):
        """SCR_COLOUR or SCR_MONO, from the depth appl_init reported."""
        return SCR_COLOUR if self.a.gl_nplanes > 1 else SCR_MONO

    def desk_patcol_apply(self):
        """The remembered pair onto the desk and every window's box;
        the high bytes -- border and text colours -- are left alone."""
        pc = self.patcol[self.desk_screen()]
        o = self.screen[DROOT]
        o.ob_spec = (o.ob_spec & ~PATCOL_MASK) | pc[0]
        for i in range(1, NUM_WNODES + 1):
            o = self.screen[DROOT + i]
            o.ob_spec = (o.ob_spec & ~PATCOL_MASK) | pc[1]

    def desk_patcol(self, deskpc, winpc):
        pc = self.patcol[self.desk_screen()]
        pc[0], pc[1] = deskpc, winpc
        self.desk_patcol_apply()

    def app_start(self):
        """What the shell buffer holds, then the file, then the
        built-in default (deskwin.c app_start)."""
        for pc in self.patcol:
            pc[0] = DESK_SPEC & PATCOL_MASK
            pc[1] = WINDOW_SPEC & PATCOL_MASK
        self.call(SHEL_GET, (SIZE_SHELBUF,), tree=self.shelbuf)
        if self.shelbuf_data.raw[CPDATA_LEN] != ord("#") and not self.inf_load():
            self.build_inf()
        self.inf_parse()

    def inf_save(self):
        """Options -> Save desktop."""
        self.cnx_put()
        return self.inf_store(self.inf_write())

    def inf_read(self):
        """Options -> Read .INF file: the file back, and the windows
        with it -- what is open is closed first."""
        if not self.inf_load():
            return False
        self.inf_parse()
        for pw in self.wlist:
            if pw.id > 0:
                self.win_close(pw, True)
        self.cnx_get()
        return True

    def app_save(self):
        n = self.inf_write()
        self.call(SHEL_PUT, (n,), tree=self.shelbuf)

    def obj_get_obid(self, drive):
        objnum = self.screen[DROOT].ob_head
        while objnum >= WOBS_START:
            o = self.screen[objnum]
            if o.ob_type == G_ICON and (self.obj_info(objnum).char & 0xFF) == drive:
                return objnum
            objnum = o.ob_next
        return 0

    def cnx_put(self):
        """The open windows into the slots, bottom-most first, the rest
        cleared."""
        n = 0
        wob = self.screen[ROOT].ob_head
        while wob > ROOT:
            if wob != DROOT:
                pw = self.wlist[wob - (DROOT + 1)]
                if pw.id > 0:
                    r = self.wind_get_rect(pw.id, WF_CXYWH)
                    self.do_xyfix(r)
                    ws = self.wsave[n]
                    ws.x, ws.y, ws.w, ws.h = r.x, r.y, r.w, r.h
                    ws.hsl, ws.vsl = 0, pw.cvrow
                    ws.path = pw.path.spec.s
                    n += 1
            wob = self.screen[wob].ob_next
        for ws in self.wsave[n:]:
            ws.path = ""

    def cnx_get(self):
        """The windows back from the slots, growing from their drive
        icons."""
        d = self.desk
        for ws in self.wsave:
            if ws.x >= d.w:
                ws.x = d.w // 2
            if ws.y >= d.h:
                ws.y = d.h // 2
            if ws.w <= 0 or ws.w > d.w:
                ws.w = d.w
            if ws.h <= 0 or ws.h > d.h:
                ws.h = d.h
            if not ws.path:
                continue
            obid = self.obj_get_obid(ord(ws.path[0]))
            pw = self.win_alloc()
            if pw is None:
                continue
            pw.cvrow = ws.vsl
            r = Rect(ws.x, ws.y, ws.w, ws.h)
            self.do_xyfix(r)
            ws.x, ws.y = r.x, r.y
            if not self.do_diropen(pw, True, obid, ws.path, r, True):
                self.win_free(pw)

    # -- the window manager's messages ---------------------------------------
    def hndl_wmsg(self, msg):
        wh = msg[3]
        pw = self.win_find(wh)
        kind = msg[0]
        if kind == WM_REDRAW:
            self.do_wredraw(wh, Rect(*msg[4:8]))
        elif kind in (WM_TOPPED, WM_NEWTOP):
            if kind == WM_TOPPED:
                self.wind_set(wh, WF_TOP)
            if pw:
                self.win_top(pw)
        elif kind == WM_CLOSED:             # the closer is File -> Close
            if pw:
                self.win_close(pw, False)
        elif kind == WM_FULLED:
            self.do_wfull(wh)
            self.desk_verify(wh)
        elif kind == WM_ARROWED:
            if pw:
                self.win_arrow(pw, msg[4])
        elif kind == WM_VSLID:
            if pw:
                self.win_slide(pw, msg[4])
        elif kind == WM_HSLID:
            if pw:
                self.win_hslide(pw, msg[4])
        elif kind in (WM_SIZED, WM_MOVED):
            if not pw:
                return
            t = Rect(*msg[4:8])
            self.do_xyfix(t)
            self.wind_set_rect(wh, WF_CXYWH, t)
            if kind == WM_SIZED:
                cols = pw.pncol
                self.desk_verify(wh)
                if pw.pncol != cols:            # the items moved: the AES
                    t = self.wind_get_rect(wh, WF_WXYWH)  # redraws only what it uncovered
                    self.do_wredraw(wh, t)
            else:                               # the items keep their places
                t = self.wind_get_rect(wh, WF_WXYWH)    # in the box: move the box
                self.obj_wfree(pw.root, t.x, t.y, t.w, t.h)
                self.desk_verify(wh)

    # -- the menu ------------------------------------------------------------
    # -- deskfun.c: New folder, and Delete ----------------------------------
    def ted_of(self, tree, obj):
        """The TEDINFO a G_FTEXT's ob_spec points at (deskinf.c)."""
        return self.a.mem[self.a.trees[tree][obj].ob_spec]

    def inf_sset(self, tree, obj, text):
        ted = self.ted_of(tree, obj)
        old = self.a.mem[ted.ptext]
        self.a.mem[ted.ptext] = Text(text[:ted.txtlen - 1], old.size)

    def inf_sget(self, tree, obj):
        return self.a.mem[self.ted_of(tree, obj).ptext].s

    def inf_numset(self, tree, obj, value):
        """The number at the right of the field, the donor's "%*lu"."""
        ted = self.ted_of(tree, obj)
        n = ted.txtlen - 1
        old = self.a.mem[ted.ptext]
        self.a.mem[ted.ptext] = Text(f"{value:{n}d}"[-n:], old.size)

    @staticmethod
    def inf_dttm_places(date, time):
        """The ten places a stamp fills: day, month, year, hour, minute
        (deskfun.c inf_dttm)."""
        return "%02d%02d%02d%02d%02d" % (
            date & 0x1F, (date >> 5) & 0x0F, ((date >> 9) + 80) % 100,
            (time >> 11) & 0x1F, (time >> 5) & 0x3F)

    @staticmethod
    def fmt_name(name):
        """"ONE.TXT" -> the eleven places "________.___" scatters
        (deskfun.c fmt_name); a name with no extension is not padded."""
        stem, dot, ext = name.partition(".")
        places = stem[:8]
        if dot:
            places = places.ljust(8) + ext[:3]
        return places

    @staticmethod
    def unfmt_name(places):
        """...and back (deskfun.c unfmt_name): a blank place is not part
        of the name, and an extension of nothing but blanks takes its
        dot with it."""
        name = places[:8].replace(" ", "")
        if len(places) > 8:
            ext = places[8:].replace(" ", "")
            if ext:
                name += "." + ext
        return name

    def inf_what(self, tree, ok):
        """Which of the two buttons after `ok` is selected, its state
        cleared: 1 for `ok` itself (the donor's inf_what)."""
        objs = self.a.trees[tree]
        for i in range(2):
            if objs[ok + i].ob_state & SELECTED:
                objs[ok + i].ob_state = NORMAL
                return 1 if i == 0 else 0
        return 0

    def fun_fld(self, tree, obj):
        """One field of a dialog already on the screen (draw_fld)."""
        io, _ = self.call(OBJC_OFFSET, (obj,), tree=tree)
        o = self.a.trees[tree][obj]
        self.call(OBJC_DRAW, (obj, MAX_DEPTH),
                  (io[1], io[2], o.ob_width, o.ob_height), tree=tree)

    def fun_mkdir(self, pw):
        """deskfun.c fun_mkdir: the name typed into ADMKDBOX, Dcreate,
        the window listed again."""
        tree = self.a_mkdir
        self.op_path = pw.path.spec.s
        self.inf_sset(tree, MKNAME, "")
        self.start_dialog(tree)
        self.call(FORM_DO, (ROOT,), tree=tree, steps=self.take_input("form_do"))
        self.end_dialog()
        if not self.inf_what(tree, MKOK):
            return
        made = self.unfmt_name(self.inf_sget(tree, MKNAME))
        if not made:
            return
        self.add_fname(made)
        self.busy(True)
        ok = self.op_gemdos(DCREATE) == E_OK
        self.busy(False)
        if not ok:
            self.fun_alert(1, STFOFAIL)
            return
        self.win_rebld(pw)
        return

    # the path an operation works on, mutated in place as the target
    # mutates op_path (deskfun.c)
    @staticmethod
    def path_tail(p):
        return p.rfind("\\") + 1

    def add_fname(self, name):
        self.op_path = self.op_path[:self.path_tail(self.op_path)] + name

    def set_all_files(self):
        self.op_path = self.op_path[:self.path_tail(self.op_path)] + "*.*"

    def add_path(self, name):
        k = self.path_tail(self.op_path)
        p = self.op_path[:k] + name
        if len(p) + 5 > LEN_ZPATH:
            self.op_path = self.op_path[:k] + "*.*"
            return False
        self.op_path = p + "\\*.*"
        return True

    def sub_path(self):
        p = self.op_path
        k = self.path_tail(p)
        if k > 3:
            self.op_path = p[:p.rfind("\\", 0, k - 1) + 1] + "*.*"

    # the same four, as functions of a path: a copy has two of them and
    # they go down and back up together (deskfun.c, dst_path)
    @classmethod
    def p_add_fname(cls, p, name):
        return p[:cls.path_tail(p)] + name

    @classmethod
    def p_set_all(cls, p):
        return p[:cls.path_tail(p)] + "*.*"

    @classmethod
    def p_add_path(cls, p, name):
        k = cls.path_tail(p)
        q = p[:k] + name
        if len(q) + 5 > LEN_ZPATH:
            return False, p[:k] + "*.*"
        return True, q + "\\*.*"

    @classmethod
    def p_sub_path(cls, p):
        k = cls.path_tail(p)
        if k > 3:
            return p[:p.rfind("\\", 0, k - 1) + 1] + "*.*"
        return p

    def op_gemdos(self, fn, *rest):
        """A GEMDOS call on op_path (the target passes its own buffer;
        the model keeps one string at STACK_STRING)."""
        self.a.mem[STACK_STRING] = Text(self.op_path)
        return self.gemdos_long(fn, STACK_STRING, *rest)

    def dst_gemdos(self, fn, *rest):
        """...and one on dst_path."""
        self.a.mem[STACK_STRING2] = Text(self.dst_path)
        return self.gemdos_long(fn, STACK_STRING2, *rest)

    # -- copying and moving (deskfun.c) ------------------------------------
    def make_dir(self):
        """The destination directory, without the "*.*"; one that is
        already there is not an error."""
        k = self.path_tail(self.dst_path)
        self.a.mem[STACK_STRING2] = Text(self.dst_path[:k - 1])
        ret = self.gemdos_long(DCREATE, STACK_STRING2)
        if ret in (E_OK, GD_EACCDN):
            return True
        self.fun_alert(1, STFOFAIL)
        return False

    def copy_file(self):
        """op_path to dst_path, COPY_BUF at a time, through the arena."""
        h_in = self.op_gemdos(FOPEN, 0)
        if h_in < 0:
            self.fun_alert(1, STCPYFIL)
            return False
        h_out = self.dst_gemdos(FCREATE, 0)
        if h_out < 0:
            self.gemdos(FCLOSE, (h_in,))
            self.fun_alert(1, STCPYFIL)
            return False
        ok = True
        while True:
            got = self.gemdos(FREAD, (h_in, COPY_BUF & 0xFFFF, COPY_BUF >> 16,
                                      self.copybuf & 0xFFFF, self.copybuf >> 16))
            if got <= 0:
                if got < 0:
                    ok = False
                break
            put = self.gemdos(FWRITE, (h_out, got & 0xFFFF, got >> 16,
                                       self.copybuf & 0xFFFF, self.copybuf >> 16))
            if put != got:
                self.fun_alert(1, STDISKFU)
                ok = False
                break
            if got < COPY_BUF:
                break
        self.gemdos(FCLOSE, (h_in,))
        self.gemdos(FCLOSE, (h_out,))
        if not ok:
            self.dst_gemdos(FDELETE)
            return False
        return True

    def copy_one(self, op):
        if not self.copy_file():
            return False
        if op == OP_MOVE and self.op_gemdos(FDELETE) != E_OK:
            self.fun_alert(1, STDELFIL)
            return False
        return True

    def walk(self, level, op):
        """deskfun.c walk: one directory, op_path ending in "*.*" (and
        dst_path with it for a copy), with a DTA of its own -- our
        GEMDOS keeps a search by the DTA that owns it, so the nested
        walk does not disturb this one."""
        if level >= MAX_DELLEVEL:
            self.fun_alert(1, STFO8DEE)
            return False
        dta = self.opdta + level * DTA_SIZE
        self.call(FSETDTA, (dta & 0xFFFF, dta >> 16))
        ret = self.op_gemdos(FSFIRST, FA_SUBDIR)
        while ret == E_OK:
            name, attr, _t, _d, _size = self.a.dos_dta_data
            if name[:1] != ".":
                if attr & FA_SUBDIR:
                    if not self.add_path(name):
                        self.fun_alert(1, STDEEPPA)
                        return False
                    if op in (OP_COPY, OP_MOVE):
                        ok, self.dst_path = self.p_add_path(self.dst_path, name)
                        if not ok:
                            self.fun_alert(1, STDEEPPA)
                            return False
                        if not self.make_dir():
                            return False
                    if not self.walk(level + 1, op):
                        return False
                    self.sub_path()
                    if op in (OP_COPY, OP_MOVE):
                        self.dst_path = self.p_sub_path(self.dst_path)
                    self.call(FSETDTA, (dta & 0xFFFF, dta >> 16))
                    self.add_fname(name)
                    if op == OP_COUNT:
                        self.ndirs += 1
                    elif op == OP_COPY:
                        self.ndirs -= 1
                        self.op_count(CDFOLDS, self.ndirs)
                    else:
                        if self.op_gemdos(DDELETE) != E_OK:
                            self.fun_alert(1, STDELDIR)
                            return False
                        self.ndirs -= 1
                        self.op_count(CDFOLDS, self.ndirs)
                    self.set_all_files()
                else:
                    self.add_fname(name)
                    if op == OP_COUNT:
                        self.nfiles += 1
                        self.opsize += _size
                    elif op == OP_DELETE:
                        if self.op_gemdos(FDELETE) != E_OK:
                            self.fun_alert(1, STDELFIL)
                            return False
                        self.nfiles -= 1
                        self.op_count(CDFILES, self.nfiles)
                    else:
                        self.dst_path = self.p_add_fname(self.dst_path, name)
                        if not self.copy_one(op):
                            return False
                        self.dst_path = self.p_set_all(self.dst_path)
                        self.nfiles -= 1
                        self.op_count(CDFILES, self.nfiles)
                    self.set_all_files()
            ret = self.gemdos(FSNEXT)
        return True

    def op_count(self, field, left):
        self.inf_numset(self.a_delete, field, left)
        self.fun_fld(self.a_delete, field)

    def rename(self):
        """Frename, whose trap frame is a reserved word and then the two
        paths (src/app/gemlib.c) -- the model keeps them at the two
        stack-string addresses op_gemdos and dst_gemdos use."""
        self.a.mem[STACK_STRING] = Text(self.op_path)
        self.a.mem[STACK_STRING2] = Text(self.dst_path)
        return self.gemdos(FRENAME,
                           (0, STACK_STRING & 0xFFFF, STACK_STRING >> 16,
                            STACK_STRING2 & 0xFFFF, STACK_STRING2 >> 16))

    def fun_info(self, pw):
        """deskfun.c fun_info: the item selected in the window, what the
        listing knows about it, and the two things this dialog changes --
        its name, which is the desktop's rename, and its read-only bit."""
        tree = self.a_finfo
        pn = pw.path
        pf = None
        for x in pn.fnodes[:pn.count]:
            if x.flags & F_SELECTED:
                pf = x
                break
        if pf is None:
            return
        folder = bool(pf.attr & FA_SUBDIR)
        self.dlg_title(tree, FITITLE, STFOINFO if folder else STFIINFO)

        objs = self.a.trees[tree]
        places = self.fmt_name(pf.name)
        self.inf_sset(tree, FINAME, places)
        was = self.unfmt_name(places)           # what the field started as
        self.inf_sset(tree, FIDATE, self.inf_dttm_places(pf.date, pf.time))
        # A folder's name is not the DOS's to change (deskfun.c: XIO 32
        # renames a file, and answers EFILNF for a directory on both
        # SpartaDOS 3.2 and SpartaDOS X), so the field is shown and not
        # editable rather than editable and always refused.
        if folder:
            objs[FINAME].ob_flags &= ~EDITABLE
        else:
            objs[FINAME].ob_flags |= EDITABLE
        if folder:                              # as big as what it holds
            self.op_path = pn.spec.s
            if not self.add_path(pf.name):
                self.fun_alert(1, STDEEPPA)
                return
            self.nfiles = self.ndirs = self.opsize = 0
            self.busy(True)
            ok = self.walk(0, OP_COUNT)
            self.busy(False)
            if not ok:
                return
            self.inf_numset(tree, FISIZE, self.opsize)
            self.inf_numset(tree, FIFILES, self.nfiles)
            self.inf_numset(tree, FIFOLDS, self.ndirs)
        else:
            self.inf_numset(tree, FISIZE, pf.size)
            self.inf_sset(tree, FIFILES, "")
            self.inf_sset(tree, FIFOLDS, "")
        objs[FIFILES].ob_state = NORMAL if folder else DISABLED
        objs[FIFOLDS].ob_state = NORMAL if folder else DISABLED

        changed = False
        while True:
            if folder:                          # not a folder's to change
                objs[FIRDWR].ob_state = DISABLED
                objs[FIRONLY].ob_state = DISABLED
            elif pf.attr & FA_RDONLY:
                objs[FIRDWR].ob_state = NORMAL
                objs[FIRONLY].ob_state = SELECTED
            else:
                objs[FIRDWR].ob_state = SELECTED
                objs[FIRONLY].ob_state = NORMAL
            objs[FIOK].ob_state = NORMAL
            self.start_dialog(tree)
            self.call(FORM_DO, (ROOT,), tree=tree,
                      steps=self.take_input("form_do"))
            self.end_dialog()
            if not self.inf_what(tree, FIOK):   # Cancel: nothing changes
                break

            self.busy(True)
            self.op_path = self.p_add_fname(pn.spec.s, pf.name)
            if not folder:
                attr = pf.attr
                if objs[FIRONLY].ob_state & SELECTED:
                    attr |= FA_RDONLY
                else:
                    attr &= ~FA_RDONLY
                if attr != pf.attr:
                    self.op_gemdos(FATTRIB, 1, attr)
                    pf.attr = attr
                    changed = True
            name = self.unfmt_name(self.inf_sget(tree, FINAME))
            if folder or not name or name == was:   # the name it started with
                self.busy(False)
                break
            self.dst_path = self.p_add_fname(pn.spec.s, name)
            ok = self.rename() == E_OK
            self.busy(False)
            if ok:
                changed = True
                break
            if self.fun_alert(1, STRENAME) == 2:    # Cancel: give it up
                break

        if changed:
            self.win_rebld(pw)

    def fun_del(self, pw):
        """deskfun.c fun_del: what is selected, counted (the donor's
        OP_COUNT), confirmed in ADDELDIA, then deleted, and the window
        listed again."""
        tree = self.a_delete
        pn = pw.path
        ok = any(pf.flags & F_SELECTED for pf in pn.fnodes[:pn.count])
        if not ok:
            return

        self.busy(True)                         # what it will do
        self.nfiles = self.ndirs = 0
        for pf in pn.fnodes[:pn.count]:
            if not ok:
                break
            if not pf.flags & F_SELECTED:
                continue
            self.op_path = pn.spec.s
            if pf.attr & FA_SUBDIR:
                if not self.add_path(pf.name):
                    self.fun_alert(1, STDEEPPA)
                    ok = False
                    break
                ok = self.walk(0, OP_COUNT)
                self.ndirs += 1
            else:
                self.nfiles += 1
        self.busy(False)
        if not ok:
            return

        self.inf_numset(tree, CDFILES, self.nfiles)      # ...and ask
        self.inf_numset(tree, CDFOLDS, self.ndirs)
        self.start_dialog(tree)
        self.call(FORM_DO, (ROOT,), tree=tree, steps=self.take_input("form_do"))
        if not self.inf_what(tree, CDOK):
            self.end_dialog()
            return

        self.busy(True)                         # ...and do it
        for pf in pn.fnodes[:pn.count]:
            if not ok:
                break
            if not pf.flags & F_SELECTED:
                continue
            self.op_path = pn.spec.s
            if pf.attr & FA_SUBDIR:
                self.add_path(pf.name)          # it fitted at the count
                ok = self.walk(0, OP_DELETE)
                if not ok:
                    break
                self.sub_path()
                self.add_fname(pf.name)
                if self.op_gemdos(DDELETE) != E_OK:
                    self.fun_alert(1, STDELDIR)
                    break
                self.ndirs -= 1
                self.inf_numset(tree, CDFOLDS, self.ndirs)
                self.fun_fld(tree, CDFOLDS)
                self.set_all_files()
            else:
                self.add_fname(pf.name)
                if self.op_gemdos(FDELETE) != E_OK:
                    self.fun_alert(1, STDELFIL)
                    break
                self.nfiles -= 1
                self.inf_numset(tree, CDFILES, self.nfiles)
                self.fun_fld(tree, CDFILES)
        self.busy(False)
        self.end_dialog()
        self.win_rebld(pw)
        return

    def dlg_title(self, tree, obj, stnum):
        """A title from the resource, centred on the box as the donor's
        align_title centres it: only ob_x moves (deskfun.c dlg_title)."""
        addr = self.rsrc_gaddr(R_STRING, stnum)
        objs = self.a.trees[tree]
        objs[obj].ob_spec = addr
        length = len(self.a.mem[addr].s) * self.wchar
        if length > objs[ROOT].ob_width:
            length = objs[ROOT].ob_width
        objs[obj].ob_x = (objs[ROOT].ob_width - length) // 2

    def op_title(self, op):
        """The operation dialog says which of the three it is, from a
        free string of the resource (deskfun.c op_title)."""
        stnum = (STCPYTTL if op == OP_COPY else
                 STMOVTTL if op == OP_MOVE else STDELTTL)
        self.dlg_title(self.a_delete, CDTITLE, stnum)

    def drop_path(self, dst_wh, dst_obj):
        """Where a drop landed, as a path ending in "*.*", or None."""
        if dst_wh == DESKWH:
            drive = self.obj_info(dst_obj).icon.char & 0xFF
            if not drive:
                return None                     # the trash: not a place
            return chr(drive) + ":\\*.*"
        pd = self.win_find(dst_wh)
        if pd is None:
            return None
        path = pd.path.spec.s
        if not dst_obj:
            return path
        pf = self.win_fnode(pd, dst_obj)
        if pf is None or not pf.attr & FA_SUBDIR:
            return None
        ok, path = self.p_add_path(path, pf.name)
        return path if ok else None

    def fun_file2any(self, pw, dst_wh, dst_obj, kstate):
        """deskfun.c fun_file2any: what is selected, dragged somewhere.
        The same three passes as a delete -- count, ask, do -- with a
        destination path kept in step with the source."""
        tree = self.a_delete
        pn = pw.path
        op = OP_MOVE if kstate & (MODE_LSHIFT | MODE_RSHIFT) else OP_COPY
        if dst_wh == DESKWH and not (self.obj_info(dst_obj).icon.char & 0xFF):
            self.fun_del(pw)                    # the trash
            return
        dest = self.drop_path(dst_wh, dst_obj)
        if dest is None:
            return
        if not any(pf.flags & F_SELECTED for pf in pn.fnodes[:pn.count]):
            self.fun_alert(1, STNOTHIN)
            return
        if dest == pn.spec.s:
            self.fun_alert(1, STSAMEPL)
            return

        self.busy(True)                         # what it will do
        self.nfiles = self.ndirs = 0
        ok = True
        for pf in pn.fnodes[:pn.count]:
            if not ok:
                break
            if not pf.flags & F_SELECTED:
                continue
            self.op_path = pn.spec.s
            if pf.attr & FA_SUBDIR:
                if not self.add_path(pf.name):
                    self.fun_alert(1, STDEEPPA)
                    ok = False
                    break
                ok = self.walk(0, OP_COUNT)
                self.ndirs += 1
            else:
                self.nfiles += 1
        self.busy(False)
        if not ok:
            return

        self.op_title(op)                       # ...and ask
        self.inf_numset(tree, CDFILES, self.nfiles)
        self.inf_numset(tree, CDFOLDS, self.ndirs)
        self.start_dialog(tree)
        self.call(FORM_DO, (ROOT,), tree=tree, steps=self.take_input("form_do"))
        if not self.inf_what(tree, CDOK):
            self.end_dialog()
            self.op_title(OP_DELETE)
            return

        self.busy(True)                         # ...and do it
        for pf in pn.fnodes[:pn.count]:
            if not ok:
                break
            if not pf.flags & F_SELECTED:
                continue
            self.op_path = pn.spec.s
            self.dst_path = dest
            if pf.attr & FA_SUBDIR:
                self.add_path(pf.name)          # both fitted at the count
                good, self.dst_path = self.p_add_path(self.dst_path, pf.name)
                if not good or not self.make_dir():
                    break
                ok = self.walk(0, op)
                if not ok:
                    break
                self.sub_path()
                self.dst_path = self.p_sub_path(self.dst_path)
                self.add_fname(pf.name)
                if op == OP_MOVE and self.op_gemdos(DDELETE) != E_OK:
                    self.fun_alert(1, STDELDIR)
                    break
                self.ndirs -= 1
                self.op_count(CDFOLDS, self.ndirs)
                self.set_all_files()
            else:
                self.add_fname(pf.name)
                self.dst_path = self.p_add_fname(self.dst_path, pf.name)
                if not self.copy_one(op):
                    break
                self.dst_path = self.p_set_all(self.dst_path)
                self.set_all_files()
                self.nfiles -= 1
                self.op_count(CDFILES, self.nfiles)
        self.busy(False)
        self.end_dialog()
        self.op_title(OP_DELETE)                # as the resource has it
        self.win_rebld(pw)
        pd = None if dst_wh == DESKWH else self.win_find(dst_wh)
        if pd is not None and pd is not pw:
            self.win_rebld(pd)

    def do_deskmenu(self, item):
        if item == ABOUITEM:
            tree = self.a_info
            self.start_dialog(tree)
            self.call(FORM_DO, (ROOT,), tree=tree, steps=self.take_input("form_do"))
            self.a.trees[tree][DEOK].ob_state = NORMAL
            self.end_dialog()
        return False

    def do_filemenu(self, item):
        pw = self.win_ontop()
        if item == OPENITEM:                    # the top window's selection,
            obj = self.sel_item(pw.root) if pw else 0     # else the desk's
            if obj:
                return self.do_open(pw.id, obj)
            obj = self.sel_item(DROOT)
            if obj:
                return self.do_open(DESKWH, obj)
        elif item == SHOWITEM:                  # what the selection is,
            if pw:                              # and its name to change
                self.fun_info(pw)
        elif item == NFOLITEM:                  # a folder in the top
            if pw:                              # window's directory
                self.fun_mkdir(pw)              # never done: only a
        elif item == DELTITEM:                  # program ends the loop
            if pw:
                self.fun_del(pw)
        elif item == CLOSITEM:
            if pw:
                self.win_close(pw, False)
        elif item == CLSWITEM:
            if pw:
                self.win_close(pw, True)
        elif item == QUITITEM:
            self.call(SHEL_WRITE, (SHW_SHUTDOWN, 0, 0))
            return True
        return False

    def desk_view(self, view):
        """The view the desktop is in: the checkmark moves with it and
        the item metrics are worked out again (desktop.c desk_view)."""
        if view != self.iview:
            self.call(MENU_ICHECK, (ICONITEM + self.iview, 0), tree=self.a_menu)
            self.call(MENU_ICHECK, (ICONITEM + view, 1), tree=self.a_menu)
            self.iview = view
        self.win_view()

    def desk_sort(self, sort):
        """The order the listings are in (desktop.c desk_sort)."""
        if sort != self.isort:
            self.call(MENU_ICHECK, (NAMEITEM + self.isort, 0), tree=self.a_menu)
            self.call(MENU_ICHECK, (NAMEITEM + sort, 1), tree=self.a_menu)
            self.isort = sort

    def desk_fit(self, fit):
        """Size to fit, or not (desktop.c desk_fit)."""
        self.ifit = 1 if fit else 0
        self.call(MENU_ICHECK, (FITITEM, self.ifit), tree=self.a_menu)

    def do_viewmenu(self, item):
        sorted_, viewed = False, False
        if item in (ICONITEM, TEXTITEM):
            if item - ICONITEM != self.iview:
                self.desk_view(item - ICONITEM)
                viewed = True
        elif item in (NAMEITEM, TYPEITEM, SIZEITEM, DATEITEM, NSRTITEM):
            if item - NAMEITEM != self.isort:
                self.desk_sort(item - NAMEITEM)
                sorted_ = True
        elif item == FITITEM:
            self.desk_fit(not self.ifit)
            viewed = True                       # the same rebuild
        if sorted_ or viewed:
            self.busy(True)
            if sorted_:
                self.win_srtall()
            self.win_bdall()
            self.win_shwall()
            self.busy(False)
        return False

    def do_optnmenu(self, item):
        """desktop.c do_optnmenu: the layout to the disk and back."""
        if item == SAVEITEM:
            if not self.inf_save():
                self.fun_alert(1, STSVINF)
        elif item == READITEM:
            if not self.inf_read():
                self.fun_alert(1, STRDINF)
        return False

    def hndl_menu(self, title, item):
        done = False
        if title == DESKMENU:
            done = self.do_deskmenu(item)
        elif title == FILEMENU:
            done = self.do_filemenu(item)
        elif title == VIEWMENU:
            done = self.do_viewmenu(item)
        elif title == OPTNMENU:
            done = self.do_optnmenu(item)
        self.call(MENU_TNORMAL, (title, 1), tree=self.a_menu)
        return done

    # -- events --------------------------------------------------------------
    def hndl_drag(self, pw, obj, wh, root):
        """desktop.c hndl_drag: the AES drags the outline, and where the
        POINTER came up says where it went.  True when it really was a
        drag; False when the button had already come up, which makes it
        a click and the caller's business."""
        io, _ = self.call(GRAF_MKSTATE)         # a sample, not a wait
        mstate, kstate = signed(io[3]), signed(io[4])
        if not (mstate & 1):                    # already let go: a click
            return False
        # what is dragged is the selection, and an item pressed on that
        # was not part of it becomes the whole of it
        if not (self.screen[obj].ob_state & SELECTED):
            self.act_select(wh, root, obj)
        io, _ = self.call(OBJC_OFFSET, (obj,), tree=self.g_screen_addr)
        bx, by = signed(io[0]), signed(io[1])
        d = self.wind_get_rect(0, WF_WXYWH)     # WF_WORKXYWH: the desk
        pob = self.screen[obj]
        self.call(GRAF_DRAGBOX,
                  (pob.ob_width, pob.ob_height, bx, by, d.x, d.y, d.w, d.h),
                  steps=self.take_input("dragbox"))
        io, _ = self.call(GRAF_MKSTATE)
        x, y, mstate, kstate = (signed(io[1]), signed(io[2]),
                                signed(io[3]), signed(io[4]))
        io, _ = self.call(WIND_FIND, (x, y))
        dwh = signed(io[0])
        if dwh == DESKWH:
            io, _ = self.call(OBJC_FIND, (DROOT, MAX_DEPTH), (x, y),
                              tree=self.g_screen_addr)
            dobj = signed(io[0])
            if dobj < WOBS_START:
                return True
        else:
            pd = self.win_find(dwh)
            if pd is None:
                return True
            io, _ = self.call(OBJC_FIND, (pd.root, MAX_DEPTH), (x, y),
                              tree=self.g_screen_addr)
            dobj = signed(io[0])
            if dobj < WOBS_START:
                dobj = 0
            if dwh == wh and (dobj == 0 or dobj == obj):
                return True
        self.fun_file2any(pw, dwh, dobj, kstate)
        return True

    def hndl_rubber(self, wh, root, mx, my):
        """desktop.c hndl_rubber: the AES draws the box while the button
        is down and says how big it got; everything it touches is the
        new selection.  False when the button had already come up."""
        io, _ = self.call(GRAF_MKSTATE)
        if not (signed(io[3]) & 1):
            return False
        io, _ = self.call(GRAF_RUBBOX, (mx, my, 1, 1),
                          steps=self.take_input("rubbox"))
        box = Rect(mx, my, signed(io[1]), signed(io[2]))
        self.act_allselect(wh, root, box)
        return True

    def hndl_button(self, clicks, mx, my, kstate):
        io, _ = self.call(WIND_FIND, (mx, my))
        wh = signed(io[0])
        pw = None
        if wh == DESKWH:
            root = DROOT
        else:
            pw = self.win_find(wh)
            if pw is None:
                return False
            root = pw.root
        io, _ = self.call(OBJC_FIND, (root, MAX_DEPTH), (mx, my),
                          tree=self.g_screen_addr)
        obj = signed(io[0])
        if obj < WOBS_START:
            obj = 0
        if obj and clicks == 2:
            self.act_select(wh, root, obj)      # just the one is opened
            return self.do_open(wh, obj)
        if obj and pw is not None and self.hndl_drag(pw, obj, wh, root):
            return False
        if not obj and pw is not None and self.hndl_rubber(wh, root, mx, my):
            return False
        self.act_bsclick(wh, root, obj, kstate)
        return False

    def hndl_msg(self):
        msg = self.rmsg
        if msg[0] == MN_SELECTED:
            return self.hndl_menu(msg[3], msg[4])
        if WM_REDRAW <= msg[0] <= WM_NEWTOP:
            self.hndl_wmsg(msg)
        return False

    def main(self):
        self.call(APPL_INIT)
        io, _ = self.call(GRAF_HANDLE)
        self.handle, self.wchar, self.hchar, self.wbox, self.hbox = io[0:5]
        self.desk = self.wind_get_rect(DESKWH, WF_WXYWH)
        self.busy(True)
        self.rsrc_load()
        self.a_menu = self.rsrc_gaddr(R_TREE, ADMENU)
        self.a_info = self.rsrc_gaddr(R_TREE, ADDINFO)
        self.a_mkdir = self.rsrc_gaddr(R_TREE, ADMKDBOX)
        self.a_delete = self.rsrc_gaddr(R_TREE, ADDELDIA)
        self.a_finfo = self.rsrc_gaddr(R_TREE, ADFINFO)
        self.a_iblist = self.rsrc_gaddr(R_ICONBLK, 0)
        self.fline = self.rsrc_gaddr(R_STRING, STFLINE)
        self.fmark = self.rsrc_gaddr(R_STRING, STFMARK)
        self.set_version()
        for item in NOT_YET:
            self.call(MENU_IENABLE, (item, 0), tree=self.a_menu)
        # deskcmd.c cmd_init: File -> DOS command is greyed on a DOS with
        # no command processor to hand a line to (Psystem, src/sys/dos.c;
        # the AES model answers by its `psystem`, which the gate sets from
        # the DOS it booted)
        if self.gemdos(PSYSTEM, (0,) * 6) < 0:
            self.call(MENU_IENABLE, (CMDITEM, 0), tree=self.a_menu)
        self.obj_init()
        self.desk_build()
        self.win_view()                             # V_ICON, until the INF
        if not self.win_start():
            self.busy(False)
            self.fun_alert(1, STNOMEM)
            self.call(RSRC_FREE)
            self.call(SHEL_WRITE, (SHW_SHUTDOWN, 0, 0))
            self.call(APPL_EXIT)
            return 1
        self.app_start()
        self.call(WIND_SET, (DESKWH, WF_NEWDESK,
                             self.g_screen_addr >> 16,
                             self.g_screen_addr & 0xFFFF, DROOT, 0))
        self.call(WIND_UPDATE, (BEG_UPDATE,))
        self.do_wredraw(DESKWH, self.desk)
        self.cnx_get()
        self.call(MENU_BAR, (1,), tree=self.a_menu)
        self.call(WIND_UPDATE, (END_UPDATE,))
        self.busy(False)

        done = False
        while not done:
            which, mx, my, button, kstate, kret, bret = self.wait(
                MU_BUTTON | MU_MESAG | MU_KEYBD, 2, 1, 1, 0, True)
            self.call(WIND_UPDATE, (BEG_UPDATE,))
            if which & MU_BUTTON:
                if self.hndl_button(bret, mx, my, kstate):
                    done = True
            while (which & MU_MESAG) and not done:
                if self.hndl_msg():
                    done = True
                which, mx, my, button, kstate, kret, bret = self.wait(
                    MU_MESAG | MU_TIMER, 2, 1, 1, 0, False)
            self.call(WIND_UPDATE, (END_UPDATE,))

        # the windows stay open: their places go to the shell buffer for
        # the next desktop, and the shell's reinitialisation takes the
        # screen back
        self.cnx_put()
        self.app_save()
        self.call(MENU_BAR, (0,), tree=self.a_menu)
        self.call(WIND_SET, (DESKWH, WF_NEWDESK, 0, 0, ROOT, 0))
        self.call(RSRC_FREE)
        self.call(APPL_EXIT)
        return 0

    # -- G, as the target lays it out ----------------------------------------
    def globes(self):
        """G packed as desk.h declares it: what a dump of the target's G
        should read at the same moment."""
        d = self.desk
        out = b"".join(p(x) for x in (
            self.a_menu, self.a_info, self.a_mkdir, self.a_delete,
            self.a_finfo, self.a_iblist))
        out += b"".join(w(x) for x in (
            self.handle, self.wchar, self.hchar, self.wbox, self.hbox,
            d.x, d.y, d.w, d.h, self.wicon, self.hicon,
            self.iview, self.isort, self.ifit, self.iwext, self.ihext,
            self.iwint, self.ihint))
        out += p(self.fline) + p(self.fmark)
        out += b"".join(w(x) for x in (
            self.icw, self.ich, self.icols,
            self.screenfree)) + b"".join(w(x) for x in self.rmsg)
        out += (w(self.wcnt) + dw(self.nfiles) + dw(self.ndirs)
                + dw(self.opsize)
                + dw(self.dta) + dw(self.opdta) + dw(self.cnxsave)
                + dw(self.shelbuf) + dw(self.copybuf))
        out += b"".join(pw.pack() for pw in self.wlist)
        out += b"".join(w(v) for pc in self.patcol for v in pc)
        assert len(out) == g_offset("g_screen"), len(out)
        out += b"".join(o.pack() for o in self.screen)
        for i, (ib, label) in enumerate(zip(self.info, self.labels)):
            if self.istext[i]:
                out += self.lines[i].pack()
            else:
                out += ((ib.pack() if ib else bytes(ICONBLK_SIZE))
                        + label.pack()
                        + bytes(SCREENINFO_SIZE - ICONBLK_SIZE - LABEL_LEN))
        assert len(out) == GLOBES_SIZE, len(out)
        return out

    # -- where things are, for the gate's plans ------------------------------
    def centre(self, tree, obj):
        a = self.a
        a.tree = a.trees[tree]
        r = a.ob_actxywh(obj)
        return (r.x + r.w // 2, r.y + r.h // 2)

    def gadget(self, wh, obj):
        """The middle of window wh's gadget obj (aesref's W_* index), as
        the AES lays the frame out now."""
        a = self.a
        a.tree = a.W_ACTIVE
        a.w_bldactive(wh)
        r = a.ob_actxywh(obj)
        return (r.x + r.w // 2, r.y + r.h // 2)

    def item(self, pw, name):
        """The middle of the icon window pw shows for entry `name`."""
        for pf in pw.path.fnodes[:pw.path.count]:
            if pf.name == name and pf.obid:
                return self.centre(self.g_screen_addr, pf.obid)
        raise KeyError(f"{name} is not shown in {pw.path.spec.s}")

    def pointer(self):
        return (self.v.ptr_x, self.v.ptr_y)


def describe(d):
    """One line per record, for a log."""
    for i, rec in enumerate(d.script):
        mark = "*" if i in d.plan else " "
        at = ""
        if len(rec) > 3:
            at = " @" + (hex(rec[3]) if isinstance(rec[3], int) else repr(rec[3]))
        print(f"{mark}{i:3d} {rec[0]} {rec[2]}{at}")
