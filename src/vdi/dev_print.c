/* dev_print.c -- the printer side of the seam (vdidev.h).
 *
 * 640 x 800 dots at 1bpp in far memory, declared to the printer at 100
 * dpi: 6.4 x 8.0 inches, 80 columns of the same 8x8 face the VBXE screen
 * draws with, so a form laid out for the screen lands on the page at the
 * same coordinates.  docs/printing.md has the arithmetic and why the
 * page is that size and not a rounder one.
 *
 * THE PAGE IS ONE BANK, and that is the reason every loop below reads
 * like src/antic/antic.c's.  80 bytes a row by 800 rows is 64,000 against
 * a far bank's 65,536, so the page never straddles a bank -- and `FAR`
 * pointer arithmetic is sixteen bits WITHIN one (docs/phase24.md).  Pick
 * a page an inch taller and every offset here becomes a 24-bit
 * computation that Calypsi will do wrong in one of the ways this tree has
 * already been bitten by three times.
 *
 * WHAT A PRINTER HAS NOT GOT.  No pointer, so the four cursor calls are
 * nothing.  No palette, so the two colour calls are nothing: a dot is on
 * the paper or it is not, and a pen the VDI thinks is one of sixteen is
 * ink unless it is zero -- the same reading dev_antic.c takes, for the
 * same reason.  Nothing to flush and nothing to invalidate: the write
 * WAS the drawing, and what makes it a page is v_updwk, which is the
 * emitter's business and not this file's.
 */
#include "portab.h"
#include "vdi.h"
#include "vdidev.h"
#include "print.h"
#include "font.h"
#include "../sys/farmem.h"

uint8_t FAR *pr_page;

/* The masks a run's first and last byte are painted through.  Bit 7 is
 * the LEFTMOST dot, which is the one thing about 1bpp that catches
 * everyone once (src/antic/antic.c says so too). */
static const uint8_t pr_left[8] = {
    0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01
};
static const uint8_t pr_right[8] = {
    0x80, 0xC0, 0xE0, 0xF0, 0xF8, 0xFC, 0xFE, 0xFF
};

int16_t pr_page_open(void)
{
    uint16_t i;

    if (pr_page)
        return 1;                       /* one page; a second workstation
                                         * shares it, as it would a screen */
    pr_page = (uint8_t FAR *)far_alloc(PR_BYTES);
    if (!pr_page)
        return 0;
    for (i = 0; i < PR_BYTES; i++)
        pr_page[i] = 0;
    return 1;
}

void pr_page_close(void)
{
    /* The far heap is a bump allocator wound back by app_free, so the
     * page goes with the program that opened it.  Forgetting the pointer
     * is what this has to do; giving the bytes back is not its call. */
    pr_page = 0;
}

/* ---- the dots ---------------------------------------------------------- */

/* A byte of the page.  The offset is 16 bits because the page is one
 * bank; see the note at the top. */
static uint8_t FAR *pr_at(WORD x, WORD y)
{
    return pr_page + (uint16_t)((uint16_t)y * PR_STRIDE + ((UWORD)x >> 3));
}

static void pr_plot(WORD x, WORD y, uint8_t set)
{
    uint8_t FAR *p;
    uint8_t bit, v;

    if (!pr_page || x < 0 || y < 0 || x >= PR_W || y >= PR_H)
        return;
    p = pr_at(x, y);
    bit = (uint8_t)(0x80 >> (x & 7));
    v = *p;                             /* out, decided, back: ccbug rule 3 */
    v = set ? (uint8_t)(v | bit) : (uint8_t)(v & (uint8_t)~bit);
    *p = v;
}

static uint8_t pr_get(WORD x, WORD y)
{
    if (!pr_page || x < 0 || y < 0 || x >= PR_W || y >= PR_H)
        return 0;
    return (uint8_t)((*pr_at(x, y) >> (7 - (x & 7))) & 1);
}

/* One run in one writing mode.  The whole bytes in the middle are
 * written outright and only the two ends are read-modify-write, which is
 * the difference between a span and a string of plots.  `bits` is the
 * run's pattern for this row, already anchored by the caller. */
static void pr_span(WORD x1, WORD x2, WORD y, UWORD bits, WORD mode,
                    uint8_t pen)
{
    uint8_t FAR *p;
    uint8_t lm, rm, m, src, v;
    WORD b1, b2, b;

    if (!pr_page || y < 0 || y >= PR_H)
        return;
    if (x1 > x2) { WORD t = x1; x1 = x2; x2 = t; }
    if (x2 < 0 || x1 >= PR_W)
        return;
    if (x1 < 0) x1 = 0;
    if (x2 >= PR_W) x2 = PR_W - 1;

    b1 = (WORD)((UWORD)x1 >> 3);
    b2 = (WORD)((UWORD)x2 >> 3);
    lm = pr_left[x1 & 7];
    rm = pr_right[x2 & 7];
    p = pr_at(x1, y);

    for (b = b1; b <= b2; b++, p++) {
        m = 0xFF;
        if (b == b1) m &= lm;
        if (b == b2) m &= rm;
        /* The pattern's byte for this byte of the row.  A pattern row is
         * sixteen dots anchored to the page's 16-dot grid, so an even
         * byte takes the high half and an odd byte the low one -- the
         * phase is the VDI's (pat_bits) and not this file's. */
        src = (uint8_t)((b & 1) ? (bits & 0xFF) : (bits >> 8));
        if (!pen)
            src = (uint8_t)~src;        /* pen 0 paints the pattern's gaps */
        v = *p;
        switch (mode) {
        case MD_TRANS:  v = (uint8_t)(v | (src & m));               break;
        case MD_XOR:    v = (uint8_t)(v ^ (src & m));               break;
        case MD_ERASE:  v = (uint8_t)(v & (uint8_t)~((uint8_t)~src & m)); break;
        default:        v = (uint8_t)((v & (uint8_t)~m) | (src & m)); break;
        }
        *p = v;
    }
}

/* ---- the seam ---------------------------------------------------------- */

void dev_fill_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    WORD y;
    for (y = y1; y <= y2; y++)
        pr_span(x1, x2, y, pen ? 0xFFFF : 0x0000, MD_REPLACE,
                (uint8_t)(pen ? 1 : 0));
}

void dev_xor_rect(WORD x1, WORD y1, WORD x2, WORD y2)
{
    WORD y;
    for (y = y1; y <= y2; y++)
        pr_span(x1, x2, y, 0xFFFF, MD_XOR, 1);
}

void dev_patt_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    WORD y;

    for (y = y1; y <= y2; y++)
        pr_span(x1, x2, y, pat_bits(y), mode, (uint8_t)(pen ? 1 : 0));
}

void dev_style_line(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    uint8_t pen = (uint8_t)(vwk.line_color ? 1 : 0);
    WORD y;

    if (y1 == y2) {
        pr_span(x1, x2, y1, mask, mode, pen);
        return;
    }
    for (y = y1; y <= y2; y++) {
        WORD bit = (WORD)((mask >> (15 - (y & 15))) & 1);
        switch (mode) {
        case MD_TRANS:  if (bit) pr_plot(x1, y, pen);                  break;
        case MD_XOR:    if (bit) pr_plot(x1, y, (uint8_t)!pr_get(x1, y)); break;
        case MD_ERASE:  if (!bit) pr_plot(x1, y, pen);                 break;
        default:        pr_plot(x1, y, (uint8_t)(bit ? pen : 0));      break;
        }
    }
}

/* A row of a glyph.  THE FACE IS A STRIP, not a run of cells: row r of
 * every one of the 256 characters lies together, so the subscript is
 * `row * 256 + ch` and not `ch * height + row`.  It was the latter here
 * until test-m30 rendered "GEM4XE" as six other letters' middles -- the
 * whole reason the gate compares the page with the model rather than
 * looking at it.  src/antic/antic.c's an_font_row is the same function
 * for the same reason, including the arithmetic being done on the
 * uint32_t BEFORE the cast: a far pointer indexed by a computed
 * subscript does not survive cc65816 5.18 (docs/phase24.md). */
#define PR_FONT_STRIDE 256

static uint8_t pr_font_row(uint32_t face, WORD ch, WORD row)
{
    const uint8_t FAR *sr =
        (const uint8_t FAR *)(face + (uint32_t)(UWORD)row * PR_FONT_STRIDE);

    return sr[(UWORD)ch & 0xFF];
}

void dev_glyph(WORD ch, WORD cx, WORD cy, WORD overlay)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    uint8_t pen = (uint8_t)(vwk.text_color ? 1 : 0);
    WORD r;

    if (overlay == GLYPH_THICK) {       /* the letter, then its second pass */
        dev_glyph(ch, cx, cy, 0);
        dev_glyph(ch, (WORD)(cx + 1), cy, 1);
        return;
    }

    if (overlay && mode == MD_REPLACE)
        mode = MD_TRANS;                /* the thickening pass ADDS ink */
    if (vwk.clip &&
        (cx < vwk.xmn_clip || cy < vwk.ymn_clip ||
         cx + FONT_W - 1 > vwk.xmx_clip || cy + FONT_H - 1 > vwk.ymx_clip))
        return;                         /* the cell, or none of it */
    for (r = 0; r < FONT_H; r++) {
        uint8_t row = pr_font_row(vdi_font, ch, r);
        WORD i;
        for (i = 0; i < FONT_W; i++) {
            WORD bit = (WORD)((row >> (7 - i)) & 1);
            WORD x = (WORD)(cx + i), y = (WORD)(cy + r);
            switch (mode) {
            case MD_TRANS:  if (bit) pr_plot(x, y, pen);                 break;
            case MD_XOR:    if (bit) pr_plot(x, y, (uint8_t)!pr_get(x, y)); break;
            case MD_ERASE:  if (!bit) pr_plot(x, y, pen);                break;
            default:        pr_plot(x, y, (uint8_t)(bit ? pen : 0));     break;
            }
        }
    }
}

void dev_font_changed(void)
{
    /* nothing cached: the face is read a row at a time out of far memory */
}

void dev_raster_1bpp(const uint8_t FAR *bits, uint16_t stride,
                     WORD sx, WORD sy, WORD w, WORD h,
                     WORD dx, WORD dy, WORD mode, WORD ink, WORD bg)
{
    uint8_t pen = (uint8_t)(ink ? 1 : 0);
    uint8_t pap = (uint8_t)(bg ? 1 : 0);
    WORD r, c;

    for (r = 0; r < h; r++) {
        const uint8_t FAR *row = bits + (uint16_t)(sy + r) * stride;
        WORD y = (WORD)(dy + r);

        for (c = 0; c < w; c++) {
            WORD x = (WORD)(dx + c), sxc = (WORD)(sx + c);
            WORD set = (WORD)((row[(UWORD)sxc >> 3] >> (7 - (sxc & 7))) & 1);

            if (vwk.clip && (x < vwk.xmn_clip || x > vwk.xmx_clip ||
                             y < vwk.ymn_clip || y > vwk.ymx_clip))
                continue;
            switch (mode) {
            case MD_TRANS:  if (set) pr_plot(x, y, pen);                 break;
            case MD_XOR:    if (set) pr_plot(x, y, (uint8_t)!pr_get(x, y)); break;
            case MD_ERASE:  if (!set) pr_plot(x, y, pen);                break;
            default:        pr_plot(x, y, (uint8_t)(set ? pen : pap));   break;
            }
        }
    }
}

/* ---- what paper has not got ------------------------------------------- */

void dev_cursor_form(WORD bg, WORD fg, const UWORD *mask, const UWORD *data)
{
    (void)bg; (void)fg; (void)mask; (void)data;
}
void dev_cursor_show(WORD cx, WORD cy)  { (void)cx; (void)cy; }
void dev_cursor_hide(void)              { }
void dev_cursor_discard(void)           { }
void dev_invalidate(void)               { }
void dev_flush(void)                    { }
void dev_palette_all(const uint8_t *rgb)             { (void)rgb; }
void dev_palette_one(WORD pen, const uint8_t *rgb)   { (void)pen; (void)rgb; }

/* ---- the diagonal ------------------------------------------------------
 * The same Bresenham, in the same order, as both other devices: the
 * pixel set a line covers is the VDI's specification (tools/vdiref.py)
 * and not a device's choice.
 */
void dev_line_diag(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    uint8_t pen = (uint8_t)(vwk.line_color ? 1 : 0);
    WORD dx, dy, sx, sy, err, x = x1, y = y1;
    UWORD n, m = mask;

    dx = (WORD)(x2 - x1); if (dx < 0) dx = (WORD)-dx;
    dy = (WORD)(y2 - y1); if (dy < 0) dy = (WORD)-dy;
    sx = (WORD)(x1 < x2 ? 1 : -1);
    sy = (WORD)(y1 < y2 ? 1 : -1);
    err = (WORD)(dx - dy);
    n = (UWORD)((dx > dy ? dx : dy) + 1);

    for (;;) {
        WORD e2, bit;

        if (m != 0xFFFF)
            m = (UWORD)((m << 1) | (m >> 15));
        bit = (WORD)(m & 1);

        if (x >= 0 && y >= 0 && x < PR_W && y < PR_H &&
            (!vwk.clip || (x >= vwk.xmn_clip && x <= vwk.xmx_clip &&
                           y >= vwk.ymn_clip && y <= vwk.ymx_clip))) {
            switch (mode) {
            case MD_TRANS:  if (bit) pr_plot(x, y, pen);                 break;
            case MD_XOR:    if (bit) pr_plot(x, y, (uint8_t)!pr_get(x, y)); break;
            case MD_ERASE:  if (!bit) pr_plot(x, y, pen);                break;
            default:        pr_plot(x, y, (uint8_t)(bit ? pen : 0));     break;
            }
        }
        if (--n == 0)
            break;
        e2 = (WORD)(err << 1);
        if (e2 > (WORD)-dy) { err = (WORD)(err - dy); x = (WORD)(x + sx); }
        if (e2 < dx)        { err = (WORD)(err + dx); y = (WORD)(y + sy); }
    }
}

/* ---- forms -------------------------------------------------------------
 * The page IS a far form, so an MFDB naming it carries a 24-bit address
 * the way one naming the ANTIC device's save area does -- which is what
 * fd_addr has been 32 bits wide for since phase 2.
 */
void dev_screen_form(RFORM *f)
{
    f->base = (uint32_t)pr_page;
    f->stride = PR_STRIDE;
    f->w = PR_W;
    f->h = PR_H;
    f->screen = 1;
}

void dev_save_form(MFDB *m)
{
    /* No menus come down over a page, so nothing is ever saved from
     * under one.  An MFDB with no address is what the VDI reads as "this
     * device has no save area", which is the honest answer. */
    m->fd_addr = 0;
    m->fd_w = PR_W;
    m->fd_h = PR_H;
    m->fd_wdwidth = PR_W / 16;
    m->fd_stand = 0;
    m->fd_nplanes = 1;
    m->fd_r1 = m->fd_r2 = m->fd_r3 = 0;
}

static uint8_t form_get(const RFORM *f, WORD x, WORD y)
{
    uint32_t a = f->base + (uint32_t)y * f->stride + ((uint32_t)(UWORD)x >> 3);
    uint8_t b = (a < 0x10000UL) ? *(const uint8_t *)(uint16_t)a : far_read8(a);

    return (uint8_t)((b >> (7 - (x & 7))) & 1);
}

static void form_put(const RFORM *f, WORD x, WORD y, uint8_t v)
{
    uint32_t a = f->base + (uint32_t)y * f->stride + ((uint32_t)(UWORD)x >> 3);
    uint8_t bit = (uint8_t)(0x80 >> (x & 7));
    uint8_t b;

    if (a < 0x10000UL) {
        uint8_t *p = (uint8_t *)(uint16_t)a;
        b = *p;
        b = v ? (uint8_t)(b | bit) : (uint8_t)(b & (uint8_t)~bit);
        *p = b;
    } else {
        b = far_read8(a);
        b = v ? (uint8_t)(b | bit) : (uint8_t)(b & (uint8_t)~bit);
        far_write8(a, b);
    }
}

void dev_copy_form(const RFORM *src, WORD sx1, WORD sy1,
                   const RFORM *dst, WORD dx1, WORD dy1, WORD w, WORD h)
{
    WORD y, i, back_y, back_x;

    back_y = (WORD)(dy1 > sy1);
    back_x = (WORD)(dx1 > sx1);
    for (y = 0; y < h; y++) {
        WORD sy = back_y ? (WORD)(sy1 + h - 1 - y) : (WORD)(sy1 + y);
        WORD dy = back_y ? (WORD)(dy1 + h - 1 - y) : (WORD)(dy1 + y);

        for (i = 0; i < w; i++) {
            WORD sx = back_x ? (WORD)(sx1 + w - 1 - i) : (WORD)(sx1 + i);
            WORD dx = back_x ? (WORD)(dx1 + w - 1 - i) : (WORD)(dx1 + i);
            form_put(dst, dx, dy, form_get(src, sx, sy));
        }
    }
}

/* ---- the rest ---------------------------------------------------------- */

void dev_clear_screen(void)
{
    uint16_t i;
    if (!pr_page)
        return;
    for (i = 0; i < PR_BYTES; i++)
        pr_page[i] = 0;
}

WORD dev_pen_value(WORD pen)            { return (WORD)(pen ? 1 : 0); }

void dev_get_pixel(WORD x, WORD y, WORD *value, WORD *pen)
{
    WORD v = (WORD)pr_get(x, y);
    *value = v;
    *pen = v;
}

void dev_read_row(WORD y, uint8_t *px)
{
    const uint8_t FAR *p = pr_page + (uint16_t)((uint16_t)y * PR_STRIDE);
    WORD i;

    for (i = 0; i < PR_STRIDE; i++)
        px[i] = p[i];
}

WORD dev_row_pixel(const uint8_t *px, WORD x)
{
    uint8_t b = px[(UWORD)x >> 3];
    return (WORD)((b >> (7 - (x & 7))) & 1);
}

WORD dev_colours(void)  { return 2; }   /* ink, or no ink */
WORD dev_planes(void)   { return 1; }

/* ---- the table (vdidev.h) --------------------------------------------- */
extern const uint8_t FAR font8x8[];

const VDIDEV FAR vdev_print = {
    SCR_W, SCR_H, SCR_STRIDE,
    FONT_W, FONT_H,
    FONT_TOP, FONT_ASCENT, FONT_HALF, FONT_DESCENT, FONT_BOTTOM,
    FONT_POINT, font8x8,

    dev_fill_rect,
    dev_xor_rect,
    dev_patt_rect,
    dev_style_line,
    dev_glyph,
    dev_font_changed,
    dev_raster_1bpp,
    dev_cursor_form,
    dev_cursor_show,
    dev_cursor_hide,
    dev_cursor_discard,
    dev_line_diag,
    dev_screen_form,
    dev_copy_form,
    dev_save_form,
    dev_clear_screen,
    dev_get_pixel,
    dev_pen_value,
    dev_read_row,
    dev_row_pixel,
    dev_colours,
    dev_planes,
    dev_palette_all,
    dev_palette_one,
    dev_invalidate,
    dev_flush,
};
