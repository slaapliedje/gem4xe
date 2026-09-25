/* raster_sim.c -- antic_raster_row against the per-pixel rules it replaced.
 *
 * vrt_cpyfm on the ANTIC screen used to go pixel by pixel through
 * antic_plot; it goes a byte at a time now (src/antic/antic.c,
 * docs/phase52.md).  This drives the new routine with pseudo-random rows
 * -- every writing mode, both pens, every alignment of source and
 * destination, runs of one pixel and of the whole screen -- and checks
 * each result, byte for byte, against the same row worked out here one
 * pixel at a time by the VDI's rules:
 *
 *   replace      ink where set, bg where clear
 *   transparent  ink where set
 *   XOR          complement where set
 *   erase        bg where CLEAR
 *
 * The bytes either side of the run must not change at all.  Compiled by
 * the real compiler and run in its simulator, because that is where this
 * tree's rasteriser bugs have come from (tools/ccbug).
 */
#include "portab.h"
#include "antic/antic.h"

/* every destination alignment x every source alignment x every mode --
 * 256, with the two pens cycling through them -- and then some runs
 * across the whole screen.  ENUMERATED rather than random: a simulated
 * 65816 does a hundred random rows in eighteen seconds, and a random set
 * that size would not be sure of reaching every alignment. */
#define ALIGNED 256
#define LONG    4
#define CASES   (ALIGNED + LONG)
#define SRCLEN  44                      /* bytes of source a row may use:
                                         * a whole row and a little */

uint16_t rr_cases;                      /* run */
uint16_t rr_bad;                        /* whose row came out wrong */
uint16_t rr_first;                      /* the first bad one, or 0xFFFF */
uint16_t rr_first_x1, rr_first_x2, rr_first_mode, rr_first_sbit;

static uint8_t src[SRCLEN + 2];
static uint8_t want[AN_STRIDE];
static uint32_t seed = 12345UL;

static uint16_t rnd(void)
{
    seed = seed * 1103515245UL + 12345UL;
    return (uint16_t)(seed >> 16);
}

static uint8_t bit_of(const uint8_t *b, uint16_t i)
{
    uint8_t v = b[i >> 3];

    return (uint8_t)((v >> (7 - (i & 7))) & 1);
}

static void set_bit(uint8_t *b, uint16_t i, uint8_t on)
{
    uint8_t m = (uint8_t)(0x80 >> (i & 7));
    uint8_t v = b[i >> 3];

    if (on)
        v = (uint8_t)(v | m);
    else
        v = (uint8_t)(v & (uint8_t)~m);
    b[i >> 3] = v;
}

int main(void)
{
    volatile uint8_t *screen = (volatile uint8_t *)AN_SCREEN;
    uint16_t c, i;

    rr_first = 0xFFFF;
    for (c = 0; c < CASES; c++) {
        uint16_t y = (uint16_t)(rnd() % AN_H);
        uint16_t x1, span, x2, sbit;
        int16_t mode;
        uint8_t pen, pap;

        if (c < ALIGNED) {
            /* c = dalign*32 + salign*4 + mode-1 */
            x1 = (uint16_t)(8 * (1 + rnd() % 30) + (c >> 5));
            sbit = (uint16_t)(8 * (rnd() % 4) + ((c >> 2) & 7));
            mode = (int16_t)(1 + (c & 3));
            span = (uint16_t)(rnd() % 24);
            pen = (uint8_t)((c >> 1) & 1);
            pap = (uint8_t)(((c >> 3) ^ c) & 1);
        } else {
            x1 = (uint16_t)(rnd() % 16);
            sbit = (uint16_t)(rnd() % 16);
            mode = (int16_t)(1 + rnd() % 4);
            span = (uint16_t)(AN_W - 1 - rnd() % 16);
            pen = (uint8_t)(rnd() & 1);
            pap = (uint8_t)(rnd() & 1);
        }
        x2 = (uint16_t)(x1 + span);
        volatile uint8_t *row = screen + y * AN_STRIDE;
        uint16_t x, bad = 0;

        if (x2 >= AN_W)
            x2 = AN_W - 1;
        /* the source must hold every bit the run reads, and one byte more */
        if (sbit + (x2 - x1) >= (uint16_t)(SRCLEN * 8))
            x2 = (uint16_t)(x1 + (SRCLEN * 8 - 1 - sbit));
        for (i = 0; i < SRCLEN + 2; i++)
            src[i] = (uint8_t)rnd();
        for (i = 0; i < AN_STRIDE; i++) {
            uint8_t v = (uint8_t)rnd();

            want[i] = v;
            row[i] = v;
        }
        for (x = x1; x <= x2; x++) {
            uint8_t s = bit_of(src, (uint16_t)(sbit + (x - x1)));
            uint8_t d = bit_of(want, x);

            switch (mode) {
            case 2:                     /* transparent */
                if (s)
                    set_bit(want, x, pen);
                break;
            case 3:                     /* XOR */
                if (s)
                    set_bit(want, x, (uint8_t)!d);
                break;
            case 4:                     /* erase */
                if (!s)
                    set_bit(want, x, pap);
                break;
            default:                    /* replace */
                set_bit(want, x, s ? pen : pap);
                break;
            }
        }
        antic_raster_row((const uint8_t FAR *)src, sbit, (int16_t)x1,
                         (int16_t)x2, (int16_t)y, mode, pen, pap);
        for (i = 0; i < AN_STRIDE; i++) {
            uint8_t got = row[i];

            if (got != want[i])
                bad = 1;
        }
        rr_cases++;
        if (bad) {
            if (rr_first == 0xFFFF) {
                rr_first = c;
                rr_first_x1 = x1;
                rr_first_x2 = x2;
                rr_first_mode = (uint16_t)mode;
                rr_first_sbit = sbit;
            }
            rr_bad++;
        }
    }
    return 0;
}
