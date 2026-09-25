/* text_sim.c -- antic_text against the n glyphs it stands in for.
 *
 * v_gtext on the ANTIC screen hands the device a string's visible run in
 * one call, drawn a row of the whole run at a time (src/antic/antic.c,
 * docs/phase54.md).  It must come out exactly as antic_glyph drew the
 * same cells one by one -- which the desktop's gates hold it to for the
 * strings the desktop happens to draw.  Here: every writing mode, both
 * pens, every alignment of the run's first pixel, three cell widths and
 * runs of one cell to a whole row, over random screen bytes, against a
 * font whose unused columns are random too, so a cell that leaks past
 * its width shows.  The rows either side and the bytes either side of
 * the run must not change.  In the compiler's own simulator at -O2,
 * because that is where this tree's rasteriser bugs have come from.
 */
#include "portab.h"
#include "antic/antic.h"

#define H      6                        /* rows a glyph has */
#define FSTR   256                      /* antic.c: AN_FONT_STRIDE */
#define CASES  (4 * 2 * 8 * 3)          /* mode x pen x alignment x width */

uint16_t ts_cases;                      /* run */
uint16_t ts_bad;                        /* whose pixels differ */
uint16_t ts_first;                      /* the first bad one, or 0xFFFF */
uint16_t ts_first_x, ts_first_n, ts_first_mode, ts_first_w;

static uint8_t font[H * FSTR];
static int16_t chars[64];
static uint8_t before[(H + 2) * AN_STRIDE];
static uint8_t want[(H + 2) * AN_STRIDE];
static uint32_t seed = 4321UL;

static uint16_t rnd(void)
{
    seed = seed * 1103515245UL + 12345UL;
    return (uint16_t)(seed >> 16);
}

int main(void)
{
    volatile uint8_t *screen = (volatile uint8_t *)AN_SCREEN;
    uint32_t face = (uint32_t)(const uint8_t FAR *)font;
    uint16_t c, i, j;
    static const int16_t widths[3] = { 6, 8, 5 };

    for (i = 0; i < H * FSTR; i++)
        font[i] = (uint8_t)rnd();
    ts_first = 0xFFFF;
    for (c = 0; c < CASES; c++) {
        int16_t mode = (int16_t)(1 + (c & 3));
        uint8_t pen = (uint8_t)((c >> 2) & 1);
        int16_t w = widths[(c >> 6) % 3];
        uint16_t most = (uint16_t)((AN_W - 16) / w);
        uint16_t n = (uint16_t)(c % 11 == 0 ? most : 1 + rnd() % 20);
        int16_t x = (int16_t)(8 * (rnd() % 2) + ((c >> 3) & 7));
        /* a row above and below the glyphs, which must not move */
        int16_t y0 = (int16_t)(rnd() % (AN_H - H - 2));
        volatile uint8_t *rows = screen + (uint16_t)y0 * AN_STRIDE;
        uint16_t bad = 0;

        if (n > most)
            n = most;
        for (i = 0; i < n; i++)
            chars[i] = (int16_t)(rnd() & 0xFF);
        for (i = 0; i < (H + 2) * AN_STRIDE; i++) {
            uint8_t v = (uint8_t)rnd();

            before[i] = v;
            rows[i] = v;
        }
        /* the cells one at a time: what the screen should end up as */
        for (i = 0; i < n; i++)
            antic_glyph(face, (uint16_t)chars[i], (int16_t)(x + (int16_t)i * w),
                        (int16_t)(y0 + 1), mode, pen, w, H);
        for (i = 0; i < (H + 2) * AN_STRIDE; i++) {
            uint8_t v = rows[i];

            want[i] = v;
            rows[i] = before[i];
        }
        antic_text(face, chars, n, x, (int16_t)(y0 + 1), mode, pen, w, H);
        for (j = 0; j < (H + 2) * AN_STRIDE; j++) {
            uint8_t got = rows[j];

            if (got != want[j])
                bad = 1;
        }
        ts_cases++;
        if (bad) {
            if (ts_first == 0xFFFF) {
                ts_first = c;
                ts_first_x = (uint16_t)x;
                ts_first_n = n;
                ts_first_mode = (uint16_t)mode;
                ts_first_w = (uint16_t)w;
            }
            ts_bad++;
        }
    }
    return 0;
}
