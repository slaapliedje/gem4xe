/* graf.c -- the AES's drawing waist (EmuTOS aes/gemgraf.c + gemgsxif.c).
 *
 * Everything the AES puts on the screen goes through the handful of routines
 * here, and they in turn go through the VDI parameter block exactly as an
 * application would.  Keeping that waist narrow is what makes the object
 * library device-independent: objc.c never knows what a pixel is.
 *
 * The gl_* geometry -- character cell, box cell, screen size -- is READ FROM
 * THE WORKSTATION at gsx_start(), never assumed.  The same code has to lay
 * out a dialog on a 640x240 VBXE overlay and, later, on ANTIC mode F, and the
 * only thing that knows the difference is the driver behind v_opnwk.
 */
#include "portab.h"
#include <string.h>
#include "aes.h"
#include "../vdi/vdi.h"
#include "sys/farmem.h"
#include "gemdata.h"

WORD gl_wchar, gl_hchar;
WORD gl_wbox, gl_hbox;
WORD gl_width, gl_height;
GRECT gl_clip;
GRECT gl_rscreen, gl_rfull, gl_rcenter, gl_rmenu;

/* The font's "top" -- the distance from the top of a cell to the baseline.
 * v_gtext positions text by its baseline; the AES thinks in cells. */
static WORD gl_hptschar, gl_wptschar;
WORD gl_nplanes;                /* what vq_extnd reports, for appl_init's global */
WORD gl_handle;                 /* the workstation the AES draws on */

/* What the VDI currently holds, so the AES does not re-send attributes it
 * has already set.  -1 = unknown, forcing the first call through. */
static WORD gl_mode, gl_tcolor, gl_lcolor;
static WORD gl_fis, gl_patt;
static WORD gl_moff;            /* mouse-off nesting depth */

/* ---- calling the VDI --------------------------------------------------- */

static void gsx_call(WORD op, WORD npts, WORD nint)
{
    contrl[0] = op;
    contrl[1] = npts;
    contrl[3] = nint;
    contrl[6] = gl_handle;
    vdi();
}

static void gsx_1code(WORD op, WORD v)
{
    intin[0] = v;
    gsx_call(op, 0, 1);
}

/* ---- rectangles (EmuTOS util/rectfunc.c) ------------------------------- */

void r_set(GRECT *pt, WORD x, WORD y, WORD w, WORD h)
{
    pt->g_x = x;  pt->g_y = y;  pt->g_w = w;  pt->g_h = h;
}

WORD inside(WORD x, WORD y, const GRECT *pt)
{
    return (x >= pt->g_x && y >= pt->g_y &&
            x < pt->g_x + pt->g_w && y < pt->g_y + pt->g_h);
}

/* Intersect p2 with p1, in place; FALSE (and an empty p2) if disjoint. */
WORD rc_intersect(const GRECT *p1, GRECT *p2)
{
    WORD tx, ty, tw, th;

    tw = (WORD)(p1->g_x + p1->g_w);
    if (p2->g_x + p2->g_w < tw)
        tw = (WORD)(p2->g_x + p2->g_w);
    th = (WORD)(p1->g_y + p1->g_h);
    if (p2->g_y + p2->g_h < th)
        th = (WORD)(p2->g_y + p2->g_h);
    tx = (p1->g_x > p2->g_x) ? p1->g_x : p2->g_x;
    ty = (p1->g_y > p2->g_y) ? p1->g_y : p2->g_y;
    p2->g_x = tx;
    p2->g_y = ty;
    p2->g_w = (WORD)(tw - tx);
    p2->g_h = (WORD)(th - ty);
    return (tw > tx && th > ty);
}

/* p2 becomes the bounding box of p1 and p2. */
void rc_union(const GRECT *p1, GRECT *p2)
{
    WORD tx, ty, tw, th;

    tw = (WORD)(p1->g_x + p1->g_w);
    if (p2->g_x + p2->g_w > tw)
        tw = (WORD)(p2->g_x + p2->g_w);
    th = (WORD)(p1->g_y + p1->g_h);
    if (p2->g_y + p2->g_h > th)
        th = (WORD)(p2->g_y + p2->g_h);
    tx = (p1->g_x < p2->g_x) ? p1->g_x : p2->g_x;
    ty = (p1->g_y < p2->g_y) ? p1->g_y : p2->g_y;
    p2->g_x = tx;
    p2->g_y = ty;
    p2->g_w = (WORD)(tw - tx);
    p2->g_h = (WORD)(th - ty);
}

WORD rc_equal(const GRECT *p1, const GRECT *p2)
{
    return (p1->g_x == p2->g_x && p1->g_y == p2->g_y &&
            p1->g_w == p2->g_w && p1->g_h == p2->g_h);
}

/* Move pt so that it lies inside pc (a pt larger than pc keeps its
 * top/left edge inside). */
void rc_constrain(const GRECT *pc, GRECT *pt)
{
    if (pt->g_x < pc->g_x)
        pt->g_x = pc->g_x;
    if (pt->g_y < pc->g_y)
        pt->g_y = pc->g_y;
    if (pt->g_x + pt->g_w > pc->g_x + pc->g_w)
        pt->g_x = (WORD)(pc->g_x + pc->g_w - pt->g_w);
    if (pt->g_y + pt->g_h > pc->g_y + pc->g_h)
        pt->g_y = (WORD)(pc->g_y + pc->g_h - pt->g_h);
}

/* (m1 * m2) / d1 through a 32-bit intermediate, truncating toward zero
 * as the 68000's divs does. */
WORD mul_div(WORD m1, WORD m2, WORD d1)
{
    int32_t q = ((int32_t)m1 * m2) / d1;
    return (WORD)q;
}

/* The same, rounded to nearest: EmuTOS's miscasm.S computes
 * (m1*m2*2)/d1 truncating, then halves it with the rounding bit, floor
 * for a negative quotient. */
WORD mul_div_round(WORD m1, WORD m2, WORD d1)
{
    int32_t q = ((int32_t)m1 * m2 * 2) / d1;
    WORD r = (WORD)q;

    if (r < 0)
        return (WORD)((r - 1) >> 1);
    return (WORD)((r + 1) >> 1);
}

/* ---- workstation bring-up --------------------------------------------- */

/* Read the workstation's geometry and derive the AES layout constants.
 * Assumes vdi_init() has already opened the physical workstation. */
static uint32_t gl_mfmem;               /* the pointer's three forms, far:
                                         * taken in gsx_start, kept below */

void gsx_start(void)
{
    WORD hpixel, wpixel;

    gl_mode = gl_tcolor = gl_lcolor = -1;
    gl_fis = gl_patt = -1;
    gl_moff = 0;
    gl_handle = VDI_PHYS_HANDLE;    /* the workstation vdi_init opened: the
                                     * AES draws on the device itself, and
                                     * an application on a virtual one */
    if (!gl_mfmem)                  /* the pointer's three forms: once, and
                                     * now, below any program's memory --
                                     * app_free returns the heap to where
                                     * the program found it */
        gl_mfmem = far_alloc(3UL * GEM_MFORM_WORDS * 2);

    /* vq_extnd(0) answers as v_opnwk did: extent and pixel size. */
    gsx_1code(VQ_EXTND, 0);
    gl_width  = (WORD)(intout[0] + 1);
    gl_height = (WORD)(intout[1] + 1);
    wpixel = intout[3];
    hpixel = intout[4];
    gsx_1code(VQ_EXTND, 1);
    gl_nplanes = intout[4];

    /* The system font's cell.  vst_height reports (char w, char h, cell w,
     * cell h), where "char h" is the font's top: the baseline offset. */
    ptsin[0] = 0;
    ptsin[1] = 0;
    gsx_call(VST_HEIGHT, 1, 0);
    gl_wptschar = ptsout[0];
    gl_hptschar = ptsout[1];
    gl_wchar = ptsout[2];
    gl_hchar = ptsout[3];

    /* A "box" is a character cell with three pixels of breathing room,
     * squared up to the pixel aspect so a menu bar looks the same on any
     * device. */
    gl_hbox = (WORD)(gl_hchar + 3);
    gl_wbox = (WORD)((gl_hbox * hpixel) / wpixel);
    if (gl_wbox < gl_wchar + 4)
        gl_wbox = (WORD)(gl_wchar + 4);

    /* Lines: the AES draws its dotted "user" style through vsl_udsty and
     * never changes width, so set these once. */
    gsx_1code(VSL_TYPE, 7);
    ptsin[0] = 1;
    ptsin[1] = 0;
    gsx_call(VSL_WIDTH, 1, 0);
    gsx_1code(VSL_UDSTY, (WORD)0xFFFF);

    r_set(&gl_rscreen, 0, 0, gl_width, gl_height);
    r_set(&gl_rfull, 0, gl_hbox, gl_width, (WORD)(gl_height - gl_hbox));
    r_set(&gl_rcenter, (WORD)((gl_width - gl_wbox) / 2),
          (WORD)((gl_height - 2 * gl_hbox) / 2), gl_wbox, gl_hbox);
    r_set(&gl_rmenu, 0, 0, gl_width, gl_hbox);

    /* The AES clips to the whole screen and a little more, so that an
     * object drawn at the edge is not cut off by a half-open interval. */
    r_set(&gl_clip, 0, 0, (WORD)(gl_width + 1), (WORD)(gl_height + 1));
    gsx_sclip(&gl_clip);
}

/* ---- the mouse -------------------------------------------------------- */

void gsx_moff(void)
{
    if (!gl_moff)
        gsx_call(V_HIDE_C, 0, 0);
    gl_moff++;
}

void gsx_mon(void)
{
    gl_moff--;
    if (!gl_moff)
        gsx_1code(V_SHOW_C, 1);      /* 1: undo one hide, not "force" */
}

/* The pointer visible again however deep the hides are: wind_new's "the
 * mouse pointer hide count is reset" (Compendium p.457), which is there
 * because a program that exits between a gsx_moff and its gsx_mon
 * leaves the screen with no pointer and no way to get one back.
 *
 * One forced show rather than a gsx_mon loop: intin[0] == 0 makes the
 * VDI drop its own count to zero and draw (src/vdi/vdi.c), so the two
 * counts end up agreeing.  A loop would issue one V_SHOW_C per hide and
 * the AES's count could still walk away from the VDI's. */
void gsx_mreset(void)
{
    if (gl_moff) {
        gl_moff = 0;
        gsx_1code(V_SHOW_C, 0);
    }
}

/* The pointer's shape (gsx_mfset).  A form is 37 words -- hot spot,
 * planes, the mask's colour and the data's, then sixteen words of each
 * -- and vsc_form takes them in intin, so the AES's own eight forms can
 * live in far memory and be copied down one at a time (tools/gemdata.py,
 * build/gemdata.c).
 *
 * The three forms the AES must remember -- the one set, the one before
 * it (graf_mouse(M_PREVIOUS)) and the one an application saved
 * (M_SAVE) -- are 222 bytes, which bank $00 has not got: they live in
 * far memory too, taken once, and travel through a local on the way in
 * and out.  Far memory is where everything the AES keeps and does not
 * read every frame belongs (docs/phase12.md).
 *
 * The change is made under a hide and a show, as the donor makes it:
 * vsc_form only defines the form, and a pointer that is on the screen
 * and not moving keeps its old picture until something redraws it.
 * Without the pair the desktop's hourglass stayed over a folder it had
 * finished opening until the mouse moved (phase 14, milestone 5). */
#define MF_CURR   0
#define MF_PREV   1
#define MF_SAVED  2

static WORD     gl_mform_set;           /* has one been set at all? */

static uint32_t mf_slot(WORD which)
{
    if (!gl_mfmem)                  /* gsx_start could not get them */
        return 0;
    return gl_mfmem + (uint32_t)which * (GEM_MFORM_WORDS * 2);
}

void gsx_mfset(const WORD *pmform)
{
    WORD i;
    uint32_t curr = mf_slot(MF_CURR), prev = mf_slot(MF_PREV);

    gsx_moff();
    if (curr && prev && gl_mform_set) {
        WORD was[GEM_MFORM_WORDS];
        far_get((uint8_t *)was, curr, sizeof was);
        far_put(prev, (const uint8_t *)was, sizeof was);
    }
    for (i = 0; i < GEM_MFORM_WORDS; i++)
        intin[i] = pmform[i];
    if (curr)
        far_put(curr, (const uint8_t *)pmform, GEM_MFORM_WORDS * 2);
    gl_mform_set = TRUE;
    gsx_call(VSC_FORM, 0, GEM_MFORM_WORDS);
    gsx_mon();
}

/* One of the AES's own eight, out of far memory. */
void gsx_mfform(WORD which, WORD *out)
{
    if (which < 0 || which >= GEM_MFORMS)
        which = 0;
    far_get((uint8_t *)out, (uint32_t)(const WORD FAR *)gem_mforms[which],
            GEM_MFORM_WORDS * 2);
}

/* A remembered form: MF_CURR, MF_PREV or MF_SAVED.  FALSE when there is
 * none -- nothing has been set, or far memory was not there. */
WORD gsx_mfget(WORD which, WORD *out)
{
    uint32_t slot = mf_slot(which);

    if (!slot || !gl_mform_set)
        return FALSE;
    far_get((uint8_t *)out, slot, GEM_MFORM_WORDS * 2);
    return TRUE;
}

/* graf_mouse(M_SAVE): the form now, kept for M_RESTORE. */
void gsx_mfsave(void)
{
    WORD form[GEM_MFORM_WORDS];
    uint32_t saved = mf_slot(MF_SAVED);

    if (saved && gsx_mfget(MF_CURR, form))
        far_put(saved, (const uint8_t *)form, sizeof form);
}

/* The pointer on whatever the hide count (the donor's ratinit, for the
 * menu's ct_mouse): returns the count for gsx_munforce to put back. */
WORD gsx_mforce(void)
{
    WORD old = gl_moff;

    if (old) {
        gsx_1code(V_SHOW_C, 0);      /* 0: show, whatever the count */
        gl_moff = 0;
    }
    return old;
}

/* Back to the hide count gsx_mforce found: one hide to take the pointer
 * off, then the count as it was. */
void gsx_munforce(WORD old)
{
    if (old) {
        gsx_moff();
        gl_moff = old;
    }
}

/* The pointer on, whatever the count -- the donor's ratinit, which its
 * sh_main calls before each program so that one that returned with the
 * pointer hidden does not hide it for the next.  Unconditional, unlike
 * gsx_mforce: the VDI opens with the pointer hidden and the AES's count
 * at zero, and this is what first shows it. */
void ratinit(void)
{
    gsx_1code(V_SHOW_C, 0);
    gl_moff = 0;
}

/* ---- attributes ------------------------------------------------------- */

/* Set the writing mode and either the text or the line colour, sending
 * only what has changed.  Leaves intin[0] as it found it, because callers
 * stage a character there before calling. */
void gsx_attr(WORD text, WORD mode, WORD color)
{
    WORD tmp = intin[0];

    if (mode != gl_mode) {
        gsx_1code(VSWR_MODE, mode);
        gl_mode = mode;
    }
    if (text) {
        if (color != gl_tcolor) {
            gsx_1code(VST_COLOR, color);
            gl_tcolor = color;
        }
    } else {
        if (color != gl_lcolor) {
            gsx_1code(VSL_COLOR, color);
            gl_lcolor = color;
        }
    }
    intin[0] = tmp;
}

/* The fill colour is not cached: it changes with every object and the VDI
 * call is cheap. */
void gsx_fcolor(WORD color)
{
    gsx_1code(VSF_COLOR, color);
}

/* ---- clipping --------------------------------------------------------- */

void gsx_sclip(const GRECT *pt)
{
    gl_clip = *pt;
    if (gl_clip.g_w && gl_clip.g_h) {
        intin[0] = 1;
        ptsin[0] = gl_clip.g_x;
        ptsin[1] = gl_clip.g_y;
        ptsin[2] = (WORD)(gl_clip.g_x + gl_clip.g_w - 1);
        ptsin[3] = (WORD)(gl_clip.g_y + gl_clip.g_h - 1);
        gsx_call(VS_CLIP, 2, 1);
    } else {
        intin[0] = 0;
        gsx_call(VS_CLIP, 0, 1);
    }
}

void gsx_gclip(GRECT *pt)
{
    *pt = gl_clip;
}

/* TRUE if any of pt could be visible through the current clip. */
WORD gsx_chkclip(const GRECT *pt)
{
    if (gl_clip.g_w && gl_clip.g_h) {
        if (pt->g_y + pt->g_h < gl_clip.g_y)
            return 0;
        if (pt->g_x + pt->g_w < gl_clip.g_x)
            return 0;
        if (gl_clip.g_y + gl_clip.g_h <= pt->g_y)
            return 0;
        if (gl_clip.g_x + gl_clip.g_w <= pt->g_x)
            return 0;
    }
    return 1;
}

/* ---- lines and boxes -------------------------------------------------- */

/* The outline of pt as a closed polyline: the current line attributes. */
static void gsx_box(const GRECT *pt)
{
    WORD x2 = (WORD)(pt->g_x + pt->g_w - 1);
    WORD y2 = (WORD)(pt->g_y + pt->g_h - 1);

    ptsin[0] = pt->g_x;  ptsin[1] = pt->g_y;
    ptsin[2] = x2;       ptsin[3] = pt->g_y;
    ptsin[4] = x2;       ptsin[5] = y2;
    ptsin[6] = pt->g_x;  ptsin[7] = y2;
    ptsin[8] = pt->g_x;  ptsin[9] = pt->g_y;
    gsx_call(V_PLINE, 5, 0);
}

void gsx_cline(WORD x1, WORD y1, WORD x2, WORD y2)
{
    gsx_moff();
    ptsin[0] = x1;  ptsin[1] = y1;
    ptsin[2] = x2;  ptsin[3] = y2;
    gsx_call(V_PLINE, 2, 0);
    gsx_mon();
}

/* ---- XOR boxes that survive a dithered surface (gemgraf.c) --------------
 * A solid XOR line over a 50% stipple is invisible every other pixel, so
 * the rubber boxes are drawn dotted, with the dot phase chosen from the
 * parity of the line's own position: two such lines drawn on top of each
 * other cancel exactly, whatever is underneath. */

static void gsx_xline(WORD n, const WORD *pts)
{
    static const WORD hztltbl[2] = { 0x5555, (WORD)0xAAAA };
    static const WORD verttbl[4] = { 0x5555, (WORD)0xAAAA, (WORD)0xAAAA, 0x5555 };
    WORD i, x1, y1, x2, y2, st, yl;

    for (i = 1; i < n; i++) {
        x1 = pts[0];  y1 = pts[1];
        x2 = pts[2];  y2 = pts[3];
        if (x1 == x2) {
            st = verttbl[(x1 & 1) | ((y1 & 1) << 1)];
        } else {
            yl = (x1 < x2) ? y1 : y2;   /* the leftmost end's row */
            st = hztltbl[yl & 1];
        }
        gsx_1code(VSL_UDSTY, st);
        ptsin[0] = x1;  ptsin[1] = y1;
        ptsin[2] = x2;  ptsin[3] = y2;
        gsx_call(V_PLINE, 2, 0);
        pts += 2;
    }
    gsx_1code(VSL_UDSTY, (WORD)0xFFFF);
}

/* The five points of pt's outline, x..x+w-1 by y..y+h-1, closed. */
static void gsx_bxpts(const GRECT *pt, WORD *p)
{
    WORD x2 = (WORD)(pt->g_x + pt->g_w - 1);
    WORD y2 = (WORD)(pt->g_y + pt->g_h - 1);

    p[0] = pt->g_x;  p[1] = pt->g_y;
    p[2] = x2;       p[3] = pt->g_y;
    p[4] = x2;       p[5] = y2;
    p[6] = pt->g_x;  p[7] = y2;
    p[8] = pt->g_x;  p[9] = pt->g_y;
}

void gsx_xbox(const GRECT *pt)
{
    WORD p[10];

    gsx_bxpts(pt, p);
    gsx_xline(5, p);
}

/* Just the corners of pt, each arm two box cells long. */
void gsx_xcbox(const GRECT *pt)
{
    WORD p[6];
    WORD wa = (WORD)(2 * gl_wbox), ha = (WORD)(2 * gl_hbox);
    WORD x1 = pt->g_x, y1 = pt->g_y;
    WORD x2 = (WORD)(pt->g_x + pt->g_w - 1);
    WORD y2 = (WORD)(pt->g_y + pt->g_h - 1);

    p[0] = x1;               p[1] = (WORD)(y1 + ha);
    p[2] = x1;               p[3] = y1;
    p[4] = (WORD)(x1 + wa);  p[5] = y1;
    gsx_xline(3, p);

    p[0] = (WORD)(x2 + 1 - wa);  p[1] = y1;
    p[2] = x2;                   p[3] = y1;
    p[4] = x2;                   p[5] = (WORD)(y1 + ha);
    gsx_xline(3, p);

    p[0] = x2;                   p[1] = (WORD)(y2 + 1 - ha);
    p[2] = x2;                   p[3] = y2;
    p[4] = (WORD)(x2 + 1 - wa);  p[5] = y2;
    gsx_xline(3, p);

    p[0] = (WORD)(x1 + wa);  p[1] = y2;
    p[2] = x1;               p[3] = y2;
    p[4] = x1;               p[5] = (WORD)(y2 + 1 - ha);
    gsx_xline(3, p);
}

/* ---- input through the VDI -------------------------------------------- */

/* Exchange an input vector.  Function pointers are 24 bits under the large
 * code model, so the address goes in as two words, contrl[7] low and
 * contrl[8] high, and the old one comes back the same way in [9..10].
 * Returns intout[0], which only vex_timv fills (the tick length). */
WORD gsx_vex(WORD op, VDI_VEC fn)
{
    uint32_t a = (uint32_t)fn;

    contrl[7] = (WORD)a;
    contrl[8] = (WORD)(a >> 16);
    intout[0] = 0;
    gsx_call(op, 0, 0);
    return intout[0];
}

/* Where the pointer is and which buttons are down (vq_mouse). */
WORD gsx_mouse(WORD *px, WORD *py)
{
    gsx_call(VQ_MOUSE, 0, 0);
    *px = ptsout[0];
    *py = ptsout[1];
    return intout[0];
}

/* The shift-key state word (vq_key_s). */
WORD gsx_kstate(void)
{
    gsx_call(VQ_KEY_S, 0, 0);
    return intout[0];
}

/* One key from the VDI's queue, or FALSE if none is waiting (v_string in
 * sample mode returns at most one key per call on this driver). */
WORD gsx_getkey(WORD *pkey)
{
    intin[0] = 1;                   /* max length: one key */
    intin[1] = 0;                   /* no echo */
    ptsin[0] = 0;
    ptsin[1] = 0;
    gsx_call(V_STRING, 1, 2);
    if (contrl[4] == 0)
        return FALSE;
    *pkey = intout[0];
    return TRUE;
}

/* Shrink pt by th on every side (grow it if th is negative). */
void gr_inside(GRECT *pt, WORD th)
{
    pt->g_x = (WORD)(pt->g_x + th);
    pt->g_y = (WORD)(pt->g_y + th);
    pt->g_w = (WORD)(pt->g_w - 2 * th);
    pt->g_h = (WORD)(pt->g_h - 2 * th);
}

/* A border th pixels thick around (x,y,w,h), in the current line colour.
 * GEM's sign convention: positive grows inward from the rectangle, negative
 * outward.  Drawn as |th| nested one-pixel outlines. */
void gr_box(WORD x, WORD y, WORD w, WORD h, WORD th)
{
    GRECT t, n;

    r_set(&t, x, y, w, h);
    if (th != 0) {
        if (th < 0)
            th--;
        gsx_moff();
        do {
            th = (WORD)(th + ((th > 0) ? -1 : 1));
            n = t;
            gr_inside(&n, th);
            gsx_box(&n);
        } while (th != 0);
        gsx_mon();
    }
}

/* ---- fills ------------------------------------------------------------ */

/* Fill (x,y,w,h) with interior style fis / pattern patt in the current
 * fill colour.  The colour is the caller's business (vsf_color is cheap
 * and uncached); the mode and pattern are cached here. */
void bb_fill(WORD mode, WORD fis, WORD patt, WORD x, WORD y, WORD w, WORD h)
{
    gsx_attr(1, mode, gl_tcolor);
    if (fis != gl_fis) {
        gsx_1code(VSF_INTERIOR, fis);
        gl_fis = fis;
    }
    if (patt != gl_patt) {
        gsx_1code(VSF_STYLE, patt);
        gl_patt = patt;
    }
    ptsin[0] = x;
    ptsin[1] = y;
    ptsin[2] = (WORD)(x + w - 1);
    ptsin[3] = (WORD)(y + h - 1);
    gsx_call(VR_RECFL, 2, 0);
}

/* The inside of an object: ipattern 0 is hollow (white), 7 solid, 1..6 the
 * VDI's first six fill patterns, all in icolor, replacing. */
void gr_rect(WORD icolor, WORD ipattern, const GRECT *pt)
{
    WORD fis = FIS_PATTERN;

    if (ipattern == IP_HOLLOW)
        fis = FIS_HOLLOW;
    else if (ipattern == IP_SOLID)
        fis = FIS_SOLID;
    gsx_fcolor(icolor);
    bb_fill(MD_REPLACE, fis, ipattern, pt->g_x, pt->g_y, pt->g_w, pt->g_h);
}

/* ---- text ------------------------------------------------------------- */

/* Stage a C string into intin[] as v_gtext wants it, one word per unsigned
 * byte; returns the count.  Clamped to the parameter block. */
WORD expand_string(WORD *dst, const char FAR *s)
{
    WORD n = 0;
    /* The byte is read into a local FIRST.  `dst[n++] = (uint8_t)*s++`
     * through a far pointer never finishes compiling at -O1 or -O2 in the
     * small data model -- cc65816 5.18.2 loops until it is killed (B18,
     * tools/ccbug/b18_farloop.c).  Splitting the read from the narrowing
     * is one of four shapes it accepts; this one costs nothing. */
    while (n < INTIN_SIZE - 1) {
        char c = *s++;
        if (!c)
            break;
        dst[n++] = (WORD)(uint8_t)c;
    }
    dst[n] = 0;
    return n;
}

/* Draw nc characters already staged in intin[] with the cell's top-left at
 * (x,y).  Only the system font exists on this device. */
void gsx_tblt(WORD font, WORD x, WORD y, WORD nc)
{
    (void)font;
    y = (WORD)(y + gl_hptschar);       /* v_gtext wants the baseline */
    ptsin[0] = x;
    ptsin[1] = y;
    gsx_call(V_GTEXT, 1, nc);
}

/* Measure text against a box: on return *pw / *ph are the extent the text
 * would occupy inside w x h; the result is how many characters fit.  The
 * string is staged in intin[] as a side effect, ready for gsx_tblt.
 *
 * The donor returns the count through a fifth pointer.  Calypsi 5.18
 * miscompiles `*out = c ? a : b` once it inlines a static function -- the
 * store lands in a dead stack slot and *out is never written
 * (tools/ccbug/, `make check-cc`) -- so the count is returned instead. */
static WORD gsx_tcalc(WORD font, const char FAR *ptext, WORD *pw, WORD *ph)
{
    WORD wc, hc, n;

    (void)font;
    wc = gl_wchar;
    hc = gl_hchar;
    n = expand_string(intin, ptext);
    if (n * wc < *pw)
        *pw = (WORD)(n * wc);
    if (hc < *ph)
        *ph = hc;
    if (*ph / hc)
        return (n < *pw / wc) ? n : (WORD)(*pw / wc);
    return 0;
}

/* Place text of the given justification inside (pt->g_x, pt->g_y, w, h):
 * pt is moved to where the first character goes.  Returns the number of
 * characters that fit (staged in intin[]). */
WORD gr_just(WORD just, WORD font, const char FAR *ptext, WORD w, WORD h, GRECT *pt)
{
    WORD numchs;

    pt->g_w = w;
    pt->g_h = h;
    numchs = gsx_tcalc(font, ptext, &pt->g_w, &pt->g_h);
    h = (WORD)(h - pt->g_h);
    if (h > 0)
        pt->g_y = (WORD)(pt->g_y + (h + 1) / 2);
    w = (WORD)(w - pt->g_w);
    if (w > 0) {
        switch (just) {
        case TE_RIGHT:
            pt->g_x = (WORD)(pt->g_x + w);
            break;
        case TE_CNTR:
            pt->g_x = (WORD)(pt->g_x + (w + 1) / 2);
            break;
        default:
            break;
        }
    }
    return numchs;
}

void gr_gtext(WORD just, WORD font, const char FAR *ptext, const GRECT *pt)
{
    GRECT t;
    WORD numchs;

    t = *pt;
    numchs = gr_just(just, font, ptext, t.g_w, t.g_h, &t);
    if (numchs > 0)
        gsx_tblt(font, t.g_x, t.g_y, numchs);
}

/* ---- raster ----------------------------------------------------------- */

/* Copy a w x h block of a 1-plane form at saddr to the screen at (dx,dy).
 * fg == -1 means an opaque copy (vro_cpyfm, rule is the raster op);
 * otherwise a transparent one in fg/bg (vrt_cpyfm, rule is the write mode). */
void gsx_blt(uint32_t saddr, WORD sx, WORD sy, WORD dx, WORD dy, WORD w, WORD h,
             WORD rule, WORD fg, WORD bg)
{
    static MFDB src, dst;

    src.fd_addr = saddr;
    src.fd_w = (WORD)((w / 8) * 8);
    src.fd_h = h;
    src.fd_wdwidth = (WORD)((w / 8) / 2);
    src.fd_stand = 0;
    src.fd_nplanes = 1;
    dst.fd_addr = 0;                    /* the screen */

    gsx_moff();
    ptsin[0] = sx;  ptsin[1] = sy;
    ptsin[2] = (WORD)(sx + w - 1);  ptsin[3] = (WORD)(sy + h - 1);
    ptsin[4] = dx;  ptsin[5] = dy;
    ptsin[6] = (WORD)(dx + w - 1);  ptsin[7] = (WORD)(dy + h - 1);
    contrl[7] = (WORD)(uint16_t)&src;
    contrl[8] = 0;
    contrl[9] = (WORD)(uint16_t)&dst;
    contrl[10] = 0;
    intin[0] = rule;
    if (fg == -1) {
        gsx_call(VRO_CPYFM, 4, 1);
    } else {
        intin[1] = fg;
        intin[2] = bg;
        gsx_call(VRT_CPYFM, 4, 3);
    }
    gsx_mon();
}

/* Screen-to-screen copy: what the window manager moves a window with.
 * The VDI clips the destination to the clip rectangle and drops the same
 * span from the source, so a window pushed part-way off the screen loses
 * only the part that left it.  Even x on both sides keeps this a single
 * blit (the blitter has no shifter); the window manager snaps window x
 * to even for that reason. */
void bb_screen(WORD sx, WORD sy, WORD dx, WORD dy, WORD w, WORD h)
{
    static MFDB scr;

    scr.fd_addr = 0;
    gsx_moff();
    ptsin[0] = sx;  ptsin[1] = sy;
    ptsin[2] = (WORD)(sx + w - 1);  ptsin[3] = (WORD)(sy + h - 1);
    ptsin[4] = dx;  ptsin[5] = dy;
    ptsin[6] = (WORD)(dx + w - 1);  ptsin[7] = (WORD)(dy + h - 1);
    contrl[7] = (WORD)(uint16_t)&scr;
    contrl[8] = 0;
    contrl[9] = (WORD)(uint16_t)&scr;
    contrl[10] = 0;
    intin[0] = S_ONLY;
    gsx_call(VRO_CPYFM, 4, 1);
    gsx_mon();
}

/* Save and restore a screen rectangle through the driver's save buffer
 * (vdi_save_form): a drop-down or an alert saves what it is about to cover
 * and puts it back afterwards.  The buffer is laid out like the screen, so
 * the copy goes both ways at the same coordinates and nothing has to
 * remember where a saved block came from.  The rectangle is widened to
 * even x and even width first: the blitter has no shifter, and the pixels
 * taken in are put back unchanged, so it costs nothing.  The donor's buffer
 * is 25 character columns wide and a wider drop-down overflows it (the
 * Atari corpus's menu_sr landmine, with the unclipped save); here the VDI
 * clips to the screen and the buffer is the screen's size, so neither can
 * happen. */
static void bb_save_restore(const GRECT *pr, WORD saveit)
{
    static MFDB scr, buf;
    GRECT clip;
    WORD x = (WORD)(pr->g_x & ~1);
    WORD w = (WORD)((pr->g_w + (pr->g_x & 1) + 1) & ~1);

    /* The clip comes off for the duration.  The rectangle is the whole
     * argument here -- what was taken in is what goes back -- and the
     * copy to the screen IS clipped by gem4xe's vro_cpyfm (the donor's
     * raster ops are not).  A clip that cuts the even-aligned rectangle
     * back to an odd one costs the blitter: the copy falls onto the
     * per-pixel path through the MEMAC window, which for an alert-sized
     * 200x70 is 168 frames against one blit.  Measured, once, the hard
     * way (docs/phase12.md).  menu_sr turns the clip off around its own
     * save and restore for the same reason; doing it here means no
     * caller has to know. */
    gsx_gclip(&clip);
    gsx_sclip(&gl_rzero);

    scr.fd_addr = 0;
    vdi_save_form(&buf);
    gsx_moff();
    ptsin[0] = x;  ptsin[1] = pr->g_y;
    ptsin[2] = (WORD)(x + w - 1);  ptsin[3] = (WORD)(pr->g_y + pr->g_h - 1);
    ptsin[4] = ptsin[0];  ptsin[5] = ptsin[1];
    ptsin[6] = ptsin[2];  ptsin[7] = ptsin[3];
    contrl[7] = (WORD)(uint16_t)(saveit ? &scr : &buf);
    contrl[8] = 0;
    contrl[9] = (WORD)(uint16_t)(saveit ? &buf : &scr);
    contrl[10] = 0;
    intin[0] = S_ONLY;
    gsx_call(VRO_CPYFM, 4, 1);
    gsx_mon();
    gsx_sclip(&clip);
}

void bb_save(const GRECT *pr)
{
    bb_save_restore(pr, TRUE);
}

void bb_restore(const GRECT *pr)
{
    bb_save_restore(pr, FALSE);
}

/* ---- the colour word -------------------------------------------------- */

/* Crack the colour word: border 15-12, text 11-8, mode bit 7,
 * pattern 6-4, inside 3-0. */
void gr_crack(UWORD color, WORD *pbc, WORD *ptc, WORD *pip, WORD *pic, WORD *pmd)
{
    *pbc = (WORD)((color >> 12) & 0x0F);
    *ptc = (WORD)((color >> 8) & 0x0F);
    *pmd = (WORD)((color & 0x80) ? MD_REPLACE : MD_TRANS);
    *pip = (WORD)((color >> 4) & 0x07);
    *pic = (WORD)(color & 0x0F);
}
