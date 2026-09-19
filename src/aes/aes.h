/* aes.h -- GEM AES object model for gem4xe.
 *
 * Structures are the GEM ones, byte for byte, because a .RSC resource file is
 * a dump of exactly these and every GEM application builds trees at this
 * layout.  Where a field is a 32-bit pointer in GEM it stays 32 bits here for
 * the same reason the MFDB's fd_addr did -- see the note in vdi/vdi.h.
 */
#ifndef GEM4XE_AES_H
#define GEM4XE_AES_H

#include "portab.h"
#include <stdint.h>
#include "../vdi/vdi.h"

typedef struct {
    WORD g_x, g_y, g_w, g_h;
} GRECT;

/* The object.  24 bytes: three link words, three attribute words, a 32-bit
 * ob_spec, then the rectangle. */
typedef struct {
    WORD  ob_next;          /* -1 = none */
    WORD  ob_head;          /* first child, -1 = none */
    WORD  ob_tail;          /* last child,  -1 = none */
    UWORD ob_type;
    UWORD ob_flags;
    UWORD ob_state;
    /* ob_spec.  For the box types this packs three things, and the order is
     * the 68000's byte order inside the LONG, which is what every .RSC on
     * disk contains:
     *     bits 31-24  character   (G_BOXCHAR only)
     *     bits 23-16  thickness   (signed byte)
     *     bits 15-0   colour word
     * (EmuTOS aes/gemobjop.c ob_sst: `th = *(((char *)pspec)+1)` and
     * `return *(char *)pspec`, with gr_crack taking the low word.)
     * For the text and button types it is an address instead. */
    uint32_t ob_spec;
    WORD  ob_x, ob_y;       /* relative to the PARENT */
    WORD  ob_width, ob_height;
} OBJECT;

/* ob_type */
#define G_BOX       20
#define G_TEXT      21
#define G_BOXTEXT   22
#define G_IMAGE     23
#define G_USERDEF   24
#define G_IBOX      25
#define G_BUTTON    26
#define G_BOXCHAR   27
#define G_STRING    28
#define G_FTEXT     29
#define G_FBOXTEXT  30
#define G_ICON      31
#define G_TITLE     32
#define G_CICON     33      /* a colour icon: its CICONBLK starts with an
                             * ICONBLK, and that is what is drawn (below) */

/* ob_flags */
#define NONE        0x0000
#define SELECTABLE  0x0001
#define DEFAULT     0x0002
#define EXIT        0x0004
#define EDITABLE    0x0008
#define RBUTTON     0x0010
#define LASTOB      0x0020
#define TOUCHEXIT   0x0040
#define HIDETREE    0x0080
#define INDIRECT    0x0100
#define SUBMENU     0x0800      /* this item carries a menu of its own */

/* ob_state */
#define NORMAL      0x0000
#define SELECTED    0x0001
#define CROSSED     0x0002
#define CHECKED     0x0004
#define DISABLED    0x0008
#define OUTLINED    0x0010
#define SHADOWED    0x0020
#define WHITEBAK    0x0040      /* an icon over a white ground: leave it */

#define NIL         (-1)
#define ROOT        0
#define MAX_DEPTH   8       /* deepest objc_draw / objc_find descend */
#define MAX_COORDINATE 10000 /* the far edge of a drag's constraint */
#define MAX_LEN     81      /* longest editable string, NUL included */

#ifndef TRUE
#define TRUE        1
#define FALSE       0
#endif

/* evnt_multi event flags */
#define MU_KEYBD    0x0001
#define MU_BUTTON   0x0002
#define MU_M1       0x0004
#define MU_M2       0x0008
#define MU_MESAG    0x0010
#define MU_TIMER    0x0020

/* ---- the window manager's vocabulary ----------------------------------- */

/* Messages, as they arrive in evnt_mesag's 8-word buffer: [0] the type,
 * [1] the sender's id, [2] the length beyond 16 bytes (0), [3..7] the
 * arguments -- a handle and a rectangle for WM_REDRAW, a handle for the
 * rest, a handle and an arrow code for WM_ARROWED. */
#define MN_SELECTED 10
#define WM_REDRAW   20
#define WM_TOPPED   21
#define WM_CLOSED   22
#define WM_FULLED   23
#define WM_ARROWED  24
#define WM_HSLID    25
#define WM_VSLID    26
#define WM_SIZED    27
#define WM_MOVED    28
#define WM_NEWTOP   29
#define WM_UNTOPPED 30
#define WM_ONTOP    31
#define AC_OPEN     40
#define AC_CLOSE    41

/* graf_mouse's forms (aesdefs.h).  0..7 are the AES's own, in
 * tools/gemdata.py's order; the rest are commands, not shapes. */
#define ARROW        0
#define TEXT_CRSR    1
#define HOURGLASS    2
#define POINT_HAND   3
#define FLAT_HAND    4
#define THIN_CROSS   5
#define THICK_CROSS  6
#define OUTLN_CROSS  7
#define USER_DEF     255
#define M_OFF        256
#define M_ON         257
#define M_SAVE       258
#define M_RESTORE    259
#define M_PREVIOUS   260

/* WM_ARROWED's arrow codes */
#define WA_UPPAGE   0
#define WA_DNPAGE   1
#define WA_UPLINE   2
#define WA_DNLINE   3
#define WA_LFPAGE   4
#define WA_RTPAGE   5
#define WA_LFLINE   6
#define WA_RTLINE   7

/* Window kinds: the gadgets a window has (wind_create's kind) */
#define NAME        0x0001
#define CLOSER      0x0002
#define FULLER      0x0004
#define MOVER       0x0008
#define INFO        0x0010
#define SIZER       0x0020
#define UPARROW     0x0040
#define DNARROW     0x0080
#define VSLIDE      0x0100
#define LFARROW     0x0200
#define RTARROW     0x0400
#define HSLIDE      0x0800
#define HOTCLOSE    0x1000
#define TGADGETS    (NAME | CLOSER | FULLER | MOVER)
#define VGADGETS    (UPARROW | DNARROW | VSLIDE)
#define HGADGETS    (LFARROW | RTARROW | HSLIDE)

/* wind_get / wind_set fields */
#define WF_KIND     1
#define WF_NAME     2
#define WF_INFO     3
#define WF_WXYWH    4
#define WF_CXYWH    5
#define WF_PXYWH    6
#define WF_FXYWH    7
#define WF_HSLIDE   8
#define WF_VSLIDE   9
#define WF_TOP      10
#define WF_FIRSTXYWH 11
#define WF_NEXTXYWH 12
#define WF_RESVD    13
#define WF_NEWDESK  14
#define WF_HSLSIZ   15
#define WF_VSLSIZ   16
#define WF_SCREEN   17
#define WF_COLOR    18
#define WF_DCOLOR   19
#define WF_OWNER    20
#define WF_BOTTOM   25      /* wind_get only: wind_set(WF_BOTTOM) is not served */

/* wind_calc */
#define WC_BORDER   0
#define WC_WORK     1

/* wind_update */
#define END_UPDATE  0
#define BEG_UPDATE  1
#define END_MCTRL   2
#define BEG_MCTRL   3

/* The window frame's objects: W_ACTIVE[], built by w_bldactive for
 * whichever window is being drawn. */
#define W_BOX       0
#define W_TITLE     1
#define W_CLOSER    2
#define W_NAME      3
#define W_FULLER    4
#define W_INFO      5
#define W_DATA      6
#define W_WORK      7
#define W_SIZER     8
#define W_VBAR      9
#define W_UPARROW   10
#define W_DNARROW   11
#define W_VSLIDE    12
#define W_VELEV     13
#define W_HBAR      14
#define W_LFARROW   15
#define W_RTARROW   16
#define W_HSLIDE    17
#define W_HELEV     18
#define NUM_ELEM    19

/* Sizes, as the ROM AES has them: eight windows counting the desktop, an
 * 80-rectangle pool for the visible-rectangle lists, a 256-byte message
 * pipe (16 messages of 8 words). */
#define NUM_WIN     8
#define NUM_ORECT   80
#define NUM_MSGS    16
#define DESKWH      0       /* the desktop's window handle */

/* w_flags */
#define VF_INUSE    0x0001
#define VF_BROKEN   0x0002  /* its rectangle list is not one rectangle */
#define VF_ISOPEN   0x0004

/* w_getsize / w_setsize: which of a window's rectangles */
#define WS_FULL     0
#define WS_CURR     1
#define WS_PREV     2
#define WS_WORK     3
#define WS_TRUE     4       /* CURR plus the drop shadow */

/* vro_cpyfm's logic operations (the ones the AES uses) */
#define ALL_WHITE   0
#define S_AND_D     1
#define S_ONLY      3
#define S_XOR_D     6
#define S_OR_D      7
#define D_INVERT    10
#define ALL_BLACK   15

/* form_dial types */
#define FMD_START   0
#define FMD_GROW    1
#define FMD_SHRINK  2
#define FMD_FINISH  3

/* form_do's field-to-field directions */
#define FORWARD     0
#define BACKWARD    1
#define DEFLT       2

/* Object colours (the colour word's nibbles) */
#define WHITE       0

/* objc_sysvar: what a program is told about 3D object rendering.  The
 * Compendium's names (6.121).  gem4xe draws no 3D objects, so the
 * inquiry answers zero throughout and setting is refused -- see
 * ob_sysvar in objc.c for why zero is the TRUE answer and not a stub. */
#define SV_INQUIRE  0
#define SV_SET      1
#define LK3DIND     1           /* indicator: does its text move, its colour change */
#define LK3DACT     2           /* activator: the same two */
#define INDBUTCOL   3           /* an indicator's default colour */
#define ACTBUTCOL   4           /* an activator's */
#define BACKGRCOL   5           /* a background object's */
#define AD3DVALUE   6           /* extra pixels each side for the 3D effect */
#define BLACK       1
#define LWHITE      8
#define LBLACK      9

/* Inside patterns (the colour word's 3-bit field): 0 hollow, 1..6 the first
 * six VDI fill patterns, 7 solid.  IP_4PATT is the 50% stipple the AES greys
 * a DISABLED object with. */
#define IP_HOLLOW   0
#define IP_4PATT    4
#define IP_SOLID    7

/* te_font */
#define IBM         3
#define SMALL       5

/* te_just */
#define TE_LEFT     0
#define TE_RIGHT    1
#define TE_CNTR     2

/* objc_edit kinds */
#define EDSTART     0
#define EDINIT      1
#define EDCHAR      2
#define EDEND       3

/* Keys as the AES sees them: scancode in the high byte, ASCII in the low.
 * The editable-field keys, and the ones form_do reads. */
#define ESCAPE      0x011B
#define BACKSPACE   0x0E08
#define TAB         0x0F09
#define RETURN      0x1C0D
#define DELETE      0x537F
#define UNDO        0x6100
#define ENTER       0x720D
#define ARROW_UP    0x4800
#define ARROW_DOWN  0x5000
#define ARROW_LEFT  0x4B00
#define ARROW_RIGHT 0x4D00

/* TEDINFO, for the G_TEXT family.  Three 32-bit addresses -- text, template,
 * validation -- then the attributes.  28 bytes, as in a .RSC. */
typedef struct {
    uint32_t te_ptext;
    uint32_t te_ptmplt;
    uint32_t te_pvalid;
    WORD te_font, te_fontid;
    WORD te_just;           /* TE_LEFT / TE_RIGHT / TE_CNTR */
    WORD te_color;
    WORD te_fontsize;
    WORD te_thickness;
    WORD te_txtlen, te_tmplen;
} TEDINFO;

/* BITBLK, for G_IMAGE: a 1-plane form drawn transparently in bi_color. */
typedef struct {
    uint32_t bi_pdata;
    WORD bi_wb;             /* width in BYTES */
    WORD bi_hl;             /* height in lines */
    WORD bi_x, bi_y;        /* source origin within the form */
    WORD bi_color;
} BITBLK;

/* ICONBLK, for G_ICON: a mask, an image and a text, 34 bytes as in a
 * .RSC.  The mask and image fields are 32 bits and hold FAR addresses
 * once rsrc_load has moved the bits up (src/aes/rsrc.c, rs_imfar) -- and
 * for a G_CICON the same record, since a CICONBLK begins with an ICONBLK
 * and that is what objc_draw draws of it (rs_cicons). */
typedef struct {
    uint32_t ib_pmask;
    uint32_t ib_pdata;
    uint32_t ib_ptext;
    WORD ib_char;
    WORD ib_xchar, ib_ychar;
    WORD ib_xicon, ib_yicon, ib_wicon, ib_hicon;
    WORD ib_xtext, ib_ytext, ib_wtext, ib_htext;
} ICONBLK;

/* The .RSC header (EmuTOS include/rsdefs.h): 36 bytes, offsets from the
 * start of the file.  On disk every word is big-endian; rsrc_load swaps
 * the header and the tables, never the strings or the image data. */
typedef struct {
    UWORD rsh_vrsn;
    UWORD rsh_object, rsh_tedinfo, rsh_iconblk, rsh_bitblk;
    UWORD rsh_frstr, rsh_string, rsh_imdata, rsh_frimg, rsh_trindex;
    WORD  rsh_nobs, rsh_ntree, rsh_nted, rsh_nib, rsh_nbb;
    WORD  rsh_nstring, rsh_nimages;
    UWORD rsh_rssize;
} RSHDR;
/* rsh_vrsn's bit for the colour-icon extension.  It IS carried: rs_load
 * parses the extension array, the colour-icon table and every CICONBLK
 * (rsrc.c).  What is not done with it is DRAWING -- a G_CICON draws its
 * mono form (objc.c) -- and a resource that has to load FAR is refused
 * if it is new-format.  appl_getinfo says exactly that: AES_SYSTEM's
 * fourth word is 1 for the format and its third is 0 for the icons.
 * (This comment used to read "not carried", from before rs_cicons.) */
#define NEW_FORMAT_RSC 0x0004

/* rsrc_gaddr / rsrc_saddr types */
#define R_TREE      0
#define R_OBJECT    1
#define R_TEDINFO   2
#define R_ICONBLK   3
#define R_BITBLK    4
#define R_STRING    5
#define R_IMAGEDATA 6
#define R_OBSPEC    7
#define R_TEPTEXT   8
#define R_TEPTMPLT  9
#define R_TEPVALID  10
#define R_IBPMASK   11
#define R_IBPDATA   12
#define R_IBPTEXT   13
#define R_BIPDATA   14
#define R_FRSTR     15
#define R_FRIMG     16

/* A mouse rectangle event: five words, laid out as evnt_multi's int_in
 * carries them, so the dispatcher can point straight at the parameter
 * block.  m_out: report when the pointer LEAVES m_gr rather than enters. */
typedef struct {
    WORD  m_out;
    GRECT m_gr;
} MOBLK;

/* A window's visible-rectangle list: what an application may draw into
 * without touching the windows above it.  The pool is gl_olist[]. */
typedef struct orect {
    struct orect FAR *o_link;
    GRECT               o_gr;
} ORECT;

/* One window (gemlib.h's WINDOW), less the per-window colours.  w_pname/w_pinfo are the application's strings, by
 * address, exactly as wind_set(WF_NAME) received them -- ALL 24 BITS of
 * it, which is why they are uint32_t and not pointers.  The ST's AES
 * keeps a pointer and re-reads the string at every redraw, so the shim
 * cannot bounce a far title into a scratch that lasts the call the way
 * it does form_alert's text; a --data-model=large program's title is far
 * and would be cut to 16 bits.  Keeping the whole address and bringing a
 * far one down at DRAW time (w_ptext, src/aes/wind.c) preserves the
 * contract in both directions: the application may still edit its title
 * in place and see it at the next redraw. */
typedef struct {
    UWORD       w_flags;    /* VF_* */
    UWORD       w_kind;     /* the gadgets */
    /* Who created it: what wind_get(WF_OWNER) answers.  An accessory can
     * own a window here -- it has a process of its own (src/aes/proc.h)
     * -- so this is the process that called wind_create and not a
     * constant, even though the application is usually the only one
     * asking. */
    WORD        w_owner;
    uint32_t    w_pname;
    uint32_t    w_pinfo;
    GRECT       w_full;
    GRECT       w_work;
    GRECT       w_prev;
    WORD        w_hslide, w_vslide;     /* 0..1000 */
    WORD        w_hslsiz, w_vslsiz;     /* 0..1000, -1 = the default */
    /* Far, because the rectangle pool is (src/aes/wind.c says why). */
    ORECT FAR *w_rlist;   /* the visible rectangles */
    ORECT FAR *w_rnext;   /* the WF_NEXTXYWH cursor */
} WINDOW;

/* ---- AES-wide screen geometry (gemgraf.c's gl_* globals) ---------------
 * Read from the workstation by gsx_start(), never assumed. */
extern WORD gl_wchar, gl_hchar;     /* system font cell */
extern WORD gl_wbox, gl_hbox;       /* a "box" cell: menu bar height etc. */
extern WORD gl_width, gl_height;    /* the screen */
extern WORD gl_nplanes;             /* ... and its depth */
extern WORD gl_handle;              /* the VDI handle the AES draws with */
extern GRECT gl_clip;               /* the AES's own copy of the VDI clip */
extern GRECT gl_rscreen, gl_rfull, gl_rcenter, gl_rmenu;

/* ---- input state (geminput.c / gemevlib.c globals) ---------------------
 * The pointer as the AES last saw it; pr_* is the previous transition when
 * two arrived before anyone asked (mtrans > 1). */
extern WORD button, xrat, yrat, kstate, mclick, mtrans;
extern WORD pr_button, pr_xrat, pr_yrat, pr_mclick;
extern WORD gl_ticktime;            /* ms per timer tick, from the VDI */
extern WORD gl_dclick;              /* double-click window, in ticks */
extern WORD gl_dcindex;             /* evnt_dclick rate 0..4 */

/* ---- rectangles ------------------------------------------------------- */
void r_set(GRECT *pt, WORD x, WORD y, WORD w, WORD h);
WORD inside(WORD x, WORD y, const GRECT *pt);
WORD rc_intersect(const GRECT *p1, GRECT *p2);
void rc_union(const GRECT *p1, GRECT *p2);
WORD rc_equal(const GRECT *p1, const GRECT *p2);
void rc_constrain(const GRECT *pc, GRECT *pt);
#define rc_copy(src, dst)   (*(dst) = *(src))
WORD mul_div(WORD m1, WORD m2, WORD d1);
WORD mul_div_round(WORD m1, WORD m2, WORD d1);

/* ---- the gsx_ / gr_ waist: everything the AES draws goes through here ----
 * graf.c */
void gsx_start(void);
void gsx_moff(void);
void gsx_mon(void);
void gsx_mreset(void);      /* ...and visible whatever the depth */
WORD gsx_mforce(void);           /* the pointer on whatever the count */
void gsx_munforce(WORD old);     /* ... and the count back */
void ratinit(void);              /* the pointer on, count zero: sh_main */
void gsx_mfset(const WORD *pmform);   /* the pointer's shape: 37 words */
void gsx_mfform(WORD which, WORD *out);  /* one of the AES's own, from far */
WORD gsx_mfget(WORD which, WORD *out);   /* MF_CURR/MF_PREV/MF_SAVED, far */
void gsx_mfsave(void);                   /* graf_mouse(M_SAVE) */
#define MF_CURR   0
#define MF_PREV   1
#define MF_SAVED  2
void gsx_attr(WORD text, WORD mode, WORD color);
void gsx_fcolor(WORD color);
void gsx_sclip(const GRECT *pt);
void gsx_gclip(GRECT *pt);
WORD gsx_chkclip(const GRECT *pt);
void gsx_cline(WORD x1, WORD y1, WORD x2, WORD y2);
void gsx_tblt(WORD font, WORD x, WORD y, WORD nc);
void gsx_blt(uint32_t saddr, WORD sx, WORD sy, WORD dx, WORD dy, WORD w, WORD h,
             WORD rule, WORD fg, WORD bg);
void bb_fill(WORD mode, WORD fis, WORD patt, WORD x, WORD y, WORD w, WORD h);
void bb_screen(WORD sx, WORD sy, WORD dx, WORD dy, WORD w, WORD h);
void bb_save(const GRECT *pr);
void bb_restore(const GRECT *pr);
WORD expand_string(WORD *dst, const char FAR *s);
void gr_crack(UWORD color, WORD *pbc, WORD *ptc, WORD *pip, WORD *pic, WORD *pmd);
void gr_inside(GRECT *pt, WORD th);
void gr_rect(WORD icolor, WORD ipattern, const GRECT *pt);
WORD gr_just(WORD just, WORD font, const char FAR *ptext, WORD w, WORD h, GRECT *pt);
void gr_gtext(WORD just, WORD font, const char FAR *ptext, const GRECT *pt);
void gr_box(WORD x, WORD y, WORD w, WORD h, WORD th);
void gsx_xbox(const GRECT *pt);
void gsx_xcbox(const GRECT *pt);
WORD gsx_vex(WORD op, VDI_VEC fn);
WORD gsx_mouse(WORD *px, WORD *py);
WORD gsx_kstate(void);
WORD gsx_getkey(WORD *pkey);

/* ---- the graphics library: grlib.c (gemgrlib.c) ------------------------ */
WORD gr_stilldn(WORD out, WORD x, WORD y, WORD w, WORD h);
/* graf_mbox/graf_movebox (72): a ghost box walked from one place to
 * another.  gr_growbox and gr_shrinkbox are this with the two ends
 * worked out for them, which is why it was a static until the opcode
 * was served. */
void gr_movebox(WORD w, WORD h, WORD srcx, WORD srcy, WORD dstx, WORD dsty);
void gr_growbox(const GRECT *po, const GRECT *pt);
void gr_shrinkbox(const GRECT *po, const GRECT *pt);
WORD gr_watchbox(OBJECT FAR *tree, WORD obj, WORD instate, WORD outstate);
void gr_mouse(WORD mode, const WORD *pmform);
void gr_mkstate(WORD *pmx, WORD *pmy, WORD *pmstat, WORD *pkstat);
void gr_rubwind(WORD xo, WORD yo, WORD wmin, WORD hmin, const GRECT *poff,
                WORD *pw, WORD *ph);
void gr_rubbox(WORD xo, WORD yo, WORD wmin, WORD hmin, WORD *pw, WORD *ph);
void gr_dragbox(WORD w, WORD h, WORD sx, WORD sy, const GRECT *pc,
                WORD *pdx, WORD *pdy);
WORD gr_slidebox(OBJECT FAR *tree, WORD parent, WORD obj, WORD isvert);

/* ---- events: event.c (gemevlib.c + geminput.c) ------------------------- */
void ev_init(void);
WORD ev_dclick(WORD rate, WORD setit);
WORD ev_multi(WORD flags, const MOBLK *pmo1, const MOBLK *pmo2,
              uint32_t tmcount, uint32_t buparm, WORD *mebuff, WORD *prets);
WORD ev_block(WORD code, uint32_t lvalue);
WORD ev_keybd(void);
WORD ev_keyq(WORD *pkey);       /* one poll; a key if one is there, else 0 */
WORD ev_button(WORD clicks, UWORD mask, UWORD state, WORD *rets);
WORD ev_mouse(const MOBLK *pmo, WORD *rets);
WORD ev_timer(uint32_t count);
uint32_t combine_cms(WORD clicks, UWORD mask, UWORD state);
void ev_fq(void);
void ev_poll(void);             /* one poll, and the control manager's turn */
extern uint32_t gl_ticks;       /* timer ticks since ev_init */

/* Mouse ownership (geminput.c): the application owns the control
 * rectangle -- the top window's work area, or the whole screen inside
 * form_do -- and the window manager owns the rest.  A press decides who
 * gets the button, and the loser sees nothing until it is up again. */
void set_ctrl(const GRECT *pt);
void get_ctrl(GRECT *pt);
void ct_chgown(const GRECT *pr);
void ct_poll(void);

/* ---- the control manager: ctrl.c (gemctrl.c) --------------------------- */
extern WORD gl_ctmown;          /* the menu has taken the mouse */
void hctl_button(WORD mx, WORD my);
void hctl_rect(void);            /* the pointer into the menu bar */
void ct_mouse(WORD grabit);      /* the menu taking the mouse, and back */
void ct_arrow_repeat(void);      /* a held arrow: one WM_ARROWED per ask */
void ct_arrow_stop(void);

/* ---- the menu library: menu.c (gemmnlib.c) ----------------------------- */
extern OBJECT FAR *gl_mntree;       /* the menu bar showing, or 0 */
extern MOBLK   gl_ctwait;       /* the rectangle whose entry runs the menu */
void mn_init(void);
void mn_bar(OBJECT FAR *tree, WORD showit);
/* mn_do also says WHICH TREE and which box the item came from, because
 * with sub-menus the item may be in neither the menu bar's tree nor its
 * drop-down: those are MN_SELECTED's words 5, 6 and 7 (ctrl.c). */
WORD mn_do(WORD *ptitle, WORD *pitem, uint32_t *ptree, WORD *pmenu);
WORD do_chg(OBJECT FAR *tree, WORD iitem, UWORD chgvalue, WORD dochg,
            WORD dodraw, WORD chkdisabled);
void mn_text(OBJECT FAR *tree, WORD item, const char *text);

/* menu_popup: the box `imenu` of `tree` put up with item `istart` under
 * the pointer at (x, y), tracked, and taken away again.  The item chosen
 * or NIL, and *pkeystate always -- both donors write the keystate
 * whatever happens.  The Compendium's MENU block does NOT come in here:
 * src/sys/abi.c unpacks the caller's into these scalars.  That is where
 * the caller's memory belongs, and it is also the version that works --
 * an AESMENU struct with a far-pointer field delivered the tree with a
 * bank of $3E and no reduced case reproduced it, so the reason is not
 * known and is not being guessed at in a comment (src/sys/abi.c). */
WORD mn_popup(OBJECT FAR *tree, WORD imenu, WORD istart, WORD x, WORD y,
              WORD *pkeystate);

/* menu_attach's flag, and menu_istart's.  The ROM writes bare integers
 * (MN_SUBMN.C); the names are EmuTOS's. */
#define ME_INQUIRE  0
#define ME_ATTACH   1
#define ME_REMOVE   2
#define MIS_INQUIRE 0
#define MIS_SET     1
/* menu_attach.  The four words are OUT on an inquiry and IN on an
 * attach, where mn_item is clamped into the box and written back.  The
 * tree is an ADDRESS for the reason menu.c gives. */
WORD mn_attach(WORD flag, OBJECT FAR *tree, WORD item,
               uint32_t *ptree, WORD *pmenu, WORD *pitem, WORD *pscroll);
/* menu_istart: the start item, or 0 for an error -- the ROM's ambiguity,
 * harmless because object 0 is a root and never a menu item. */
WORD mn_istart(WORD flag, uint32_t tree, WORD imenu, WORD item);
/* The objects every menu tree has in these positions -- the shape the
 * RCS builds and the AES trusts.  THEDESK is the Desk TITLE, and it is
 * the word AC_OPEN carries in msg[3]; the control manager and the menu
 * library both need it, so it is here once rather than twice.  A tree
 * whose first menu title is not object 3 breaks accessory dispatch in
 * silence -- the donor carries the same constant with the same warning. */
#define THESCREEN   0
#define THEBAR      1
#define THEACTIVE   2
#define THEDESK     3

void mn_start(void);             /* once per AES start: the registry cleared */
WORD mn_register(WORD pid, const char *pstr);
struct PROC *mn_owner(WORD id);  /* who registered that slot, or 0 */
void mn_cleanup(void);           /* AC_CLOSE to every registered accessory */
extern WORD gl_dafirst;          /* where the first accessory name lands */
extern WORD gl_accreg;           /* names registered in the Desk menu */
extern const char *gl_acctitle[]; /* by slot; the ACCESSORY's own memory */

/* The message pipe (gemqueue.c).  Every process has one -- src/aes/proc.h
 * -- and mq_put names which; mq_get and mq_count are the running one's.
 * A WM_REDRAW for a handle that already has one waiting is unioned into
 * it, and a WM_ARROWED replaces any WM_ARROWED waiting.  Full pipe: the
 * message is dropped, as GEM would rather block the sender and the
 * sender here is usually the AES itself. */
struct PROC;
void mq_put(struct PROC *to, const WORD *msg);
WORD mq_get(WORD *msg);         /* the running process's; FALSE if empty */
WORD mq_count(void);
WORD *gl_appqueue(WORD *max);   /* the application's, in the banked window */
WORD ct_idle(void);             /* TRUE when a turn may change hands */
void ev_mesag(WORD *mebuff);    /* evnt_mesag: wait for one */
void ap_sendmsg(struct PROC *to, WORD type, WORD w3, WORD w4,
                WORD w5, WORD w6, WORD w7);

/* ---- forms: form.c (gemfmlib.c) --------------------------------------- */
void fm_own(WORD beg_ownit);
WORD fm_do(OBJECT FAR *tree, WORD start);
WORD fm_dial(WORD type, const GRECT *pi, const GRECT *pt);
WORD fm_keybd(OBJECT FAR *tree, WORD obj, WORD *pchar, WORD *pnew_obj);
WORD fm_button(OBJECT FAR *tree, WORD new_obj, WORD clks, WORD *pnew_obj);

WORD form_do(OBJECT FAR *tree, WORD start);
WORD form_dial(WORD type, const GRECT *pi, const GRECT *pt);
WORD fm_alert(WORD defbut, const char *palstr);   /* form_alert */
WORD fm_error(WORD n);                            /* form_error */
WORD form_keybd(OBJECT FAR *tree, WORD obj, WORD *pchar, WORD *pnew_obj);
WORD form_button(OBJECT FAR *tree, WORD new_obj, WORD clks, WORD *pnew_obj);

/* ---- the object library: objc.c ---------------------------------------- */
typedef void (*OBJ_ROUTINE)(OBJECT FAR *tree, WORD obj, WORD sx, WORD sy);
void everyobj(OBJECT FAR *tree, WORD this, WORD last, OBJ_ROUTINE routine,
              WORD startx, WORD starty, WORD maxdep);
void ob_draw(OBJECT FAR *tree, WORD obj, WORD depth);
void ob_add(OBJECT FAR *tree, WORD parent, WORD child);
WORD ob_delete(OBJECT FAR *tree, WORD obj);
WORD ob_order(OBJECT FAR *tree, WORD mov_obj, WORD new_pos);
void ob_offset(OBJECT FAR *tree, WORD obj, WORD *px, WORD *py);
void ob_actxywh(OBJECT FAR *tree, WORD obj, GRECT *pt);
void ob_relxywh(OBJECT FAR *tree, WORD obj, GRECT *pt);
WORD ob_get_par(OBJECT FAR *tree, WORD obj);
void ob_format(WORD just, char *raw, const char *tmpl, char *fmt);
void ob_center(OBJECT FAR *tree, GRECT *pt);
void ob_change(OBJECT FAR *tree, WORD obj, UWORD new_state, WORD redraw);
WORD ob_find(OBJECT FAR *tree, WORD currobj, WORD depth, WORD mx, WORD my);
WORD ob_edit(OBJECT FAR *tree, WORD obj, WORD in_char, WORD *idx, WORD kind);
WORD ob_sysvar(WORD mode, WORD which, WORD in1, WORD in2,
               WORD *out1, WORD *out2);

void objc_draw(OBJECT FAR *tree, WORD start, WORD depth, const GRECT *clip);
WORD objc_find(OBJECT FAR *tree, WORD start, WORD depth, WORD mx, WORD my);
void objc_offset(OBJECT FAR *tree, WORD obj, WORD *px, WORD *py);
void objc_change(OBJECT FAR *tree, WORD obj, const GRECT *clip, UWORD newstate,
                 WORD redraw);
WORD objc_edit(OBJECT FAR *tree, WORD obj, WORD kchar, WORD *idx, WORD kind);

/* ---- the window manager: wind.c (gemwmlib.c + gemwrect.c) ------------- */
extern OBJECT FAR *gl_wtree;            /* the window tree: W_TREE[NUM_WIN] */
extern OBJECT FAR *gl_awind;            /* the frame being drawn: W_ACTIVE[] */
extern WORD    gl_wtop;             /* the top window, NIL for none */
extern WINDOW  gl_win[NUM_WIN];
extern OBJECT FAR *gl_newdesk;          /* the desktop tree, if one is installed */
extern WORD    gl_newroot;
extern GRECT   gl_rzero;

void wm_init(void);
void w_drawdesk(const GRECT *pc);
void w_getsize(WORD which, WORD w_handle, GRECT *pt);
void w_setsize(WORD which, WORD w_handle, const GRECT *pt);
void w_bldactive(WORD w_handle);
void w_cpwalk(WORD wh, WORD obj, WORD depth, WORD usetrue);
void w_update(WORD bottom, GRECT *pt, WORD top, WORD moved);
WORD wm_create(WORD kind, const GRECT *pt);
WORD wm_open(WORD w_handle, const GRECT *pt);
WORD wm_close(WORD w_handle);
WORD wm_delete(WORD w_handle);
WORD wm_get(WORD w_handle, WORD w_field, WORD *poutwds, const WORD *pinwds);
WORD wm_set(WORD w_handle, WORD w_field, WORD *pinwds);
WORD wm_find(WORD x, WORD y);
void wm_update(WORD beg_update);
/* wind_new (109): the windows, the locks and the pointer's hide count
 * put back as a program found them.  See the body. */
void wm_new(void);
extern WORD ml_ocnt;        /* form.c: fm_own's nesting depth */
extern WORD wm_ucount;      /* wind.c: wind_update's */
void wm_calc(WORD wtype, UWORD kind, WORD x, WORD y, WORD w, WORD h,
             WORD *px, WORD *py, WORD *pw, WORD *ph);

/* ---- the resource library: rsrc.c (gemrslib.c) ------------------------
 * One resource loaded at a time, into the bank-$00 pool (src/sys/app.h). */
/* The RUNNING process's loaded resource, or 0 (src/aes/rsrc.c): a macro
 * over its process record, not a global, so that an accessory holding one
 * does not stop an application loading one. */
uint32_t rs_loaded(void);           /* the resource's base: bank $00 or far; 0 if none */
void rs_header(RSHDR *h);           /* its header, copied out */
/* Where the loaded resource's icon bitmaps went, and how many bytes:
 * base 0 when they stayed in the pool.  See src/aes/rsrc.c. */
void rs_imaddr(uint32_t *base, uint16_t *len);
/* ...and where a new-format resource's colour-icon extension went: base 0
 * when the file had none.  The mono headers are near (rs_cicons). */
void rs_ciaddr(uint32_t *base, uint16_t *len);
WORD rs_load(const char *name, WORD wants_far);   /* wants_far: the caller takes far addresses */
WORD rs_free(void);
WORD rs_gaddr(UWORD rtype, UWORD rindex, uint32_t *paddr);
WORD rs_saddr(UWORD rtype, UWORD rindex, uint32_t addr);
void rs_obfix(OBJECT FAR *tree, WORD obj);
void rs_fixit(uint32_t base);       /* the loader's fix-up, on any image, at any base */

/* ---- what the system says: LANG.RSC (src/aes/lang.c) ------------------ */
/* The file a translator replaces, looked for where the program was
 * started.  lang_str answers a NEAR string good until the next call --
 * one buffer, which is enough because alerts are modal. */
#define LANG_FILE "LANG.RSC"
void lang_init(void);                   /* the strings: needs far memory only */
void lang_font(void);                   /* SYSTEM.FNT: needs the VDI device  */
WORD lang_loaded(void);                 /* 1 when LANG.RSC is what is in use */
const char *lang_str(WORD n);                    /* LS_*, build/lang_rsc.h */

/* ---- appl.c: what this AES has, asked one subject at a time ----------- */
/* appl_getinfo (130).  TRUE for a subject it knows, FALSE for one it does
 * not -- the donor's convention, which the Compendium states backwards
 * (appl.c has the four readings).  The four words are always written,
 * zeroed first, so a caller reading them after a FALSE gets zeros rather
 * than whatever was on the stack. */
#define SYSTEM_FONT     0       /* ...and its ap_gout3 for the two fonts */
#define OUTLINE_FONT    1
#define AESLANG_ENGLISH 0       /* ...and its ap_gout1 for the language */
WORD ap_getinfo(WORD which, WORD *out1, WORD *out2, WORD *out3, WORD *out4);

/* appl_read: one message out of the CALLER'S OWN pipe into `buf`, which
 * may be far, waiting the way evnt_mesag waits.  `length` must be
 * AP_MSGBYTES exactly -- this pipe is messages and not bytes, and
 * appl.c has the reason and what it cost to keep it that way. */
#define AP_MSGWORDS     8
#define AP_MSGBYTES     (AP_MSGWORDS * 2)
WORD ap_read(WORD ap_id, WORD length, uint32_t buf);

/* fsel.c -- the file selector (docs/phase11.md) */
extern WORD gl_drvbits;             /* which drive buttons are live, A = bit 0 */
void fs_start(void);                /* at AES start-up: the far name slots */
WORD fs_input(char *pipath, char *pisel, WORD *pbutton, const char *pilabel);

/* ---- the scrap manager: scrap.c (gemsclib.c) --------------------------
 * The clipboard's DIRECTORY, not the clipboard: the scrap itself is files
 * called SCRAP.* in it, so what the AES arbitrates is a place and not a
 * format.  One far buffer, taken once by sc_init() before any application
 * is loaded, for the shell library's reason below. */
void sc_init(void);
WORD sc_read(char *pscrap);
WORD sc_write(const char *pscrap);
WORD sc_clear(void);            /* PC-GEM's: no Atari AES has opcode 82 */

/* ---- the shell library: shel.c (gemshlib.c) ----------------------------
 * Buffers in far memory, taken once by sh_init() before any application
 * is loaded; the environment a constant in bank $00. */
extern WORD sh_doexec;              /* shel_write's request: SHW_*, -1 none */
extern WORD sh_isgem;
void sh_init(void);
void sh_read(char *pcmd, char *ptail);
/* Pexec's child (src/sys/gemdos.c) reads its own name and tail with
 * shel_read: sh_push keeps the running program's in SH_SAVELEN bytes of
 * far memory at `save` and puts the child's in their place -- the tail
 * the ST's way, a length byte and the bytes, from wherever the program
 * keeps it -- and sh_pop puts the program's back. */
#define SH_SAVELEN  256
void sh_push(uint32_t save, const char *cmd, uint32_t tail);
void sh_pop(uint32_t save);
WORD sh_write(WORD doex, WORD isgem, WORD isover, const char *pcmd,
              const char *ptail);
void sh_get(uint32_t pbuffer, WORD len);     /* far addresses */
void sh_put(uint32_t pdata, WORD len);
void sh_envrn(const char **ppath, const char *psrch);
WORD sh_find(char *pspec);
void sh_cioname(const char *gem, char *cio);
/* The shell loop: the desktop (DESKTOP.G4A on the default drive), the
 * programs it asks for, until a shutdown.  Returns how many programs it
 * ran, or a negative APP_* status when the desktop itself would not
 * load; the counters say what happened last. */
WORD sh_main(void);
extern WORD sh_runs, sh_lastret, sh_lastrc;

#endif /* GEM4XE_AES_H */
