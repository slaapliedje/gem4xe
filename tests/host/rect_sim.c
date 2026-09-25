/* rect_sim.c -- antic_fill_rect against the spans it stands in for.
 *
 * A rectangle on the ANTIC screen used to be one antic_span or
 * antic_patt_span a row; it is one call now, with the set-up done once
 * and the covered middle of each row stored where the op allows
 * (src/antic/antic.c, docs/phase55.md).  This draws each case both ways
 * over the same random screen and requires the same bytes -- every
 * writing mode, both pens, solid and patterned, every alignment of both
 * edges, both parities of the first byte, one byte wide to the whole row,
 * and rectangles that run off every edge of the screen.  In the
 * compiler's own simulator at -O2.
 */
#include "portab.h"
#include "antic/antic.h"

#define CASES  (4 * 2 * 2 * 8 * 4)      /* mode x pen x solid x x1&7 x kind */
#define ROWS   4                        /* rows a case may touch */

uint16_t rs_cases;
uint16_t rs_bad;
uint16_t rs_first;                      /* the first bad case, or 0xFFFF */
uint16_t rs_first_x1, rs_first_x2, rs_first_mode, rs_first_patt;

static uint16_t rows[16];
static uint8_t before[(ROWS + 2) * AN_STRIDE];
static uint8_t want[(ROWS + 2) * AN_STRIDE];
static uint32_t seed = 777UL;

static uint16_t rnd(void)
{
    seed = seed * 1103515245UL + 12345UL;
    return (uint16_t)(seed >> 16);
}

int main(void)
{
    volatile uint8_t *screen = (volatile uint8_t *)AN_SCREEN;
    uint16_t c, i;

    rs_first = 0xFFFF;
    for (c = 0; c < CASES; c++) {
        int16_t mode = (int16_t)(1 + (c & 3));
        uint8_t pen = (uint8_t)((c >> 2) & 1);
        uint16_t patt = (uint16_t)((c >> 3) & 1);
        uint16_t kind = (uint16_t)((c >> 7) & 3);
        int16_t x1 = (int16_t)(8 * (rnd() % 30) + ((c >> 4) & 7));
        int16_t x2, y1, y2, top, y;
        volatile uint8_t *band;
        uint16_t bad = 0;

        switch (kind) {
        case 0:  x2 = (int16_t)(x1 + rnd() % 8); break;        /* a byte or two */
        case 1:  x2 = (int16_t)(x1 + 8 + rnd() % 40); break;   /* a few */
        case 2:  x2 = (int16_t)(x1 + rnd() % 300); break;      /* wide */
        default: x1 = (int16_t)(-(int16_t)(rnd() % 20));       /* off the edges */
                 x2 = (int16_t)(AN_W + rnd() % 20); break;
        }
        if (kind != 3 && x2 >= AN_W)
            x2 = AN_W - 1;
        /* a band of ROWS+2 rows, the rectangle inside it -- or, for the
         * last kind, hanging off the top or the bottom of the screen */
        if (kind == 3 && (c & 1)) {
            top = 0;
            y1 = (int16_t)(-3);
            y2 = (int16_t)(ROWS - 4);
        } else if (kind == 3) {
            top = (int16_t)(AN_H - ROWS - 2);
            y1 = (int16_t)(top + 3);
            y2 = (int16_t)(AN_H + 4);
        } else {
            top = (int16_t)(rnd() % (AN_H - ROWS - 2));
            y1 = (int16_t)(top + 1);
            y2 = (int16_t)(y1 + rnd() % ROWS);
        }
        band = screen + (uint16_t)top * AN_STRIDE;
        for (i = 0; i < 16; i++)
            rows[i] = patt ? rnd() : 0xFFFF;
        for (i = 0; i < (ROWS + 2) * AN_STRIDE; i++) {
            uint8_t v = (uint8_t)rnd();

            before[i] = v;
            band[i] = v;
        }
        /* a span a row: what the screen should end up as */
        for (y = y1; y <= y2; y++) {
            if (patt)
                antic_patt_span(x1, x2, y, rows[y & 15], mode, pen);
            else
                antic_span(x1, x2, y, mode, pen);
        }
        for (i = 0; i < (ROWS + 2) * AN_STRIDE; i++) {
            uint8_t v = band[i];

            want[i] = v;
            band[i] = before[i];
        }
        antic_fill_rect(x1, y1, x2, y2, patt ? rows : 0, mode, pen);
        for (i = 0; i < (ROWS + 2) * AN_STRIDE; i++) {
            uint8_t got = band[i];

            if (got != want[i])
                bad = 1;
        }
        rs_cases++;
        if (bad) {
            if (rs_first == 0xFFFF) {
                rs_first = c;
                rs_first_x1 = (uint16_t)x1;
                rs_first_x2 = (uint16_t)x2;
                rs_first_mode = (uint16_t)mode;
                rs_first_patt = patt;
            }
            rs_bad++;
        }
    }
    return 0;
}
