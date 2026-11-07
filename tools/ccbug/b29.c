/* B29 -- a member's address cast to an integer is an internal compiler
 * error:
 *
 *   internal error: Translator/Compiler/IL/Evaluate.hs:370:11-54:
 *   Irrefutable pattern failed for pattern (trail, LoadConst _ e)
 *
 * Every -O level, both data models, to a 16- or a 32-bit integer.  The
 * member's address as a pointer compiles (`return &p->m;`); it is the
 * cast to a number that the constant evaluator cannot take.  Found in
 * phase 131, the second try at B28's offset. */
#include <stdint.h>

struct b29 { int16_t x, m; } *r_b29_p;

uint16_t r_b29_bug(void)
{
    return (uint16_t)&r_b29_p->m;
}
