/* b21.c -- a join reached with two accumulator widths.
 *
 * A loop that reads a volatile byte ON ONE PATH ONLY, stores it into a
 * local buffer, and hands the buffer on.  cc65816 5.18 at -O2 outlines a
 * `sep #32 / ldy ##0 / rtl` tail, calls it on the path that reads, and
 * lets that path fall into the join with the accumulator still 8 bits
 * wide -- where the join's next 16-bit immediate (`adc ##33`, 69 21 00)
 * runs as `adc #$21` and then BRK.  Found in src/antic/antic.c's
 * antic_copy, 2026-09-24; tools/ccbug/mscan.py's joins() is the detector.
 */
#include <stdint.h>

void take(const uint8_t *buf, int16_t n);

void b21(int16_t y, int16_t sb, int16_t n)
{
    uint8_t buf[42];
    int16_t k;

    for (k = 0; k < n; k++) {
        int16_t bx = (int16_t)(sb + k);
        uint8_t v = 0;

        if (y >= 0 && y < 168 && bx >= 0 && bx < 40) {
            volatile uint8_t *sp = (volatile uint8_t *)0x8100
                                   + (uint16_t)y * 40 + (uint16_t)bx;
            v = *sp;
        }
        buf[k] = v;
    }
    take(buf, n);
}
