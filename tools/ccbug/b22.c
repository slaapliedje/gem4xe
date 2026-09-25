/* B22 -- a far array indexed by a byte cast of a loaded value, in a loop,
 * is an internal compiler error, not a miscompile, so this file is
 * compiled on its own and the outcome read from the compiler:
 *
 *   internal error: anyIndOffset (1,s),y
 *
 * Every -O level.  What does NOT crash: `& 0xFF` in place of the cast,
 * an index that is already a uint8_t element, a uint16_t cast, the same
 * loop over a near table, the same expression outside a loop, and a
 * pointer walked with ++ -- so the sources write `& 0xFF`
 * (src/antic/antic.c, an_pack6).  Found in phase 54, packing a string's
 * glyph rows for the ANTIC screen. */
#include <stdint.h>

uint16_t r_b22_bug(const uint8_t __far *face, const int16_t *chars, uint16_t n)
{
    uint16_t i, sum = 0, j;

    for (i = 0; i < n; i++) {
        j = (uint8_t)chars[i];
        sum += face[j];
    }
    return sum;
}
