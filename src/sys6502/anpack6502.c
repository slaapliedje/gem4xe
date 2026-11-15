/* anpack6502.c -- antic_text's two helpers, in C, for the 6502 build.
 *
 * The 65C816 build has them in assembler (src/antic/anpack.s, phase 146),
 * with the same names and the same direct-page arguments, which
 * src/antic/antic.c sets and calls.  On the 6502 the arguments are zero
 * page (TINY) and the code is the C antic.c had before phase 146 -- the
 * packer as it was, and the row put through AN_MIX's formula -- until a
 * 6502 assembler version earns its place on a bench (docs/6502.md).
 */
#include "portab.h"
#include <stdint.h>

TINY uint32_t ap_sr;
TINY uint16_t ap_chars, ap_buf, ap_n, ap_lead;
TINY uint16_t pr_buf, pr_scr, pr_last;
TINY uint8_t pr_lm, pr_rm, pr_x1, pr_y1, pr_x0, pr_y0;

/* One row of a run: `lead` zero bits, then six of each glyph (its bits
 * 7..2), MSB first, a last partial byte left-aligned. */
void an_pack6_s(void)
{
    const uint8_t *sr = (const uint8_t *)(uint16_t)ap_sr;
    const int16_t *chars = (const int16_t *)ap_chars;
    uint8_t *buf = (uint8_t *)ap_buf;
    uint16_t i, k = 0, acc = 0, bits = ap_lead;
    uint8_t g;

    for (i = 0; i < ap_n; i++) {
        g = sr[chars[i] & 0xFF];
        acc = (uint16_t)((acc << 6) | (uint16_t)(g >> 2));
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            g = (uint8_t)(acc >> bits);
            buf[k] = g;
            k++;
        }
    }
    if (bits) {
        g = (uint8_t)(acc << (8 - bits));
        buf[k] = g;
    }
}

/* The packed row onto the screen through the op:
 *     t1 = (d & x1) ^ y1,  t0 = (d & x0) ^ y0
 *     d' = (s & t1) | (~s & t0), kept inside the mask m. */
void an_put_row_s(void)
{
    const uint8_t *buf = (const uint8_t *)pr_buf;
    volatile uint8_t *p = (volatile uint8_t *)pr_scr;
    uint16_t k;
    uint8_t s, m, d, t1, t0, n;

    for (k = 0; k <= pr_last; k++) {
        s = buf[k];
        m = 0xFF;
        if (k == 0)
            m = pr_lm;
        if (k == pr_last)
            m = (uint8_t)(m & pr_rm);
        d = 0;
        if (m != 0xFF || (pr_x1 | pr_x0))
            d = p[k];
        t1 = (uint8_t)((d & pr_x1) ^ pr_y1);
        t0 = (uint8_t)((d & pr_x0) ^ pr_y0);
        n = (uint8_t)((s & t1) | ((uint8_t)~s & t0));
        n = (uint8_t)((d & (uint8_t)~m) | (n & m));
        p[k] = n;
    }
}
