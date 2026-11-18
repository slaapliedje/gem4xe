/* farm6502.c -- far memory for a 6502 program of several banks
 * (docs/6502.md, step 5c-2): gem.h's fa_* on the 6502.
 *
 * A far address is the system's (src/sys6502/farmem6502.c): bank 0 is
 * near memory, read and written as it is; far bank k >= 1 is four PORTB
 * banks, piece p of it at bank index b6_far_base + (k-1)*4 + p, seen at
 * $4000 + (offset & $3FFF).  These map that piece into the window
 * themselves -- PORTB from the system's b6_portb, whose address the link
 * block gives (src/app/crt6502m.s) -- copy, and map back the program's
 * own bank, the one b6_cur names: no call into the system.
 *
 * SO THEY MUST NOT BE IN A BANK.  This file is compiled without one and
 * lands in the program's shared RAM under the ROM (src/app/
 * gemappm6502.scm), outside the window it maps; a near buffer handed to
 * them must be outside it too -- a program's data and stack are.  The
 * ROM is out throughout (b6_portb's values have bit 0 clear), and an
 * interrupt puts PORTB back as it found it.  A program of several banks
 * is refused on an Axlon (src/a6_evt.c), so PORTB is the register.
 */
#include "portab.h"
#include "gem.h"
#include <string.h>

#define PORTB   (*(volatile uint8_t *)0xD301)
#define WINDOW  0x4000u
#define PIECE   0x4000u

extern const uint8_t *g6_l_tab;         /* b6_portb */
extern const uint8_t *g6_l_cur;         /* b6_cur */
extern uint8_t g6_l_fbase;              /* b6_far_base */

/* the piece of far address a into the window; its window address */
static uint8_t *fa_map(uint32_t a)
{
    uint8_t k = (uint8_t)(a >> 16), p = (uint8_t)((uint16_t)a >> 14);

    k--;
    k = (uint8_t)(k << 2);
    p &= 3;
    k += p;                             /* bytes stored, then an index: cc6502 */
    k += g6_l_fbase;                    /* sign-extends a computed byte cast */
    PORTB = g6_l_tab[k];
    return (uint8_t *)(WINDOW + ((uint16_t)a & (PIECE - 1)));
}

static void fa_back(void)
{
    PORTB = g6_l_tab[*g6_l_cur];
}

void fa_get(void *dst, uint32_t src, UWORD n)
{
    uint8_t *d = (uint8_t *)dst;
    uint16_t k;

    if (!(src >> 16)) {
        memcpy(d, (const void *)(uint16_t)src, n);
        return;
    }
    while (n) {
        k = (uint16_t)(PIECE - ((uint16_t)src & (PIECE - 1)));
        if (k > n)
            k = n;
        memcpy(d, fa_map(src), k);
        d += k;
        src += k;
        n = (UWORD)(n - k);
    }
    fa_back();
}

void fa_put(uint32_t dst, const void *src, UWORD n)
{
    const uint8_t *s = (const uint8_t *)src;
    uint16_t k;

    if (!(dst >> 16)) {
        memcpy((void *)(uint16_t)dst, s, n);
        return;
    }
    while (n) {
        k = (uint16_t)(PIECE - ((uint16_t)dst & (PIECE - 1)));
        if (k > n)
            k = n;
        memcpy(fa_map(dst), s, k);
        s += k;
        dst += k;
        n = (UWORD)(n - k);
    }
    fa_back();
}

uint8_t fa_rd8(uint32_t a)
{
    uint8_t v;

    fa_get(&v, a, 1);
    return v;
}

uint16_t fa_rd16(uint32_t a)
{
    uint16_t v;

    fa_get(&v, a, 2);
    return v;
}

uint32_t fa_rd32(uint32_t a)
{
    uint32_t v;

    fa_get(&v, a, 4);
    return v;
}

void fa_wr8(uint32_t a, uint8_t v)   { fa_put(a, &v, 1); }
void fa_wr16(uint32_t a, uint16_t v) { fa_put(a, &v, 2); }
void fa_wr32(uint32_t a, uint32_t v) { fa_put(a, &v, 4); }
