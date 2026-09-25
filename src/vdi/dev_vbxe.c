/* dev_vbxe.c -- the VBXE side of the seam (vdidev.h).
 *
 * 640x240 at 4bpp, in VRAM that sits on the 1.79 MHz chip bus however
 * fast the 65816 runs.  So every primitive here compiles a BLIT LIST and
 * the CPU touches a pixel only where the blitter genuinely cannot help;
 * dev_flush() is what starts the list and waits for it.  The other
 * device (src/vdi/dev_antic.c) writes bytes and has nothing to flush,
 * and that difference is the whole reason the seam exists.
 *
 * Two pixels share a byte, high nibble the LEFT one, so every rectangle
 * has up to two partial ends.  Rectangle edges are exactly where 4bpp
 * VDI drivers historically went wrong, which is why tests/emu/m3_vdi.py
 * exercises odd x1, odd x2, and rectangles one pixel wide inside a
 * single byte.
 */
#include "portab.h"
#include "vdi.h"
#include "vdidev.h"
#include "../vbxe/vbxe.h"
#include "font.h"

/* The VDI's pen order into this device's hardware indices; the table is
 * below, with the reason it exists. */
#define HW(pen) ((WORD)map_col[(pen) & 0x0F])
extern const uint8_t map_col[16];

/* The VRAM offset of screen row y: y * SCR_STRIDE, without a multiply.
 *
 * It was `scr_row(y)` at every primitive's first line, and
 * that is a 32-bit multiply -- the stride is the device's, read at run
 * time, so the compiler cannot turn it into shifts -- which the compiler
 * then folded into shared fragments calling _Mul32.  The VBXE bench put
 * _Mul32 at a tenth of a window redraw (docs/phase53.md).  Every stride
 * this device has -- 256, 320 and 336 bytes, the three overlay widths --
 * is a multiple of 16, so y * (stride / 16) is at most 240 * 21 and fits
 * a word; it is a handful of shifts and adds over the five bits of that
 * small factor, and then the one shift back up. */
typedef char vb_strides_are_multiples_of_16[
    ((VB_W_NARROW / 2) % 16 == 0 && (VB_W_NORMAL / 2) % 16 == 0 &&
     (VB_W_WIDE / 2) % 16 == 0) ? 1 : -1];

static uint32_t scr_row(WORD y)
{
    uint16_t f = (uint16_t)((uint16_t)SCR_STRIDE >> 4);
    uint16_t a = (uint16_t)y, r = 0;

    while (f) {
        if (f & 1)
            r = (uint16_t)(r + a);
        a = (uint16_t)(a << 1);
        f = (uint16_t)(f >> 1);
    }
    return (uint32_t)r << 4;
}

void dev_fill_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    WORD hwpen = HW(pen);
    uint32_t base = VR_SCREEN0 + scr_row(y1);
    uint16_t rows = (uint16_t)(y2 - y1 + 1);
    uint8_t  c    = (uint8_t)(((hwpen & 0x0F) << 4) | (hwpen & 0x0F));
    WORD bl = (WORD)(x1 >> 1), br = (WORD)(x2 >> 1);

    if (bl == br) {
        if ((x1 & 1) == 0 && (x2 & 1) == 1) {           /* whole byte */
            blit_fill(base + bl, SCR_STRIDE, 1, rows, c);
        } else if (x1 & 1) {                            /* low nibble only */
            blit_and(base + bl, SCR_STRIDE, 1, rows, 0xF0);
            blit_or(base + bl, SCR_STRIDE, 1, rows, (uint8_t)(c & 0x0F));
        } else {                                        /* high nibble only */
            blit_and(base + bl, SCR_STRIDE, 1, rows, 0x0F);
            blit_or(base + bl, SCR_STRIDE, 1, rows, (uint8_t)(c & 0xF0));
        }
        return;
    }
    if (x1 & 1) {                                       /* partial left */
        blit_and(base + bl, SCR_STRIDE, 1, rows, 0xF0);
        blit_or(base + bl, SCR_STRIDE, 1, rows, (uint8_t)(c & 0x0F));
        bl++;
    }
    if ((x2 & 1) == 0) {                                /* partial right */
        blit_and(base + br, SCR_STRIDE, 1, rows, 0x0F);
        blit_or(base + br, SCR_STRIDE, 1, rows, (uint8_t)(c & 0xF0));
        br--;
    }
    if (br >= bl)
        blit_fill(base + bl, SCR_STRIDE, (uint16_t)(br - bl + 1), rows, c);
}

/* XOR a device rectangle: complement every pixel, which is what XOR mode
 * means in the VDI -- the pen is not consulted.  Same edge handling as the
 * fill, with the blitter's XOR mode doing the read-modify-write. */
void dev_xor_rect(WORD x1, WORD y1, WORD x2, WORD y2)
{
    uint32_t base = VR_SCREEN0 + scr_row(y1);
    uint16_t rows = (uint16_t)(y2 - y1 + 1);
    WORD bl = (WORD)(x1 >> 1), br = (WORD)(x2 >> 1);

    if (bl == br) {
        uint8_t m = 0xFF;
        if (x1 & 1)            m = 0x0F;        /* low nibble only  */
        else if ((x2 & 1) == 0) m = 0xF0;       /* high nibble only */
        blit_xor(base + bl, SCR_STRIDE, 1, rows, m);
        return;
    }
    if (x1 & 1) {
        blit_xor(base + bl, SCR_STRIDE, 1, rows, 0x0F);
        bl++;
    }
    if ((x2 & 1) == 0) {
        blit_xor(base + br, SCR_STRIDE, 1, rows, 0xF0);
        br--;
    }
    if (br >= bl)
        blit_xor(base + bl, SCR_STRIDE, (uint16_t)(br - bl + 1), rows, 0xFF);
}


/* The list started and waited for.  This is the only place the VDI's
 * device-independent code learns that a device might be asynchronous. */
void dev_flush(void)
{
    blit_run();
}

/* The pattern the blitter reads lives in VRAM at VR_PATT: 16 rows, each one
 * 16-pixel repeat of the pattern expanded to nibbles -- `set` where the bit
 * is one, `clr` where it is zero -- and written twice over, so that a blit
 * may begin at any byte of the repeat and read eight bytes before the
 * pattern counter sends it back to that byte.  Expanding costs 256 writes
 * through the MEMAC window, so what is there is remembered and reused until
 * the pattern or the nibbles change. */
static WORD    pe_src, pe_idx, pe_msk;
static uint8_t pe_set, pe_clr, pe_valid;

/* One 16-pixel repeat as eight nibble-pair bytes, written twice over. */
static void patt_row(volatile uint8_t *w, UWORD bits, uint8_t set, uint8_t clr)
{
    WORD k;
    for (k = 0; k < 8; k++) {
        uint8_t b = (uint8_t)(((bits & 0x8000) ? (set & 0xF0) : (clr & 0xF0)) |
                              ((bits & 0x4000) ? (set & 0x0F) : (clr & 0x0F)));
        w[k] = b;
        w[k + 8] = b;
        bits <<= 2;
    }
}

static void patt_expand(uint8_t set, uint8_t clr)
{
    volatile uint8_t *w;
    WORD r;

    if (pe_valid && pe_src == vwk.patsrc && pe_idx == vwk.patidx &&
        pe_msk == vwk.patmsk && pe_set == set && pe_clr == clr)
        return;
    w = vram_win(VR_PATT);
    for (r = 0; r < VR_PATT_ROWS; r++) {
        patt_row(w, pat_bits(r), set, clr);
        w += VR_PATT_STRIDE;
    }
    pe_src = vwk.patsrc;  pe_idx = vwk.patidx;  pe_msk = vwk.patmsk;
    pe_set = set;         pe_clr = clr;
    pe_valid = 1;
}

/* How a span of pattern is combined with the screen, per writing mode.  The
 * expansion holds what the mode needs (see patt_rect_dev), and `nib` says
 * which nibbles of each byte are inside the rectangle: 0xFF for the run of
 * whole bytes, 0x0F or 0xF0 for a partial byte at an odd edge.
 *
 * Mode 6 (the nibble stencil) cannot write nibble 0, and pen 0 -- white --
 * IS nibble 0; so a transparent or erase fill in pen 0 goes through AND
 * instead, F where the pixel survives and 0 where it is cleared.  AND is a
 * read-modify-write mode and the blitter skips any byte whose source is 0,
 * which is precisely the byte whose two pixels should both be cleared, so
 * it is applied a nibble at a time with the other nibble's mask forced to
 * F through the XOR mask.  Replace at an edge must leave the other pixel
 * alone, which a copy cannot: there it is an AND to clear the nibble and
 * an OR of the pattern into it, the pair dev_fill_rect uses. */
enum { PT_COPY, PT_HR, PT_AND, PT_XOR };

static void patt_span(WORD how, uint32_t src, uint16_t sstride, uint32_t dst,
                      uint16_t bytes, uint16_t rows, uint8_t nib)
{
    switch (how) {
    case PT_COPY:
        if (nib == 0xFF) {
            blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                         0xFF, 0x00, BLT_MODE_COPY, 8);
        } else {
            blit_and(dst, SCR_STRIDE, bytes, rows, (uint8_t)~nib);
            blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                         nib, 0x00, BLT_MODE_OR, 8);
        }
        break;
    case PT_HR:
        blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                     nib, 0x00, BLT_MODE_HR, 8);
        break;
    case PT_AND:
        if (nib & 0x0F)
            blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                         0x0F, 0xF0, BLT_MODE_AND, 8);
        if (nib & 0xF0)
            blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                         0xF0, 0x0F, BLT_MODE_AND, 8);
        break;
    default:
        blit_pattern(src, sstride, dst, SCR_STRIDE, bytes, rows,
                     nib, 0x00, BLT_MODE_XOR, 8);
        break;
    }
}

/* What the expansion holds and how it is combined, per writing mode:
 *
 *   replace       copy of (pen where set, 0 where clear); 0 is pen 0
 *   transparent   stencil (pen where set) -- or AND (0 where set) for pen 0
 *   XOR           XOR with F where set
 *   erase         transparent with set and clear exchanged
 */
static WORD patt_mode(WORD pen, uint8_t *set, uint8_t *clr)
{
    uint8_t nn = (uint8_t)(HW(pen) * 0x11);

    switch (vwk.wrt_mode + 1) {
    case MD_TRANS:
        if (nn) { *set = nn;   *clr = 0x00; return PT_HR; }
        *set = 0x00; *clr = 0xFF; return PT_AND;
    case MD_ERASE:
        if (nn) { *set = 0x00; *clr = nn;   return PT_HR; }
        *set = 0xFF; *clr = 0x00; return PT_AND;
    case MD_XOR:
        *set = 0xFF; *clr = 0x00; return PT_XOR;
    default:
        *set = nn;   *clr = 0x00; return PT_COPY;
    }
}

/* A device rectangle in the current pattern and writing mode: the general
 * case of vr_recfl, solid and hollow having been peeled off by fill_rect().
 *
 * The pattern is anchored to the SCREEN, not to the rectangle -- row y takes
 * pattern row (y AND mask), bit 15 is pixel 0 of every 16-aligned word -- so
 * adjoining fills tile seamlessly, which the GEM desktop's background relies
 * on.  A screen byte column c therefore wants pattern byte (c AND 7), which
 * is where each blit's source read starts, and the blitter's pattern counter
 * repeats the eight bytes from there.  The expansion has 16 rows, so a tall
 * rectangle goes in bands of up to 16 rows, each band its own short blit
 * list: edges first, then the run of whole bytes.  See patt_mode for what
 * each writing mode puts in the expansion. */
void dev_patt_rect(WORD x1, WORD y1, WORD x2, WORD y2, WORD pen)
{
    uint8_t set, clr;
    WORD how = patt_mode(pen, &set, &clr);
    WORD y;
    WORD bl = (WORD)(x1 >> 1), br = (WORD)(x2 >> 1);

    if (blit_pending())         /* nothing may still be reading VR_PATT */
        blit_run();
    patt_expand(set, clr);

    y = y1;
    while (y <= y2) {
        WORD     pr   = (WORD)(y & (VR_PATT_ROWS - 1));
        uint16_t rows = (uint16_t)(VR_PATT_ROWS - pr);
        uint32_t src  = VR_PATT + (uint32_t)pr * VR_PATT_STRIDE;
        uint32_t dst  = VR_SCREEN0 + scr_row(y);
        WORD l = bl, r = br;

        if (rows > (uint16_t)(y2 - y + 1))
            rows = (uint16_t)(y2 - y + 1);
        if (x1 & 1) {                                   /* partial left */
            patt_span(how, src + (l & 7), VR_PATT_STRIDE, dst + l, 1, rows, 0x0F);
            l++;
        }
        if ((x2 & 1) == 0) {                            /* partial right */
            patt_span(how, src + (r & 7), VR_PATT_STRIDE, dst + r, 1, rows, 0xF0);
            r--;
        }
        if (r >= l)
            patt_span(how, src + (l & 7), VR_PATT_STRIDE, dst + l,
                      (uint16_t)(r - l + 1), rows, 0xFF);
        y += (WORD)rows;
    }
}

/* A styled horizontal or vertical line as a pattern blit.  The AES draws its
 * rubber boxes and drag outlines in vsl_udsty dots, and plotting a 300x150
 * box pixel by pixel through the MEMAC window -- a read and a write on the
 * 1.79 MHz bus for each of 900 dots -- took milliseconds to show and again
 * to erase, enough to push a WM_MOVED past the frame it was due in.
 *
 * The style is anchored to the line's FIRST point: bit 15 there, the next
 * bit at each step towards the second point, in either direction, which is
 * what the Bresenham path below does and what tools/vdiref.py specifies.
 * As a word anchored to the screen (bit 15 at pixel 0 of every 16-aligned
 * word, the way a fill pattern is) that is the style rotated by the start
 * position, and clipping the line afterwards moves nothing.  A horizontal
 * line is one row of that word, expanded like a pattern row; a vertical line
 * is a column of bytes, one per row, all-set or all-clear, written once and
 * replicated by the blitter to VR_LINE_V_ROWS so that any screen height is
 * one control block.  Each strip is remembered, like the fill expansion: a
 * box's four sides alternate two phases, and its erase repeats them. */
static UWORD   lh_bits, lv_bits;
static uint8_t lh_set, lh_clr, lh_valid;
static uint8_t lv_set, lv_clr, lv_valid;

void dev_style_line(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask)
{
    uint8_t set, clr;
    WORD how = patt_mode(vwk.line_color, &set, &clr);
    WORD a, b;
    UWORD bits;
    uint32_t dst;

    /* No flush up front: a strip is only ever rewritten through vram_win(),
     * which drains the queue first (src/vbxe/vbxe.c), so the blits still
     * reading the old strip run before it changes -- and a run of lines in
     * the same style, which is most of them, never waits at all. */
    if (y1 == y2) {
        WORD l, r;

        bits = style_anchor(mask, x1, (x2 >= x1) ? 1 : -1);
        a = x1;  b = x2;  order(&a, &b);
        if (!clip_rect(&a, &y1, &b, &y2))
            return;
        if (!(lh_valid && lh_bits == bits && lh_set == set && lh_clr == clr)) {
            patt_row(vram_win(VR_LINE_H), bits, set, clr);
            lh_bits = bits;  lh_set = set;  lh_clr = clr;  lh_valid = 1;
        }
        dst = VR_SCREEN0 + scr_row(y1);
        l = (WORD)(a >> 1);  r = (WORD)(b >> 1);
        if (a & 1) {                                    /* partial left */
            patt_span(how, VR_LINE_H + (l & 7), 0, dst + l, 1, 1, 0x0F);
            l++;
        }
        if ((b & 1) == 0) {                             /* partial right */
            patt_span(how, VR_LINE_H + (r & 7), 0, dst + r, 1, 1, 0xF0);
            r--;
        }
        if (r >= l)
            patt_span(how, VR_LINE_H + (l & 7), 0, dst + l,
                      (uint16_t)(r - l + 1), 1, 0xFF);
    } else {
        bits = style_anchor(mask, y1, (y2 >= y1) ? 1 : -1);
        a = y1;  b = y2;  order(&a, &b);
        if (!clip_rect(&x1, &a, &x2, &b))
            return;
        if (!(lv_valid && lv_bits == bits && lv_set == set && lv_clr == clr)) {
            volatile uint8_t *w = vram_win(VR_LINE_V);
            UWORD bb = bits;
            WORD k;
            for (k = 0; k < 16; k++) {
                w[k] = (bb & 0x8000) ? set : clr;
                bb <<= 1;
            }
            /* the column, 16 rows of it, copied over the rest of the strip:
             * a source Y step of 0 re-reads the same 16 bytes each row */
            blit_copy(VR_LINE_V, 0, VR_LINE_V + 16, 16, 16,
                      (uint16_t)(VR_LINE_V_ROWS / 16 - 1));
            /* queued ahead of the span that reads it: order is enough */
            lv_bits = bits;  lv_set = set;  lv_clr = clr;  lv_valid = 1;
        }
        dst = VR_SCREEN0 + scr_row(a) + (uint32_t)(x1 >> 1);
        patt_span(how, VR_LINE_V + (a & 15), 1, dst, 1, (uint16_t)(b - a + 1),
                  (x1 & 1) ? 0x0F : 0xF0);
    }
}


/* The expansions above are caches; this is the VDI saying they are stale. */
void dev_invalidate(void)
{
    pe_valid = 0;
    lh_valid = lv_valid = 0;
}

/* ---- the pointer ------------------------------------------------------
 * The form as this device keeps it: the sixteen rows the VDI handed over,
 * and the 4bpp strips they expand into. */
static WORD  cur_bg, cur_fg;
static UWORD cur_mask[16], cur_data[16];
static WORD  sv_bx, sv_y, sv_nb, sv_nr;   /* what cursor_save() captured */

/* The pointer is drawn by the blitter.  vsc_form expands the form to 4bpp
 * strips, one pair per parity of x: an AND strip ($0 under the form, $F
 * elsewhere) and an OR strip (the data colour under the data, the mask colour
 * under the rest of the mask, $0 elsewhere).  A show is then the save copy
 * and two blits, one chain, wherever the pointer is; a hide is one copy.
 *
 * The first version plotted the 256 pixels through the MEMAC window.  At
 * ~60 us a pixel that was 12 ms a show -- most of a frame -- paid on every
 * move and twice around every primitive the AES hides the pointer for, and
 * it is what pushed the window sizer's release past the frame it was due in
 * (docs/phase8b.md).  The four strips are a kilobyte written once per form.
 *
 * Like real GEM the pointer ignores the clipping rectangle: it is drawn
 * wherever it is on the screen (the plotted version clipped it, and so did
 * the model -- both were wrong the same way). */
#define CUR_W          16
#define CUR_ROWS       VR_CURSOR_ROWS
#define CUR_STRIDE     VR_CURSOR_STRIDE
#define CUR_BYTES      (CUR_W / 2 + 1)         /* the odd-x span; even pads */
#define CUR_STRIP_LEN  ((uint32_t)CUR_STRIDE * CUR_ROWS)
#define VR_CUR_AND(par) (VR_CURSOR + (uint32_t)(par) * 2 * CUR_STRIP_LEN)
#define VR_CUR_OR(par)  (VR_CUR_AND(par) + CUR_STRIP_LEN)
typedef char cursor_strips_fit_one_page
    [((VR_CURSOR & 0xFFFUL) + VR_CURSOR_LEN <= 0x1000UL) ? 1 : -1];
typedef char cursor_stride_holds_the_odd_span[(CUR_STRIDE >= CUR_BYTES) ? 1 : -1];

void dev_cursor_form(WORD bg_pen, WORD fg_pen, const UWORD *mask,
                    const UWORD *data)
{
    cur_bg = bg_pen;  cur_fg = fg_pen;
    {
        WORD i;
        for (i = 0; i < 16; i++) {
            cur_mask[i] = mask[i];
            cur_data[i] = data[i];
        }
    }
    volatile uint8_t *w;
    WORD par, row, p;
    uint8_t fg = (uint8_t)HW(cur_fg), bg = (uint8_t)HW(cur_bg);

    if (blit_pending())         /* a show may still be reading the strips */
        blit_run();
    w = vram_win(VR_CURSOR);
    for (par = 0; par < 2; par++) {
        volatile uint8_t *pa = w + (uint16_t)(par * 2 * CUR_STRIP_LEN);
        volatile uint8_t *po = pa + (uint16_t)CUR_STRIP_LEN;
        for (row = 0; row < CUR_ROWS; row++) {
            UWORD m = cur_mask[row], d = cur_data[row];
            uint8_t a = 0, o = 0;
            /* strip pixel p holds form column p - par: at odd x the form
             * starts in the low nibble of its first byte */
            for (p = 0; p < 2 * CUR_BYTES; p++) {
                WORD col = (WORD)(p - par);
                uint8_t an = 0x0F, on = 0x00;
                if (col >= 0 && col < CUR_W) {
                    UWORD bit = (UWORD)(0x8000u >> col);
                    if (d & bit)      { an = 0; on = fg; }
                    else if (m & bit) { an = 0; on = bg; }
                }
                if (p & 1) {
                    pa[p >> 1] = (uint8_t)(a | an);
                    po[p >> 1] = (uint8_t)(o | on);
                } else {
                    a = (uint8_t)(an << 4);
                    o = (uint8_t)(on << 4);
                }
            }
            pa += CUR_STRIDE;
            po += CUR_STRIDE;
        }
    }
}

/* Queue the copy of what is under the form.  The caller runs the chain. */
static void cursor_save(WORD cx, WORD cy)
{
    WORD bx0, bx1, y0, y1;
    bx0 = (WORD)(cx >> 1);
    bx1 = (WORD)((cx + 15) >> 1);
    y0 = cy;
    y1 = (WORD)(cy + 15);
    if (bx0 < 0) bx0 = 0;
    if (y0 < 0) y0 = 0;
    if (bx1 > SCR_STRIDE - 1) bx1 = SCR_STRIDE - 1;
    if (y1 > SCR_H - 1) y1 = SCR_H - 1;
    if (bx1 < bx0 || y1 < y0) { sv_nb = 0; return; }
    sv_bx = bx0;
    sv_y  = y0;
    sv_nb = (WORD)(bx1 - bx0 + 1);
    sv_nr = (WORD)(y1 - y0 + 1);
    blit_copy(VR_SCREEN0 + scr_row(sv_y) + (uint32_t)sv_bx,
              SCR_STRIDE, VR_CURSAVE, VR_CURSAVE_STRIDE,
              (uint16_t)sv_nb, (uint16_t)sv_nr);
}

static void cursor_restore(void)
{
    if (!sv_nb)
        return;
    blit_copy(VR_CURSAVE, VR_CURSAVE_STRIDE,
              VR_SCREEN0 + scr_row(sv_y) + (uint32_t)sv_bx,
              SCR_STRIDE, (uint16_t)sv_nb, (uint16_t)sv_nr);
    blit_run();
    sv_nb = 0;
}

/* Queue the two strip blits over the block cursor_save() described.  The
 * strips are read from the same offset the screen edges clipped away. */
static void cursor_paint(WORD cx, WORD cy)
{
    WORD par = (WORD)(cx & 1);
    uint32_t off, dst;
    if (!sv_nb)
        return;
    off = (uint32_t)(sv_y - cy) * CUR_STRIDE
        + (uint32_t)(sv_bx - (WORD)(cx >> 1));
    dst = VR_SCREEN0 + scr_row(sv_y) + (uint32_t)sv_bx;
    blit_mask(VR_CUR_AND(par) + off, CUR_STRIDE, dst, SCR_STRIDE,
              (uint16_t)sv_nb, (uint16_t)sv_nr, 0xFF, 0x00, BLT_MODE_AND);
    blit_mask(VR_CUR_OR(par) + off, CUR_STRIDE, dst, SCR_STRIDE,
              (uint16_t)sv_nb, (uint16_t)sv_nr, 0xFF, 0x00, BLT_MODE_OR);
}


/* The three blits the VDI asks for as one: the block under the form
 * copied away, then the two strips over it, then the chain run. */
void dev_cursor_show(WORD cx, WORD cy)
{
    if (blit_pending())         /* room for the three blocks */
        blit_run();
    cursor_save(cx, cy);
    cursor_paint(cx, cy);
    blit_run();
}

void dev_cursor_hide(void)
{
    cursor_restore();
}

void dev_cursor_discard(void)
{
    sv_nb = 0;
}

/* Expand the 1bpp font strip into 4bpp glyph MASKS in VRAM: $F where ink,
 * $0 where paper.  One mask serves every ink colour -- see draw_glyph().
 *
 * Layout mirrors the source strip so a glyph is a single rectangle:
 *   VR_FONT + row*FONT_VSTRIDE + ch*FONT_BYTES, 4 bytes wide, 8 rows.
 *
 * The blitter has no shifter, so that strip only serves an EVEN x.  A second
 * strip holds every glyph one pixel to the right -- five bytes wide, with a
 * paper nibble at each end -- for odd x:
 *   VR_FONT_ODD + row*FONT_OSTRIDE + ch*FONT_OBYTES, 5 bytes wide, 8 rows.
 * The paper nibbles at the ends make the AND/OR pair leave the neighbouring
 * pixels alone, which is what keeps this correct under clipping.  Before it
 * existed, text at odd x went pixel by pixel through the MEMAC window at
 * about 6 ms per glyph -- a dialog's worth of text took half a second.
 *
 * Expanding on target rather than shipping a 4bpp blob keeps 2 KB linked
 * instead of 18 KB, which matters when the whole program lives in bank $00.
 */
#define FONT_BYTES   (FONT_W / 2)                 /* 4 bytes per glyph row */
#define FONT_VSTRIDE (256 * FONT_BYTES)           /* 1024 bytes per row    */
#define FONT_OBYTES  (FONT_W / 2 + 1)             /* 5 bytes, shifted      */
#define FONT_OSTRIDE (256 * FONT_OBYTES)          /* 1280 bytes per row    */
#define VR_FONT_ODD  (VR_FONT + (uint32_t)FONT_VSTRIDE * FONT_H)

/* A nibble-pair for every possible bit-pair, so expansion is a table lookup
 * rather than four conditionals per byte. */
static const uint8_t nib2[4] = { 0x00, 0x0F, 0xF0, 0xFF };

void dev_font_changed(void)
{
    /* The expanded font is 8 KB at VR_FONT: exactly two 4 KB MEMAC pages, and
     * within a page the layout is contiguous.  Streaming through a window
     * pointer keeps this to 16-bit pointer arithmetic; doing it with a
     * vram_write() per glyph costs 32-bit address maths 2,048 times and took
     * several emulated SECONDS. */
    WORD page, row, ch;
    for (page = 0; page < 2; page++) {
        volatile uint8_t *p = vram_win(VR_FONT + (uint32_t)page * 0x1000);
        for (row = (WORD)(page * 4); row < (WORD)(page * 4 + 4); row++) {
            const uint8_t FAR *sr =
                (const uint8_t FAR *)(vdi_font + (uint32_t)row * FONT_STRIDE);
            for (ch = 0; ch < 256; ch++) {
                uint8_t b = sr[ch];
                *p++ = nib2[(b >> 6) & 3];
                *p++ = nib2[(b >> 4) & 3];
                *p++ = nib2[(b >> 2) & 3];
                *p++ = nib2[b & 3];
            }
        }
    }

    /* The odd strip's rows are 1280 bytes, so they straddle MEMAC pages:
     * count the bytes left in the window and re-map when it runs out. */
    {
        uint32_t a = VR_FONT_ODD;
        volatile uint8_t *p = vram_win(a);
        uint16_t left = (uint16_t)(MEMAC_WIN_SIZE - (a & (MEMAC_WIN_SIZE - 1)));
        for (row = 0; row < FONT_H; row++) {
            const uint8_t FAR *sr =
                (const uint8_t FAR *)(vdi_font + (uint32_t)row * FONT_STRIDE);
            for (ch = 0; ch < 256; ch++) {
                uint8_t b = sr[ch];
                uint8_t out[FONT_OBYTES];
                WORD k;
                out[0] = nib2[(b >> 7) & 1];          /* paper, pixel 0     */
                out[1] = nib2[(b >> 5) & 3];
                out[2] = nib2[(b >> 3) & 3];
                out[3] = nib2[(b >> 1) & 3];
                out[4] = nib2[(b & 1) << 1];          /* pixel 7, paper     */
                for (k = 0; k < FONT_OBYTES; k++) {
                    *p++ = out[k];
                    if (--left == 0) {          /* next page, from its top */
                        a = (a | (MEMAC_WIN_SIZE - 1)) + 1;
                        p = vram_win(a);
                        left = MEMAC_WIN_SIZE;
                    }
                }
            }
        }
    }
}

/* Draw one glyph with its top-left at (cx, cy), cell fully visible, either
 * parity of cx -- the odd strip carries the shift.
 *
 * Two blits, and they work for every ink colour including 0:
 *
 *   AND  src=mask, and=$FF, xor=$FF, mode 4
 *        c is $00 where ink and $FF where paper.  Mode 4 is the one mode that
 *        WRITES 0 when c == 0 instead of skipping, so this clears exactly the
 *        ink pixels and leaves the paper ones untouched.
 *   OR   src=mask, and=ink*$11, xor=$00, mode 3
 *        c is the ink colour where ink and 0 where paper; a zero c is skipped,
 *        so only ink pixels are painted.
 *
 * With ink == 0 the OR writes nothing -- and it does not need to, because the
 * AND already left colour 0 there.  That is why no inverted mask is needed,
 * and why mode 6's nibble stencil (which cannot write colour 0) is not used.
 *
 * A caller that has just cleared the cell (replace mode) passes `cleared`
 * and the AND is skipped: there is nothing left for it to clear.
 */
static void draw_glyph(WORD ch, WORD cx, WORD cy, WORD hwink, WORD cleared)
{
    uint32_t src, dst;
    uint16_t sstride, bytes;
    uint8_t  c = (uint8_t)(((hwink & 0x0F) << 4) | (hwink & 0x0F));

    if (cx & 1) {
        src     = VR_FONT_ODD + (uint32_t)(ch & 0xFF) * FONT_OBYTES;
        sstride = FONT_OSTRIDE;
        bytes   = FONT_OBYTES;
    } else {
        src     = VR_FONT + (uint32_t)(ch & 0xFF) * FONT_BYTES;
        sstride = FONT_VSTRIDE;
        bytes   = FONT_BYTES;
    }
    dst = VR_SCREEN0 + scr_row(cy) + (uint32_t)(cx >> 1);

    if (!cleared)
        blit_mask(src, sstride, dst, SCR_STRIDE, bytes, FONT_H,
                  0xFF, 0xFF, BLT_MODE_AND);
    if (c)
        blit_mask(src, sstride, dst, SCR_STRIDE, bytes, FONT_H,
                  c, 0x00, BLT_MODE_OR);
}

/* ---------------------------------------------------------------------- */
/* 1bpp rasters: icons and cut glyphs                                     */
/* ---------------------------------------------------------------------- */

/* Expand a rectangle of a ONE-PLANE form into the screen in writing mode
 * `mode` (MD_*), with HARDWARE pens `fg` and `bg`.  This is vrt_cpyfm, and
 * v_gtext's fallback for a glyph the clip cuts or a mode the glyph blits do
 * not do.
 *
 * The source lives in RAM, not VRAM, so the blitter cannot read it; but it
 * can do the writing.  The CPU expands the clipped destination rectangle
 * into one 4bpp strip at VR_STRIP through one MEMAC mapping, and one blit
 * applies it; the strip holds most of a page, so a wide form goes in bands.
 *
 * The rules per mode, pixel by pixel, are the VDI's and tools/vdiref.py's:
 *   replace      fg where set, bg where clear
 *   transparent  fg where set
 *   XOR          complement where set
 *   erase        bg where CLEAR
 * and a pixel outside the clip rectangle or the screen is left alone.
 * Clipping is to the pixel.
 *
 * Which blit applies the strip depends on the pens.  Blitter mode 6, the
 * nibble stencil, writes each non-zero nibble of its source and leaves the
 * pixel under a zero one alone: so a strip holding the pen wherever a pixel
 * is written and 0 elsewhere -- clipped pixels included -- is the whole
 * raster in one blit, as long as no pen written is hardware 0, white, the
 * one nibble mode 6 cannot write.  A raster that writes only white is one
 * AND strip, 0 where written and $F elsewhere; XOR is one XOR strip, $F
 * where set.  A replace with white in it is a plain copy of the strip when
 * every strip byte lies wholly inside the clip; when the first or the last
 * does not, the strip is ORed in under an AND blit whose source is ONE row
 * -- $00 inside, $F over the pixel outside, the same on every row -- that
 * the blitter reads at a source step of zero.  The second strip of earlier
 * versions, a band of AND bytes for every raster, is gone: half the
 * slow-bus stores, and one control block instead of two.
 *
 * Eight source pixels -- one byte -- at a time: each nibble indexes a
 * 16-entry table of strip WORDS, the two strip bytes for four pixels, so a
 * source byte becomes four strip bytes in two indexed loads and stores.
 * Only a strip byte with a pixel outside the clip -- the first and the
 * last of a row -- and up to three bytes of remainder are built pixel by
 * pixel.  The tables are rebuilt only when the mode or a pen changes.  The
 * expander's state is in the direct page: the 65816 reaches it in two-byte
 * instructions and indexes through it, where a stack local costs a
 * three-byte one and cannot be indexed.  The first version did every pixel
 * on its own, ~120 instructions each; the second went four pixels at a time
 * through a shift register, ~80 per four; the third built two strips
 * (docs/phase8c.md).
 *
 * Source bits are MSB-first within each byte, rows `stride` bytes apart --
 * the VDI's own layout, kept exactly (see the MFDB note in vdi.h).  The form
 * is in bank $00: `bits` is a near pointer. */
#define R1_ROW   ((uint16_t)(VR_STRIP_LEN - 512))   /* the AND row's place */
                                        /* in the page; the strip is below  */
#define R1_TWO   0xFF                   /* r1_kind: the AND row and an OR   */

static uint8_t r1_pv[4];                /* two pixels (even<<1|odd) -> byte */
static UWORD   r1_v16[16];              /* four pixels -> two strip bytes,  */
                                        /* the first in the low byte        */
static uint8_t r1_out;                  /* the nibble of a pixel left alone */
static uint8_t r1_kind;                 /* BLT_MODE_* of the blit, or R1_TWO */
static UWORD   r1_sig = 0xFFFF;         /* what the tables were built for   */
static const uint8_t bit_of[8] = {0x80, 0x40, 0x20, 0x10, 8, 4, 2, 1};

/* the row expander's state, in the direct page */
/* FAR, because a 1bpp form's bytes need not be in bank $00 any more: a
 * resource's icons live in far memory so the application pool does not
 * have to hold them (src/aes/rsrc.c).  This was a near pointer and the
 * assignment from `bits` truncated the address to sixteen bits without a
 * word from the compiler -- the desktop's icons drew as noise and every
 * address on the way in was correct.  Four bytes of direct page and a
 * long read per source byte; a 32-wide icon is four of those a row. */
static const uint8_t FAR * TINY r1_s;  /* next source byte */
static volatile UWORD   * TINY r1_w;   /* next strip word  */
static TINY UWORD r1_n;                /* bytes to go      */
static TINY UWORD r1_b;                /* the source byte  */
static TINY UWORD r1_rsh;              /* 8 - shift        */
static TINY UWORD r1_hi, r1_lo;        /* the two nibbles' */
                                                        /* table offsets    */
/* A strip word from the table, by byte offset: one indexed load, the offset
 * held in the direct page rather than derived at each use. */
#define T16(t, off)  (*(const UWORD *)((const uint8_t *)(t) + (off)))

/* Build the table for a mode and a pair of pens, unless it stands, and
 * choose the blit.  `edges` says a strip byte has a pixel outside the
 * clip, which only a replace with white in it cares about. */
static void r1_tables(WORD mode, uint8_t fg, uint8_t bg, WORD edges)
{
    UWORD sig = (UWORD)(((UWORD)mode << 9) | ((UWORD)edges << 8) |
                        ((UWORD)fg << 4) | bg);
    uint8_t set_v, clr_v;
    WORD i;

    if (sig == r1_sig)
        return;
    r1_sig = sig;
    /* What a set and a clear source bit put in the strip. */
    switch (mode) {
    case MD_TRANS:
        if (fg) { set_v = fg;  clr_v = 0x0; r1_kind = BLT_MODE_HR;  }
        else    { set_v = 0x0; clr_v = 0xF; r1_kind = BLT_MODE_AND; }
        break;
    case MD_ERASE:
        if (bg) { set_v = 0x0; clr_v = bg;  r1_kind = BLT_MODE_HR;  }
        else    { set_v = 0xF; clr_v = 0x0; r1_kind = BLT_MODE_AND; }
        break;
    case MD_XOR:
        set_v = 0xF;  clr_v = 0x0;  r1_kind = BLT_MODE_XOR;
        break;
    default:                                            /* replace */
        set_v = fg;  clr_v = bg;
        r1_kind = (uint8_t)((fg && bg)   ? BLT_MODE_HR
                          : (!fg && !bg) ? BLT_MODE_AND
                          : edges        ? R1_TWO
                          :                BLT_MODE_COPY);
        break;
    }
    r1_out = (uint8_t)(r1_kind == BLT_MODE_AND ? 0xF : 0x0);
    for (i = 0; i < 4; i++)
        r1_pv[i] = (uint8_t)((((i & 2) ? set_v : clr_v) << 4) |
                             ((i & 1) ? set_v : clr_v));
    for (i = 0; i < 16; i++)
        r1_v16[i] = (UWORD)(r1_pv[i >> 2] | ((UWORD)r1_pv[i & 3] << 8));
}

/* r1_n source bytes that lie on the strip's byte boundaries: four strip
 * bytes each. */
static void expand_aligned(void)
{
    do {
        r1_b = *r1_s++;
        r1_hi = (UWORD)((r1_b >> 4) << 1);
        r1_lo = (UWORD)((r1_b & 15) << 1);
        r1_w[0] = T16(r1_v16, r1_hi);
        r1_w[1] = T16(r1_v16, r1_lo);
        r1_w += 2;
    } while (--r1_n);
}

/* The same, with the source r1_rsh bits to the right of the strip's byte
 * boundaries: each output byte straddles two source bytes.  The last one
 * reads one byte past the row it needs, inside the form or just after it:
 * bank $00 RAM, and only the bits above the boundary are used. */
static void expand_shifted(void)
{
    do {
        r1_b = (UWORD)((((UWORD)r1_s[0] << 8) | r1_s[1]) >> r1_rsh) & 0xFF;
        r1_s++;
        r1_hi = (UWORD)((r1_b >> 4) << 1);
        r1_lo = (UWORD)((r1_b & 15) << 1);
        r1_w[0] = T16(r1_v16, r1_hi);
        r1_w[1] = T16(r1_v16, r1_lo);
        r1_w += 2;
    } while (--r1_n);
}

/* One strip byte for a pixel pair, `i` its bits (even<<1|odd), with the
 * pixel outside the clip -- if there is one -- left alone. */
static void edge_byte(WORD i, WORD in_even, WORD in_odd, volatile uint8_t *pv)
{
    uint8_t vb = r1_pv[i];
    if (!in_even) vb = (uint8_t)((vb & 0x0F) | (r1_out << 4));
    if (!in_odd)  vb = (uint8_t)((vb & 0xF0) | r1_out);
    *pv = vb;
}

/* source pixel p of a row, as 0 or 1 */
#define SRC_BIT(row, p) (((row)[(UWORD)(p) >> 3] & bit_of[(p) & 7]) ? 1 : 0)

static void raster_1bpp(const uint8_t FAR *bits, uint16_t stride,
                        WORD sx1, WORD sy1, WORD w, WORD h,
                        WORD dx1, WORD dy1, WORD mode, uint8_t fg, uint8_t bg)
{
    WORD cx0, cy0, cx1, cy1, bx0, nb, band, y;
    WORD first_part, last_part, n8, rem, sxf, sh, px_first, px_rem, px_last;

    if (w <= 0 || h <= 0)
        return;
    /* The destination, clipped to the pixel: the clip rectangle when one is
     * set, then the screen. */
    cx0 = dx1;  cy0 = dy1;
    cx1 = (WORD)(dx1 + w - 1);  cy1 = (WORD)(dy1 + h - 1);
    if (vwk.clip) {
        if (cx0 < vwk.xmn_clip) cx0 = vwk.xmn_clip;
        if (cy0 < vwk.ymn_clip) cy0 = vwk.ymn_clip;
        if (cx1 > vwk.xmx_clip) cx1 = vwk.xmx_clip;
        if (cy1 > vwk.ymx_clip) cy1 = vwk.ymx_clip;
    }
    if (cx0 < 0) cx0 = 0;
    if (cy0 < 0) cy0 = 0;
    if (cx1 > SCR_W - 1) cx1 = SCR_W - 1;
    if (cy1 > SCR_H - 1) cy1 = SCR_H - 1;
    if (cx1 < cx0 || cy1 < cy0)
        return;
    bx0 = (WORD)(cx0 >> 1);
    nb  = (WORD)((cx1 >> 1) - bx0 + 1);

    /* A strip byte with a pixel outside the clip is built on its own: the
     * first when the clip starts at odd x, the last when it ends at even x.
     * The bytes between go a source byte -- four strip bytes -- at a time,
     * and up to three remain: a pair of strip bytes from the high nibble of
     * the next source byte, then a single one built from its pixels. */
    first_part = (WORD)(cx0 & 1);
    last_part  = (WORD)(!(cx1 & 1));
    {
        WORD nf = (WORD)(nb - first_part - last_part);
        n8  = (WORD)((UWORD)nf >> 2);   /* nf >= 0; and see asr() */
        rem = (WORD)(nf & 3);
        /* source x under the first whole byte's even pixel, and under the
         * even pixel of each byte built on its own */
        sxf = (WORD)(sx1 + (bx0 * 2 + first_part * 2 - dx1));
        sh  = (WORD)(sxf & 7);
        px_first = (WORD)(sxf - 1);                     /* its odd pixel   */
        px_rem   = (WORD)(sxf + n8 * 8 + ((rem & 2) ? 4 : 0));
        px_last  = (WORD)(sx1 + (cx1 - dx1));
    }
    r1_rsh = (UWORD)(8 - sh);
    r1_tables(mode, fg, bg, (WORD)(first_part | last_part));

    band = (WORD)(R1_ROW / (uint16_t)nb);       /* rows a band holds */
    if (band > 256)
        band = 256;
    if (blit_pending())     /* the last raster may still read the strip */
        blit_run();
    if (r1_kind == R1_TWO) {
        /* the AND row: everything inside cleared, the outside pixel kept */
        volatile uint8_t *pa = vram_win(VR_STRIP) + R1_ROW;
        WORD k;
        for (k = 0; k < nb; k++)
            pa[k] = 0x00;
        if (first_part) pa[0] = 0xF0;
        if (last_part)  pa[nb - 1] |= 0x0F;
    }
    /* the source row under the first clipped destination row */
    bits += (uint16_t)(sy1 + (cy0 - dy1)) * stride;
    for (y = cy0; y <= cy1; y += band) {
        WORD rows = (WORD)(cy1 - y + 1);
        volatile uint8_t *pv;
        uint32_t dst;
        WORD r;

        if (rows > band)
            rows = band;
        if (blit_pending())     /* the last band may still read the strip */
            blit_run();
        pv = vram_win(VR_STRIP);
        for (r = 0; r < rows; r++, bits += stride) {
            if (first_part) {
                edge_byte(SRC_BIT(bits, px_first), 0, 1, pv);
                pv++;
            }
            if (n8) {
                r1_s = bits + ((UWORD)sxf >> 3);
                r1_w = (volatile UWORD *)pv;
                r1_n = (UWORD)n8;
                if (sh)
                    expand_shifted();
                else
                    expand_aligned();
                pv += n8 * 4;
            }
            if (rem & 2) {
                WORD p = (WORD)(sxf + n8 * 8);
                WORD i = (WORD)((SRC_BIT(bits, p) << 3) |
                                (SRC_BIT(bits, p + 1) << 2) |
                                (SRC_BIT(bits, p + 2) << 1) |
                                 SRC_BIT(bits, p + 3));
                *(volatile UWORD *)pv = r1_v16[i];
                pv += 2;
            }
            if (rem & 1) {
                edge_byte((WORD)((SRC_BIT(bits, px_rem) << 1) |
                                  SRC_BIT(bits, px_rem + 1)), 1, 1, pv);
                pv++;
            }
            if (last_part) {
                edge_byte((WORD)(SRC_BIT(bits, px_last) << 1), 1, 0, pv);
                pv++;
            }
        }
        dst = VR_SCREEN0 + scr_row(y) + (uint32_t)bx0;
        if (r1_kind == R1_TWO) {
            blit_mask(VR_STRIP + R1_ROW, 0, dst, SCR_STRIDE,
                      (uint16_t)nb, (uint16_t)rows, 0xFF, 0x00,
                      BLT_MODE_AND);
            blit_mask(VR_STRIP, (uint16_t)nb, dst, SCR_STRIDE,
                      (uint16_t)nb, (uint16_t)rows, 0xFF, 0x00,
                      BLT_MODE_OR);
        } else {
            blit_mask(VR_STRIP, (uint16_t)nb, dst, SCR_STRIDE,
                      (uint16_t)nb, (uint16_t)rows, 0xFF, 0x00, r1_kind);
        }
        /* the next band's vram_win() drains these before the strip moves */
    }
}

/* A glyph the clipping rectangle or the screen cuts, or a writing mode the
 * two-blit path does not do (XOR, erase): its eight rows go through the same
 * 1bpp raster path as an icon.  Erase paints the text colour where the glyph
 * is CLEAR, so that is the "background" it is given. */
static void draw_glyph_cpu(WORD ch, WORD cx, WORD cy)
{
    uint8_t g[FONT_H];
    WORD row, mode = (WORD)(vwk.wrt_mode + 1);
    uint8_t ink = (uint8_t)HW(vwk.text_color);
    for (row = 0; row < FONT_H; row++)
        g[row] = *(const uint8_t FAR *)
                  (vdi_font + (uint32_t)row * FONT_STRIDE + (ch & 0xFF));
    raster_1bpp(g, 1, 0, 0, FONT_W, FONT_H, cx, cy, mode, ink,
                (uint8_t)(mode == MD_ERASE ? ink : HW(0)));
}

/* v_gtext.  Alignment is left/baseline (vst_alignment is not implemented, so
 * only the default applies): the y given is the BASELINE, and the cell top is
 * y - FONT_TOP.
 *
 * Replace mode paints the cell background first; transparent mode leaves it.
 * GEM has no separate text background colour -- replace mode uses pen 0.
 * XOR and erase modes go pixel by pixel; the AES draws text in replace and
 * transparent mode only, so those two are the ones the blitter serves. */

/* One glyph, and the two ways this device has of putting it there: the
 * blitter serves replace and transparent mode, which is what the AES
 * draws text in, and everything else goes pixel by pixel through
 * raster_1bpp.  `overlay` is the thickening pass -- no cell background,
 * and never a fresh clear. */
void dev_glyph(WORD ch, WORD cx, WORD cy, WORD overlay)
{
    WORD mode = (WORD)(vwk.wrt_mode + 1);
    WORD blittable = (mode == MD_REPLACE || mode == MD_TRANS);
    WORD fits = (cx >= 0 && cy >= 0 &&
                 cx + FONT_W <= SCR_W && cy + FONT_H <= SCR_H);

    if (fits && vwk.clip)
        fits = (cx >= vwk.xmn_clip && cy >= vwk.ymn_clip &&
                cx + FONT_W - 1 <= vwk.xmx_clip &&
                cy + FONT_H - 1 <= vwk.ymx_clip);
    if (fits && blittable) {
        if (mode == MD_REPLACE && !overlay)
            dev_fill_rect(cx, cy, (WORD)(cx + FONT_W - 1),
                          (WORD)(cy + FONT_H - 1), 0);
        draw_glyph(ch, cx, cy, HW(vwk.text_color),
                   (WORD)(!overlay && mode == MD_REPLACE));
        /* no run per glyph: a string is one list (vdi(), src/vdi/vdi.c) */
    } else {
        draw_glyph_cpu(ch, cx, cy);
    }
}

/* vrt_cpyfm's one-plane expansion, with the pens mapped here. */
void dev_raster_1bpp(const uint8_t FAR *bits, uint16_t stride,
                     WORD sx, WORD sy, WORD w, WORD h,
                     WORD dx, WORD dy, WORD mode, WORD ink, WORD bg)
{
    raster_1bpp(bits, stride, sx, sy, w, h, dx, dy, mode,
                (uint8_t)HW(ink), (uint8_t)HW(bg));
}

/* A diagonal: Bresenham, one pixel at a time through the MEMAC window, the
 * one primitive the blitter does not accelerate.  The pixel rules are
 * tools/vdiref.py's _paint_pixel: replace writes the pen where the style bit
 * is set and pen 0 where it is clear, transparent the pen where set, XOR the
 * complement where set, erase the pen where clear.  The style's bit 15 is
 * the first pixel and it rotates once per pixel, on and off the screen.
 *
 * Every mode is one read-modify-write, (byte & am) ^ xv, with am and xv
 * chosen by the style bit and the pixel's parity -- four entries -- and a
 * pixel a mode leaves alone is skipped before the window is touched.  The
 * stepper's state is in the direct page (see the raster section).  The
 * first version called paint_pixel(), plot(), plot_visible() and two VRAM
 * accessors per step, ~200 instructions; the second kept everything in
 * stack locals, ~150 (docs/phase8c.md). */
#define WIN ((volatile uint8_t *)MEMAC_WIN_ADDR)   /* the window, fixed  */

static TINY WORD  ld_x, ld_y, ld_i;
static TINY WORD  ld_dx, ld_dy, ld_ndy, ld_sx, ld_sy, ld_err;
static TINY UWORD ld_n;                /* pixels to go        */
static TINY UWORD ld_m;                /* the style, rotating */
static TINY UWORD ld_cx0, ld_cy0, ld_cw, ld_ch;
static TINY UWORD ld_page;             /* the 4K page mapped  */
static TINY UWORD ld_rpage;            /* the row's page ...  */
static TINY WORD  ld_roff, ld_rstep;   /* ... and offset in it */
static TINY UWORD ld_off, ld_pg;
static TINY UWORD ld_inside;           /* no pixel needs the */
                                                        /* clip test          */
static TINY uint8_t ld_a, ld_v;
static uint8_t ld_am[4], ld_xv[4], ld_skip[4];  /* [style bit << 1 | x & 1] */
                                /* not tiny: cc65816 5.18 dies on an indexed  */
                                /* direct-page array (docs/phase8c.md)        */

void dev_line_diag(WORD x1, WORD y1, WORD x2, WORD y2, UWORD mask)
{
    WORD cx0 = 0, cy0 = 0, cx1 = SCR_W - 1, cy1 = SCR_H - 1;
    WORD lo, hi, i;
    uint8_t pen = (uint8_t)HW(vwk.line_color), pen0 = (uint8_t)HW(0);

    if (vwk.clip) {
        if (cx0 < vwk.xmn_clip) cx0 = vwk.xmn_clip;
        if (cy0 < vwk.ymn_clip) cy0 = vwk.ymn_clip;
        if (cx1 > vwk.xmx_clip) cx1 = vwk.xmx_clip;
        if (cy1 > vwk.ymx_clip) cy1 = vwk.ymx_clip;
    }
    if (cx1 < cx0 || cy1 < cy0)
        return;
    /* a line whose box misses the clip has no pixel to plot */
    lo = x1; hi = x2; order(&lo, &hi);
    if (hi < cx0 || lo > cx1)
        return;
    lo = y1; hi = y2; order(&lo, &hi);
    if (hi < cy0 || lo > cy1)
        return;
    ld_cx0 = (UWORD)cx0;  ld_cw = (UWORD)(cx1 - cx0);
    ld_cy0 = (UWORD)cy0;  ld_ch = (UWORD)(cy1 - cy0);
    /* both ends inside the clip: so is every pixel between them */
    ld_inside = (UWORD)(x1 >= cx0 && x1 <= cx1 && x2 >= cx0 && x2 <= cx1 &&
                        y1 >= cy0 && y1 <= cy1 && y2 >= cy0 && y2 <= cy1);

    /* the four (style bit, parity) cases: what the byte keeps, what flips */
    for (i = 0; i < 4; i++) {
        WORD set = (WORD)(i & 2), odd = (WORD)(i & 1);
        uint8_t keep = (uint8_t)(odd ? 0xF0 : 0x0F);   /* the other pixel */
        uint8_t am = 0xFF, xv = 0;
        switch (vwk.wrt_mode + 1) {
        case MD_TRANS:
            if (set) { am = keep; xv = pen; }
            break;
        case MD_XOR:
            if (set) xv = 0xF;
            break;
        case MD_ERASE:
            if (!set) { am = keep; xv = pen; }
            break;
        default:
            am = keep; xv = set ? pen : pen0;
            break;
        }
        ld_am[i] = am;
        ld_xv[i] = (uint8_t)(odd ? xv : (xv << 4));
        ld_skip[i] = (uint8_t)(am == 0xFF && xv == 0);
    }

    ld_x = x1;  ld_y = y1;
    ld_dx = (WORD)(x2 - x1); if (ld_dx < 0) ld_dx = (WORD)-ld_dx;
    ld_dy = (WORD)(y2 - y1); if (ld_dy < 0) ld_dy = (WORD)-ld_dy;
    ld_ndy = (WORD)-ld_dy;
    ld_sx = (WORD)(x1 < x2 ? 1 : -1);
    ld_sy = (WORD)(y1 < y2 ? 1 : -1);
    ld_err = (WORD)(ld_dx - ld_dy);
    /* Bresenham steps the major axis every time, so the pixel count is
     * known: no endpoint compare in the loop */
    ld_n = (UWORD)((ld_dx > ld_dy ? ld_dx : ld_dy) + 1);
    ld_m = mask;
    ld_page = 0xFFFF;
    /* The row address as a 4K page and an offset in it, so that a step is
     * 16-bit arithmetic with a carry test.  y1 may be negative here: the
     * page is then negative too, and counts back up onto the screen. */
    {
        int32_t row = (int32_t)VR_SCREEN0 + (int32_t)y1 * (int32_t)SCR_STRIDE;
        ld_rpage = (UWORD)(row >> 12);
        ld_roff  = (WORD)(row & 0x0FFF);
    }
    ld_rstep = (WORD)(ld_sy > 0 ? SCR_STRIDE : -SCR_STRIDE);
    for (;;) {
        WORD e2;
        if (ld_m != 0xFFFF)     /* a solid style rotates into itself */
            ld_m = (UWORD)((ld_m << 1) | (ld_m >> 15));
        ld_i = (WORD)(((ld_m & 1) << 1) | (ld_x & 1));
        if (!ld_skip[ld_i] &&
            (ld_inside || ((UWORD)(ld_x - ld_cx0) <= ld_cw &&
                           (UWORD)(ld_y - ld_cy0) <= ld_ch))) {
            ld_off = (UWORD)(ld_roff + ((UWORD)ld_x >> 1));
            ld_pg  = ld_rpage;
            if (ld_off >= 0x1000) {
                ld_off -= 0x1000;
                ld_pg++;
            }
            if (ld_pg != ld_page) {
                ld_page = ld_pg;
                vram_map_page((uint8_t)ld_pg);
            }
            ld_a = ld_am[ld_i];
            ld_v = ld_xv[ld_i];
            WIN[ld_off] = (uint8_t)((WIN[ld_off] & ld_a) ^ ld_v);
        }
        if (--ld_n == 0)
            break;
        e2 = (WORD)(ld_err << 1);
        if (e2 > ld_ndy) { ld_err = (WORD)(ld_err - ld_dy); ld_x = (WORD)(ld_x + ld_sx); }
        if (e2 <  ld_dx) {
            ld_err = (WORD)(ld_err + ld_dx);
            ld_y = (WORD)(ld_y + ld_sy);
            ld_roff = (WORD)(ld_roff + ld_rstep);
            if ((UWORD)ld_roff >= 0x1000) {      /* crossed a page, either way */
                if (ld_roff < 0) { ld_roff += 0x1000; ld_rpage--; }
                else             { ld_roff -= 0x1000; ld_rpage++; }
            }
        }
    }
}


/* Row y of a form: y * stride for a form whose stride is anything -- an
 * off-screen MFDB's, not the screen's -- as shifts and adds over the bits
 * of y, which is a row count and never large, instead of the 32-bit
 * multiply the compiler made of it (see scr_row).  y is inside the form,
 * so it is not negative. */
static uint32_t form_row(WORD y, WORD stride)
{
    uint32_t s = (uint32_t)(uint16_t)stride, r = 0;
    uint16_t a = (uint16_t)y;

    while (a) {
        if (a & 1)
            r += s;
        s <<= 1;
        a = (uint16_t)(a >> 1);
    }
    return r;
}

/* One pixel into a form, already known to be inside it. */
static void rform_plot(const RFORM *f, WORD x, WORD y, WORD hwpen)
{
    uint32_t a = f->base + form_row(y, f->stride) + (uint32_t)(x >> 1);
    uint8_t  b = vram_read8(a);
    if (x & 1)
        b = (uint8_t)((b & 0xF0) | (hwpen & 0x0F));
    else
        b = (uint8_t)((b & 0x0F) | ((hwpen & 0x0F) << 4));
    vram_write8(a, b);
}


void dev_save_form(MFDB *m)
{
    m->fd_addr = VR_SAVE;
    m->fd_w = SCR_W;
    m->fd_h = vdev->h;          /* the screen, not the buffer */
    m->fd_wdwidth = SCR_W / 16;
    m->fd_stand = 0;
    m->fd_nplanes = 4;
    m->fd_r1 = m->fd_r2 = m->fd_r3 = 0;
}

/* The screen, as a form. */
void dev_screen_form(RFORM *f)
{
    f->base = VR_SCREEN0;  f->stride = SCR_STRIDE;
    f->w = SCR_W;  f->h = vdev->h;  f->screen = 1;
}

/* One blit when both ends share their alignment and the width is a whole
 * number of bytes; otherwise pixel by pixel through the window, in the
 * direction that keeps an overlapping move safe.  The blitter has no
 * shifter, which is why the fast path is so particular -- and why a
 * window that moves by an EVEN number of pixels stays on it. */
void dev_copy_form(const RFORM *src, WORD sx1, WORD sy1,
                   const RFORM *dst, WORD dx1, WORD dy1, WORD w, WORD h)
{
    WORD y;

    if (((sx1 ^ dx1) & 1) == 0 && (sx1 & 1) == 0 && (w & 1) == 0) {
        blit_move(src->base + form_row(sy1, src->stride) + (uint32_t)(sx1 >> 1),
                  src->stride,
                  dst->base + form_row(dy1, dst->stride) + (uint32_t)(dx1 >> 1),
                  dst->stride,
                  (uint16_t)(w >> 1), (uint16_t)h);
        return;
    }
    for (y = 0; y < h; y++) {
        WORD sy = (dy1 > sy1) ? (WORD)(sy1 + h - 1 - y) : (WORD)(sy1 + y);
        WORD dy = (dy1 > sy1) ? (WORD)(dy1 + h - 1 - y) : (WORD)(dy1 + y);
        WORD i;
        for (i = 0; i < w; i++) {
            WORD sx = (dx1 > sx1) ? (WORD)(sx1 + w - 1 - i) : (WORD)(sx1 + i);
            WORD dx = (dx1 > sx1) ? (WORD)(dx1 + w - 1 - i) : (WORD)(dx1 + i);
            uint32_t a = src->base + form_row(sy, src->stride) + (uint32_t)(sx >> 1);
            uint8_t  v = vram_read8(a);
            rform_plot(dst, dx, dy, (WORD)((sx & 1) ? (v & 0x0F) : (v >> 4)));
        }
    }
}

/* VDI pen -> hardware pen.
 *
 * GEM numbers its pens white=0, black=1, red=2 ... but XOR mode complements
 * the pixel's BITS, and the AES relies on that complement turning black into
 * white and back (a selected button is drawn by XORing its rectangle).  That
 * only holds if black and white are bitwise complements in the hardware, so
 * the VDI keeps GEM's pen numbers at its interface and stores every pixel
 * through this map -- the same permutation the ST's VDI applies -- with the
 * palette loaded in hardware order to match.  black -> 15, white -> 0. */
const uint8_t map_col[16] = {
    0, 15, 1, 2, 4, 6, 3, 5, 7, 8, 9, 10, 12, 14, 11, 13
};


#define HW(pen) ((WORD)map_col[(pen) & 0x0F])

/* And back: the VDI pen that maps to a hardware index.  A search, not a
 * second table -- it is wanted once per v_get_pixel and nowhere hot. */
static WORD rev_col(WORD hw)
{
    WORD i;
    for (i = 0; i < 16; i++)
        if (map_col[i] == (uint8_t)hw)
            return i;
    return 0;
}

void dev_read_row(WORD y, uint8_t *px)
{
    uint32_t base = VR_SCREEN0 + scr_row(y);
    WORD i = 0;

    while (i < SCR_STRIDE) {
        volatile uint8_t *w = vram_win(base + (uint32_t)i);
        WORD room = (WORD)(0x1000 - (WORD)((base + (uint32_t)i) & 0x0FFF));
        WORD k = (WORD)(SCR_STRIDE - i), j;

        if (k > room)
            k = room;
        for (j = 0; j < k; j++)
            px[i + j] = w[j];
        i = (WORD)(i + k);
    }
}

/* Two pixels share a byte, high nibble the LEFT one. */
WORD dev_row_pixel(const uint8_t *px, WORD x)
{
    uint8_t b = px[(UWORD)x >> 1];      /* unsigned: see asr() */
    return (WORD)((x & 1) ? (b & 0x0F) : (b >> 4));
}

WORD dev_pen_value(WORD pen)
{
    return HW(pen);
}

void dev_get_pixel(WORD x, WORD y, WORD *value, WORD *pen)
{
    uint8_t b = vram_read8(VR_SCREEN0 + scr_row(y)
                           + (uint32_t)((UWORD)x >> 1));
    WORD hw = (WORD)((x & 1) ? (b & 0x0F) : (b >> 4));

    *value = hw;
    *pen = rev_col(hw);
}

void dev_clear_screen(void)
{
    blit_fill(VR_SCREEN0, SCR_STRIDE, SCR_STRIDE, vdev->h, 0x00);
    blit_run();
}

/* The palette in HARDWARE order: entry map_col[pen] gets pen's colour. */
void dev_palette_all(const uint8_t *rgb)
{
    uint8_t hw[16 * 3];
    WORD pen;

    for (pen = 0; pen < 16; pen++) {
        WORD h = map_col[pen];
        hw[h * 3]     = rgb[pen * 3];
        hw[h * 3 + 1] = rgb[pen * 3 + 1];
        hw[h * 3 + 2] = rgb[pen * 3 + 2];
    }
    vbxe_palette(1, 0, hw, 16);
}

void dev_palette_one(WORD pen, const uint8_t *rgb)
{
    vbxe_palette(1, (uint8_t)HW(pen), rgb, 1);
}

WORD dev_colours(void)
{
    return 16;                          /* HR is 4bpp */
}

WORD dev_planes(void)
{
    return 4;
}

/* ---- the table (vdidev.h) --------------------------------------------
 * What the VDI reaches this file through.  The geometry and the font
 * metrics are constants HERE and variables above the seam, which is the
 * whole trade: this file may fold them, and vdi.c may be compiled once
 * for both screens.
 */
extern const uint8_t FAR font8x8[];

/* THE DEVICE, three times over, differing only in how many lines it
 * shows.  The height cannot simply be a variable: this table is
 * `const ... FAR` and so lives in `cfar` (src/gem4xe.scm), and dropping
 * the const would move a hundred-odd bytes of it into bank $00 -- which
 * has single figures to spare (tools/memreport.py).  Three tables in far
 * const cost nothing there.
 *
 * THE FRAMEBUFFER IS 240 LINES WHICHEVER IS CHOSEN.  Only what the XDL
 * displays and what the seam reports change, so the VRAM map does not
 * move and a shorter screen simply leaves the rows below it unshown --
 * which is also why the clipping inside this file may go on using the
 * compile-time SCR_H: it is the BUFFER's bound, a safe superset of the
 * screen's, and everything above the seam has already clipped to
 * vdev->h. */
#define VBXE_DEV(ww, hh) {                                                \
    (ww), (hh), (ww) / 2,       /* HR is 4bpp: two pixels to the byte */  \
    FONT_W, FONT_H,                                                       \
    FONT_TOP, FONT_ASCENT, FONT_HALF, FONT_DESCENT, FONT_BOTTOM,          \
    FONT_POINT, font8x8,                                                  \
                                                                          \
    dev_fill_rect,                                                        \
    dev_xor_rect,                                                         \
    dev_patt_rect,                                                        \
    dev_style_line,                                                       \
    dev_glyph,                                                            \
    dev_font_changed,                                                     \
    dev_raster_1bpp,                                                      \
    dev_cursor_form,                                                      \
    dev_cursor_show,                                                      \
    dev_cursor_hide,                                                      \
    dev_cursor_discard,                                                   \
    dev_line_diag,                                                        \
    dev_screen_form,                                                      \
    dev_copy_form,                                                        \
    dev_save_form,                                                        \
    dev_clear_screen,                                                     \
    dev_get_pixel,                                                        \
    dev_pen_value,                                                        \
    dev_read_row,                                                         \
    dev_row_pixel,                                                        \
    dev_colours,                                                          \
    dev_planes,                                                           \
    dev_palette_all,                                                      \
    dev_palette_one,                                                      \
    dev_invalidate,                                                       \
    dev_flush,                                                            \
    1,                  /* text_prefill: a string's background is one fill */ \
}

/* Every width the overlay has by every height a tube might want, which
 * is nine tables of about 130 bytes in `cfar` -- far, banked, and next
 * to the code that reads them.  A table per combination rather than a
 * mutable one in bank $00: the seam's whole argument is that `vdev` is
 * a CONST far pointer set once, so there is no second copy of the
 * screen's shape to disagree with the first (src/vdi/vdidev.h).
 *
 * The widths are the hardware's three, measured: the overlay occupies
 * 128, 160 or 168 colour clocks and HR puts four pixels in each
 * (src/vbxe/vbxe.h).  The heights are what GEM4XE.CFG's SCREENH has
 * always offered -- the BUFFER is VB_H lines whatever is shown, so only
 * the XDL and what this reports change. */
#define VBXE_DEVS(ww)  { VBXE_DEV(ww, VB_H), VBXE_DEV(ww, 224), VBXE_DEV(ww, 200) }
const VDIDEV FAR vdev_vbxe_tab[VB_WIDTHS][VB_HEIGHTS] = {
    VBXE_DEVS(VB_W_NARROW),
    VBXE_DEVS(VB_W_NORMAL),
    VBXE_DEVS(VB_W_WIDE),
};
/* The one a runner that does not care means: the screen as it has always
 * been, 640 by 240. */
const VDIDEV FAR *const vdev_vbxe = &vdev_vbxe_tab[VB_WIDE_NORMAL][0];
