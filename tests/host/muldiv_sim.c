/* muldiv_sim.c -- quotients for tests/host/test_muldiv.py, in the simulator.
 *
 * umuldiv(a, b, c) under its contract (src/sys/muldiv.s): c not zero and
 * a <= c, which is how clc_flit calls it (|t| <= |dy|) and which keeps
 * the quotient at most b.  Edge values first, then N pseudo-random
 * triples, a third of them with a divisor under 256.  Every quotient is
 * folded into a checksum; the first few are kept whole.
 *
 * Then flit_scan, the polygon filler's scan line, against flit_ref: the
 * C loop it replaced (src/vdi/vdi.c's flit_small before it), over random
 * polygons inside clc_flit's +-16383 and a zigzag that crosses one line
 * more often than MAX_INTERSECT allows.  Every disagreement is counted. */
#include <stdint.h>

extern uint16_t umuldiv(uint16_t a, uint16_t b, uint16_t c);
extern int16_t flit_scan(const int16_t *pt, int16_t vectors, int16_t y,
                         int16_t *out);

#define MAX_INTERSECT 32                /* src/vdi/vdi.c's */
#define POLYS 60
#define ROWS 24

uint16_t fl_bad;                /* scan lines where the two disagree */
uint16_t fl_rows;               /* scan lines compared */
uint16_t fl_hits;               /* crossings found, all told */
static int16_t pt[2 * 72 + 2];
static int16_t got[MAX_INTERSECT], want[MAX_INTERSECT];

#define N 3000

static const uint16_t edge_c[] = {1, 2, 3, 255, 256, 32766, 32767, 65535};
static const uint16_t edge_b[] = {0, 1, 2, 12345, 32768, 65532, 65535};

uint32_t md_sum;
uint16_t md_first[8];
uint16_t md_count;

static uint32_t xs = 0x2545f491UL;

static uint32_t next(void)
{
    xs ^= xs << 13;
    xs ^= xs >> 17;
    xs ^= xs << 5;
    return xs;
}

static void fold(uint16_t q)
{
    if (md_count < 8)
        md_first[md_count] = q;
    md_count++;
    md_sum = ((md_sum << 7) | (md_sum >> 25)) ^ q;
}

static uint16_t uabs(int16_t v)
{
    return v < 0 ? (uint16_t)(0u - (uint16_t)v) : (uint16_t)v;
}

static int16_t asr1(int16_t v)
{
    if (v >= 0)
        return (int16_t)((uint16_t)v >> 1);
    return (int16_t)(-(int16_t)(((uint16_t)(-v) + 1u) >> 1));
}

static int16_t flit_ref(const int16_t *pts, int16_t vectors, int16_t y,
                        int16_t *out)
{
    const int16_t *p = pts;
    int16_t i, n = 0;

    for (i = vectors; i > 0; i--, p += 2) {
        int16_t y1 = p[1], y2 = p[3], x1, x2;
        uint16_t q, dy;

        if (y1 < y2) {
            if (y < y1 || y >= y2)
                continue;
            dy = (uint16_t)(y2 - y1);
        } else {
            if (y < y2 || y >= y1)
                continue;
            dy = (uint16_t)(y1 - y2);
        }
        if (n >= MAX_INTERSECT)
            break;
        x1 = p[0];
        x2 = p[2];
        if (x2 < x1) {
            q = umuldiv(uabs((int16_t)(y - y2)), (uint16_t)((uint16_t)(x1 - x2) << 1), dy);
            x1 = x2;
        } else {
            q = umuldiv(uabs((int16_t)(y - y1)), (uint16_t)((uint16_t)(x2 - x1) << 1), dy);
        }
        out[n++] = (int16_t)(asr1((int16_t)((int16_t)q + 1)) + x1);
    }
    return n;
}

static void compare(int16_t v, int16_t y)
{
    int16_t a = flit_scan(pt, v, y, got), b = flit_ref(pt, v, y, want), i;
    int bad = a != b;

    for (i = 0; !bad && i < b; i++)
        bad = got[i] != want[i];
    fl_bad += bad;
    fl_rows++;
    fl_hits += (uint16_t)b;
}

/* a coordinate: mostly on and around the screen, sometimes far out */
static int16_t coord(int16_t lo, int16_t span)
{
    uint32_t r = next();

    if ((r & 15) == 0)
        return (int16_t)((int32_t)(r >> 8) % 32767 - 16383);
    return (int16_t)(lo + (int16_t)((r >> 8) % (uint32_t)span));
}

static void flit_test(void)
{
    int16_t k, v, i, y;

    for (k = 0; k < POLYS; k++) {
        v = (int16_t)(3 + next() % 70);
        for (i = 0; i < v; i++) {
            pt[2 * i] = coord(-40, 720);
            pt[2 * i + 1] = coord(-20, 280);
        }
        pt[2 * v] = pt[0];
        pt[2 * v + 1] = pt[1];
        for (i = 0; i < ROWS; i++) {
            y = (int16_t)((int16_t)(next() % 241) - 1);
            compare(v, y);
        }
    }
    /* a zigzag across y = 100, 70 edges: 70 crossings, 32 kept */
    for (i = 0; i <= 70; i++) {
        pt[2 * i] = (int16_t)(i * 9);
        pt[2 * i + 1] = (i & 1) ? 150 : 50;
    }
    pt[2 * 71] = pt[0];
    pt[2 * 71 + 1] = pt[1];
    for (y = 40; y < 160; y += 7)
        compare(71, y);
}

int main(void)
{
    unsigned i, j, k;
    uint16_t a, b, c;

    for (i = 0; i < sizeof edge_c / sizeof edge_c[0]; i++)
        for (j = 0; j < sizeof edge_b / sizeof edge_b[0]; j++) {
            c = edge_c[i];
            b = edge_b[j];
            fold(umuldiv(0, b, c));
            fold(umuldiv(1, b, c));
            fold(umuldiv((uint16_t)(c / 2), b, c));
            fold(umuldiv((uint16_t)(c - 1), b, c));
            fold(umuldiv(c, b, c));
        }
    for (k = 0; k < N; k++) {
        c = (uint16_t)next();
        if (next() % 3 == 0)
            c &= 0xff;
        if (!c)
            c = 1;
        b = (uint16_t)next();
        a = (uint16_t)next();
        if (c != 0xffff)
            a = (uint16_t)(a % (uint16_t)(c + 1));
        fold(umuldiv(a, b, c));
    }
    flit_test();
    return 0;
}
