/* farmem.c -- linear RAM above bank $00: reached, and handed out.
 *
 * Which banks there are is found by src/sys/hiprobe.c, the Atari's part;
 * this file is the allocator and the far-memory helpers, and knows nothing
 * of the machine beyond FARMEM's first and last bank. */
#include "portab.h"
#include "farmem.h"
#include "zwin.h"

/* Calypsi wants the address-space qualifier AFTER the base type in a
 * declarator: `uint8_t FAR *p`, not `FAR uint8_t *p`.  The latter parses
 * at file scope but is rejected as a local, which is a confusing way to find
 * out. */

FARMEM farmem;


void far_write8(uint32_t addr, uint8_t v)
{
    uint8_t FAR *p = (uint8_t FAR *)addr;
    *p = v;
}

uint8_t far_read8(uint32_t addr)
{
    uint8_t FAR *p = (uint8_t FAR *)addr;
    return *p;
}

void far_put(uint32_t dst, const uint8_t *src, uint16_t len)
{
    uint8_t FAR *p = (uint8_t FAR *)dst;
    while (len--)
        *p++ = *src++;
}

void far_get(uint8_t *dst, uint32_t src, uint16_t len)
{
    uint8_t FAR *p = (uint8_t FAR *)src;
    while (len--)
        *dst++ = *p++;
}

/* Far to far, ascending: the AES's shell buffer and an application's
 * copy of it both live above bank $00 (shel_get, shel_put). */
void far_copy(uint32_t dst, uint32_t src, uint16_t len)
{
    uint8_t FAR *d = (uint8_t FAR *)dst;
    const uint8_t FAR *s = (const uint8_t FAR *)src;
    while (len--)
        *d++ = *s++;
}

/* Far fill (the shell buffer's clearing). */
void far_fill(uint32_t dst, uint8_t v, uint16_t len)
{
    uint8_t FAR *d = (uint8_t FAR *)dst;
    while (len--)
        *d++ = v;
}

/* Bounded strcpy across the bank boundary, both ways: a string an
 * application hands the AES lives in far memory and the AES's own
 * buffers are sized, so neither copy may run past `max` with its NUL. */
void far_strget(char *dst, uint32_t src, uint16_t max)
{
    const char FAR *p = (const char FAR *)src;
    uint16_t k;
    for (k = 0; k + 1 < max && p[k]; k++)
        dst[k] = p[k];
    dst[k] = 0;
}

void far_strput(uint32_t dst, const char *src, uint16_t max)
{
    char FAR *p = (char FAR *)dst;
    uint16_t k;
    for (k = 0; k + 1 < max && src[k]; k++)
        p[k] = src[k];
    p[k] = 0;
}

/* -- A FAR POINTER'S ARITHMETIC IS SIXTEEN BITS.
 *
 * This is the fact the three functions below exist for, and it is worth
 * stating plainly because it is not what "24-bit pointer" suggests and
 * because getting it wrong is silent.  Calypsi compiles `p + n` on a
 * `__far` pointer as a 16-bit add to the OFFSET with the bank byte
 * loaded unchanged -- the carry is dropped:
 *
 *     clc
 *     lda  _Dp        ; the offset
 *     adc  _Dp+4      ; + n, low 16 bits only
 *     sta  _Dp
 *     lda  _Dp+2      ; the bank, UNTOUCHED
 *
 * So a walk that runs off the top of a bank comes back at its bottom and
 * reads somebody else's memory.  (The manual is consistent with this and
 * says so obliquely: a `far` OBJECT is capped at 64K minus one byte.
 * Crossing banks is what the `huge` attribute is for, and it widens
 * size_t to 32 bits everywhere, which is not a trade this system makes.)
 *
 * far_alloc's rule follows from it: nothing it hands out crosses a bank,
 * so anything allocated there can be walked with an ordinary far pointer.
 * far_put, far_get and far_copy above are correct for exactly that.
 *
 * A block that MAY straddle a bank, for the one thing that has to: a
 * file read into far memory whole (far_read_file).  far_alloc will not
 * give one, and a file bigger than the room left in the current bank
 * therefore could not be read AT ALL -- which went unnoticed for as long
 * as it did because every file gem4xe had loaded was a few KB.  GACS's
 * shell is 139 KB, and the failure it gave was APP_E_FILE, which reads
 * like a missing file.
 *
 * What lives here must be reached by RECOMPUTING the address for each
 * access -- far_read8, far_write8, far_copy_span -- and never by walking
 * a pointer across the boundary. */
/* Bank-safe copies, for what far_alloc_span handed out: the address is
 * rebuilt at every bank boundary instead of being walked over it.  The
 * inner copies are the ordinary far_put/far_copy, which are correct
 * because each call is given a run that stays inside one bank. */
void far_put_span(uint32_t dst, const uint8_t *src, uint16_t len)
{
    while (len) {
        uint32_t room = 0x10000UL - (dst & 0xFFFFUL);
        uint16_t k = (room >= len) ? len : (uint16_t)room;
        far_put(dst, src, k);
        dst += k;
        src += k;
        len = (uint16_t)(len - k);
    }
}

void far_copy_span(uint32_t dst, uint32_t src, uint32_t len)
{
    while (len) {
        uint32_t droom = 0x10000UL - (dst & 0xFFFFUL);
        uint32_t sroom = 0x10000UL - (src & 0xFFFFUL);
        uint32_t k = len;
        if (k > droom) k = droom;
        if (k > sroom) k = sroom;
        if (k > 0x4000UL) k = 0x4000UL;     /* a uint16_t can count it */
        far_copy(dst, src, (uint16_t)k);
        dst += k;
        src += k;
        len -= k;
    }
}


/* ---------------------------------------------------------------------------
 * THE ALLOCATOR -- blocks with owners, freed in any order (phase 79).
 *
 * It was a bump pointer with marks until 0.9.2, which could only give
 * back the top of the heap and so needed every release to be the reverse
 * of the takes.  Its cost was measured on a 65C816 with 960K: an
 * accessory of 4 KB took two whole banks, a resource loaded between two
 * programs started another, and the desktop never got its turn
 * (docs/phase78.md).  Now:
 *
 *   A TABLE OF BLOCKS, sorted by address, in the first bank of the heap
 *   (it is block 0, the system's).  Free space is what lies between them
 *   -- there is no second list to keep in step with the first.  Each
 *   entry is the address with its OWNER in the top byte, and the length.
 *
 *   OWNERS.  0 is the system: the shell's buffers, the desktop's cached
 *   file, the table.  Every program app_load takes in gets one of its
 *   own (far_new_owner), and far_owner says whose the next block is --
 *   src/sys/ctx.c sets it at every switch, so a block an accessory asks
 *   for at run time is the accessory's.  A program's exit frees its owner
 *   (far_free_owner); an accessory's is never freed, which is what made it
 *   permanent, where the bump allocator needed a floor for that.
 *
 *   FOUR KINDS OF REQUEST, each the lowest that fits:
 *     far_alloc        4-aligned, never across a bank (a far pointer's
 *                      arithmetic is sixteen bits, the note above)
 *     far_alloc_span   4-aligned, MAY cross: a file read whole
 *     far_alloc_page   page-aligned, and ending at or below `limit` in its
 *                      bank: a program's code relocated by pages, which
 *                      must stay under the $D5 page (src/gem4xe.scm)
 *     far_alloc_banks  whole banks, the LOWEST free run (on a Rapidus the
 *                      top of the heap is cached SDRAM; the reason is at
 *                      the function)
 *
 * tools/farref.py is the same rules in Python -- the model the desktop
 * gates place the desktop with, held to this file by test_farmem.py.
 */
#define FB_MAX      256                 /* blocks; the table is 2 KB */
#define FB_ADDR     0x00FFFFFCUL        /* every block is 4-aligned, so */
#define FB_PURGE    0x00000003UL        /* the low bits are its purge level */
#define FB_LEN      0x00FFFFFFUL        /* the tag is len's top byte */

typedef struct {
    uint32_t at;                        /* owner << 24 | address */
    /* len:  tag << 24 | length (phase 119) -- a block is never 16 MB */
    uint32_t len;
} FBLK;

uint8_t  far_owner;
ZWIN uint16_t far_purged;               /* blocks purged, ever: the gates */
ZWIN void (*far_purge_hook)(uint32_t addr);     /* zwin: LoRAM's floor */
ZWIN uint8_t far_tag;                   /* zwin: LoRAM is at its floor */
uint16_t far_blocks;
uint32_t far_table;

#define FB(i)       (((FBLK FAR *)far_table)[i])

static uint32_t heap_lo(void) { return (uint32_t)farmem.first_bank << 16; }
static uint32_t heap_hi(void) { return (uint32_t)(farmem.last_bank + 1) << 16; }

static uint32_t fb_start(uint16_t i)
{
    uint32_t at = FB(i).at;
    return at & FB_ADDR;
}

static uint32_t fb_end(uint16_t i)
{
    uint32_t len = FB(i).len & FB_LEN;
    return fb_start(i) + ((len + 3) & ~3UL);
}

/* The gap before entry i (i == far_blocks: the gap above the last). */
static uint32_t gap_lo(uint16_t i) { return i ? fb_end((uint16_t)(i - 1)) : heap_lo(); }
static uint32_t gap_hi(uint16_t i) { return i < far_blocks ? fb_start(i) : heap_hi(); }

/* Entry i made the block at..at+len, owner far_owner, the rest moved up. */
static uint32_t fb_insert(uint16_t i, uint32_t at, uint32_t len)
{
    uint16_t k;
    FBLK e;

    if (far_blocks >= FB_MAX)
        return 0;
    for (k = far_blocks; k > i; k--) {
        e = FB(k - 1);
        FB(k) = e;
    }
    e.at = at | ((uint32_t)far_owner << 24);
    e.len = len | ((uint32_t)far_tag << 24);
    FB(i) = e;
    far_blocks++;
    return at;
}

static void fb_remove(uint16_t i)
{
    FBLK e;

    far_blocks--;
    for (; i < far_blocks; i++) {
        e = FB(i + 1);
        FB(i) = e;
    }
}

/* No heap at all, until the probe has found one (src/sys/hiprobe.c). */
void far_heap_clear(void)
{
    far_blocks = 0;
    far_table = 0;
}

void far_heap_init(void)
{
    uint8_t keep = far_owner, keept = far_tag;

    far_blocks = 0;
    far_table = 0;
    far_owner = 0;
    far_tag = 0;
    if (!farmem.banks)
        return;
    far_table = heap_lo();
    fb_insert(0, far_table, (uint32_t)FB_MAX * sizeof(FBLK));
    far_owner = keep;
    far_tag = keept;
}

/* Where a request of `bytes` fits in [lo, hi), or 0.
 *   how 0: 4-aligned, inside one bank      2: page-aligned, below `limit`
 *   how 1: 4-aligned, may cross banks          in its bank */
static uint32_t fit(uint32_t lo, uint32_t hi, uint32_t bytes, uint16_t how,
                    uint32_t limit)
{
    uint32_t a;

    if (how == 2) {
        a = (lo + 0xFFUL) & ~0xFFUL;
        if ((a & 0xFFFFUL) + bytes > limit)
            a = (a | 0xFFFFUL) + 1;     /* the next bank's foot */
        if ((a & 0xFFFFUL) + bytes > limit)
            return 0;
    } else {
        a = (lo + 3) & ~3UL;
        if (how == 0 && (a & 0xFFFFUL) + bytes > 0x10000UL)
            a = (a | 0xFFFFUL) + 1;
    }
    if (a < lo || a + bytes > hi || a + bytes < a)
        return 0;
    return a;
}

/* PURGING (phase 120).  A block's purge level is 0, never purged -- every
 * block unless somebody says otherwise -- or 1 to 3, GS/OS's: memory that
 * is worth keeping only while nobody needs the room, 3 the first to go.
 * When a request does not fit, every block of level 3 is purged and the
 * request tried again, then every block of level 2, then level 1, and only
 * then is it refused.  Each purged block is named to far_purge_hook, so
 * that whoever kept it as a cache forgets it: there are no handles here
 * to set to nil, and an address that is gone may be given out again.
 *
 * A level at a time rather than a block at a time, as GS/OS does it:
 * which block of a level to give up first would be a guess, and the
 * levels are the owner's own say in the matter. */
static uint16_t purge_level(uint16_t level)
{
    uint16_t i = 1, n = 0;

    while (i < far_blocks) {
        uint32_t at = FB(i).at;
        if ((uint16_t)(at & FB_PURGE) == level) {
            fb_remove(i);
            n++;
            far_purged++;
            if (far_purge_hook)
                far_purge_hook(at & FB_ADDR);
        } else {
            i++;
        }
    }
    return n;
}

/* The next level down that had anything to purge, purged: 1 if a request
 * is worth trying again.  *level starts at 4. */
static uint16_t purge_next(uint16_t *level)
{
    while (*level > 1) {
        (*level)--;
        if (purge_level(*level))
            return 1;
    }
    return 0;
}

/* The block at addr becomes `owner`'s, with `tag`: a dormant desktop's
 * image handed to the system and back (src/sys/app.c app_keep, phase
 * 121).  Its purge level stays as it was.  1 if it was a block. */
uint16_t far_adopt(uint32_t addr, uint8_t owner, uint8_t tag)
{
    uint16_t i;
    uint32_t v;

    for (i = 1; i < far_blocks; i++)
        if (fb_start(i) == addr) {
            v = FB(i).at;
            v = (v & ~0xFF000000UL) | ((uint32_t)owner << 24);
            FB(i).at = v;
            v = FB(i).len;
            v = (v & FB_LEN) | ((uint32_t)tag << 24);
            FB(i).len = v;
            return 1;
        }
    return 0;
}

uint16_t far_set_purge(uint32_t addr, uint16_t level)
{
    uint16_t i;
    uint32_t at;

    for (i = 1; i < far_blocks; i++)
        if (fb_start(i) == addr) {
            at = FB(i).at;
            at = (at & ~FB_PURGE) | (level & FB_PURGE);
            FB(i).at = at;
            return 1;
        }
    return 0;
}

static uint32_t take1(uint32_t bytes, uint16_t how, uint32_t limit)
{
    uint16_t i;
    uint32_t a;

    if (!far_table || bytes == 0)
        return 0;
    if (how == 0 && bytes > 0x10000UL)  /* no block can be indexed past */
        return 0;                       /* its own bank */
    for (i = 0; i <= far_blocks; i++) {
        a = fit(gap_lo(i), gap_hi(i), bytes, how, limit);
        if (a)
            return fb_insert(i, a, bytes);
    }
    return 0;
}

static uint32_t take(uint32_t bytes, uint16_t how, uint32_t limit)
{
    uint16_t level = 4;
    uint32_t a;

    while (!(a = take1(bytes, how, limit)) && purge_next(&level))
        ;
    return a;
}

uint32_t far_alloc(uint32_t bytes)       { return take(bytes, 0, 0); }
uint32_t far_alloc_span(uint32_t bytes)  { return take(bytes, 1, 0); }
uint32_t far_alloc_page(uint32_t bytes, uint32_t limit)
{
    return take(bytes, 2, limit);
}

/* Exactly at..at+bytes, or 0 if any of it is taken or outside the heap:
 * for memory a foreign program finds by ADDRESS, not by asking -- an Apple
 * IIGS program calls the Toolbox at $E1:0000 and draws at $E1:2000
 * (GSlayer, Mclaim in src/sys/gemdos.c).  `at` is rounded down and the
 * end up to 4, as every block's are. */
static uint32_t claim1(uint32_t at, uint32_t bytes);

uint32_t far_claim(uint32_t at, uint32_t bytes)
{
    uint16_t level = 4;
    uint32_t a;

    while (!(a = claim1(at, bytes)) && purge_next(&level))
        ;
    return a;
}

static uint32_t claim1(uint32_t at, uint32_t bytes)
{
    uint16_t i;
    uint32_t end;

    if (!far_table || bytes == 0)
        return 0;
    end = at + bytes;
    at &= ~3UL;
    if (end < at)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        if (gap_hi(i) <= at)
            continue;
        if (gap_lo(i) > at || end > gap_hi(i))
            return 0;
        return fb_insert(i, at, end - at);
    }
    return 0;
}

/* ...and at the TOP of the highest gap it fits, which may cross banks:
 * for a block that lives only a moment -- the span a squeezed program is
 * unpacked into (src/sys/app.c, phase 94) -- so that what is placed while
 * it lives goes where it would have gone without it.  Taken low, it put
 * every boot-time program above it and left the hole under them when it
 * went (test-m37: the boot past three banks).  Data only, never code, so
 * the SDRAM cache worry below does not reach it. */
static uint32_t top1(uint32_t bytes);

uint32_t far_alloc_top(uint32_t bytes)
{
    uint16_t level = 4;
    uint32_t a;

    while (!(a = top1(bytes)) && purge_next(&level))
        ;
    return a;
}

static uint32_t top1(uint32_t bytes)
{
    uint16_t i;
    uint32_t lo, hi, a;

    if (!far_table || bytes == 0)
        return 0;
    for (i = (uint16_t)(far_blocks + 1); i-- > 0; ) {
        lo = gap_lo(i);
        hi = gap_hi(i);
        if (hi - lo < bytes)
            continue;
        a = (hi - bytes) & ~3UL;
        if (a < lo)
            continue;
        return fb_insert(i, a, bytes);
    }
    return 0;
}

/* n whole banks, the LOWEST run that is free: the first bank's number.
 * Low, not from the top where they would keep out of the small blocks'
 * way: on a Rapidus the top of the heap is SDRAM, behind a cache that no
 * gate here can say is coherent for code the loader writes and then runs
 * (docs/rapidus-cache.md), and the first megabyte is SRAM. */
static uint16_t banks1(uint16_t n);

uint16_t far_alloc_banks(uint16_t n)
{
    uint16_t level = 4, b;

    while (!(b = banks1(n)) && purge_next(&level))
        ;
    return b;
}

static uint16_t banks1(uint16_t n)
{
    uint16_t i;
    uint32_t bytes = (uint32_t)n << 16, a;

    if (!far_table || n == 0)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        a = (gap_lo(i) + 0xFFFFUL) & ~0xFFFFUL;
        if (a + bytes > gap_hi(i) || a + bytes < a)
            continue;
        if (!fb_insert(i, a, bytes))
            return 0;
        return (uint16_t)(a >> 16);
    }
    return 0;
}

static uint16_t fb_find(uint32_t addr)
{
    uint16_t i;

    for (i = 0; i < far_blocks; i++)
        if (fb_start(i) == addr)
            return i;
    return 0xFFFF;
}

uint16_t far_free(uint32_t addr)
{
    uint16_t i = fb_find(addr);

    if (i == 0xFFFF || i == 0)          /* not a block; or the table */
        return 0;
    fb_remove(i);
    return 1;
}

/* The block at addr becomes the system's: its owner's exit leaves it,
 * and only far_free gives it back.  The desktop's colour icons, kept
 * across its restarts (objc_sysvar G4_DESKICON, phase 89). */
uint16_t far_keep(uint32_t addr)
{
    uint16_t i = fb_find(addr);
    uint32_t at;

    if (i == 0xFFFF || i == 0)
        return 0;
    at = FB(i).at;
    at &= FB_ADDR;
    FB(i).at = at;
    at = FB(i).len;                     /* ...and no kind or sub-pool */
    at &= FB_LEN;
    FB(i).len = at;
    return 1;
}

void far_free_owner(uint8_t owner)
{
    uint16_t i = 1;

    if (!owner)                         /* the system's are for ever */
        return;
    while (i < far_blocks) {
        uint32_t at = FB(i).at;
        if ((uint8_t)(at >> 24) == owner)
            fb_remove(i);
        else
            i++;
    }
}

/* One sub-pool of an owner: its blocks whose tag says `sub`.  Sub-pool 0
 * is the owner's own memory and is not a sub-pool -- far_free_owner is
 * how that goes. */
void far_free_sub(uint8_t owner, uint8_t sub)
{
    uint16_t i = 1;

    if (!owner || !sub)
        return;
    while (i < far_blocks) {
        uint32_t at = FB(i).at, len = FB(i).len;
        if ((uint8_t)(at >> 24) == owner
            && OWN_SUB((uint8_t)(len >> 24)) == sub)
            fb_remove(i);
        else
            i++;
    }
}

uint16_t far_shrink(uint32_t addr, uint32_t bytes)
{
    uint16_t i = fb_find(addr);
    uint32_t len;

    if (i == 0xFFFF || i == 0)
        return 0;
    len = FB(i).len;
    if (bytes == 0 || bytes > (len & FB_LEN))
        return 0;
    FB(i).len = bytes | (len & ~FB_LEN);    /* the tag stays */
    return 1;
}

uint32_t far_size(uint32_t addr)
{
    uint16_t i = fb_find(addr);
    uint32_t len;

    if (i == 0xFFFF)
        return 0;
    len = FB(i).len;
    return len & FB_LEN;
}

/* The biggest request of kind `span` (0: inside a bank, 1: may cross) that
 * would succeed now. */
uint32_t far_largest(uint16_t span)
{
    uint16_t i;
    uint32_t best = 0, lo, hi, n, b;

    if (!far_table)
        return 0;
    for (i = 0; i <= far_blocks; i++) {
        lo = (gap_lo(i) + 3) & ~3UL;
        hi = gap_hi(i);
        if (hi <= lo)
            continue;
        if (span) {
            n = hi - lo;
        } else {
            n = 0;
            for (b = lo; b < hi; b = (b | 0xFFFFUL) + 1) {
                uint32_t e = (b | 0xFFFFUL) + 1;
                if (e > hi)
                    e = hi;
                if (e - b > n)
                    n = e - b;
            }
        }
        if (n > best)
            best = n;
    }
    return best;
}

/* An owner that has no blocks, for a program about to be loaded. */
uint8_t far_new_owner(void)
{
    static uint8_t next = 1;
    uint16_t tries, i;

    for (tries = 0; tries < 255; tries++) {
        uint8_t o = next;
        next = (uint8_t)(next == 255 ? 1 : next + 1);
        for (i = 0; i < far_blocks; i++) {
            uint32_t at = FB(i).at;
            if ((uint8_t)(at >> 24) == o)
                break;
        }
        if (i == far_blocks)
            return o;
    }
    return 0;
}
