/* farmem_sim.c -- the far allocator, run through a script of requests.
 *
 * tests/host/test_farmem.py writes the script (farmem_script.h) and runs
 * the same one through tools/farref.py: every answer here must be the
 * model's.  Each step is {op, a, b}; `a` of a free or a shrink names an
 * EARLIER step, whose answer is the address.  After every step the whole
 * table is checked: sorted, no two blocks overlapping, and no block made
 * by far_alloc crossing a bank -- a far pointer's arithmetic is sixteen
 * bits, so one that did would wrap into the bottom of its own bank
 * (docs/phase24.md).
 *
 * The loader's symbol is stubbed: nothing here probes hardware.
 */
#include "portab.h"
#include "sys/farmem.h"
#include "farmem_script.h"      /* STEPS, script[STEPS][3], FIRST, LAST */

const uint8_t _fl_top[3] = { 0, 0, 1 };     /* the image ends in bank $01 */

uint32_t fm_out[STEPS];
uint16_t fm_bad;                /* the first step after which the table was
                                 * wrong, plus one; 0 if never */
uint16_t fm_crossed;            /* far_alloc blocks that cross a bank */

typedef struct { uint32_t at, len; } FBLK;

static uint16_t table_ok(void)
{
    uint16_t i;
    uint32_t end = 0;
    const FBLK FAR *t = (const FBLK FAR *)far_table;

    for (i = 0; i < far_blocks; i++) {
        uint32_t a = t[i].at & 0xFFFFFFUL, n = t[i].len;
        if (a < end)
            return 0;
        end = a + ((n + 3) & ~3UL);
    }
    return 1;
}

int main(void)
{
    uint16_t k;

    farmem.kind = FARMEM_RAPIDUS;
    farmem.first_bank = FIRST;
    farmem.last_bank = LAST;
    farmem.banks = (uint8_t)(LAST - FIRST + 1);
    farmem.bytes = (uint32_t)farmem.banks << 16;
    far_heap_init();
    for (k = 0; k < STEPS; k++) {
        uint32_t op = script[k][0], a = script[k][1], b = script[k][2], r = 0;
        switch ((uint16_t)op) {
        case 1: r = far_alloc(a);
                if (r && (r >> 16) != ((r + a - 1) >> 16))
                    fm_crossed++;
                break;
        case 2: r = far_alloc_span(a); break;
        case 3: r = far_alloc_page(a, b); break;
        case 4: r = far_alloc_banks((uint16_t)a); break;
        case 5: r = far_free(fm_out[a]); break;
        case 6: far_free_owner((uint8_t)a); break;
        case 7: r = far_shrink(fm_out[a], b); break;
        case 8: far_owner = (uint8_t)a; break;
        case 9: r = far_largest((uint16_t)a); break;
        }
        fm_out[k] = r;
        if (!fm_bad && !table_ok())
            fm_bad = (uint16_t)(k + 1);
    }
    return 0;
}
