/* pool_sim.c -- the bank-$00 pool, run through a script of requests.
 *
 * tests/host/test_pool.py writes the script (pool_script.h) and runs the
 * same one through tools/poolref.py: every answer here must be the
 * model's.  Each step is {op, a, b}; the `a` of a release or a free names
 * an EARLIER step, whose answer is the address.  After every step the
 * top is recorded too, and the table checked: sorted, inside the pool,
 * no two blocks overlapping.  Nothing is written to the pool's memory,
 * so its bounds can be anywhere.
 */
#include "portab.h"
#include "sys/pool.h"
#include "pool_script.h"        /* STEPS, script[STEPS][3], LO, HI */

const uint16_t app_pool_lo = LO, app_pool_hi = HI;
uint8_t far_owner, far_tag;

uint16_t pl_out[STEPS];
uint16_t pl_top[STEPS];
uint16_t pl_bad;                /* the first step after which the table was
                                 * wrong, plus one; 0 if never */

extern uint16_t pb_at[], pb_len[];

static uint16_t table_ok(void)
{
    uint16_t i;
    uint32_t end = LO;

    for (i = 0; i < pool_blocks; i++) {
        if (pb_at[i] < end || pb_len[i] == 0)
            return 0;
        end = (uint32_t)pb_at[i] + pb_len[i];
    }
    return end <= HI;
}

int main(void)
{
    uint16_t k;

    for (k = 0; k < STEPS; k++) {
        uint16_t op = script[k][0], a = script[k][1], b = script[k][2], r = 0;
        switch (op) {
        case 1: r = (uint16_t)pool_alloc(a, b); break;
        case 2: r = (uint16_t)pool_take(a, b); break;
        case 3: r = pool_mark(); break;
        case 4: pool_release(pl_out[a]); break;
        case 5: r = pool_free((void *)pl_out[a]); break;
        case 6: pool_free_owner((uint8_t)a); break;
        case 7: far_owner = (uint8_t)a; break;
        case 8: pool_keep_mark(); break;
        case 9: r = pool_room(); break;
        case 10: r = pool_refused; break;
        case 11: r = pool_full; break;
        case 12: pool_release(a); break;    /* a mark given as a number */
        case 13: far_tag = (uint8_t)a; break;
        case 14: pool_free_sub((uint8_t)a, (uint8_t)b); break;
        case 15: r = (uint16_t)pool_claim(a, b); break;
        }
        pl_out[k] = r;
        pl_top[k] = pool_mark();
        if (!pl_bad && !table_ok())
            pl_bad = (uint16_t)(k + 1);
    }
    return 0;
}
