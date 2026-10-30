/* gsqd.c -- QuickDraw II ($04), the part milestone 1 draws with.
 *
 * Everything is drawn into the Super Hi-Res screen at $E1:2000 exactly as
 * the IIGS lays it out (Hardware Reference, "Super Hi-Res graphics"), so
 * the result can be held against what Apple's own QuickDraw II drew on
 * MAME's apple2gs byte for byte.  The calls are the Toolbox Reference's,
 * volume 2, chapter 16; their numbers are its.
 *
 * So far: the screen port only (origin 0,0, clipped to the screen), solid
 * pen patterns, copy mode, a 1x1 pen.  640 mode draws four 2-bit pixels a
 * byte, leftmost in bits 7-6; 320 mode two 4-bit pixels, leftmost high.
 *
 * TEXT is drawn in gem4xe's 8x8 font (EmuTOS's, GPL), not Shaston 8:
 * Shaston is Apple's, in Apple's ROM, and its system-font handle does not
 * hold the font record volume 2 documents.  The gate compares everything
 * else byte for byte and the text by where it is (docs/gslayer.md).
 */
#include "gs.h"

extern const uint8_t FAR font8x8[2048];

/* Table 16-7, standard color tables. */
static const uint16_t std640[16] = {
    0x000, 0xF00, 0x0F0, 0xFFF, 0x000, 0x00F, 0xFF0, 0xFFF,
    0x000, 0xF00, 0x0F0, 0xFFF, 0x000, 0x00F, 0xFF0, 0xFFF
};
static const uint16_t std320[16] = {
    0x000, 0x777, 0x841, 0x72C, 0x00F, 0x080, 0xF70, 0xD00,
    0xFA9, 0xFF0, 0x0E0, 0x4DF, 0xDAF, 0x78F, 0xCCC, 0xFFF
};

static uint8_t  qd_640;             /* the master SCB's mode bit */
static int16_t  pen_h, pen_v;
static uint8_t  pen_colour;         /* the solid pattern's pixel value */
static uint8_t  fg_colour;          /* text */

static uint8_t rd8(uint32_t a) { return *(uint8_t FAR *)a; }
static void wr8(uint32_t a, uint8_t v) { *(uint8_t FAR *)a = v; }

static int16_t rdw(uint32_t a)
{
    return (int16_t)(rd8(a) | rd8(a + 1) << 8);
}

static void wrw(uint32_t a, int16_t v)
{
    wr8(a, (uint8_t)v);
    wr8(a + 1, (uint8_t)((uint16_t)v >> 8));
}

static int16_t width(void) { return qd_640 ? 640 : 320; }

static void plot(int16_t x, int16_t y, uint8_t c)
{
    uint32_t a;
    uint16_t b, sh, m;                  /* words: B23 (gsomf.c's super) */

    if (x < 0 || y < 0 || x >= width() || y >= GS_LINES)
        return;
    if (qd_640) {
        a = GS_SHR + (uint32_t)y * GS_LINE + (uint16_t)x / 4;
        sh = (uint16_t)(6 - 2 * (x & 3));
        m = (uint16_t)(3 << sh);
        c = (uint8_t)((c & 3) << sh);
    } else {
        a = GS_SHR + (uint32_t)y * GS_LINE + (uint16_t)x / 2;
        sh = (uint16_t)((x & 1) ? 0 : 4);
        m = (uint16_t)(15 << sh);
        c = (uint8_t)((c & 15) << sh);
    }
    b = rd8(a);
    wr8(a, (uint8_t)((b & ~m) | c));
}

static void fill(int16_t h1, int16_t v1, int16_t h2, int16_t v2, uint8_t c)
{
    int16_t x, y;

    for (y = v1; y < v2; y++)
        for (x = h1; x < h2; x++)
            plot(x, y, c);
}

/* A Rect at `a`: v1, h1, v2, h2 (volume 2, "Rectangles"). */
typedef struct { int16_t v1, h1, v2, h2; } QRect;

static void get_rect(uint32_t a, QRect *r)
{
    r->v1 = rdw(a);
    r->h1 = rdw(a + 2);
    r->v2 = rdw(a + 4);
    r->h2 = rdw(a + 6);
}

/* QDStartUp's effect on the screen, also what GSlayer starts with. */
void gs_qd_reset(void)
{
    pen_h = 0;
    pen_v = 0;
    pen_colour = 0;
    fg_colour = 0;
}

static void startup(uint8_t scb)
{
    uint16_t i;
    const uint16_t *t;

    qd_640 = (uint8_t)(scb & 0x80);
    for (i = 0; i < 256; i++)           /* every byte of the SCB page, as */
        wr8(GS_SCB + i, scb);           /* Apple's leaves it (gs1_hello.py) */
    t = qd_640 ? std640 : std320;
    for (i = 0; i < 16; i++)
        wrw(GS_PAL + i * 2, (int16_t)t[i]);
    gs_qd_reset();
}

static void draw_char(uint8_t ch)
{
    uint16_t r, b, bits;

    for (r = 0; r < 8; r++) {
        bits = font8x8[r * 256 + ch];
        for (b = 0; b < 8; b++)
            if (bits & (0x80 >> b))
                plot((int16_t)(pen_h + b), (int16_t)(pen_v - 7 + r), fg_colour);
    }
    pen_h = (int16_t)(pen_h + 8);
}

uint16_t gs_qd(uint8_t fn, uint8_t *p)
{
    QRect r;
    uint32_t a;
    uint16_t w, c;

    switch (fn) {
    case 0x02:                          /* QDStartUp(dPage, SCB, maxWidth, ID) */
        gs_pop = 8;
        startup((uint8_t)GS_W(p, 4));
        return 0;
    case 0x03:                          /* QDShutDown */
        return 0;
    case 0x15:                          /* ClearScreen(colorWord) */
        gs_pop = 2;
        w = GS_W(p, 0);
        for (a = GS_SHR; a < GS_SCB; a += 2) {
            wr8(a, (uint8_t)w);
            wr8(a + 1, (uint8_t)(w >> 8));
        }
        return 0;
    case 0x37:                          /* SetSolidPenPat(colorNum) */
        gs_pop = 2;
        pen_colour = (uint8_t)GS_W(p, 0);
        return 0;
    case 0x3A:                          /* MoveTo(h, v) */
        gs_pop = 4;
        pen_v = (int16_t)GS_W(p, 0);
        pen_h = (int16_t)GS_W(p, 2);
        return 0;
    case 0x4A:                          /* SetRect(rect, left, top, right, bottom) */
        gs_pop = 12;
        a = GS_L(p, 8);
        wrw(a, (int16_t)GS_W(p, 4));    /* v1: top */
        wrw(a + 2, (int16_t)GS_W(p, 6)); /* h1: left */
        wrw(a + 4, (int16_t)GS_W(p, 0)); /* v2: bottom */
        wrw(a + 6, (int16_t)GS_W(p, 2)); /* h2: right */
        return 0;
    case 0x53:                          /* FrameRect(rect): inside its edge */
        gs_pop = 4;
        get_rect(GS_L(p, 0), &r);
        if (r.h2 <= r.h1 || r.v2 <= r.v1)
            return 0;
        fill(r.h1, r.v1, r.h2, (int16_t)(r.v1 + 1), pen_colour);
        fill(r.h1, (int16_t)(r.v2 - 1), r.h2, r.v2, pen_colour);
        fill(r.h1, r.v1, (int16_t)(r.h1 + 1), r.v2, pen_colour);
        fill((int16_t)(r.h2 - 1), r.v1, r.h2, r.v2, pen_colour);
        return 0;
    case 0x54:                          /* PaintRect(rect) */
        gs_pop = 4;
        get_rect(GS_L(p, 0), &r);
        fill(r.h1, r.v1, r.h2, r.v2, pen_colour);
        return 0;
    case 0xA6:                          /* DrawCString(cString) */
        gs_pop = 4;
        a = GS_L(p, 0);
        while ((c = rd8(a)) != 0) {
            draw_char((uint8_t)c);
            a++;
        }
        return 0;
    }
    return GS_NOTYET;
}
