/* dev_antic.c -- the ANTIC side of the seam (vdidev.h).
 *
 * 320x192 at 1bpp in plain motherboard RAM -- on the 1.79 MHz bus, not at
 * the accelerator's speed (src/antic/antic.c says why).  So every
 * primitive here writes BYTES, each screen byte once, there is no list to
 * compile and nothing to flush -- the write WAS the drawing.  That is
 * the whole difference from src/vdi/dev_vbxe.c, and the reason the seam
 * is drawn where it is: above this line the VDI decides WHAT to draw,
 * below it the device decides how, and neither has to know the other's
 * bus.
 *
 * THE PEN.  This device has two colours, so a VDI pen is 0 or 1 and
 * there is no palette to map through.  A pen the VDI thinks is one of
 * sixteen arrives here as whatever it is; anything but 0 is ink, which
 * is the only sensible reading of "colour 7" on a device that has two.
 */
#include "portab.h"
#include "vdi.h"
#include "vdidev.h"
#include "../antic/antic.h"
#include "../sys/farmem.h"
#include <string.h>
#include "font.h"      /* vdi_font: WHICH face, which is not this file's choice */

void dev_fill_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    antic_rect_mode((int16_t)x1, (int16_t)y1, (int16_t)x2, (int16_t)y2,
                    1 /* MD_REPLACE */, (uint8_t)(pen ? 1 : 0));
}

void dev_xor_rect(WORD x1, WORD y1, WORD x2, WORD y2)
{
    antic_rect_mode((int16_t)x1, (int16_t)y1, (int16_t)x2, (int16_t)y2,
                    3 /* MD_XOR */, 1);
}

void dev_flush(void)
{
    /* nothing: the bytes are already on the screen */
}

/* A rectangle in the current pattern and writing mode.  Where the VBXE
 * device expands the pattern into VRAM once and lets the blitter walk
 * it, this one asks the VDI for a row per scanline and writes it -- the
 * same pattern, arriving a different way, which is exactly what the seam
 * is for.  pat_bits() takes the screen row and applies the pattern's own
 * row mask, so the phase is the VDI's and not this file's. */
void dev_patt_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    uint16_t rows[16];
    WORD r;

    /* The pattern's rows once, not once a scanline: every one repeats
     * within sixteen, and pat_bits takes a screen row. */
    for (r = 0; r < 16; r++)
        rows[r] = pat_bits(r);
    antic_fill_rect((int16_t)x1, (int16_t)y1, (int16_t)x2, (int16_t)y2,
                    rows, (int16_t)mode, (uint8_t)(pen ? 1 : 0));
}

/* A styled horizontal or vertical line.  The mask arrives anchored to
 * the screen's 16-pixel grid, so a horizontal line IS a patterned span
 * of one row and a vertical one is the same mask indexed by y. */
void dev_style_line(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    uint8_t pen = (uint8_t)(vwk.line_color ? 1 : 0);
    UWORD bits;
    WORD a, b;

    if (y1 == y2) {
        bits = style_anchor(mask, x1, (x2 >= x1) ? 1 : -1);
        a = x1;  b = x2;  order(&a, &b);
        if (!clip_rect(&a, &y1, &b, &y2))
            return;
        {
            /* ONE ROW OF A RECTANGLE: antic_fill_rect reads only
             * rows[y & 15], and a solid line is a solid rectangle.  So
             * antic_patt_span is not linked into the product at all --
             * 782 bytes the DOS 2 floppy did not have (docs/phase55.md). */
            uint16_t rows[16];

            rows[y1 & 15] = bits;
            antic_fill_rect((int16_t)a, (int16_t)y1, (int16_t)b, (int16_t)y1,
                            bits == 0xFFFF ? 0 : rows, (int16_t)mode, pen);
        }
        return;
    }
    bits = style_anchor(mask, y1, (y2 >= y1) ? 1 : -1);
    a = y1;  b = y2;  order(&a, &b);
    if (!clip_rect(&x1, &a, &x2, &b))
        return;
    antic_vline((int16_t)x1, (int16_t)a, (int16_t)b, bits,
                (int16_t)mode, pen);
}

/* Nothing is precomputed here, so there is nothing to throw away. */
void dev_invalidate(void)
{
}

/* ---- the pointer ------------------------------------------------------
 * The form as it stands: this device is 1bpp and so is GEM's MFORM, so
 * there is nothing to expand.  The VBXE side keeps a kilobyte of 4bpp
 * strips at both x parities for the same sixteen rows.
 */
static UWORD an_cur_mask[16], an_cur_data[16];
static uint8_t an_cur_bg, an_cur_fg;

void dev_cursor_form(WORD bg_pen, WORD fg_pen, const UWORD *mask,
                     const UWORD *data)
{
    WORD i;

    an_cur_bg = (uint8_t)(bg_pen ? 1 : 0);
    an_cur_fg = (uint8_t)(fg_pen ? 1 : 0);
    for (i = 0; i < 16; i++) {
        an_cur_mask[i] = mask[i];
        an_cur_data[i] = data[i];
    }
}

void dev_cursor_show(WORD cx, WORD cy)
{
    antic_cursor_save((int16_t)cx, (int16_t)cy);
    antic_cursor_paint((int16_t)cx, (int16_t)cy, an_cur_mask, an_cur_data,
                       an_cur_bg, an_cur_fg);
}

void dev_cursor_hide(void)
{
    antic_cursor_restore();
}

void dev_cursor_discard(void)
{
    antic_cursor_discard();
}

/* ---- text --------------------------------------------------------------
 * The font strip is 1bpp and so is this screen, so a glyph goes down as
 * it stands.  Nothing is derived from it and nothing has to be thrown
 * away when the face changes.
 */
void dev_font_changed(void)
{
}

void dev_raster_1bpp(const uint8_t FAR *bits, uint16_t stride,
                     WORD sx, WORD sy, WORD w, WORD h,
                     WORD dx, WORD dy, WORD mode, WORD ink, WORD bg);

void dev_glyph(WORD ch, WORD cx, WORD cy, WORD overlay)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);

    /* The thickening pass must ADD ink to the letter already there, so a
     * replace-mode overlay is drawn transparently -- otherwise it would
     * repaint the cell background and rub out the first pass.  XOR and
     * erase overlay in their own mode, which is what the other device's
     * pixel path does. */
    if (overlay && mode == MD_REPLACE)
        mode = MD_TRANS;
    if (cx < 0 || cy < 0 || cx + FONT_W > AN_W || cy + FONT_H > AN_H ||
        (vwk.clip &&
         (cx < vwk.xmn_clip || cy < vwk.ymn_clip ||
          cx + FONT_W - 1 > vwk.xmx_clip || cy + FONT_H - 1 > vwk.ymx_clip))) {
        /* A cell the clip or the screen edge cuts: the pixels of it that
         * are inside, through the raster path that clips by the row and
         * the column -- what the VBXE device's draw_glyph_cpu does.  It
         * used to be "the cell, or none of it", and a redraw whose edge
         * crossed a word left the letters under the edge blank: a 0.8.1
         * tester's DISK A read "DIS  A" under an F after About closed
         * (docs/phase67.md). */
        uint8_t g[FONT_H];
        WORD row;

        for (row = 0; row < FONT_H; row++)
            g[row] = *(const uint8_t FAR *)
                      (vdi_font + (uint32_t)row * FONT_STRIDE + (ch & 0xFF));
        dev_raster_1bpp((const uint8_t FAR *)g, 1, 0, 0, FONT_W, FONT_H,
                        cx, cy, mode, vwk.text_color,
                        mode == MD_ERASE ? vwk.text_color : 0);
        return;
    }
    {
        /* A run of one: the same pixels as antic_glyph, which the product
         * no longer links -- the DOS 2 floppy had no room for both
         * (docs/phase55.md). */
        int16_t c = (int16_t)ch;

        antic_text(vdi_font, &c, 1, (int16_t)cx, (int16_t)cy, (int16_t)mode,
                   (uint8_t)(vwk.text_color ? 1 : 0), FONT_W, FONT_H);
    }
}

/* A string's visible run, a row of the whole run at a time (text_run in
 * vdidev.h).  The mode is dev_glyph's for a first pass: never an overlay,
 * because v_gtext does not ask for thickened text here. */
void dev_text_run(const WORD *chars, WORD n, WORD x, WORD cy)
{
    antic_text(vdi_font, (const int16_t *)chars, (uint16_t)n,
               (int16_t)x, (int16_t)cy, (int16_t)(vwk.wrt_mode + 1),
               (uint8_t)(vwk.text_color ? 1 : 0), FONT_W, FONT_H);
}

/* vrt_cpyfm: a one-plane source into the screen -- which is how every
 * icon on the desk is drawn.  The rules per mode are the VDI's:
 *
 *   replace      ink where set, bg where clear
 *   transparent  ink where set
 *   XOR          complement where set
 *   erase        bg where CLEAR
 *
 * CLIPPED BY THE ROW, DRAWN BY THE BYTE.  It used to go pixel by pixel,
 * each one an antic_plot -- a call, four bounds tests, a row multiply and
 * a read and a write on the 1.79 MHz bus -- so a 32x32 icon cost 1,024 of
 * them.  Now the row's x range is cut to the screen and the clip
 * rectangle once, and antic_raster_row shifts the source into place and
 * touches each screen byte once: about 160 for the same icon, and none
 * of them a read where a replace covers the whole byte (docs/phase52.md).
 * The pixels are the same ones; test-m26's desk says so. */
void dev_raster_1bpp(const uint8_t FAR *bits, uint16_t stride,
                     WORD sx, WORD sy, WORD w, WORD h,
                     WORD dx, WORD dy, WORD mode, WORD ink, WORD bg)
{
    uint8_t pen = (uint8_t)(ink ? 1 : 0);
    uint8_t pap = (uint8_t)(bg ? 1 : 0);
    WORD r, xl, xr;

    /* the columns, once: the screen, then the clip rectangle */
    xl = dx;
    xr = (WORD)(dx + w - 1);
    if (xl < 0)
        xl = 0;
    if (xr >= AN_W)
        xr = AN_W - 1;
    if (vwk.clip) {
        if (xl < vwk.xmn_clip)
            xl = vwk.xmn_clip;
        if (xr > vwk.xmx_clip)
            xr = vwk.xmx_clip;
    }
    if (xl > xr || w <= 0)
        return;

    for (r = 0; r < h; r++) {
        WORD y = (WORD)(dy + r);
        const uint8_t FAR *row = bits + (uint16_t)(sy + r) * stride;

        if (y < 0 || y >= AN_H)
            continue;
        if (vwk.clip && (y < vwk.ymn_clip || y > vwk.ymx_clip))
            continue;
        antic_raster_row(row, (uint16_t)(sx + (xl - dx)),
                         (int16_t)xl, (int16_t)xr, (int16_t)y,
                         (int16_t)mode, pen, pap);
    }
}

/* ---- the diagonal ------------------------------------------------------
 * The same Bresenham the VBXE device runs, and the same order of
 * operations, because the pixel SET a line covers is the VDI's
 * specification (tools/vdiref.py) and not a device's choice: the style
 * rotates before each pixel and keeps rotating over pixels that are
 * clipped away or off the screen, the major axis steps every time so
 * the count is known in advance, and both ends are drawn.
 *
 * What differs is only what a pixel costs.  There it is a page map and a
 * read-modify-write through the MEMAC window; here it is a byte in RAM.
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
        WORD e2;
        WORD bit;

        if (m != 0xFFFF)                /* a solid style rotates into itself */
            m = (UWORD)((m << 1) | (m >> 15));
        bit = (WORD)(m & 1);

        if (x >= 0 && y >= 0 && x < AN_W && y < AN_H &&
            (!vwk.clip || (x >= vwk.xmn_clip && x <= vwk.xmx_clip &&
                           y >= vwk.ymn_clip && y <= vwk.ymx_clip))) {
            switch (mode) {
            case MD_TRANS:
                if (bit)
                    antic_plot((int16_t)x, (int16_t)y, pen);
                break;
            case MD_XOR:
                if (bit)
                    antic_plot((int16_t)x, (int16_t)y,
                               (uint8_t)!antic_get_pixel((int16_t)x, (int16_t)y));
                break;
            case MD_ERASE:
                if (!bit)
                    antic_plot((int16_t)x, (int16_t)y, pen);
                break;
            default:                    /* replace: the pen, or pen 0 */
                antic_plot((int16_t)x, (int16_t)y, (uint8_t)(bit ? pen : 0));
                break;
            }
        }
        if (--n == 0)
            break;
        e2 = (WORD)(err << 1);
        if (e2 > (WORD)-dy) { err = (WORD)(err - dy); x = (WORD)(x + sx); }
        if (e2 < dx)        { err = (WORD)(err + dx); y = (WORD)(y + sy); }
    }
}

/* ---- rasters -----------------------------------------------------------
 * WHERE THE SAVE AREA IS, and why it is not in bank $00.  The AES saves
 * the screen under a menu or a dialog into an off-screen form.  On the
 * VBXE device that is VRAM, of which there is half a megabyte spare; on
 * this one a screen is 7,680 bytes and bank $00 has not got them -- the
 * framebuffer already took the last free region ($8000-$9BFF), which is
 * the arithmetic src/antic/antic.h does for the screen's 192 lines.
 *
 * So the save area lives in FAR memory, in the accelerator's own SRAM,
 * taken once from the far allocator.  An MFDB's fd_addr is 24 bits wide
 * for exactly this reason, and a form here may therefore be near (the
 * screen, or an application's own form in bank $00) or far (this one) --
 * which is what form_get and form_put below are for.
 *
 * A machine with no accelerator has no far memory and gets no save area;
 * the AES then draws its menus without saving underneath, which is a
 * redraw, not a failure.
 */
static uint32_t an_save;                /* the far save area, 0 until asked */

void dev_screen_form(RFORM *f)
{
    f->base = AN_SCREEN;
    f->stride = AN_STRIDE;
    f->w = AN_W;
    f->h = AN_H;
    f->screen = 1;
}

void dev_save_form(MFDB *m)
{
    if (!an_save)
        an_save = far_alloc((uint32_t)AN_STRIDE * AN_H);
    m->fd_addr = an_save;
    m->fd_w = AN_W;
    m->fd_h = AN_H;
    m->fd_wdwidth = AN_W / 16;
    m->fd_stand = 0;
    m->fd_nplanes = 1;
    m->fd_r1 = m->fd_r2 = m->fd_r3 = 0;
}

/* A pixel of a form, near or far.  Anything below bank $01 is addressed
 * directly; anything above goes through the far window. */
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

/* A row's bytes in or out of a form, near or far. */
static void row_io(uint32_t a, uint8_t *buf, uint16_t n, WORD put)
{
    if (a + n <= 0x10000UL) {
        uint8_t *p = (uint8_t *)(uint16_t)a;
        if (put)
            memcpy(p, buf, n);
        else
            memcpy(buf, p, n);
    } else if (put) {
        far_put(a, buf, n);
    } else {
        far_get(buf, a, n);
    }
}

/* Two different forms copy a row of whole bytes at a time: the source
 * row read once, shifted into the destination's bit positions, and the
 * first and last destination bytes merged under a mask so not a pixel
 * outside the rectangle changes.  The pixel path below costs two 32-bit
 * multiplies and two far accesses a PIXEL: 0.8.1's tester saw a
 * drop-down take five seconds to appear at 14 MHz (the save under it is
 * screen to far memory, and the restore the same back), and G4BENCH had
 * screen to memory and back at 650-750 ms for 64x32.  The same form both
 * ends keeps the pixel path, which knows which way an overlap runs. */
#define ROW_MAX 48                      /* a screen row is 41 at most */

static WORD copy_rows(const RFORM *src, WORD sx1, WORD sy1,
                      const RFORM *dst, WORD dx1, WORD dy1, WORD w, WORD h)
{
    /* on the stack: bank $00 has no 50 bytes to keep for this (the
     * LoRAM budget, tests/host/test_memory.py) */
    uint8_t row[ROW_MAX + 2], e0, e1;
    uint16_t n, i, lead;
    uint8_t lm, rm, off;
    uint32_t sa, da;
    WORD y, q, sb;

    if (src->base == dst->base || w <= 0 || h <= 0)
        return 0;
    n = (uint16_t)((((UWORD)(dx1 + w - 1)) >> 3) - ((UWORD)dx1 >> 3) + 1);
    if (n > ROW_MAX)
        return 0;
    lm = (uint8_t)(0xFF >> (dx1 & 7));
    rm = (uint8_t)(0xFF << (7 - ((dx1 + w - 1) & 7)));
    if (n == 1)
        lm = rm = (uint8_t)(lm & rm);
    /* the source pixel under the destination's first whole byte: it may
     * be left of the source row's start, and those bits are masked off,
     * so a zero byte stands in for what would be read there */
    q = (WORD)(sx1 - (dx1 & 7));
    if (q < 0) {                        /* -7..-1: a byte before byte 0 */
        lead = 1;
        sb = 0;
        off = (uint8_t)(q + 8);
    } else {
        lead = 0;
        sb = (WORD)((UWORD)q >> 3);
        off = (uint8_t)(q & 7);
    }
    sa = src->base + (uint32_t)(UWORD)sy1 * src->stride + (UWORD)sb;
    da = dst->base + (uint32_t)(UWORD)dy1 * dst->stride + ((UWORD)dx1 >> 3);
    for (y = 0; y < h; y++) {
        /* n + 1 source bytes feed n shifted ones; the last may lie past
         * the row, and is read only for bits the mask throws away --
         * so it is not read at all past the form's own row */
        uint16_t want = (uint16_t)(n + 1 - lead);
        if ((uint16_t)(sb + want) > src->stride)
            want = (uint16_t)(src->stride - sb);
        row[0] = 0;
        row[want + lead] = 0;
        row_io(sa, row + lead, want, 0);
        row_io(da, &e0, 1, 0);
        row_io(da + n - 1, &e1, 1, 0);
        for (i = 0; i < n; i++)         /* in place: row[i + 1] is still
                                         * the source when row[i] is made */
            if (off)
                row[i] = (uint8_t)((row[i] << off) | (row[i + 1] >> (8 - off)));
        row[0] = (uint8_t)((e0 & (uint8_t)~lm) | (row[0] & lm));
        row[n - 1] = (uint8_t)((e1 & (uint8_t)~rm) | (row[n - 1] & rm));
        row_io(da, row, n, 1);
        sa += src->stride;
        da += dst->stride;
    }
    return 1;
}

void dev_copy_form(const RFORM *src, WORD sx1, WORD sy1,
                   const RFORM *dst, WORD dx1, WORD dy1, WORD w, WORD h)
{
    WORD y, i;
    WORD back_y, back_x;

    /* screen to screen is the window manager's move, and the surface has
     * a byte path for it */
    if (src->screen && dst->screen) {
        antic_copy((int16_t)sx1, (int16_t)sy1, (int16_t)dx1, (int16_t)dy1,
                   (int16_t)w, (int16_t)h);
        return;
    }
    if (copy_rows(src, sx1, sy1, dst, dx1, dy1, w, h))
        return;
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

/* ---- the rest ----------------------------------------------------------
 * A device with TWO colours, so the pen mapping is no mapping: pen 0 is
 * the background and anything else is ink.  There is no permutation to
 * make black and white bitwise complements, because on one bit they
 * already are -- which is the whole reason the VBXE device needs
 * map_col, and a good illustration of what the seam is hiding.
 */
void dev_clear_screen(void)
{
    antic_clear(0);
}

WORD dev_pen_value(WORD pen)
{
    return (WORD)(pen ? 1 : 0);
}

void dev_get_pixel(WORD x, WORD y, WORD *value, WORD *pen)
{
    WORD v = (WORD)antic_get_pixel((int16_t)x, (int16_t)y);

    *value = v;
    *pen = v;                           /* the same thing here */
}

void dev_read_row(WORD y, uint8_t *px)
{
    const uint8_t *p = (const uint8_t *)(uint16_t)
                       (AN_SCREEN + (uint16_t)y * AN_STRIDE);
    WORD i;

    for (i = 0; i < AN_STRIDE; i++)
        px[i] = p[i];
}

WORD dev_row_pixel(const uint8_t *px, WORD x)
{
    uint8_t b = px[(UWORD)x >> 3];      /* unsigned: see asr() */
    return (WORD)((b >> (7 - (x & 7))) & 1);
}

/* Two colours, and only one of them is a choice: mode F takes the
 * LUMINANCE of COLPF1 on the hue of COLPF2 (src/antic/antic.h).  So the
 * sixteen entries the VDI offers come down to the brightness of pen 1
 * against pen 0, and the rest is discarded rather than approximated --
 * a device that cannot show a colour should not pretend to. */
static uint8_t an_lum(const uint8_t *rgb)
{
    /* the usual weights, to a 4-bit Atari luminance */
    uint16_t l = (uint16_t)((rgb[0] * 77u + rgb[1] * 151u + rgb[2] * 28u) >> 8);
    return (uint8_t)((l >> 4) & 0x0E);
}

void dev_palette_all(const uint8_t *rgb)
{
    antic_init(an_lum(rgb + 3), an_lum(rgb));   /* pen 1 on pen 0 */
}

void dev_palette_one(WORD pen, const uint8_t *rgb)
{
    if (pen == 0 || pen == 1)
        antic_recolour(pen, an_lum(rgb));
}

WORD dev_colours(void)
{
    return 2;                           /* mode F is one bit */
}

WORD dev_planes(void)
{
    return 1;
}

/* ---- the table (vdidev.h) --------------------------------------------
 * The other half of the seam.  Same order, same promises, a different
 * screen -- and the font is Atari's condensed 6x6 rather than the 8x8,
 * because 320 pixels will not carry 80 columns of the other one.
 */
extern const uint8_t FAR font6x6[];

const VDIDEV FAR vdev_antic = {
    SCR_W, SCR_H, SCR_STRIDE,
    FONT_W, FONT_H,
    FONT_TOP, FONT_ASCENT, FONT_HALF, FONT_DESCENT, FONT_BOTTOM,
    FONT_POINT, font6x6,

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
    0,                  /* text_prefill: each byte is touched once anyway */
    dev_text_run,
};
