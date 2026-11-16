/* c6_procs.c -- the two contexts of src/c6_ctx.c, each in a bank of its
 * own: proc_a and its recursion in `cxa` (the wrapper's section), proc_b
 * in `cxb`.  test-m27's (src/m27_ctx.c), letter for letter.
 */
#include "portab.h"
#include <stdint.h>
#include "sys/ctx.h"

#define ROUNDS  5
#define DEEP    6

void note(uint16_t who);        /* src/c6_ctx.c, resident */
extern uint16_t deep_put[], deep_got[], deep_bad, rounds_a, rounds_b;
extern CTX c_a, c_b;

/* Down DEEP frames, switch away from the bottom, check every level on the
 * way back up.  `mine` is live across the call, so it is in one of the
 * compiler's saved registers, which each frame keeps on the C stack. */
static void recurse(uint16_t level)
{
    uint16_t mine = (uint16_t)(0xC000 + level * 7);

    deep_put[level] = mine;
    if (level + 1 < DEEP)
        recurse((uint16_t)(level + 1));
    else
        ctx_switch(&c_b);           /* the deepest frame yields */
    deep_got[level] = mine;
    if (mine != (uint16_t)(0xC000 + level * 7))
        deep_bad++;
}

int16_t proc_a(void)
{
    uint16_t i;

    for (i = 0; i < ROUNDS; i++) {
        note(1);
        rounds_a++;
        ctx_switch(&c_b);
    }
    recurse(0);
    note(0x11);
    return 0;                       /* done: ctx_boot hands back to the root */
}

BANK_TEXT("cxb")

int16_t proc_b(void)
{
    for (;;) {
        note(2);
        rounds_b++;
        ctx_switch(&c_a);
    }
}
