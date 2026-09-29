/* color.c -- COLOR.CPX, the screen's colours (0.9, item 6).
 *
 * The ST's Color panel: pick a pen from the row, move its red, green and
 * blue a step at a time, and the screen changes as you do.  A FORM CPX,
 * like GENERAL.CPX, and for the same reason: form_do is the right tool
 * for a page of buttons, and the panel's loop can wait while it is up.
 *
 * EVERY STEP APPLIES AT ONCE, through vs_color on the AES's own
 * workstation, because a colour can only be judged on the screen.  So
 * Cancel has real work: it puts back every pen exactly as the dialog
 * found it, from vq_color's REQUESTED values (flag 0) rather than from
 * what the hardware made of them, so nothing drifts.
 *
 * SIXTEEN STEPS A CHANNEL, 0..15, which is exactly the standard palette
 * (FF, BB and 77 are 15, 11 and 7): Reset puts back the palette gem4xe
 * starts with, not an approximation.  A step is 1000/15 of the VDI's
 * thousandths.  On ANTIC the screen has two pens, and of those only the
 * brightness survives (src/vdi/dev_antic.c) -- the row shows the two,
 * and the steps still move the brightness, which is what that screen
 * can do.
 *
 * WHAT IS SAVED is the whole palette as levels, a nibble a channel: 24
 * bytes for sixteen pens behind a mark, in the module's 64.  OK saves;
 * the panel puts it back at boot through CPX_BOOTINIT, as it does
 * GENERAL.CPX's.
 *
 * SMALL IN BANK $00 ON PURPOSE.  A module's near region comes out of the
 * application pool for the life of the machine, and QED needs 6,144 of
 * the 7,424 bytes a program gets with every accessory loaded
 * (docs/phase69.md) -- so this asks for the least the map says it uses,
 * and GENERAL.CPX was trimmed to the same.
 */
#include "cpx.h"
#include "colorrsc.h"

#define CL_MARK     0xC5        /* "a palette was saved here" */
#define CL_BYTES    (N_PENS * 3 / 2)

static OBJECT FAR *tree;
static CPXINFO cinfo;
static XCPB FAR *cl_xcpb;

static WORD vh;                 /* the AES's workstation */
static WORD npens;              /* what this screen has, at most N_PENS */
static WORD wchar;
static WORD sel;                /* the pen being edited */
static WORD lvl[N_PENS][3];     /* 0..15 */
static WORD was[N_PENS][3];     /* thousandths, as the dialog found them */

/* The standard palette in levels (src/vdi/vdi.c gem_rgb). */
static const uint8_t cl_default[N_PENS][3] = {
    {15, 15, 15}, { 0,  0,  0}, {15,  0,  0}, { 0, 15,  0},
    { 0,  0, 15}, { 0, 15, 15}, {15, 15,  0}, {15,  0, 15},
    {11, 11, 11}, { 7,  7,  7}, {11,  0,  0}, { 0, 11,  0},
    { 0,  0, 11}, { 0, 11, 11}, {11, 11,  0}, {11,  0, 11}
};

static WORD to_level(WORD v)
{
    WORD l = (WORD)(((int32_t)v * 15 + 500) / 1000);
    return (WORD)(l < 0 ? 0 : l > 15 ? 15 : l);
}

static void set_pen(WORD pen)
{
    WORD rgb[3], k;

    for (k = 0; k < 3; k++)
        rgb[k] = (WORD)(((int32_t)lvl[pen][k] * 1000 + 7) / 15);
    vs_color(vh, pen, rgb);
}

static void cl_open(void)
{
    WORD d, work_out[57];

    if (vh)
        return;
    vh = graf_handle(&wchar, &d, &d, &d);
    vq_extnd(vh, 0, work_out);
    npens = work_out[13];
    if (npens > N_PENS || npens < 2)
        npens = N_PENS;
}

/* ---- saving ----------------------------------------------------------- */

static void cl_restore(void)
{
    const uint8_t FAR *b;
    WORD p, k, i;

    if (!cl_xcpb || !cl_xcpb->buffer)
        return;
    b = (const uint8_t FAR *)cl_xcpb->buffer;
    if (b[0] != CL_MARK)
        return;                         /* nothing has been saved yet */
    for (p = 0; p < N_PENS; p++)
        for (k = 0; k < 3; k++) {
            WORD n = (WORD)(p * 3 + k);
            UWORD byte = b[1 + (n >> 1)];
            /* UNSIGNED: a signed 16-bit >> 4 is B12 (tools/ccbug), which
             * sign-extends from the wrong bit -- 0xFF >> 4 was -1, and a
             * saved white came back at boot with no red */
            lvl[p][k] = (WORD)((n & 1) ? (byte & 0x0F) : (byte >> 4));
        }
    for (i = 0; i < npens; i++)
        set_pen(i);
}

static void cl_remember(void)
{
    uint8_t FAR *b;
    WORD p, k;

    if (!cl_xcpb || !cl_xcpb->buffer || !cl_xcpb->CPX_Save)
        return;
    /* Packed in a local and written out whole, a byte each. */
    WORD pack[CL_BYTES];

    for (p = 0; p < CL_BYTES; p++)
        pack[p] = 0;
    for (p = 0; p < N_PENS; p++)
        for (k = 0; k < 3; k++) {
            WORD n = (WORD)(p * 3 + k);
            WORD v = lvl[p][k];
            if (n & 1)
                pack[n >> 1] |= v;
            else
                pack[n >> 1] |= (WORD)(v << 4);
        }
    b = (uint8_t FAR *)cl_xcpb->buffer;
    b[0] = CL_MARK;
    for (p = 0; p < CL_BYTES; p++)
        b[1 + p] = (uint8_t)pack[p];
    cl_xcpb->CPX_Save((uint32_t)cl_xcpb);
}

/* ---- the dialog ------------------------------------------------------- */

static WORD dx, dy, dw, dh;

/* An object, from the dialog's own background up: the root drawn,
 * clipped to the object.  A G_STRING is drawn transparently, so drawing
 * only it would leave the old digits under the new ones ("15" then " 0"
 * reads "10"). */
static void redraw(WORD ob)
{
    WORD x, y;

    objc_offset(tree, ob, &x, &y);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, tree[ob].ob_width,
              tree[ob].ob_height);
}

/* A TOUCHEXIT object makes form_do return while the button is still
 * DOWN, so asking again at once returns again: one click stepped a
 * channel seven times.  One press, one step -- wait for the release. */
static void wait_up(void)
{
    WORD d;

    evnt_button(1, 1, 0, &d, &d, &d, &d);
}

/* The channel's number and its bar, from lvl[sel]. */
static void show_channel(WORD c)
{
    WORD b = (WORD)(CLCH0 + c * CH_STEP), l = lvl[sel][c];
    char FAR *s = (char FAR *)(uint32_t)tree[b + CH_VALUE].ob_spec.index;

    s[0] = (char)(l >= 10 ? '1' : ' ');
    s[1] = (char)('0' + l % 10);
    tree[b + CH_BAR].ob_width = (WORD)(l * wchar);
    if (l)
        tree[b + CH_BAR].ob_flags &= (UWORD)~HIDETREE;
    else
        tree[b + CH_BAR].ob_flags |= HIDETREE;
}

static void show_all(void)
{
    WORD c;

    tree[CLMARK].ob_x = (WORD)(tree[CLSWBOX].ob_x + sel * tree[CLSW0].ob_width);
    for (c = 0; c < N_CHANNELS; c++)
        show_channel(c);
}

static void draw_channels(void)
{
    WORD c, b;

    for (c = 0; c < N_CHANNELS; c++) {
        b = (WORD)(CLCH0 + c * CH_STEP);
        redraw((WORD)(b + CH_VALUE));
        redraw((WORD)(b + CH_FRAME));
    }
}

/* The swatch row and the marker under it: the root, clipped to the strip
 * they share, so the old marker is erased by the background. */
static void draw_row(void)
{
    WORD x, y;

    objc_offset(tree, CLSWBOX, &x, &y);
    objc_draw(tree, ROOT, MAX_DEPTH, x, y, tree[CLSWBOX].ob_width,
              (WORD)(tree[CLSWBOX].ob_height * 2));
}

static SAVEDS void cl_cpx_call(uint32_t pbaddr)
{
    CPXPB FAR *pb = (CPXPB FAR *)pbaddr;
    WORD ret, ob, p, k, c, b;

    pb->ret = 0;                        /* a FORM CPX, like GENERAL's */
    if (!tree)
        return;
    cl_xcpb = (XCPB FAR *)pb->xcpb;
    cl_open();
    /* BOOTING: the saved palette, and no dialog (src/app/cpx.h) */
    if (cl_xcpb && cl_xcpb->booting) {
        cl_restore();
        return;
    }

    for (p = 0; p < N_PENS; p++) {
        WORD rgb[3];
        vq_color(vh, p, 0, rgb);        /* what was asked for: exact */
        for (k = 0; k < 3; k++) {
            was[p][k] = rgb[k];
            lvl[p][k] = to_level(rgb[k]);
        }
        if (p < npens)
            tree[CLSW0 + p].ob_flags &= (UWORD)~HIDETREE;
        else
            tree[CLSW0 + p].ob_flags |= HIDETREE;
    }
    if (sel >= npens)
        sel = 0;
    show_all();
    tree[CLRESET].ob_state = NORMAL;
    tree[CLOK].ob_state = NORMAL;
    tree[CLCNCL].ob_state = NORMAL;

    form_center(tree, &dx, &dy, &dw, &dh);
    form_dial(FMD_START, 0, 0, 0, 0, dx, dy, dw, dh);
    objc_draw(tree, ROOT, MAX_DEPTH, dx, dy, dw, dh);

    for (;;) {
        ret = form_do(tree, 0);
        ob = (WORD)(ret & 0x7FFF);
        if (ob == CLOK || ob == CLCNCL)
            break;
        if (ob >= CLSW0 && ob < CLSW0 + npens) {
            wait_up();
            sel = (WORD)(ob - CLSW0);
            show_all();
            draw_row();
            draw_channels();
            continue;
        }
        if (ob == CLRESET) {
            for (p = 0; p < N_PENS; p++) {
                for (k = 0; k < 3; k++)
                    lvl[p][k] = cl_default[p][k];
                if (p < npens)
                    set_pen(p);
            }
            tree[CLRESET].ob_state = NORMAL;
            show_all();
            objc_draw(tree, ROOT, MAX_DEPTH, dx, dy, dw, dh);
            continue;
        }
        for (c = 0; c < N_CHANNELS; c++) {
            b = (WORD)(CLCH0 + c * CH_STEP);
            if (ob == b + CH_MINUS || ob == b + CH_PLUS) {
                WORD l = lvl[sel][c];
                wait_up();
                l = (WORD)(ob == b + CH_PLUS ? l + 1 : l - 1);
                if (l < 0 || l > 15)
                    break;
                lvl[sel][c] = l;
                set_pen(sel);
                show_channel(c);
                redraw((WORD)(b + CH_VALUE));
                redraw((WORD)(b + CH_FRAME));
                break;
            }
        }
    }

    if (ob == CLOK) {
        cl_remember();
    } else {                            /* exactly what was there */
        for (p = 0; p < npens; p++)
            vs_color(vh, p, was[p]);
    }
    tree[CLOK].ob_state = NORMAL;
    tree[CLCNCL].ob_state = NORMAL;
    form_dial(FMD_FINISH, 0, 0, 0, 0, dx, dy, dw, dh);
}

static SAVEDS void cl_cpx_close(uint32_t pbaddr)
{
    (void)pbaddr;
}

CPX_ENTRY CPXINFO FAR *cpx_init(XCPB FAR *pb, CPXHEAD FAR *hdr)
{
    static const char title[] = "Color";
    WORD i;

    (void)pb;
    /* Taken once and kept, as GENERAL.CPX's is: a module lives as long
     * as the machine (src/aes/shel.c). */
    if (!rsrc_load("COLOR.RSC"))
        return (CPXINFO FAR *)0;
    rsrc_gaddr(R_TREE, ADCOLOR, (void **)&tree);
    if (!tree)
        return (CPXINFO FAR *)0;

    hdr->magic = CPX_MAGIC;
    hdr->flags = CPX_BOOTINIT;          /* the saved palette at boot */
    hdr->cpx_id = 0x434F4C52L;          /* 'COLR' */
    hdr->cpx_version = 1;
    for (i = 0; title[i] && i < 17; i++)
        hdr->title_txt[i] = title[i];
    hdr->title_txt[i] = 0;
    for (i = 0; title[i] && i < 13; i++)
        hdr->i_text[i] = title[i];
    hdr->i_text[i] = 0;

    cinfo.cpx_call = cl_cpx_call;
    cinfo.cpx_close = cl_cpx_close;
    return &cinfo;
}
