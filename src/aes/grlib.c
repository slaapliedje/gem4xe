/* grlib.c -- the AES graphics library (EmuTOS aes/gemgrlib.c): the XOR
 * rubber boxes behind form_dial's grow and shrink, graf_watchbox, and the
 * drag and rubber boxes the control manager moves and sizes windows with.
 *
 * Every box here is drawn twice in XOR mode, once to show and once to take
 * away, through gsx_xbox/gsx_xcbox's parity-phased dotted lines, so the
 * screen is left exactly as it was found.  What is left is the animation:
 * a box that walks from the icon to the dialog's centre and grows.
 */
#include "portab.h"
#include "aes.h"
#include "gemdata.h"

/* TRUE while the button is still down: waits for a release, a key, or the
 * pointer crossing the edge of (x,y,w,h) in the direction `out` asks. */
WORD gr_stilldn(WORD out, WORD x, WORD y, WORD w, WORD h)
{
    WORD  rets[6];
    MOBLK mo;
    WORD  which;

    mo.m_out = out;
    r_set(&mo.m_gr, x, y, w, h);
    which = ev_multi(MU_KEYBD | MU_BUTTON | MU_M1, &mo, 0,
                     0, 0x0001FF00UL, 0, rets);
    if (which & MU_BUTTON)
        return FALSE;
    return TRUE;
}

static void gr_setup(WORD color)
{
    gsx_sclip(&gl_rscreen);
    gsx_attr(FALSE, MD_XOR, color);
}

/* How many boxes to draw between here and there, and how far apart:
 * halve the mean distance until it is gone, one box per halving. */
static void gr_scale(WORD xdist, WORD ydist, WORD *pcnt, WORD *pxstep,
                     WORD *pystep)
{
    WORD i, dist, xs, ys;

    gr_setup(BLACK);
    dist = (WORD)((xdist + ydist) / 2);
    for (i = 0; dist; i++)
        dist = (WORD)(dist / 2);
    *pcnt = i;
    if (i != 0) {
        xs = (WORD)(xdist / i);
        if (xs < 1) xs = 1;
        ys = (WORD)(ydist / i);
        if (ys < 1) ys = 1;
    } else {
        xs = 1;
        ys = 1;
    }
    *pxstep = xs;
    *pystep = ys;
}

/* The centre of pt that a box orgw by orgh grows out of / shrinks into,
 * and the steps from there to pt's own corner. */
static void gr_stepcalc(WORD orgw, WORD orgh, const GRECT *pt, WORD *pcx,
                        WORD *pcy, WORD *pcnt, WORD *pxstep, WORD *pystep)
{
    WORD cx, cy;

    cx = (WORD)(pt->g_w / 2 - orgw / 2);
    cy = (WORD)(pt->g_h / 2 - orgh / 2);
    gr_scale(cx, cy, pcnt, pxstep, pystep);
    *pcx = (WORD)(cx + pt->g_x);
    *pcy = (WORD)(cy + pt->g_y);
}

/* cnt+1 boxes, each xstep/ystep up and left of the last and, if dowdht,
 * 2*step wider and taller: a box that grows about its centre. */
static void gr_xor(WORD clipped, WORD cnt, WORD cx, WORD cy, WORD cw, WORD ch,
                   WORD xstep, WORD ystep, WORD dowdht)
{
    GRECT t;

    do {
        r_set(&t, cx, cy, cw, ch);
        if (clipped)
            gsx_xcbox(&t);
        else
            gsx_xbox(&t);
        cx = (WORD)(cx - xstep);
        cy = (WORD)(cy - ystep);
        if (dowdht) {
            cw = (WORD)(cw + 2 * xstep);
            ch = (WORD)(ch + 2 * ystep);
        }
    } while (cnt--);
}

/* The sequence drawn and then undrawn. */
static void gr_2box(WORD flag1, WORD cnt, const GRECT *pt, WORD xstep,
                    WORD ystep, WORD flag2)
{
    WORD i;

    gsx_moff();
    for (i = 0; i < 2; i++)
        gr_xor(flag1, cnt, pt->g_x, pt->g_y, pt->g_w, pt->g_h,
               xstep, ystep, flag2);
    gsx_mon();
}

/* A box w by h that moves from (srcx,srcy) to (dstx,dsty). */
void gr_movebox(WORD w, WORD h, WORD srcx, WORD srcy, WORD dstx,
                       WORD dsty)
{
    WORD  signx, signy, cnt, xstep, ystep;
    GRECT t;

    r_set(&t, srcx, srcy, w, h);
    signx = (srcx < dstx) ? -1 : 1;
    signy = (srcy < dsty) ? -1 : 1;
    gr_scale((WORD)(signx * (srcx - dstx)), (WORD)(signy * (srcy - dsty)),
             &cnt, &xstep, &ystep);
    gr_2box(FALSE, cnt, &t, (WORD)(signx * xstep), (WORD)(signy * ystep),
            FALSE);
}

/* A small box that moves from po to the centre of pt and grows to fill
 * it (graf_growbox).  po is the caller's: GEM lets gr_growbox scribble on
 * its copy of the parameters, so the walk is done on a copy here. */
void gr_growbox(const GRECT *po, const GRECT *pt)
{
    WORD  cx, cy, cnt, xstep, ystep;
    GRECT o = *po;

    gr_stepcalc(o.g_w, o.g_h, pt, &cx, &cy, &cnt, &xstep, &ystep);
    gr_movebox(o.g_w, o.g_h, o.g_x, o.g_y, cx, cy);
    o.g_x = cx;
    o.g_y = cy;
    gr_2box(TRUE, cnt, &o, xstep, ystep, TRUE);
}

/* The reverse: pt shrinks to a small box at its centre, which moves to
 * po (graf_shrinkbox). */
void gr_shrinkbox(const GRECT *po, const GRECT *pt)
{
    WORD cx, cy, cnt, xstep, ystep;

    gr_stepcalc(po->g_w, po->g_h, pt, &cx, &cy, &cnt, &xstep, &ystep);
    gr_2box(TRUE, cnt, pt, (WORD)-xstep, (WORD)-ystep, TRUE);
    gr_movebox(po->g_w, po->g_h, cx, cy, po->g_x, po->g_y);
}

/* Track the button over obj: instate while the pointer is inside it,
 * outstate while outside, until the button is released.  Returns TRUE if
 * the pointer was inside at the release: `out` is flipped before each
 * wait to say which crossing to watch for next, so when the release ends
 * the loop it holds the opposite of where the pointer was. */
WORD gr_watchbox(OBJECT FAR *tree, WORD obj, WORD instate, WORD outstate)
{
    WORD  out, state;
    GRECT t;

    gsx_sclip(&gl_rscreen);
    ob_actxywh(tree, obj, &t);
    out = FALSE;
    do {
        if (out)
            state = outstate;
        else
            state = instate;
        ob_change(tree, obj, (UWORD)state, TRUE);
        out = !out;
    } while (gr_stilldn(out, t.g_x, t.g_y, t.g_w, t.g_h));
    return out;
}

/* The pointer and shift keys right now.  GEM's interrupts keep these
 * current; here a poll brings them up to date first. */
/* graf_mouse: the pointer's shape, or a command about it.  The donor's
 * gr_mouse (gemgrlib.c), with its M_SAVE/M_RESTORE/M_PREVIOUS extension:
 * there is one application here, so the saved form is one slot rather
 * than a field of the process.  A mode that is not a shape and not a
 * command is the arrow, as the donor's fail-safe. */
void gr_mouse(WORD mode, const WORD *pmform)
{
    WORD form[GEM_MFORM_WORDS];

    switch (mode) {
    case M_OFF:
        gsx_moff();
        return;
    case M_ON:
        gsx_mon();
        return;
    case M_SAVE:
        gsx_mfsave();
        return;
    case M_RESTORE:
        pmform = gsx_mfget(MF_SAVED, form) ? form : 0;
        break;
    case M_PREVIOUS:
        pmform = gsx_mfget(MF_PREV, form) ? form : 0;
        break;
    case USER_DEF:
        break;                          /* the caller's own 37 words */
    default:
        if (mode < ARROW || mode > OUTLN_CROSS)
            mode = ARROW;
        gsx_mfform(mode, form);
        pmform = form;
        break;
    }
    if (pmform)
        gsx_mfset(pmform);
}

void gr_mkstate(WORD *pmx, WORD *pmy, WORD *pmstat, WORD *pkstat)
{
    vdi_input_poll();
    kstate = gsx_kstate();
    *pmx = xrat;
    *pmy = yrat;
    *pmstat = button;
    *pkstat = kstate;
}

/* ---- drag and rubber boxes ---------------------------------------------- */

/* The rubber box's size from its corner and the pointer, no smaller than
 * the minimum. */
static void gr_clamp(WORD xo, WORD yo, WORD wmin, WORD hmin,
                     WORD *pw, WORD *ph)
{
    WORD w, h;

    w = xrat - xo + 1;
    h = yrat - yo + 1;
    *pw = (w > wmin) ? w : wmin;
    *ph = (h > hmin) ? h : hmin;
}

/* The box, and a second one offset from it (the work area inside a window
 * being sized) if there is one. */
static void gr_draw(WORD have2box, const GRECT *po, const GRECT *poff)
{
    GRECT t;

    gsx_xbox(po);
    if (have2box) {
        r_set(&t, po->g_x + poff->g_x, po->g_y + poff->g_y,
              po->g_w + poff->g_w, po->g_h + poff->g_h);
        gsx_xbox(&t);
    }
}

/* Show the box, wait for the pointer to move or the button to come up,
 * take the box away; TRUE if the button is still down. */
static WORD gr_wait(const GRECT *po, const GRECT *poff)
{
    WORD have2box, down;

    have2box = !rc_equal(&gl_rzero, poff);
    gsx_moff();
    gr_draw(have2box, po, poff);
    gsx_mon();
    down = gr_stilldn(TRUE, xrat, yrat, 1, 1);
    gsx_moff();
    gr_draw(have2box, po, poff);
    gsx_mon();
    return down;
}

/* A rubber box anchored at (xo,yo) that follows the pointer until the
 * button comes up; poff is the offset of a second box to draw along with
 * it (gl_rzero for none).  Returns the size. */
void gr_rubwind(WORD xo, WORD yo, WORD wmin, WORD hmin, const GRECT *poff,
                WORD *pw, WORD *ph)
{
    WORD  down;
    GRECT o;

    wm_update(BEG_UPDATE);
    gr_setup(BLACK);
    r_set(&o, xo, yo, 0, 0);
    do {
        gr_clamp(o.g_x, o.g_y, wmin, hmin, &o.g_w, &o.g_h);
        down = gr_wait(&o, poff);
    } while (down);
    *pw = o.g_w;
    *ph = o.g_h;
    wm_update(END_UPDATE);
}

void gr_rubbox(WORD xo, WORD yo, WORD wmin, WORD hmin, WORD *pw, WORD *ph)
{
    gr_rubwind(xo, yo, wmin, hmin, &gl_rzero, pw, ph);
}

/* Drag a w x h box from (sx,sy), keeping it inside pc, until the button
 * comes up.  The pointer keeps its offset into the box.  Returns where it
 * ended. */
void gr_dragbox(WORD w, WORD h, WORD sx, WORD sy, const GRECT *pc,
                WORD *pdx, WORD *pdy)
{
    WORD  offx, offy, down;
    GRECT o;

    wm_update(BEG_UPDATE);
    gr_setup(BLACK);
    gr_clamp(sx + 1, sy + 1, 0, 0, &offx, &offy);
    r_set(&o, sx, sy, w, h);
    do {
        o.g_x = xrat - offx;
        o.g_y = yrat - offy;
        rc_constrain(pc, &o);
        down = gr_wait(&o, &gl_rzero);
    } while (down);
    *pdx = o.g_x;
    *pdy = o.g_y;
    wm_update(END_UPDATE);
}

/* Drag the elevator obj along its bar parent; the result is where it was
 * left, in thousandths of the bar's travel. */
WORD gr_slidebox(OBJECT FAR *tree, WORD parent, WORD obj, WORD isvert)
{
    GRECT t, c;
    WORD  divnd, divis;

    ob_actxywh(tree, parent, &c);
    ob_relxywh(tree, obj, &t);
    gr_dragbox(t.g_w, t.g_h, t.g_x + c.g_x, t.g_y + c.g_y, &c,
               &t.g_x, &t.g_y);
    divnd = isvert ? t.g_y - c.g_y : t.g_x - c.g_x;
    divis = isvert ? c.g_h - t.g_h : c.g_w - t.g_w;
    return divis ? mul_div_round(divnd, 1000, divis) : 0;
}
