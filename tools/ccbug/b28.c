/* B28 -- the hand-written offsetof, a member's address less the struct's
 * as char pointers, is an internal compiler error, not a miscompile, so
 * this file is compiled on its own and the outcome read from the
 * compiler:
 *
 *   internal error: Translator/Compiler/IL/ScaleIndex.hs:74:11-64:
 *   Irrefutable pattern failed for pattern Just ptoqt
 *
 * Every -O level, both data models, through a pointer or a plain struct.
 * What compiles: sizeof arithmetic on the struct, as the sources do
 * (src/aes/shel.c, sh_takes_apterm: p_msgs is PROC's last word).  Found
 * in phase 131, reading a field out of a copy of a process record kept
 * in far memory. */
#include <stdint.h>

struct b28 { int16_t x, m; } r_b28_v;

uint16_t r_b28_bug(void)
{
    return (uint16_t)((char *)&r_b28_v.m - (char *)&r_b28_v);
}
