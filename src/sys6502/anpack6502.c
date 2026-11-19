/* anpack6502.c -- antic_text's two helpers' arguments, for the 6502 build.
 *
 * The 65C816 build has the helpers in assembler (src/antic/anpack.s,
 * phase 146), with the same names and the same direct-page arguments,
 * which src/antic/antic.c sets and calls.  On the 6502 the arguments are
 * zero page (TINY), here, and the helpers are assembler too, in the antic
 * bank (src/sys6502/antic6502.s, speed 4: a menu's text was most of its
 * drawing in C).  The packer's C stays for a face in a PORTB bank, which
 * the assembler hands here.
 */
#include "portab.h"
#include <stdint.h>
#include "sys/farmem.h"

TINY uint32_t ap_sr;
TINY uint16_t ap_chars, ap_buf, ap_n, ap_lead;
TINY uint16_t pr_buf, pr_scr, pr_last;
TINY uint8_t pr_lm, pr_rm, pr_x1, pr_y1, pr_x0, pr_y0;

/* One row of a run: `lead` zero bits, then six of each glyph (its bits
 * 7..2), MSB first, a last partial byte left-aligned -- from a face in a
 * PORTB bank, read a byte at a time through far_read8. */
void an_pack6_c(void)
{
    const uint8_t *sr = (const uint8_t *)(uint16_t)ap_sr;
    uint8_t bank = (uint8_t)(ap_sr >> 16);      /* stored: b6scan's fault B */
    uint8_t far = bank != 0;                    /* a face in a PORTB bank */
    const int16_t *chars = (const int16_t *)ap_chars;
    uint8_t *buf = (uint8_t *)ap_buf;
    uint16_t i, k = 0, acc = 0, bits = ap_lead;
    uint8_t g;

    for (i = 0; i < ap_n; i++) {
        g = far ? far_read8(ap_sr + (uint16_t)(chars[i] & 0xFF)) : sr[chars[i] & 0xFF];
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
