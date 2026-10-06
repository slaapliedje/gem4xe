/* tablet_sim.c -- runs the tablets' decode over every pot pair, both kinds,
 * and their buttons over every state of the direction lines, in the
 * compiler's simulator, for tests/host/test_pointer.py to compare with a
 * model of Altirra's ATTabletController (phase 108).  The bridge can attach
 * neither tablet nor set a pot, so this is where the arithmetic is held. */
#include <stdint.h>
#include "vdi/pointer.h"

uint32_t r_cx77;        /* over every (px, py): down?, x, y */
uint32_t r_koala;
uint32_t r_buttons;     /* over every direction nibble */

/* every value of each pot against the edges and the middle of the
 * other, and both stylus-up values: the decode is one line per axis, so
 * this is every case it has */
static const uint8_t edge[6] = { 0, 1, 114, 227, 228, 255 };

static uint32_t one(uint32_t h, WORD kind, uint8_t px, uint8_t py)
{
    WORD x = -1, y = -1;

    h = h * 31u + (ptr_decode_tablet(kind, px, py, &x, &y) ? 1u : 2u);
    h = h * 31u + (uint16_t)x;
    return h * 31u + (uint16_t)y;
}

static uint32_t walk(WORD kind)
{
    uint32_t h = 0;
    uint16_t v;
    uint8_t e;

    for (v = 0; v < 256; v++)
        for (e = 0; e < 6; e++) {
            h = one(h, kind, (uint8_t)v, edge[e]);
            h = one(h, kind, edge[e], (uint8_t)v);
        }
    return h;
}

int main(void)
{
    uint32_t b = 0;
    uint16_t n;

    r_cx77 = walk(PTR_CX77);
    r_koala = walk(PTR_KOALA);
    for (n = 0; n < 16; n++)
        b = b * 7u + (uint32_t)ptr_tablet_buttons((uint8_t)n);
    r_buttons = b;
    return 0;
}
