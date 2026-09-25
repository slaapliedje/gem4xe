/* antic.c -- the ANTIC mode F surface.  See antic.h for the map and for
 * why the framebuffer is where it is.
 *
 * Everything here is CPU work.  There is no blitter on this side of the
 * seam, which is the whole difference between the two drivers.
 *
 * AND THE SCREEN IS NOT FAST.  This file used to say the framebuffer is
 * "plain motherboard RAM the accelerator reaches at full speed".  It is
 * motherboard RAM, at $8100-$9B3F, in the Rapidus's window 2 -- which
 * rapidus_speedup() keeps on the 1.79 MHz bus always, because the VBXE's
 * MEMAC window is in it on the other device.  So every read and write of
 * a screen byte here is a slow-bus cycle however fast the CPU is, and the
 * rule for everything below is: touch each screen byte ONCE, work out what
 * goes in it in fast memory first, and do not read what a write is about
 * to cover (docs/phase52.md, which measured it).
 */
#include "portab.h"
#include "antic.h"

/* Character N's row r of a face.  The strip is one byte per character
 * per row, 256 of them, the glyph LEFT-ALIGNED in its byte -- which is
 * the layout every face gem4xe links is repacked into, whatever the
 * donor's packing was.  WHICH face is the caller's business: this file
 * used to reach for font8x8 itself, and then quietly went on drawing it
 * after the VDI had been told to use the condensed one. */
#define AN_FONT_STRIDE 256

/* The ADDRESS is a uint32_t and the arithmetic is done on it BEFORE the
 * cast, which is not a style choice: a far pointer indexed by a computed
 * subscript does not survive cc65816 5.18, and the same idiom is what
 * vdi_font_expand and draw_glyph_cpu use on the other device. */
static uint8_t an_font_row(uint32_t face, uint16_t ch, uint16_t row)
{
    const uint8_t FAR *sr =
        (const uint8_t FAR *)(face + (uint32_t)row * AN_FONT_STRIDE);
    return sr[ch & 0xFF];
}

#define REG8(a)  (*(volatile uint8_t *)(a))
#define SCREEN   ((volatile uint8_t *)AN_SCREEN)

/* ANTIC's instruction bytes. */
#define AN_MODE_F   0x0F
#define AN_LMS      0x40
#define AN_JVB      0x41
#define AN_BLANK8   0x70                /* eight blank scan lines */

/* The masks a run's first and last byte are painted through: bit 7 is
 * the LEFTMOST pixel of a byte, which is the one thing about a 1bpp
 * Atari screen that catches everyone once. */
static const uint8_t an_left[8] = {
    0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01
};
static const uint8_t an_right[8] = {
    0x80, 0xC0, 0xE0, 0xF0, 0xF8, 0xFC, 0xFE, 0xFF
};

void antic_init(uint8_t fg, uint8_t bg)
{
    volatile uint8_t *d = (volatile uint8_t *)AN_DLIST;
    uint16_t i;

    /* The screen off while the list is built: ANTIC reads the list as it
     * goes, and a half-written one is a machine that fetches instructions
     * from whatever was there. */
    REG8(AN_DMACTL) = 0;
    REG8(AN_SDMCTL) = 0;

    /* Three blank rows are the OS's own convention for the top of a
     * display list, and they are what puts the first drawn line at scan
     * line 8. */
    *d++ = AN_BLANK8;
    *d++ = AN_BLANK8;
    *d++ = AN_BLANK8;

    *d++ = AN_MODE_F | AN_LMS;              /* line 0, from the base */
    *d++ = (uint8_t)AN_SCREEN;
    *d++ = (uint8_t)(AN_SCREEN >> 8);
    for (i = 1; i < AN_SPLIT; i++)
        *d++ = AN_MODE_F;
    /* ...and again at the line the 4 KB crossing falls in front of, at
     * exactly the address the linear formula gives (antic.h). */
    *d++ = AN_MODE_F | AN_LMS;
    *d++ = (uint8_t)(AN_SCREEN + AN_SPLIT * AN_STRIDE);
    *d++ = (uint8_t)((AN_SCREEN + AN_SPLIT * AN_STRIDE) >> 8);
    for (i = AN_SPLIT + 1; i < AN_H; i++)
        *d++ = AN_MODE_F;

    *d++ = AN_JVB;
    *d++ = (uint8_t)AN_DLIST;
    *d++ = (uint8_t)(AN_DLIST >> 8);

    REG8(AN_COLPF1) = fg;
    REG8(AN_COLPF2) = bg;
    REG8(AN_COLBK)  = bg;
    REG8(AN_COLOR1) = fg;
    REG8(AN_COLOR2) = bg;
    REG8(AN_COLOR4) = bg;

    /* GTIA'S MODE BITS, CLEARED.  ANTIC mode F is hi-res only while the
     * top two bits of PRIOR are 00: with either set the SAME bytes are
     * read as GTIA mode 9, 10 or 11 -- and mode 11 is sixteen HUES, which
     * is exactly what "colour bars where the desktop should be" looks
     * like on a machine where something before us left them set.  Nothing
     * here uses players, so the rest of the register is left as found.
     * The shadow as well as the register, because the OS VBI copies the
     * shadow over it every frame and would put the bits straight back. */
    REG8(AN_GPRIOR) = (uint8_t)(REG8(AN_GPRIOR) & 0x3F);
    REG8(AN_PRIOR)  = REG8(AN_GPRIOR);

    REG8(AN_DLISTL)     = (uint8_t)AN_DLIST;
    REG8(AN_DLISTL + 1) = (uint8_t)(AN_DLIST >> 8);
    REG8(AN_SDLSTL)     = (uint8_t)AN_DLIST;
    REG8(AN_SDLSTL + 1) = (uint8_t)(AN_DLIST >> 8);

    antic_clear(0);
    REG8(AN_DMACTL) = 0x22;                 /* list DMA + normal playfield */
    REG8(AN_SDMCTL) = 0x22;
}

void antic_recolour(int16_t pen, uint8_t value)
{
    if (pen) {
        REG8(AN_COLPF1) = value;
        REG8(AN_COLOR1) = value;
    } else {
        REG8(AN_COLPF2) = value;
        REG8(AN_COLBK)  = value;
        REG8(AN_COLOR2) = value;
        REG8(AN_COLOR4) = value;
    }
}

void antic_off(void)
{
    REG8(AN_DMACTL) = 0;
    REG8(AN_SDMCTL) = 0;
}

/* The shadow is what is kept, not the register: DOS runs with the OS VBI
 * on, and the VBI writes the shadow to DMACTL every frame, so the shadow
 * is what DOS will see again -- and the register is written too, for
 * the frames until then.  Measured in docs/bench.md: the September 2
 * figures were taken with the OS's display list under the runner's
 * buffers, which is this switch thrown by accident; with the list intact
 * every VRAM-bound row ran a quarter slower, and this is the remedy. */
static uint8_t an_saved_dmactl;

void antic_suspend(void)
{
    an_saved_dmactl = REG8(AN_SDMCTL);
    REG8(AN_DMACTL) = 0;
    REG8(AN_SDMCTL) = 0;
}

void antic_resume(void)
{
    REG8(AN_SDMCTL) = an_saved_dmactl;
    REG8(AN_DMACTL) = an_saved_dmactl;
}

void antic_clear(uint8_t value)
{
    volatile uint8_t *p = SCREEN;
    uint16_t n = AN_BYTES;

    while (n--)
        *p++ = value;
}

/* The byte a pixel is in.  The shift is UNSIGNED for the reason
 * tools/ccbug rule 12 gives -- cc65816 5.18 mangles a signed 16-bit
 * right shift -- and the caller has already established that x is not
 * negative.  With the signed shift the diagonal in test-m24 was drawn
 * correctly to x=31 and then eight bytes short of where it belonged for
 * every pixel after it, which is what a sign that appears at 32 looks
 * like from the outside. */
static volatile uint8_t *an_at(int16_t x, int16_t y)
{
    return SCREEN + (uint16_t)y * AN_STRIDE + ((uint16_t)x >> 3);
}

void antic_plot(int16_t x, int16_t y, uint8_t set)
{
    volatile uint8_t *p;
    uint8_t bit, v;

    if (x < 0 || y < 0 || x >= AN_W || y >= AN_H)
        return;
    p = an_at(x, y);
    bit = (uint8_t)(0x80 >> (x & 7));
    v = *p;                                 /* ccbug rule 3: the byte comes
                                             * out, is decided, and goes back;
                                             * never *p = c ? a : b */
    v = set ? (uint8_t)(v | bit) : (uint8_t)(v & (uint8_t)~bit);
    *p = v;
}

/* One run.  The whole bytes in the middle are written outright and only
 * the two ends are read-modify-write, which is the difference between a
 * span and a string of plots. */
void antic_hline(int16_t x1, int16_t x2, int16_t y, uint8_t set)
{
    volatile uint8_t *p;
    uint8_t lm, rm, fill, v;
    int16_t b1, b2, b;

    if (y < 0 || y >= AN_H)
        return;
    if (x1 > x2) {
        int16_t t = x1; x1 = x2; x2 = t;
    }
    if (x2 < 0 || x1 >= AN_W)
        return;
    if (x1 < 0)
        x1 = 0;
    if (x2 >= AN_W)
        x2 = AN_W - 1;

    /* ccbug rule 12: never right-shift a signed 16-bit value.  Both are
     * non-negative by now, so an unsigned copy is the shift to make. */
    b1 = (int16_t)((uint16_t)x1 >> 3);
    b2 = (int16_t)((uint16_t)x2 >> 3);
    lm = an_left[x1 & 7];
    rm = an_right[x2 & 7];
    fill = set ? 0xFF : 0x00;               /* decided once, not per byte */
    p = SCREEN + (uint16_t)y * AN_STRIDE + (uint16_t)b1;

    if (b1 == b2) {                         /* one byte, both ends in it */
        uint8_t m = (uint8_t)(lm & rm);
        v = *p;
        v = set ? (uint8_t)(v | m) : (uint8_t)(v & (uint8_t)~m);
        *p = v;
        return;
    }
    v = *p;
    v = set ? (uint8_t)(v | lm) : (uint8_t)(v & (uint8_t)~lm);
    *p = v;
    /* THE MIDDLE, and the shape it is written in is not a preference.
     * `*p++ = set ? 0xFF : 0x00;` -- the obvious line -- breaks two of
     * the standing rules at once (tools/ccbug: never store a conditional
     * through a pointer, never increment a pointer in the expression
     * that uses it), and cc65816 5.18 miscompiles it in a way no amount
     * of staring at one iteration reveals: the loop runs ONCE for any
     * count above two and then leaves the function, so the run's right
     * edge is never drawn either.  Two middle bytes work and eight do
     * not, which is exactly the kind of thing that would have shipped.
     * Hoisting the constant out and separating the increment from the
     * store fixes it and is better code besides. */
    for (b = (int16_t)(b1 + 1); b < b2; b++) {
        p++;
        *p = fill;
    }
    p++;
    v = *p;
    v = set ? (uint8_t)(v | rm) : (uint8_t)(v & (uint8_t)~rm);
    *p = v;
}

void antic_rect(int16_t x1, int16_t y1, int16_t x2, int16_t y2, uint8_t set)
{
    int16_t y;

    if (y1 > y2) {
        y = y1; y1 = y2; y2 = y;
    }
    if (y1 < 0)
        y1 = 0;
    if (y2 >= AN_H)
        y2 = AN_H - 1;
    for (y = y1; y <= y2; y++)
        antic_hline(x1, x2, y, set);
}

/* ---- the writing modes ------------------------------------------------ */

/* One destination byte: the source applied through mask `m` in `mode`,
 * everything outside the mask left alone.  The VDI's modes are numbered
 * from 1 (src/vdi/vdi.h), which is what the caller passes. */
#define AN_MD_REPLACE 1
#define AN_MD_TRANS   2
#define AN_MD_XOR     3
#define AN_MD_ERASE   4

/* A WRITING MODE AS FOUR BYTES, worked out once per call rather than
 * switched on per byte.  Each mode says what a SET source bit does to the
 * pixel under it and what a CLEAR one does, and each of those is one of
 * four things -- paint 0, paint 1, leave it, invert it -- which are all
 * `(d & X) ^ Y` for some X and Y:
 *
 *              set bit        clear bit
 *   replace    the "on" pen   the "off" pen
 *   trans      the "on" pen   leave
 *   XOR        invert         leave
 *   erase      leave          the "off" pen
 *
 * So a byte is  (s & ((d & x1) ^ y1)) | (~s & ((d & x0) ^ y0)),  masked,
 * with no branch and no call.  And when both X are zero the destination
 * does not come into it: a byte the mask covers whole is only WRITTEN,
 * which on this screen means one access on the 1.79 MHz bus instead of
 * two (docs/phase52.md).  The "off" pen is the background in a raster and
 * in replace, and the ink in erase -- the VDI's rules, as an_apply had
 * them. */
typedef struct {
    uint8_t x1, y1, x0, y0;
} AN_OP;

static void an_op(AN_OP *o, int16_t mode, uint8_t on, uint8_t off)
{
    uint8_t onb = on ? 0xFF : 0x00;
    uint8_t offb = off ? 0xFF : 0x00;

    switch (mode) {
    case AN_MD_TRANS:
        o->x1 = 0x00; o->y1 = onb;  o->x0 = 0xFF; o->y0 = 0x00;
        break;
    case AN_MD_XOR:
        o->x1 = 0xFF; o->y1 = 0xFF; o->x0 = 0xFF; o->y0 = 0x00;
        break;
    case AN_MD_ERASE:
        o->x1 = 0xFF; o->y1 = 0x00; o->x0 = 0x00; o->y0 = offb;
        break;
    default:                                /* AN_MD_REPLACE */
        o->x1 = 0x00; o->y1 = onb;  o->x0 = 0x00; o->y0 = offb;
        break;
    }
}

/* One byte through the op: d the destination, s the source, m the pixels
 * that are this call's.  A macro and not a function, because it is the
 * inner loop of every primitive below. */
#define AN_MIX(o, d, s, m) \
    ((uint8_t)(((d) & (uint8_t)~(m)) | ((m) & \
      (uint8_t)(((s) & (uint8_t)(((d) & (o).x1) ^ (o).y1)) | \
                ((uint8_t)~(s) & (uint8_t)(((d) & (o).x0) ^ (o).y0))))))

/* Does this op need the destination at all? */
#define AN_READS(o) ((o).x1 | (o).x0)

/* an_apply's pens: the "off" colour is the other pen in replace and the
 * ink in erase, which is how the solid and patterned primitives, the
 * glyphs and the lines have always drawn. */
static void an_op_pen(AN_OP *o, int16_t mode, uint8_t pen)
{
    an_op(o, mode, pen, (uint8_t)(mode == AN_MD_REPLACE ? !pen : pen));
}

/* One screen byte through the op, reading it only if it must.  A MACRO:
 * as a function it was a third of all the work a window redraw did on
 * this device, most of it the call (docs/phase52.md).  `d_` is the
 * caller's scratch byte; the store is of a value computed first, never of
 * an expression through the pointer (tools/ccbug rule 3). */
#define AN_PUT(p, o, s, m, d_)                                  \
    do {                                                        \
        (d_) = 0;                                               \
        if ((uint8_t)(m) != 0xFF || AN_READS(o))                \
            (d_) = *(p);                                        \
        (d_) = AN_MIX(o, (d_), (uint8_t)(s), (uint8_t)(m));     \
        *(p) = (d_);                                            \
    } while (0)

/* A solid run: the source is all ones, so REPLACE and TRANS write the
 * pen, XOR inverts and ERASE does nothing. */
void antic_span(int16_t x1, int16_t x2, int16_t y, int16_t mode, uint8_t pen)
{
    uint8_t t;                          /* AN_PUT's scratch */
    volatile uint8_t *p;
    AN_OP o;
    uint8_t lm, rm;
    int16_t b1, b2, b;

    if (y < 0 || y >= AN_H)
        return;
    if (x1 > x2) {
        int16_t t = x1; x1 = x2; x2 = t;
    }
    if (x2 < 0 || x1 >= AN_W)
        return;
    if (x1 < 0)
        x1 = 0;
    if (x2 >= AN_W)
        x2 = AN_W - 1;

    an_op_pen(&o, mode, pen);
    b1 = (int16_t)((uint16_t)x1 >> 3);
    b2 = (int16_t)((uint16_t)x2 >> 3);
    lm = an_left[x1 & 7];
    rm = an_right[x2 & 7];
    p = SCREEN + (uint16_t)y * AN_STRIDE + (uint16_t)b1;

    if (b1 == b2) {
        AN_PUT(p, o, 0xFF, (uint8_t)(lm & rm), t);
        return;
    }
    AN_PUT(p, o, 0xFF, lm, t);
    if (mode != AN_MD_ERASE) {          /* erase with a solid source: no-op */
        for (b = (int16_t)(b1 + 1); b < b2; b++) {
            p++;
            AN_PUT(p, o, 0xFF, 0xFF, t);
        }
    } else {
        p += b2 - b1 - 1;
    }
    p++;
    AN_PUT(p, o, 0xFF, rm, t);
}

void antic_rect_mode(int16_t x1, int16_t y1, int16_t x2, int16_t y2,
                     int16_t mode, uint8_t pen)
{
    int16_t y;

    if (y1 > y2) {
        y = y1; y1 = y2; y2 = y;
    }
    if (y1 < 0)
        y1 = 0;
    if (y2 >= AN_H)
        y2 = AN_H - 1;
    for (y = y1; y <= y2; y++)
        antic_span(x1, x2, y, mode, pen);
}

/* ---- text -------------------------------------------------------------
 * The font is a 1bpp strip already (src/vdi/vdi.h): character N's row r
 * is font8x8[r * FONT_STRIDE + N], bit 7 leftmost.  So a glyph goes into
 * a 1bpp framebuffer as itself, shifted into place across at most two
 * bytes -- no expansion, no second pre-shifted copy, none of what the
 * VBXE driver keeps in VRAM to blit the same glyph at an odd x.
 *
 * A cell that runs off an edge is dropped whole rather than clipped:
 * the VDI clips text by the cell, and a partial glyph is not something
 * GEM asks for. */
void antic_glyph(uint32_t face, uint16_t ch, int16_t x, int16_t y,
                 int16_t mode, uint8_t pen, int16_t w, int16_t h)
{
    uint8_t t;                          /* AN_PUT's scratch */
    volatile uint8_t *p;
    AN_OP o;
    uint16_t row;
    uint8_t shift, g, cell, mh, ml;

    if (w < 1 || w > 8)
        return;
    cell = (uint8_t)(0xFF << (8 - w));  /* the columns the face uses */
    if (x < 0 || y < 0 || x + w > AN_W || y + h > AN_H)
        return;
    an_op_pen(&o, mode, pen);
    shift = (uint8_t)(x & 7);
    mh = (uint8_t)(cell >> shift);
    ml = (uint8_t)(cell << (8 - shift));
    p = SCREEN + (uint16_t)y * AN_STRIDE + ((uint16_t)x >> 3);

    for (row = 0; row < (uint16_t)h; row++) {
        g = (uint8_t)(an_font_row(face, ch, row) & cell);
        if (shift == 0) {
            AN_PUT(p, o, g, cell, t);
        } else {
            AN_PUT(p, o, (uint8_t)(g >> shift), mh, t);
            AN_PUT(p + 1, o, (uint8_t)(g << (8 - shift)), ml, t);
        }
        p += AN_STRIDE;
    }
}

/* ---- rasters ---------------------------------------------------------- */

/* Eight source bits starting at bit `b` of `row`, bit 7 leftmost, the way
 * a screen byte holds them.  It may read one byte past the bits it uses,
 * which is a read and nothing else. */
static uint8_t an_src8(const uint8_t FAR *row, uint16_t b)
{
    uint16_t i = (uint16_t)(b >> 3);
    uint8_t sh = (uint8_t)(b & 7);
    uint8_t hi = row[i];
    uint8_t lo;

    if (sh == 0)
        return hi;
    lo = row[(uint16_t)(i + 1)];
    return (uint8_t)((uint8_t)(hi << sh) | (uint8_t)(lo >> (8 - sh)));
}

void antic_raster_row(const uint8_t FAR *row, uint16_t sbit,
                      int16_t x1, int16_t x2, int16_t y,
                      int16_t mode, uint8_t pen, uint8_t pap)
{
    uint8_t t;                          /* AN_PUT's scratch */
    volatile uint8_t *p;
    AN_OP o;
    uint16_t b1, b2, b, lead;

    if (x1 > x2)
        return;
    an_op(&o, mode, pen, pap);
    b1 = (uint16_t)x1 >> 3;
    b2 = (uint16_t)x2 >> 3;
    /* The source bit that lands on the FIRST pixel of byte b1, which is
     * `lead` pixels left of x1.  Those pixels are outside the mask, so
     * what the source holds for them does not matter -- but it cannot be
     * read from before the row starts, so it is shifted in as zeros. */
    lead = (uint16_t)x1 & 7;
    p = SCREEN + (uint16_t)y * AN_STRIDE + b1;
    for (b = b1; b <= b2; b++) {
        uint8_t m = 0xFF, src;

        if (b == b1)
            m = an_left[lead];
        if (b == b2)
            m = (uint8_t)(m & an_right[(uint16_t)x2 & 7]);
        if (b == b1 && lead)
            src = (uint8_t)(an_src8(row, sbit) >> lead);
        else
            src = an_src8(row, (uint16_t)(sbit + ((b - b1) << 3) - lead));
        AN_PUT(p, o, src, m, t);
        p++;
    }
}

uint8_t antic_get_pixel(int16_t x, int16_t y)
{
    volatile uint8_t *p;

    if (x < 0 || y < 0 || x >= AN_W || y >= AN_H)
        return 0;
    p = an_at(x, y);
    return (uint8_t)((*p >> (7 - (x & 7))) & 1);
}

/* ---- patterns, and the styled lines that are patterns ------------------ */

/* The byte of `patrow` that lands on screen byte `bx`: the pattern is
 * aligned to the screen's 16-pixel word, so an even byte takes the high
 * half and an odd byte the low one. */
static uint8_t an_patt_byte(uint16_t patrow, int16_t bx)
{
    return (uint8_t)((bx & 1) ? (patrow & 0xFF) : (patrow >> 8));
}

void antic_patt_span(int16_t x1, int16_t x2, int16_t y, uint16_t patrow,
                     int16_t mode, uint8_t pen)
{
    uint8_t t;                          /* AN_PUT's scratch */
    volatile uint8_t *p;
    AN_OP o;
    uint8_t lm, rm, ev, od;
    int16_t b1, b2, b;

    if (y < 0 || y >= AN_H)
        return;
    if (x1 > x2) {
        int16_t t = x1; x1 = x2; x2 = t;
    }
    if (x2 < 0 || x1 >= AN_W)
        return;
    if (x1 < 0)
        x1 = 0;
    if (x2 >= AN_W)
        x2 = AN_W - 1;

    an_op_pen(&o, mode, pen);
    ev = an_patt_byte(patrow, 0);       /* the even bytes' half */
    od = an_patt_byte(patrow, 1);       /* ...and the odd ones' */
    b1 = (int16_t)((uint16_t)x1 >> 3);
    b2 = (int16_t)((uint16_t)x2 >> 3);
    lm = an_left[x1 & 7];
    rm = an_right[x2 & 7];
    p = SCREEN + (uint16_t)y * AN_STRIDE + (uint16_t)b1;

    if (b1 == b2) {
        AN_PUT(p, o, (b1 & 1) ? od : ev, (uint8_t)(lm & rm), t);
        return;
    }
    AN_PUT(p, o, (b1 & 1) ? od : ev, lm, t);
    for (b = (int16_t)(b1 + 1); b < b2; b++) {
        p++;
        AN_PUT(p, o, (b & 1) ? od : ev, 0xFF, t);
    }
    p++;
    AN_PUT(p, o, (b2 & 1) ? od : ev, rm, t);
}

/* A vertical line, one screen byte a row.  It used to call the whole
 * patterned span for every pixel. */
void antic_vline(int16_t x, int16_t y1, int16_t y2, uint16_t mask,
                 int16_t mode, uint8_t pen)
{
    uint8_t t;                          /* AN_PUT's scratch */
    volatile uint8_t *p;
    AN_OP o;
    int16_t y;
    uint8_t m;

    if (x < 0 || x >= AN_W)
        return;
    if (y1 > y2) {
        y = y1; y1 = y2; y2 = y;
    }
    if (y1 < 0)
        y1 = 0;
    if (y2 >= AN_H)
        y2 = AN_H - 1;
    an_op_pen(&o, mode, pen);
    m = (uint8_t)(0x80 >> (x & 7));
    p = SCREEN + (uint16_t)y1 * AN_STRIDE + ((uint16_t)x >> 3);
    for (y = y1; y <= y2; y++) {
        /* the style is anchored to the screen's grid, as a horizontal
         * one is: pixel y takes bit 15 - (y & 15) */
        uint8_t bit = (uint8_t)((mask >> (15 - (y & 15))) & 1);
        AN_PUT(p, o, bit ? 0xFF : 0x00, m, t);
        p += AN_STRIDE;
    }
}

/* ---- vro_cpyfm, screen to screen -------------------------------------- */

/* A screen byte by row and column, or 0 off the screen.  A FUNCTION, and
 * that is not tidiness: written inline in antic_copy's row loop -- a
 * conditional volatile read, then the store into the row buffer -- cc65816
 * 5.18 at -O2 factored a `sep #32 / ldy ##0 / rtl` tail out of it and let
 * the read's path fall into the join with the accumulator still 8 bits
 * wide, where `adc ##33` (69 21 00) ran as `adc #$21` and then BRK.
 * test-m24 caught it as a program that never started drawing; the compiler's
 * simulator found the line (docs/phase52.md, tools/ccbug B21). */
static uint8_t an_byte_at(int16_t y, int16_t bx)
{
    volatile uint8_t *sp;

    if (y < 0 || y >= AN_H || bx < 0 || bx >= AN_STRIDE)
        return 0;
    sp = SCREEN + (uint16_t)y * AN_STRIDE + (uint16_t)bx;
    return *sp;
}

void antic_copy(int16_t sx, int16_t sy, int16_t dx, int16_t dy,
                int16_t w, int16_t h)
{
    int16_t y, i, n;
    int16_t back_y, back_x;

    if (w <= 0 || h <= 0)
        return;
    back_y = (int16_t)(dy > sy);            /* rows bottom-up */
    back_x = (int16_t)(dx > sx);            /* and right to left */

    if (((sx ^ dx) & 7) == 0 && (sx & 7) == 0 && (w & 7) == 0) {
        /* byte aligned at both ends and a whole number of bytes wide */
        n = (int16_t)((uint16_t)w >> 3);
        for (y = 0; y < h; y++) {
            int16_t syy = back_y ? (int16_t)(sy + h - 1 - y) : (int16_t)(sy + y);
            int16_t dyy = back_y ? (int16_t)(dy + h - 1 - y) : (int16_t)(dy + y);
            volatile uint8_t *s, *d;
            uint8_t v;

            if (syy < 0 || syy >= AN_H || dyy < 0 || dyy >= AN_H)
                continue;
            s = SCREEN + (uint16_t)syy * AN_STRIDE + ((uint16_t)sx >> 3);
            d = SCREEN + (uint16_t)dyy * AN_STRIDE + ((uint16_t)dx >> 3);
            if (back_x) {
                s += n - 1;
                d += n - 1;
                for (i = 0; i < n; i++) {
                    v = *s;
                    *d = v;
                    s--;
                    d--;
                }
            } else {
                for (i = 0; i < n; i++) {
                    v = *s;
                    *d = v;
                    s++;
                    d++;
                }
            }
        }
        return;
    }
    /* Unaligned, or a width that is not a whole number of bytes -- which on
     * this screen is most window moves, since a window snaps to EVEN x and
     * a byte is eight.  It used to go pixel by pixel, a get and a plot
     * each; a moved window was tens of thousands of them.  Now each source
     * row is read ONCE into a buffer, whole bytes, and put down shifted
     * with antic_raster_row, which is vrt_cpyfm's own path.  Reading the
     * row before writing any of it is also what makes an overlapping move
     * on the same row safe, whichever way it goes; the rows themselves are
     * still taken in the order that keeps a vertical overlap safe.
     * Pixels whose source is off the screen read as 0, as get_pixel's
     * did. */
    {
        uint8_t buf[AN_STRIDE + 2];
        int16_t xl = dx, xr = (int16_t)(dx + w - 1), k, sb;

        if (xl < 0)
            xl = 0;
        if (xr >= AN_W)
            xr = AN_W - 1;
        if (xl > xr)
            return;
        for (y = 0; y < h; y++) {
            int16_t syy = back_y ? (int16_t)(sy + h - 1 - y) : (int16_t)(sy + y);
            int16_t dyy = back_y ? (int16_t)(dy + h - 1 - y) : (int16_t)(dy + y);
            int16_t s0 = (int16_t)(sx + (xl - dx));     /* source x of xl */

            if (dyy < 0 || dyy >= AN_H)
                continue;
            /* the source row's bytes from the one holding s0 on, as many
             * as the run needs and one more; off-screen ones are 0.  The
             * byte column is floored, not truncated: s0 may be negative */
            sb = (int16_t)(s0 >= 0 ? (int16_t)((uint16_t)s0 >> 3)
                                   : (int16_t)(-1 - (int16_t)((uint16_t)(-1 - s0) >> 3)));
            n = (int16_t)((int16_t)((uint16_t)(xr - xl) >> 3) + 2);
            for (k = 0; k < n; k++) {
                uint8_t v = an_byte_at(syy, (int16_t)(sb + k));
                buf[k] = v;
            }
            antic_raster_row((const uint8_t FAR *)buf,
                             (uint16_t)(s0 - (int16_t)(sb * 8)),
                             xl, xr, dyy, AN_MD_REPLACE, 1, 0);
        }
    }
    (void)i;
    (void)back_x;
}

/* ---- the mouse cursor -------------------------------------------------- */

#define AN_CUR_W  16
#define AN_CUR_NB 3                     /* 16 pixels at any shift: 3 bytes */

static uint8_t an_cur_buf[AN_CUR_NB * AN_CUR_W];
static int16_t an_cur_bx, an_cur_y, an_cur_nb, an_cur_nr;
static uint8_t an_cur_valid;

void antic_cursor_save(int16_t x, int16_t y)
{
    int16_t bx0 = (int16_t)((uint16_t)(x < 0 ? 0 : x) >> 3);
    int16_t bx1 = (int16_t)((uint16_t)(x + AN_CUR_W - 1) >> 3);
    int16_t y0 = y, y1 = (int16_t)(y + AN_CUR_W - 1);
    int16_t r, c;

    an_cur_valid = 0;
    if (x >= AN_W || y >= AN_H || x + AN_CUR_W <= 0 || y + AN_CUR_W <= 0)
        return;
    if (bx1 > AN_STRIDE - 1)
        bx1 = AN_STRIDE - 1;
    if (y0 < 0)
        y0 = 0;
    if (y1 > AN_H - 1)
        y1 = AN_H - 1;
    if (bx1 < bx0 || y1 < y0)
        return;
    an_cur_bx = bx0;
    an_cur_y = y0;
    an_cur_nb = (int16_t)(bx1 - bx0 + 1);
    an_cur_nr = (int16_t)(y1 - y0 + 1);
    for (r = 0; r < an_cur_nr; r++) {
        volatile uint8_t *p = SCREEN + (uint16_t)(y0 + r) * AN_STRIDE
                              + (uint16_t)bx0;
        for (c = 0; c < an_cur_nb; c++) {
            uint8_t v = *p;
            an_cur_buf[r * AN_CUR_NB + c] = v;
            p++;
        }
    }
    an_cur_valid = 1;
}

void antic_cursor_restore(void)
{
    int16_t r, c;

    if (!an_cur_valid)
        return;
    for (r = 0; r < an_cur_nr; r++) {
        volatile uint8_t *p = SCREEN + (uint16_t)(an_cur_y + r) * AN_STRIDE
                              + (uint16_t)an_cur_bx;
        for (c = 0; c < an_cur_nb; c++) {
            uint8_t v = an_cur_buf[r * AN_CUR_NB + c];
            *p = v;
            p++;
        }
    }
    an_cur_valid = 0;
}

void antic_cursor_discard(void)
{
    an_cur_valid = 0;
}

/* The pointer, three bytes a row rather than a plot a pixel: the form is
 * shifted into the screen's alignment as a 24-bit row, and each screen
 * byte is read and written once.  A data bit paints fg, a mask bit that
 * is not data paints bg -- antic_plot's rule, pixel for pixel -- and
 * columns off either edge of the screen are left alone. */
void antic_cursor_paint(int16_t x, int16_t y, const uint16_t *mask,
                        const uint16_t *data, uint8_t bg, uint8_t fg)
{
    int16_t r, c, bx0;
    uint8_t sh, fgb = fg ? 0xFF : 0x00, bgb = bg ? 0xFF : 0x00;

    if (x >= AN_W || x + AN_CUR_W <= 0)
        return;
    /* the byte column of the form's first pixel, floored: x may be
     * off the left edge */
    bx0 = (int16_t)(x >= 0 ? (int16_t)((uint16_t)x >> 3)
                           : (int16_t)(-1 - (int16_t)((uint16_t)(-1 - x) >> 3)));
    sh = (uint8_t)(x - bx0 * 8);
    for (r = 0; r < AN_CUR_W; r++) {
        int16_t yy = (int16_t)(y + r);
        uint32_t d24, m24;

        if (yy < 0 || yy >= AN_H)
            continue;
        d24 = ((uint32_t)data[r] << 8) >> sh;
        m24 = ((uint32_t)mask[r] << 8) >> sh;
        for (c = 0; c < AN_CUR_NB; c++) {
            int16_t bx = (int16_t)(bx0 + c);
            uint8_t db, mb, fgm, bgm, dst, v;
            volatile uint8_t *p;

            if (bx < 0 || bx >= AN_STRIDE)
                continue;
            db = (uint8_t)(d24 >> (16 - 8 * c));
            mb = (uint8_t)(m24 >> (16 - 8 * c));
            fgm = db;
            bgm = (uint8_t)(mb & (uint8_t)~db);
            if (!(fgm | bgm))
                continue;
            p = SCREEN + (uint16_t)yy * AN_STRIDE + (uint16_t)bx;
            dst = *p;
            v = (uint8_t)((dst & (uint8_t)~(fgm | bgm))
                          | (fgm & fgb) | (bgm & bgb));
            *p = v;
        }
    }
}
