/* muldiv6502.c -- src/sys/muldiv.s's two routines, in C, for the 6502.
 *
 * umuldiv(a, b, c) = floor(a * b / c), and flit_scan, the polygon filler's
 * scan line: the C loop it replaced, tests/host/muldiv_sim.c's flit_ref,
 * which the 65C816's assembly is held to.  Same names, same arguments.
 */
#include "portab.h"
#include <stdint.h>

#define MAX_INTERSECT 32                /* src/vdi/vdi.c's */

/* cc6502's own 16 x 16 -> 32 multiply swaps the product's low bytes
 * (src/sys6502/mul6502.s); this file is resident, which bankasm does not
 * rewrite, so it names the right one itself. */
uint32_t b6_mul16to32(uint16_t a, uint16_t b);

uint16_t umuldiv(uint16_t a, uint16_t b, uint16_t c)
{
    return (uint16_t)(b6_mul16to32(a, b) / c);
}

static uint16_t uabs(int16_t v)
{
    return (uint16_t)(v < 0 ? -v : v);
}

/* v >> 1, rounding toward minus infinity, without a signed shift */
static int16_t asr1(int16_t v)
{
    uint16_t u = (uint16_t)v >> 1;

    if (v < 0)
        u |= 0x8000U;
    return (int16_t)u;
}

int16_t flit_scan(const int16_t *pts, int16_t vectors, int16_t y, int16_t *out)
{
    const int16_t *p = pts;
    int16_t i, n = 0;

    for (i = vectors; i > 0; i--, p += 2) {
        int16_t y1 = p[1], y2 = p[3], x1, x2;
        uint16_t q, dy;

        if (y1 < y2) {
            if (y < y1 || y >= y2)
                continue;
            dy = (uint16_t)(y2 - y1);
        } else {
            if (y < y2 || y >= y1)
                continue;
            dy = (uint16_t)(y1 - y2);
        }
        if (n >= MAX_INTERSECT)
            break;
        x1 = p[0];
        x2 = p[2];
        if (x2 < x1) {
            q = umuldiv(uabs((int16_t)(y - y2)), (uint16_t)((uint16_t)(x1 - x2) << 1), dy);
            x1 = x2;
        } else {
            q = umuldiv(uabs((int16_t)(y - y1)), (uint16_t)((uint16_t)(x2 - x1) << 1), dy);
        }
        out[n++] = (int16_t)(asr1((int16_t)((int16_t)q + 1)) + x1);
    }
    return n;
}
