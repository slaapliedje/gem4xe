/* mul32_sim.c -- products for tests/host/test_mul32.py, in the simulator.
 *
 * The operands come from a xorshift generator, which makes them with
 * shifts and exclusive-ors only -- no multiply -- so the routine under
 * test is not used to choose its own inputs.  First the edge cases, then
 * N pseudo-random pairs, a third of them cut to 16 bits and a third to
 * 8, so every path through _Mul32 (both high halves zero, one, neither)
 * is taken often.  Every product is folded into a checksum; the first
 * few are kept whole, for a failure to name.
 *
 * Built with -DTABLE for the link with ours: the table the routine made
 * on its first call, in its far variables, is folded too, by position. */
#include <stdint.h>

#ifdef TABLE
extern __far uint16_t mul32_sqr[511];
uint32_t m32_tsum;              /* the table, folded */
#endif

#define N 4000

static const int32_t edge[] = {
    0, 1, -1, 2, 255, 256, 65535, 65536, 65537, 0x7fffffffL,
    (int32_t)0x80000000UL, -65536L, -65535L, 0x12345678L, -0x12345678L,
    0x00ff00ffL, 0x0100ff01L, 46341L, -46341L, 0xffffL * 3
};
#define NEDGE ((int)(sizeof edge / sizeof edge[0]))

uint32_t m32_sum;               /* every product, folded */
uint32_t m32_first[8];          /* the first eight products, whole */
uint16_t m32_count;

static uint32_t xs = 0x2545f491UL;

static uint32_t next(void)
{
    xs ^= xs << 13;
    xs ^= xs >> 17;
    xs ^= xs << 5;
    return xs;
}

static void fold(uint32_t p)
{
    if (m32_count < 8)
        m32_first[m32_count] = p;
    m32_count++;
    m32_sum = ((m32_sum << 7) | (m32_sum >> 25)) ^ p;
}

int main(void)
{
    int i, j;
    uint32_t a, b, k;

    for (i = 0; i < NEDGE; i++)
        for (j = 0; j < NEDGE; j++)
            fold((uint32_t)(edge[i] * edge[j]));
    for (i = 0; i < N; i++) {
        a = next();
        b = next();
        k = next() % 3;
        if (k == 1) { a &= 0xffffUL; b &= 0xffffUL; }
        else if (k == 2) { a &= 0xffUL; b = (b & 1) ? (b & 0xffUL) : b; }
        fold(a * b);
        fold((uint32_t)((int32_t)a * (int32_t)b));
    }
#ifdef TABLE
    for (i = 0; i < 511; i++)
        m32_tsum = ((m32_tsum << 5) | (m32_tsum >> 27)) ^ mul32_sqr[i];
#endif
    return 0;
}
