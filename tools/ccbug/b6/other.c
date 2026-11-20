/* Callees, in their own file so the calls in bugs6.c cannot be inlined. */
#include <stdint.h>
typedef short WORD;

/* C4: says whether it got the tree and object its caller was given */
uint32_t c4_want;
int c4_take(uint32_t tree, WORD obj, uint32_t *spec, WORD *state, WORD *type,
            WORD *flags, int *t, WORD *th)
{ *spec = 0; *state = *type = *flags = *th = 0; *t = 0;
  return tree == c4_want && obj == 7; }

/* C5: returns the 32-bit value its two middle words make */
uint32_t c5_got;
WORD c5_take(WORD h, WORD f, WORD hi, WORD lo, WORD x, WORD y)
{ c5_got = ((uint32_t)(uint16_t)hi << 16) | (uint16_t)lo; return h + f + x + y; }

/* C6: records the pointer it was handed */
char *c6_got;
void c6_put(char *p, char v) { c6_got = p; *p = v; }
