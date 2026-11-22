/* minefld.c -- MINES' field, the game without the GEM.  See minefld.h.
 *
 * Written for cc65816 5.18 as well as the host's compiler, so it keeps
 * tools/ccbug's rules: no signed right shift (12), an array element read
 * into a scalar before it is combined (1, 13, 15), and no ?: into a
 * variable whose address is taken (9).
 */
#include "minefld.h"

uint8_t  mf_cell[MF_CELLS];
uint8_t  mf_w, mf_h, mf_state;
uint16_t mf_mines, mf_flags, mf_opened, mf_boom;
uint16_t mf_dirty[MF_CELLS];
uint16_t mf_ndirty;

static uint16_t stack[MF_CELLS];        /* the open's work: each square once */
static uint16_t nstack;
static uint32_t rs = 0x2545F491UL;      /* xorshift32's state, never 0 */

void mf_seed(uint32_t seed)
{
    rs = seed ? seed : 0x2545F491UL;
}

/* 0 .. n-1.  The high half of xorshift32, the better half. */
static uint16_t rnd(uint16_t n)
{
    uint32_t s = rs;
    uint16_t hi;

    s ^= s << 13;
    s ^= s >> 17;
    s ^= s << 5;
    rs = s;
    hi = (uint16_t)(s >> 16);
    return (uint16_t)(hi % n);
}

static void dirty(uint16_t i)
{
    if (mf_ndirty < MF_CELLS)
        mf_dirty[mf_ndirty++] = i;
}

/* The squares round square i: up to eight, into nb[], how many. */
static uint16_t round_of(uint16_t i, uint16_t *nb)
{
    uint16_t n = 0;
    int16_t x = (int16_t)(i % mf_w), y = (int16_t)(i / mf_w);
    int16_t dx, dy, nx, ny;

    for (dy = -1; dy <= 1; dy++) {
        ny = (int16_t)(y + dy);
        if (ny < 0 || ny >= (int16_t)mf_h)
            continue;
        for (dx = -1; dx <= 1; dx++) {
            nx = (int16_t)(x + dx);
            if ((dx == 0 && dy == 0) || nx < 0 || nx >= (int16_t)mf_w)
                continue;
            nb[n++] = (uint16_t)((uint16_t)ny * mf_w + (uint16_t)nx);
        }
    }
    return n;
}

void mf_new(uint8_t w, uint8_t h, uint16_t mines)
{
    uint16_t i, cells;

    if (w > MF_MAXW)
        w = MF_MAXW;
    if (h > MF_MAXH)
        h = MF_MAXH;
    cells = (uint16_t)((uint16_t)w * h);
    if (mines >= cells)
        mines = (uint16_t)(cells - 1);
    mf_w = w;
    mf_h = h;
    mf_mines = mines;
    mf_flags = 0;
    mf_opened = 0;
    mf_boom = 0xFFFF;
    mf_ndirty = 0;
    mf_state = MF_FRESH;
    for (i = 0; i < MF_CELLS; i++)
        mf_cell[i] = 0;
}

/* The mines laid, clear of `first` and -- if the field has room -- of
 * the squares round it; then every square's count.  The squares kept
 * clear are marked in the field itself while the mines go down (KEEP,
 * a bit no square uses), which saves the program 480 bytes of bank $00. */
#define KEEP 0x80

static void lay(uint16_t first)
{
    uint16_t cells = (uint16_t)((uint16_t)mf_w * mf_h);
    uint16_t nb[8], n, k, i, laid = 0, wide;

    {
        uint8_t v = mf_cell[first];     /* a flag put up before stays */

        mf_cell[first] = (uint8_t)(v | KEEP);
    }
    wide = (uint16_t)(cells - mf_mines >= 9);
    if (wide) {
        n = round_of(first, nb);
        for (k = 0; k < n; k++) {
            uint8_t v;

            i = nb[k];
            v = mf_cell[i];
            mf_cell[i] = (uint8_t)(v | KEEP);
        }
    }
    while (laid < mf_mines) {
        uint8_t v;

        i = rnd(cells);
        v = mf_cell[i];
        if (v & (KEEP | MF_MINE))
            continue;
        mf_cell[i] = (uint8_t)(v | MF_MINE);
        laid++;
    }
    for (i = 0; i < cells; i++) {
        uint8_t v = mf_cell[i];

        mf_cell[i] = (uint8_t)(v & ~KEEP);
    }
    for (i = 0; i < cells; i++) {
        uint8_t v = mf_cell[i], c = 0;

        n = round_of(i, nb);
        for (k = 0; k < n; k++) {
            uint16_t j = nb[k];
            uint8_t u = mf_cell[j];

            if (u & MF_MINE)
                c++;
        }
        mf_cell[i] = (uint8_t)(v | c);
    }
    mf_state = MF_PLAYING;
}

/* Lost on square i: every mine shown, and every flag that was wrong. */
static void lose(uint16_t i)
{
    uint16_t cells = (uint16_t)((uint16_t)mf_w * mf_h), k;

    mf_boom = i;
    mf_state = MF_LOST;
    for (k = 0; k < cells; k++) {
        uint8_t v = mf_cell[k];

        if ((v & MF_MINE) && !(v & MF_FLAG)) {
            mf_cell[k] = (uint8_t)(v | MF_OPEN);
            dirty(k);
        } else if (!(v & MF_MINE) && (v & MF_FLAG)) {
            dirty(k);                   /* drawn as a mistake */
        }
    }
}

/* Every square that is not a mine open: won, and the mines flagged. */
static void check_won(void)
{
    uint16_t cells = (uint16_t)((uint16_t)mf_w * mf_h), k;

    if (mf_state != MF_PLAYING || mf_opened != (uint16_t)(cells - mf_mines))
        return;
    mf_state = MF_WON;
    for (k = 0; k < cells; k++) {
        uint8_t v = mf_cell[k];

        if ((v & MF_MINE) && !(v & MF_FLAG)) {
            mf_cell[k] = (uint8_t)(v | MF_FLAG);
            mf_flags++;
            dirty(k);
        }
    }
}

/* Square i opened, and the empty country round it.  A square is marked
 * open as it is PUSHED, so none is pushed twice and the stack holds. */
static void open_one(uint16_t i)
{
    uint16_t nb[8], n, k;
    uint8_t v = mf_cell[i];

    if (v & (MF_OPEN | MF_FLAG))
        return;
    if (v & MF_MINE) {
        lose(i);
        return;
    }
    mf_cell[i] = (uint8_t)(v | MF_OPEN);
    mf_opened++;
    dirty(i);
    if (v & MF_COUNT)
        return;
    nstack = 0;
    stack[nstack++] = i;
    while (nstack) {
        uint16_t j = stack[--nstack];

        n = round_of(j, nb);
        for (k = 0; k < n; k++) {
            uint16_t m = nb[k];
            uint8_t u = mf_cell[m];

            if (u & (MF_OPEN | MF_FLAG | MF_MINE))
                continue;
            mf_cell[m] = (uint8_t)(u | MF_OPEN);
            mf_opened++;
            dirty(m);
            if (!(u & MF_COUNT))
                stack[nstack++] = m;
        }
    }
}

static uint16_t at(uint8_t x, uint8_t y)
{
    return (uint16_t)((uint16_t)y * mf_w + x);
}

void mf_open(uint8_t x, uint8_t y)
{
    uint16_t i;

    mf_ndirty = 0;
    if (x >= mf_w || y >= mf_h || mf_state == MF_WON || mf_state == MF_LOST)
        return;
    i = at(x, y);
    if (mf_cell[i] & MF_FLAG)
        return;
    if (mf_state == MF_FRESH)
        lay(i);
    open_one(i);
    check_won();
}

void mf_flag(uint8_t x, uint8_t y)
{
    uint16_t i;
    uint8_t v;

    mf_ndirty = 0;
    if (x >= mf_w || y >= mf_h || mf_state == MF_WON || mf_state == MF_LOST)
        return;
    i = at(x, y);
    v = mf_cell[i];
    if (v & MF_OPEN)
        return;
    if (v & MF_FLAG) {
        mf_cell[i] = (uint8_t)(v & ~MF_FLAG);
        mf_flags--;
    } else {
        mf_cell[i] = (uint8_t)(v | MF_FLAG);
        mf_flags++;
    }
    dirty(i);
}

void mf_chord(uint8_t x, uint8_t y)
{
    uint16_t nb[8], n, k, i, flags = 0;
    uint8_t v;

    mf_ndirty = 0;
    if (x >= mf_w || y >= mf_h || mf_state != MF_PLAYING)
        return;
    i = at(x, y);
    v = mf_cell[i];
    if (!(v & MF_OPEN) || !(v & MF_COUNT))
        return;
    n = round_of(i, nb);
    for (k = 0; k < n; k++) {
        uint16_t j = nb[k];
        uint8_t u = mf_cell[j];

        if (u & MF_FLAG)
            flags++;
    }
    if (flags != (uint16_t)(v & MF_COUNT))
        return;
    for (k = 0; k < n && mf_state == MF_PLAYING; k++)
        open_one(nb[k]);
    check_won();
}
