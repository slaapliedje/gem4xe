/* pool.c -- bank $00's application pool.  See pool.h. */
#include "portab.h"
#include "sys/pool.h"
#include "sys/farmem.h"             /* far_owner: whose the next block is */
#include "sys/zwin.h"

/* The pool's bounds, from the linker (src/sys/apppool.s). */
extern const uint16_t app_pool_lo, app_pool_hi;

/* THE TABLE, sorted by address: three arrays rather than an array of a
 * struct, because a struct's size here is two numbers (Calypsi B7, the
 * memory notes) and five bytes an entry is what zwin can spare.  Free
 * space is what lies between the blocks and above the last. */
ZWIN uint16_t pb_at[POOL_MAX];
ZWIN uint16_t pb_len[POOL_MAX];
ZWIN uint8_t  pb_own[POOL_MAX];
ZWIN uint8_t  pb_tag[POOL_MAX];         /* far_tag's: kind and sub-pool */
ZWIN uint16_t pool_blocks;          /* zwin too: LoRAM is at its floor */
ZWIN uint16_t pool_full;

/* The top of the highest block, or the pool's foot: 0 until the first
 * call, because app_pool_lo is the linker's and not a constant here.  The
 * gates read it by this name, as they read the cursor it replaced. */
uint16_t pool_brk;
uint16_t pool_low;                  /* the floor: see pool.h */
uint16_t pool_refused;

static void pool_start(void)
{
    if (!pool_brk) {
        pool_brk = app_pool_lo;
        pool_low = app_pool_lo;
    }
}

static uint16_t pb_end(uint16_t i)
{
    return (uint16_t)(pb_at[i] + pb_len[i]);
}

/* The top is the last block's end -- the table is sorted -- or the foot. */
static void pool_settle(void)
{
    pool_brk = pool_blocks ? pb_end((uint16_t)(pool_blocks - 1)) : app_pool_lo;
}

/* Entry i made the block at..at+len, owner far_owner, the rest moved up. */
static void *pb_insert(uint16_t i, uint16_t at, uint16_t len)
{
    uint16_t k;

    if (pool_blocks >= POOL_MAX) {
        pool_full++;
        return 0;
    }
    for (k = pool_blocks; k > i; k--) {
        pb_at[k] = pb_at[k - 1];
        pb_len[k] = pb_len[k - 1];
        pb_own[k] = pb_own[k - 1];
        pb_tag[k] = pb_tag[k - 1];
    }
    pb_at[i] = at;
    pb_len[i] = len;
    pb_own[i] = far_owner;
    pb_tag[i] = far_tag;
    pool_blocks++;
    pool_settle();
    return (void *)at;
}

static void pb_remove(uint16_t i)
{
    pool_blocks--;
    for (; i < pool_blocks; i++) {
        pb_at[i] = pb_at[i + 1];
        pb_len[i] = pb_len[i + 1];
        pb_own[i] = pb_own[i + 1];
        pb_tag[i] = pb_tag[i + 1];
    }
    pool_settle();
}

/* Where `size` bytes aligned to `align` fit in [lo, hi), or 0.  A zero
 * size is a place and not a block: the old cursor handed one out without
 * moving, and so does this, without an entry. */
static uint16_t fit(uint16_t lo, uint16_t hi, uint16_t size, uint16_t align)
{
    uint16_t mask = (uint16_t)(align - 1);
    uint16_t base = (uint16_t)((lo + mask) & ~mask);

    if (base < lo || (uint32_t)base + size > hi)
        return 0;
    return base;
}

uint16_t pool_mark(void)
{
    pool_start();
    return pool_brk;
}

/* Everything taken so far is permanent. */
void pool_keep_mark(void)
{
    pool_low = pool_mark();
}

uint16_t pool_floor(void)
{
    pool_start();
    return pool_low;
}

void *pool_alloc(uint16_t size, uint16_t align)
{
    uint16_t base;

    pool_start();
    base = fit(pool_brk, app_pool_hi, size, align);
    if (!base)
        return 0;
    if (!size)
        return (void *)base;
    return pb_insert(pool_blocks, base, size);
}

/* The lowest gap first: below the first block, between two, above the
 * last -- so a program's near region goes back into the hole the last one
 * left, and the top stays for the stack-like takings. */
void *pool_take(uint16_t size, uint16_t align)
{
    uint16_t i, lo, hi, base;

    pool_start();
    if (!size)
        return pool_alloc(size, align);
    lo = app_pool_lo;
    for (i = 0; i <= pool_blocks; i++) {
        hi = i < pool_blocks ? pb_at[i] : app_pool_hi;
        base = fit(lo, hi, size, align);
        if (base)
            return pb_insert(i, base, size);
        if (i < pool_blocks)
            lo = pb_end(i);
    }
    return 0;
}

/* The current owner's blocks above `mark` go, and one that straddles it
 * ends there: what winding the cursor back did, for one owner. */
void pool_release(uint16_t mark)
{
    uint16_t i, own = far_owner;

    if (mark < pool_floor()) {
        pool_refused++;             /* somebody else's memory: see pool.h */
        return;
    }
    for (i = pool_blocks; i > 0; i--) {
        uint16_t k = (uint16_t)(i - 1), at = pb_at[k];
        if (pb_own[k] != own)
            continue;
        if (at >= mark)
            pb_remove(k);
        else if (pb_end(k) > mark) {
            pb_len[k] = (uint16_t)(mark - at);
            pool_settle();
        }
    }
}

uint16_t pool_free(void *block)
{
    uint16_t i, at = (uint16_t)block;

    for (i = 0; i < pool_blocks; i++)
        if (pb_at[i] == at) {
            pb_remove(i);
            return 1;
        }
    return 0;
}

void pool_free_owner(uint8_t owner)
{
    uint16_t i;

    if (!owner)
        return;                     /* the system's: never, as far_free_owner */
    for (i = pool_blocks; i > 0; i--)
        if (pb_own[i - 1] == owner)
            pb_remove((uint16_t)(i - 1));
}

/* One sub-pool of an owner (src/sys/farmem.h, far_free_sub). */
void pool_free_sub(uint8_t owner, uint8_t sub)
{
    uint16_t i;

    if (!owner || !sub)
        return;
    for (i = pool_blocks; i > 0; i--)
        if (pb_own[i - 1] == owner && OWN_SUB(pb_tag[i - 1]) == sub)
            pb_remove((uint16_t)(i - 1));
}

uint16_t pool_room(void)
{
    return (uint16_t)(app_pool_hi - pool_mark());
}
